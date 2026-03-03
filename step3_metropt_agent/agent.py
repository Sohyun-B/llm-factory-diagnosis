"""
agent.py
MetroPT LLM 진단 에이전트: 센서 분석 + 이벤트 로그 RAG 교차 추론

Step 2 대비 추가:
  - search_maintenance_log: 정비 이력 RAG 검색
  - get_recent_events: 이상 발생 전 이벤트 조회
  - search_similar_failures: 유사 과거 사례 검색
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
VECTORSTORE_DIR = os.path.join(MODELS_DIR, "vectorstore")


# ── 아티팩트 로드 ──────────────────────────────────────────────────────────────

def load_artifacts():
    def _load(name):
        with open(os.path.join(MODELS_DIR, name), "rb") as f:
            return pickle.load(f)

    import faiss
    index = faiss.read_index(os.path.join(VECTORSTORE_DIR, "index.faiss"))
    with open(os.path.join(VECTORSTORE_DIR, "documents.pkl"), "rb") as f:
        documents = pickle.load(f)

    return {
        "features":           _load("features.pkl"),
        "labels":             _load("labels.pkl"),
        "baseline":           _load("baseline.pkl"),
        "anomaly_detector":   _load("anomaly_detector.pkl"),
        "failure_classifier": _load("failure_classifier.pkl") if os.path.exists(
            os.path.join(MODELS_DIR, "failure_classifier.pkl")) else None,
        "faiss_index":  index,
        "documents":    documents,
    }


# ── 툴 실행 함수 ──────────────────────────────────────────────────────────────

def _get_window_idx(features: pd.DataFrame, timestamp: str) -> int | None:
    """타임스탬프에 가장 가까운 10분 윈도우 인덱스 반환"""
    ts = pd.Timestamp(timestamp)
    diffs = abs(features.index - ts)
    idx = diffs.argmin()
    if diffs[idx] > pd.Timedelta(hours=1):
        return None
    return idx


def _detect_anomaly(artifacts: dict, timestamp: str) -> dict:
    features = artifacts["features"]
    baseline = artifacts["baseline"]
    art = artifacts["anomaly_detector"]
    model = art["model"]
    feature_names = art["feature_names"]

    idx = _get_window_idx(features, timestamp)
    if idx is None:
        return {"error": f"해당 타임스탬프 근처 데이터 없음: {timestamp}"}

    window_ts = features.index[idx]
    X = features.iloc[[idx]][feature_names].values
    proba = model.predict_proba(X)[0]
    predicted = model.classes_[np.argmax(proba)]
    anomaly_score = float(proba[list(model.classes_).index(1)] if 1 in model.classes_ else proba[1])

    # 센서별 정상 대비 편차
    row = features.iloc[idx]
    sensor_deviations = {}
    key_sensors = [c for c in feature_names if c.endswith("_mean")]
    for col in key_sensors:
        if col in baseline["mean"].index:
            val = float(row[col])
            base = float(baseline["mean"][col])
            dev = round((val - base) / abs(base) * 100, 1) if base != 0 else 0
            sensor_deviations[col] = {
                "value": round(val, 4),
                "baseline": round(base, 4),
                "deviation_pct": dev,
            }

    # 디지털 신호 상태
    digital_status = {}
    for col in [c for c in feature_names if c.endswith("_rate")]:
        digital_status[col] = round(float(row[col]), 3)

    return {
        "timestamp": str(window_ts),
        "anomaly_score": round(anomaly_score, 3),
        "is_anomaly": bool(predicted == 1),
        "sensor_deviations": sensor_deviations,
        "digital_status": digital_status,
        "top_features": art["top_features"],
    }


def _classify_failure(artifacts: dict, timestamp: str) -> dict:
    features = artifacts["features"]
    art = artifacts["failure_classifier"]
    if art is None:
        return {"error": "failure_classifier 모델 없음"}

    idx = _get_window_idx(features, timestamp)
    if idx is None:
        return {"error": f"해당 타임스탬프 근처 데이터 없음: {timestamp}"}

    X = features.iloc[[idx]][art["feature_names"]].values
    proba = art["model"].predict_proba(X)[0]
    classes = art["model"].classes_
    proba_dict = {cls: round(float(p), 3) for cls, p in zip(classes, proba)}
    predicted = classes[np.argmax(proba)]

    return {
        "timestamp": str(features.index[idx]),
        "predicted_failure_type": predicted,
        "probabilities": proba_dict,
        "confidence": round(float(np.max(proba)), 3),
    }


def _get_sensor_trend(artifacts: dict, timestamp: str, window_hours: int = 6) -> dict:
    features = artifacts["features"]
    baseline = artifacts["baseline"]

    ts = pd.Timestamp(timestamp)
    start = ts - pd.Timedelta(hours=window_hours)
    period = features[(features.index >= start) & (features.index <= ts)]

    if len(period) == 0:
        return {"error": "해당 구간 데이터 없음"}

    key_sensors = ["TP2_mean", "TP3_mean", "Reservoirs_mean", "Oil_temperature_mean",
                   "Motor_current_mean", "LPS_rate", "Oil_level_rate"]
    result = {"period": f"{start} ~ {ts}", "n_windows": len(period), "sensors": {}}

    for col in key_sensors:
        if col not in period.columns:
            continue
        vals = period[col]
        base = float(baseline["mean"].get(col, vals.mean()))
        result["sensors"][col] = {
            "mean": round(float(vals.mean()), 4),
            "std": round(float(vals.std()), 4),
            "min": round(float(vals.min()), 4),
            "max": round(float(vals.max()), 4),
            "trend": "상승" if vals.iloc[-1] > vals.iloc[0] else "하강" if vals.iloc[-1] < vals.iloc[0] else "유지",
            "deviation_pct": round((float(vals.mean()) - base) / abs(base) * 100, 1) if base != 0 else 0,
        }

    return result


def _search_rag(artifacts: dict, query: str, top_k: int = 3, doc_type_filter: str = None) -> dict:
    """자연어 쿼리로 벡터 DB 검색"""
    client = OpenAI()
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=[query],
    )
    query_vec = np.array([response.data[0].embedding], dtype=np.float32)

    index = artifacts["faiss_index"]
    documents = artifacts["documents"]

    distances, indices = index.search(query_vec, top_k * 3)  # 넉넉히 검색 후 필터

    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < 0 or idx >= len(documents):
            continue
        doc = documents[idx]
        if doc_type_filter and doc["type"] != doc_type_filter:
            continue
        results.append({
            "id": doc["id"],
            "type": doc["type"],
            "timestamp": doc.get("timestamp"),
            "text": doc["text"],
            "similarity_score": round(float(1 / (1 + dist)), 3),
        })
        if len(results) >= top_k:
            break

    return {
        "query": query,
        "results": results,
        "n_found": len(results),
    }


def _get_recent_events(artifacts: dict, timestamp: str, hours_before: int = 24) -> dict:
    """특정 시점 이전 N시간 이내 이벤트 조회"""
    ts = pd.Timestamp(timestamp)
    start = ts - pd.Timedelta(hours=hours_before)

    documents = artifacts["documents"]
    results = []
    for doc in documents:
        if doc["type"] == "domain_knowledge":
            continue
        if doc.get("timestamp") is None:
            continue
        doc_ts = pd.Timestamp(doc["timestamp"])
        if start <= doc_ts <= ts:
            results.append({
                "id": doc["id"],
                "type": doc["type"],
                "timestamp": doc["timestamp"],
                "text": doc["text"],
            })

    results.sort(key=lambda x: x["timestamp"])
    return {
        "period": f"{start} ~ {ts}",
        "events": results,
        "n_events": len(results),
    }


TOOL_DISPATCHER = {
    "detect_anomaly":          lambda a, timestamp, **_: _detect_anomaly(a, timestamp),
    "classify_failure_type":   lambda a, timestamp, **_: _classify_failure(a, timestamp),
    "get_sensor_trend":        lambda a, timestamp, hours=6, **_: _get_sensor_trend(a, timestamp, hours),
    "search_maintenance_log":  lambda a, query, **_: _search_rag(a, query, doc_type_filter="maintenance_report"),
    "search_domain_knowledge": lambda a, query, **_: _search_rag(a, query, doc_type_filter="domain_knowledge"),
    "search_similar_failures":  lambda a, query, **_: _search_rag(a, query),
    "get_recent_events":       lambda a, timestamp, hours=24, **_: _get_recent_events(a, timestamp, hours),
}


# ── OpenAI 툴 스키마 ──────────────────────────────────────────────────────────

_REASONING = {
    "reasoning": {
        "type": "string",
        "description": "이 툴을 호출하는 이유: 현재 가설, 무엇을 검증하려는지, 결과가 가설을 어떻게 뒷받침하거나 반박할 수 있는지를 한국어로 설명하십시오.",
    }
}

def _params(extra: dict = None) -> dict:
    props = {**_REASONING, **(extra or {})}
    required = ["reasoning"] + list((extra or {}).keys())
    return {"type": "object", "properties": props, "required": required}

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "detect_anomaly",
        "description": "ML 모델로 특정 타임스탬프의 센서 상태를 분석합니다. 이상 점수, 각 센서의 정상 대비 편차(%)를 반환합니다.",
        "parameters": _params({"timestamp": {"type": "string", "description": "분석할 시점 (예: '2020-04-18 12:00:00')"}}),
    }},
    {"type": "function", "function": {
        "name": "classify_failure_type",
        "description": "이상이 감지된 경우 실패 유형(Air Leak / Oil Leak 등)을 ML 모델로 분류합니다.",
        "parameters": _params({"timestamp": {"type": "string", "description": "분석할 시점"}}),
    }},
    {"type": "function", "function": {
        "name": "get_sensor_trend",
        "description": "특정 시점 이전 N시간 동안의 센서 트렌드(평균, 추세 방향, 정상 대비 편차)를 조회합니다.",
        "parameters": _params({
            "timestamp": {"type": "string", "description": "분석 기준 시점"},
            "hours": {"type": "integer", "description": "조회할 시간 범위 (기본 6시간)"},
        }),
    }},
    {"type": "function", "function": {
        "name": "search_maintenance_log",
        "description": "과거 정비 보고서에서 현재 상황과 관련된 정비 이력을 자연어로 검색합니다. "
                       "현재 이상의 원인이 과거 정비와 연관이 있는지 확인할 때 사용하십시오.",
        "parameters": _params({"query": {"type": "string", "description": "검색할 내용 (예: 'Air Leak 압력 저하 정비')"}}),
    }},
    {"type": "function", "function": {
        "name": "search_domain_knowledge",
        "description": "APU 시스템 도메인 지식(센서 의미, 고장 패턴, 점검 기준)을 검색합니다. "
                       "특정 센서 이상의 물리적 의미를 해석하거나 고장 패턴을 확인할 때 사용하십시오.",
        "parameters": _params({"query": {"type": "string", "description": "검색할 도메인 지식 (예: 'Reservoirs 압력 저하 의미')"}}),
    }},
    {"type": "function", "function": {
        "name": "search_similar_failures",
        "description": "현재 증상과 유사한 과거 실패 사례를 전체 문서에서 검색합니다. "
                       "과거 패턴을 현재 케이스에 연결해 추론을 보강할 때 사용하십시오.",
        "parameters": _params({"query": {"type": "string", "description": "유사 사례 검색 내용"}}),
    }},
    {"type": "function", "function": {
        "name": "get_recent_events",
        "description": "특정 시점 이전 N시간 이내에 발생한 이벤트(알람, 정비 기록)를 시간순으로 조회합니다. "
                       "이상 발생 직전 무슨 일이 있었는지 확인할 때 사용하십시오.",
        "parameters": _params({
            "timestamp": {"type": "string", "description": "기준 시점"},
            "hours": {"type": "integer", "description": "조회할 시간 범위 (기본 24시간)"},
        }),
    }},
]


# ── 시스템 프롬프트 ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """당신은 포르투 지하철 열차의 APU(공기 생산 장치) 진단 AI 에이전트입니다.

## APU 시스템
열차의 브레이크, 서스펜션, 도어에 공급할 압축 공기를 생산하는 장치입니다.
주요 부품: 압축기(Compressor) → 에어드라이어(Air Dryer) → 공기탱크(Reservoir) → 클라이언트 파이프

## 분석 원칙

**1단계: 현재 상태 진단**
detect_anomaly로 이상 점수와 센서 편차를 확인하십시오.

**2단계: 가설 수립**
이상이 감지되면 가능한 원인을 가설로 세우십시오.
가설을 세울 때는 도메인 지식을 먼저 검색하여 물리적 근거를 확보하십시오.

**3단계: 다중 증거 교차 검증**
가설을 검증할 때 반드시 다음 두 가지를 모두 확인하십시오:
- **센서 근거**: 가설에 맞는 센서 패턴이 실제로 존재하는가? (get_sensor_trend)
- **이벤트 로그 근거**: 관련 정비 이력이나 과거 유사 사례가 있는가? (search_maintenance_log, search_similar_failures)

센서만으로 결론을 내리는 것은 허용되지 않습니다.
이벤트 로그 검색 없이 결론을 내리는 것은 허용되지 않습니다.

**4단계: 결론**
센서 증거 + 이벤트 로그 근거 + 도메인 지식을 종합하여 결론을 도출하십시오.

## 최종 응답 형식

## 현재 상태 요약
(이상 점수, 주요 이상 센서)

## 가설 및 센서 검증
(세운 가설과 센서 데이터가 뒷받침하는지 여부)

## 이벤트 로그 교차 검증
(정비 이력, 과거 사례에서 찾은 관련 증거)

## 근본 원인 분석
(센서 + 이벤트 로그 3중 교차 근거를 종합한 결론)

## 권고 사항
- 즉시: ...
- 단기 (1일 내): ...
- 모니터링: ...
"""


# ── DiagnosticAgent ────────────────────────────────────────────────────────────

class DiagnosticAgent:
    def __init__(self):
        self.artifacts = load_artifacts()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def run(self, timestamp: str):
        """
        멀티 라운드 tool calling 루프.
        Returns:
            final_text (str): LLM 최종 응답
            tool_log (list[dict]): 툴 호출 기록
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{timestamp} 시점을 분석해주세요."},
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
                assistant_text = (choice.message.content or "").strip()
                if assistant_text:
                    tool_log.append({"type": "thought", "round": round_num, "text": assistant_text})

                messages.append(choice.message)

                for tool_call in choice.message.tool_calls:
                    name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments or "{}")
                    reasoning = args.pop("reasoning", "")

                    if name in TOOL_DISPATCHER:
                        result = TOOL_DISPATCHER[name](self.artifacts, **args)
                    else:
                        result = {"error": f"알 수 없는 툴: {name}"}

                    result_str = json.dumps(result, ensure_ascii=False, indent=2)

                    tool_log.append({
                        "type": "tool",
                        "round": round_num,
                        "name": name,
                        "reasoning": reasoning,
                        "result_summary": _summarize(name, result),
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


def _summarize(name: str, result: dict) -> str:
    if name == "detect_anomaly":
        score = result.get("anomaly_score", 0)
        is_anom = result.get("is_anomaly", False)
        flag = "⚠️ 이상" if is_anom else "✅ 정상"
        return f"{flag} (이상 점수 {score:.2f})"

    if name == "classify_failure_type":
        ftype = result.get("predicted_failure_type", "?")
        conf = result.get("confidence", 0)
        return f"{ftype} ({conf*100:.0f}%)"

    if name == "get_sensor_trend":
        n = result.get("n_windows", 0)
        sensors = result.get("sensors", {})
        worst = max(sensors.items(), key=lambda x: abs(x[1].get("deviation_pct", 0)), default=(None, {}))
        if worst[0]:
            return f"{n}개 윈도우 분석 | 최대 편차: {worst[0]} {worst[1].get('deviation_pct', 0):+.1f}%"
        return f"{n}개 윈도우 분석"

    if name in ("search_maintenance_log", "search_domain_knowledge", "search_similar_failures"):
        n = result.get("n_found", 0)
        return f"{n}건 검색됨"

    if name == "get_recent_events":
        n = result.get("n_events", 0)
        return f"{n}건 이벤트"

    return json.dumps(result, ensure_ascii=False)[:80]
