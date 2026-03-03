"""
preprocess.py
UCI Hydraulic 데이터 전처리:
  1. 각 센서 파일에서 사이클별 통계량(mean/std/max/min) 추출
  2. 전체 feature 행렬 저장 (features.pkl)
  3. 센서 그룹별 통계 저장 (cycle_stats.pkl)  ← Group B 툴이 사용
  4. 정상 사이클 baseline 계산 후 저장 (baseline.pkl)
  5. 레이블 저장 (labels.pkl)

실행: python preprocess.py
"""

import os
import pickle
import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")

# 센서 파일 정의: (파일명, 그룹명, Hz)
SENSORS = [
    ("PS1", "pressure", 100), ("PS2", "pressure", 100), ("PS3", "pressure", 100),
    ("PS4", "pressure", 100), ("PS5", "pressure", 100), ("PS6", "pressure", 100),
    ("EPS1", "power",    100),
    ("FS1",  "flow",      10), ("FS2",  "flow",      10),
    ("TS1",  "temperature", 1), ("TS2",  "temperature", 1),
    ("TS3",  "temperature", 1), ("TS4",  "temperature", 1),
    ("VS1",  "vibration",  1),
    ("CE",   "efficiency", 1), ("CP",  "efficiency",  1), ("SE",  "efficiency",  1),
]

# 레이블 컬럼 정보
LABEL_COLS = ["cooler", "valve", "pump", "accumulator", "stable"]

# 정상(normal) 기준값
NORMAL_VALUES = {
    "cooler": 100,
    "valve": 100,
    "pump": 0,
    "accumulator": 130,
}


def load_sensor_file(name: str) -> np.ndarray:
    """센서 파일 로드 → (2205, samples) 배열"""
    path = os.path.join(DATA_DIR, f"{name}.txt")
    return np.loadtxt(path)  # 공백/탭 구분 자동 처리


def extract_stats(arr: np.ndarray, sensor_name: str) -> dict:
    """사이클별(행별) 통계 추출 → dict of arrays (len=2205)"""
    return {
        f"{sensor_name}_mean": arr.mean(axis=1),
        f"{sensor_name}_std":  arr.std(axis=1),
        f"{sensor_name}_max":  arr.max(axis=1),
        f"{sensor_name}_min":  arr.min(axis=1),
    }


def load_labels() -> pd.DataFrame:
    path = os.path.join(DATA_DIR, "profile.txt")
    labels = pd.read_csv(path, sep=r"\s+", header=None, names=LABEL_COLS)
    return labels


def compute_baseline(features: pd.DataFrame, labels: pd.DataFrame) -> dict:
    """4개 부품 모두 정상인 사이클들의 평균/표준편차"""
    normal_mask = (
        (labels["cooler"] == NORMAL_VALUES["cooler"]) &
        (labels["valve"] == NORMAL_VALUES["valve"]) &
        (labels["pump"] == NORMAL_VALUES["pump"]) &
        (labels["accumulator"] == NORMAL_VALUES["accumulator"])
    )
    normal_cycles = features[normal_mask]
    return {
        "mean": normal_cycles.mean(),
        "std":  normal_cycles.std().replace(0, 1e-6),  # 0 방지
        "n_normal": int(normal_mask.sum()),
    }


def run():
    os.makedirs(MODELS_DIR, exist_ok=True)

    print("센서 파일 로딩 중...")
    all_stats = {}
    group_data = {}  # 그룹별 센서 이름 목록

    for sensor_name, group, hz in SENSORS:
        arr = load_sensor_file(sensor_name)
        stats = extract_stats(arr, sensor_name)
        all_stats.update(stats)

        if group not in group_data:
            group_data[group] = []
        group_data[group].append(sensor_name)

        print(f"  {sensor_name}: {arr.shape} ({hz}Hz) → {len(stats)}개 통계")

    # feature 행렬 (ML 학습용)
    features = pd.DataFrame(all_stats)
    print(f"\nfeature 행렬: {features.shape}")

    # 레이블 로드
    labels = load_labels()
    print(f"레이블: {labels.shape}")
    print("  냉각기 분포:", labels["cooler"].value_counts().to_dict())
    print("  밸브 분포:",   labels["valve"].value_counts().to_dict())
    print("  펌프 분포:",   labels["pump"].value_counts().to_dict())
    print("  어큐뮬레이터 분포:", labels["accumulator"].value_counts().to_dict())

    # 정상 baseline 계산
    baseline = compute_baseline(features, labels)
    print(f"\n정상 사이클 수: {baseline['n_normal']}")

    # 센서 그룹별 통계 (Group B 툴용)
    # 각 그룹의 mean 컬럼들만 추출해 사이클별 그룹 평균 계산
    cycle_stats = {}
    for group, sensor_names in group_data.items():
        mean_cols = [f"{s}_mean" for s in sensor_names]
        std_cols  = [f"{s}_std"  for s in sensor_names]
        cycle_stats[group] = {
            "sensors":   sensor_names,
            "mean_cols": mean_cols,
            "values":    features[mean_cols + std_cols].copy(),
        }

    # 저장
    with open(os.path.join(MODELS_DIR, "features.pkl"), "wb") as f:
        pickle.dump(features, f)
    with open(os.path.join(MODELS_DIR, "labels.pkl"), "wb") as f:
        pickle.dump(labels, f)
    with open(os.path.join(MODELS_DIR, "baseline.pkl"), "wb") as f:
        pickle.dump(baseline, f)
    with open(os.path.join(MODELS_DIR, "cycle_stats.pkl"), "wb") as f:
        pickle.dump(cycle_stats, f)
    with open(os.path.join(MODELS_DIR, "group_data.pkl"), "wb") as f:
        pickle.dump(group_data, f)

    print("\n저장 완료:")
    print(f"  models/features.pkl    ({features.shape[0]}행 × {features.shape[1]}열)")
    print(f"  models/labels.pkl      ({len(labels)}행)")
    print(f"  models/baseline.pkl    (정상 {baseline['n_normal']}사이클 기준)")
    print(f"  models/cycle_stats.pkl ({len(cycle_stats)}개 그룹)")


if __name__ == "__main__":
    run()
