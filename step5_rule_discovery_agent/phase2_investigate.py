"""
Phase 2: 심화 분석 — LLM₁이 지목한 대상을 깊이 파는 ML 도구 모음

입력: orders.csv + phase2_requests.json (LLM₁이 생성)
출력: phase2_results.json (요청별 상세 결과)

Usage:
    python phase2_investigate.py --data-dir synthetic/data --requests synthetic/results/phase2_requests.json
"""

import argparse
import json
import os
import numpy as np
import pandas as pd
from itertools import combinations


def load_data(data_dir: str) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    orders = pd.read_csv(os.path.join(data_dir, "orders.csv"), encoding="utf-8-sig")
    orders["date"] = pd.to_datetime(orders["date"])

    events_path = os.path.join(data_dir, "events.csv")
    events = None
    if os.path.exists(events_path):
        events = pd.read_csv(events_path, encoding="utf-8-sig")
        events["date"] = pd.to_datetime(events["date"])

    return orders, events


# ============================================================
# 분석 함수들
# ============================================================

def precursor_check(orders: pd.DataFrame, params: dict) -> dict:
    """특정 고객-품목의 짧은 간격 주문 직전에 다른 고객 주문이 있었는지 확인"""
    customer = params["customer"]
    item = params["item"]
    target_max_interval = params.get("target_max_interval", 5)
    look_back_days = params.get("look_back_days", 7)

    ci_orders = orders[
        (orders["customer"] == customer) & (orders["item"] == item)
    ].sort_values("date").reset_index(drop=True)

    if len(ci_orders) < 3:
        return {"error": f"{customer}/{item} 주문 {len(ci_orders)}건 — 분석 불가"}

    dates = ci_orders["date"].values
    intervals = np.diff(dates).astype("timedelta64[D]").astype(int)

    short_indices = [i for i, iv in enumerate(intervals) if iv <= target_max_interval]

    if not short_indices:
        return {
            "short_interval_count": 0,
            "summary": f"{target_max_interval}일 이하 간격 없음"
        }

    precursor_hits = []
    for idx in short_indices:
        order_date = pd.Timestamp(dates[idx + 1])
        interval = int(intervals[idx])

        nearby = orders[
            (orders["customer"] != customer) &
            (orders["date"] >= order_date - pd.Timedelta(days=look_back_days)) &
            (orders["date"] < order_date)
        ]

        precursors = []
        for _, row in nearby.iterrows():
            lag = (order_date - row["date"]).days
            if 1 <= lag <= look_back_days:
                precursors.append({
                    "customer": row["customer"],
                    "item": row["item"],
                    "date": str(row["date"].date()),
                    "lag_days": lag,
                })

        precursor_hits.append({
            "order_date": str(order_date.date()),
            "interval_days": interval,
            "precursors": precursors,
        })

    # 선행자 빈도 집계
    from collections import Counter
    prec_counter = Counter()
    for hit in precursor_hits:
        for p in hit["precursors"]:
            prec_counter[f"{p['customer']}/{p['item']}"] += 1

    top_precursors = [
        {"precursor": k, "count": v, "rate": round(v / len(short_indices), 2)}
        for k, v in prec_counter.most_common(5)
    ]

    return {
        "target": f"{customer}/{item}",
        "target_max_interval": target_max_interval,
        "short_interval_count": len(short_indices),
        "total_intervals": len(intervals),
        "details": precursor_hits,
        "top_precursors": top_precursors,
        "summary": f"짧은 간격 {len(short_indices)}건 중 "
                   + (f"상위 선행자: {top_precursors[0]['precursor']} ({top_precursors[0]['count']}건, {top_precursors[0]['rate']:.0%})"
                      if top_precursors else "선행자 없음"),
    }


def cross_customer_detail(orders: pd.DataFrame, params: dict) -> dict:
    """두 고객 간 주문일 상세 매칭 (날짜별, 품목별)"""
    from_cust = params["from_customer"]
    to_cust = params["to_customer"]
    from_item = params.get("from_item")
    to_item = params.get("to_item")
    lag_min = params.get("lag_min", 1)
    lag_max = params.get("lag_max", 7)

    from_orders = orders[orders["customer"] == from_cust]
    to_orders = orders[orders["customer"] == to_cust]

    if from_item:
        from_orders = from_orders[from_orders["item"] == from_item]
    if to_item:
        to_orders = to_orders[to_orders["item"] == to_item]

    from_dates = sorted(from_orders["date"].dt.normalize().unique())
    to_dates = sorted(to_orders["date"].dt.normalize().unique())

    if len(from_dates) < 2 or len(to_dates) < 2:
        return {"error": "주문 건수 부족"}

    pairs = []
    for fd in from_dates:
        for td in to_dates:
            lag = (td - fd).days
            if lag_min <= lag <= lag_max:
                pairs.append({
                    "from_date": str(pd.Timestamp(fd).date()),
                    "to_date": str(pd.Timestamp(td).date()),
                    "lag_days": lag,
                })
                break  # 첫 매칭만

    # 기대 확률 계산
    days_span = (max(to_dates) - min(to_dates)).days + 1
    expected_prob = min(1.0, len(to_dates) * (lag_max - lag_min + 1) / days_span) if days_span > 0 else 0
    actual_prob = len(pairs) / len(from_dates) if from_dates else 0
    lift = round(actual_prob / expected_prob, 2) if expected_prob > 0 else float("inf")

    return {
        "from": f"{from_cust}" + (f"/{from_item}" if from_item else ""),
        "to": f"{to_cust}" + (f"/{to_item}" if to_item else ""),
        "lag_range": f"{lag_min}~{lag_max}일",
        "hit_count": len(pairs),
        "total_from_orders": len(from_dates),
        "probability": round(actual_prob, 2),
        "expected_random": round(expected_prob, 2),
        "lift": lift,
        "pairs": pairs,
        "summary": f"{from_cust}→{to_cust}: {len(pairs)}/{len(from_dates)} = {actual_prob:.0%} "
                   f"(기대 {expected_prob:.0%}, lift={lift})",
    }


def quantity_anomaly(orders: pd.DataFrame, params: dict) -> dict:
    """평소 대비 이상 수량 주문 식별 + 공통점 분석"""
    customer = params.get("customer")
    item = params.get("item")
    threshold_pct = params.get("threshold_pct", 50)

    filtered = orders.copy()
    if customer:
        filtered = filtered[filtered["customer"] == customer]
    if item:
        filtered = filtered[filtered["item"] == item]

    if len(filtered) < 5:
        return {"error": "주문 건수 부족"}

    mean_qty = filtered["quantity"].mean()
    std_qty = filtered["quantity"].std()
    low_bound = mean_qty * (1 - threshold_pct / 100)
    high_bound = mean_qty * (1 + threshold_pct / 100)

    anomalies = filtered[
        (filtered["quantity"] < low_bound) | (filtered["quantity"] > high_bound)
    ]

    anomaly_list = []
    for _, row in anomalies.iterrows():
        anomaly_list.append({
            "date": str(row["date"].date()),
            "customer": row["customer"],
            "item": row["item"],
            "quantity": int(row["quantity"]),
            "deviation_pct": round((row["quantity"] - mean_qty) / mean_qty * 100, 1),
        })

    # 공통점 분석
    context = {}
    if len(anomalies) >= 2:
        context["weekday_dist"] = anomalies["date"].dt.day_name().value_counts().to_dict()
        context["month_dist"] = anomalies["date"].dt.month.value_counts().to_dict()
        if "customer" in anomalies.columns and not customer:
            context["customer_dist"] = anomalies["customer"].value_counts().to_dict()

    return {
        "filter": f"{customer or '전체'}/{item or '전체'}",
        "mean_quantity": round(mean_qty, 1),
        "threshold_pct": threshold_pct,
        "anomaly_count": len(anomalies),
        "total_orders": len(filtered),
        "anomalies": anomaly_list,
        "common_patterns": context,
        "summary": f"이상 수량 {len(anomalies)}/{len(filtered)}건 "
                   f"(평균 {mean_qty:.0f}, ±{threshold_pct}% 기준)",
    }


def conditional_trigger(orders: pd.DataFrame, params: dict) -> dict:
    """A 조건일 때 B가 발생하는가 검정"""
    trigger_cust = params["trigger_customer"]
    trigger_item = params["trigger_item"]
    trigger_condition = params.get("trigger_condition", {})
    effect_cust = params["effect_customer"]
    effect_item = params["effect_item"]
    time_window = params.get("time_window", 30)

    trigger_orders = orders[
        (orders["customer"] == trigger_cust) & (orders["item"] == trigger_item)
    ].sort_values("date")

    # 조건 필터링
    min_qty = trigger_condition.get("min_quantity")
    if min_qty:
        trigger_orders = trigger_orders[trigger_orders["quantity"] >= min_qty]

    if len(trigger_orders) < 2:
        return {"error": "트리거 조건 충족 건수 부족"}

    effect_orders = orders[
        (orders["customer"] == effect_cust) & (orders["item"] == effect_item)
    ].sort_values("date")

    hits = []
    for _, trig in trigger_orders.iterrows():
        followers = effect_orders[
            (effect_orders["date"] > trig["date"]) &
            (effect_orders["date"] <= trig["date"] + pd.Timedelta(days=time_window))
        ]
        if len(followers) > 0:
            f = followers.iloc[0]
            lag = (f["date"] - trig["date"]).days
            hits.append({
                "trigger_date": str(trig["date"].date()),
                "trigger_qty": int(trig["quantity"]),
                "effect_date": str(f["date"].date()),
                "effect_qty": int(f["quantity"]),
                "lag_days": lag,
            })

    # 비조건 (조건 미충족) 대비 확률
    all_trigger = orders[
        (orders["customer"] == trigger_cust) & (orders["item"] == trigger_item)
    ].sort_values("date")
    if min_qty:
        non_trigger = all_trigger[all_trigger["quantity"] < min_qty]
    else:
        non_trigger = pd.DataFrame()

    non_trigger_hits = 0
    for _, trig in non_trigger.iterrows():
        followers = effect_orders[
            (effect_orders["date"] > trig["date"]) &
            (effect_orders["date"] <= trig["date"] + pd.Timedelta(days=time_window))
        ]
        if len(followers) > 0:
            non_trigger_hits += 1

    hit_rate = len(hits) / len(trigger_orders) if len(trigger_orders) > 0 else 0
    baseline_rate = non_trigger_hits / len(non_trigger) if len(non_trigger) > 0 else 0

    return {
        "trigger": f"{trigger_cust}/{trigger_item}" + (f" (qty>={min_qty})" if min_qty else ""),
        "effect": f"{effect_cust}/{effect_item}",
        "time_window": f"{time_window}일",
        "trigger_count": len(trigger_orders),
        "hit_count": len(hits),
        "hit_rate": round(hit_rate, 2),
        "baseline_count": len(non_trigger),
        "baseline_hits": non_trigger_hits,
        "baseline_rate": round(baseline_rate, 2),
        "hits": hits,
        "summary": f"조건 충족 {len(trigger_orders)}건 중 {len(hits)}건 후속 ({hit_rate:.0%}), "
                   f"비조건 {baseline_rate:.0%}",
    }


def drift_detail(orders: pd.DataFrame, params: dict) -> dict:
    """교란 요인 제거 후 drift 재검정"""
    from scipy.stats import spearmanr

    customer = params["customer"]
    item = params["item"]
    remove_precursor = params.get("remove_precursor")  # "한진산업/STS304" 형태
    remove_lag_max = params.get("remove_lag_max", 5)

    ci_orders = orders[
        (orders["customer"] == customer) & (orders["item"] == item)
    ].sort_values("date").reset_index(drop=True)

    if len(ci_orders) < 6:
        return {"error": "주문 건수 부족"}

    # 원본 drift
    dates_raw = ci_orders["date"].values
    intervals_raw = np.diff(dates_raw).astype("timedelta64[D]").astype(int).astype(float)
    n = len(intervals_raw)
    third = max(1, n // 3)

    rho_raw, p_raw = spearmanr(range(n), intervals_raw)
    raw_drift = {
        "first_third_mean": round(float(np.mean(intervals_raw[:third])), 1),
        "last_third_mean": round(float(np.mean(intervals_raw[-third:])), 1),
        "spearman_rho": round(float(rho_raw), 3),
        "spearman_p": round(float(p_raw), 3),
    }

    # 교란 제거
    cleaned_drift = None
    removed_count = 0

    if remove_precursor:
        parts = remove_precursor.split("/")
        prec_cust, prec_item = parts[0], "/".join(parts[1:])

        remove_positions = set()
        for pos in range(len(ci_orders)):
            od = ci_orders.iloc[pos]["date"]
            nearby = orders[
                (orders["customer"] == prec_cust) &
                (orders["item"] == prec_item) &
                (orders["date"] >= od - pd.Timedelta(days=remove_lag_max)) &
                (orders["date"] < od)
            ]
            if len(nearby) > 0:
                remove_positions.add(pos)

        removed_count = len(remove_positions)

        if removed_count > 0 and len(ci_orders) - removed_count >= 6:
            clean_mask = np.ones(len(ci_orders), dtype=bool)
            for pos in remove_positions:
                clean_mask[pos] = False

            clean_dates = ci_orders[clean_mask]["date"].values
            clean_ivs = np.diff(clean_dates).astype("timedelta64[D]").astype(int).astype(float)

            if len(clean_ivs) >= 6:
                nc = len(clean_ivs)
                tc = max(1, nc // 3)
                rho_clean, p_clean = spearmanr(range(nc), clean_ivs)

                cleaned_drift = {
                    "removed_orders": removed_count,
                    "remaining_intervals": nc,
                    "first_third_mean": round(float(np.mean(clean_ivs[:tc])), 1),
                    "last_third_mean": round(float(np.mean(clean_ivs[-tc:])), 1),
                    "spearman_rho": round(float(rho_clean), 3),
                    "spearman_p": round(float(p_clean), 3),
                    "intervals": [int(x) for x in clean_ivs],
                }

    return {
        "target": f"{customer}/{item}",
        "total_orders": len(ci_orders),
        "raw_drift": raw_drift,
        "remove_precursor": remove_precursor,
        "cleaned_drift": cleaned_drift,
        "summary": (
            f"원본 rho={raw_drift['spearman_rho']}, p={raw_drift['spearman_p']}"
            + (f" → 정제 후 rho={cleaned_drift['spearman_rho']}, p={cleaned_drift['spearman_p']} "
               f"({removed_count}건 제거)" if cleaned_drift else "")
        ),
    }


def alternation_check(orders: pd.DataFrame, params: dict) -> dict:
    """한 고객의 두 품목이 교대로 주문되는지 확인"""
    customer = params["customer"]
    items = params["items"]  # [item_a, item_b]

    # items가 비어있으면 해당 고객의 상위 2개 품목 자동 선택
    if not items or len(items) < 2:
        cust_items = orders[orders["customer"] == customer]["item"].value_counts()
        if len(cust_items) < 2:
            return {"error": f"{customer}의 품목이 2개 미만"}
        items = cust_items.index[:2].tolist()

    if len(items) != 2:
        return {"error": "정확히 2개 품목 필요"}

    cust_orders = orders[
        (orders["customer"] == customer) & (orders["item"].isin(items))
    ].sort_values("date").reset_index(drop=True)

    if len(cust_orders) < 4:
        return {"error": "주문 건수 부족"}

    sequence = cust_orders["item"].tolist()

    # 교대 패턴 점수: 연속으로 같은 품목이 나오지 않는 비율
    alternations = 0
    for i in range(1, len(sequence)):
        if sequence[i] != sequence[i - 1]:
            alternations += 1

    alt_rate = alternations / (len(sequence) - 1)

    # 날짜별 상세
    timeline = []
    for _, row in cust_orders.iterrows():
        timeline.append({
            "date": str(row["date"].date()),
            "item": row["item"],
            "quantity": int(row["quantity"]),
        })

    return {
        "customer": customer,
        "items": items,
        "total_orders": len(cust_orders),
        "alternation_rate": round(alt_rate, 2),
        "perfect_alternation": alt_rate > 0.8,
        "timeline": timeline,
        "summary": f"{customer}의 {items[0]}↔{items[1]}: "
                   f"교대율 {alt_rate:.0%} ({alternations}/{len(sequence) - 1})",
    }


def event_lead_detail(orders: pd.DataFrame, events: pd.DataFrame, params: dict) -> dict:
    """이벤트→주문 전환 상세 분석"""
    if events is None:
        return {"error": "이벤트 데이터 없음"}

    customer = params.get("customer")
    event_type = params.get("event_type")
    lag_max = params.get("lag_max", 30)

    filtered_events = events.copy()
    if customer:
        filtered_events = filtered_events[filtered_events["customer"] == customer]
    if event_type:
        filtered_events = filtered_events[filtered_events["event_type"] == event_type]

    if len(filtered_events) < 2:
        return {"error": "이벤트 건수 부족"}

    results = []
    for _, ev in filtered_events.iterrows():
        cust_orders = orders[orders["customer"] == ev["customer"]].sort_values("date")
        followers = cust_orders[
            (cust_orders["date"] > ev["date"]) &
            (cust_orders["date"] <= ev["date"] + pd.Timedelta(days=lag_max))
        ]

        if len(followers) > 0:
            f = followers.iloc[0]
            item_match = (pd.notna(ev.get("item")) and ev["item"] == f["item"])
            results.append({
                "event_date": str(ev["date"].date()),
                "event_type": ev["event_type"],
                "event_customer": ev["customer"],
                "event_item": str(ev.get("item", "")),
                "order_date": str(f["date"].date()),
                "order_item": f["item"],
                "order_qty": int(f["quantity"]),
                "lag_days": (f["date"] - ev["date"]).days,
                "item_match": bool(item_match),
            })

    follow_rate = len(results) / len(filtered_events) if len(filtered_events) > 0 else 0
    item_matches = sum(1 for r in results if r["item_match"])
    item_match_rate = item_matches / len(results) if results else 0

    return {
        "filter": f"{customer or '전체'}/{event_type or '전체'}",
        "event_count": len(filtered_events),
        "follow_count": len(results),
        "follow_rate": round(follow_rate, 2),
        "item_match_count": item_matches,
        "item_match_rate": round(item_match_rate, 2),
        "mean_lag": round(float(np.mean([r["lag_days"] for r in results])), 1) if results else None,
        "details": results,
        "summary": f"이벤트 {len(filtered_events)}건 중 {len(results)}건 후속 주문 ({follow_rate:.0%}), "
                   f"품목 일치 {item_match_rate:.0%}",
    }


def seasonal_shift(orders: pd.DataFrame, params: dict) -> dict:
    """분기/월별로 주문 패턴 분리 비교"""
    customer = params.get("customer")
    item = params.get("item")
    split_by = params.get("split_by", "quarter")

    filtered = orders.copy()
    if customer:
        filtered = filtered[filtered["customer"] == customer]
    if item:
        filtered = filtered[filtered["item"] == item]

    if len(filtered) < 8:
        return {"error": "주문 건수 부족"}

    if split_by == "quarter":
        filtered["period"] = filtered["date"].dt.quarter.map({1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"})
    else:
        filtered["period"] = filtered["date"].dt.month

    period_stats = {}
    for period, group in filtered.groupby("period"):
        period_stats[str(period)] = {
            "count": len(group),
            "mean_qty": round(float(group["quantity"].mean()), 1),
            "total_qty": int(group["quantity"].sum()),
        }

    counts = [s["count"] for s in period_stats.values()]
    max_period = max(period_stats, key=lambda k: period_stats[k]["count"])
    min_period = min(period_stats, key=lambda k: period_stats[k]["count"])

    return {
        "filter": f"{customer or '전체'}/{item or '전체'}",
        "split_by": split_by,
        "periods": period_stats,
        "peak_period": max_period,
        "trough_period": min_period,
        "ratio": round(max(counts) / min(counts), 2) if min(counts) > 0 else float("inf"),
        "summary": f"최대 {max_period} ({period_stats[max_period]['count']}건) vs "
                   f"최소 {min_period} ({period_stats[min_period]['count']}건), "
                   f"비율 {max(counts) / min(counts):.1f}x" if min(counts) > 0 else "비교 불가",
    }


# ============================================================
# 디스패처
# ============================================================

ANALYSIS_FUNCTIONS = {
    "precursor_check": precursor_check,
    "cross_customer_detail": cross_customer_detail,
    "quantity_anomaly": quantity_anomaly,
    "conditional_trigger": conditional_trigger,
    "drift_detail": drift_detail,
    "alternation_check": alternation_check,
    "event_lead_detail": event_lead_detail,
    "seasonal_shift": seasonal_shift,
}

# event_lead_detail은 events 인자가 추가로 필요
NEEDS_EVENTS = {"event_lead_detail"}


def normalize_params(analysis_type: str, params: dict) -> dict:
    """LLM이 생성한 파라미터 이름을 함수 시그니처에 맞게 정규화"""
    p = dict(params)

    # cross_customer_detail: customer_a/b → from_customer/to_customer
    if analysis_type == "cross_customer_detail":
        if "customer_a" in p and "from_customer" not in p:
            p["from_customer"] = p.pop("customer_a")
        if "customer_b" in p and "to_customer" not in p:
            p["to_customer"] = p.pop("customer_b")
        if "item_a" in p and "from_item" not in p:
            p["from_item"] = p.pop("item_a")
        if "item_b" in p and "to_item" not in p:
            p["to_item"] = p.pop("item_b")

    # alternation_check: 단일 item → items 리스트 변환 불가 시 에러 방지
    if analysis_type == "alternation_check":
        if "items" not in p:
            # customer의 상위 2개 품목을 자동 선택하도록 빈 리스트
            p["items"] = p.get("items", [])

    # conditional_trigger: 다양한 이름 변형 처리
    if analysis_type == "conditional_trigger":
        if "event_customer" in p and "trigger_customer" not in p:
            p["trigger_customer"] = p.pop("event_customer")
        if "target_customer" in p and "effect_customer" not in p:
            p["effect_customer"] = p.pop("target_customer")
        if "event_type" in p and "trigger_item" not in p:
            p["trigger_item"] = p.pop("event_type", "")
        if "target_items" in p and "effect_item" not in p:
            items = p.pop("target_items")
            p["effect_item"] = items[0] if isinstance(items, list) and items else ""

    return p


def run_request(request: dict, orders: pd.DataFrame, events: pd.DataFrame | None) -> dict:
    analysis_type = request["analysis_type"]
    params = normalize_params(analysis_type, request.get("params", {}))

    func = ANALYSIS_FUNCTIONS.get(analysis_type)
    if func is None:
        return {"error": f"알 수 없는 분석 유형: {analysis_type}"}

    try:
        if analysis_type in NEEDS_EVENTS:
            return func(orders, events, params)
        else:
            return func(orders, params)
    except (KeyError, TypeError, ValueError) as e:
        return {"error": f"{analysis_type} 실행 실패: {e}", "params_received": params}


def main():
    parser = argparse.ArgumentParser(description="Phase 2: 심화 분석")
    parser.add_argument("--data-dir", required=True, help="CSV 데이터 디렉토리")
    parser.add_argument("--requests", required=True, help="phase2_requests.json 경로")
    parser.add_argument("--output", default=None, help="결과 저장 경로 (기본: requests와 같은 디렉토리)")
    args = parser.parse_args()

    orders, events = load_data(args.data_dir)
    print(f"데이터 로드: 주문 {len(orders)}건" + (f", 이벤트 {len(events)}건" if events is not None else ""))

    with open(args.requests, "r", encoding="utf-8") as f:
        requests_data = json.load(f)

    requests_list = requests_data.get("phase2_requests", [])
    print(f"분석 요청: {len(requests_list)}건")

    results = {}
    for req in requests_list:
        req_id = req["id"]
        print(f"\n  [{req_id}] {req.get('question', req['analysis_type'])}...")
        result = run_request(req, orders, events)
        results[req_id] = {
            "question": req.get("question", ""),
            "analysis_type": req["analysis_type"],
            "result": result,
        }
        print(f"    → {result.get('summary', 'done')}")

    output_path = args.output or os.path.join(
        os.path.dirname(args.requests), "phase2_results.json"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n결과 저장: {output_path}")


if __name__ == "__main__":
    main()
