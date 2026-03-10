# Step 5 테스트용 데이터셋 후보 조사

> 조사일: 2026-03-10
> 목적: 장기 반복 구매 이력이 있는 공개 데이터셋 → 복잡한 규칙 주입 후 규칙 발견/생애주기/drift 테스트

---

## 선정 기준

| # | 조건 | 이유 |
|---|------|------|
| 1 | 장기 시계열 (1~2년+) | 규칙 생애주기(탄생→검증→퇴역→부활) 테스트 |
| 2 | 같은 고객이 같은 상품 반복 구매 | 주기성, 교차 패턴 발견의 전제 |
| 3 | Customer ID + Product ID + Date + Quantity | 최소 필수 컬럼 |
| 4 | B2B 또는 도매 성격 | 자재 발주 시나리오와 유사 |
| 5 | 적당한 크기 (수십만~수백만 행) | 작업 가능한 규모 |

---

## 후보 목록

### Tier 1: 강력 추천

#### 1. UCI Online Retail II ⭐ 선정

| 항목 | 내용 |
|------|------|
| **출처** | [UCI ML Repository](https://archive.ics.uci.edu/dataset/502/online+retail+ii) / [Kaggle](https://www.kaggle.com/datasets/mashlyn/online-retail-ii-uci) |
| **기간** | 2009-12-01 ~ 2011-12-09 (약 2년) |
| **규모** | 1,067,371행, 43MB |
| **성격** | B2B 도매 (UK 기프트웨어 소매업체의 도매 거래) |
| **컬럼** | InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country |
| **반복구매** | 매우 강함 — 도매 고객이 같은 상품을 수십 번 반복 주문 |
| **이슈** | CustomerID 25% 결측, "C"로 시작하는 InvoiceNo는 취소 건, 음수 수량 = 반품 |
| **선정 이유** | B2B 도매, 2년, 고객/상품/수량/날짜 전부 있음, 적당한 크기 |

#### 2. Instacart Market Basket

| 항목 | 내용 |
|------|------|
| **출처** | [Kaggle](https://www.kaggle.com/datasets/psparks/instacart-market-basket-analysis) |
| **기간** | 익명화 (상대적 시간만, days_since_prior_order) |
| **규모** | 340만 주문, 3,240만 품목 행, ~200MB |
| **성격** | B2C 식료품 |
| **컬럼** | order_id, user_id, product_id, reordered, order_dow, order_hour_of_day, days_since_prior_order |
| **반복구매** | 매우 강함 — reordered 플래그 59.86% |
| **이슈** | 실제 날짜 없음, 수량 없음(바스켓에 있다/없다만) |
| **비고** | 주기성 탐지에는 좋지만 날짜/수량 없어서 Step 5 시나리오에 부적합 |

#### 3. Corporacion Favorita Grocery Sales

| 항목 | 내용 |
|------|------|
| **출처** | [Kaggle](https://www.kaggle.com/c/favorita-grocery-sales-forecasting/data) |
| **기간** | 2013-01 ~ 2017-08 (4.5년) |
| **규모** | 1.25억 행, 4.5GB |
| **성격** | B2C 식료품 소매 (매장 단위 집계) |
| **컬럼** | date, store_nbr, item_nbr, unit_sales, onpromotion + 보조 테이블(유가, 공휴일, 매장정보) |
| **반복구매** | 매장-상품 단위로 매우 강함 |
| **이슈** | 개별 고객 ID 없음(매장이 "고객"), 너무 큼 |
| **비고** | 최장 기간, 외부 변수 풍부하지만 고객 단위 분석 불가 |

---

### Tier 2: 조건부 추천

#### 4. DataCo SMART Supply Chain

| 항목 | 내용 |
|------|------|
| **출처** | [Kaggle](https://www.kaggle.com/datasets/shashwatwork/dataco-smart-supply-chain-for-big-data-analysis) |
| **기간** | 2015~2018 (3년) |
| **규모** | 180,519행, 27MB |
| **성격** | B2C + 물류 |
| **컬럼** | Order Customer Id, Product Name, Order Date, Order Item Quantity, Sales, Shipping Mode, Delivery Status, Late_delivery_risk 등 ~50개 |
| **반복구매** | 중간 |
| **이슈** | 반합성 데이터 의심, 순수 B2B 아님 |

#### 5. Open E-Commerce 1.0 (Amazon)

| 항목 | 내용 |
|------|------|
| **출처** | [Harvard Dataverse](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/YGLYDY) |
| **기간** | 2018~2022 (5년) |
| **규모** | 180만 구매, 5,027 소비자 |
| **성격** | B2C (Amazon) |
| **반복구매** | 강함 — 5년간 전체 구매 이력 |
| **이슈** | 소비자 5,027명뿐, B2C, Harvard Dataverse 계정 필요 |

#### 6. California State Purchase Order Data

| 항목 | 내용 |
|------|------|
| **출처** | [California Open Data](https://data.ca.gov/dataset/purchase-order-data) |
| **기간** | FY 2012~2015 (3 회계연도) |
| **규모** | 수천 건, 130+ 주정부 부서 |
| **성격** | B2B 정부 조달 |
| **반복구매** | 있음 — 같은 부서가 같은 공급사에서 반복 조달 |
| **이슈** | $5,000 이상만, PO당 첫 UNSPSC 코드만 기록 |

#### 7. Global Public Procurement Dataset (GPPD)

| 항목 | 내용 |
|------|------|
| **출처** | [Mendeley Data](https://data.mendeley.com/datasets/fwzpywbhgw/3) |
| **기간** | 2006~2021 (15년) |
| **규모** | 7,200만 계약, 42개국 |
| **성격** | B2B 공공 조달 |
| **반복구매** | 매우 강함 |
| **이슈** | 너무 큼, 국가별 데이터 품질 편차, 서비스/건설 위주 |

---

### 비추천

#### 8. Olist Brazilian E-Commerce

- 출처: [Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
- 반복구매율 ~3% → 주기 패턴 탐지 불가

#### 9. Rossmann Store Sales

- 출처: [Kaggle](https://www.kaggle.com/c/rossmann-store-sales)
- 매장 단위 일별 집계만 — 고객/상품 정보 없음

---

## 최종 선정: UCI Online Retail II

**선정 이유 요약**:
1. B2B 도매 → 자재 발주와 가장 유사
2. 2년치 → 계절성 2사이클 확인 가능
3. 같은 고객이 같은 상품 반복 주문 → 주기성/교차 패턴 발견 가능
4. 43MB → 작업하기 적당
5. CustomerID, StockCode, Quantity, InvoiceDate, UnitPrice 전부 존재

**데이터 위에 심을 규칙 설계**: 별도 문서로 작성 예정
