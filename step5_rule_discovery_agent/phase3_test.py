"""
Phase 3: 가설 검정 — LLM₂가 생성한 가설을 ML로 테스트

입력: orders.csv + hypotheses.json (LLM₂가 생성)
출력: phase3_results.json (가설별 검정 결과)

Usage:
    python phase3_test.py --data-dir synthetic/data --hypotheses synthetic/results/hypotheses.json
"""

import argparse
import json
import os
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, mannwhitneyu


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
# 가설 검정 함수들
# ============================================================

def test_cross_customer_binary(orders: pd.DataFrame, params: dict) -> dict:
    """A 발주 후 B 발주 있었다/없었다 이진 검정"""
    trigger_cust = params["trigger_customer"]
    trigger_item = params.get("trigger_item")
    effect_cust = params["effect_customer"]
    effect_item = params.get("effect_item")
    lag_window = params.get("lag_window", [1, 7])
    lag_min, lag_max = lag_window

    trigger_orders = orders[orders["customer"] == trigger_cust]
    if trigger_item:
        trigger_orders = trigger_orders[trigger_orders["item"] == trigger_item]
    trigger_dates = sorted(trigger_orders["date"].dt.normalize().unique())

    effect_orders = orders[orders["customer"] == effect_cust]
    if effect_item:
        effect_orders = effect_orders[effect_orders["item"] == effect_item]
    effect_dates = sorted(effect_orders["date"].dt.normalize().unique())

    if len(trigger_dates) < 3 or len(effect_dates) < 3:
        return {"verdict": "insufficient_data", "reason": "주문 건수 부족"}

    hits = 0
    details = []
    for td in trigger_dates:
        found = False
        for ed in effect_dates:
            lag = (ed - td).days
            if lag_min <= lag <= lag_max:
                found = True
                details.append({"trigger": str(pd.Timestamp(td).date()),
                                "effect": str(pd.Timestamp(ed).date()), "lag": lag})
                break
        if not found:
            details.append({"trigger": str(pd.Timestamp(td).date()),
                            "effect": None, "lag": None})
        hits += int(found)

    hit_rate = hits / len(trigger_dates)

    # 기대 확률
    days_span = (max(effect_dates) - min(effect_dates)).days + 1
    window_size = lag_max - lag_min + 1
    expected = min(1.0, len(effect_dates) * window_size / days_span) if days_span > 0 else 0
    lift = round(hit_rate / expected, 2) if expected > 0 else float("inf")

    # 판정
    if hit_rate >= 0.7 and lift >= 1.5:
        verdict = "confirmed"
    elif hit_rate >= 0.5 and lift >= 1.2:
        verdict = "partially_confirmed"
    else:
        verdict = "rejected"

    return {
        "verdict": verdict,
        "hit_rate": round(hit_rate, 2),
        "hits": hits,
        "total": len(trigger_dates),
        "expected_random": round(expected, 2),
        "lift": lift,
        "details": details,
    }


def test_quantity_comparison(orders: pd.DataFrame, params: dict) -> dict:
    """두 그룹 간 수량 비교"""
    customer = params["customer"]
    item = params["item"]
    split_condition = params.get("split_condition", {})

    ci_orders = orders[
        (orders["customer"] == customer) & (orders["item"] == item)
    ].sort_values("date").reset_index(drop=True)

    if len(ci_orders) < 6:
        return {"verdict": "insufficient_data", "reason": "주문 건수 부족"}

    # 간격 기준 분리
    max_interval = split_condition.get("max_interval")
    if max_interval:
        dates = ci_orders["date"].values
        intervals = np.diff(dates).astype("timedelta64[D]").astype(int)
        short_mask = np.zeros(len(ci_orders), dtype=bool)
        for i, iv in enumerate(intervals):
            if iv <= max_interval:
                short_mask[i + 1] = True  # 짧은 간격 뒤의 주문

        group_a = ci_orders[short_mask]["quantity"].values
        group_b = ci_orders[~short_mask]["quantity"].values
        group_a_label = f"interval<={max_interval}일"
        group_b_label = f"interval>{max_interval}일"
    else:
        # 수량 중앙값 기준 분리
        median_qty = ci_orders["quantity"].median()
        group_a = ci_orders[ci_orders["quantity"] <= median_qty]["quantity"].values
        group_b = ci_orders[ci_orders["quantity"] > median_qty]["quantity"].values
        group_a_label = f"qty<={median_qty}"
        group_b_label = f"qty>{median_qty}"

    if len(group_a) < 2 or len(group_b) < 2:
        return {"verdict": "insufficient_data", "reason": "그룹 크기 부족"}

    mean_a = float(np.mean(group_a))
    mean_b = float(np.mean(group_b))

    try:
        stat, p_value = mannwhitneyu(group_a, group_b, alternative="two-sided")
    except ValueError:
        p_value = 1.0

    ratio = mean_a / mean_b if mean_b > 0 else float("inf")

    if p_value < 0.05 and abs(ratio - 1) > 0.3:
        verdict = "confirmed"
    elif p_value < 0.1:
        verdict = "partially_confirmed"
    else:
        verdict = "rejected"

    return {
        "verdict": verdict,
        "group_a": {"label": group_a_label, "n": len(group_a), "mean": round(mean_a, 1)},
        "group_b": {"label": group_b_label, "n": len(group_b), "mean": round(mean_b, 1)},
        "ratio": round(ratio, 2),
        "mann_whitney_p": round(p_value, 4),
    }


def test_conditional_trigger(orders: pd.DataFrame, params: dict) -> dict:
    """조건 충족 시 vs 미충족 시 후속 확률 비교"""
    trigger_cust = params["trigger_customer"]
    trigger_item = params["trigger_item"]
    min_quantity = params.get("min_quantity")
    effect_cust = params["effect_customer"]
    effect_item = params["effect_item"]
    time_window = params.get("time_window", 30)

    all_triggers = orders[
        (orders["customer"] == trigger_cust) & (orders["item"] == trigger_item)
    ].sort_values("date")

    effect_orders = orders[
        (orders["customer"] == effect_cust) & (orders["item"] == effect_item)
    ].sort_values("date")

    if len(all_triggers) < 3:
        return {"verdict": "insufficient_data", "reason": "트리거 건수 부족"}

    def count_follows(trigger_df):
        hits = 0
        for _, trig in trigger_df.iterrows():
            followers = effect_orders[
                (effect_orders["date"] > trig["date"]) &
                (effect_orders["date"] <= trig["date"] + pd.Timedelta(days=time_window))
            ]
            if len(followers) > 0:
                hits += 1
        return hits

    if min_quantity:
        cond_triggers = all_triggers[all_triggers["quantity"] >= min_quantity]
        non_triggers = all_triggers[all_triggers["quantity"] < min_quantity]
    else:
        return {"verdict": "error", "reason": "조건(min_quantity) 미지정"}

    cond_hits = count_follows(cond_triggers)
    non_hits = count_follows(non_triggers)

    cond_rate = cond_hits / len(cond_triggers) if len(cond_triggers) > 0 else 0
    non_rate = non_hits / len(non_triggers) if len(non_triggers) > 0 else 0

    if cond_rate > non_rate * 1.5 and cond_rate >= 0.5 and len(cond_triggers) >= 2:
        verdict = "confirmed"
    elif cond_rate > non_rate and cond_rate >= 0.3:
        verdict = "partially_confirmed"
    else:
        verdict = "rejected"

    return {
        "verdict": verdict,
        "conditional": {
            "condition": f"qty>={min_quantity}",
            "count": len(cond_triggers),
            "hits": cond_hits,
            "rate": round(cond_rate, 2),
        },
        "baseline": {
            "condition": f"qty<{min_quantity}",
            "count": len(non_triggers),
            "hits": non_hits,
            "rate": round(non_rate, 2),
        },
        "rate_ratio": round(cond_rate / non_rate, 2) if non_rate > 0 else float("inf"),
    }


def test_drift_after_cleaning(orders: pd.DataFrame, params: dict) -> dict:
    """교란 제거 후 drift Spearman 재검정"""
    customer = params["customer"]
    item = params["item"]
    remove_precursor = params.get("remove_precursor")
    remove_lag_max = params.get("remove_lag_max", 5)

    ci_orders = orders[
        (orders["customer"] == customer) & (orders["item"] == item)
    ].sort_values("date").reset_index(drop=True)

    if len(ci_orders) < 6:
        return {"verdict": "insufficient_data", "reason": "주문 건수 부족"}

    # 원본 drift
    dates_raw = ci_orders["date"].values
    ivs_raw = np.diff(dates_raw).astype("timedelta64[D]").astype(int).astype(float)
    rho_raw, p_raw = spearmanr(range(len(ivs_raw)), ivs_raw)

    result = {
        "raw": {
            "n_intervals": len(ivs_raw),
            "spearman_rho": round(float(rho_raw), 3),
            "spearman_p": round(float(p_raw), 3),
        }
    }

    # 정제
    if remove_precursor:
        parts = remove_precursor.split("/")
        prec_cust, prec_item = parts[0], "/".join(parts[1:])

        remove_pos = set()
        for pos in range(len(ci_orders)):
            od = ci_orders.iloc[pos]["date"]
            nearby = orders[
                (orders["customer"] == prec_cust) &
                (orders["item"] == prec_item) &
                (orders["date"] >= od - pd.Timedelta(days=remove_lag_max)) &
                (orders["date"] < od)
            ]
            if len(nearby) > 0:
                remove_pos.add(pos)

        if remove_pos and len(ci_orders) - len(remove_pos) >= 6:
            clean_mask = np.ones(len(ci_orders), dtype=bool)
            for pos in remove_pos:
                clean_mask[pos] = False

            clean_dates = ci_orders[clean_mask]["date"].values
            clean_ivs = np.diff(clean_dates).astype("timedelta64[D]").astype(int).astype(float)

            if len(clean_ivs) >= 6:
                rho_clean, p_clean = spearmanr(range(len(clean_ivs)), clean_ivs)
                nc = len(clean_ivs)
                tc = max(1, nc // 3)

                result["cleaned"] = {
                    "removed": len(remove_pos),
                    "n_intervals": len(clean_ivs),
                    "spearman_rho": round(float(rho_clean), 3),
                    "spearman_p": round(float(p_clean), 3),
                    "first_third_mean": round(float(np.mean(clean_ivs[:tc])), 1),
                    "last_third_mean": round(float(np.mean(clean_ivs[-tc:])), 1),
                }

    # 판정
    cleaned = result.get("cleaned")
    if cleaned and abs(cleaned["spearman_rho"]) > 0.3 and cleaned["spearman_p"] < 0.05:
        verdict = "confirmed"
    elif cleaned and abs(cleaned["spearman_rho"]) > 0.3 and cleaned["spearman_p"] < 0.1:
        verdict = "partially_confirmed"
    elif abs(rho_raw) > 0.3 and p_raw < 0.05:
        verdict = "confirmed"
    else:
        verdict = "rejected"

    result["verdict"] = verdict
    return result


def test_periodicity(orders: pd.DataFrame, params: dict) -> dict:
    """특정 주기 가설의 정확도 측정"""
    customer = params["customer"]
    item = params.get("item")
    expected_period = params["expected_period"]
    tolerance_pct = params.get("tolerance_pct", 15)

    # item이 없으면 해당 고객의 전체 품목에서 주기성 검사
    if item:
        ci_orders = orders[
            (orders["customer"] == customer) & (orders["item"] == item)
        ].sort_values("date")
    else:
        ci_orders = orders[orders["customer"] == customer].sort_values("date")

    if len(ci_orders) < 3:
        return {"verdict": "insufficient_data", "reason": "주문 건수 부족"}

    dates = ci_orders["date"].values
    intervals = np.diff(dates).astype("timedelta64[D]").astype(int)

    tolerance = expected_period * tolerance_pct / 100
    low = expected_period - tolerance
    high = expected_period + tolerance

    matches = sum(1 for iv in intervals if low <= iv <= high)
    accuracy = matches / len(intervals) if len(intervals) > 0 else 0

    deviations = [int(iv) - expected_period for iv in intervals]

    if accuracy >= 0.7:
        verdict = "confirmed"
    elif accuracy >= 0.5:
        verdict = "partially_confirmed"
    else:
        verdict = "rejected"

    return {
        "verdict": verdict,
        "expected_period": expected_period,
        "tolerance": f"±{tolerance_pct}% ({low:.0f}~{high:.0f}일)",
        "matches": matches,
        "total_intervals": len(intervals),
        "accuracy": round(accuracy, 2),
        "actual_intervals": [int(iv) for iv in intervals],
        "mean_interval": round(float(np.mean(intervals)), 1),
        "deviations": deviations,
    }


def test_seasonal_split(orders: pd.DataFrame, params: dict) -> dict:
    """분기별로 분리하여 패턴 강도 비교"""
    from_cust = params.get("from_customer")
    to_cust = params.get("to_customer")
    split_by = params.get("split_by", "quarter")
    lag_min = params.get("lag_min", 1)
    lag_max = params.get("lag_max", 7)

    from_orders = orders[orders["customer"] == from_cust].sort_values("date")
    to_orders = orders[orders["customer"] == to_cust].sort_values("date")

    if split_by == "quarter":
        from_orders["period"] = from_orders["date"].dt.quarter.map(
            {1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"})
    else:
        from_orders["period"] = from_orders["date"].dt.month

    to_dates = sorted(to_orders["date"].dt.normalize().unique())

    period_rates = {}
    for period, group in from_orders.groupby("period"):
        f_dates = sorted(group["date"].dt.normalize().unique())
        hits = 0
        for fd in f_dates:
            for td in to_dates:
                lag = (td - fd).days
                if lag_min <= lag <= lag_max:
                    hits += 1
                    break
        rate = hits / len(f_dates) if f_dates else 0
        period_rates[str(period)] = {"count": len(f_dates), "hits": hits, "rate": round(rate, 2)}

    rates = [v["rate"] for v in period_rates.values() if v["count"] >= 2]

    if not rates:
        return {"verdict": "insufficient_data", "reason": "기간별 데이터 부족"}

    max_rate = max(rates)
    min_rate = min(rates)
    ratio = max_rate / min_rate if min_rate > 0 else float("inf")

    verdict = "confirmed" if ratio >= 2.0 else "rejected"

    return {
        "verdict": verdict,
        "periods": period_rates,
        "max_min_ratio": round(ratio, 2),
    }


def test_event_conversion(orders: pd.DataFrame, params: dict, events: pd.DataFrame = None) -> dict:
    """이벤트→주문 전환율 검정"""
    customer = params.get("customer")
    event_type = params.get("event_type")
    target_item = params.get("target_item")
    max_lag = params.get("max_lag", 30)

    if events is None or len(events) == 0:
        return {"verdict": "insufficient_data", "reason": "이벤트 데이터 없음"}

    ev = events.copy()
    if customer:
        ev = ev[ev["customer"] == customer]
    if event_type:
        ev = ev[ev["event_type"] == event_type]

    if len(ev) < 2:
        return {"verdict": "insufficient_data", "reason": "이벤트 건수 부족"}

    hits = 0
    item_matches = 0
    lags = []
    details = []

    for _, event in ev.iterrows():
        ed = event["date"]
        after = orders[
            (orders["customer"] == event["customer"]) &
            (orders["date"] > ed) &
            (orders["date"] <= ed + pd.Timedelta(days=max_lag))
        ]
        if target_item:
            after_item = after[after["item"] == target_item]
        else:
            after_item = after

        if len(after_item) > 0:
            hits += 1
            lag = (after_item.iloc[0]["date"] - ed).days
            lags.append(lag)
            # 품목 일치 여부
            if "item" in event and len(after[after["item"] == event.get("item", "")]) > 0:
                item_matches += 1
            details.append({"event_date": str(ed.date()), "order_lag": lag, "item_match": True})
        else:
            details.append({"event_date": str(ed.date()), "order_lag": None, "item_match": False})

    conversion_rate = hits / len(ev) if len(ev) > 0 else 0
    item_match_rate = item_matches / hits if hits > 0 else 0
    mean_lag = float(np.mean(lags)) if lags else 0

    if conversion_rate >= 0.7:
        verdict = "confirmed"
    elif conversion_rate >= 0.4:
        verdict = "partially_confirmed"
    else:
        verdict = "rejected"

    return {
        "verdict": verdict,
        "total_events": len(ev),
        "conversions": hits,
        "conversion_rate": round(conversion_rate, 2),
        "item_match_rate": round(item_match_rate, 2),
        "mean_lag": round(mean_lag, 1),
        "lags": lags,
        "details": details,
    }


def test_time_concentration(orders: pd.DataFrame, params: dict) -> dict:
    """특정 요일/주차 집중도 검정"""
    customer = params.get("customer")
    item = params.get("item")
    expected_weekday = params.get("expected_weekday")  # 0=월 ~ 6=일
    expected_week = params.get("expected_week")  # 1~5

    co = orders.copy()
    if customer:
        co = co[co["customer"] == customer]
    if item:
        co = co[co["item"] == item]

    if len(co) < 5:
        return {"verdict": "insufficient_data", "reason": "건수 부족"}

    result = {}

    # 요일 집중도
    weekdays = co["date"].dt.weekday.values  # 0=월 ~ 6=일
    wd_counts = pd.Series(weekdays).value_counts()
    dominant_wd = int(wd_counts.index[0])
    wd_concentration = float(wd_counts.iloc[0] / len(co))

    wd_names = ["월", "화", "수", "목", "금", "토", "일"]
    result["weekday"] = {
        "dominant": wd_names[dominant_wd],
        "dominant_idx": dominant_wd,
        "concentration": round(wd_concentration, 2),
        "distribution": {wd_names[int(k)]: int(v) for k, v in wd_counts.items()},
    }

    # 주차 집중도
    weeks = ((co["date"].dt.day - 1) // 7 + 1).values
    wk_counts = pd.Series(weeks).value_counts()
    dominant_wk = int(wk_counts.index[0])
    wk_concentration = float(wk_counts.iloc[0] / len(co))

    result["week_of_month"] = {
        "dominant": f"W{dominant_wk}",
        "dominant_idx": dominant_wk,
        "concentration": round(wk_concentration, 2),
        "distribution": {f"W{int(k)}": int(v) for k, v in wk_counts.items()},
    }

    # 판정
    confirmed_wd = False
    confirmed_wk = False

    if expected_weekday is not None:
        confirmed_wd = (dominant_wd == expected_weekday and wd_concentration >= 0.3)
    if expected_week is not None:
        confirmed_wk = (dominant_wk == expected_week and wk_concentration >= 0.3)

    if expected_weekday is not None and expected_week is not None:
        if confirmed_wd and confirmed_wk:
            verdict = "confirmed"
        elif confirmed_wd or confirmed_wk:
            verdict = "partially_confirmed"
        else:
            verdict = "rejected"
    elif expected_weekday is not None:
        verdict = "confirmed" if confirmed_wd else ("partially_confirmed" if wd_concentration >= 0.25 else "rejected")
    elif expected_week is not None:
        verdict = "confirmed" if confirmed_wk else ("partially_confirmed" if wk_concentration >= 0.25 else "rejected")
    else:
        # 기대값 없음 — 집중도만 보고
        if wd_concentration >= 0.35 or wk_concentration >= 0.35:
            verdict = "confirmed"
        elif wd_concentration >= 0.25 or wk_concentration >= 0.25:
            verdict = "partially_confirmed"
        else:
            verdict = "rejected"

    result["verdict"] = verdict
    return result


def test_co_occurrence(orders: pd.DataFrame, params: dict) -> dict:
    """같은 주 동반 발주 검정"""
    item_a = params.get("item_a")
    item_b = params.get("item_b")
    customer = params.get("customer")  # optional: 특정 고객만

    co = orders.copy()
    if customer:
        co = co[co["customer"] == customer]

    co["year_week"] = co["date"].dt.isocalendar().apply(
        lambda x: f"{x.year}-W{x.week:02d}", axis=1)

    weeks_a = set(co[co["item"] == item_a]["year_week"])
    weeks_b = set(co[co["item"] == item_b]["year_week"])
    all_weeks = set(co["year_week"])

    co_weeks = weeks_a & weeks_b
    n_co = len(co_weeks)
    n_a = len(weeks_a)
    n_b = len(weeks_b)
    n_total = len(all_weeks)

    if n_a < 2 or n_b < 2:
        return {"verdict": "insufficient_data", "reason": "건수 부족"}

    # 기대값 (독립 가정)
    expected = n_a * n_b / n_total if n_total > 0 else 0
    lift = n_co / expected if expected > 0 else float("inf")

    support = n_co / n_total if n_total > 0 else 0

    if lift >= 2.0 and n_co >= 3:
        verdict = "confirmed"
    elif lift >= 1.5 and n_co >= 2:
        verdict = "partially_confirmed"
    else:
        verdict = "rejected"

    return {
        "verdict": verdict,
        "item_a": item_a,
        "item_b": item_b,
        "co_occurrence_weeks": n_co,
        "weeks_a": n_a,
        "weeks_b": n_b,
        "total_weeks": n_total,
        "expected_random": round(expected, 1),
        "lift": round(lift, 2),
        "support": round(support, 3),
    }


# ============================================================
# 디스패처
# ============================================================

TEST_FUNCTIONS = {
    "cross_customer_binary": test_cross_customer_binary,
    "quantity_comparison": test_quantity_comparison,
    "conditional_trigger": test_conditional_trigger,
    "drift_after_cleaning": test_drift_after_cleaning,
    "periodicity_test": test_periodicity,
    "seasonal_split": test_seasonal_split,
    "event_conversion": test_event_conversion,
    "time_concentration": test_time_concentration,
    "co_occurrence_test": test_co_occurrence,
}

# LLM이 자주 생성하는 잘못된 test_type → 올바른 매핑
TEST_TYPE_ALIASES = {
    "co_occurrence": "co_occurrence_test",
    "event_order_lag": "event_conversion",
    "event_trigger": "event_conversion",
    "event_trigger_test": "event_conversion",
    "event_conversion_test": "event_conversion",
    "periodicity": "periodicity_test",
    "cross_customer": "cross_customer_binary",
    "cross_customer_test": "cross_customer_binary",
    "drift": "drift_after_cleaning",
    "seasonal": "seasonal_split",
    "seasonal_test": "seasonal_split",
    "time_concentration_test": "time_concentration",
}


def normalize_test_params(test_type: str, params: dict) -> dict:
    """LLM이 생성한 파라미터를 함수 시그니처에 맞게 보정"""
    params = dict(params)

    # periodicity_test: tolerance_pct가 0이면 기본값 15로
    if test_type == "periodicity_test":
        if params.get("tolerance_pct", 15) == 0:
            params["tolerance_pct"] = 15

    # seasonal_split: "all" 같은 비실제 고객명 처리
    if test_type == "seasonal_split":
        if params.get("from_customer") in ("all", "전체", "*"):
            return None  # skip
        if params.get("to_customer") in ("all", "전체", "*"):
            return None

    # co_occurrence_test는 item_a/item_b를 그대로 사용
    if test_type == "co_occurrence_test" and "item_a" in params:
        return params  # 정상 파라미터

    # 잘못된 co_occurrence → cross_customer_binary 변환 시 파라미터 매핑
    if "item_a" in params and "trigger_customer" not in params and test_type != "co_occurrence_test":
        return None

    # event_order_lag → conditional_trigger 변환 시 파라미터 매핑
    if "event_type" in params and "trigger_customer" not in params:
        customer = params.get("customer", "")
        params["trigger_customer"] = customer
        params["effect_customer"] = customer
        params.setdefault("trigger_item", "")
        params.setdefault("effect_item", "")
        params.setdefault("min_quantity", 1)
        params.setdefault("time_window", 30)

    return params


def run_test(hypothesis: dict, orders: pd.DataFrame, events: pd.DataFrame = None) -> dict:
    test_type = hypothesis["test_type"]
    params = hypothesis.get("params", {})

    # test_type 별칭 매핑
    if test_type not in TEST_FUNCTIONS and test_type in TEST_TYPE_ALIASES:
        test_type = TEST_TYPE_ALIASES[test_type]

    func = TEST_FUNCTIONS.get(test_type)
    if func is None:
        return {"verdict": "error", "reason": f"알 수 없는 검정 유형: {hypothesis['test_type']}"}

    # 파라미터 보정
    params = normalize_test_params(test_type, params)
    if params is None:
        return {"verdict": "error",
                "reason": f"파라미터 변환 불가: {hypothesis.get('test_type')} → {test_type}",
                "params_received": hypothesis.get("params", {})}

    try:
        # event_conversion은 events도 필요
        if test_type == "event_conversion":
            result = func(orders, params, events=events)
        else:
            result = func(orders, params)
    except (KeyError, TypeError, ValueError) as e:
        return {"verdict": "error", "reason": f"{test_type} 실행 실패: {e}",
                "params_received": params}

    result["statement"] = hypothesis.get("statement", "")
    result["success_criteria"] = hypothesis.get("success_criteria", "")
    return result


def main():
    parser = argparse.ArgumentParser(description="Phase 3: 가설 검정")
    parser.add_argument("--data-dir", required=True, help="CSV 데이터 디렉토리")
    parser.add_argument("--hypotheses", required=True, help="hypotheses.json 경로")
    parser.add_argument("--output", default=None, help="결과 저장 경로")
    args = parser.parse_args()

    orders, _ = load_data(args.data_dir)
    print(f"데이터 로드: 주문 {len(orders)}건")

    with open(args.hypotheses, "r", encoding="utf-8") as f:
        hyp_data = json.load(f)

    hypotheses = hyp_data.get("hypotheses", [])
    print(f"가설 검정: {len(hypotheses)}건")

    results = {}
    for hyp in hypotheses:
        hyp_id = hyp["id"]
        print(f"\n  [{hyp_id}] {hyp.get('statement', hyp['test_type'])}...")
        result = run_test(hyp, orders)
        results[hyp_id] = result
        print(f"    → {result.get('verdict', '?')}")

    output_path = args.output or os.path.join(
        os.path.dirname(args.hypotheses), "phase3_results.json"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n결과 저장: {output_path}")

    # 요약
    verdicts = [r.get("verdict", "?") for r in results.values()]
    confirmed = verdicts.count("confirmed")
    partial = verdicts.count("partially_confirmed")
    rejected = verdicts.count("rejected")
    print(f"요약: 확인 {confirmed}, 부분확인 {partial}, 기각 {rejected}")


if __name__ == "__main__":
    main()
