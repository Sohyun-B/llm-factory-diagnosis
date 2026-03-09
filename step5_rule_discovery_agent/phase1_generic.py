"""
Phase 1 Generic: 도메인 무관 표준 거래 데이터 분석
- 어떤 거래(주문/발주/구매) 데이터든 돌릴 수 있는 분석만 포함
- 심어둔 패턴에 대한 사전 지식 없음
- 파라미터는 데이터 분포에서 자동 결정

입력: date, customer, item, quantity가 있는 CSV
      (선택) events CSV (date, customer, event_type, item)
출력: level0_results.json — LLM에게 전달할 통계 요약
"""

import pandas as pd
import numpy as np
from collections import Counter
from itertools import combinations
import json
import os
import sys

# === 설정 ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# === 데이터 로드 (스키마 자동 감지) ===
orders = pd.read_csv(os.path.join(DATA_DIR, "orders.csv"), encoding="utf-8-sig")
orders["date"] = pd.to_datetime(orders["date"])

has_events = os.path.exists(os.path.join(DATA_DIR, "events.csv"))
if has_events:
    events = pd.read_csv(os.path.join(DATA_DIR, "events.csv"), encoding="utf-8-sig")
    events["date"] = pd.to_datetime(events["date"])

# 스키마 보고
print("=" * 60)
print("0. 데이터 스키마")
print("=" * 60)
print(f"  주문 테이블: {len(orders)}행, 컬럼: {list(orders.columns)}")
print(f"  기간: {orders['date'].min().date()} ~ {orders['date'].max().date()}")
print(f"  고객 수: {orders['customer'].nunique()}")
print(f"  품목 수: {orders['item'].nunique()}")
if has_events:
    print(f"  이벤트 테이블: {len(events)}행, 컬럼: {list(events.columns)}")

results = {
    "schema": {
        "rows": len(orders),
        "date_range": [str(orders["date"].min().date()), str(orders["date"].max().date())],
        "customers": sorted(orders["customer"].unique().tolist()),
        "items": sorted(orders["item"].unique().tolist()),
        "n_customers": int(orders["customer"].nunique()),
        "n_items": int(orders["item"].nunique()),
    }
}


# ============================================================
# 분석 1: 전체 분포 요약 (기초 통계)
# ============================================================
print("\n" + "=" * 60)
print("1. 기초 분포")
print("=" * 60)

# 고객별 주문 건수
cust_counts = orders["customer"].value_counts()
print("\n고객별 주문 건수:")
for c, n in cust_counts.items():
    print(f"  {c}: {n}건")

# 품목별 주문 건수
item_counts = orders["item"].value_counts()
print("\n품목별 주문 건수 (상위):")
for i, n in item_counts.head(10).items():
    print(f"  {i}: {n}건")

# 수량 분포
print(f"\n수량 분포: mean={orders['quantity'].mean():.1f}, "
      f"median={orders['quantity'].median():.1f}, "
      f"std={orders['quantity'].std():.1f}, "
      f"min={orders['quantity'].min()}, max={orders['quantity'].max()}")

results["basic_distribution"] = {
    "customer_order_counts": {c: int(n) for c, n in cust_counts.items()},
    "item_order_counts": {i: int(n) for i, n in item_counts.items()},
    "quantity_stats": {
        "mean": round(float(orders["quantity"].mean()), 1),
        "median": round(float(orders["quantity"].median()), 1),
        "std": round(float(orders["quantity"].std()), 1),
        "min": int(orders["quantity"].min()),
        "max": int(orders["quantity"].max()),
    }
}


# ============================================================
# 분석 2: 고객-품목별 주문 간격 분석
# - 파라미터: 없음 (모든 조합을 자동 분석)
# - 최소 3건 이상인 조합만
# ============================================================
print("\n" + "=" * 60)
print("2. 고객-품목별 주문 간격")
print("=" * 60)

MIN_ORDERS = 3  # 간격 분석 최소 건수
interval_results = {}

for (customer, item), group in orders.groupby(["customer", "item"]):
    if len(group) < MIN_ORDERS:
        continue

    dates = group.sort_values("date")["date"].values
    intervals = np.diff(dates).astype("timedelta64[D]").astype(int)

    mean_iv = float(np.mean(intervals))
    std_iv = float(np.std(intervals))
    cv = std_iv / mean_iv if mean_iv > 0 else float("inf")

    key = f"{customer}/{item}"
    interval_results[key] = {
        "customer": customer,
        "item": item,
        "count": len(group),
        "mean_interval": round(mean_iv, 1),
        "std_interval": round(std_iv, 1),
        "median_interval": round(float(np.median(intervals)), 1),
        "cv": round(cv, 2),
        "min_interval": int(np.min(intervals)),
        "max_interval": int(np.max(intervals)),
        "intervals": [int(i) for i in intervals],
    }

# CV 기준 정렬 — 규칙적인 것부터
sorted_intervals = sorted(interval_results.items(), key=lambda x: x[1]["cv"])

print("\n규칙성 순서 (CV 낮을수록 규칙적):")
for key, stats in sorted_intervals:
    regularity = "매우 규칙적" if stats["cv"] < 0.2 else \
                 "규칙적" if stats["cv"] < 0.5 else \
                 "불규칙"
    print(f"  {key}: {stats['count']}건, 평균 {stats['mean_interval']}일, "
          f"CV={stats['cv']} ({regularity})")

results["interval_analysis"] = interval_results


# ============================================================
# 분석 3: 시간 패턴 (월별/요일별/주차별)
# - 전체 + 고객별
# ============================================================
print("\n" + "=" * 60)
print("3. 시간 패턴")
print("=" * 60)

orders["month"] = orders["date"].dt.month
orders["weekday"] = orders["date"].dt.weekday  # 0=월
orders["day_of_month"] = orders["date"].dt.day
orders["week_of_month"] = (orders["date"].dt.day - 1) // 7 + 1
orders["year_month"] = orders["date"].dt.to_period("M").astype(str)

# 월별 집계
monthly = orders.groupby("year_month").agg(
    orders=("order_id", "count"),
    total_qty=("quantity", "sum"),
).to_dict(orient="index")

print("\n월별:")
for ym, stats in sorted(monthly.items()):
    print(f"  {ym}: {stats['orders']}건, 수량 {stats['total_qty']}")

# 요일 분포 (전체)
weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
wd_dist = orders["weekday"].value_counts().sort_index()
print("\n요일 분포 (전체):")
for wd, cnt in wd_dist.items():
    print(f"  {weekday_names[wd]}: {cnt}건")

# 고객별 시간 집중도
time_concentration = {}
for customer in orders["customer"].unique():
    cust = orders[orders["customer"] == customer]
    n = len(cust)
    if n < 5:
        continue

    # 요일 집중도 (엔트로피 기반)
    wd_counts = cust["weekday"].value_counts()
    wd_probs = wd_counts / n
    wd_entropy = -sum(p * np.log2(p) for p in wd_probs if p > 0)
    max_entropy = np.log2(min(5, len(wd_counts)))
    wd_concentration = round(1 - wd_entropy / max_entropy, 2) if max_entropy > 0 else 0

    # 주차 집중도
    wom_counts = cust["week_of_month"].value_counts()
    wom_probs = wom_counts / n
    wom_entropy = -sum(p * np.log2(p) for p in wom_probs if p > 0)
    max_wom_entropy = np.log2(len(wom_counts))
    wom_concentration = round(1 - wom_entropy / max_wom_entropy, 2) if max_wom_entropy > 0 else 0

    # 월 집중도 (특정 달에 몰리는지)
    month_counts = cust["month"].value_counts()
    month_probs = month_counts / n
    month_entropy = -sum(p * np.log2(p) for p in month_probs if p > 0)
    max_month_entropy = np.log2(len(month_counts))
    month_concentration = round(1 - month_entropy / max_month_entropy, 2) if max_month_entropy > 0 else 0

    time_concentration[customer] = {
        "weekday_concentration": wd_concentration,
        "dominant_weekday": weekday_names[wd_counts.idxmax()],
        "week_of_month_concentration": wom_concentration,
        "dominant_week": f"W{wom_counts.idxmax()}",
        "month_concentration": month_concentration,
        "active_months": sorted([int(m) for m in month_counts.index]),
        "weekday_dist": {weekday_names[int(k)]: int(v) for k, v in wd_counts.items()},
        "week_dist": {f"W{int(k)}": int(v) for k, v in wom_counts.items()},
    }

    if wd_concentration > 0.15 or wom_concentration > 0.15 or month_concentration > 0.15:
        flags = []
        if wd_concentration > 0.15:
            flags.append(f"요일 집중({weekday_names[wd_counts.idxmax()]})")
        if wom_concentration > 0.15:
            flags.append(f"주차 집중(W{wom_counts.idxmax()})")
        if month_concentration > 0.15:
            flags.append(f"월 집중")
        print(f"\n  {customer}: {', '.join(flags)}")

results["time_patterns"] = {
    "monthly": {k: {kk: int(vv) for kk, vv in v.items()} for k, v in monthly.items()},
    "customer_time_concentration": time_concentration,
}


# ============================================================
# 분석 4: 수량 패턴 (고객-품목별 수량 분포)
# - 수량에 군집이 있는지 (bimodal 등)
# ============================================================
print("\n" + "=" * 60)
print("4. 수량 패턴")
print("=" * 60)

quantity_patterns = {}
for (customer, item), group in orders.groupby(["customer", "item"]):
    if len(group) < 5:
        continue

    qtys = group["quantity"].values
    mean_q = float(np.mean(qtys))
    std_q = float(np.std(qtys))
    cv_q = std_q / mean_q if mean_q > 0 else 0

    # 간단한 bimodal 감지: 중앙값 기준 위아래로 분리, 각 그룹 평균 차이
    median_q = np.median(qtys)
    low_group = qtys[qtys <= median_q]
    high_group = qtys[qtys > median_q]

    bimodal_score = 0
    if len(low_group) >= 2 and len(high_group) >= 2:
        gap = np.mean(high_group) - np.mean(low_group)
        bimodal_score = round(gap / (std_q + 1e-6), 2)

    key = f"{customer}/{item}"
    quantity_patterns[key] = {
        "count": len(group),
        "mean": round(mean_q, 1),
        "std": round(std_q, 1),
        "cv": round(cv_q, 2),
        "min": int(np.min(qtys)),
        "max": int(np.max(qtys)),
        "values": sorted([int(q) for q in qtys]),
        "bimodal_score": bimodal_score,
    }

    if bimodal_score > 1.5:
        print(f"  {key}: 수량 이봉 분포 의심 (score={bimodal_score})")
        print(f"    하위 그룹: {sorted([int(q) for q in low_group])}")
        print(f"    상위 그룹: {sorted([int(q) for q in high_group])}")

results["quantity_patterns"] = quantity_patterns


# ============================================================
# 분석 5: 품목 동반 주문 (Co-occurrence)
# - 같은 고객이 같은 주에 주문한 품목 쌍
# - 파라미터: 윈도우 = 7일 (1주)
# ============================================================
print("\n" + "=" * 60)
print("5. 품목 동반 주문")
print("=" * 60)

orders["year_week"] = orders["date"].dt.isocalendar().apply(
    lambda x: f"{x.year}-W{x.week:02d}", axis=1)

co_occurrence = Counter()
basket_count = 0

for (customer, yw), group in orders.groupby(["customer", "year_week"]):
    items = sorted(group["item"].unique())
    if len(items) >= 2:
        basket_count += 1
        for i1, i2 in combinations(items, 2):
            co_occurrence[(i1, i2)] += 1

# 전체 주문 바스켓 수 대비 support
total_baskets = len(orders.groupby(["customer", "year_week"]))
co_occ_results = []
for (i1, i2), count in co_occurrence.most_common(15):
    if count >= 2:
        support = count / total_baskets
        co_occ_results.append({
            "item_a": i1,
            "item_b": i2,
            "count": count,
            "support": round(support, 3),
        })
        print(f"  {i1} + {i2}: {count}회 (support={support:.3f})")

results["co_occurrence"] = co_occ_results


# ============================================================
# 분석 6: 고객 간 시간 근접성 (일반화된 교차 분석)
# - 모든 고객 쌍에 대해, 발주일 간의 시차 분포를 계산
# - lag 범위: 데이터 기반 자동 설정 (평균 간격의 0.1~0.5배)
# ============================================================
print("\n" + "=" * 60)
print("6. 고객 간 시간 근접성")
print("=" * 60)

# 전체 평균 간격 계산 (lag 범위 자동 설정용)
all_intervals = []
for customer in orders["customer"].unique():
    dates = sorted(orders[orders["customer"] == customer]["date"].unique())
    if len(dates) >= 2:
        ivs = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
        all_intervals.extend(ivs)

global_mean_interval = np.mean(all_intervals) if all_intervals else 14
# lag 범위: 1일 ~ 평균간격의 0.5배 (최소 3일, 최대 14일)
max_lag = max(3, min(14, int(global_mean_interval * 0.5)))
print(f"  자동 설정: 전체 평균 간격={global_mean_interval:.1f}일, 탐색 lag=1~{max_lag}일")

customer_proximity = []
customers = orders["customer"].unique()

for c1, c2 in combinations(customers, 2):
    c1_dates = sorted(orders[orders["customer"] == c1]["date"].dt.normalize().unique())
    c2_dates = sorted(orders[orders["customer"] == c2]["date"].dt.normalize().unique())

    if len(c1_dates) < 3 or len(c2_dates) < 3:
        continue

    # c1 발주 후 1~max_lag일 내 c2 발주
    follow_count = 0
    for d1 in c1_dates:
        for d2 in c2_dates:
            diff = (d2 - d1).days
            if 1 <= diff <= max_lag:
                follow_count += 1
                break

    prob = follow_count / len(c1_dates)

    # 역방향도 확인
    reverse_count = 0
    for d2 in c2_dates:
        for d1 in c1_dates:
            diff = (d1 - d2).days
            if 1 <= diff <= max_lag:
                reverse_count += 1
                break

    reverse_prob = reverse_count / len(c2_dates)

    # 랜덤 기대치: c2가 1년에 n건이면, max_lag일 윈도우에 걸릴 확률
    # ≈ 1 - (1 - max_lag/365) ^ len(c2_dates_in_period)
    days_span = (max(c2_dates) - min(c2_dates)).days + 1
    expected_prob = min(1.0, len(c2_dates) * max_lag / days_span) if days_span > 0 else 0

    # 기대치 대비 유의미하게 높은 것만 보고
    if prob > expected_prob * 1.3 and follow_count >= 3:
        customer_proximity.append({
            "from": c1,
            "to": c2,
            "lag_window": f"1~{max_lag}일",
            "follow_count": follow_count,
            "total": len(c1_dates),
            "probability": round(prob, 2),
            "expected_random": round(expected_prob, 2),
            "lift": round(prob / expected_prob, 2) if expected_prob > 0 else float("inf"),
        })

    if reverse_prob > expected_prob * 1.3 and reverse_count >= 3:
        customer_proximity.append({
            "from": c2,
            "to": c1,
            "lag_window": f"1~{max_lag}일",
            "follow_count": reverse_count,
            "total": len(c2_dates),
            "probability": round(reverse_prob, 2),
            "expected_random": round(expected_prob, 2),
            "lift": round(reverse_prob / expected_prob, 2) if expected_prob > 0 else float("inf"),
        })

# lift 순 정렬
customer_proximity.sort(key=lambda x: -x["lift"])
for cp in customer_proximity[:10]:
    print(f"  {cp['from']} → {cp['to']}: {cp['follow_count']}/{cp['total']} = {cp['probability']:.0%} "
          f"(기대 {cp['expected_random']:.0%}, lift={cp['lift']})")

results["customer_proximity"] = customer_proximity


# ============================================================
# 분석 7: 시계열 추세 변화 (Rolling window)
# - 고객-품목별 간격의 시간에 따른 변화
# - 윈도우: 데이터 건수의 1/3
# ============================================================
print("\n" + "=" * 60)
print("7. 간격 추세 변화")
print("=" * 60)

trend_changes = {}
for key, stats in interval_results.items():
    intervals = stats["intervals"]
    if len(intervals) < 6:
        continue

    # 3등분 비교
    n = len(intervals)
    third = n // 3
    first = intervals[:third]
    middle = intervals[third:2*third]
    last = intervals[2*third:]

    mean_first = np.mean(first)
    mean_last = np.mean(last)
    change = mean_last - mean_first
    pct_change = change / mean_first * 100 if mean_first > 0 else 0

    # 단조 증가/감소 경향 (Spearman 상관)
    from scipy.stats import spearmanr
    rho, p_value = spearmanr(range(len(intervals)), intervals)

    trend_changes[key] = {
        "first_third_mean": round(float(mean_first), 1),
        "middle_third_mean": round(float(np.mean(middle)), 1),
        "last_third_mean": round(float(mean_last), 1),
        "absolute_change": round(float(change), 1),
        "pct_change": round(float(pct_change), 1),
        "spearman_rho": round(float(rho), 3),
        "spearman_p": round(float(p_value), 3),
        "intervals": intervals,
    }

    if abs(rho) > 0.3 or abs(pct_change) > 30:
        direction = "증가" if change > 0 else "감소"
        sig = f"p={p_value:.3f}" if p_value < 0.1 else "비유의"
        print(f"  {key}: {mean_first:.1f} → {mean_last:.1f}일 ({direction} {abs(pct_change):.0f}%), "
              f"rho={rho:.3f} ({sig})")

results["trend_changes"] = trend_changes


# ============================================================
# 분석 8: 이벤트-주문 시차 (이벤트 테이블이 있을 때만)
# - 모든 고객 × 이벤트 유형에 대해 자동 분석
# - lag 범위: 1~30일
# ============================================================
if has_events:
    print("\n" + "=" * 60)
    print("8. 이벤트 → 주문 시차")
    print("=" * 60)

    event_lag_results = {}
    MAX_EVENT_LAG = 30

    for (customer, etype), egroup in events.groupby(["customer", "event_type"]):
        if len(egroup) < 2:
            continue

        cust_orders = orders[orders["customer"] == customer].sort_values("date")
        lags = []
        item_matches = 0

        for _, ev in egroup.iterrows():
            followers = cust_orders[
                (cust_orders["date"] > ev["date"]) &
                (cust_orders["date"] <= ev["date"] + pd.Timedelta(days=MAX_EVENT_LAG))
            ]
            if len(followers) > 0:
                f = followers.iloc[0]
                lag = (f["date"] - ev["date"]).days
                lags.append(lag)
                if pd.notna(ev.get("item")) and ev["item"] == f["item"]:
                    item_matches += 1

        if len(lags) >= 2:
            key = f"{customer}/{etype}"
            event_lag_results[key] = {
                "customer": customer,
                "event_type": etype,
                "event_count": len(egroup),
                "followed_by_order": len(lags),
                "follow_rate": round(len(lags) / len(egroup), 2),
                "mean_lag": round(float(np.mean(lags)), 1),
                "std_lag": round(float(np.std(lags)), 1),
                "median_lag": round(float(np.median(lags)), 1),
                "item_match_count": item_matches,
                "item_match_rate": round(item_matches / len(lags), 2) if lags else 0,
                "lags": lags,
            }

            print(f"  {key}: {len(lags)}/{len(egroup)} 후속주문 ({len(lags)/len(egroup):.0%}), "
                  f"평균 {np.mean(lags):.1f}일, 품목일치 {item_matches}/{len(lags)}")

    results["event_order_lag"] = event_lag_results


# ============================================================
# 저장
# ============================================================
def convert(obj):
    if isinstance(obj, (np.integer,)): return int(obj)
    elif isinstance(obj, (np.floating,)): return float(obj)
    elif isinstance(obj, np.ndarray): return obj.tolist()
    elif isinstance(obj, pd.Timestamp): return str(obj.date())
    return obj

def deep_convert(obj):
    if isinstance(obj, dict):
        return {str(k): deep_convert(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [deep_convert(i) for i in obj]
    return convert(obj)

results = deep_convert(results)

out_path = os.path.join(DATA_DIR, "level0_results.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n{'='*60}")
print(f"Level 0 결과 저장: {out_path}")
print(f"분석 항목: {list(results.keys())}")
