"""
Phase 3: 검증

LLM이 발견한 규칙(llm_rules.json)을 실제 심어둔 패턴(P1~P10)과 대조하여
발견율, 거짓양성, 매칭 상세를 보고서로 생성한다.

Usage:
    python phase3_verify.py
    python phase3_verify.py --results-dir synthetic/results --data-dir synthetic/data
"""

import argparse
import json
import os
from datetime import datetime


# 정답 패턴 정의 (P1~P10)
GROUND_TRUTH = {
    "P1": {
        "type": "periodic",
        "customer": "한진산업",
        "item": "STS304",
        "desc": "월초 발주 (약 28일 주기)",
    },
    "P2": {
        "type": "seasonal",
        "desc": "봄철(4~5월) 수량 증가",
    },
    "P3": {
        "type": "periodic",
        "customer": "대성기업",
        "item": "AL6061",
        "desc": "격주 발주 (약 14일 주기)",
    },
    "P4": {
        "type": "cross_customer",
        "from": "한진산업",
        "to": "대성기업",
        "desc": "한진산업 발주 후 2~4일 내 대성기업 추가 발주",
    },
    "P5": {
        "type": "exception",
        "customer": "한진산업",
        "desc": "공휴일 월에 둘째 주로 밀림",
    },
    "P6": {
        "type": "periodic",
        "customer": "세진테크",
        "desc": "분기별(91일) 3품목(STS304, AL5052, CARBON_STEEL) 묶음 발주",
    },
    "P7": {
        "type": "co_occurrence",
        "items": ["STS304", "CU_PIPE"],
        "desc": "STS304와 CU_PIPE 동반 발주",
    },
    "P8": {
        "type": "event_trigger",
        "customer": "동아전자",
        "desc": "견적요청 후 평균 10일 뒤 발주, 품목 일치",
    },
    "P9": {
        "type": "conditional",
        "from": "한진산업",
        "to": "세진테크",
        "desc": "한진산업 대형발주(150kg+) 후 세진테크 STS316 발주",
    },
    "P10": {
        "type": "drift",
        "customer": "대성기업",
        "item": "AL6061",
        "desc": "발주 간격이 후반부로 갈수록 증가 (14일→21일)",
    },
}


def load_rules(results_dir: str) -> dict:
    path = os.path.join(results_dir, "llm_rules.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize(s: str) -> str:
    """비교를 위한 정규화"""
    return s.strip().lower().replace(" ", "")


def match_rule_to_pattern(rule: dict, pattern_id: str, pattern: dict) -> tuple[bool, str]:
    """규칙이 특정 패턴과 매칭되는지 판단. (matched, reason) 반환."""
    r_type = rule.get("type", "")
    r_content = rule.get("content", "")
    r_entities = rule.get("entities", {})
    r_evidence = rule.get("evidence", "")
    text = f"{r_content} {r_evidence} {r_type}"

    p_type = pattern.get("type", "")

    # 타입 매칭 (유연하게)
    type_aliases = {
        "periodic": ["periodic", "regular", "cycle", "주기"],
        "seasonal": ["seasonal", "season", "계절"],
        "cross_customer": ["cross_customer", "cross", "교차", "연쇄"],
        "co_occurrence": ["co_occurrence", "cooccurrence", "동반", "bundle"],
        "event_trigger": ["event_trigger", "event", "trigger", "견적", "이벤트"],
        "conditional": ["conditional", "condition", "조건"],
        "drift": ["drift", "trend", "추세", "변화"],
        "exception": ["exception", "예외", "공휴일", "holiday"],
    }

    # 엔티티 매칭
    def has_customer(cust: str) -> bool:
        return (cust in r_entities.get("customer", "") or
                cust in r_entities.get("from", "") or
                cust in r_entities.get("to", "") or
                cust in r_content)

    def has_item(item: str) -> bool:
        items_list = r_entities.get("items", [])
        return (item in r_entities.get("item", "") or
                item in str(items_list) or
                item in r_content)

    # P1: 한진산업 + STS304 + periodic
    if pattern_id == "P1":
        if has_customer("한진산업") and has_item("STS304"):
            if r_type in type_aliases["periodic"] or any(kw in text for kw in ["주기", "월", "28일", "30일", "정기"]):
                return True, "고객+품목+주기 매칭"
        return False, ""

    # P2: 봄/계절 + 수량 증가
    if pattern_id == "P2":
        season_kw = ["봄", "spring", "4월", "5월", "계절", "seasonal", "season"]
        if any(kw in text for kw in season_kw):
            if any(kw in text for kw in ["증가", "높", "상승", "peak", "surge"]):
                return True, "계절성+증가 매칭"
        if r_type in type_aliases["seasonal"]:
            return True, "seasonal 타입 매칭"
        return False, ""

    # P3: 대성기업 + AL6061 + periodic
    if pattern_id == "P3":
        if has_customer("대성기업") and has_item("AL6061"):
            if r_type in type_aliases["periodic"] or any(kw in text for kw in ["격주", "14일", "12일", "bi-weekly", "2주"]):
                return True, "고객+품목+격주 매칭"
        return False, ""

    # P4: 한진산업→대성기업 교차
    if pattern_id == "P4":
        if has_customer("한진산업") and has_customer("대성기업"):
            if r_type in type_aliases["cross_customer"] or any(kw in text for kw in ["교차", "연쇄", "따라", "후", "뒤"]):
                return True, "교차 발주 매칭"
        return False, ""

    # P5: 공휴일 예외
    if pattern_id == "P5":
        if any(kw in text for kw in ["공휴일", "연휴", "holiday", "예외", "밀림", "둘째"]):
            if has_customer("한진산업") or r_type in type_aliases["exception"]:
                return True, "공휴일 예외 매칭"
        return False, ""

    # P6: 세진테크 + 분기
    if pattern_id == "P6":
        if has_customer("세진테크"):
            if any(kw in text for kw in ["분기", "91일", "90일", "quarterly", "3품목", "묶음", "bundle"]):
                return True, "세진테크 분기 매칭"
            if r_type in type_aliases["periodic"] and any(kw in text for kw in ["91", "90", "quarter"]):
                return True, "세진테크 주기 매칭"
        return False, ""

    # P7: STS304 + CU_PIPE 동반
    if pattern_id == "P7":
        if has_item("STS304") and has_item("CU_PIPE"):
            return True, "동반 발주 매칭"
        if r_type in type_aliases["co_occurrence"]:
            if "STS304" in text and "CU_PIPE" in text:
                return True, "동반 발주 내용 매칭"
        return False, ""

    # P8: 동아전자 + 견적→발주
    if pattern_id == "P8":
        if has_customer("동아전자"):
            if any(kw in text for kw in ["견적", "이벤트", "event", "trigger", "전환"]):
                return True, "견적→발주 매칭"
        if r_type in type_aliases["event_trigger"] and "동아전자" in text:
            return True, "이벤트 트리거 매칭"
        return False, ""

    # P9: 한진산업 대형→세진테크 STS316
    if pattern_id == "P9":
        if has_customer("한진산업") and (has_customer("세진테크") or "세진테크" in text):
            if any(kw in text for kw in ["대형", "150", "대량", "high_qty", "조건", "conditional"]):
                return True, "조건부 발주 매칭"
        if r_type in type_aliases["conditional"]:
            if "한진산업" in text and "세진테크" in text:
                return True, "조건부 타입 매칭"
        return False, ""

    # P10: 대성기업 AL6061 drift
    if pattern_id == "P10":
        if has_customer("대성기업"):
            if r_type in type_aliases["drift"] or any(kw in text for kw in ["drift", "추세", "증가", "변화", "길어"]):
                if has_item("AL6061") or "간격" in text or "interval" in text:
                    return True, "drift 매칭"
        return False, ""

    return False, ""


def verify(rules_data: dict) -> dict:
    """규칙 vs 정답 매칭 수행"""
    rules = rules_data.get("rules", [])
    results = {}
    used_rules = set()

    # 각 패턴에 대해 매칭되는 규칙 찾기
    for pid, pattern in GROUND_TRUTH.items():
        matched_rules = []
        for rule in rules:
            is_match, reason = match_rule_to_pattern(rule, pid, pattern)
            if is_match:
                matched_rules.append({
                    "rule_id": rule.get("id", "?"),
                    "content": rule.get("content", ""),
                    "confidence": rule.get("confidence", 0),
                    "reason": reason,
                })
                used_rules.add(rule.get("id", ""))

        results[pid] = {
            "pattern": pattern,
            "found": len(matched_rules) > 0,
            "matched_rules": matched_rules,
        }

    # 거짓 양성 (어떤 패턴에도 매칭되지 않은 규칙)
    false_positives = []
    for rule in rules:
        rid = rule.get("id", "")
        if rid not in used_rules:
            false_positives.append({
                "rule_id": rid,
                "content": rule.get("content", ""),
                "type": rule.get("type", ""),
                "confidence": rule.get("confidence", 0),
            })

    return {
        "pattern_results": results,
        "false_positives": false_positives,
        "total_rules": len(rules),
    }


def generate_report(verification: dict) -> str:
    """마크다운 검증 보고서 생성"""
    pr = verification["pattern_results"]
    fp = verification["false_positives"]
    total_rules = verification["total_rules"]

    found_count = sum(1 for v in pr.values() if v["found"])
    total_patterns = len(GROUND_TRUTH)

    lines = []
    lines.append("# 통합 실험 검증 보고서")
    lines.append("")
    lines.append(f"> 생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 실험: v2_stats_e2e (Phase 1 통계 → Phase 2 LLM 규칙 발견)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 요약
    lines.append("## 요약")
    lines.append("")
    lines.append(f"- **심어둔 패턴**: {total_patterns}개 (P1~P10)")
    lines.append(f"- **LLM 발견 규칙**: {total_rules}개")
    lines.append(f"- **매칭 성공**: {found_count}/{total_patterns}개 "
                  f"({found_count/total_patterns*100:.0f}%)")
    lines.append(f"- **미발견**: {total_patterns - found_count}개")
    lines.append(f"- **거짓 양성**: {len(fp)}개")
    lines.append("")

    # 난이도별 분류
    easy = ["P1", "P3", "P6"]
    medium = ["P2", "P7", "P8", "P4"]
    hard = ["P5", "P9", "P10"]

    def count_found(pids):
        return sum(1 for p in pids if pr[p]["found"])

    lines.append("### 난이도별 결과")
    lines.append(f"- Easy (P1,P3,P6): {count_found(easy)}/{len(easy)}")
    lines.append(f"- Medium (P2,P4,P7,P8): {count_found(medium)}/{len(medium)}")
    lines.append(f"- Hard (P5,P9,P10): {count_found(hard)}/{len(hard)}")
    lines.append("")

    # 패턴별 상세
    lines.append("---")
    lines.append("")
    lines.append("## 패턴별 상세")
    lines.append("")
    lines.append("| 패턴 | 유형 | 설명 | 발견 | 매칭 규칙 | 비고 |")
    lines.append("|------|------|------|------|----------|------|")
    for pid in ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"]:
        p = pr[pid]
        pattern = p["pattern"]
        found_mark = "✅" if p["found"] else "❌"
        matched_ids = ", ".join(m["rule_id"] for m in p["matched_rules"]) or "-"
        note = ""
        if p["matched_rules"]:
            note = p["matched_rules"][0]["reason"]
        elif not p["found"]:
            note = "미감지"
        lines.append(f"| {pid} | {pattern['type']} | {pattern['desc']} | "
                      f"{found_mark} | {matched_ids} | {note} |")
    lines.append("")

    # 매칭 상세
    lines.append("---")
    lines.append("")
    lines.append("## 매칭 상세")
    lines.append("")
    for pid in ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"]:
        p = pr[pid]
        pattern = p["pattern"]
        status = "✅ 발견" if p["found"] else "❌ 미발견"
        lines.append(f"### {pid}: {pattern['desc']} ({status})")
        lines.append(f"- 유형: `{pattern['type']}`")
        if "customer" in pattern:
            lines.append(f"- 고객: {pattern['customer']}")
        if "item" in pattern:
            lines.append(f"- 품목: {pattern['item']}")
        if "from" in pattern:
            lines.append(f"- 관계: {pattern['from']} → {pattern.get('to', '?')}")
        if "items" in pattern:
            lines.append(f"- 품목: {', '.join(pattern['items'])}")
        lines.append("")

        if p["matched_rules"]:
            for m in p["matched_rules"]:
                lines.append(f"**매칭 규칙 {m['rule_id']}** (confidence={m['confidence']})")
                lines.append(f"> {m['content']}")
                lines.append(f"- 매칭 사유: {m['reason']}")
                lines.append("")
        else:
            lines.append("매칭된 규칙 없음.")
            lines.append("")

    # 거짓 양성
    if fp:
        lines.append("---")
        lines.append("")
        lines.append("## 거짓 양성 (False Positives)")
        lines.append("")
        lines.append("심어둔 P1~P10 어디에도 매칭되지 않은 규칙들.")
        lines.append("")
        for f in fp:
            lines.append(f"- **{f['rule_id']}** (type={f['type']}, confidence={f['confidence']})")
            lines.append(f"  > {f['content']}")
        lines.append("")

    # Exp 1 비교
    lines.append("---")
    lines.append("")
    lines.append("## Exp 1 대비 비교")
    lines.append("")
    lines.append("| 조건 | Easy (3) | Medium (4) | Hard (3) | 계 |")
    lines.append("|------|----------|------------|----------|----|")
    lines.append(f"| Exp 5 (v2 통계만) | {count_found(easy)}/3 | "
                  f"{count_found(medium)}/4 | {count_found(hard)}/3 | "
                  f"{found_count}/10 |")
    lines.append("| Exp 1 (v1 통계+raw) | 3/3 | 2/4 | 1/3 | 6/10 |")
    lines.append("| Exp 1 (v1+raw+LLM) | 3/3 | 4/4 | 3/3 | 10/10 |")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Phase 3: LLM 규칙 검증")
    parser.add_argument("--results-dir", default="synthetic/results",
                        help="llm_rules.json이 있는 디렉토리 (기본: synthetic/results)")
    parser.add_argument("--data-dir", default="synthetic/data",
                        help="CSV 데이터 디렉토리 (기본: synthetic/data)")
    args = parser.parse_args()

    rules_data = load_rules(args.results_dir)
    print(f"✓ 규칙 로드: {len(rules_data.get('rules', []))}개")

    verification = verify(rules_data)

    report = generate_report(verification)
    output_path = os.path.join(args.results_dir, "verification_report.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    # 콘솔 요약
    pr = verification["pattern_results"]
    found = sum(1 for v in pr.values() if v["found"])
    print(f"✓ 검증 완료: {found}/10 패턴 발견, "
          f"거짓양성 {len(verification['false_positives'])}개")
    print(f"✓ 보고서 저장: {output_path}")

    # 미발견 패턴 표시
    missed = [pid for pid, v in pr.items() if not v["found"]]
    if missed:
        print(f"  ⚠ 미발견: {', '.join(missed)}")


if __name__ == "__main__":
    main()
