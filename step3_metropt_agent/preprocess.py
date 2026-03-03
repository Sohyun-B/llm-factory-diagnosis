"""
preprocess.py
MetroPT-3 데이터 전처리:
  1. 10초 샘플링 원본 → 10분 윈도우 통계 집계
  2. 정상 구간 baseline 계산
  3. 실패 이벤트 정의 (정비 보고서 하드코딩)
  4. 학습용 레이블 생성 (정상 / Air_Leak_Clients / Air_Leak_AirDryer)

실행: python preprocess.py
"""

import os
import pickle
import numpy as np
import pandas as pd

DATA_PATH = os.path.join(
    os.path.dirname(__file__), "..",
    "data", "metropt+3+dataset", "MetroPT3(AirCompressor).csv"
)
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")

# 아날로그 센서 (통계량 4개 추출)
ANALOG_SENSORS = ["TP2", "TP3", "H1", "DV_pressure", "Reservoirs", "Oil_temperature", "Motor_current"]

# 디지털 신호 (비율만 추출)
DIGITAL_SENSORS = ["COMP", "DV_eletric", "Towers", "MPG", "LPS", "Pressure_switch", "Oil_level", "Caudal_impulses"]

# 윈도우 크기
WINDOW = "10min"

# ── 실패 이벤트 정의 (MetroPT-3 논문 기준) ──────────────────────────────────
# 논문: "The MetroPT dataset for predictive maintenance", Scientific Data 2022
FAILURE_EVENTS = [
    {
        "id": "F1",
        "type": "Air_Leak",
        "component": "Clients",
        "description": "클라이언트 파이프(브레이크/도어/서스펜션) 공기 누출",
        "start": "2020-04-18 00:00:00",
        "end":   "2020-04-18 23:59:59",
    },
    {
        "id": "F2",
        "type": "Air_Leak",
        "component": "Air_Dryer",
        "description": "에어드라이어 공기 누출",
        "start": "2020-05-29 00:00:00",
        "end":   "2020-05-29 23:59:59",
    },
]

# 실패 2시간 전 선행 경고 구간 (사전 감지 타겟)
PRE_FAILURE_HOURS = 2


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.drop(columns=["Unnamed: 0"], errors="ignore")
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def aggregate_windows(df: pd.DataFrame) -> pd.DataFrame:
    """10초 원본 → 10분 윈도우 통계 집계"""
    df = df.set_index("timestamp")

    agg_dict = {}
    for s in ANALOG_SENSORS:
        agg_dict[f"{s}_mean"] = pd.NamedAgg(column=s, aggfunc="mean")
        agg_dict[f"{s}_std"]  = pd.NamedAgg(column=s, aggfunc="std")
        agg_dict[f"{s}_max"]  = pd.NamedAgg(column=s, aggfunc="max")
        agg_dict[f"{s}_min"]  = pd.NamedAgg(column=s, aggfunc="min")
    for s in DIGITAL_SENSORS:
        agg_dict[f"{s}_rate"] = pd.NamedAgg(column=s, aggfunc="mean")  # 활성화 비율

    features = df.resample(WINDOW).agg(**agg_dict).dropna()
    return features


def make_labels(features: pd.DataFrame) -> pd.Series:
    """각 윈도우에 레이블 부여: normal / Air_Leak_Clients / Air_Leak_AirDryer"""
    labels = pd.Series("normal", index=features.index, name="label")

    for evt in FAILURE_EVENTS:
        mask = (features.index >= evt["start"]) & (features.index <= evt["end"])
        labels[mask] = f"{evt['type']}_{evt['component']}"

    return labels


def make_pre_failure_labels(features: pd.DataFrame) -> pd.Series:
    """실패 N시간 전 구간을 'pre_failure'로 레이블링 (조기 감지용)"""
    labels = pd.Series("normal", index=features.index, name="pre_label")

    for evt in FAILURE_EVENTS:
        fail_start = pd.Timestamp(evt["start"])
        pre_start  = fail_start - pd.Timedelta(hours=PRE_FAILURE_HOURS)

        # 실패 구간
        mask_fail = (features.index >= evt["start"]) & (features.index <= evt["end"])
        labels[mask_fail] = f"failure_{evt['component']}"

        # 선행 경고 구간
        mask_pre = (features.index >= pre_start) & (features.index < fail_start)
        labels[mask_pre] = f"pre_failure_{evt['component']}"

    return labels


def compute_baseline(features: pd.DataFrame, labels: pd.Series) -> dict:
    """정상 구간만 사용해 baseline 평균/표준편차 계산"""
    normal = features[labels == "normal"]
    return {
        "mean": normal.mean(),
        "std":  normal.std().replace(0, 1e-6),
        "n_normal_windows": int((labels == "normal").sum()),
    }


def run():
    os.makedirs(MODELS_DIR, exist_ok=True)

    print("원본 데이터 로딩...")
    df = load_raw()
    print(f"  원본: {df.shape}, 기간: {df['timestamp'].min()} ~ {df['timestamp'].max()}")

    print(f"\n{WINDOW} 윈도우 집계 중...")
    features = aggregate_windows(df)
    print(f"  집계 후: {features.shape}")

    print("\n레이블 생성...")
    labels = make_labels(features)
    pre_labels = make_pre_failure_labels(features)

    print("  레이블 분포:")
    for lbl, cnt in labels.value_counts().items():
        print(f"    {lbl}: {cnt}윈도우 ({cnt * 10 / 60:.1f}시간)")

    print("\n정상 baseline 계산...")
    baseline = compute_baseline(features, labels)
    print(f"  정상 윈도우 수: {baseline['n_normal_windows']:,}")

    # 센서별 정상 범위 요약 출력
    print("\n  주요 센서 정상 범위 (mean ± std):")
    for sensor in ["TP2_mean", "TP3_mean", "Oil_temperature_mean", "Motor_current_mean"]:
        m = baseline["mean"][sensor]
        s = baseline["std"][sensor]
        print(f"    {sensor}: {m:.3f} ± {s:.3f}")

    # 실패 이벤트 JSON 저장
    import json
    events_path = os.path.join(MODELS_DIR, "failure_events.json")
    with open(events_path, "w", encoding="utf-8") as f:
        json.dump(FAILURE_EVENTS, f, ensure_ascii=False, indent=2)

    # 저장
    with open(os.path.join(MODELS_DIR, "features.pkl"), "wb") as f:
        pickle.dump(features, f)
    with open(os.path.join(MODELS_DIR, "labels.pkl"), "wb") as f:
        pickle.dump(labels, f)
    with open(os.path.join(MODELS_DIR, "pre_labels.pkl"), "wb") as f:
        pickle.dump(pre_labels, f)
    with open(os.path.join(MODELS_DIR, "baseline.pkl"), "wb") as f:
        pickle.dump(baseline, f)

    print("\n저장 완료:")
    print(f"  models/features.pkl    ({features.shape[0]}윈도우 × {features.shape[1]}피처)")
    print(f"  models/labels.pkl      (정상/실패 레이블)")
    print(f"  models/pre_labels.pkl  (정상/선행경고/실패 레이블)")
    print(f"  models/baseline.pkl    (정상 {baseline['n_normal_windows']}윈도우 기준)")
    print(f"  models/failure_events.json")


if __name__ == "__main__":
    run()
