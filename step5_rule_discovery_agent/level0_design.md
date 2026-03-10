# Level 0 분석 설계 원칙: 도메인 무관 일반화 프레임워크

> 작성일: 2026-03-09
> 갱신일: 2026-03-10 — 혼합 패턴 분해 레이어 추가 (Layer 1.5, 2.5, 3.5) + 구현 완료 (`phase1_generic.py`)
> 핵심 질문: "처음 보는 데이터를 받았을 때, 사전 지식 없이 어떤 분석을 먼저 돌려야 하는가?"

---

## 1. 기존 프레임워크에서 배운 것

### 1-1. hctsa → catch22: "7,700개를 22개로 줄인 방법"

시계열 분석 라이브러리 [hctsa](https://github.com/benfulcher/hctsa)는 7,700개 이상의 시계열 피처를 추출한다.
이 중에서 **93개 분류 문제에서 성능이 좋고, 서로 중복이 적은 22개**를 추린 것이 [catch22](https://github.com/DynamicsAndNeuralSystems/catch22).

catch22가 커버하는 **7가지 분석 축**:

| 축 | 무엇을 측정하는가 | 예시 |
|---|---|---|
| **분포(Distribution)** | 값의 분포 형태 | 히스토그램 모드, 이봉성 |
| **선형 자기상관(Linear AC)** | 과거 값과의 선형 관계 | ACF 첫 교차, 첫 최소점 |
| **비선형 자기상관(Nonlinear AC)** | 비선형 시간 의존성 | 시차 기반 비선형 통계 |
| **연속 차분(Successive diff)** | 연속 값 사이의 변화율 | 변화량의 분산, 평균 |
| **이상치/극단값(Outliers)** | 극단 이벤트의 시간 패턴 | 이상치 간 간격의 중앙값 |
| **변동 스케일링(Fluctuation)** | 스케일에 따른 변동 구조 | 자기유사 스케일링 지수 |
| **예측가능성(Predictability)** | 단순 예측 모델의 잔차 | 이동평균 예측 오차 |

**교훈**: 7,700개 중 22개만 남겨도 93개 분류 문제에서 성능이 유지된다.
→ **Level 0도 "축"을 잘 고르면 적은 분석으로 넓은 커버리지 가능.**

### 1-2. tsfresh: "794개 피처의 5가지 카테고리"

[tsfresh](https://github.com/blue-yonder/tsfresh)는 63개 시계열 분석 메서드로 794개 피처를 추출한다.
5가지 카테고리:

1. **분포 통계** — mean, std, skewness, kurtosis, quantile
2. **자기상관** — ACF, partial ACF, 시차별 상관
3. **엔트로피** — sample entropy, approximate entropy, permutation entropy
4. **정상성** — ADF test (단위근), 추세 검정
5. **비선형** — Friedrich coefficients, 재귀 시간

### 1-3. DataPrep.EDA / YData Profiling: "데이터 타입 기반 자동 분석"

[DataPrep.EDA](https://arxiv.org/abs/2104.00841)는 **컬럼 타입을 감지하고, 타입에 맞는 분석을 자동 선택**한다:
- 숫자(Numeric) → 분포, 상관, 이상치
- 범주(Categorical) → 빈도, 카디널리티, 연관
- 시간(DateTime) → 시간별 집계, 추세
- 텍스트(Text) → 길이, 패턴

**교훈**: 분석 항목을 데이터 타입에서 자동 결정하면 도메인 지식 없이 일반화 가능.

### 1-4. EDA 체크리스트: "단변량 → 이변량 → 다변량 순서"

R. Peng의 [EDA 체크리스트](https://bookdown.org/rdpeng/exdata/exploratory-data-analysis-checklist.html):
1. 데이터 구조 확인 (dimensions, types)
2. 상위/하위 데이터 확인 (head/tail)
3. 각 변수의 요약 통계 (summary)
4. 각 변수의 결측/이상 확인
5. **단변량 분포** 확인
6. **이변량 관계** 확인
7. 가설 검정

**교훈**: 복잡한 패턴은 항상 단순한 관찰 위에 쌓인다. 순서가 중요하다.

---

## 2. Level 0 일반화 설계: 8-Layer 분석 스택

기존 프레임워크들의 공통점을 추출하면, **데이터 타입과 무관하게 적용 가능한 분석 레이어**가 나온다.

초기 설계(v1)에서는 5개 레이어였으나, **혼합 패턴 분해 실험**(synthetic_experiment_results.md의 P10 미감지)에서
단일 패턴 분석만으로는 현실 데이터의 다중 원인 구조를 다룰 수 없음이 확인되어 3개 레이어를 추가했다.

```
Layer 4:   조건부 패턴    ← "A이면 B" 관계
Layer 3.5: 다중 조건 연관  ← "A AND B이면 C" 관계         ★ 추가
Layer 3:   시간 구조      ← 시간에 따른 변화
Layer 2.5: 잔차 분석      ← 주 패턴 제거 후 2차 패턴 탐색   ★ 추가
Layer 2:   관계           ← 엔티티 간, 변수 간 상관
Layer 1.5: 혼합 분포 분해  ← GMM으로 component 분리        ★ 추가
Layer 1:   엔티티별 프로파일 ← 각 주체의 행동 특성
Layer 0:   스키마 & 분포   ← 데이터 자체의 구조
```

### 왜 추가했는가: P10 미감지 사후 분석

합성 데이터 실험(Exp 3)에서 대성기업 AL6061의 interval drift(P10: 14일→21일)가 검증 쿼리로 감지되지 못했다.
원인: 같은 고객의 같은 상품 발주 30건 안에 **다른 패턴(P3 격주 + P4 교차)**이 혼합되어 있었기 때문.

```
대성기업 AL6061 간격: [15, 14, 1, 14, 0, 13, 15, 4, 15, 17, 3, ...]
                              ^           ^              ^
                              P4(교차)    P4(교차)        P4(교차)

→ 0, 1, 4일 간격 = P4 교차 발주가 만든 것
→ 이것이 평균을 오염시켜 drift(14→21일) 신호가 매몰됨
→ 단순 전반부/후반부 비교, Spearman 상관 모두 실패
```

**이 문제는 현실에서 항상 발생한다:**
- 같은 고객의 같은 상품이라도 **다른 이유**로 구매
- 같은 센서 값이라도 **다른 고장 모드**가 겹침
- 같은 알람이라도 **다른 원인**으로 발생

### Layer 0: 스키마 & 분포 (What is this data?)

**목적**: 데이터의 구조, 크기, 타입, 기본 분포를 파악

| 분석 | 입력 | 출력 | 비고 |
|------|------|------|------|
| 컬럼 타입 감지 | 전체 데이터 | {numeric, categorical, datetime, text, id} | DataPrep 방식 |
| 기초 통계 | 각 컬럼 | mean, median, std, min, max, quantiles | 숫자형만 |
| 빈도 분포 | 범주형 컬럼 | value_counts, cardinality, 최빈값 | |
| 결측/이상 | 전체 | 결측 비율, IQR 이상치 비율 | |
| 기간/샘플링 | datetime 컬럼 | 시작~끝, 간격 분포, 공백 기간 | |

**이 레이어는 어떤 데이터든 동일하게 적용 가능** — pandas_profiling, DataPrep이 이미 자동화한 영역.

### Layer 1: 엔티티별 프로파일 (Who does what?)

**목적**: 각 "주체"(고객, 센서, 장비 등)의 개별 행동 특성

| 분석 | 무엇을 측정 | 파라미터 결정 방법 |
|------|------------|-------------------|
| **발생 간격 통계** | mean, std, CV, median | 엔티티 × 카테고리 자동 groupby |
| **활동 규칙성** | CV (변동계수) | CV < 0.3 = 규칙적, > 0.7 = 불규칙 |
| **시간 집중도** | 요일/주차/월 엔트로피 | 균등분포 대비 집중도 (1 - H/H_max) |
| **수량 분포** | mean, std, bimodal score | 중앙값 기준 이봉성 테스트 |
| **활동 기간** | 첫 등장 ~ 마지막 등장 | 전체 기간 대비 활동 범위 |

**핵심 설계 원칙**:
- `groupby` 키는 **엔티티 컬럼(고객, 장비 등) × 카테고리 컬럼(품목, 센서 등)의 모든 조합**을 자동 생성
- 최소 건수(3~5건) 미만은 분석 제외
- 파라미터(CV 임계값 등)는 **데이터 분포에서 자동 결정** (하드코딩 아님)

### Layer 1.5: 혼합 분포 분해 (Is there more than one pattern?) ★ 추가

**목적**: 하나의 시계열(간격, 수량 등)에 **여러 패턴이 섞여 있는지** 감지하고, 각 데이터 포인트에 component 라벨을 부여

**왜 필요한가**: Layer 1의 bimodal score는 "두 덩어리가 있다"만 알려준다. GMM은 **각 데이터 포인트가 어느 component에 속하는지**까지 알려준다.

| 분석 | 무엇을 측정 | 파라미터 결정 방법 |
|------|------------|-------------------|
| **GMM 혼합 분해** | 간격/수량의 혼합 분포를 component별로 분리 | n_components = BIC 최소화 (2~4 탐색) |
| **component 라벨링** | 각 데이터 포인트에 가장 가능한 component 부여 | argmax(posterior) |
| **component별 통계** | 분리된 각 component의 mean, std, count | GMM 결과에서 자동 |
| **조건부 분리 검증** | component 라벨이 외부 조건과 일치하는지 | 다른 변수(시간, 관련 엔티티)와 교차 확인 |

**적용 트리거**: Layer 1에서 다음 조건 중 하나 이상:
- bimodal score > 1.5
- CV > 0.5이면서 count > 10
- 간격의 min과 max 비율 > 5배

**구체적 예시**:

```python
from sklearn.mixture import GaussianMixture

# 대성기업 AL6061 간격
intervals = np.array([15, 14, 1, 14, 0, 13, 15, 4, 15, 17, 3, ...])

# BIC로 최적 component 수 결정
best_k, best_bic = 1, float('inf')
for k in range(1, 5):
    gmm = GaussianMixture(n_components=k, random_state=42)
    gmm.fit(intervals.reshape(-1, 1))
    if gmm.bic(intervals.reshape(-1, 1)) < best_bic:
        best_k, best_bic = k, gmm.bic(intervals.reshape(-1, 1))

# 최적 모델로 라벨링
gmm = GaussianMixture(n_components=best_k, random_state=42)
gmm.fit(intervals.reshape(-1, 1))
labels = gmm.predict(intervals.reshape(-1, 1))

# 결과:
#   Component 0: mean=14.2, std=1.3, count=23 → "격주 패턴"
#   Component 1: mean=1.8,  std=1.5, count=6  → "교차 패턴"
#   → 이제 Component 0만 따로 drift 분석 가능!
```

**출력**:
```json
{
  "대성기업/AL6061": {
    "n_components": 2,
    "bic_improvement": 12.3,
    "components": [
      {"label": 0, "mean": 14.2, "std": 1.3, "count": 23, "proportion": 0.79},
      {"label": 1, "mean": 1.8,  "std": 1.5, "count": 6,  "proportion": 0.21}
    ],
    "per_point_labels": [0, 0, 1, 0, 1, 0, 0, 1, 0, 0, 1, ...]
  }
}
```

**핵심 설계 원칙**:
- GMM은 **비지도 분해** — 도메인 지식 없이 자동으로 component를 찾는다
- 분해 결과의 **해석**(각 component가 뭘 의미하는지)은 Layer 2~4에서 한다
- BIC 기준 1-component가 최적이면 혼합이 아닌 것 → 스킵
- **GMM 외 대안**: KDE peak detection, Hartigan's dip test (bimodality만 확인)

---

### Layer 2: 관계 (Who relates to whom?)

**목적**: 엔티티 간, 변수 간, 품목 간 관계 발견

| 분석 | 무엇을 측정 | 파라미터 결정 방법 |
|------|------------|-------------------|
| **동반 발생** | 같은 윈도우 내 항목 쌍 빈도 | 윈도우 = Layer 1의 평균 간격 × 0.5 |
| **시간 근접성** | 엔티티 A 활동 후 N일 내 B 활동 확률 | lag 범위 = 전체 평균 간격의 0.1~0.5배 |
| **랜덤 기대치 대비 lift** | 실제 동시발생 / 독립 가정 시 기대치 | lift > 1.3 이상만 보고 |
| **수량 상관** | 엔티티 A 수량과 B 수량의 상관 | Pearson/Spearman 자동 선택 |
| **이벤트→행동 시차** | 이벤트 후 행동까지 lag 분포 | 이벤트 테이블이 있을 때만 |

**핵심 설계 원칙**:
- **lag 범위를 데이터에서 자동 결정**하는 것이 가장 중요
  - 고정값(예: 2~4일)을 쓰면 "답을 아는 것"이 됨
  - 대신: `lag_max = max(3, min(14, int(global_mean_interval * 0.5)))`
- **lift로 우연 제거**: 빈도가 높은 엔티티끼리는 우연히 겹칠 확률이 높음. 반드시 기대치 대비 비교

### Layer 2.5: 잔차 기반 계층적 분해 (What's left after the main pattern?) ★ 추가

**목적**: 가장 강한 패턴을 먼저 모델링하고 제거한 뒤, **남은 잔차에서 2차 패턴을 탐색**

**왜 필요한가**: Layer 1~2는 모든 데이터를 한꺼번에 분석한다.
하지만 강한 패턴(격주 주기)이 약한 패턴(drift, 교차)을 가리는 경우,
주 패턴을 빼고 나서야 숨은 패턴이 드러난다.

이것은 시계열 분해(STL: Seasonal-Trend-Loess decomposition)의 아이디어를
**이산 거래 데이터에 적용**한 것이다.

```
STL:  Y = Trend + Seasonal + Residual
Step5: 거래 = 주패턴(격주) + 교차패턴(한진→대성) + drift + noise
```

| 분석 | 무엇을 측정 | 파라미터 결정 방법 |
|------|------------|-------------------|
| **주 패턴 모델링** | 가장 규칙적(CV 최소)인 패턴을 단순 모델로 근사 | 예측값 = last_date + mean_interval |
| **잔차 추출** | 실제 발생일 - 예측 발생일 | 양수 = 늦음, 음수 = 빠름 |
| **잔차 패턴 탐색** | 잔차에서 Layer 1~2를 다시 실행 | 재귀적 분석 (깊이 2까지) |
| **잔여 건 분리** | GMM label이 주 패턴이 아닌 건만 추출 | Layer 1.5의 결과 활용 |
| **분리 후 재분석** | 분리된 건에 대해 독립적으로 간격/drift/관계 분석 | Layer 1~3 재실행 |

**적용 트리거**: Layer 1.5에서 n_components >= 2인 경우

**구체적 예시: P10 drift 발견 경로**:

```
Step 1: Layer 1에서 대성기업 AL6061 발견 — 평균 12.2일, CV=0.45

Step 2: Layer 1.5(GMM)에서 2 component 발견
  → Component A: mean=14.2일 (격주, 23건)
  → Component B: mean=1.8일  (비정상적으로 짧은, 6건)

Step 3: Layer 2.5 — Component A만 추출하여 drift 재분석
  → 전반부(12건): 평균 13.8일
  → 후반부(11건): 평균 18.1일
  → Spearman ρ = 0.52, p = 0.02
  → ✅ drift 감지 성공!

Step 4: Layer 2.5 — Component B (6건) 분석
  → 발생 시점이 한진산업 STS304 발주 후 2~4일
  → Layer 2의 시간 근접성과 교차 확인
  → ✅ P4 교차 패턴 확인
```

**핵심 설계 원칙**:
- **주 패턴을 빼는 것이 핵심** — 강한 신호가 약한 신호를 가린다
- Layer 1.5의 GMM 라벨을 활용하여 **패턴별로 분리한 뒤 독립 분석**
- 분해 깊이는 최대 2 (3단계 이상은 과적합 위험)
- 잔차 자체에 패턴이 없으면 (CV > 1.0) 스킵

---

### Layer 3: 시간 구조 (How does it change?)

**목적**: 시간에 따른 변화, 추세, 주기성, 계절성

| 분석 | 무엇을 측정 | 파라미터 결정 방법 |
|------|------------|-------------------|
| **월별/분기별 집계** | 기간별 건수, 수량, 금액 | datetime에서 자동 추출 |
| **계절 그룹핑** | 봄/여름/가을/겨울 또는 Q1~Q4 | 위도 기반? → 너무 복잡. **3~4개 균등 분할로 고정** |
| **간격 추세** | Spearman ρ (간격 vs 시간) | N등분(3등분) + 단조 상관 |
| **수량 추세** | 시간에 따른 수량 변화 | rolling mean 비교 |
| **구조 변화** | 전반부 vs 후반부 통계 차이 | 자동 2등분/3등분 |

**핵심 설계 원칙**:
- 계절 그룹핑은 **도메인에 따라 다를 수 있음** → 기본값은 달력 분기(Q1~Q4), 사용자가 오버라이드 가능
- 추세 감지는 **Spearman 상관 + 3등분 비교** 두 가지를 동시에 돌림 (하나만으론 놓칠 수 있음)

### Layer 3.5: 다중 조건 연관 (Does A AND B cause C?) ★ 추가

**목적**: **단일 조건(A→C)보다 다중 조건(A∧B→C)에서 유의미하게 확률이 높아지는 관계** 발견

**왜 필요한가**: 현실의 규칙은 단일 조건보다 복합 조건인 경우가 많다.

```
단일 조건:
  P(세진테크 STS316 | 한진산업 발주) = 25%  → 약한 신호
  P(세진테크 STS316 | 봄)           = 20%  → 약한 신호

다중 조건:
  P(세진테크 STS316 | 한진산업 150kg+ AND 봄) = 100%  → 강한 신호!
  → 단일 조건으로는 안 보이지만, 두 조건이 동시에 있을 때만 발동하는 규칙
```

| 분석 | 무엇을 측정 | 파라미터 결정 방법 |
|------|------------|-------------------|
| **조건부 확률 비교** | P(C\|A∧B) vs P(C\|A), P(C\|B) | 두 단일 조건보다 교차 조건이 1.5배+ 높으면 보고 |
| **상호작용 효과** | P(C\|A∧B) - P(C\|A) - P(C\|B) + P(C) | > 0이면 양의 상호작용 (synergy) |
| **조건 변수 자동 생성** | 이벤트, 수량 구간, 시간대, 다른 엔티티 활동 | Layer 1~3의 결과에서 유의미한 변수 추출 |

**조합 폭발 방지**:
- 모든 변수 쌍을 탐색하면 조합이 폭발한다
- **전략**: Layer 2에서 이미 유의미한 단일 조건(lift > 1.3)들만 교차 검증
- 즉, "A→C가 약하고, B→C도 약하지만, A∧B→C가 강한" 경우를 찾는 것

```python
# 조합 폭발 방지: 강한 단일 조건 쌍만 교차
significant_conditions = [c for c in all_conditions if lift(c -> target) > 1.0]

for cond_a, cond_b in combinations(significant_conditions, 2):
    # A AND B 동시 충족 건수가 최소 3건 이상
    ab_count = count(cond_a AND cond_b)
    if ab_count < 3:
        continue

    p_c_given_ab = count(cond_a AND cond_b AND target) / ab_count
    p_c_given_a  = count(cond_a AND target) / count(cond_a)
    p_c_given_b  = count(cond_b AND target) / count(cond_b)

    # 상호작용: 교차 조건이 단독보다 유의미하게 높은 경우만
    if p_c_given_ab > p_c_given_a * 1.5 and p_c_given_ab > p_c_given_b * 1.5:
        report(f"{cond_a} AND {cond_b} → {target}: "
               f"P={p_c_given_ab:.0%} (A만:{p_c_given_a:.0%}, B만:{p_c_given_b:.0%})")
```

**자동 생성되는 조건 변수 예시**:

| 원천 Layer | 조건 변수 | 예시 |
|-----------|----------|------|
| Layer 1 | 수량 구간 (Q75+) | "한진산업 STS304 수량 >= 150kg" |
| Layer 1 | 시간 집중도 | "월 첫째 주" |
| Layer 2 | 다른 엔티티 활동 | "3일 내 한진산업 발주 있음" |
| Layer 3 | 계절 | "봄(3~5월)" |
| Layer 3 | 추세 구간 | "후반부(7월~)" |
| 외부 | 이벤트 | "견적 요청 있음", "공휴일 주" |

**핵심 설계 원칙**:
- **도구가 계산, LLM이 해석** — P(C|A∧B)는 도구가, "왜 이 조합이 의미 있는지"는 LLM이
- 조합 폭발은 **유의미한 단일 조건의 교차만 탐색**하여 방지
- 최소 동시 충족 건수 기준 (default 3건)으로 표본 부족 필터링
- 결과는 "상호작용 점수"(interaction score = P(C|A∧B) - max(P(C|A), P(C|B)))로 정렬

---

### Layer 4: 조건부 패턴 (If A then B?)

**목적**: 단순 상관이 아닌 조건부 관계 발견 + **하위 레이어 결과의 종합 해석**

| 분석 | 무엇을 측정 | 파라미터 결정 방법 |
|------|------------|-------------------|
| **수량 조건부 후속** | "A가 X 이상일 때, B가 이어지는가" | X = Q75 (자동) |
| **이봉 분포 → 원인 분리** | bimodal score 높은 변수 → 두 그룹의 시간/원인 차이 | Layer 1의 bimodal score > 1.5 |
| **예외 조건 탐색** | 규칙적 패턴의 예외 발생 시점 특성 | Layer 1에서 CV < 0.3인 패턴의 이상 간격 |
| **GMM component 해석** | Layer 1.5에서 분리된 component가 뭘 의미하는지 | Layer 2의 관계와 교차 확인 |
| **잔차 패턴 해석** | Layer 2.5에서 발견된 2차 패턴의 원인 추론 | LLM이 도메인 맥락과 결합 |
| **다중 조건 규칙 해석** | Layer 3.5의 A∧B→C에서 왜 이 조합인지 | LLM이 인과 관계 추론 |

**핵심 설계 원칙**:
- Layer 4는 **Layer 0~3.5의 모든 결과를 입력으로 받음** — 독립 실행 불가
- "왜?"를 묻는 레이어이므로, **이 레이어가 LLM이 개입하는 지점**
- 도구(통계)는 Layer 0~3.5에서 충분, Layer 4는 **해석과 가설 생성**
- Layer 1.5/2.5/3.5의 결과를 종합하여 **"이 component는 교차 패턴이고, 이 잔차에 drift가 있다"** 같은 서사를 구성

---

## 3. 도메인별 커스터마이징: 무엇이 고정이고 무엇이 변수인가

### 고정 (도메인 무관, 모든 데이터에 적용)

| 항목 | Layer | 이유 |
|------|-------|------|
| 컬럼 타입 자동 감지 | 0 | 어떤 CSV든 동일 |
| 엔티티별 간격 + CV 계산 | 1 | 반복 행동이 있는 데이터면 항상 유효 |
| **GMM 혼합 분해** | **1.5** | **CV>0.5이면 자동 실행, 도메인 무관** |
| 동반 발생 분석 | 2 | 장바구니, 센서 동시 반응 등 범용 |
| 시간 근접성 + lift | 2 | 기대치 대비 비교는 도메인 무관 |
| **component별 분리 재분석** | **2.5** | **GMM 결과 있으면 자동 실행** |
| 이봉 분포 감지 | 1 | 혼합 패턴의 보편적 징후 |
| Spearman 추세 검정 | 3 | 비모수적이라 분포 가정 없음 |
| 3등분 시간 비교 | 3 | 단순하지만 robust |
| **유의미 단일 조건 교차 검증** | **3.5** | **조합 폭발 없이 다중 조건 탐색** |

### 반고정 (기본값 있지만 도메인이 바꿀 수 있음)

| 항목 | 기본값 | 도메인 오버라이드 예시 |
|------|--------|---------------------|
| groupby 키 | 모든 (엔티티 × 카테고리) 조합 | 제조업: (장비 × 센서), 유통: (고객 × 품목) |
| 시간 윈도우 | 평균 간격 × 0.5 | 금융: 1분, 물류: 1주 |
| 계절 구분 | 달력 분기 (Q1~Q4) | 소매: 블프/크리스마스/신학기 |
| 최소 건수 | 3건 | 희소 데이터: 2건, 대용량: 10건 |
| 이상치 기준 | IQR × 1.5 | 제조업 센서: 3σ |

### 변수 (도메인이 반드시 지정해야 함)

| 항목 | 왜 자동화 불가? | 예시 |
|------|----------------|------|
| 엔티티 컬럼이 뭔지 | "customer"인지 "sensor_id"인지 | 스키마에서 추론 가능하지만 확실하지 않음 |
| 이벤트 테이블 존재 여부 | 별도 테이블 구조를 알아야 함 | 견적요청, 알람로그, 유지보수 기록 |
| 공휴일/비영업일 | 국가/산업별로 다름 | 한국 공휴일, 미국 연방 공휴일 |
| "대형"의 기준 | 업종별 스케일이 다름 | 자재: 150kg, 반도체: 10만개 |

---

## 4. 실전 설계: Level 0 Config 스키마

```python
class Level0Config:
    """Level 0 분석 설정 — 도메인별 최소 설정"""

    # === 필수: 도메인이 지정해야 함 ===
    entity_columns: list[str]      # ["customer"], ["sensor_id", "equipment"]
    category_columns: list[str]    # ["item"], ["alarm_code"]
    datetime_column: str           # "date", "timestamp"
    value_columns: list[str]       # ["quantity"], ["temperature", "pressure"]

    # === 선택: 있으면 더 좋음 ===
    event_table: str | None = None # "events.csv"
    holidays: list[date] | None = None

    # === 반고정: 기본값 있음, 오버라이드 가능 ===
    min_count: int = 3             # 분석 최소 건수
    time_window_factor: float = 0.5  # lag 범위 = 평균간격 × 이 값
    season_groups: dict | None = None  # {"봄": [3,4,5], "여름": [6,7,8], ...}
    outlier_method: str = "iqr"    # "iqr" | "zscore" | "percentile"
```

**이 설정만 주면 Layer 0~3.5이 자동으로 돌아간다.**
Layer 4(조건부 패턴)는 Layer 0~3.5 결과를 LLM에게 넘겨서 LLM이 결정.

> 구현: `phase1_generic.py`가 이 설계를 따른다. Config 대신 CSV 컬럼명 자동 감지 + argparse로 경로 지정.

---

## 5. 다른 도메인 적용 예시

### 예시 A: 풍력 터빈 SCADA (Step 4)

```python
config = Level0Config(
    entity_columns=["turbine_id"],
    category_columns=["sensor_name"],  # 또는 자동: 수치형 컬럼 각각
    datetime_column="timestamp",
    value_columns=["active_power", "wind_speed", "gen_rpm", "pitch_angle"],
    event_table="alarm_log.csv",
    min_count=100,  # 10분 간격이라 데이터 풍부
    time_window_factor=0.1,  # 빠른 샘플링이라 짧은 윈도우
)
```

Level 0~3 자동 분석:
- L0: 센서별 분포, 결측, 범위
- L1: 터빈별 센서 통계 + CV → 어떤 터빈이 불안정한지
- L2: 터빈 간 출력 상관 → fleet 비교 (같은 바람인데 한 터빈만 출력 낮으면?)
- L3: 시간별 출력 추세 → 성능 저하 감지
- L4 (LLM): "T07의 출력이 3월부터 낮아졌는데, 같은 시기 pitch angle도 변했나?" → 인과 추론

### 예시 B: 제조업 설비 센서 (Step 3 MetroPT)

```python
config = Level0Config(
    entity_columns=["equipment_id"],  # 단일 APU라면 없을 수 있음
    category_columns=[],  # 센서별로 자동 분석
    datetime_column="timestamp",
    value_columns=["TP2", "TP3", "H1", "DV_pressure", "Oil_temperature"],
    event_table="maintenance_log.csv",
    min_count=50,
    time_window_factor=0.3,
)
```

### 예시 C: 이커머스 구매 데이터

```python
config = Level0Config(
    entity_columns=["user_id"],
    category_columns=["product_category", "brand"],
    datetime_column="purchase_date",
    value_columns=["amount", "quantity"],
    event_table="page_views.csv",  # 조회 → 구매 선행 지표
    season_groups={"신학기": [2,3], "여름세일": [7,8], "블프": [11], "연말": [12]},
    time_window_factor=0.3,
)
```

### 예시 D: 의료 처방 데이터

```python
config = Level0Config(
    entity_columns=["patient_id"],
    category_columns=["drug_code", "diagnosis_code"],
    datetime_column="prescription_date",
    value_columns=["dosage"],
    event_table="lab_results.csv",  # 검사 결과 → 처방 변경
    min_count=2,  # 환자당 처방 적을 수 있음
)
```

---

## 6. Level 0 vs Level 1의 경계: 어디까지가 도구이고 어디서부터가 LLM인가

```
                도구 영역 (코드로 자동화)                     LLM 영역 (해석 + 가설)
            ┌────────────────────────────────────────┐    ┌──────────────────────────────┐
Layer 0     │ 타입 감지, 기초 통계, 결측               │    │                              │
Layer 1     │ 간격 CV, 시간 집중도, bimodal score      │    │                              │
Layer 1.5 ★ │ GMM 혼합 분해, component 라벨링          │    │                              │
Layer 2     │ 동반 발생, 시간 근접성 + lift             │    │                              │
Layer 2.5 ★ │ 잔차 추출, component별 분리 재분석        │    │                              │
Layer 3     │ 월별 집계, Spearman 추세, 3등분 비교      │    │                              │
Layer 3.5 ★ │ 다중 조건 P(C|A∧B), 상호작용 점수        │    │                              │
            └────────────────────────────────────────┘    │                              │
Layer 4     │                                        │    │ "이 component는 무엇인가?"    │
            │                                        │    │ "잔차 패턴의 원인은?"         │
            │                                        │    │ "A∧B→C의 인과관계?"          │
            │                                        │    │ "drift의 원인은?"             │
            │                                        │    │ "예외 발생 조건?"             │
            └────────────────────────────────────────┘    └──────────────────────────────┘
```

**핵심 원칙**:
- **"무엇을 계산할 것인가"는 고정** (Layer 0~3.5의 분석 항목)
- **"결과를 어떻게 해석할 것인가"가 LLM** (Layer 4)
- Layer 0~3.5은 도메인 무관하게 항상 같은 분석을 돌림
- Layer 4에서 LLM이 "왜?"를 물으면, 필요한 추가 분석을 코드로 돌림 (Level 1 반복)

### ★ 추가된 레이어들의 핵심 역할

```
이전 (v1, synthetic/phase1_v1_analysis.py): 데이터 → 단일 패턴 분석 → LLM 해석
           문제: 혼합 패턴이 서로를 가려서 약한 신호를 놓침 (P10 미감지)

이후 (v2, phase1_generic.py): 데이터 → 단일 패턴 분석 → [분해] → 분리 패턴 분석 → [교차 검증] → LLM 해석
           Layer 1.5: "이 데이터 안에 몇 가지 패턴이 섞여 있는가?" (GMM)
           Layer 2.5: "주 패턴을 빼면 뭐가 남는가?" (cleaned drift)
           Layer 3.5: "단독으로 약한 조건들이 합쳐지면 강해지는가?" (multi-condition)
           → 10/10 패턴 감지 성공 (P10 drift 포함)
```

**데이터 흐름**:
```
Layer 0~1: 전체 데이터 분석
    ↓
Layer 1.5: bimodal/고CV 감지 → GMM 분해
    ↓
Layer 2: 전체 데이터 관계 분석
    ↓
Layer 2.5: GMM component별로 Layer 1~2 재실행
    ↓
Layer 3: 전체 + component별 시간 구조
    ↓
Layer 3.5: 유의미 단일 조건들의 교차 검증
    ↓
Layer 4: LLM이 모든 결과를 종합하여 규칙 생성
```

---

## 7. 이전 실험과의 대조

| 항목 | 이전 phase1_v1_analysis.py | phase1_generic.py (v2) ✅ 구현 완료 |
|------|------------------------|--------------------------------------|
| lag 범위 | **2~4일 고정** (답을 앎) | ✅ 평균간격 × 0.5 자동 |
| 교차 상관 | 한진→대성 특화 | ✅ 모든 쌍 전수 스캔 + lift |
| 이봉 분포 | 없음 | ✅ bimodal score + GMM 분해 |
| 계절 구분 | 봄/여름/가을/겨울 하드코딩 | ✅ 월별/분기별 자동 집계 |
| Drift 감지 | 전반/후반 평균 비교 | ✅ Spearman + 3등분 + cleaned drift |
| 이벤트 시차 | 동아전자 특화 | ✅ 모든 고객×이벤트 전수 |
| **혼합 분포 분해** | **없음** | **✅ GMM + BIC + Ashman D (Layer 1.5)** |
| **잔차 기반 2차 패턴** | **없음** | **✅ component별 분리 재분석 (Layer 2.5)** |
| **다중 조건 연관** | **없음** | **✅ P(C\|A∧B) 교차 검증 (Layer 3.5)** |
| **P10 drift 감지** | **❌ 실패** | **✅ GMM 분리 후 감지 성공** (rho=0.505, p=0.014) |

> 파일 위치: `phase1_generic.py` (루트), 합성 데이터: `synthetic/data/`, 결과: `synthetic/results/`
> 실행: `python phase1_generic.py` (기본값) 또는 `python phase1_generic.py --data-dir online_retail/data`

---

## 8. 결론: Level 0의 4가지 설계 원칙

### 원칙 1: "축"은 고정, "파라미터"는 데이터에서 유도

catch22가 7,700개를 7개 축(분포, 자기상관, 비선형...)으로 정리한 것처럼,
거래 데이터의 Level 0도 **8개 레이어 × 핵심 분석 항목**으로 고정한다.
하지만 lag 범위, 윈도우 크기, GMM component 수 등의 파라미터는 데이터 분포에서 자동 계산한다.

### 원칙 2: 도메인 지식은 "해석"에만, "계산"에는 안 쓴다

Level 0~3.5의 계산은 도메인 무관하게 동일하게 돌린다.
도메인 지식은 Level 4(LLM이 "왜?"를 물을 때)에서만 필요하다.
유일한 예외: Config에서 엔티티/카테고리 컬럼 지정 (이것은 도메인이 아니라 스키마 지식).

### 원칙 3: "빠뜨리지 않는 것"이 "정확한 것"보다 중요

Level 0의 목표는 정밀한 패턴 발견이 아니라 **"놓치지 않는 것"**.
lift가 1.3인 약한 신호도 일단 보고하고, LLM이 Level 4에서 걸러낸다.
Phase 1에서 한진→대성 교차 패턴을 놓친 건, lag 범위를 좁게 잡아서가 아니라
**넓게 잡되 우연을 걸러내는 lift를 안 썼기 때문**.

### 원칙 4: "분해한 뒤 분석"이 "한꺼번에 분석"보다 낫다 ★ 추가

현실 데이터에서 하나의 시계열에는 **여러 원인**이 섞여 있다.
섞인 채로 분석하면 강한 패턴이 약한 패턴을 가린다.

```
❌ 한꺼번에: intervals = [15, 14, 1, 14, 0, 13, 15, 4, 15, 17]
              → 평균 10.8일, CV=0.58 → "불규칙"으로 분류 → drift 놓침

✅ 분해 후:  Component A = [15, 14, 14, 13, 15, 15, 17]  → 평균 14.7일, drift ↑
             Component B = [1, 0, 4]                       → "교차 패턴"으로 분류
```

GMM 분해(Layer 1.5) → component별 재분석(Layer 2.5) → 다중 조건 교차 검증(Layer 3.5)
이 파이프라인이 v2의 핵심 추가사항이며, `phase1_generic.py`에 구현 완료되어
합성 데이터(P1~P10) 10/10 감지에 성공했다. (synthetic_experiment_results.md Exp 4 참조)

---

## 참고 자료

- [hctsa](https://github.com/benfulcher/hctsa) — 7,700+ 시계열 피처 추출
- [catch22](https://github.com/DynamicsAndNeuralSystems/catch22) — 22개 정선 시계열 피처
- [tsfresh](https://github.com/blue-yonder/tsfresh) — 794개 피처, 5개 카테고리
- [DataPrep.EDA](https://arxiv.org/abs/2104.00841) — 타입 기반 자동 EDA
- [YData Profiling](https://github.com/ydataai/ydata-profiling) — 원클릭 데이터 프로파일링
- [EDA Checklist (R. Peng)](https://bookdown.org/rdpeng/exdata/exploratory-data-analysis-checklist.html) — 단변량→이변량 순서
