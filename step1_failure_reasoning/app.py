import os
import math
import random
import pandas as pd
import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

load_dotenv()

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ai4i2020.csv")

FAILURE_LABELS = {
    "TWF": "공구 마모 실패",
    "HDF": "열 방출 실패",
    "PWF": "전력 실패",
    "OSF": "과부하 실패",
}
FEATURE_COLS = ["온도차", "전력", "마모_토크", "Rotational speed [rpm]", "Torque [Nm]", "Tool wear [min]"]
ACTUAL_RULES = """
**HDF**: (공정온도 - 공기온도) < 8.6 K **AND** 회전속도 < 1380 RPM
**PWF**: 전력(토크 × RPM × 2π/60) < 3500 W 또는 > 9000 W
**OSF**: 공구마모 × 토크 > 임계값 (L=11,000 / M=12,000 / H=13,000 Nm·분)
**TWF**: 공구마모 200~240분 구간에서 확률적 발생
"""

SYSTEM_PROMPT = """당신은 공장 설비 진단 전문가이자 데이터 과학자입니다.
분석 대상은 회전형 기계 설비입니다.

원시 센서:
- 공기온도(K): 설비 주변 환경 온도
- 공정온도(K): 가공 중 발생 온도 (항상 공기온도보다 높음)
- 회전속도(RPM): 주축 분당 회전수
- 토크(Nm): 주축에 가해지는 회전력
- 공구마모(분): 공구 누적 사용 시간
- 제품유형: L(경량) / M(중간) / H(중량)

파생 변수 (물리 법칙 기반):
- 온도차(K) = 공정온도 - 공기온도 → 열 방출 효율 지표
- 전력(W) = 토크 × RPM × 2π/60 → 실제 소비 전력
- 마모_토크(Nm·분) = 공구마모 × 토크 → 기계적 누적 부하

고장 유형: HDF / PWF / OSF / TWF"""


# ── 데이터 준비 ─────────────────────────────────────────────────────────────

@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df_fail = df[df["Machine failure"] == 1].copy()
    # RNF 단독 제외
    non_rnf = df_fail[["TWF", "HDF", "PWF", "OSF"]].sum(axis=1) > 0
    df_fail = df_fail[non_rnf].reset_index(drop=True)

    # 파생 변수
    df_fail["온도차"] = df_fail["Process temperature [K]"] - df_fail["Air temperature [K]"]
    df_fail["전력"] = df_fail["Torque [Nm]"] * df_fail["Rotational speed [rpm]"] * (2 * math.pi / 60)
    df_fail["마모_토크"] = df_fail["Tool wear [min]"] * df_fail["Torque [Nm]"]

    # 단일 고장 유형 라벨 (복합 고장은 별도 표기)
    def primary_label(row):
        types = [c for c in ["TWF", "HDF", "PWF", "OSF"] if row[c] == 1]
        return types[0] if len(types) == 1 else "복합"
    df_fail["고장유형"] = df_fail.apply(primary_label, axis=1)

    return df_fail


def build_metadata(df: pd.DataFrame) -> str:
    """원시 데이터 대신 LLM에게 전달할 통계 요약"""
    lines = []

    # 개요
    dist = df["고장유형"].value_counts()
    lines.append(f"## 데이터셋 개요\n- 총 고장 샘플: {len(df)}개\n")
    lines.append("## 고장 유형 분포")
    for k, v in dist.items():
        lines.append(f"- {k}: {v}개 ({v/len(df)*100:.1f}%)")

    # 유형별 통계
    stat_cols = ["온도차", "전력", "마모_토크", "Rotational speed [rpm]", "Torque [Nm]", "Tool wear [min]"]
    lines.append("\n## 고장 유형별 변수 통계 (평균 / 최솟값 / 최댓값)")
    for col in stat_cols:
        lines.append(f"\n**{col}**")
        for ft in dist.index:
            sub = df[df["고장유형"] == ft][col]
            lines.append(f"  {ft}: 평균={sub.mean():.1f}, 범위=[{sub.min():.1f}, {sub.max():.1f}]")

    return "\n".join(lines)


# ── LLM 호출 ────────────────────────────────────────────────────────────────

def call_llm(user_prompt: str) -> str:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    return response.choices[0].message.content


def prompt_plan(metadata: str) -> str:
    return f"""아래는 공장 설비 고장 데이터의 통계 요약입니다.
(원시 데이터 전체가 아닌, 변수별 분포 요약만 제공됩니다.)

{metadata}

이 요약을 바탕으로 분석하세요:
1. 각 고장 유형을 구분할 핵심 변수가 무엇인지, 통계 수치 근거를 들어 설명하세요.
2. 파생 변수(온도차, 전력, 마모_토크)가 원시 센서보다 고장 구분에 더 적합한 이유를 물리적으로 설명하세요.
3. 머신러닝 분류 시 예상되는 어려움(클래스 불균형, 복합 고장 등)을 지적하세요."""


def prompt_interpret_ml(report: str, importances: str, tree_rules: str) -> str:
    return f"""의사결정나무(Decision Tree)로 공장 설비 고장을 분류한 결과입니다.

## 분류 성능
{report}

## 피처 중요도
{importances}

## 의사결정나무가 찾은 규칙 (상위 부분)
{tree_rules[:2500]}

이 결과를 해석하세요:
1. 피처 중요도 순위를 물리적으로 설명하세요. 왜 이 변수가 중요한가?
2. 나무 규칙을 각 고장 유형별로 자연어로 풀어서 설명하세요.
3. 분류가 잘 안 되는 유형이 있다면 이유를 설명하세요."""


def prompt_explain_sample(row: pd.Series, prediction: str, decision_path: str, actual: str) -> str:
    return f"""공장 설비에서 고장이 발생했습니다. 머신러닝 모델이 이를 분류했고, 그 결과를 설명해야 합니다.

## 측정값
- 공기온도: {row['Air temperature [K]']:.1f} K
- 공정온도: {row['Process temperature [K]']:.1f} K
- 회전속도: {row['Rotational speed [rpm]']:.0f} RPM
- 토크: {row['Torque [Nm]']:.1f} Nm
- 공구마모: {row['Tool wear [min]']:.0f} 분
- 제품유형: {row['Type']}

## 파생 변수
- 온도차: {row['온도차']:.1f} K
- 전력: {row['전력']:.0f} W
- 마모_토크: {row['마모_토크']:.0f} Nm·분

## ML 분류 결과
- 예측: **{prediction}**
- 실제: **{actual}**

## ML 의사결정 경로
{decision_path}

설비 운영자에게 설명하듯이 작성하세요:
1. 왜 이 고장 유형으로 분류되었는지 (어떤 수치가 결정적이었는가)
2. 이 고장의 물리적 원인 (기계 내부에서 무슨 일이 일어나고 있는가)
3. 운영자가 지금 당장 취해야 할 조치"""


# ── ML ──────────────────────────────────────────────────────────────────────

def run_decision_tree(df: pd.DataFrame):
    df_single = df[df["고장유형"] != "복합"]
    X = df_single[FEATURE_COLS]
    y = df_single["고장유형"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    clf = DecisionTreeClassifier(max_depth=5, min_samples_leaf=3, random_state=42)
    clf.fit(X_train, y_train)

    report = classification_report(y_test, clf.predict(X_test))
    tree_rules = export_text(clf, feature_names=FEATURE_COLS)
    importances = pd.Series(clf.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)

    return clf, report, tree_rules, importances


def get_decision_path(clf, row: pd.Series) -> str:
    X = pd.DataFrame([row[FEATURE_COLS]])
    node_ids = clf.decision_path(X).indices
    tree = clf.tree_
    lines = []
    for nid in node_ids[:-1]:
        feat = FEATURE_COLS[tree.feature[nid]]
        threshold = tree.threshold[nid]
        val = X.iloc[0][feat]
        direction = "<=" if val <= threshold else ">"
        lines.append(f"  {feat} {direction} {threshold:.2f}  (측정값: {val:.2f})")
    return "\n".join(lines)


# ── UI ───────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="LLM 공장 고장 추론", layout="wide")
st.title("LLM 공장 고장 원인 추론")
st.caption("ML이 패턴을 찾고, LLM이 물리적 의미로 해석한다.")

if not os.path.exists(DATA_PATH):
    st.error("data/ai4i2020.csv 파일이 없습니다.")
    st.stop()

df = load_data(DATA_PATH)
st.caption(f"고장 샘플: {len(df)}개 (RNF 단독 제외)")

tab1, tab2, tab3 = st.tabs(["📊 1단계: 메타데이터 분석", "🌳 2단계: ML 학습 + 해석", "🔍 3단계: 샘플 설명"])


# ── Tab 1: 메타데이터 → LLM 계획 ─────────────────────────────────────────────

with tab1:
    st.subheader("데이터 메타데이터 → LLM 분석")
    st.write("원시 데이터 대신 **통계 요약**을 LLM에게 주고, 어떤 변수가 고장 구분에 유효한지 분석하게 합니다.")

    metadata = build_metadata(df)

    with st.expander("LLM에게 전달되는 메타데이터"):
        st.markdown(metadata)

    if st.button("LLM 분석 시작", type="primary"):
        with st.spinner("GPT-4o 분석 중..."):
            try:
                st.session_state["plan"] = call_llm(prompt_plan(metadata))
            except Exception as e:
                st.error(f"API 오류: {e}")

    if "plan" in st.session_state:
        st.markdown("#### LLM 분석 결과")
        st.markdown(st.session_state["plan"])


# ── Tab 2: ML 학습 + LLM 해석 ────────────────────────────────────────────────

with tab2:
    st.subheader("ML 학습 → LLM 해석")
    st.write("의사결정나무로 고장을 분류하고, ML이 발견한 규칙을 LLM이 물리적으로 해석합니다.")

    if st.button("ML 학습 + 해석", type="primary"):
        with st.spinner("의사결정나무 학습 중..."):
            clf, report, tree_rules, importances = run_decision_tree(df)
            st.session_state.update({
                "clf": clf,
                "ml_report": report,
                "tree_rules": tree_rules,
                "importances": importances,
            })

        with st.spinner("GPT-4o 해석 중..."):
            try:
                interp = call_llm(prompt_interpret_ml(report, importances.to_string(), tree_rules))
                st.session_state["ml_interp"] = interp
            except Exception as e:
                st.error(f"API 오류: {e}")

    if "ml_report" in st.session_state:
        col1, col2 = st.columns([1, 1])
        with col1:
            st.markdown("#### ML 분류 성능")
            st.code(st.session_state["ml_report"])
            st.markdown("#### 피처 중요도")
            st.bar_chart(st.session_state["importances"])
        with col2:
            st.markdown("#### LLM 해석")
            st.markdown(st.session_state.get("ml_interp", ""))

        with st.expander("의사결정나무 규칙 전체"):
            st.code(st.session_state["tree_rules"])
        with st.expander("실제 규칙 비교 (논문 공개)"):
            st.markdown(ACTUAL_RULES)


# ── Tab 3: 샘플 → ML 분류 → LLM 설명 ────────────────────────────────────────

with tab3:
    st.subheader("새 샘플 → ML 분류 → LLM 설명")
    st.write("ML이 고장 유형을 분류하고, LLM이 운영자가 이해할 수 있는 언어로 원인과 조치를 설명합니다.")

    if "clf" not in st.session_state:
        st.warning("먼저 '2단계: ML 학습 + 해석' 탭에서 ML 학습을 실행하세요.")
    else:
        with st.sidebar:
            st.header("샘플 선택")
            options = ["전체 (랜덤)"] + sorted(df["고장유형"].unique().tolist())
            filter_type = st.selectbox("고장 유형 필터", options)
            filtered = df if filter_type == "전체 (랜덤)" else df[df["고장유형"] == filter_type]
            st.caption(f"해당 조건 샘플 수: {len(filtered)}")

            if st.button("랜덤 샘플 선택", use_container_width=True):
                st.session_state["sample_row"] = filtered.sample(1).iloc[0]
                st.session_state["sample_result"] = None

        if "sample_row" not in st.session_state:
            st.info("사이드바에서 '랜덤 샘플 선택'을 눌러주세요.")
        else:
            row = st.session_state["sample_row"]
            clf = st.session_state["clf"]

            # 센서값 표시
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**원시 센서값**")
                raw = {
                    "공기온도(K)": f"{row['Air temperature [K]']:.1f}",
                    "공정온도(K)": f"{row['Process temperature [K]']:.1f}",
                    "회전속도(RPM)": f"{row['Rotational speed [rpm]']:.0f}",
                    "토크(Nm)": f"{row['Torque [Nm]']:.1f}",
                    "공구마모(분)": f"{row['Tool wear [min]']:.0f}",
                    "제품유형": row["Type"],
                }
                st.table(pd.DataFrame(raw, index=["값"]).T)
            with col2:
                st.markdown("**파생 변수**")
                derived = {
                    "온도차(K)": f"{row['온도차']:.1f}",
                    "전력(W)": f"{row['전력']:.0f}",
                    "마모_토크(Nm·분)": f"{row['마모_토크']:.0f}",
                }
                st.table(pd.DataFrame(derived, index=["값"]).T)
                st.markdown("**실제 고장 유형**")
                st.info(f"`{row['고장유형']}` — {FAILURE_LABELS.get(row['고장유형'], row['고장유형'])}")

            if st.button("ML 분류 + LLM 설명", type="primary"):
                X_new = pd.DataFrame([row[FEATURE_COLS]])
                prediction = clf.predict(X_new)[0]
                decision_path = get_decision_path(clf, row)
                actual = row["고장유형"]

                if prediction == actual:
                    st.success(f"ML 예측: **{prediction}** ✅")
                else:
                    st.error(f"ML 예측: **{prediction}** ❌ (실제: {actual})")

                with st.spinner("GPT-4o 설명 생성 중..."):
                    try:
                        explanation = call_llm(
                            prompt_explain_sample(row, prediction, decision_path, actual)
                        )
                        st.session_state["sample_result"] = explanation
                        st.session_state["decision_path"] = decision_path
                    except Exception as e:
                        st.error(f"API 오류: {e}")

            if st.session_state.get("sample_result"):
                st.markdown("---")
                st.markdown("#### LLM 설명")
                st.markdown(st.session_state["sample_result"])

                with st.expander("ML 의사결정 경로 상세"):
                    st.code(st.session_state.get("decision_path", ""))
