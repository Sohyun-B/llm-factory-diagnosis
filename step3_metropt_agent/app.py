"""
app.py — Step 3: MetroPT APU 에이전트 진단
실행: streamlit run step3_metropt_agent/app.py
"""

import os
import json
import random
import pickle
import pandas as pd
import streamlit as st
from agent import DiagnosticAgent

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")

# 실패 이벤트 (사이드바 정답 표시용)
FAILURE_EVENTS = [
    {"id": "F1", "type": "Air_Leak", "component": "Clients",
     "start": "2020-04-18 00:00:00", "end": "2020-04-18 23:59:59"},
    {"id": "F2", "type": "Air_Leak", "component": "Air_Dryer",
     "start": "2020-05-29 00:00:00", "end": "2020-05-29 23:59:59"},
]

TOOL_DESCRIPTIONS = {
    "detect_anomaly":          "이상 감지 (ML)",
    "classify_failure_type":   "실패 유형 분류 (ML)",
    "get_sensor_trend":        "센서 트렌드 조회",
    "search_maintenance_log":  "정비 이력 RAG 검색",
    "search_domain_knowledge": "도메인 지식 RAG 검색",
    "search_similar_failures": "유사 사례 RAG 검색",
    "get_recent_events":       "최근 이벤트 조회",
}

GROUP_A = {"detect_anomaly", "classify_failure_type"}
GROUP_RAG = {"search_maintenance_log", "search_domain_knowledge", "search_similar_failures", "get_recent_events"}


def artifacts_exist() -> bool:
    needed = ["features.pkl", "labels.pkl", "baseline.pkl",
              "anomaly_detector.pkl", "failure_events.json",
              "vectorstore/index.faiss", "vectorstore/documents.pkl"]
    return all(os.path.exists(os.path.join(MODELS_DIR, f)) for f in needed)


@st.cache_resource
def load_agent():
    return DiagnosticAgent()


@st.cache_data
def load_features():
    with open(os.path.join(MODELS_DIR, "features.pkl"), "rb") as f:
        return pickle.load(f)


@st.cache_data
def load_labels():
    with open(os.path.join(MODELS_DIR, "labels.pkl"), "rb") as f:
        return pickle.load(f)


def get_ground_truth(timestamp: str) -> dict | None:
    ts = pd.Timestamp(timestamp)
    for evt in FAILURE_EVENTS:
        if pd.Timestamp(evt["start"]) <= ts <= pd.Timestamp(evt["end"]):
            return evt
    return None


def get_sensor_summary(features: pd.DataFrame, timestamp: str) -> dict:
    ts = pd.Timestamp(timestamp)
    diffs = abs(features.index - ts)
    idx = diffs.argmin()
    row = features.iloc[idx]
    return {
        "TP3 (출력 압력)":   f"{row.get('TP3_mean', 0):.3f} bar",
        "Reservoirs (탱크)": f"{row.get('Reservoirs_mean', 0):.3f} bar",
        "오일 온도":         f"{row.get('Oil_temperature_mean', 0):.1f} °C",
        "모터 전류":         f"{row.get('Motor_current_mean', 0):.3f} A",
        "LPS 알람율":        f"{row.get('LPS_rate', 0)*100:.1f} %",
    }


# ── UI ────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="MetroPT APU 에이전트 진단", layout="wide")
st.title("MetroPT APU 에이전트 진단")
st.caption("ML 이상 감지 + 이벤트 로그 RAG 교차 추론으로 근본 원인을 분석합니다.")

if not artifacts_exist():
    st.error("학습된 모델 또는 벡터 DB가 없습니다.")
    st.markdown("""
**준비 순서:**
1. `python preprocess.py`
2. `python train_models.py`
3. `python build_rag.py`
4. 다시 앱 실행
""")
    st.stop()

agent = load_agent()
features = load_features()
labels = load_labels()

# ── 사이드바 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("시점 선택")

    ts_min = features.index.min().strftime("%Y-%m-%d %H:%M:%S")
    ts_max = features.index.max().strftime("%Y-%m-%d %H:%M:%S")
    st.caption(f"데이터 기간: {ts_min} ~ {ts_max}")

    timestamp_input = st.text_input(
        "분석할 타임스탬프",
        value=st.session_state.get("timestamp", "2020-04-18 12:00:00"),
        placeholder="YYYY-MM-DD HH:MM:SS",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("랜덤 (이상)", use_container_width=True):
            anomaly_ts = labels[labels != "normal"].index
            if len(anomaly_ts) > 0:
                st.session_state["timestamp"] = str(random.choice(anomaly_ts))
                st.session_state["result"] = None
                st.rerun()
    with col2:
        if st.button("랜덤 (정상)", use_container_width=True):
            normal_ts = labels[labels == "normal"].index
            st.session_state["timestamp"] = str(random.choice(normal_ts))
            st.session_state["result"] = None
            st.rerun()

    timestamp = timestamp_input
    st.session_state["timestamp"] = timestamp

    st.divider()
    show_truth = st.toggle("정답 보기", value=False)

    st.divider()
    st.markdown("**실패 이벤트 목록**")
    for evt in FAILURE_EVENTS:
        st.markdown(f"- `{evt['id']}` {evt['type']} ({evt['component']}) | {evt['start'][:10]}")

    st.divider()
    st.caption(f"전체 윈도우: {len(features):,}개")


# ── 메인 ──────────────────────────────────────────────────────────────────────

st.subheader(f"분석 시점: {timestamp}")

try:
    sensor_summary = get_sensor_summary(features, timestamp)
    cols = st.columns(len(sensor_summary))
    for col, (label, value) in zip(cols, sensor_summary.items()):
        col.metric(label, value)
except Exception:
    st.warning("해당 시점 센서 데이터를 찾을 수 없습니다.")

st.divider()

if st.button("에이전트 분석 시작", type="primary", use_container_width=True):
    st.session_state["result"] = None

    with st.spinner("에이전트 실행 중..."):
        final_text, tool_log = agent.run(timestamp)

    st.session_state["result"] = {
        "final_text": final_text,
        "tool_log": tool_log,
        "timestamp": timestamp,
    }
    st.rerun()

# ── 결과 ──────────────────────────────────────────────────────────────────────
result = st.session_state.get("result")

if result and result.get("timestamp") == timestamp:
    tool_log = result["tool_log"]
    final_text = result["final_text"]

    st.markdown("#### 에이전트 실행 로그")

    current_round = 0
    for entry in tool_log:
        rnd = entry["round"]
        if rnd != current_round:
            current_round = rnd
            if rnd == 1:
                label = "기초 진단"
            else:
                label = f"가설 검증 Round {rnd}"
            st.markdown(f"**▸ Round {rnd} — {label}**")

        if entry.get("type") == "thought":
            with st.container(border=True):
                st.markdown("🧠 **LLM 중간 사고**")
                st.markdown(entry["text"])
            continue

        name = entry["name"]
        reasoning = entry.get("reasoning", "")
        summary = entry["result_summary"]

        is_group_a   = name in GROUP_A
        is_group_rag = name in GROUP_RAG
        icon = "🔧" if is_group_a else "📚" if is_group_rag else "📊"
        badge = " `RAG`" if is_group_rag else ""

        tool_desc = TOOL_DESCRIPTIONS.get(name, name)

        with st.container(border=True):
            col1, col2 = st.columns([3, 2])
            with col1:
                st.markdown(f"{icon} **{tool_desc}**{badge}")
            with col2:
                st.markdown(f"→ `{summary}`")

            if reasoning:
                st.markdown(
                    f"<div style='background:#f0f2f6;border-left:3px solid #888;"
                    f"padding:6px 10px;margin-top:4px;border-radius:4px;"
                    f"font-size:0.88em;color:#444;'>"
                    f"💬 <b>호출 이유:</b> {reasoning}</div>",
                    unsafe_allow_html=True,
                )

            with st.expander("상세 결과", expanded=False):
                st.json(entry["result_full"])

    st.divider()
    st.markdown("#### LLM 최종 판단")
    st.markdown(final_text)

    if show_truth:
        st.divider()
        st.markdown("#### 정답")
        ground_truth = get_ground_truth(timestamp)
        if ground_truth:
            st.error(
                f"**실패 구간**: {ground_truth['id']} | "
                f"{ground_truth['type']} — {ground_truth['component']} | "
                f"{ground_truth['start']} ~ {ground_truth['end']}"
            )
        else:
            st.success("**정상 구간** — 실패 이벤트 없음")

else:
    st.info("사이드바에서 타임스탬프를 입력하고 '에이전트 분석 시작'을 눌러주세요.")
