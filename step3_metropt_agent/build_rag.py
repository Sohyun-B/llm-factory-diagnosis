"""
build_rag.py
이벤트 로그 → FAISS 벡터 DB 구축

문서 소스:
  1. 실패 이벤트 정비 보고서 (models/failure_events.json)
  2. 각 실패 구간의 센서 요약 (자동 생성)
  3. 부품-센서 도메인 지식 (하드코딩)

실행: python build_rag.py  (preprocess.py 먼저 실행 필요)
의존성: pip install faiss-cpu openai
"""

import os
import json
import pickle
import numpy as np
import pandas as pd

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
VECTORSTORE_DIR = os.path.join(MODELS_DIR, "vectorstore")


# ── 도메인 지식 문서 ──────────────────────────────────────────────────────────
# 센서-부품 관계, 고장 패턴 설명 (실제 매뉴얼 대체)

DOMAIN_DOCS = [
    # 시스템 구조
    "APU(공기 생산 장치)는 포르투 지하철 열차의 브레이크, 서스펜션, 도어에 사용할 압축 공기를 생산한다. "
    "주요 부품: 압축기(Compressor), 에어드라이어(Air Dryer), 공기탱크(Reservoir), 클라이언트 파이프. "
    "데이터는 2020년 2월~8월, 1Hz로 수집됐으며 7개 아날로그 센서와 8개 디지털 센서로 구성된다.",

    # 아날로그 센서
    "TP2(bar)는 압축기 내부 압력을 측정한다. "
    "TP2가 급락하면 압축기 자체 이상 또는 Air Leak를 의심한다.",

    "TP3(bar)는 공기압 패널 출력 압력을 측정한다. "
    "Reservoirs 압력은 TP3와 유사해야 정상이며, 두 값의 차이가 커지면 파이프 누출을 의심한다.",

    "H1(bar)은 사이클론 분리기 필터 배출 시 발생하는 압력 강하를 측정한다.",

    "DV_pressure(bar)는 에어드라이어 타워가 공기를 배출할 때 발생하는 압력 강하를 측정한다. "
    "압축기가 부하 운전 중일 때 값이 0이 정상이다. 비정상적으로 높은 값은 에어드라이어 이상을 시사한다.",

    "Reservoirs(bar)는 공기탱크의 하류 압력을 측정한다. TP3 값과 근사해야 정상이다. "
    "브레이크/도어 작동 시 소비되므로 사용 빈도에 따라 압력이 변동한다. "
    "지속적으로 낮으면 Air Leak 가능성이 높다.",

    "Motor_current(A)는 3상 모터의 1개 상 전류를 측정한다. "
    "정상 구간별 기준값: 정지 시 ~0A, 무부하 운전 시 ~4A, 부하 운전 시 ~7A, 기동 시 ~9A. "
    "7A를 지속적으로 초과하면 기계적 과부하를 의심한다.",

    "Oil_temperature(°C)는 압축기 오일 온도를 측정한다. "
    "오일 온도가 비정상적으로 상승하면 냉각 이상을 의심한다.",

    # 디지털 신호
    "COMP는 압축기 흡입 밸브의 전기 신호다. 공기 흡입이 없을 때(압축기 정지 또는 무부하 운전 상태) 활성화된다.",

    "DV_electric은 압축기 출구 밸브를 제어하는 전기 신호다. 부하 운전 시 활성화, 정지 또는 무부하 운전 시 비활성화된다.",

    "TOWERS는 에어드라이어에서 공기 건조 담당 타워와 습기 배출 담당 타워를 정의하는 신호다. "
    "비활성 시 타워1 운전, 활성 시 타워2 운전을 나타낸다.",

    "MPG는 APU 압력이 8.2 bar 미만으로 떨어질 때 압축기를 부하 운전으로 기동시키는 신호다. "
    "MPG 활성화 빈도가 증가하면 Air Leak로 인한 압력 저하를 의심한다.",

    "LPS(Low Pressure Switch)는 공기압이 7 bar 미만일 때 활성화(1)되는 저압 알람이다. "
    "LPS가 자주 활성화되면 Air Leak 또는 과소비가 진행 중이다.",

    "Pressure_switch는 에어드라이어 타워의 수분 배출을 감지하는 전기 신호다.",

    "Oil_level은 오일이 정상 수준 이하일 때 활성화(1)되는 신호다.",

    "Caudal_impulses는 APU에서 저수지로 흐르는 공기량의 절대값을 펄스로 계산하는 신호다.",

    # 고장 패턴 (MetroPT-3 실제 발생 유형: Air Leak만 존재)
    "Air Leak 패턴: Reservoirs 압력이 점진적으로 저하 → MPG 신호 활성화 빈도 증가 → LPS 알람 발생. "
    "원인: 브레이크, 도어, 서스펜션 연결 파이프 또는 에어드라이어 내부의 균열/피팅 이완. "
    "MetroPT-3 데이터셋(2020년 2~8월)에서 발생한 실패는 전부 Air Leak이다.",

    "Air Leak (에어드라이어) 세부 패턴: "
    "DV_pressure 값 이상 + Pressure_switch 신호 불규칙 + TP3와 Reservoirs 사이 압력 차이 발생. "
    "원인: 에어드라이어 내부 밸브 또는 배관 결함.",

    # 점검 기준
    "정비 기준: 실패 발생 2시간 전에 이상 신호를 감지하는 것이 목표(MetroPT 논문 명시). "
    "Air Leak의 경우 Reservoirs 압력이 정상 대비 5% 이상 저하되거나 LPS 알람이 발생하면 즉시 점검이 필요하다.",
]


def build_documents(features: pd.DataFrame, baseline: dict, failure_events: list) -> list[dict]:
    """벡터 DB에 넣을 문서 목록 생성"""
    docs = []

    # 1. 도메인 지식
    for i, text in enumerate(DOMAIN_DOCS):
        docs.append({
            "id": f"domain_{i}",
            "type": "domain_knowledge",
            "timestamp": None,
            "text": text,
        })

    # 2. 실패 이벤트 정비 보고서
    for evt in failure_events:
        # 실패 구간 센서 요약 계산
        mask = (features.index >= evt["start"]) & (features.index <= evt["end"])
        period = features[mask]

        if len(period) == 0:
            continue

        # 정상 대비 편차 계산
        deviations = []
        key_sensors = ["TP2_mean", "TP3_mean", "Reservoirs_mean", "Oil_temperature_mean", "Motor_current_mean"]
        for col in key_sensors:
            if col in period.columns and col in baseline["mean"].index:
                val = period[col].mean()
                base = baseline["mean"][col]
                dev = (val - base) / abs(base) * 100 if base != 0 else 0
                deviations.append(f"{col}={val:.3f}(정상 대비 {dev:+.1f}%)")

        sensor_summary = ", ".join(deviations)

        text = (
            f"[정비 보고서 {evt['id']}] "
            f"실패 유형: {evt['type']} | "
            f"부품: {evt['component']} | "
            f"기간: {evt['start']} ~ {evt['end']} | "
            f"설명: {evt['description']} | "
            f"센서 요약: {sensor_summary}"
        )

        docs.append({
            "id": evt["id"],
            "type": "maintenance_report",
            "timestamp": evt["start"],
            "failure_type": evt["type"],
            "component": evt["component"],
            "text": text,
        })

    # 3. 주요 이상 구간 자동 요약 (LPS 알람 발생 구간)
    lps_on = features[features["LPS_rate"] > 0.5]
    if len(lps_on) > 0:
        # 연속 구간 찾기 (인접 윈도우 묶기)
        lps_times = lps_on.index.tolist()
        groups = []
        current_group = [lps_times[0]]
        for t in lps_times[1:]:
            if (t - current_group[-1]).total_seconds() <= 700:  # 10분+여유
                current_group.append(t)
            else:
                groups.append(current_group)
                current_group = [t]
        groups.append(current_group)

        for i, grp in enumerate(groups[:20]):  # 최대 20개 구간
            start, end = grp[0], grp[-1]
            period = features.loc[start:end]
            tp3_mean = period["TP3_mean"].mean()
            res_mean = period["Reservoirs_mean"].mean()
            motor_mean = period["Motor_current_mean"].mean()

            text = (
                f"[LPS 저압 알람 구간 #{i+1}] "
                f"기간: {start} ~ {end} | "
                f"TP3={tp3_mean:.3f}bar, Reservoirs={res_mean:.3f}bar, "
                f"Motor_current={motor_mean:.3f}A | "
                f"저압 알람 지속 시간: {len(grp)*10}분"
            )
            docs.append({
                "id": f"lps_event_{i}",
                "type": "alarm_event",
                "timestamp": str(start),
                "text": text,
            })

    return docs


def run():
    from dotenv import load_dotenv
    load_dotenv()

    os.makedirs(VECTORSTORE_DIR, exist_ok=True)

    # 아티팩트 로드
    with open(os.path.join(MODELS_DIR, "features.pkl"), "rb") as f:
        features = pickle.load(f)
    with open(os.path.join(MODELS_DIR, "baseline.pkl"), "rb") as f:
        baseline = pickle.load(f)
    with open(os.path.join(MODELS_DIR, "failure_events.json"), "r", encoding="utf-8") as f:
        failure_events = json.load(f)

    print("문서 생성 중...")
    docs = build_documents(features, baseline, failure_events)
    print(f"  총 문서 수: {len(docs)}")
    for doc_type in ["domain_knowledge", "maintenance_report", "alarm_event"]:
        count = sum(1 for d in docs if d["type"] == doc_type)
        print(f"    {doc_type}: {count}건")

    # OpenAI 임베딩으로 FAISS 벡터 DB 구축
    print("\nOpenAI 임베딩 생성 중...")
    from openai import OpenAI
    client = OpenAI()

    texts = [d["text"] for d in docs]
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    embeddings = np.array([e.embedding for e in response.data], dtype=np.float32)
    print(f"  임베딩 shape: {embeddings.shape}")

    # FAISS 인덱스 구축
    import faiss
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)
    print(f"  FAISS 인덱스: {index.ntotal}개 벡터")

    # 저장 (FAISS C++ 라이브러리가 한글 경로 미지원 → 임시 ASCII 경로 우회)
    import tempfile, shutil
    tmp_dir = tempfile.mkdtemp()
    tmp_faiss = os.path.join(tmp_dir, "index.faiss")
    faiss.write_index(index, tmp_faiss)
    shutil.move(tmp_faiss, os.path.join(VECTORSTORE_DIR, "index.faiss"))
    shutil.rmtree(tmp_dir, ignore_errors=True)
    with open(os.path.join(VECTORSTORE_DIR, "documents.pkl"), "wb") as f:
        pickle.dump(docs, f)
    with open(os.path.join(VECTORSTORE_DIR, "embeddings.pkl"), "wb") as f:
        pickle.dump(embeddings, f)

    print("\n저장 완료:")
    print(f"  models/vectorstore/index.faiss")
    print(f"  models/vectorstore/documents.pkl  ({len(docs)}건)")


if __name__ == "__main__":
    run()
