# LLM-연결 다단계 분석 아키텍처

> 작성일: 2026-03-11
> 상태: 설계 초안
> 기반: README.md 섹션 6 "5단계 질문 깊이" + Exp 5 결과

---

## 1. 핵심: Phase는 ML, 연결은 LLM

README 섹션 6-2의 원칙을 그대로 따른다:
- **통계 도구가 패턴을 찾고, LLM이 자연어로 해석하는 분업**
- Phase 1이 잡은 기본 패턴 안에서 **더 구체적인 "왜"를 파고드는 것**

현재 파이프라인은 Phase 1 → (고정 프롬프트) → LLM → 검증으로 이어지는데,
이걸 **ML과 LLM이 번갈아가며 점점 깊이 파는 구조**로 바꾼다.

```
Phase 1 (ML)    기초 통계 — 큰 그림
    ↓ 결과
  LLM₁          "뭐가 설명 안 됨?" + "어떤 추가 검사 필요?"
    ↓ 분석 지시
Phase 2 (ML)    LLM₁이 요청한 심화 분석 실행
    ↓ 결과
  LLM₂          가설 생성 — 자유롭고 다양하게
    ↓ 가설 목록
Phase 3 (ML)    가설 검정 실행
    ↓ 결과
  LLM₃          결과 종합 → Rule Card 생성
    ↓
  RAG 저장       생애주기 관리 시작
```

---

## 2. README 5단계 질문 깊이와의 매핑

README 섹션 6-3의 질문 깊이가 Phase에 직접 대응한다:

| Level | 누가 | 하는 것 | → Phase |
|-------|------|---------|---------|
| **0** | 도구 | 기초 통계 ("평균 발주 주기 28일") | Phase 1 |
| **1** | 도구→LLM 정리 | 큰 그림 패턴 ("매달 STS304 100kg") | Phase 1 → LLM₁ |
| **2** | 도구+LLM | 큰 그림 안의 "왜" ("첫째 주가 80%인 이유") | LLM₁ → Phase 2 → LLM₂ |
| **3** | 도구+LLM | 교차 패턴 ("한진 후 3일 내 대성 78%") | LLM₂ → Phase 3 |
| **4** | LLM | 맥락 추론 ("원청/하청 관계 가능성") | LLM₃ |

**Level 0~1은 Phase 1(고정 ML)이 자동으로 커버한다.**
**Level 2~4는 LLM이 방향을 잡고, ML이 검증하고, LLM이 해석하는 루프로 커버한다.**

---

## 3. 각 단계 상세

### Phase 1: 큰 그림 잡기 (ML, 고정)

**기존 `phase1_generic.py` 그대로.** 8-Layer 스택, 파라미터 고정.

```
입력: orders.csv, events.csv
출력: level0_results.json

Layer 0   : 스키마, 분포
Layer 1   : 엔티티별 프로파일 (간격, CV, 요일/주차 집중)
Layer 1.5 : GMM 혼합 분포 분해
Layer 2   : 관계 (동반 발주, 고객 간 근접)
Layer 2.5 : Component 재분석 (cleaned drift, 선행자)
Layer 3   : 시간 구조 (월별 추세)
Layer 3.5 : 다중 조건 연관
Layer 4   : 이벤트→행동 시차
```

Phase 1은 **넓고 얕다**. 모든 조합을 기본 임계값으로 훑는다.

---

### LLM₁: 이상 식별 + 추가 분석 방향 결정

LLM₁은 Phase 1 결과를 읽고 두 가지를 한다:

#### (a) 기본 패턴 정리

README 6-4의 "[큰 그림 — 이미 알려진 패턴]" 부분:

```
Phase 1 결과를 보니:
- 한진산업: STS304, 월 1회, 평균 100kg, CV=0.20 (매우 규칙적)
- 대성기업: AL6061, 격주, CV=0.58 (애매함)
- 세진테크: STS304, 분기, CV=0.05 (극도로 규칙적)
- 봄철 수량 증가 신호 있음
```

#### (b) "설명 안 되는 것" 식별 + Phase 2 지시

README 6-4의 "[큰 그림 안에서 도구가 발견한 세부 단서]"를 만들기 위해,
**Phase 2에서 어떤 추가 분석을 해야 하는지** 결정:

```
의문 1: 대성기업 AL6061의 CV=0.58 — 규칙적도 불규칙적도 아님
  → Phase 1의 GMM이 2-component로 분리함 (14.2일 83%, 2.8일 17%)
  → 17%의 정체가 뭔지 모름
  → Phase 2 지시: "대성기업 AL6061의 짧은 간격(2~4일) 주문 5건의
    직전에 어떤 고객이 주문했는지 확인해라"

의문 2: 한진산업→대성기업 proximity lift=1.8인데 follow_count=4밖에 안 됨
  → 통계적으로 약함. 실제인지 우연인지 구분 필요
  → Phase 2 지시: "한진산업 STS304 주문 날짜와 대성기업 AL6061 주문 날짜를
    1~7일 lag로 상세 비교해라. 품목 필터링 포함"

의문 3: 명성산업 PIPE_SCH40 간격에 이상한 패턴이 보임
  → Phase 1에선 "불규칙"으로 분류됐지만 뭔가 있을 수도
  → Phase 2 지시: "명성산업의 PIPE_SCH40과 CARBON_STEEL 주문일을
    나란히 놓고 교대 패턴이 있는지 확인해라"
```

**LLM₁의 출력: Phase 2에 대한 분석 요청 목록 (JSON)**

```json
{
  "phase2_requests": [
    {
      "id": "INV-001",
      "question": "대성기업 AL6061 짧은 간격(2~4일)의 원인",
      "analysis_type": "precursor_check",
      "params": {
        "customer": "대성기업", "item": "AL6061",
        "target_intervals": [0, 1, 2, 3, 4],
        "look_back_days": 7
      }
    },
    {
      "id": "INV-002",
      "question": "한진산업→대성기업 교차 발주 실제 여부",
      "analysis_type": "cross_customer_detail",
      "params": {
        "from_customer": "한진산업", "from_item": "STS304",
        "to_customer": "대성기업", "to_item": "AL6061",
        "lag_min": 1, "lag_max": 7
      }
    },
    {
      "id": "INV-003",
      "question": "명성산업 품목 교대 패턴 여부",
      "analysis_type": "alternation_check",
      "params": {
        "customer": "명성산업",
        "items": ["PIPE_SCH40", "CARBON_STEEL"]
      }
    }
  ]
}
```

---

### Phase 2: 심화 분석 (ML, LLM₁의 지시에 따라 실행)

Phase 2는 **Phase 1과 다른 ML 스크립트**다.
Phase 1이 "모든 조합을 기본값으로 훑는" 것이라면,
Phase 2는 **LLM₁이 지목한 특정 조합을, 지정한 방식으로 깊이 파는** 것.

```
입력: orders.csv + LLM₁의 분석 요청 JSON
출력: phase2_results.json (요청별 상세 결과)
```

#### Phase 2가 실행하는 분석 유형들

README 6-5의 "도메인별 질문 템플릿"이 곧 Phase 2의 분석 유형이다:

| 분석 유형 | README 템플릿 | 하는 것 |
|-----------|--------------|---------|
| `precursor_check` | — | 특정 주문 직전에 다른 고객 주문이 있었는지 조회 |
| `cross_customer_detail` | "교차 패턴" | 두 고객 간 주문일 상세 매칭 (날짜별, 품목별) |
| `alternation_check` | — | 한 고객의 두 품목이 교대로 주문되는지 확인 |
| `quantity_anomaly` | "수량 이상" | 평소 대비 ±50% 이상인 주문들의 공통점 |
| `event_lead` | "선행 지표" | 이벤트 → 주문 전환의 날짜별 상세 |
| `seasonal_shift` | "계절 전환" | YoY 비교로 패턴 변화 감지 |
| `time_window_detail` | — | 특정 기간의 raw 주문 목록 + 통계 |
| `conditional_trigger` | — | "A 조건일 때 B가 발생하는가" 검정 |
| `drift_detail` | — | 교란 요인 제거 후 drift 재검정 |
| `holiday_effect` | — | 공휴일 전후 주문 시점 이동 확인 |

각 분석 유형은 **독립된 함수**로 구현하되,
Phase 2 스크립트가 LLM₁의 요청 JSON을 읽어서 해당 함수를 순서대로 실행한다.

#### Phase 2 출력 예시

```json
{
  "INV-001": {
    "question": "대성기업 AL6061 짧은 간격의 원인",
    "result": {
      "short_intervals": [
        {"date": "2025-06-10", "interval": 2, "precursor": "한진산업/STS304 (2025-06-08, 2일 전)"},
        {"date": "2025-08-06", "interval": 3, "precursor": "한진산업/STS304 (2025-08-04, 2일 전)"},
        {"date": "2025-10-01", "interval": 1, "precursor": "한진산업/STS304 (2025-09-29, 2일 전)"}
      ],
      "precursor_hit_rate": 0.60,
      "summary": "짧은 간격 5건 중 3건에서 한진산업/STS304가 1~3일 전에 선행"
    }
  },
  "INV-002": {
    "question": "한진산업→대성기업 교차 발주 실제 여부",
    "result": {
      "pairs": [
        {"hangjin_date": "2025-06-08", "daesung_date": "2025-06-10", "lag": 2},
        {"hangjin_date": "2025-08-04", "daesung_date": "2025-08-06", "lag": 2},
        ...
      ],
      "hit_count": 10, "total": 12,
      "probability": 0.83, "expected_random": 0.30, "lift": 2.8
    }
  }
}
```

---

### LLM₂: 가설 생성

LLM₂는 Phase 1 + Phase 2 결과를 모두 보고, **자유롭게 가설을 세운다**.

이것이 README 6-2의 핵심:
> "Phase 1이 잡은 기본 패턴 안에서 더 구체적인 '왜'를 파고드는 것"

```
Phase 2 결과를 보니:

INV-001 결과: 대성기업 짧은 간격 5건 중 3건에 한진산업이 선행
INV-002 결과: 한진산업→대성기업 lag 2~3일, 확률 83%, lift 2.8

가설 A: 한진산업과 대성기업은 같은 프로젝트의 원청/하청이다.
        한진산업이 STS304를 먼저 발주하면 대성기업이 AL6061로 후속한다.
        → 검정 방법: 한진산업 발주 날짜 기준으로 대성기업 후속 발주를
          "있었다/없었다"로 이진 분류. 정확도 측정.

가설 B: 대성기업의 짧은 간격은 교차 발주가 아니라 긴급 발주일 수 있다.
        수량이 평소보다 적다면 긴급 보충일 가능성.
        → 검정 방법: 짧은 간격 주문의 수량 vs 정상 간격 주문의 수량 비교.

가설 C: 한진산업 대형 발주(150kg+) 후에만 대성기업이 따라온다.
        일반 발주에는 반응하지 않는다면 조건부 트리거.
        → 검정 방법: 한진산업 발주를 수량 기준으로 분류,
          각 그룹별 대성기업 후속 확률 비교.

가설 D: 대성기업 AL6061 간격이 시간이 갈수록 늘고 있다 (drift).
        교차 발주를 제거하면 drift가 더 뚜렷해질 것.
        → 검정 방법: 교차 발주 제거 후 Spearman rho 재계산.

가설 E: 특정 계절에만 교차 패턴이 활성화된다.
        → 검정 방법: 분기별로 교차 확률 분리 비교.
```

**LLM₂의 출력: 가설 목록 + 각 가설의 검정 방법 (JSON)**

```json
{
  "hypotheses": [
    {
      "id": "H-A",
      "statement": "한진산업→대성기업 원청/하청 교차 발주",
      "test_type": "cross_customer_binary",
      "params": {
        "trigger_customer": "한진산업", "trigger_item": "STS304",
        "effect_customer": "대성기업", "effect_item": "AL6061",
        "lag_window": [1, 5]
      },
      "success_criteria": "hit_rate > 0.70"
    },
    {
      "id": "H-B",
      "statement": "짧은 간격 = 긴급 보충 (수량 적음)",
      "test_type": "quantity_comparison",
      "params": {
        "customer": "대성기업", "item": "AL6061",
        "group_a": "short_interval (<=4일)",
        "group_b": "normal_interval (>4일)"
      },
      "success_criteria": "mean_a < mean_b * 0.7"
    },
    {
      "id": "H-C",
      "statement": "한진산업 대형 발주(150kg+)에만 대성기업 반응",
      "test_type": "conditional_trigger",
      "params": {
        "trigger_customer": "한진산업", "trigger_item": "STS304",
        "trigger_condition": "quantity >= 150",
        "effect_customer": "대성기업", "effect_item": "AL6061",
        "time_window": 7
      },
      "success_criteria": "conditional_rate > baseline_rate * 1.5"
    },
    {
      "id": "H-D",
      "statement": "교차 발주 제거 후 drift 뚜렷해짐",
      "test_type": "drift_after_cleaning",
      "params": {
        "customer": "대성기업", "item": "AL6061",
        "remove_condition": "precursor 한진산업 within 5 days"
      },
      "success_criteria": "abs(rho) > 0.3 AND p < 0.05"
    },
    {
      "id": "H-E",
      "statement": "교차 패턴이 계절 한정",
      "test_type": "seasonal_split",
      "params": {
        "from_customer": "한진산업", "to_customer": "대성기업",
        "split_by": "quarter"
      },
      "success_criteria": "max_quarter_rate > 2 * min_quarter_rate"
    }
  ]
}
```

---

### Phase 3: 가설 검정 (ML, LLM₂의 가설을 테스트)

Phase 3은 **LLM₂가 설계한 가설을 하나씩 실행하는 ML 스크립트**.
Phase 2와 마찬가지로 분석 유형별 함수가 있고, 가설 JSON을 읽어서 실행한다.

```
입력: orders.csv + LLM₂의 가설 JSON
출력: phase3_results.json (가설별 검정 결과)
```

#### Phase 3 출력 예시

```json
{
  "H-A": {
    "statement": "한진산업→대성기업 원청/하청 교차 발주",
    "result": "confirmed",
    "evidence": {
      "hit_rate": 0.83, "total": 12, "hits": 10,
      "expected_random": 0.30, "lift": 2.8, "p_value": 0.001
    }
  },
  "H-B": {
    "statement": "짧은 간격 = 긴급 보충 (수량 적음)",
    "result": "rejected",
    "evidence": {
      "short_interval_mean_qty": 48.2,
      "normal_interval_mean_qty": 51.5,
      "ratio": 0.94,
      "reason": "수량 차이 무의미 (6% 차이)"
    }
  },
  "H-C": {
    "statement": "한진산업 대형 발주에만 대성기업 반응",
    "result": "partially_confirmed",
    "evidence": {
      "large_order_follow_rate": 1.00,
      "normal_order_follow_rate": 0.75,
      "difference": 0.25,
      "note": "대형 발주 표본 3건으로 통계적 유의성 부족, 방향은 일치"
    }
  },
  "H-D": {
    "statement": "교차 발주 제거 후 drift",
    "result": "confirmed",
    "evidence": {
      "before_cleaning": {"rho": 0.28, "p": 0.12},
      "after_cleaning": {"rho": 0.505, "p": 0.014},
      "removed_orders": 6, "remaining": 24
    }
  },
  "H-E": {
    "statement": "교차 패턴이 계절 한정",
    "result": "rejected",
    "evidence": {
      "q1_rate": 0.80, "q2_rate": 0.85, "q3_rate": 0.83, "q4_rate": 0.82,
      "reason": "분기별 차이 없음, 연중 지속"
    }
  }
}
```

---

### LLM₃: 결과 종합 → Rule Card 생성

LLM₃은 Phase 1 + Phase 2 + Phase 3 **전체 결과를 보고 최종 해석**한다.
이것이 README Level 4 — **맥락 추론**.

```
결과 종합:

✅ H-A 확인: 한진산업→대성기업 교차 발주, 83%, lift 2.8
❌ H-B 기각: 짧은 간격이 긴급 보충은 아님 (수량 차이 없음)
△ H-C 부분 확인: 대형 발주 시 반응률 더 높으나 표본 부족
✅ H-D 확인: 교차 제거 후 drift 뚜렷 (rho=0.505, p=0.014)
❌ H-E 기각: 계절 무관, 연중 지속

종합 해석:
1. 대성기업 AL6061에는 두 가지 패턴이 섞여있다:
   - 주 패턴: 격주(14일) 정기 발주
   - 부 패턴: 한진산업 발주 후 2~3일 내 추가 발주 (교차)
2. 교차 패턴을 제거하면 주 패턴의 간격이 늘어나는 drift가 보인다
3. 한진산업 대형 발주가 트리거인 가능성은 있으나 표본 부족

→ Rule Card 3장 생성:
  RULE-003: 대성기업 격주 AL6061 (주 패턴)
  RULE-004: 한진산업→대성기업 교차 발주 (교차 패턴)
  RULE-013: 대성기업 AL6061 간격 drift (추세)
```

LLM₃가 생성하는 Rule Card는 README 섹션 5, 8의 포맷을 따른다.

---

## 4. 전체 데이터 흐름

```
orders.csv ──→ phase1_generic.py ──→ level0_results.json
                                          │
                                          ▼
                                     ┌─────────┐
                                     │  LLM₁   │  "뭐가 이상한지" + "뭘 더 볼지"
                                     └────┬────┘
                                          │ phase2_requests.json
                                          ▼
orders.csv ──→ phase2_investigate.py ──→ phase2_results.json
                                          │
                                          ▼
                                     ┌─────────┐
                                     │  LLM₂   │  가설 생성 (자유롭게, 다양하게)
                                     └────┬────┘
                                          │ hypotheses.json
                                          ▼
orders.csv ──→ phase3_test.py ──→ phase3_results.json
                                          │
                                          ▼
                                     ┌─────────┐
                                     │  LLM₃   │  결과 종합 + Rule Card 생성
                                     └────┬────┘
                                          │
                                          ▼
                                    rule_cards/*.json
                                          │
                                          ▼
                                    RAG 저장 + 생애주기 관리
```

---

## 5. 각 컴포넌트 역할 정리

| 컴포넌트 | 유형 | 입력 | 출력 | 핵심 역할 |
|----------|------|------|------|-----------|
| `phase1_generic.py` | ML (고정) | orders.csv | level0_results.json | 넓고 얕은 기본 스캔 |
| LLM₁ | LLM | level0_results.json | phase2_requests.json | 이상 식별 + 방향 결정 |
| `phase2_investigate.py` | ML (가변) | orders.csv + requests | phase2_results.json | LLM₁이 지목한 곳을 깊이 파기 |
| LLM₂ | LLM | phase1 + phase2 결과 | hypotheses.json | 자유로운 가설 생성 |
| `phase3_test.py` | ML (가변) | orders.csv + hypotheses | phase3_results.json | 가설 검정 |
| LLM₃ | LLM | 전체 결과 | rule_cards/*.json | 종합 해석 + Rule Card |

**"가변"의 의미**: 스크립트 자체는 고정이지만, **무엇을 분석할지(파라미터)**는 LLM이 결정한다.

---

## 6. Phase 2 분석 유형 카탈로그

README 6-5의 "도메인별 질문 템플릿"을 Phase 2 함수로 구현한다:

| 분석 유형 | README 원문 | Phase 2 함수 |
|-----------|------------|-------------|
| 교차 패턴 | "고객 A 발주 후 N일 이내 고객 B" | `cross_customer_detail()` |
| 수량 이상 | "평소 대비 ±50% 이상인 건의 공통점" | `quantity_anomaly()` |
| 선행 지표 | "발주 전 N일 내 가격문의/견적요청" | `event_lead_detail()` |
| 계절 전환 | "작년 같은 시기 대비 달라진 고객" | `seasonal_shift()` |
| 선행자 확인 | — | `precursor_check()` |
| 교대 패턴 | — | `alternation_check()` |
| 시간 상세 | — | `time_window_detail()` |
| 조건부 트리거 | — | `conditional_trigger()` |
| drift 상세 | — | `drift_detail()` |
| 공휴일 효과 | — | `holiday_effect()` |

## 7. Phase 3 가설 검정 유형 카탈로그

| 검정 유형 | 하는 것 |
|-----------|---------|
| `cross_customer_binary` | A 발주 후 B 발주 있었다/없었다 이진 검정 |
| `quantity_comparison` | 두 그룹 간 수량 비교 (t-test 또는 Mann-Whitney) |
| `conditional_trigger` | 조건 충족 시 vs 미충족 시 후속 확률 비교 |
| `drift_after_cleaning` | 교란 제거 후 Spearman 재검정 |
| `seasonal_split` | 분기/월별로 분리하여 패턴 강도 비교 |
| `periodicity_test` | 특정 주기 가설의 정확도 측정 |
| `association_strength` | 두 변수 간 연관 강도 (lift, chi-square) |

---

## 8. Rule Card와 생애주기

README 섹션 4, 5, 7, 8을 그대로 따른다.

LLM₃가 생성한 Rule Card는:
- **섹션 5**의 데이터 구조 (id, content, verification, accuracy_history, status)
- **섹션 7**의 건강 관리 (Warning → Review → Retire → Revive)
- **섹션 8**의 자연어 확신도 ("거의 확실하다" / "가능성이 높은 편이다")

```
rule_cards/
├── active/        # 검증된 규칙
├── candidate/     # 새로 발견, 검증 대기
├── warning/       # 정확도 하락 중
├── archived/      # 퇴역 (계절 부활 가능)
└── index.json     # 전체 메타데이터
```

---

## 9. 실행 방식

### 옵션 A: 오케스트레이터 스크립트

```bash
python orchestrator.py --data-dir synthetic/data

# 내부적으로:
# 1. phase1_generic.py 실행 → level0_results.json
# 2. LLM₁ 호출 (API) → phase2_requests.json
# 3. phase2_investigate.py 실행 → phase2_results.json
# 4. LLM₂ 호출 (API) → hypotheses.json
# 5. phase3_test.py 실행 → phase3_results.json
# 6. LLM₃ 호출 (API) → rule_cards/*.json
```

### 옵션 B: Claude Code 서브에이전트 체인

각 LLM 단계를 서브에이전트로 실행. 서브에이전트가 ML 스크립트를
Bash 도구로 호출하고 결과를 읽어서 다음 판단을 내림.

### 결정 필요

| # | 질문 | 선택지 |
|---|------|--------|
| 1 | LLM 호출 방식 | Claude API tool-use vs Claude Code 서브에이전트 |
| 2 | LLM₁~₃을 같은 LLM 세션으로? | 단일 컨텍스트(누적) vs 독립 호출(각각 새로) |
| 3 | Phase 2/3 함수를 하나의 파일에? | `ml_tools.py` 단일 vs `phase2_investigate.py` + `phase3_test.py` 분리 |

---

## 10. 구현 순서

1. **Phase 2 ML 함수** (`phase2_investigate.py`)
   - `cross_customer_detail`, `precursor_check`, `quantity_anomaly` 등
   - LLM₁의 요청 JSON을 읽어서 해당 함수 실행

2. **Phase 3 ML 함수** (`phase3_test.py` 리팩터링)
   - 기존 P1~P10 대조 검증 → 범용 가설 검정으로 확장
   - LLM₂의 가설 JSON을 읽어서 해당 검정 실행

3. **LLM 프롬프트 3종** (LLM₁, LLM₂, LLM₃)
   - 각 단계별 시스템 프롬프트 + 입출력 JSON 스펙

4. **오케스트레이터** (`orchestrator.py`)
   - Phase 1 → LLM₁ → Phase 2 → LLM₂ → Phase 3 → LLM₃ 체인 실행

5. **Rule Card 관리** (`rule_card_manager.py`)
   - CRUD + 생애주기 상태 전이 + RAG 인덱스
