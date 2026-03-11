"""
Signal Extractor: level0_results.json → 자동 발견 + LLM용 요약

1) extract_auto_findings: 통계적으로 확실한 패턴을 자동 추출 (LLM 번역 불필요)
2) summarize: 나머지 모든 데이터를 LLM이 읽을 수 있는 마크다운으로
"""

import json


# ============================================================
# 자동 발견: ML이 이미 답을 가진 패턴을 직접 추출
# ============================================================

def extract_auto_findings(level0: dict) -> list[dict]:
    """level0 결과에서 통계적으로 확실한 패턴을 자동 추출.

    각 finding은:
    - id: AF-001 형식
    - type: periodic / cross_customer / event_trigger / drift / time_concentration / association
    - statement: 자연어 서술
    - evidence: 통계적 근거
    - confidence: 자동 부여 (0.7~1.0)
    - entities: customer, item 등
    - verification: 이미 검증된 것이므로 추가 테스트 불필요
    """
    findings = []
    fid = 0

    intervals = level0.get("interval_analysis", {})
    gmm = level0.get("gmm_mixture", {})
    comp_reanalysis = level0.get("component_reanalysis", {})
    trends = level0.get("trend_changes", {})
    proximity = level0.get("customer_proximity", [])
    events = level0.get("event_order_lag", {})
    time_patterns = level0.get("time_patterns", {})
    conc = time_patterns.get("customer_time_concentration", {})
    multi = level0.get("multi_condition", {})
    co_occurrence = level0.get("co_occurrence", [])

    # ── 1. 주기성: CV < 0.10 → 거의 확실한 주기 ──
    for key, data in intervals.items():
        cv = data.get("cv", 1)
        count = data.get("count", 0)
        mean = data.get("mean_interval", 0)
        if cv < 0.10 and count >= 3:
            customer, item = key.split("/", 1)
            fid += 1
            findings.append({
                "id": f"AF-{fid:03d}",
                "type": "periodic",
                "statement": f"{customer}는 {item}을 {mean:.0f}일 주기로 발주한다",
                "entities": {"customer": customer, "item": item},
                "evidence": {
                    "mean_interval": mean, "cv": cv, "count": count,
                    "intervals": data.get("intervals", []),
                },
                "confidence": 1.0 if cv == 0 else 0.9,
            })

    # ── 2. GMM 메인 성분 주기: 혼합 패턴에서 메인 성분 추출 ──
    for key, data in comp_reanalysis.items():
        components = data.get("components", [])
        main_comp = next((c for c in components if c.get("is_main")), None)
        sub_comps = [c for c in components if not c.get("is_main")]

        if main_comp and sub_comps and main_comp["n"] >= 5:
            customer, item = key.split("/", 1)
            main_mean = main_comp["mean"]
            main_n = main_comp["n"]
            total_n = sum(c["n"] for c in components)

            # 메인 성분이 전체의 60% 이상이면 유의미
            if main_n / total_n >= 0.6:
                fid += 1
                sub_desc = ", ".join(
                    f"부성분({c['n']}건, {c['mean']:.1f}일)" for c in sub_comps)
                findings.append({
                    "id": f"AF-{fid:03d}",
                    "type": "periodic_with_noise",
                    "statement": f"{customer}의 {item} 주요 발주 주기는 {main_mean:.0f}일이다 (전체 {total_n}건 중 {main_n}건, {sub_desc})",
                    "entities": {"customer": customer, "item": item},
                    "evidence": {
                        "main_period": main_mean, "main_count": main_n,
                        "total_count": total_n,
                        "sub_components": [{"n": c["n"], "mean": c["mean"]} for c in sub_comps],
                    },
                    "confidence": 0.8,
                })

    # ── 3. GMM 교차 패턴: 부성분의 원인이 다른 고객일 때 ──
    for key, data in comp_reanalysis.items():
        components = data.get("components", [])
        customer, item = key.split("/", 1)

        for comp in components:
            if comp.get("is_main"):
                continue
            candidates = comp.get("cross_pattern_candidates", [])
            for cand in candidates:
                hit_rate = cand["count"] / cand["total"] if cand["total"] > 0 else 0
                if hit_rate >= 0.5 and cand["count"] >= 2:
                    precursor = cand["precursor"]  # "한진산업/STS304" 형식
                    prec_parts = precursor.split("/", 1)
                    prec_cust = prec_parts[0]
                    prec_item = prec_parts[1] if len(prec_parts) > 1 else ""

                    fid += 1
                    findings.append({
                        "id": f"AF-{fid:03d}",
                        "type": "cross_customer",
                        "statement": f"{customer}의 {item} 짧은간격 발주 중 {cand['count']}/{cand['total']}건이 {precursor} 발주 직후 발생한다",
                        "entities": {
                            "customer": customer, "item": item,
                            "trigger_customer": prec_cust, "trigger_item": prec_item,
                        },
                        "evidence": {
                            "sub_component_mean": comp["mean"],
                            "sub_component_n": comp["n"],
                            "precursor": precursor,
                            "hit_count": cand["count"],
                            "total": cand["total"],
                            "hit_rate": hit_rate,
                        },
                        "confidence": 0.7 if hit_rate >= 0.6 else 0.6,
                    })

    # ── 4. 정제 후 drift: p < 0.05 ──
    for key, data in comp_reanalysis.items():
        cleaned = data.get("cleaned_drift", {})
        if not cleaned:
            continue
        rho = cleaned.get("spearman_rho")
        p = cleaned.get("spearman_p")
        if rho is not None and p is not None and p < 0.05 and abs(rho) > 0.3:
            customer, item = key.split("/", 1)
            direction = "증가" if rho > 0 else "감소"
            first = cleaned.get("first_third_mean", 0)
            last = cleaned.get("last_third_mean", 0)
            precursor = cleaned.get("precursor", "")

            fid += 1
            findings.append({
                "id": f"AF-{fid:03d}",
                "type": "drift",
                "statement": f"{customer}의 {item} 발주 간격이 시간에 따라 {direction}한다 ({first:.0f}일→{last:.0f}일, 교란 제거 후 rho={rho:.3f}, p={p:.3f})",
                "entities": {"customer": customer, "item": item},
                "evidence": {
                    "spearman_rho": rho, "spearman_p": p,
                    "first_third_mean": first, "last_third_mean": last,
                    "precursor_removed": precursor,
                    "clean_intervals": cleaned.get("clean_intervals", []),
                },
                "confidence": 0.8 if p < 0.01 else 0.7,
            })

    # ── 5. 이벤트→주문 전환: 전환율 ≥ 80% ──
    for key, data in events.items():
        rate = data.get("follow_rate", 0)
        item_match = data.get("item_match_rate", 0)
        count = data.get("event_count", 0)
        if rate >= 0.8 and count >= 3:
            customer = data["customer"]
            event_type = data["event_type"]
            mean_lag = data.get("mean_lag", 0)

            fid += 1
            findings.append({
                "id": f"AF-{fid:03d}",
                "type": "event_trigger",
                "statement": f"{customer}의 {event_type}은 {rate:.0%} 확률로 주문으로 전환된다 (평균 {mean_lag:.0f}일 지연, 품목일치 {item_match:.0%})",
                "entities": {"customer": customer, "event_type": event_type},
                "evidence": {
                    "conversion_rate": rate, "event_count": count,
                    "mean_lag": mean_lag, "item_match_rate": item_match,
                },
                "confidence": 0.9 if rate >= 0.9 and item_match >= 0.8 else 0.7,
            })

    # ── 6. 시간 집중도: concentration ≥ 0.30 ──
    for cust, data in conc.items():
        wd_conc = data.get("weekday_concentration", 0)
        wom_conc = data.get("week_of_month_concentration", 0)
        dom_wd = data.get("dominant_weekday", "")
        dom_wk = data.get("dominant_week", "")

        parts = []
        if wd_conc >= 0.30:
            parts.append(f"{dom_wd}요일 집중({wd_conc:.0%})")
        if wom_conc >= 0.20:
            parts.append(f"{dom_wk} 집중({wom_conc:.0%})")

        if parts:
            fid += 1
            findings.append({
                "id": f"AF-{fid:03d}",
                "type": "time_concentration",
                "statement": f"{cust}의 발주는 {', '.join(parts)}",
                "entities": {"customer": cust},
                "evidence": {
                    "weekday_concentration": wd_conc,
                    "dominant_weekday": dom_wd,
                    "week_of_month_concentration": wom_conc,
                    "dominant_week": dom_wk,
                },
                "confidence": 0.8 if (wd_conc >= 0.4 or wom_conc >= 0.3) else 0.6,
            })

    # ── 7. 연관 규칙: lift ≥ 2.5 AND 조건부확률 ≥ 70% ──
    for rule in multi.get("top_single_associations", []):
        lift = rule.get("lift", 0)
        p_given = rule.get("p_given_cond", 0)
        support = rule.get("support", 0)
        if lift >= 2.5 and p_given >= 0.7 and support >= 2:
            fid += 1
            findings.append({
                "id": f"AF-{fid:03d}",
                "type": "association",
                "statement": f"{rule['condition']} 후 {rule['target']}이 따른다 (lift={lift:.1f}, 확률={p_given:.0%}, {support}건)",
                "entities": {"condition": rule["condition"], "target": rule["target"]},
                "evidence": {
                    "lift": lift, "conditional_probability": p_given,
                    "support": support,
                },
                "confidence": 0.7 if support >= 3 else 0.5,
            })

    # ── 8. 교차 고객: lift ≥ 1.5 AND 건수 ≥ 5 ──
    for data in proximity:
        lift = data.get("lift", 0)
        prob = data.get("probability", 0)
        follow = data.get("follow_count", 0)
        total = data.get("total", 0)
        if lift >= 1.5 and follow >= 5 and prob >= 0.5:
            fid += 1
            findings.append({
                "id": f"AF-{fid:03d}",
                "type": "cross_customer_proximity",
                "statement": f"{data['from']} 발주 후 1~8일 내 {data['to']} 발주 확률이 높다 (lift={lift:.2f}, {prob:.0%}, {follow}/{total}건)",
                "entities": {
                    "trigger_customer": data["from"],
                    "effect_customer": data["to"],
                },
                "evidence": {
                    "lift": lift, "probability": prob,
                    "follow_count": follow, "total": total,
                    "expected_random": data.get("expected_random", 0),
                },
                "confidence": 0.7 if lift >= 2.0 else 0.5,
            })

    return findings


# ============================================================
# LLM용 요약 (변경 없음)
# ============================================================

def summarize(level0: dict) -> str:
    """level0 결과를 LLM이 읽기 좋은 마크다운 요약으로 변환"""
    sections = []

    # ── 1. 데이터 개요 ──
    schema = level0.get("schema", {})
    basic = level0.get("basic_distribution", {})
    qty_stats = basic.get("quantity_stats", {})
    date_range = schema.get("date_range", ["?", "?"])

    sections.append(f"""## 1. 데이터 개요
- 기간: {date_range[0]} ~ {date_range[1]}
- 주문: {schema.get('rows', '?')}건, 고객 {schema.get('n_customers', '?')}개, 품목 {schema.get('n_items', '?')}개
- 수량: 평균 {qty_stats.get('mean', '?')}, 중앙값 {qty_stats.get('median', '?')}, 최대 {qty_stats.get('max', '?')}""")

    # ── 2. 주문 간격 분석 (핵심 테이블) ──
    intervals = level0.get("interval_analysis", {})
    gmm = level0.get("gmm_mixture", {})
    trends = level0.get("trend_changes", {})

    rows = []
    for key in sorted(intervals.keys()):
        data = intervals[key]
        count = data["count"]
        mean = data["mean_interval"]
        cv = data["cv"]
        min_iv = data["min_interval"]
        max_iv = data["max_interval"]

        # GMM
        gmm_data = gmm.get(key, {})
        n_comp = gmm_data.get("n_components", "-")

        # Trend
        trend_data = trends.get(key, {})
        rho = trend_data.get("spearman_rho")
        rho_str = f"{rho:+.2f}" if rho is not None else "-"
        pct = trend_data.get("pct_change")
        pct_str = f"{pct:+.1f}%" if pct is not None else ""

        rows.append(
            f"| {key} | {count} | {mean:.1f}일 | {cv:.2f} | {min_iv}~{max_iv} | {n_comp} | {rho_str} {pct_str} |")

    sections.append(
        "\n## 2. 주문 간격 분석\n"
        "| 고객/품목 | 건수 | 평균간격 | CV | 범위 | GMM성분 | 추세(rho, 변화율) |\n"
        "|---|---|---|---|---|---|---|")
    sections.append("\n".join(rows))

    # ── 3. GMM 성분 재분석 (2+ components만) ──
    comp_reanalysis = level0.get("component_reanalysis", {})
    if comp_reanalysis:
        rows = []
        for key, data in comp_reanalysis.items():
            components = data.get("components", [])
            cleaned = data.get("cleaned_drift", {})

            comp_strs = []
            cross_strs = []
            for c in components:
                label = "메인" if c.get("is_main") else "부"
                comp_strs.append(f"{label}({c['n']}건, mean={c['mean']:.1f}일)")
                for cp in c.get("cross_pattern_candidates", []):
                    cross_strs.append(f"{cp['precursor']}({cp['count']}/{cp['total']})")

            comp_str = ", ".join(comp_strs)
            cross_str = ", ".join(cross_strs) if cross_strs else "-"

            clean_str = "-"
            if cleaned:
                clean_rho = cleaned.get("spearman_rho")
                clean_p = cleaned.get("spearman_p")
                if clean_rho is not None:
                    clean_str = f"rho={clean_rho:.3f}, p={clean_p:.3f}"

            rows.append(f"| {key} | {comp_str} | {cross_str} | {clean_str} |")

        sections.append(
            "\n## 3. GMM 성분 재분석 (혼합 패턴 상세)\n"
            "| 고객/품목 | 성분 구성 | 교차 패턴 후보 | 정제 후 추세 |\n"
            "|---|---|---|---|")
        sections.append("\n".join(rows))

    # ── 4. 교차 고객 패턴 ──
    proximity = level0.get("customer_proximity", [])
    if proximity:
        rows = []
        for data in sorted(proximity, key=lambda x: -x.get("lift", 0)):
            rows.append(
                f"| {data['from']}→{data['to']} | {data.get('lift', 0):.2f} | "
                f"{data.get('probability', 0):.0%} | {data.get('follow_count', 0)}/{data.get('total', 0)} |")

        sections.append(
            "\n## 4. 교차 고객 패턴 (1~8일 lag)\n"
            "| 방향 | lift | 확률 | 건수 |\n"
            "|---|---|---|---|")
        sections.append("\n".join(rows))

    # ── 5. 이벤트→주문 전환 ──
    events = level0.get("event_order_lag", {})
    if events:
        rows = []
        for key, data in events.items():
            rows.append(
                f"| {data['customer']}/{data['event_type']} | {data['event_count']} | "
                f"{data['follow_rate']:.0%} | {data.get('mean_lag', 0):.1f}일 | "
                f"{data.get('item_match_rate', 0):.0%} |")

        sections.append(
            "\n## 5. 이벤트→주문 전환\n"
            "| 이벤트 | 건수 | 전환율 | 평균지연 | 품목일치율 |\n"
            "|---|---|---|---|---|")
        sections.append("\n".join(rows))

    # ── 6. 품목 동반 발주 ──
    co = level0.get("co_occurrence", [])
    if co:
        rows = []
        for data in sorted(co, key=lambda x: -x.get("count", 0)):
            rows.append(
                f"| {data['item_a']}↔{data['item_b']} | {data['count']} | {data['support']:.3f} |")

        sections.append(
            "\n## 6. 품목 동반 발주 (같은 주)\n"
            "| 품목 쌍 | 건수 | support |\n"
            "|---|---|---|")
        sections.append("\n".join(rows))

    # ── 7. 시간 집중도 ──
    time_patterns = level0.get("time_patterns", {})
    conc = time_patterns.get("customer_time_concentration", {})
    if conc:
        rows = []
        for cust in sorted(conc.keys()):
            data = conc[cust]
            wd = data.get("weekday_concentration", 0)
            dom_wd = data.get("dominant_weekday", "")
            wom = data.get("week_of_month_concentration", 0)
            dom_w = data.get("dominant_week", "")
            rows.append(f"| {cust} | {wd:.2f} ({dom_wd}) | {wom:.2f} ({dom_w}) |")

        sections.append(
            "\n## 7. 시간 집중도 (0=균일, 1=극집중)\n"
            "| 고객 | 요일집중 | 주차집중 |\n"
            "|---|---|---|")
        sections.append("\n".join(rows))

    # ── 8. 월별 추이 ──
    monthly = time_patterns.get("monthly", {})
    if monthly:
        rows = []
        for month in sorted(monthly.keys()):
            data = monthly[month]
            rows.append(f"| {month} | {data['orders']} | {data['total_qty']} |")

        sections.append(
            "\n## 8. 월별 추이\n"
            "| 월 | 주문수 | 총수량 |\n"
            "|---|---|---|")
        sections.append("\n".join(rows))

    # ── 9. 수량 패턴 ──
    qty = level0.get("quantity_patterns", {})
    if qty:
        rows = []
        for key in sorted(qty.keys()):
            data = qty[key]
            bimodal = data.get("bimodal_score")
            bimodal_str = f"{bimodal:.2f}" if bimodal is not None else "-"
            rows.append(
                f"| {key} | {data['count']} | {data['mean']:.1f} | "
                f"{data.get('cv', 0):.2f} | {bimodal_str} |")

        sections.append(
            "\n## 9. 수량 패턴\n"
            "| 고객/품목 | 건수 | 평균수량 | 수량CV | bimodal |\n"
            "|---|---|---|---|---|")
        sections.append("\n".join(rows))

    # ── 10. 연관 규칙 (상위) ──
    multi = level0.get("multi_condition", {})
    top_rules = multi.get("top_single_associations", [])
    if top_rules:
        rows = []
        for rule in top_rules[:15]:
            rows.append(
                f"| {rule['condition']} → {rule['target']} | {rule['lift']:.2f} | "
                f"{rule['support']} | {rule.get('p_given_cond', 0):.0%} |")

        sections.append(
            "\n## 10. 연관 규칙 (상위)\n"
            "| 조건 → 결과 | lift | support | 조건부확률 |\n"
            "|---|---|---|---|")
        sections.append("\n".join(rows))

    return "\n".join(sections)


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "synthetic/results/level0_results.json"
    with open(path, "r", encoding="utf-8") as f:
        level0 = json.load(f)

    # 자동 발견 출력
    findings = extract_auto_findings(level0)
    print(f"=== 자동 발견: {len(findings)}개 ===\n")
    for f in findings:
        print(f"[{f['id']}] ({f['type']}, conf={f['confidence']}) {f['statement']}")

    print(f"\n=== 요약 테이블 ===\n")
    print(summarize(level0))
