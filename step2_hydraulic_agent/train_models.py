"""
train_models.py
4개 Random Forest 분류기 학습:
  - model_cooler.pkl      (3 클래스: 100/20/3)
  - model_valve.pkl       (4 클래스: 100/90/80/73)
  - model_pump.pkl        (3 클래스: 0/1/2)
  - model_accumulator.pkl (4 클래스: 130/115/100/90)

실행: python train_models.py  (preprocess.py 먼저 실행 필요)
"""

import os
import pickle
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")

# 부품별 설정: (레이블 컬럼, 모델 파일명, 클래스 의미)
COMPONENTS = {
    "cooler": {
        "col": "cooler",
        "model_file": "model_cooler.pkl",
        "label_map": {100: "정상", 20: "성능저하", 3: "고장임박"},
    },
    "valve": {
        "col": "valve",
        "model_file": "model_valve.pkl",
        "label_map": {100: "최적", 90: "경미한지연", 80: "심각한지연", 73: "고장임박"},
    },
    "pump": {
        "col": "pump",
        "model_file": "model_pump.pkl",
        "label_map": {0: "누수없음", 1: "약한누수", 2: "심각한누수"},
    },
    "accumulator": {
        "col": "accumulator",
        "model_file": "model_accumulator.pkl",
        "label_map": {130: "최적", 115: "약간저하", 100: "심각저하", 90: "고장임박"},
    },
}


def load_artifacts():
    with open(os.path.join(MODELS_DIR, "features.pkl"), "rb") as f:
        features = pickle.load(f)
    with open(os.path.join(MODELS_DIR, "labels.pkl"), "rb") as f:
        labels = pickle.load(f)
    return features, labels


def train_component(name: str, config: dict, features: pd.DataFrame, labels: pd.DataFrame):
    col = config["col"]
    label_map = config["label_map"]
    y_raw = labels[col].values
    y = np.array([label_map[v] for v in y_raw])

    X_train, X_test, y_train, y_test = train_test_split(
        features.values, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=None,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred)

    # feature importance 상위 10개 저장
    importance_series = pd.Series(
        clf.feature_importances_, index=features.columns
    ).sort_values(ascending=False)
    top10 = importance_series.head(10)

    print(f"\n{'='*50}")
    print(f"[{name.upper()}]  정확도: {acc:.4f}")
    print(report)
    print("Feature importance 상위 10:")
    for feat, imp in top10.items():
        print(f"  {feat}: {imp:.4f}")

    # 저장 (모델 + 메타데이터)
    artifact = {
        "model": clf,
        "label_map": label_map,           # 숫자 → 한국어 레이블
        "inv_label_map": {v: k for k, v in label_map.items()},
        "feature_names": list(features.columns),
        "top_features": top10.to_dict(),
        "accuracy": acc,
    }
    model_path = os.path.join(MODELS_DIR, config["model_file"])
    with open(model_path, "wb") as f:
        pickle.dump(artifact, f)

    return acc


def run():
    print("artifact 로딩...")
    features, labels = load_artifacts()
    print(f"features: {features.shape}, labels: {labels.shape}")

    results = {}
    for name, config in COMPONENTS.items():
        acc = train_component(name, config, features, labels)
        results[name] = acc

    print("\n" + "="*50)
    print("학습 완료 요약:")
    for name, acc in results.items():
        print(f"  {name:15s}: {acc:.4f} ({acc*100:.1f}%)")


if __name__ == "__main__":
    run()
