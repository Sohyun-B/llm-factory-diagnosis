"""
agent.py
LLM 에이전트: 가설 검증 루프

흐름:
  1. Group A 툴(분류기 4개)로 현재 상태 파악
  2. LLM이 가설을 세운 뒤 필요하면 Group B 툴(통계 분석)을 추가 호출
  3. finish_reason == "stop"이 될 때까지 루프 반복
  4. 최종 답변 + 툴 호출 로그 반환
"""

import os
import json
import pickle
import numpy as np
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")


# ── 아티팩트 로드 ─────────────────────────────────────────────────────────────

def load_artifacts():
    def _load(name):
        with open(os.path.join(MODELS_DIR, name), "rb") as f:
            return pickle.load(f)

    return {
        "features":    _load("features.pkl"),
        "labels":      _load("labels.pkl"),
        "baseline":    _load("baseline.pkl"),
        "cycle_stats": _load("cycle_stats.pkl"),
        "cooler":      _load("model_cooler.pkl"),
        "valve":       _load("model_valve.pkl"),
        "pump":        _load("model_pump.pkl"),
        "accumulator": _load("model_accumulator.pkl"),
    }


# ── 툴 실행 함수 ──────────────────────────────────────────────────────────────

def _classify_component(artifacts, component: str, cycle_idx: int) -> dict:
    art = artifacts[component]
    model = art["model"]
    label_map = art["label_map"]
    feature_names = art["feature_names"]

    features = artifacts["features"]
    X = features.iloc[[cycle_idx]][feature_names].values
    proba = model.predict_proba(X)[0]
    classes = model.classes_
    proba_dict = {cls: round(float(p), 3) for cls, p in zip(classes, proba)}
    predicted = classes[np.argmax(proba)]

    return {
        "component": component,
        "predicted_state": predicted,
        "probabilities": proba_dict,
        "confidence": round(float(np.max(proba)), 3),
        "top_features": art["top_features"],
    }


def _get_group_stats(artifacts, group: str, cycle_idx: int) -> dict:
    cycle_stats = artifacts["cycle_stats"]
    baseline = artifacts["baseline"]

    if group not in cycle_stats:
        return {"error": f"알 수 없는 센서 그룹: {group}"}

    group_info = cycle_stats[group]
    sensors = group_info["sensors"]
    values_df = group_info["values"]
    row = values_df.iloc[cycle_idx]

    result = {"group": group, "sensors": {}}
    for sensor in sensors:
        mean_col = f"{sensor}_mean"
        std_col  = f"{sensor}_std"
        if mean_col not in row.index:
            continue

        val_mean = float(row[mean_col])
        val_std  = float(row.get(std_col, 0))
        base_mean = float(baseline["mean"].get(mean_col, val_mean))
        base_std  = float(baseline["std"].get(mean_col, 1))

        deviation_pct = round((val_mean - base_mean) / abs(base_mean) * 100, 1) if base_mean != 0 else 0
        z_score = round((val_mean - base_mean) / base_std, 2)

        result["sensors"][sensor] = {
            "mean": round(val_mean, 3),
            "std":  round(val_std, 3),
            "baseline_mean": round(base_mean, 3),
            "deviation_pct": deviation_pct,
            "z_score": z_score,
        }

    # 그룹 요약
    deviations = [v["deviation_pct"] for v in result["sensors"].values()]
    result["avg_deviation_pct"] = round(np.mean(deviations), 1) if deviations else 0
    result["interpretation"] = (
        "정상 범위" if abs(result["avg_deviation_pct"]) < 5 else
        "경미한 이상" if abs(result["avg_deviation_pct"]) < 15 else
        "심각한 이상"
    )
    return result


def _get_similar_cycles(artifacts, cycle_idx: int, n: int = 5) -> dict:
    from sklearn.neighbors import NearestNeighbors

    features = artifacts["features"].values
    labels = artifacts["labels"]
    query = features[cycle_idx].reshape(1, -1)

    nn = NearestNeighbors(n_neighbors=n + 1, metric="euclidean")
    nn.fit(features)
    distances, indices = nn.kneighbors(query)

    similar = []
    for dist, idx in zip(distances[0][1:], indices[0][1:]):  # 자기 자신 제외
        row = labels.iloc[idx]
        similar.append({
            "cycle_id": int(idx),
            "distance": round(float(dist), 2),
            "cooler": int(row["cooler"]),
            "valve": int(row["valve"]),
            "pump": int(row["pump"]),
            "accumulator": int(row["accumulator"]),
        })

    return {
        "query_cycle": cycle_idx,
        "similar_cycles": similar,
        "note": "거리가 작을수록 더 유사한 사이클입니다.",
    }


TOOL_DISPATCHER = {
    "classify_cooler":      lambda a, c, **_: _classify_component(a, "cooler",      c),
    "classify_valve":       lambda a, c, **_: _classify_component(a, "valve",       c),
    "classify_pump":        lambda a, c, **_: _classify_component(a, "pump",        c),
    "classify_accumulator": lambda a, c, **_: _classify_component(a, "accumulator", c),
    "get_pressure_stats":    lambda a, c, **_: _get_group_stats(a, "pressure",    c),
    "get_flow_stats":        lambda a, c, **_: _get_group_stats(a, "flow",        c),
    "get_temperature_stats": lambda a, c, **_: _get_group_stats(a, "temperature", c),
    "get_efficiency_stats":  lambda a, c, **_: _get_group_stats(a, "efficiency",  c),
    "get_power_stats":       lambda a, c, **_: _get_group_stats(a, "power",       c),
    "get_similar_cycles":    lambda a, c, n=5, **_: _get_similar_cycles(a, c, n),
}


# ── OpenAI 툴 스키마 정의 ─────────────────────────────────────────────────────

_REASONING_PARAM = {
    "reasoning": {
        "type": "string",
        "description": (
            "이 툴을 호출하는 이유를 한국어로 설명하십시오. "
            "현재까지의 추론 상태, 어떤 가설을 검증하려는지, "
            "이 툴 결과가 가설을 어떻게 뒷받침하거나 반박할 수 있는지를 포함하십시오."
        ),
    }
}


def _make_params(extra: dict = None) -> dict:
    props = {**_REASONING_PARAM, **(extra or {})}
    return {"type": "object", "properties": props, "required": ["reasoning"]}


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "classify_cooler",
            "description": "ML 모델로 냉각기(Cooler) 상태를 분류합니다. 상태와 각 클래스 확률을 반환합니다.",
            "parameters": _make_params(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "classify_valve",
            "description": "ML 모델로 밸브(Valve) 상태를 분류합니다. 지연 정도와 각 클래스 확률을 반환합니다.",
            "parameters": _make_params(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "classify_pump",
            "description": "ML 모델로 내부 펌프 누수(Pump leakage) 상태를 분류합니다.",
            "parameters": _make_params(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "classify_accumulator",
            "description": "ML 모델로 유압 어큐뮬레이터(Accumulator) 상태를 분류합니다.",
            "parameters": _make_params(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pressure_stats",
            "description": (
                "압력 센서(PS1~PS6) 통계를 조회합니다. "
                "정상 사이클 대비 편차(%)와 Z-score를 포함합니다. "
                "펌프 누수나 밸브 지연으로 인한 압력 이상을 확인할 때 유용합니다."
            ),
            "parameters": _make_params(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_flow_stats",
            "description": (
                "유량 센서(FS1~FS2) 통계를 조회합니다. "
                "정상 대비 유량 감소는 펌프 성능 저하 또는 누수를 시사합니다."
            ),
            "parameters": _make_params(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_temperature_stats",
            "description": (
                "온도 센서(TS1~TS4) 통계를 조회합니다. "
                "정상 대비 온도 상승은 냉각기 성능 저하를 시사합니다."
            ),
            "parameters": _make_params(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_efficiency_stats",
            "description": (
                "냉각 효율 센서(CE/CP/SE) 통계를 조회합니다. "
                "CE(냉각 효율), CP(냉각 전력), SE(시스템 효율)의 정상 대비 편차를 반환합니다."
            ),
            "parameters": _make_params(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_power_stats",
            "description": (
                "전력 센서(EPS1) 통계를 조회합니다. "
                "모터 전력 소비가 정상 범위를 벗어나면 기계적 부하 이상을 시사합니다."
            ),
            "parameters": _make_params(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_similar_cycles",
            "description": (
                "이 사이클과 가장 유사한 과거 사이클 5개와 그 실제 부품 상태를 조회합니다. "
                "현재 분석의 불확실성이 높을 때 유사 사례로 추론을 보강할 수 있습니다."
            ),
            "parameters": _make_params(),
        },
    },
]


# ── 시스템 프롬프트 ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """당신은 유압 설비 진단 AI 에이전트입니다.

## 시스템 구조
이 유압 시스템은 4개의 핵심 부품으로 구성됩니다:
- **냉각기(Cooler)**: 작동유 온도 제어. 성능 저하 시 CE(냉각효율) 감소 + TS(온도) 상승이 반드시 동반됨
- **밸브(Valve)**: 유압 방향 제어. 지연 발생 시 PS(압력) 변동 증가 + FS(유량) 패턴 이상이 동반됨
- **내부 펌프(Pump)**: 유압 압력 생성. 누수 시 FS(유량) 감소 + PS(압력) 전반 저하가 동반됨
- **어큐뮬레이터(Accumulator)**: 압력 완충. 저하 시 PS(압력) 변동(std) 증가가 동반됨

## 부품 간 인과 관계 (센서 연결)
- 펌프 누수 → FS 유량 감소 → PS 압력 저하 → 밸브 응답 지연
- 냉각기 저하 → CE 냉각효율 감소 + TS 온도 상승 → 점도 변화 → 밸브·펌프 수명 단축
- 어큐뮬레이터 저하 → PS std(압력 변동) 증가

## 분석 원칙: ML 결과는 가설이다

**ML 분류기는 틀릴 수 있습니다.** ML 결과를 그대로 결론으로 삼지 마십시오.
ML 결과는 "가설"이며, 반드시 실제 센서 데이터로 검증해야 결론을 낼 수 있습니다.

### 검증 의무 규칙
- 어느 부품이든 **신뢰도 < 70%**이면: 해당 부품의 관련 센서 통계를 반드시 호출하여 ML 예측이 맞는지 확인하십시오.
- **이상 상태(정상/최적/누수없음이 아님)로 분류된 부품**이 있으면: 해당 부품의 물리적 지표(센서)가 실제로 이상한지 확인하십시오.
- ML 예측과 센서 데이터가 **충돌**하면(예: ML은 "고장 임박"인데 관련 센서는 정상): 이를 명시적으로 보고하고 ML을 신뢰하지 마십시오.

### 부품별 검증 센서 매핑
| 부품 이상 의심 시 | 반드시 확인할 센서 |
|---|---|
| 냉각기 이상 | get_efficiency_stats (CE 확인) + get_temperature_stats (TS 확인) |
| 밸브 이상 | get_pressure_stats (PS std 확인) + get_flow_stats (FS 확인) |
| 펌프 이상 | get_flow_stats (FS 감소 확인) + get_pressure_stats (PS 전반 저하 확인) |
| 어큐뮬레이터 이상 | get_pressure_stats (PS std 증가 확인) |

## 분석 절차

**Step 1. 기초 진단**
classify_cooler, classify_valve, classify_pump, classify_accumulator를 모두 호출하십시오.

**Step 2. 가설 명시**
ML 결과를 받은 후, 최종 응답을 내리기 전에 반드시 다음을 생각하십시오:
"이 ML 예측이 맞다면 어떤 센서가 어떻게 이상해야 하는가?"

**Step 3. 센서로 검증**
Step 2에서 도출한 예측을 센서 데이터로 확인하십시오.
- 센서가 ML 예측을 뒷받침 → ML 신뢰, 결론 강화
- 센서가 ML 예측과 충돌 → ML을 의심, 불확실성 명시 또는 결론 수정

**Step 4. 결론 도출**
센서 검증 결과까지 종합하여 최종 판단을 내리십시오.
센서 없이 ML 결과만으로 결론을 내리는 것은 허용되지 않습니다.

## 최종 응답 형식

## 부품별 상태 요약
(ML 예측 상태 + 신뢰도 + 센서 검증 결과 한 줄)

## 센서 검증 결과
(어떤 센서를 왜 확인했고, 데이터가 ML 예측을 지지했는지 반박했는지)

## 근본 원인 분석
(ML + 센서 양쪽 증거를 종합한 인과 연쇄 설명)

## ML vs 센서 충돌 여부
(ML 예측과 센서 데이터가 일치했는지, 불일치했다면 어떤 부품에서 어떻게)

## 정비 권장 사항
- 즉시 조치: ...
- 단기 조치 (1주 내): ...
- 장기 모니터링: ...
"""


# ── DiagnosticAgent ───────────────────────────────────────────────────────────

class DiagnosticAgent:
    def __init__(self):
        self.artifacts = load_artifacts()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def run(self, cycle_idx: int):
        """
        멀티 라운드 tool calling 루프.
        Returns:
            final_text (str): LLM 최종 응답
            tool_log (list[dict]): 툴 호출 기록 [{name, reason, result}, ...]
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"사이클 #{cycle_idx}를 분석해주세요."},
        ]
        tool_log = []
        round_num = 0

        while True:
            round_num += 1
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0,
            )

            choice = response.choices[0]

            if choice.finish_reason == "stop":
                return choice.message.content, tool_log

            if choice.finish_reason == "tool_calls":
                # assistant가 tool_calls 전에 텍스트를 출력했으면 캡처
                assistant_text = (choice.message.content or "").strip()
                if assistant_text:
                    tool_log.append({
                        "type": "thought",
                        "round": round_num,
                        "text": assistant_text,
                    })

                messages.append(choice.message)

                for tool_call in choice.message.tool_calls:
                    name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments or "{}")
                    reasoning = args.pop("reasoning", "")

                    # 툴 실행
                    if name in TOOL_DISPATCHER:
                        result = TOOL_DISPATCHER[name](self.artifacts, cycle_idx, **args)
                    else:
                        result = {"error": f"알 수 없는 툴: {name}"}

                    result_str = json.dumps(result, ensure_ascii=False, indent=2)

                    # 로그 기록
                    tool_log.append({
                        "type": "tool",
                        "round": round_num,
                        "name": name,
                        "reasoning": reasoning,
                        "result_summary": _summarize_result(name, result),
                        "result_full": result,
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_str,
                    })

            else:
                break

        return "", tool_log


def _summarize_result(name: str, result: dict) -> str:
    """툴 결과를 UI용 한 줄 요약으로 변환"""
    if name.startswith("classify_"):
        component = result.get("component", name)
        state = result.get("predicted_state", "?")
        conf = result.get("confidence", 0)
        return f"{state} (신뢰도 {conf*100:.0f}%)"

    if name.startswith("get_") and "sensors" in result:
        avg_dev = result.get("avg_deviation_pct", 0)
        interp = result.get("interpretation", "")
        return f"정상 대비 {avg_dev:+.1f}% — {interp}"

    if name == "get_similar_cycles":
        n = len(result.get("similar_cycles", []))
        return f"유사 사이클 {n}개 조회 완료"

    return json.dumps(result, ensure_ascii=False)[:80]
