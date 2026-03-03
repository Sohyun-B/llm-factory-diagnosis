"""
train_models.py
두 가지 ML 모델 학습:
  1. anomaly_detector: 정상 vs 이상 이진 분류 (Random Forest)
  2. failure_classifier: 실패 유형 분류 (Air_Leak_Clients / Air_Leak_AirDryer)

실행: python train_models.py  (preprocess.py 먼저 실행 필요)
"""

import os
import pickle
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, roc_auc_score

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")


def load_artifacts():
    def _load(name):
        with open(os.path.join(MODELS_DIR, name), "rb") as f:
            return pickle.load(f)
    return _load("features.pkl"), _load("labels.pkl"), _load("pre_labels.pkl"), _load("baseline.pkl")


def train_anomaly_detector(features: pd.DataFrame, labels: pd.Series):
    """정상(0) vs 이상(1) 이진 분류기"""
    y = (labels != "normal").astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        features.values, y.values, test_size=0.2, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=200, max_depth=None, min_samples_leaf=2,
        random_state=42, n_jobs=-1, class_weight="balanced"
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    y_prob = clf.predict_proba(X_test)[:, 1]
    acc  = accuracy_score(y_test, y_pred)
    auc  = roc_auc_score(y_test, y_prob)

    importance = pd.Series(
        clf.feature_importances_, index=features.columns
    ).sort_values(ascending=False)

    print(f"\n{'='*50}")
    print(f"[ANOMALY DETECTOR]  정확도: {acc:.4f}  AUC: {auc:.4f}")
    print(classification_report(y_test, y_pred, target_names=["정상", "이상"]))
    print("Feature importance 상위 10:")
    for feat, imp in importance.head(10).items():
        print(f"  {feat}: {imp:.4f}")

    artifact = {
        "model": clf,
        "feature_names": list(features.columns),
        "top_features": importance.head(10).to_dict(),
        "accuracy": acc,
        "auc": auc,
        "label_map": {0: "정상", 1: "이상"},
    }
    with open(os.path.join(MODELS_DIR, "anomaly_detector.pkl"), "wb") as f:
        pickle.dump(artifact, f)

    return acc, auc


def train_failure_classifier(features: pd.DataFrame, labels: pd.Series):
    """실패 유형 분류 (정상 제외, 실패 구간만 사용)"""
    mask = labels != "normal"
    X_fail = features[mask].values
    y_fail = labels[mask].values

    if len(np.unique(y_fail)) < 2:
        print("\n[FAILURE CLASSIFIER] 실패 유형이 1종류뿐 — 분류기 학습 생략")
        return None

    X_train, X_test, y_train, y_test = train_test_split(
        X_fail, y_fail, test_size=0.2, random_state=42, stratify=y_fail
    )

    clf = RandomForestClassifier(
        n_estimators=200, max_depth=None, min_samples_leaf=1,
        random_state=42, n_jobs=-1
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)

    print(f"\n{'='*50}")
    print(f"[FAILURE CLASSIFIER]  정확도: {acc:.4f}")
    print(classification_report(y_test, y_pred))

    importance = pd.Series(
        clf.feature_importances_, index=features.columns
    ).sort_values(ascending=False)

    artifact = {
        "model": clf,
        "feature_names": list(features.columns),
        "top_features": importance.head(10).to_dict(),
        "accuracy": acc,
        "classes": list(clf.classes_),
    }
    with open(os.path.join(MODELS_DIR, "failure_classifier.pkl"), "wb") as f:
        pickle.dump(artifact, f)

    return acc


def run():
    print("artifact 로딩...")
    features, labels, pre_labels, baseline = load_artifacts()
    print(f"features: {features.shape}, 레이블 분포: {labels.value_counts().to_dict()}")

    train_anomaly_detector(features, labels)
    train_failure_classifier(features, labels)

    print("\n" + "="*50)
    print("모델 학습 완료")
    print("  models/anomaly_detector.pkl")
    print("  models/failure_classifier.pkl")


if __name__ == "__main__":
    run()
