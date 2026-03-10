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
import argparse

# === 설정 ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

parser = argparse.ArgumentParser(description="Phase 1 Generic: 도메인 무관 표준 거래 데이터 분석")
parser.add_argument("--data-dir", default=os.path.join(BASE_DIR, "synthetic", "data"),
                    help="입력 데이터 디렉토리 (default: synthetic/data/)")
parser.add_argument("--output-dir", default=None,
                    help="결과 출력 디렉토리 (default: <data-dir>/../results/)")
args = parser.parse_args()

DATA_DIR = os.path.abspath(args.data_dir)
OUTPUT_DIR = os.path.abspath(args.output_dir) if args.output_dir else \
    os.path.join(os.path.dirname(DATA_DIR), "results")
os.makedirs(OUTPUT_DIR, exist_ok=True)

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
# 분석 4.5: 혼합 패턴 분해 (Layer 1.5 — GMM)
# - 간격 CV > 0.5인 조합에 대해 GMM(1~3) 적합
# - BIC로 최적 component 수 선택
# - 각 간격에 component 라벨 부여
# ============================================================
print("\n" + "=" * 60)
print("4.5. 혼합 패턴 분해 (GMM)")
print("=" * 60)

try:
    from sklearn.mixture import GaussianMixture
    HAS_GMM = True
except ImportError:
    print("  (sklearn 미설치 — GMM 분석 스킵)")
    HAS_GMM = False

gmm_results = {}

if HAS_GMM:
    for key, stats in interval_results.items():
        intervals_arr = np.array(stats["intervals"], dtype=float)

        if len(intervals_arr) < 6:
            continue

        cv = stats["cv"]
        bimodal = quantity_patterns.get(key, {}).get("bimodal_score", 0)

        # 트리거: CV > 0.5 (간격 불규칙) 또는 수량 bimodal > 1.5
        if cv <= 0.5 and bimodal <= 1.5:
            continue

        X = intervals_arr.reshape(-1, 1)

        # BIC로 최적 component 수 선택 (1~3)
        bic_scores = {}
        models = {}
        max_n = min(4, max(2, len(intervals_arr) // 3))

        for n_comp in range(1, max_n):
            try:
                gmm = GaussianMixture(n_components=n_comp, random_state=42, max_iter=200)
                gmm.fit(X)
                bic_scores[n_comp] = gmm.bic(X)
                models[n_comp] = gmm
            except Exception:
                continue

        if not bic_scores:
            continue

        best_n = min(bic_scores, key=bic_scores.get)

        # Ashman D fallback: BIC가 1을 선호해도, 2-component가
        # 잘 분리되면 (D > 2.0) 2를 채택
        if best_n == 1 and 2 in models:
            gmm2 = models[2]
            m1, m2 = gmm2.means_.flatten()
            s1, s2 = np.sqrt(gmm2.covariances_.flatten())
            ashman_d = abs(m1 - m2) * np.sqrt(2) / np.sqrt(s1**2 + s2**2)
            if ashman_d > 2.0:
                best_n = 2

        best_model = models[best_n]
        labels = best_model.predict(X)

        components = []
        for c in range(best_n):
            mask = labels == c
            comp_ivs = intervals_arr[mask]
            if len(comp_ivs) == 0:
                continue
            components.append({
                "id": int(c),
                "mean": round(float(np.mean(comp_ivs)), 1),
                "std": round(float(np.std(comp_ivs)), 1),
                "count": int(mask.sum()),
                "pct": round(float(mask.sum() / len(intervals_arr) * 100), 1),
                "indices": [int(i) for i in np.where(mask)[0]],
                "values": [int(v) for v in comp_ivs],
            })

        # 건수 기준 내림차순 (주 패턴 = 가장 많은 것)
        components.sort(key=lambda x: -x["count"])

        gmm_results[key] = {
            "trigger": f"CV={cv}" if cv > 0.5 else f"bimodal={bimodal}",
            "n_components": best_n,
            "bic_scores": {str(k): round(v, 1) for k, v in bic_scores.items()},
            "components": components,
            "labels": [int(l) for l in labels],
        }

        if best_n >= 2:
            print(f"\n  {key}: {best_n} components "
                  f"(trigger: {'CV>0.5' if cv > 0.5 else 'bimodal'})")
            for comp in components:
                print(f"    Component {comp['id']}: "
                      f"mean={comp['mean']}일, std={comp['std']}일, "
                      f"n={comp['count']} ({comp['pct']}%)")
        else:
            print(f"  {key}: 단일 분포 (GMM best_n=1)")

if not gmm_results:
    print("  (GMM 트리거 조건을 충족하는 조합 없음)")

results["gmm_mixture"] = gmm_results


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
# 분석 6.5: Component 분리 재분석 (Layer 2.5)
# - GMM 2+ component인 조합: 주 component drift 재분석
# - 부 component: 교차 패턴 후보 확인
# ============================================================
print("\n" + "=" * 60)
print("6.5. Component 분리 재분석 (Layer 2.5)")
print("=" * 60)

from scipy.stats import spearmanr as _spearmanr_25

component_reanalysis = {}

for key, gmm_info in gmm_results.items():
    if gmm_info["n_components"] < 2:
        continue

    stats = interval_results[key]
    all_ivs = np.array(stats["intervals"])
    customer = stats["customer"]
    item = stats["item"]

    print(f"\n  === {key} ===")

    # 이 고객-품목의 주문 날짜 목록
    cust_item_orders = orders[
        (orders["customer"] == customer) & (orders["item"] == item)
    ].sort_values("date").reset_index(drop=True)

    entry = {"components": []}

    for comp in gmm_info["components"]:
        comp_id = comp["id"]
        comp_intervals = np.array(comp["values"], dtype=float)
        comp_indices = comp["indices"]
        is_main = (comp == gmm_info["components"][0])

        comp_result = {
            "component_id": comp_id,
            "n": len(comp_intervals),
            "mean": comp["mean"],
            "is_main": is_main,
        }

        # --- Drift 재분석 (6건 이상 component) ---
        if len(comp_intervals) >= 6:
            n_ci = len(comp_intervals)
            third = max(1, n_ci // 3)
            first_third = comp_intervals[:third]
            last_third = comp_intervals[-third:]

            mean_first = float(np.mean(first_third))
            mean_last = float(np.mean(last_third))
            change = mean_last - mean_first
            pct_change = change / mean_first * 100 if mean_first > 0 else 0

            rho, p_val = _spearmanr_25(range(n_ci), comp_intervals)

            comp_result["drift"] = {
                "first_third_mean": round(mean_first, 1),
                "last_third_mean": round(mean_last, 1),
                "change": round(change, 1),
                "pct_change": round(pct_change, 1),
                "spearman_rho": round(float(rho), 3),
                "spearman_p": round(float(p_val), 3),
            }

            drift_detected = abs(rho) > 0.3 or abs(pct_change) > 20
            comp_result["drift_detected"] = drift_detected

            if drift_detected:
                direction = "증가" if change > 0 else "감소"
                sig = f"p={p_val:.3f}" if p_val < 0.1 else "비유의"
                print(f"    ★ Component {comp_id} DRIFT: "
                      f"{mean_first:.1f} → {mean_last:.1f}일 "
                      f"({direction} {abs(pct_change):.0f}%), "
                      f"rho={rho:.3f} ({sig})")

        # --- 부 component: 교차 패턴 확인 ---
        if not is_main and len(comp_indices) >= 2:
            cross_hits = Counter()

            for idx in comp_indices:
                order_pos = idx + 1  # 짧은 간격 뒤에 도착한 주문
                if order_pos < len(cust_item_orders):
                    triggered_date = cust_item_orders.iloc[order_pos]["date"]

                    # 7일 이내 선행 주문 (다른 고객)
                    nearby = orders[
                        (orders["customer"] != customer) &
                        (orders["date"] >= triggered_date - pd.Timedelta(days=7)) &
                        (orders["date"] < triggered_date)
                    ]

                    for _, row in nearby.iterrows():
                        lag = (triggered_date - row["date"]).days
                        if 1 <= lag <= 5:
                            cross_hits[(row["customer"], row["item"])] += 1

            if cross_hits:
                top_precursors = cross_hits.most_common(3)
                comp_result["cross_pattern_candidates"] = [
                    {"precursor": f"{c}/{i}", "count": cnt,
                     "total": len(comp_indices)}
                    for (c, i), cnt in top_precursors
                ]
                for (c, i), cnt in top_precursors:
                    rate = cnt / len(comp_indices) * 100
                    print(f"    Component {comp_id} 교차 후보: "
                          f"{c}/{i} → {cnt}/{len(comp_indices)} ({rate:.0f}%)")

        entry["components"].append(comp_result)

    # --- 정제된 drift 분석: 교차 패턴 촉발 주문 식별 후 제거 ---
    # 전략: (1) GMM 부 component 인접 주문 중 선행자 있는 것
    #       (2) 선행자 + 저수량(Q25 이하)인 추가 주문
    best_precursor = None
    for cr in entry["components"]:
        for cp in cr.get("cross_pattern_candidates", []):
            if best_precursor is None or cp["count"] > best_precursor["count"]:
                best_precursor = cp

    if best_precursor and best_precursor["count"] >= 2:
        prec_parts = best_precursor["precursor"].split("/")
        prec_cust, prec_item = prec_parts[0], "/".join(prec_parts[1:])

        def has_precursor(pos):
            """pos 위치의 주문 1~5일 전에 선행 주문이 있는지 확인"""
            if pos >= len(cust_item_orders):
                return False, 999
            od = cust_item_orders.iloc[pos]["date"]
            nearby = orders[
                (orders["customer"] == prec_cust) &
                (orders["item"] == prec_item) &
                (orders["date"] >= od - pd.Timedelta(days=5)) &
                (orders["date"] < od)
            ]
            for _, row in nearby.iterrows():
                lag = (od - row["date"]).days
                if 1 <= lag <= 5:
                    return True, lag
            return False, 999

        triggered_positions = set()

        # (1) 부 component 인접 주문 → 선행자로 P4 식별
        for comp in gmm_info["components"][1:]:
            for idx in comp["indices"]:
                has_i, lag_i = has_precursor(idx)
                has_j, lag_j = has_precursor(idx + 1)
                if has_i and (not has_j or lag_i <= lag_j):
                    triggered_positions.add(idx)
                elif has_j:
                    triggered_positions.add(idx + 1)
                else:
                    triggered_positions.add(idx + 1)  # 기본: 뒤쪽 제거

        # (2) GMM이 놓친 P4: 선행자 있고 + 수량 < Q25
        q25_qty = cust_item_orders["quantity"].quantile(0.25)
        for pos in range(len(cust_item_orders)):
            if pos in triggered_positions:
                continue
            has_p, _ = has_precursor(pos)
            if has_p and cust_item_orders.iloc[pos]["quantity"] < q25_qty:
                triggered_positions.add(pos)

        if triggered_positions and \
                len(cust_item_orders) - len(triggered_positions) >= 6:
            clean_mask = np.ones(len(cust_item_orders), dtype=bool)
            for pos in triggered_positions:
                clean_mask[pos] = False

            clean_orders = cust_item_orders[clean_mask]
            clean_dates = clean_orders["date"].values
            clean_ivs = np.diff(clean_dates).astype(
                "timedelta64[D]").astype(int).astype(float)

            if len(clean_ivs) >= 6:
                n_ci = len(clean_ivs)
                third = max(1, n_ci // 3)
                first_third = clean_ivs[:third]
                last_third = clean_ivs[-third:]

                mean_first = float(np.mean(first_third))
                mean_last = float(np.mean(last_third))
                change = mean_last - mean_first
                pct_change = change / mean_first * 100 if mean_first > 0 else 0

                rho, p_val = _spearmanr_25(range(n_ci), clean_ivs)

                entry["cleaned_drift"] = {
                    "precursor": best_precursor["precursor"],
                    "removed_orders": len(triggered_positions),
                    "remaining_intervals": n_ci,
                    "clean_intervals": [int(x) for x in clean_ivs],
                    "first_third_mean": round(mean_first, 1),
                    "last_third_mean": round(mean_last, 1),
                    "change": round(change, 1),
                    "pct_change": round(pct_change, 1),
                    "spearman_rho": round(float(rho), 3),
                    "spearman_p": round(float(p_val), 3),
                    "detected": bool(abs(rho) > 0.3 or abs(pct_change) > 20),
                }

                if entry["cleaned_drift"]["detected"]:
                    direction = "증가" if change > 0 else "감소"
                    sig = f"p={p_val:.3f}" if p_val < 0.1 else "비유의"
                    print(f"    ★★ CLEANED DRIFT: "
                          f"{mean_first:.1f} → {mean_last:.1f}일 "
                          f"({direction} {abs(pct_change):.0f}%), "
                          f"rho={rho:.3f} ({sig})")
                    print(f"       ({best_precursor['precursor']} 선행 "
                          f"{len(triggered_positions)}건 제거, "
                          f"{n_ci}개 간격 분석)")

    component_reanalysis[key] = entry

if not component_reanalysis:
    print("  (2+ component 조합 없음)")

results["component_reanalysis"] = component_reanalysis


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
# 분석 7.5: 다중 조건 연관 (Layer 3.5)
# - 월별 윈도우 기반 조건 변수 생성
# - 유의미한 단일 조건 쌍만 교차 검증
# - P(C|A∧B) vs P(C|A), P(C|B) 비교
# ============================================================
print("\n" + "=" * 60)
print("7.5. 다중 조건 연관 (Layer 3.5)")
print("=" * 60)

all_months = sorted(orders["year_month"].unique())
active_months = all_months[:-1]  # 마지막 달은 타겟 없음
n_months = len(active_months)

# --- 월별 조건/타겟 변수 생성 ---
monthly_conditions = {}
monthly_targets = {}

# 사전 집계: 고객-품목별 월별 수량
ci_monthly = orders.groupby(["customer", "item", "year_month"])["quantity"].sum()
# 고객-품목별 Q75 사전 계산
ci_q75 = orders.groupby(["customer", "item"])["quantity"].quantile(0.75)
ym_levels = set(ci_monthly.index.get_level_values("year_month"))

for ym in all_months:
    conditions = {}
    targets = {}
    month_num = pd.Period(ym).month

    # 고객-품목 조건: 주문 여부 + 수량 상위
    if ym in ym_levels:
        for (cust, itm), qty_sum in ci_monthly.xs(ym, level="year_month").items():
            ckey = f"{cust}/{itm}"
            conditions[f"ordered:{ckey}"] = True

            q75_val = ci_q75.get((cust, itm), None)
            if q75_val is not None and qty_sum >= q75_val:
                conditions[f"high_qty:{ckey}"] = True

    # 계절 조건
    season = {3: "spring", 4: "spring", 5: "spring",
              6: "summer", 7: "summer", 8: "summer",
              9: "fall", 10: "fall", 11: "fall"}.get(month_num, "winter")
    conditions[f"season:{season}"] = True

    # 이벤트 조건
    if has_events:
        month_evts = events[events["date"].dt.to_period("M").astype(str) == ym]
        for _, ev in month_evts.iterrows():
            conditions[f"event:{ev['customer']}/{ev['event_type']}"] = True

    # 타겟: 다음 달 주문 여부
    ym_idx = all_months.index(ym)
    if ym_idx + 1 < len(all_months):
        next_ym = all_months[ym_idx + 1]
        if next_ym in ym_levels:
            for (cust, itm), _ in ci_monthly.xs(next_ym, level="year_month").items():
                targets[f"next:{cust}/{itm}"] = True

    monthly_conditions[ym] = conditions
    monthly_targets[ym] = targets

# --- 빈번한 조건/타겟 필터 ---
cond_counts = Counter()
target_counts = Counter()
for ym in active_months:
    for c in monthly_conditions.get(ym, {}):
        cond_counts[c] += 1
    for t in monthly_targets.get(ym, {}):
        target_counts[t] += 1

freq_conditions = {c for c, n in cond_counts.items() if n >= 3}
freq_targets = {t for t, n in target_counts.items() if n >= 3}

print(f"  조건 변수: {len(freq_conditions)}개 (3회+), 타겟: {len(freq_targets)}개")

# --- 단일 조건 → 타겟 연관 ---
single_assoc = {}
for target in freq_targets:
    p_target = target_counts[target] / n_months

    for cond in freq_conditions:
        both = 0
        cond_total = 0
        for ym in active_months:
            has_cond = cond in monthly_conditions.get(ym, {})
            has_target = target in monthly_targets.get(ym, {})
            if has_cond:
                cond_total += 1
                if has_target:
                    both += 1

        if cond_total >= 3 and both >= 1:
            p_given_cond = both / cond_total
            lift = p_given_cond / p_target if p_target > 0 else 0

            if lift > 1.0:
                single_assoc[(cond, target)] = {
                    "p_target": round(p_target, 3),
                    "p_given_cond": round(p_given_cond, 3),
                    "lift": round(lift, 2),
                    "support": both,
                }

print(f"  단일 연관 (lift>1.0): {len(single_assoc)}개")

# --- 다중 조건 교차 검증 ---
multi_condition_results = []
targets_with_conds = {}
for (cond, target), info in single_assoc.items():
    targets_with_conds.setdefault(target, []).append((cond, info))

for target, cond_list in targets_with_conds.items():
    if len(cond_list) < 2:
        continue

    p_target = target_counts[target] / n_months

    for i in range(len(cond_list)):
        for j in range(i + 1, len(cond_list)):
            cond_a, info_a = cond_list[i]
            cond_b, info_b = cond_list[j]

            ab_count = 0
            ab_target = 0
            for ym in active_months:
                has_a = cond_a in monthly_conditions.get(ym, {})
                has_b = cond_b in monthly_conditions.get(ym, {})
                has_t = target in monthly_targets.get(ym, {})
                if has_a and has_b:
                    ab_count += 1
                    if has_t:
                        ab_target += 1

            if ab_count < 2:
                continue

            p_given_ab = ab_target / ab_count
            interaction = p_given_ab - max(info_a["p_given_cond"],
                                           info_b["p_given_cond"])

            if (p_given_ab > info_a["p_given_cond"] * 1.3 and
                    p_given_ab > info_b["p_given_cond"] * 1.3 and
                    p_given_ab > p_target * 1.5):

                multi_condition_results.append({
                    "condition_a": cond_a,
                    "condition_b": cond_b,
                    "target": target,
                    "p_target": round(p_target, 3),
                    "p_given_a": info_a["p_given_cond"],
                    "p_given_b": info_b["p_given_cond"],
                    "p_given_ab": round(p_given_ab, 3),
                    "ab_count": ab_count,
                    "ab_target": ab_target,
                    "interaction_score": round(interaction, 3),
                    "lift_ab": round(p_given_ab / p_target, 2) if p_target > 0 else 0,
                })

multi_condition_results.sort(key=lambda x: -x["interaction_score"])

if multi_condition_results:
    print(f"\n  다중 조건 규칙: {len(multi_condition_results)}개")
    for r in multi_condition_results[:10]:
        print(f"    {r['condition_a']} AND {r['condition_b']}")
        print(f"      → {r['target']}")
        print(f"      P={r['p_given_ab']:.0%} (A만:{r['p_given_a']:.0%}, "
              f"B만:{r['p_given_b']:.0%}, 기본:{r['p_target']:.0%})")
else:
    print("  (다중 조건 규칙 미발견 — 단일 조건으로 충분히 설명)")

results["multi_condition"] = {
    "n_conditions": len(freq_conditions),
    "n_targets": len(freq_targets),
    "n_single_associations": len(single_assoc),
    "top_single_associations": sorted(
        [{"condition": c, "target": t, **v}
         for (c, t), v in single_assoc.items()],
        key=lambda x: -x["lift"]
    )[:20],
    "multi_condition_rules": multi_condition_results[:20],
}


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
    if isinstance(obj, (np.bool_,)): return bool(obj)
    elif isinstance(obj, (np.integer,)): return int(obj)
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

out_path = os.path.join(OUTPUT_DIR, "level0_results.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n{'='*60}")
print(f"Level 0 결과 저장: {out_path}")
print(f"분석 항목: {list(results.keys())}")
