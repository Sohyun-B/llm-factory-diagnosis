"""
Rule Discovery Agent — 수사 기록 뷰어

investigation.json을 읽어서 LLM의 사고 과정과 ML 결과를
하나의 흐르는 문서처럼 보여준다.

Usage:
    streamlit run app.py
    streamlit run app.py -- --results-dir synthetic/results
"""

import json
import os
import re
import sys

import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STEP_ICONS = {1: "🔭", 2: "🔍", 3: "🧬", 4: "📋"}
STEP_SUBTITLES = {
    1: "데이터 전체에서 패턴을 파악하고, 초기 가설을 세운다",
    2: "검증 결과에서 안 맞는 것을 찾고, 왜 그런지 조사를 요청한다",
    3: "불일치의 원인을 해석하고, 더 깊은 가설을 세운다",
    4: "모든 증거를 종합하여 최종 Rule Card를 작성한다",
}

VERDICT_MAP = {
    "confirmed": ("✅ confirmed", "green"),
    "partially_confirmed": ("🔶 partially", "orange"),
    "rejected": ("❌ rejected", "red"),
    "insufficient_data": ("⚪ insufficient", "gray"),
    "error": ("⚠️ error", "gray"),
}


# ============================================================
# 데이터 로드
# ============================================================

def load_investigation(results_dir: str) -> dict | None:
    path = os.path.join(results_dir, "investigation.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 렌더 헬퍼
# ============================================================

def split_narrative_and_json(raw: str) -> tuple[str, str, str]:
    """LLM raw 응답 → (서술 전반, JSON 문자열, 서술 후반)"""
    match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        before = raw[:match.start()].strip()
        json_str = match.group(1)
        after = raw[match.end():].strip()
        return before, json_str, after
    return raw, "", ""


def render_llm_narrative(raw: str):
    """LLM의 서술(사고 과정)을 마크다운으로 렌더링. JSON 블록은 분리."""
    before, json_str, after = split_narrative_and_json(raw)

    if before:
        st.markdown(before)
    if after:
        st.markdown(after)


def render_llm_structured(parsed: dict, step_id: int):
    """LLM이 출력한 구조화된 JSON을 step에 맞게 렌더링"""

    if step_id == 1:
        # 큰 그림
        if parsed.get("big_picture"):
            st.info(parsed["big_picture"])

        patterns = parsed.get("patterns", [])
        if patterns:
            st.markdown("**발견한 패턴:**")
            for p in patterns:
                conf = p.get("confidence", "")
                st.markdown(f"- **{p['id']}** {p['description']}  `{conf}`")

        hypotheses = parsed.get("hypotheses", [])
        if hypotheses:
            st.markdown(f"**검증할 가설 ({len(hypotheses)}개):**")
            for h in hypotheses:
                pattern_ref = f" ← {h['pattern_id']}" if h.get("pattern_id") else ""
                st.markdown(f"- **{h['id']}**{pattern_ref}: {h['statement']}")
                if h.get("expected_if_true"):
                    st.caption(f"  예상: {h['expected_if_true']}")

    elif step_id == 2:
        # 불일치 추적
        if parsed.get("verification_summary"):
            st.info(parsed["verification_summary"])

        # 확인된 패턴
        confirmed = parsed.get("confirmed_patterns", [])
        if confirmed:
            st.markdown("**✅ 확인된 패턴:**")
            for c in confirmed:
                hid = c.get("hypothesis_id", "")
                st.markdown(f"- **{hid}**: {c.get('summary', '')}")

        # 예외 (핵심)
        exceptions = parsed.get("exceptions", [])
        if exceptions:
            st.markdown(f"**⚡ 예외 ({len(exceptions)}개):**")
            for ex in exceptions:
                st.markdown(f"- **{ex['id']}** ({ex.get('source', '')}): {ex['description']}")
                if ex.get("why_interesting"):
                    st.caption(f"  → {ex['why_interesting']}")

        # 기각 단서
        rejected_clues = parsed.get("rejected_clues", [])
        if rejected_clues:
            st.markdown(f"**❌ 기각된 가설의 단서 ({len(rejected_clues)}개):**")
            for rc in rejected_clues:
                st.markdown(f"- **{rc.get('hypothesis_id', '')}**: {rc.get('description', '')}")

        inv_requests = parsed.get("investigation_requests", [])
        if inv_requests:
            st.markdown(f"**조사 요청 ({len(inv_requests)}개):**")
            for r in inv_requests:
                ref = f" (← {r.get('exception_id', r.get('mismatch_id', ''))})" if r.get("exception_id") or r.get("mismatch_id") else ""
                st.markdown(f"- **{r['id']}**{ref}: {r['question']}")

    elif step_id == 3:
        # 깊은 가설
        if parsed.get("mismatch_interpretation"):
            st.info(parsed["mismatch_interpretation"])

        insights = parsed.get("insights", [])
        if insights:
            st.markdown("**새로운 인사이트:**")
            for ins in insights:
                st.markdown(f"- {ins}")

        deep_hyps = parsed.get("deep_hypotheses", [])
        if deep_hyps:
            st.markdown(f"**깊은 가설 ({len(deep_hyps)}개):**")
            for dh in deep_hyps:
                origin = f" (← {dh['origin']})" if dh.get("origin") else ""
                st.markdown(f"- **{dh['id']}**{origin}: {dh['statement']}")
                if dh.get("expected_if_true"):
                    st.caption(f"  예상: {dh['expected_if_true']}")

    elif step_id == 4:
        # 종합 — Rule Cards는 별도 렌더링이므로 summary만
        if parsed.get("investigation_summary"):
            st.info(parsed["investigation_summary"])

        open_q = parsed.get("open_questions", [])
        if open_q:
            st.markdown("**미해결 질문:**")
            for q in open_q:
                st.markdown(f"- ❓ {q}")


def render_ml_results(ml_results: dict, ml_action: str):
    """ML 실행 결과를 렌더링"""
    if not ml_results:
        return

    if ml_action == "hypothesis_test":
        for hyp_id, result in ml_results.items():
            verdict = result.get("verdict", "?")
            statement = result.get("statement", hyp_id)
            label, color = VERDICT_MAP.get(verdict, ("❓ unknown", "gray"))

            with st.expander(f":{color}[{label}]  **{hyp_id}**: {statement}",
                             expanded=(verdict == "confirmed")):
                # 핵심 수치
                cols = st.columns(4)
                if "accuracy" in result:
                    cols[0].metric("정확도", f"{result['accuracy']:.0%}")
                elif "hit_rate" in result:
                    cols[0].metric("적중률", f"{result['hit_rate']:.0%}")

                if "expected_period" in result:
                    cols[1].metric("기대 주기", f"{result['expected_period']}일")
                elif "expected_random" in result:
                    cols[1].metric("기대 확률", f"{result['expected_random']:.0%}")

                if "mean_interval" in result:
                    cols[2].metric("실제 평균", f"{result['mean_interval']:.1f}일")
                elif "lift" in result:
                    cols[2].metric("Lift", f"{result['lift']:.2f}")

                cols[3].metric("판정", verdict)

                if result.get("success_criteria"):
                    st.caption(f"기준: {result['success_criteria']}")

                with st.expander("원본 데이터", expanded=False):
                    st.json(result)

    elif ml_action == "investigation":
        for inv_id, inv_data in ml_results.items():
            question = inv_data.get("question", inv_id)
            result = inv_data.get("result", {})
            summary = result.get("summary", result.get("error", ""))

            with st.expander(f"**{inv_id}**: {question}", expanded=True):
                if summary:
                    st.markdown(f"> {summary}")
                st.json(result)


def render_rule_cards(parsed: dict):
    """최종 Rule Card를 카드 형태로 렌더링"""
    cards = parsed.get("rule_cards", [])
    if not cards:
        st.warning("Rule Card가 없습니다.")
        return

    for card in cards:
        conf = card.get("confidence", {})
        score = conf.get("score", 0)

        st.markdown(f"### {card['id']}: {card['content']}")

        col1, col2, col3 = st.columns(3)
        col1.metric("신뢰도", f"{score:.0%}")
        col2.metric("판단", conf.get("natural_language", ""))
        col3.metric("유형", card.get("type", ""))

        st.markdown(f"**근거**: {conf.get('basis', '')}")

        # Evidence
        evidence = card.get("evidence", {})
        if evidence:
            e1, e2, e3 = st.columns(3)
            e1.markdown(f"**큰 그림**\n\n{evidence.get('big_picture', '-')}")
            e2.markdown(f"**검증**\n\n{evidence.get('verification', '-')}")
            e3.markdown(f"**깊은 분석**\n\n{evidence.get('deep_dive', '-')}")

        # 기각된 가설
        rejected = card.get("rejected_hypotheses", [])
        if rejected:
            with st.expander(f"기각된 가설 ({len(rejected)}건)"):
                for r in rejected:
                    st.markdown(f"- ❌ {r}")

        # 예외, 검증 계획
        exceptions = card.get("exceptions", [])
        vplan = card.get("verification_plan", {})
        if exceptions or vplan:
            with st.expander("예외 & 향후 검증"):
                if exceptions:
                    st.markdown("**예외**: " + ", ".join(exceptions))
                if vplan:
                    st.markdown(
                        f"**검증**: {vplan.get('method', '')} ({vplan.get('frequency', '')})")

        st.divider()


# ============================================================
# 메인
# ============================================================

def main():
    st.set_page_config(
        page_title="Rule Discovery — 수사 기록",
        page_icon="🔬",
        layout="wide",
    )

    # CLI args
    results_dir = os.path.join(BASE_DIR, "synthetic", "results")
    for i, arg in enumerate(sys.argv):
        if arg == "--results-dir" and i + 1 < len(sys.argv):
            results_dir = os.path.abspath(sys.argv[i + 1])
            break

    investigation = load_investigation(results_dir)
    if investigation is None:
        st.error(f"investigation.json을 찾을 수 없습니다: {results_dir}")
        st.stop()

    steps = investigation.get("steps", [])
    meta = investigation.get("metadata", {})

    # ── 헤더 ──
    st.title("🔬 수사 기록")
    st.caption(f"{meta.get('model', '?')} · {meta.get('timestamp', '?')}")

    # ── 요약 바 ──
    final_step = steps[-1] if steps else {}
    final_parsed = final_step.get("llm_parsed", {})
    n_rules = len(final_parsed.get("rule_cards", []))

    cols = st.columns(len(steps) + 1)
    for i, step in enumerate(steps):
        icon = STEP_ICONS.get(step["id"], "")
        name = step["name"]
        parsed = step.get("llm_parsed", {})
        ml = step.get("ml_results", {})

        if step["id"] == 1:
            detail = f'{len(parsed.get("patterns", []))}개 패턴'
        elif step["id"] == 2:
            detail = f'{len(parsed.get("exceptions", []))}개 예외'
        elif step["id"] == 3:
            detail = f'{len(parsed.get("deep_hypotheses", []))}개 가설'
        elif step["id"] == 4:
            detail = f'{n_rules}개 Rule Card'
        else:
            detail = ""

        cols[i].metric(f"{icon} {name}", detail)

    cols[-1].metric("📊 최종", f"{n_rules}개 규칙")

    st.markdown("---")

    # ── Step별 렌더링 ──
    for step in steps:
        step_id = step["id"]
        name = step["name"]
        icon = STEP_ICONS.get(step_id, "")
        subtitle = STEP_SUBTITLES.get(step_id, "")

        st.header(f"{icon} Step {step_id}: {name}")
        st.caption(subtitle)

        # LLM 사고 과정
        raw = step.get("llm_raw", "")
        parsed = step.get("llm_parsed", {})

        st.subheader("LLM의 분석")
        render_llm_narrative(raw)

        # LLM 구조화 출력
        render_llm_structured(parsed, step_id)

        # 프롬프트 보기
        with st.expander("📤 이 단계에서 LLM에게 전달한 프롬프트", expanded=False):
            # investigation.json에는 프롬프트가 저장 안 됨 → transcript에서 봐야 함
            st.caption("전체 프롬프트는 conversation_transcript.md를 참조하세요")
            _, json_str, _ = split_narrative_and_json(raw)
            if json_str:
                with st.expander("LLM 출력 JSON (raw)", expanded=False):
                    st.code(json_str, language="json")

        # ML 실행 결과
        ml_results = step.get("ml_results")
        ml_action = step.get("ml_action")
        if ml_results:
            st.subheader("ML 실행 결과")
            render_ml_results(ml_results, ml_action)

        # Step 4: Rule Cards 추가 렌더링
        if step_id == 4:
            st.subheader("최종 Rule Cards")
            render_rule_cards(parsed)

        st.markdown("---")

    # ── 전체 대화 기록 ──
    transcript_path = os.path.join(results_dir, "conversation_transcript.md")
    if os.path.exists(transcript_path):
        with st.expander("📜 전체 대화 기록 (Raw Transcript)", expanded=False):
            with open(transcript_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 너무 길면 축약
            if len(content) > 50000:
                st.text(content[:50000] + "\n\n... (축약됨)")
            else:
                st.text(content)


if __name__ == "__main__":
    main()
