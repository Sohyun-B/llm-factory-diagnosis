"""
Phase 1: 통계적 빅 픽처 분석
- 자기상관 (고객별 발주 간격 패턴)
- 교차상관 (고객 간 발주 시점 연관)
- 계절성 분해
- 품목 동반 발주 (Co-occurrence)
- 요일/주차 분포
- 이벤트-발주 시차 분석

출력: phase1_results.json (LLM 에이전트에게 전달할 통계 요약)
"""

import pandas as pd
import numpy as np
from collections import defaultdict, Counter
from itertools import combinations
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# === 데이터 로드 ===
orders = pd.read_csv(os.path.join(DATA_DIR, "orders.csv"), encoding="utf-8-sig")
events = pd.read_csv(os.path.join(DATA_DIR, "events.csv"), encoding="utf-8-sig")
orders["date"] = pd.to_datetime(orders["date"])
events["date"] = pd.to_datetime(events["date"])

results = {}

# ============================================================
# 1. 고객별 발주 간격 분석 (자기상관 대용)
# ============================================================
print("=" * 60)
print("1. 고객별 발주 간격 분석")
print("=" * 60)

interval_analysis = {}
for customer in orders["customer"].unique():
    cust_orders = orders[orders["customer"] == customer].sort_values("date")

    # 전체 간격
    dates = cust_orders["date"].values
    if len(dates) < 3:
        continue

    intervals = np.diff(dates).astype("timedelta64[D]").astype(int)

    # 품목별 간격
    item_intervals = {}
    for item in cust_orders["item"].unique():
        item_dates = cust_orders[cust_orders["item"] == item]["date"].values
        if len(item_dates) >= 3:
            i_intervals = np.diff(item_dates).astype("timedelta64[D]").astype(int)
            item_intervals[item] = {
                "count": len(item_dates),
                "mean_interval_days": round(float(np.mean(i_intervals)), 1),
                "std_interval_days": round(float(np.std(i_intervals)), 1),
                "median_interval_days": round(float(np.median(i_intervals)), 1),
                "min": int(np.min(i_intervals)),
                "max": int(np.max(i_intervals)),
                "cv": round(float(np.std(i_intervals) / np.mean(i_intervals)), 2) if np.mean(i_intervals) > 0 else None,
            }

    interval_analysis[customer] = {
        "total_orders": len(cust_orders),
        "overall_mean_interval": round(float(np.mean(intervals)), 1),
        "overall_std_interval": round(float(np.std(intervals)), 1),
        "overall_cv": round(float(np.std(intervals) / np.mean(intervals)), 2) if np.mean(intervals) > 0 else None,
        "item_intervals": item_intervals,
    }

    print(f"\n{customer} (총 {len(cust_orders)}건):")
    print(f"  전체 평균 간격: {np.mean(intervals):.1f}일 (std: {np.std(intervals):.1f})")
    if item_intervals:
        for item, stats in sorted(item_intervals.items(), key=lambda x: -x[1]["count"]):
            cv_str = f"CV={stats['cv']}" if stats['cv'] is not None else ""
            print(f"  {item}: 평균 {stats['mean_interval_days']}일 간격, {cv_str}, {stats['count']}건")

results["interval_analysis"] = interval_analysis


# ============================================================
# 2. 월별/계절별 수요 패턴
# ============================================================
print("\n" + "=" * 60)
print("2. 월별/계절별 수요 패턴")
print("=" * 60)

orders["month"] = orders["date"].dt.month
orders["year_month"] = orders["date"].dt.to_period("M").astype(str)

monthly_qty = orders.groupby("year_month").agg(
    total_orders=("order_id", "count"),
    total_quantity=("quantity", "sum"),
    total_amount=("total_amount", "sum"),
).reset_index()

# 계절 구분
def get_season(month):
    if month in [3, 4, 5]: return "봄"
    elif month in [6, 7, 8]: return "여름"
    elif month in [9, 10, 11]: return "가을"
    else: return "겨울"

orders["season"] = orders["month"].apply(get_season)
seasonal = orders.groupby("season").agg(
    avg_orders_per_month=("order_id", "count"),
    avg_quantity=("quantity", "mean"),
    total_quantity=("quantity", "sum"),
).reset_index()

seasonal_dict = {}
for _, row in seasonal.iterrows():
    seasonal_dict[row["season"]] = {
        "total_orders": int(row["avg_orders_per_month"]),
        "avg_quantity_per_order": round(float(row["avg_quantity"]), 1),
        "total_quantity": int(row["total_quantity"]),
    }

results["seasonal_pattern"] = seasonal_dict
results["monthly_orders"] = monthly_qty.set_index("year_month").to_dict(orient="index")

print("\n계절별 집계:")
for season, stats in seasonal_dict.items():
    print(f"  {season}: {stats['total_orders']}건, 평균 수량 {stats['avg_quantity_per_order']}")

print("\n월별 발주 건수:")
for _, row in monthly_qty.iterrows():
    print(f"  {row['year_month']}: {row['total_orders']}건, 총수량 {row['total_quantity']}")


# ============================================================
# 3. 교차 상관 분석 (고객 간 발주 시점 연관)
# ============================================================
print("\n" + "=" * 60)
print("3. 교차 상관 분석 (고객 간)")
print("=" * 60)

# 일별 발주 여부를 이진 시계열로 변환
date_range = pd.date_range(orders["date"].min(), orders["date"].max(), freq="D")
customer_daily = pd.DataFrame(index=date_range)

for customer in orders["customer"].unique():
    cust_dates = orders[orders["customer"] == customer]["date"].dt.normalize()
    daily = cust_dates.value_counts().reindex(date_range, fill_value=0)
    customer_daily[customer] = (daily > 0).astype(int)

# 교차 상관: 고객 A 발주 후 N일 이내에 고객 B 발주 확률
cross_correlations = []
for c1, c2 in combinations(orders["customer"].unique(), 2):
    for lag in [1, 2, 3, 4, 5]:
        c1_dates = set(orders[orders["customer"] == c1]["date"].dt.normalize())
        c2_dates = set(orders[orders["customer"] == c2]["date"].dt.normalize())

        # c1 발주 후 lag일 뒤 c2 발주 횟수
        follow_count = 0
        c1_count = 0
        for d1 in c1_dates:
            c1_count += 1
            for offset in range(lag, lag + 1):
                if d1 + pd.Timedelta(days=offset) in c2_dates:
                    follow_count += 1
                    break

        if c1_count > 0 and follow_count >= 3:  # 최소 3회 이상
            prob = follow_count / c1_count
            if prob >= 0.3:  # 30% 이상만 보고
                cross_correlations.append({
                    "customer_a": c1,
                    "customer_b": c2,
                    "lag_days": lag,
                    "follow_count": follow_count,
                    "total_a_orders": c1_count,
                    "probability": round(prob, 2),
                })

# lag 범위 확대 (2~4일 윈도우)
for c1, c2 in combinations(orders["customer"].unique(), 2):
    c1_dates = sorted(orders[orders["customer"] == c1]["date"].dt.normalize().unique())
    c2_dates = sorted(orders[orders["customer"] == c2]["date"].dt.normalize().unique())

    follow_count = 0
    for d1 in c1_dates:
        for d2 in c2_dates:
            diff = (d2 - d1).days
            if 2 <= diff <= 4:
                follow_count += 1
                break

    if len(c1_dates) > 0 and follow_count >= 3:
        prob = follow_count / len(c1_dates)
        if prob >= 0.3:
            cross_correlations.append({
                "customer_a": c1,
                "customer_b": c2,
                "lag_days": "2-4",
                "follow_count": follow_count,
                "total_a_orders": len(c1_dates),
                "probability": round(prob, 2),
            })

results["cross_correlations"] = cross_correlations

if cross_correlations:
    print("\n유의미한 교차 상관:")
    for cc in sorted(cross_correlations, key=lambda x: -x["probability"]):
        print(f"  {cc['customer_a']} → {cc['customer_b']} "
              f"(lag={cc['lag_days']}일): {cc['follow_count']}/{cc['total_a_orders']} "
              f"= {cc['probability']:.0%}")
else:
    print("  유의미한 교차 상관 없음")


# ============================================================
# 4. 품목 동반 발주 분석 (Co-occurrence)
# ============================================================
print("\n" + "=" * 60)
print("4. 품목 동반 발주 분석")
print("=" * 60)

# 같은 고객이 같은 주에 주문한 품목 쌍
orders["week"] = orders["date"].dt.isocalendar().week.astype(int)
orders["year"] = orders["date"].dt.year

co_occurrence = Counter()
total_item_weeks = Counter()

for (customer, year, week), group in orders.groupby(["customer", "year", "week"]):
    items = group["item"].unique()
    for item in items:
        total_item_weeks[item] += 1
    for i1, i2 in combinations(sorted(items), 2):
        co_occurrence[(i1, i2)] += 1

co_occ_results = []
for (i1, i2), count in co_occurrence.most_common(20):
    if count >= 3:
        support = count / len(orders.groupby(["customer", "year", "week"]))
        co_occ_results.append({
            "item_a": i1,
            "item_b": i2,
            "co_occurrence_count": count,
            "support": round(support, 3),
        })
        print(f"  {i1} + {i2}: {count}회 동반 발주 (support={support:.3f})")

results["co_occurrence"] = co_occ_results


# ============================================================
# 5. 요일/주차 분포 (고객별)
# ============================================================
print("\n" + "=" * 60)
print("5. 고객별 요일/주차 선호 분석")
print("=" * 60)

orders["weekday_num"] = orders["date"].dt.weekday  # 0=월
orders["week_of_month"] = (orders["date"].dt.day - 1) // 7 + 1

weekday_pref = {}
for customer in orders["customer"].unique():
    cust = orders[orders["customer"] == customer]
    wd_dist = cust["weekday_num"].value_counts().sort_index()
    wom_dist = cust["week_of_month"].value_counts().sort_index()

    # 특정 요일에 집중도 확인
    wd_entropy = -sum((p/len(cust)) * np.log2(p/len(cust))
                       for p in wd_dist.values if p > 0)
    max_entropy = np.log2(5)  # 평일 5일 균등분포
    concentration = round(1 - wd_entropy / max_entropy, 2) if max_entropy > 0 else 0

    weekday_pref[customer] = {
        "weekday_distribution": {["월","화","수","목","금","토","일"][k]: int(v)
                                  for k, v in wd_dist.items()},
        "week_of_month_distribution": {f"W{int(k)}": int(v) for k, v in wom_dist.items()},
        "weekday_concentration": concentration,
        "dominant_week": f"W{int(wom_dist.idxmax())}" if len(wom_dist) > 0 else None,
    }

    if concentration > 0.2:
        dominant_day = ["월","화","수","목","금","토","일"][wd_dist.idxmax()]
        print(f"  {customer}: 요일 집중도 {concentration} (주로 {dominant_day}요일), "
              f"주차 집중: {weekday_pref[customer]['dominant_week']}")

results["weekday_preference"] = weekday_pref


# ============================================================
# 6. 이벤트 → 발주 시차 분석
# ============================================================
print("\n" + "=" * 60)
print("6. 이벤트 → 발주 시차 분석")
print("=" * 60)

event_order_lags = []
for _, event in events.iterrows():
    # 같은 고객의 이벤트 후 발주 찾기
    cust_orders_after = orders[
        (orders["customer"] == event["customer"]) &
        (orders["date"] > event["date"]) &
        (orders["date"] <= event["date"] + pd.Timedelta(days=30))
    ]

    if len(cust_orders_after) > 0:
        first_order = cust_orders_after.iloc[0]
        lag = (first_order["date"] - event["date"]).days
        event_order_lags.append({
            "customer": event["customer"],
            "event_type": event["event_type"],
            "event_item": event["item"],
            "order_item": first_order["item"],
            "lag_days": lag,
            "item_match": event["item"] == first_order["item"],
        })

lag_by_type = defaultdict(list)
for eol in event_order_lags:
    lag_by_type[eol["event_type"]].append(eol["lag_days"])

event_lag_summary = {}
for etype, lags in lag_by_type.items():
    event_lag_summary[etype] = {
        "count": len(lags),
        "mean_lag": round(np.mean(lags), 1),
        "median_lag": round(np.median(lags), 1),
        "std_lag": round(np.std(lags), 1),
    }
    print(f"  {etype}: 평균 {np.mean(lags):.1f}일 후 발주 ({len(lags)}건)")

# 동아전자 특화 분석
dongah_events = events[events["customer"] == "동아전자"]
dongah_lags = [e for e in event_order_lags if e["customer"] == "동아전자"]
if dongah_lags:
    item_match_rate = sum(1 for e in dongah_lags if e["item_match"]) / len(dongah_lags)
    avg_lag = np.mean([e["lag_days"] for e in dongah_lags])
    print(f"\n  동아전자 특화:")
    print(f"    견적요청 → 발주 평균 {avg_lag:.1f}일")
    print(f"    품목 일치율: {item_match_rate:.0%}")
    event_lag_summary["동아전자_견적후발주"] = {
        "avg_lag": round(avg_lag, 1),
        "item_match_rate": round(item_match_rate, 2),
        "count": len(dongah_lags),
    }

results["event_to_order_lag"] = event_lag_summary


# ============================================================
# 7. 발주 간격 변동 추이 (Drift 감지)
# ============================================================
print("\n" + "=" * 60)
print("7. 발주 간격 변동 추이 (Drift)")
print("=" * 60)

drift_analysis = {}
for customer in orders["customer"].unique():
    for item in orders[orders["customer"] == customer]["item"].unique():
        subset = orders[(orders["customer"] == customer) & (orders["item"] == item)].sort_values("date")
        if len(subset) < 6:
            continue

        dates = subset["date"].values
        intervals = np.diff(dates).astype("timedelta64[D]").astype(int)

        if len(intervals) < 4:
            continue

        # 전반부 vs 후반부 비교
        mid = len(intervals) // 2
        first_half = intervals[:mid]
        second_half = intervals[mid:]

        mean_diff = np.mean(second_half) - np.mean(first_half)

        if abs(mean_diff) > 3:  # 3일 이상 차이
            drift_analysis[f"{customer}_{item}"] = {
                "customer": customer,
                "item": item,
                "first_half_mean": round(float(np.mean(first_half)), 1),
                "second_half_mean": round(float(np.mean(second_half)), 1),
                "interval_change": round(float(mean_diff), 1),
                "direction": "늘어남" if mean_diff > 0 else "짧아짐",
                "intervals": [int(i) for i in intervals],
            }
            print(f"  {customer}/{item}: {np.mean(first_half):.1f}일 → {np.mean(second_half):.1f}일 "
                  f"({'+' if mean_diff > 0 else ''}{mean_diff:.1f}일)")

results["drift_analysis"] = drift_analysis


# ============================================================
# 8. 고객별 발주량 추이 (대형 발주 감지)
# ============================================================
print("\n" + "=" * 60)
print("8. 고객별 대형 발주 감지")
print("=" * 60)

large_orders = {}
for customer in orders["customer"].unique():
    cust = orders[orders["customer"] == customer]
    q75 = cust["quantity"].quantile(0.75)
    q25 = cust["quantity"].quantile(0.25)
    iqr = q75 - q25
    threshold = q75 + 1.5 * iqr

    outliers = cust[cust["quantity"] > threshold]
    if len(outliers) > 0:
        large_orders[customer] = {
            "threshold": round(float(threshold), 1),
            "large_order_count": len(outliers),
            "large_orders": [
                {
                    "date": row["date"].strftime("%Y-%m-%d"),
                    "item": row["item"],
                    "quantity": int(row["quantity"]),
                }
                for _, row in outliers.iterrows()
            ]
        }
        print(f"  {customer}: {len(outliers)}건 대형 발주 (임계값: {threshold:.0f})")
        for _, row in outliers.iterrows():
            print(f"    {row['date'].strftime('%Y-%m-%d')} {row['item']} {row['quantity']}")

results["large_orders"] = large_orders


# ============================================================
# 저장
# ============================================================
# JSON 직렬화를 위해 numpy/pandas 타입 변환
def convert_types(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    return obj

def deep_convert(obj):
    if isinstance(obj, dict):
        return {k: deep_convert(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [deep_convert(i) for i in obj]
    return convert_types(obj)

results = deep_convert(results)

output_path = os.path.join(DATA_DIR, "phase1_results.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n=== Phase 1 결과 저장: {output_path} ===")
print(f"분석 항목: {list(results.keys())}")
