"""
UCI Online Retail II — EDA for Step 5 Rule Discovery
- 반복 구매 패턴 분석
- 동반 구매 분석 (상위 상품만)
- 규칙 주입 후보 탐색
"""

import pandas as pd
import numpy as np
from collections import Counter
from itertools import combinations
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# === 데이터 로드 ===
print("Loading data...")
df = pd.read_csv(os.path.join(DATA_DIR, "retail_clean.csv"), encoding="utf-8-sig")
df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
df["Customer ID"] = df["Customer ID"].astype(int)
print(f"Loaded: {len(df):,} rows")


# ============================================================
# 1. 고객-상품 반복 구매 간격 패턴
# ============================================================
print("\n" + "=" * 60)
print("1. 고객-상품 반복 구매 간격 분석")
print("=" * 60)

good_pairs = []
for (cid, sc), group in df.groupby(["Customer ID", "StockCode"]):
    # Invoice 단위로 집계 (같은 Invoice에서 같은 상품 여러 줄 → 1건)
    invoices = group.groupby("Invoice").agg(
        date=("InvoiceDate", "first"),
        qty=("Quantity", "sum"),
    ).sort_values("date")

    if len(invoices) < 5:
        continue

    dates = invoices["date"].values
    intervals = np.diff(dates).astype("timedelta64[D]").astype(int)
    intervals = intervals[intervals > 0]

    if len(intervals) < 4:
        continue

    mean_iv = float(np.mean(intervals))
    if mean_iv < 3:
        continue

    cv = float(np.std(intervals) / mean_iv)
    span = int((dates[-1] - dates[0]).astype("timedelta64[D]").astype(int))

    desc = str(group["Description"].iloc[0])[:50]
    country = group["Country"].iloc[0]

    good_pairs.append({
        "cid": int(cid),
        "stock": sc,
        "desc": desc,
        "country": country,
        "n_purchases": len(invoices),
        "mean_interval": round(mean_iv, 1),
        "std_interval": round(float(np.std(intervals)), 1),
        "cv": round(cv, 2),
        "median_interval": round(float(np.median(intervals)), 1),
        "span": span,
        "mean_qty": round(float(invoices["qty"].mean()), 1),
        "std_qty": round(float(invoices["qty"].std()), 1),
        "intervals": [int(i) for i in intervals],
        "qtys": [int(q) for q in invoices["qty"].values],
        "dates": [str(d)[:10] for d in invoices["date"].values],
    })

good_df = pd.DataFrame(good_pairs)
print(f"5회 이상 반복 구매 조합: {len(good_df)}")

# CV < 0.6, span >= 180일
regular = good_df[(good_df["cv"] < 0.6) & (good_df["span"] >= 180)].sort_values("cv")
print(f"규칙적 (CV<0.6, span>=180일): {len(regular)}")

print(f"\n가장 규칙적인 30개:")
for _, row in regular.head(30).iterrows():
    print(f"  C{row['cid']} x {row['stock']}: {row['n_purchases']}회, "
          f"{row['mean_interval']}일간격(CV={row['cv']}), {row['span']}일, "
          f"평균{row['mean_qty']}개 | {row['country']} | {row['desc']}")


# ============================================================
# 2. 동반 구매 분석 (효율적 버전 — 상위 상품만)
# ============================================================
print("\n" + "=" * 60)
print("2. 동반 구매 분석")
print("=" * 60)

# 빈번한 상품만 (200회 이상 등장) 대상 — 속도 최적화
stock_counts = df["StockCode"].value_counts()
frequent_stocks = set(stock_counts[stock_counts >= 200].index)
print(f"빈번한 상품 (200회+): {len(frequent_stocks)}")

# 사전에 Invoice-StockCode 매핑 구축 (속도 최적화)
df_freq = df[df["StockCode"].isin(frequent_stocks)]
invoice_items = df_freq.groupby("Invoice")["StockCode"].apply(lambda x: frozenset(x.unique()))

co_occ = Counter()
for items in invoice_items:
    if len(items) < 2 or len(items) > 20:
        continue
    for pair in combinations(sorted(items), 2):
        co_occ[pair] += 1

# lift 계산용 사전 구축
n_invoices = df["Invoice"].nunique()
stock_invoice_counts = df_freq.groupby("StockCode")["Invoice"].nunique().to_dict()
desc_map = df.drop_duplicates("StockCode").set_index("StockCode")["Description"].to_dict()

print(f"\n상위 30 동반 구매:")
for (i1, i2), cnt in co_occ.most_common(30):
    d1 = str(desc_map.get(i1, "?"))[:30]
    d2 = str(desc_map.get(i2, "?"))[:30]
    n_i1 = stock_invoice_counts.get(i1, 1)
    n_i2 = stock_invoice_counts.get(i2, 1)
    expected = n_i1 * n_i2 / n_invoices
    lift = cnt / expected if expected > 0 else 0
    print(f"  {i1} + {i2}: {cnt}회, lift={lift:.1f} | {d1} + {d2}")


# ============================================================
# 3. 고객 간 시간 근접성 (교차 구매 후보)
# ============================================================
print("\n" + "=" * 60)
print("3. 고객 간 시간 근접성")
print("=" * 60)

# 주문 20회 이상 고객만
cust_invoice_counts = df.groupby("Customer ID")["Invoice"].nunique()
freq_custs = cust_invoice_counts[cust_invoice_counts >= 20].index.tolist()
print(f"20회 이상 주문 고객: {len(freq_custs)}")

# 고객별 주문일 추출
cust_dates = {}
for cid in freq_custs:
    dates = sorted(df[df["Customer ID"] == cid]["InvoiceDate"].dt.normalize().unique())
    if len(dates) >= 10:
        cust_dates[cid] = dates

print(f"분석 대상 고객: {len(cust_dates)}")

# 고객 쌍별 시간 근접성 (상위 100 조합만 샘플링)
import random
random.seed(42)
cust_list = list(cust_dates.keys())
if len(cust_list) > 50:
    cust_sample = random.sample(cust_list, 50)
else:
    cust_sample = cust_list

proximity_results = []
for c1, c2 in combinations(cust_sample, 2):
    d1_list = cust_dates[c1]
    d2_list = cust_dates[c2]

    # c1 → c2: c1 주문 후 1~7일 내 c2 주문
    follow = 0
    for d1 in d1_list:
        for d2 in d2_list:
            diff = (d2 - d1).days
            if 1 <= diff <= 7:
                follow += 1
                break

    prob = follow / len(d1_list)
    # 기대치
    days_span = (max(d2_list) - min(d2_list)).days + 1
    expected = min(1.0, len(d2_list) * 7 / days_span) if days_span > 0 else 0
    lift = prob / expected if expected > 0 else 0

    if prob > 0.3 and lift > 1.3 and follow >= 5:
        proximity_results.append({
            "from": int(c1), "to": int(c2),
            "follow": follow, "total": len(d1_list),
            "prob": round(prob, 2),
            "expected": round(expected, 2),
            "lift": round(lift, 2),
        })

proximity_results.sort(key=lambda x: -x["lift"])
print(f"\n유의미한 교차 패턴: {len(proximity_results)}개")
for r in proximity_results[:15]:
    print(f"  C{r['from']} → C{r['to']}: {r['follow']}/{r['total']}={r['prob']:.0%} "
          f"(기대 {r['expected']:.0%}, lift={r['lift']})")


# ============================================================
# 4. 계절성 분석 (월별 상품 카테고리)
# ============================================================
print("\n" + "=" * 60)
print("4. 계절성 분석")
print("=" * 60)

df["month"] = df["InvoiceDate"].dt.month
df["year"] = df["InvoiceDate"].dt.year

# 상위 50 상품의 월별 수량
top_stocks = df["StockCode"].value_counts().head(50).index
for sc in top_stocks[:10]:
    monthly = df[df["StockCode"] == sc].groupby("month")["Quantity"].sum()
    if monthly.max() > 0:
        peak = monthly.idxmax()
        trough = monthly.idxmin()
        ratio = monthly.max() / (monthly.mean() + 1)
        if ratio > 2:
            desc = str(df[df["StockCode"] == sc]["Description"].iloc[0])[:40]
            print(f"  {sc}: peak={peak}월, trough={trough}월, ratio={ratio:.1f} | {desc}")


# ============================================================
# 5. 요약 통계 저장
# ============================================================
summary = {
    "total_rows": len(df),
    "unique_customers": int(df["Customer ID"].nunique()),
    "unique_products": int(df["StockCode"].nunique()),
    "unique_invoices": int(df["Invoice"].nunique()),
    "date_range": [str(df["InvoiceDate"].min())[:10], str(df["InvoiceDate"].max())[:10]],
    "regular_repeat_pairs": len(regular),
    "top_regular_pairs": regular.head(50)[["cid", "stock", "desc", "country",
                                            "n_purchases", "mean_interval", "cv",
                                            "span", "mean_qty"]].to_dict(orient="records"),
    "proximity_pairs": proximity_results[:20],
}

out_path = os.path.join(DATA_DIR, "eda_summary.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
print(f"\nEDA 요약 저장: {out_path}")
print("Done.")
