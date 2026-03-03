"""
app.py  —  Step 2: UCI Hydraulic 에이전트 진단
실행: streamlit run step2_hydraulic_agent/app.py
"""

import os
import random
import pickle
import pandas as pd
import streamlit as st
from agent import DiagnosticAgent

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")

COMPONENT_LABELS = {
    "cooler":      "냉각기",
    "valve":       "밸브",
    "pump":        "펌프 누수",
    "accumulator": "어큐뮬레이터",
}

TOOL_DESCRIPTIONS = {
    "classify_cooler":       "냉각기 상태 분류 (ML)",
    "classify_valve":        "밸브 상태 분류 (ML)",
    "classify_pump":         "펌프 누수 분류 (ML)",
    "classify_accumulator":  "어큐뮬레이터 분류 (ML)",
    "get_pressure_stats":    "압력 센서(PS1~PS6) 통계 조회",
    "get_flow_stats":        "유량 센서(FS1~FS2) 통계 조회",
    "get_temperature_stats": "온도 센서(TS1~TS4) 통계 조회",
    "get_efficiency_stats":  "냉각 효율(CE/CP/SE) 통계 조회",
    "get_power_stats":       "전력 센서(EPS1) 통계 조회",
    "get_similar_cycles":    "유사 과거 사이클 조회",
}

GROUP_A = {"classify_cooler", "classify_valve", "classify_pump", "classify_accumulator"}


# ── 아티팩트 로드 ─────────────────────────────────────────────────────────────

@st.cache_resource
def load_agent():
    return DiagnosticAgent()


@st.cache_data
def load_labels():
    with open(os.path.join(MODELS_DIR, "labels.pkl"), "rb") as f:
        return pickle.load(f)


@st.cache_data
def load_features():
    with open(os.path.join(MODELS_DIR, "features.pkl"), "rb") as f:
        return pickle.load(f)


def artifacts_exist() -> bool:
    needed = ["features.pkl", "labels.pkl", "baseline.pkl",
              "cycle_stats.pkl", "model_cooler.pkl", "model_valve.pkl",
              "model_pump.pkl", "model_accumulator.pkl"]
    return all(os.path.exists(os.path.join(MODELS_DIR, f)) for f in needed)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def get_ground_truth(labels: pd.DataFrame, cycle_idx: int) -> dict:
    row = labels.iloc[cycle_idx]
    cooler_map = {100: "정상", 20: "성능저하", 3: "고장임박"}
    valve_map  = {100: "최적", 90: "경미한지연", 80: "심각한지연", 73: "고장임박"}
    pump_map   = {0: "누수없음", 1: "약한누수", 2: "심각한누수"}
    accum_map  = {130: "최적", 115: "약간저하", 100: "심각저하", 90: "고장임박"}
    return {
        "cooler":      cooler_map.get(int(row["cooler"]), str(row["cooler"])),
        "valve":       valve_map.get(int(row["valve"]), str(row["valve"])),
        "pump":        pump_map.get(int(row["pump"]), str(row["pump"])),
        "accumulator": accum_map.get(int(row["accumulator"]), str(row["accumulator"])),
    }


def get_sensor_summary(features: pd.DataFrame, cycle_idx: int) -> dict:
    row = features.iloc[cycle_idx]
    return {
        "압력 평균 (PS1~PS6)": f"{row[[c for c in features.columns if c.startswith('PS') and c.endswith('_mean')]].mean():.1f} bar",
        "유량 평균 (FS1~FS2)": f"{row[[c for c in features.columns if c.startswith('FS') and c.endswith('_mean')]].mean():.1f} L/min",
        "온도 평균 (TS1~TS4)": f"{row[[c for c in features.columns if c.startswith('TS') and c.endswith('_mean')]].mean():.1f} °C",
        "진동 평균 (VS1)":     f"{row['VS1_mean']:.2f} mm/s" if 'VS1_mean' in row else "N/A",
        "전력 평균 (EPS1)":    f"{row['EPS1_mean']:.0f} W" if 'EPS1_mean' in row else "N/A",
        "냉각 효율 (CE)":      f"{row['CE_mean']:.1f} %" if 'CE_mean' in row else "N/A",
    }


# ── UI ────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="유압 설비 에이전트 진단", layout="wide")
st.title("유압 설비 AI 에이전트 진단")
st.caption("ML 분류기 4개를 도구로 사용하고, LLM이 가설을 세워 추가 분석을 요청하며 결론을 도출합니다.")

# 준비 상태 확인
if not artifacts_exist():
    st.error("학습된 모델 파일이 없습니다.")
    st.markdown("""
**준비 순서:**
1. `data/` 폴더에 UCI Hydraulic 데이터 파일 배치 (data/README.md 참고)
2. `python preprocess.py` 실행
3. `python train_models.py` 실행
4. 다시 앱 실행
""")
    st.stop()

# 아티팩트 로드
agent = load_agent()
labels = load_labels()
features = load_features()
n_cycles = len(labels)

# ── 사이드바 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("사이클 선택")

    cycle_input = st.number_input(
        "사이클 번호 (0부터 시작)",
        min_value=0, max_value=n_cycles - 1,
        value=st.session_state.get("cycle_idx", 0),
        step=1,
        key="cycle_input",
    )

    if st.button("랜덤 선택", use_container_width=True):
        st.session_state["cycle_idx"] = random.randint(0, n_cycles - 1)
        st.session_state["result"] = None
        st.rerun()

    cycle_idx = int(cycle_input)
    st.session_state["cycle_idx"] = cycle_idx

    st.divider()
    show_truth = st.toggle("정답 보기", value=False)

    st.divider()
    st.caption(f"전체 사이클: {n_cycles:,}개")


# ── 메인 ──────────────────────────────────────────────────────────────────────

st.subheader(f"사이클 #{cycle_idx} 분석")

# 센서 요약
sensor_summary = get_sensor_summary(features, cycle_idx)
cols = st.columns(len(sensor_summary))
for col, (label, value) in zip(cols, sensor_summary.items()):
    col.metric(label, value)

st.divider()

# 실행 버튼
if st.button("에이전트 분석 시작", type="primary", use_container_width=True):
    st.session_state["result"] = None

    log_placeholder = st.empty()
    answer_placeholder = st.empty()

    tool_log_display = []

    with st.spinner("에이전트 실행 중..."):
        # 에이전트 실행 (동기)
        final_text, tool_log = agent.run(cycle_idx)

    # 결과 저장
    st.session_state["result"] = {
        "final_text": final_text,
        "tool_log": tool_log,
        "cycle_idx": cycle_idx,
    }
    st.rerun()

# ── 결과 표시 ─────────────────────────────────────────────────────────────────
result = st.session_state.get("result")

if result and result.get("cycle_idx") == cycle_idx:
    tool_log = result["tool_log"]
    final_text = result["final_text"]

    # 에이전트 실행 로그
    st.markdown("#### 에이전트 실행 로그")

    current_round = 0
    for entry in tool_log:
        rnd = entry["round"]
        entry_type = entry.get("type", "tool")

        if rnd != current_round:
            current_round = rnd
            label = "기초 진단" if rnd == 1 else f"가설 검증 (Round {rnd})"
            st.markdown(f"**▸ Round {rnd} — {label}**")

        # LLM 중간 텍스트 (tool_calls 전에 출력한 텍스트)
        if entry_type == "thought":
            with st.container(border=True):
                st.markdown("🧠 **LLM 중간 사고**")
                st.markdown(entry["text"])
            continue

        # 툴 호출 엔트리
        name = entry["name"]
        reasoning = entry.get("reasoning", "")
        summary = entry["result_summary"]
        is_group_a = name in GROUP_A

        tool_desc = TOOL_DESCRIPTIONS.get(name, name)
        icon = "🔧" if is_group_a else "🔍"

        with st.container(border=True):
            # 툴 이름 + 결과 요약
            col1, col2 = st.columns([3, 2])
            with col1:
                badge = "" if is_group_a else " `가설검증`"
                st.markdown(f"{icon} **{tool_desc}**{badge}")
            with col2:
                st.markdown(f"→ `{summary}`")

            # LLM이 이 툴을 부른 이유 (reasoning)
            if reasoning:
                st.markdown(
                    f"<div style='background:#f0f2f6;border-left:3px solid #888;"
                    f"padding:6px 10px;margin-top:4px;border-radius:4px;"
                    f"font-size:0.88em;color:#444;'>"
                    f"💬 <b>호출 이유:</b> {reasoning}</div>",
                    unsafe_allow_html=True,
                )

            # 상세 결과 토글
            with st.expander("상세 결과 보기", expanded=False):
                st.json(entry["result_full"])

    st.divider()

    # LLM 최종 판단
    st.markdown("#### LLM 최종 판단")
    st.markdown(final_text)

    # 정답 비교
    if show_truth:
        st.divider()
        st.markdown("#### 정답 비교")
        ground_truth = get_ground_truth(labels, cycle_idx)

        # ML 예측값 툴 로그에서 추출
        predictions = {}
        for entry in tool_log:
            name = entry["name"]
            if name.startswith("classify_"):
                comp = name.replace("classify_", "")
                predictions[comp] = entry["result_full"].get("predicted_state", "?")

        comp_cols = st.columns(4)
        for i, comp in enumerate(["cooler", "valve", "pump", "accumulator"]):
            with comp_cols[i]:
                truth = ground_truth[comp]
                pred = predictions.get(comp, "미실행")
                match = pred == truth
                icon = "✅" if match else "❌"
                st.markdown(f"**{COMPONENT_LABELS[comp]}**")
                st.markdown(f"예측: `{pred}`")
                st.markdown(f"실제: `{truth}` {icon}")

        # 4개 부품 정확도
        n_correct = sum(
            1 for comp in ["cooler", "valve", "pump", "accumulator"]
            if predictions.get(comp) == ground_truth[comp]
        )
        st.metric("부품 정확도 (이 사이클)", f"{n_correct}/4")

else:
    st.info("사이드바에서 사이클을 선택하고 '에이전트 분석 시작'을 눌러주세요.")
