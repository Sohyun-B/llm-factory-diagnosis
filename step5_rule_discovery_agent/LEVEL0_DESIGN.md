# Level 0 분석 설계 원칙: 도메인 무관 일반화 프레임워크

> 작성일: 2026-03-09
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

## 2. Level 0 일반화 설계: 5-Layer 분석 스택

기존 프레임워크들의 공통점을 추출하면, **데이터 타입과 무관하게 적용 가능한 5개 분석 레이어**가 나온다.

```
Layer 4: 조건부 패턴    ← "A이면 B" 관계
Layer 3: 시간 구조      ← 시간에 따른 변화
Layer 2: 관계           ← 엔티티 간, 변수 간 상관
Layer 1: 엔티티별 프로파일 ← 각 주체의 행동 특성
Layer 0: 스키마 & 분포   ← 데이터 자체의 구조
```

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

### Layer 4: 조건부 패턴 (If A then B?)

**목적**: 단순 상관이 아닌 조건부 관계 발견

| 분석 | 무엇을 측정 | 파라미터 결정 방법 |
|------|------------|-------------------|
| **수량 조건부 후속** | "A가 X 이상일 때, B가 이어지는가" | X = Q75 (자동) |
| **이봉 분포 → 원인 분리** | bimodal score 높은 변수 → 두 그룹의 시간/원인 차이 | Layer 1의 bimodal score > 1.5 |
| **예외 조건 탐색** | 규칙적 패턴의 예외 발생 시점 특성 | Layer 1에서 CV < 0.3인 패턴의 이상 간격 |

**핵심 설계 원칙**:
- Layer 4는 **Layer 1~3의 결과를 입력으로 받음** — 독립 실행 불가
- "왜?"를 묻는 레이어이므로, **이 레이어가 LLM이 개입하는 지점**
- 도구(통계)는 Layer 1~3에서 충분, Layer 4는 **해석과 가설 생성**

---

## 3. 도메인별 커스터마이징: 무엇이 고정이고 무엇이 변수인가

### 고정 (도메인 무관, 모든 데이터에 적용)

| 항목 | 이유 |
|------|------|
| 컬럼 타입 자동 감지 | 어떤 CSV든 동일 |
| 엔티티별 간격 + CV 계산 | 반복 행동이 있는 데이터면 항상 유효 |
| 동반 발생 분석 | 장바구니, 센서 동시 반응 등 범용 |
| 시간 근접성 + lift | 기대치 대비 비교는 도메인 무관 |
| 이봉 분포 감지 | 혼합 패턴의 보편적 징후 |
| Spearman 추세 검정 | 비모수적이라 분포 가정 없음 |
| 3등분 시간 비교 | 단순하지만 robust |

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

**이 설정만 주면 Layer 0~3이 자동으로 돌아간다.**
Layer 4(조건부 패턴)는 Layer 0~3 결과를 LLM에게 넘겨서 LLM이 결정.

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
                도구 영역 (코드로 자동화)                 LLM 영역 (해석 + 가설)
            ┌──────────────────────────────────────┐    ┌──────────────────────────┐
Layer 0     │ 타입 감지, 기초 통계, 결측             │    │                          │
Layer 1     │ 간격 CV, 시간 집중도, bimodal score    │    │                          │
Layer 2     │ 동반 발생, 시간 근접성 + lift           │    │                          │
Layer 3     │ 월별 집계, Spearman 추세, 3등분 비교    │    │                          │
            └──────────────────────────────────────┘    │                          │
Layer 4     │                                      │    │ "bimodal인 이유는?"       │
            │                                      │    │ "lift 높은 쌍의 인과관계?" │
            │                                      │    │ "추세 변화의 원인?"       │
            │                                      │    │ "예외 발생 조건?"         │
            └──────────────────────────────────────┘    └──────────────────────────┘
```

**핵심 원칙**:
- **"무엇을 계산할 것인가"는 고정** (Layer 0~3의 분석 항목)
- **"결과를 어떻게 해석할 것인가"가 LLM** (Layer 4)
- Layer 0~3은 도메인 무관하게 항상 같은 분석을 돌림
- Layer 4에서 LLM이 "왜?"를 물으면, 필요한 추가 분석을 코드로 돌림 (Level 1 반복)

---

## 7. 이전 실험과의 대조

| 항목 | 이전 phase1_analysis.py | 이번 phase1_generic.py | 이상적 Level 0 |
|------|------------------------|----------------------|---------------|
| lag 범위 | **2~4일 고정** (답을 앎) | 평균간격 × 0.5 자동 | ✅ 자동 |
| 교차 상관 | 한진→대성 특화 | 모든 쌍 스캔 | ✅ 전수 |
| 이봉 분포 | 없음 | bimodal score | ✅ 필수 |
| 계절 구분 | 봄/여름/가을/겨울 하드코딩 | 없음 (누락) | 달력 분기 기본값 |
| Drift 감지 | 전반/후반 평균 비교 | Spearman + 3등분 | ✅ 둘 다 |
| 이벤트 시차 | 동아전자 특화 | 모든 고객×이벤트 | ✅ 전수 |

---

## 8. 결론: Level 0의 3가지 설계 원칙

### 원칙 1: "축"은 고정, "파라미터"는 데이터에서 유도

catch22가 7,700개를 7개 축(분포, 자기상관, 비선형...)으로 정리한 것처럼,
거래 데이터의 Level 0도 **5개 레이어 × 핵심 분석 항목**으로 고정한다.
하지만 lag 범위, 윈도우 크기 등의 파라미터는 데이터 분포에서 자동 계산한다.

### 원칙 2: 도메인 지식은 "해석"에만, "계산"에는 안 쓴다

Level 0~3의 계산은 도메인 무관하게 동일하게 돌린다.
도메인 지식은 Level 4(LLM이 "왜?"를 물을 때)에서만 필요하다.
유일한 예외: Config에서 엔티티/카테고리 컬럼 지정 (이것은 도메인이 아니라 스키마 지식).

### 원칙 3: "빠뜨리지 않는 것"이 "정확한 것"보다 중요

Level 0의 목표는 정밀한 패턴 발견이 아니라 **"놓치지 않는 것"**.
lift가 1.3인 약한 신호도 일단 보고하고, LLM이 Level 4에서 걸러낸다.
Phase 1에서 한진→대성 교차 패턴을 놓친 건, lag 범위를 좁게 잡아서가 아니라
**넓게 잡되 우연을 걸러내는 lift를 안 썼기 때문**.

---

## 참고 자료

- [hctsa](https://github.com/benfulcher/hctsa) — 7,700+ 시계열 피처 추출
- [catch22](https://github.com/DynamicsAndNeuralSystems/catch22) — 22개 정선 시계열 피처
- [tsfresh](https://github.com/blue-yonder/tsfresh) — 794개 피처, 5개 카테고리
- [DataPrep.EDA](https://arxiv.org/abs/2104.00841) — 타입 기반 자동 EDA
- [YData Profiling](https://github.com/ydataai/ydata-profiling) — 원클릭 데이터 프로파일링
- [EDA Checklist (R. Peng)](https://bookdown.org/rdpeng/exdata/exploratory-data-analysis-checklist.html) — 단변량→이변량 순서
