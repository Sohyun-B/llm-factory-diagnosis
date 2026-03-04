# FJSP/JSP 환경에서의 LLM 활용 디스패칭/스케줄링 연구 서베이

> 조사일: 2025-03-04
> 대상 논문: 8편 (2024~2026)
> 분류: 디스패칭 룰 자동 생성 / 피드백 루프 / LLM 파인튜닝

---

## 목차

1. [개요 및 분류 체계](#1-개요-및-분류-체계)
2. [논문별 상세 분석](#2-논문별-상세-분석)
   - 2.1 SeEvo — 자기진화 디스패칭 룰 생성
   - 2.2 ReflecSched — 계층적 반성 기반 DFJSP
   - 2.3 LLM4EO — 진화 연산자 메타진화
   - 2.4 LLM4DRD — 이중 전문가 디스패칭 룰 설계
   - 2.5 MAEF — 다중 에이전트 진화 프레임워크
   - 2.6 Starjob — LLM 파인튜닝용 데이터셋
   - 2.7 HFLLMDRL — 인간 피드백 기반 DRL 보상 설계
   - 2.8 HRC-LLM — 인간-로봇 협업 제조 스케줄링
3. [논문 간 비교표](#3-논문-간-비교표)
4. [공통 패턴 및 핵심 인사이트](#4-공통-패턴-및-핵심-인사이트)

---

## 1. 개요 및 분류 체계

FJSP(Flexible Job Shop Scheduling Problem) 환경에서 LLM을 활용하는 연구는 크게 **3가지 패러다임**으로 나뉜다:

| 패러다임 | 설명 | 해당 논문 |
|----------|------|-----------|
| **A. 디스패칭 룰 자동 생성** | LLM이 진화 알고리즘과 결합하여 HDR(Heuristic Dispatching Rule)을 Python 코드로 자동 생성·진화 | SeEvo, LLM4DRD, LLM4EO, HRC-LLM |
| **B. 피드백 루프 (결과→수정)** | LLM이 스케줄링 결과를 분석하고 전략적 피드백을 제공하여 의사결정을 반복 개선 | ReflecSched, MAEF |
| **C. LLM 직접 학습/파인튜닝** | 스케줄링 데이터로 LLM을 파인튜닝하거나, LLM이 DRL의 보상 함수를 설계 | Starjob, HFLLMDRL |

---

## 2. 논문별 상세 분석

---

### 2.1 SeEvo — Population Self-Evolution for DJSSP

| 항목 | 내용 |
|------|------|
| **논문** | Automatic Programming via LLMs with Population Self-Evolution for Dynamic Job Shop Scheduling Problem |
| **저자** | Jin Huang, Xinyu Li, Liang Gao, Qihao Liu, Yue Teng (화중과기대) |
| **연도** | 2024.10 (arXiv: 2410.22657) |
| **문제** | Dynamic JSP (DJSSP) — 랜덤 주문 도착 하에서 makespan 최소화 |

#### LLM 활용 방식

```
┌─────────────────────────────────────────────────────────┐
│                    SeEvo 진화 루프                        │
│                                                         │
│  ┌──────────┐    반성(Reflection)    ┌──────────────┐   │
│  │ Population├──────────────────────►│  GPT-4 LLM   │   │
│  │ (Python   │                       │              │   │
│  │  HDR 코드)│◄──────────────────────┤  코드 생성    │   │
│  └─────┬─────┘    새 HDR 코드        └──────────────┘   │
│        │                                                │
│        ▼                                                │
│  ┌──────────┐                                           │
│  │ DJSSP    │  fitness 평가 (평균 makespan)              │
│  │ Simulator │                                          │
│  └──────────┘                                           │
└─────────────────────────────────────────────────────────┘
```

**핵심: 3단계 자기반성 메커니즘**

1. **Individual Co-Evolution Reflection (개체 간 비교 반성)**
   - 인구 내 두 개체(HDR)를 선택, 성능 비교
   - LLM이 "왜 A가 B보다 좋은가" 분석 → 개선 제안 생성
   - 이 제안을 기반으로 LLM이 crossover 수행 (의미 수준의 코드 합성)

2. **Individual Self-Evolution Reflection (개체 자기 반성)**
   - 한 개체의 **시간 경과에 따른 성능 변화 이력** 추적
   - LLM이 "이전 버전 대비 무엇이 좋아졌고/나빠졌는가" 분석
   - 자기 개선 방향 도출 → **SeEvo만의 고유 메커니즘** (ReEvo에는 없음)

3. **Collective Evolution Reflection (집단 반성)**
   - 누적된 모든 co-evolution 반성을 종합
   - 전체 population에서 잘 작동하는 전략 패턴을 일반화
   - mutation 가이던스로 활용 (장기 기억 역할)

**생성되는 디스패칭 룰의 형태:**
- 완전한 Python 함수 (processing time, remaining ops, queue length 등을 입력으로 priority score 반환)
- 단순 SPT/FIFO에서 시작하여, 진화를 거치며 복합적인 다인자 우선순위 함수로 발전

**실험 결과:**
- GP, GEP, end-to-end DRL, 10개 이상의 전통 HDR, ReEvo 프레임워크 모두 능가
- 특히 **unseen/dynamic 시나리오에서 일반화 성능 우수**
- 50 jobs × 15 machines에서 온라인 적용 시 30초 내 솔루션 도출

**한계:** LLM API 비용 높음, 단일 목적함수(makespan), 단일 동적 이벤트(주문 도착)만 고려

---

### 2.2 ReflecSched — Hierarchical Reflection for DFJSP

| 항목 | 내용 |
|------|------|
| **논문** | ReflecSched: Solving Dynamic Flexible Job-Shop Scheduling via LLM-Powered Hierarchical Reflection |
| **저자** | Shijie Cao, Yuan Yuan (베이항대) |
| **연도** | 2025.08 (arXiv: 2508.01724, v3: 2026.01) |
| **문제** | Dynamic FJSP (DFJSP) — 주문 도착, 기계 고장, 주문 취소, 긴급 주문 |

#### LLM 활용 방식

```
┌───────────────────────────────────────────────────────────────┐
│                   ReflecSched 아키텍처                         │
│                                                               │
│  ┌─────────────────────────────────────┐                      │
│  │   Module 1: Hierarchical Reflection │                      │
│  │                                     │                      │
│  │  상위 레벨: 장기 horizon 시뮬레이션  │                      │
│  │    └─ 병목 식별, 전체 흐름 분석      │                      │
│  │  하위 레벨: 단기 horizon 시뮬레이션  │                      │
│  │    └─ 즉각적 전술 가이던스           │                      │
│  │                                     │                      │
│  │  PDR Pool (SPT,LPT,EDD,...) ──►시뮬레이션──►LLM 분석      │
│  │                                     │                      │
│  │  출력: "Strategic Experience" (자연어)│                      │
│  └────────────────┬────────────────────┘                      │
│                   │                                           │
│                   ▼                                           │
│  ┌─────────────────────────────────────┐                      │
│  │  Module 2: Experience-Guided        │                      │
│  │            Decision-Making          │                      │
│  │                                     │                      │
│  │  Strategic Experience + 현재 상태   │                      │
│  │  → LLM이 최종 스케줄링 액션 선택    │                      │
│  └─────────────────────────────────────┘                      │
└───────────────────────────────────────────────────────────────┘
```

**핵심: LLM을 "전략적 분석가"로 포지셔닝**

직접 LLM을 스케줄러로 사용하면 3가지 함정에 빠짐:
1. **Long-context paradox**: 핵심 데이터가 활용되지 못함
2. **Heuristic underutilization**: 전문가 휴리스틱을 제대로 따르지 못함
3. **Myopic decision-making**: 근시안적 의사결정

ReflecSched의 해결:
- 휴리스틱은 **프로그래밍적으로 실행** (LLM이 직접 따를 필요 없음)
- LLM은 결과를 **분석하고 전략적 인사이트를 추출**하는 역할
- 다중 시간 horizon으로 **근시안적 의사결정 방지**

**Simulate → Reflect → Refine 사이클:**
1. PDR 풀에서 여러 규칙 샘플링 → 시뮬레이터에서 rollout 실행
2. LLM이 최선/최악 rollout 간 **대조 분석** 수행
3. 인사이트를 "Strategic Experience"라는 **간결한 자연어 요약**으로 압축
4. 이 경험을 최종 의사결정 프롬프트에 주입

**실험 결과:**
- 벤치마크: GEN-Bench, MK-Bench (Brandimarte 변환), JMS-Bench (반도체)
- 직접 LLM 대비 **71.35% Win Rate**, RPD 2.755% 감소
- IDDQN, HMPSAC 등 학습 기반 방법 대비 유의미한 우위
- **15.1% 더 토큰 효율적** (Normal-scale)
- Zero-shot (학습 불필요) → 환경 변화 시 재학습 비용 없음

**한계:** 결정론적 시뮬레이터 필요, Strategic Experience가 일시적(축적 불가), LLM 품질 의존

---

### 2.3 LLM4EO — Operator-Level Meta-Evolution for FJSP

| 항목 | 내용 |
|------|------|
| **논문** | Online Operator Design in Evolutionary Optimization for FJSP via Large Language Models |
| **저자** | Rongjie Liao, Junhao Qiu, Xin Chen, Xiaoping Li (광동공업대/동남대) |
| **연도** | 2025.11 (arXiv: 2511.16485, v3: 2026.01) |
| **문제** | FJSP — 기계 할당 + 작업 순서 결정, makespan 최소화 |

#### LLM 활용 방식

```
┌──────────────────────────────────────────────────────────┐
│              LLM4EO: 메타 수준 연산자 진화                 │
│                                                          │
│  솔루션 Population (100개)                                │
│     ↕ crossover, mutation (연산자 적용)                   │
│                                                          │
│  연산자 Population (3개)                                  │
│     │                                                    │
│     │ 정체 감지 시                                        │
│     ▼                                                    │
│  ┌────────────────────────────────────────┐              │
│  │  Perception: 진화 상태 수집             │              │
│  │  - 연산자 적합도 (f_op = n_s/n_v)      │              │
│  │  - 솔루션 population 통계              │              │
│  │  - 다양성 지표, 수렴 추이              │              │
│  └──────────────┬─────────────────────────┘              │
│                 ▼                                         │
│  ┌────────────────────────────────────────┐              │
│  │  Analysis: LLM이 진단                   │              │
│  │  - 왜 정체되었는가?                     │              │
│  │  - 어떤 연산자가 어떻게 부족한가?       │              │
│  │  - 유전자 선택 전략의 문제점            │              │
│  └──────────────┬─────────────────────────┘              │
│                 ▼                                         │
│  ┌────────────────────────────────────────┐              │
│  │  Refinement: LLM이 새 연산자 생성       │              │
│  │  - 유전자 선택 휴리스틱 코드 수정       │              │
│  │  - 최악 연산자를 교체                   │              │
│  └────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────┘
```

**핵심: LLM이 솔루션이 아닌 "연산자"를 진화시킴**

- LLM은 스케줄링 솔루션을 직접 보지 않음
- 대신 **진화 알고리즘의 crossover/mutation 연산자 자체**를 설계하고 개선
- Gene selection 함수 `g(t, Q, β) → 선택 확률`을 LLM이 코드로 생성
- 4가지 neighborhood move: OSV Crossover(POX), OSV Mutation(PPS), MAV Mutation, Critical Path Swapping

**Perception → Analysis → Refinement 폐루프:**
- 솔루션 population이 정체되면 트리거
- LLM이 진화 역학을 텍스트로 "인식"하고, "왜 막혔는지" 진단 후, 개선된 연산자 생성
- 솔루션과 연산자가 **공진화** (co-evolution)

**실험 결과:**
- Brandimarte(Mk01-10), Hurink(rdata), Lawrence(LA06-15) 벤치마크
- 10개 인스턴스 중 7개에서 최저 BM 달성
- Lawrence 인스턴스에서 **최적 BM 도달** (LA06, LA08-15)
- LLM 메타연산자 추가 시 **최소 3% 성능 향상**
- 수렴 속도 및 결과 분포 모두 우수

**한계:** 연산자 인구 크기 3개로 제한, FJSP 특화 neighborhood move, LLM 호출 비용

---

### 2.4 LLM4DRD — Dual-Expert Dispatching Rule Design

| 항목 | 내용 |
|------|------|
| **논문** | LLM-Assisted Automatic Dispatching Rule Design for Dynamic Flexible Assembly Flow Shop Scheduling |
| **연도** | 2026.01 (arXiv: 2601.15738) |
| **문제** | Dynamic FAFSP (Flexible Assembly Flow Shop) — 가공단계+조립단계, 이중 키팅 제약 |

#### LLM 활용 방식

```
┌───────────────────────────────────────────────────┐
│           LLM4DRD: 이중 전문가 메커니즘             │
│                                                   │
│  ┌─────────────┐         ┌─────────────┐         │
│  │  LLM-A      │         │  LLM-S      │         │
│  │ (Algorithm  │ 협업    │ (Scheduling │         │
│  │  Expert)    │◄──────►│  Expert)    │         │
│  │             │         │             │         │
│  │ - 코드 생성 │         │ - 스케줄링   │         │
│  │ - crossover │         │   평가      │         │
│  │ - mutation  │         │ - 반성 분석  │         │
│  └──────┬──────┘         └──────┬──────┘         │
│         │                       │                 │
│         ▼                       ▼                 │
│  ┌──────────────────────────────────────┐        │
│  │  PDR Population (Python 함수)         │        │
│  │  - 가공 PDR + 조립 PDR               │        │
│  │  - Elite knowledge 초기화             │        │
│  │  - Dynamic feature-fitting 진화      │        │
│  └──────────────────────────────────────┘        │
│                                                   │
│  이종 그래프 MDP: 주문/부품/기계 노드              │
│  + 방향 에지로 가공-조립 의존성 표현               │
└───────────────────────────────────────────────────┘
```

**핵심 혁신:**
- **LLM-A (알고리즘 전문가)**: Python 코드로 PDR 생성, 진화 연산(crossover/mutation) 수행
- **LLM-S (스케줄링 전문가)**: 생성된 규칙의 스케줄링 품질 평가, 반성적 분석 제공
- **이종 그래프**: 주문-제품-기계 관계를 방향 그래프로 모델링, 이중 키팅 제약 반영
- **Elite knowledge 초기화**: 기존 고성능 규칙으로 population warm-start
- **주관+객관 하이브리드 평가**: LLM-S의 정성 평가 + 시뮬레이션 정량 평가

**실험 결과:**
- 20개 실용 인스턴스에서 평균 납기지연 **3.17~12.39% 개선**
- 480개 인스턴스(24개 시나리오)에서 2위 대비 **11.10% 성능 우위**

**한계:** FAFSP 특화 구조, LLM 비결정성, 해석 가능성과 복잡성 트레이드오프

---

### 2.5 MAEF — Multi-Agent LLM Evolutionary Framework

| 항목 | 내용 |
|------|------|
| **논문** | Multi-agent Large Language Models as Evolutionary Optimizers for Scheduling Optimization |
| **저자** | Yidan Wang, Jiayin Wang, Zhiwei Chu (시안교통대) |
| **연도** | 2025.05, Computers & Industrial Engineering, Vol.206 |
| **문제** | SMS, FSP, JSP, RCPSP — 4가지 스케줄링 문제 |

#### LLM 활용 방식

```
┌───────────────────────────────────────────────────────┐
│                MAEF: 4-Agent 파이프라인                  │
│                                                       │
│  사용자: "5개 작업, 3대 기계, 납기 조건..." (자연어)     │
│                                                       │
│  ┌─────────────┐                                      │
│  │ Agent 1:    │  자연어 → 수학적 모델 변환              │
│  │ 문제 정의   │                                      │
│  └──────┬──────┘                                      │
│         ▼                                             │
│  ┌─────────────┐                                      │
│  │ Agent 2:    │  다양한 초기 feasible 해 생성          │
│  │ 초기해 생성 │                                      │
│  └──────┬──────┘                                      │
│         ▼                                             │
│  ┌─────────────┐     ┌─────────────┐                  │
│  │ Agent 3:    │◄───►│ Agent 4:    │  ← 피드백 루프   │
│  │ 진화 최적화 │     │ 평가       │                  │
│  │ (선택/교차/ │     │ (품질 평가  │                  │
│  │  변이)      │     │  + 피드백)  │                  │
│  └─────────────┘     └─────────────┘                  │
│                                                       │
│  Agent 3 ↔ Agent 4: 매 세대마다 반복                   │
└───────────────────────────────────────────────────────┘
```

**핵심 혁신:**
- **자연어 입력만으로 스케줄링 최적화**: 수학적 모델링/알고리즘 설계 불필요
- **4개 전문 에이전트 분업**: 문제정의 → 초기해 → 진화 → 평가
- **Agent 3 ↔ Agent 4 피드백 루프**: 단순 최종 평가가 아닌 **매 세대 실시간 피드백**
- Agent 4가 솔루션 품질을 평가하고, Agent 3이 다음 세대 탐색 방향을 조정
- 프롬프트만 수정하면 SMS/FSP/JSP/RCPSP 등 다양한 문제에 적용 가능

**실험 결과:**
- SMS, FSP, JSP, RCPSP 모두에서 전통적 휴리스틱/메타휴리스틱 대비 우수
- 확장성, 사용 편의성, 솔루션 품질 모두에서 우위

**한계:** LLM API 비용, 재현성 (LLM 출력 확률적), 대규모 인스턴스 context window 제한, 4개 문제만 검증

---

### 2.6 Starjob — LLM Fine-tuning Dataset for JSSP

| 항목 | 내용 |
|------|------|
| **논문** | Starjob: Dataset for LLM-Driven Job Shop Scheduling |
| **저자** | Henrik Abgaryan, Tristan Cazenave, Ararat Harutyunyan |
| **연도** | 2025.03 (arXiv: 2503.01877) |
| **문제** | 클래식 JSSP — LLM이 end-to-end로 직접 해를 생성 |

#### LLM 활용 방식

```
┌──────────────────────────────────────────────────────┐
│              Starjob: 파인튜닝 파이프라인               │
│                                                      │
│  1. 데이터셋 구축                                     │
│     130K JSSP 인스턴스 (2×2 ~ 50×20)                 │
│     OR-Tools CP-SAT 솔버로 해 생성 (300초 제한)       │
│     자연어로 변환                                     │
│                                                      │
│  2. 입력 형식                                         │
│     "Optimize schedule for 3 Jobs across 3 Machines  │
│      to minimize makespan.                           │
│      J0 requires: M2 (duration 105), M0 (78), ..."   │
│                                                      │
│  3. 출력 형식 (산술 체이닝)                            │
│     "J2-M0: 0+78 → 78, J1-M0: 78+134 → 212, ..."    │
│     "Maximum Makespan: 488"                          │
│                                                      │
│  4. 파인튜닝                                          │
│     LLaMA 3.1 8B (4-bit 양자화)                      │
│     RsLoRA (Rank-Stabilized LoRA)                    │
│     alpha=64, context=40K tokens, ~70시간 학습        │
│                                                      │
│  5. 추론                                              │
│     S=20 샘플링 → 최선의 feasible 해 선택             │
└──────────────────────────────────────────────────────┘
```

**핵심 혁신:**
- **최초의 JSSP 전용 supervised 데이터셋** (130K 인스턴스)
- **산술 체이닝 형식** (`start + duration → end`)이 feasible 솔루션 생성에 필수적
  - 이 형식 없이는 LLM이 infeasible 해를 대량 생성
- **LLM이 NP-hard 문제를 end-to-end로 직접 해결**하는 최초 시도 중 하나
- 3단계 검증: 작업 검증 → 기계 충돌 체크 → 작업 선행 체크

**실험 결과:**

| 벤치마크 | Starjob LLM | L2D (기존 neural SOTA) | 개선폭 |
|---------|-------------|----------------------|--------|
| Taillard | PG 21.69% | PG 29.54% | **7.85%p** |
| DMU | PG 22.14% | PG 37.50% | **15.36%p** |

- 모든 PDR (SPT, MWKR, FDD/WKR, MOPNR) 능가
- 1,000 노드(50×20) 규모까지 일반화 가능

**한계:** 최적해 대비 ~22% gap (메타휴리스틱보다 열등), 클래식 JSSP만 대상, 추론 비용 (S=20 샘플링), hallucination 문제

---

### 2.7 HFLLMDRL — Human Feedback + LLM + DRL

| 항목 | 내용 |
|------|------|
| **논문** | Large Language Model-Assisted Deep Reinforcement Learning from Human Feedback for Job Shop Scheduling |
| **저자** | Xixing Li 외 (우한이공대) |
| **연도** | 2025.04, MDPI Machines 13(5):361 |
| **문제** | JSSP — DRL 에이전트의 보상 함수 자동 설계 |

#### LLM 활용 방식

```
┌──────────────────────────────────────────────────────────┐
│          HFLLMDRL: LLM이 보상 함수를 설계                  │
│                                                          │
│  ┌──────────────────────────────────┐                    │
│  │  ROSES 프롬프트 프레임워크         │                    │
│  │  R: 역할 — "보상 엔지니어"        │                    │
│  │  O: 목표 — makespan 최소화        │                    │
│  │  S: 시나리오 — JSSP 환경 설명     │                    │
│  │  E: 기대 — 수학적 보상 함수 코드   │                    │
│  │  S: 단계 — 함수 구성 절차          │                    │
│  └────────────┬─────────────────────┘                    │
│               ▼                                          │
│  LLM → N=20개 후보 보상 함수 생성                         │
│               │                                          │
│               ▼                                          │
│  각 후보로 DRL 에이전트 학습 (ET=50회)                     │
│               │                                          │
│               ▼                                          │
│  Elite 선택 (상위 BN=3개)                                 │
│               │                                          │
│               ▼                                          │
│  인간 피드백 → 프롬프트 개선 → 다음 반복                   │
│  (M=100 iterations)                                      │
│                                                          │
│  최종 DRL 정책 네트워크: KAN (Kolmogorov-Arnold Network)   │
│  - 학습 가능한 activation (B-spline)                      │
│  - MLP 대비 대규모 문제에서 유리                          │
│  - 화이트박스 해석 가능                                   │
└──────────────────────────────────────────────────────────┘
```

**핵심 혁신:**
- **LLM이 직접 스케줄링하지 않고, DRL의 보상 함수를 코드로 생성**
- ROSES 프레임워크로 구조화된 few-shot 프롬프팅
- 100 iterations × 20 candidates = 2,000회 LLM 호출로 보상 함수 진화
- **KAN 정책 네트워크**: 에지에 학습 가능한 activation → 대규모 문제에서 MLP 대비 우수
- Elite 선택 > Greedy > Roulette wheel (수렴 안정성)

**실험 결과:**
- Taillard 벤치마크 (ta51: 50×20, ta71: 100×20)
- LLM 생성 보상 함수가 **수작업 보상 함수 대비 일관되게 우수**
- 대규모 문제에서 **KAN이 MLP 대비 명확한 우위** (적은 iteration으로 최적해 도달)

**한계:** 2,000회 LLM 호출 비용, 인간 피드백 필요 (완전 자동화 아님), 클래식 JSSP만 대상, 단일 목적함수

---

### 2.8 HRC-LLM — Human-Robot Collaborative Manufacturing

| 항목 | 내용 |
|------|------|
| **논문** | Leveraging Large Language Models for Efficient Scheduling in Human-Robot Collaborative Flexible Manufacturing Systems |
| **저자** | Jin Huang, Yue Teng, Qihao Liu, Liang Gao, Xinyu Li 외 (화중과기대) |
| **연도** | 2025.11, npj Advanced Manufacturing 2:47 |
| **문제** | HRC-FMS에서의 Dynamic FJSP — 인간/로봇/협업 팀 간 작업 배분 |

#### LLM 활용 방식

```
┌────────────────────────────────────────────────────────┐
│          HRC-LLM: 로컬 LLM + SeEvo 프레임워크           │
│                                                        │
│  Phase 1: Offline Self-Evolution                       │
│  ┌──────────────────────────────────────────────┐      │
│  │  로컬 LLM (CodeLlama 계열, LlamaFactory/LoRA)│      │
│  │  - 스케줄링 데이터로 supervised fine-tuning   │      │
│  │                                              │      │
│  │  Reflector LLM: 반성/분석 프롬프트 생성       │      │
│  │  Generator LLM: HDR Python 코드 생성          │      │
│  │                                              │      │
│  │  SeEvo 3단계 진화                             │      │
│  │  (co-evolution + self-evolution + collective) │      │
│  └──────────────────────────────────────────────┘      │
│                                                        │
│  Phase 2: Online Real-Time Application                 │
│  ┌──────────────────────────────────────────────┐      │
│  │  이벤트 발생 (고장, 긴급주문, 작업자변동)      │      │
│  │       ↓                                      │      │
│  │  진화된 HDR 즉시 적용 (밀리초 수준)           │      │
│  │       ↓                                      │      │
│  │  인간 가독 설명 생성 (신뢰성 확보)            │      │
│  └──────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────┘
```

**핵심 혁신:**
- **로컬 LLM 배포**: 클라우드 API 의존 없이, 공장 내 로컬 모델 사용 → 데이터 프라이버시 + 저지연
- **LlamaFactory + LoRA**로 스케줄링 전용 파인튜닝
- SeEvo 프레임워크 기반 (2.1 SeEvo의 확장 버전)
- 인간-로봇 협업 환경에 특화: 인간 가용성, 로봇 정밀성, 협업 팀 역량 고려
- **인간 가독 설명 생성**: 스케줄링 결정의 이유를 자연어로 설명 → HRC 환경에서 운영자 신뢰 확보
- **캐스케이딩 효과 예측**: 현재 결정의 하류 영향을 LLM이 예측

**실험 결과:**
- GP, GEP, DRL, 10+ HDR 모두 능가
- 동적/미지 시나리오에서 특히 우수한 일반화
- 실시간 환경에서 밀리초 수준 응답

**한계:** 단일 규칙 제한, 오프라인 진화 비용, 인간 요소 모델링 불완전

---

## 3. 논문 간 비교표

| 논문 | 문제 유형 | LLM 역할 | LLM 모델 | 피드백 루프 | 생성물 | 주요 성과 |
|------|----------|----------|----------|-----------|--------|----------|
| **SeEvo** | DJSSP | 코드 생성 + 반성 | GPT-4 | 3단계 자기진화 | Python HDR 코드 | GP/GEP/DRL 능가 |
| **ReflecSched** | DFJSP | 전략 분석가 | Qwen/GPT-4o/GPT-5 | Simulate→Reflect→Refine | Strategic Experience (자연어) | 71.35% Win Rate |
| **LLM4EO** | FJSP | 메타 연산자 설계 | (미명시) | Perception→Analysis→Refinement | Gene selection 코드 | BM 7/10 최저 |
| **LLM4DRD** | FAFSP | 이중 전문가 | (미명시) | LLM-A↔LLM-S 협업 | 가공+조립 PDR 코드 | 11.10% 우위 |
| **MAEF** | SMS/FSP/JSP/RCPSP | 4-Agent 분업 | (미명시) | Agent3↔Agent4 매 세대 | 스케줄링 솔루션 | 4개 문제 모두 우수 |
| **Starjob** | JSSP | End-to-end 솔버 | LLaMA 8B (LoRA) | 없음 (supervised) | 직접 스케줄 | L2D 대비 15.36%↑ |
| **HFLLMDRL** | JSSP | 보상 함수 설계 | GPT-4 (추정) | Elite 선택 + 인간 피드백 | DRL 보상 함수 코드 | 수작업 보상 능가 |
| **HRC-LLM** | HRC-DFJSP | 코드 생성 (로컬) | CodeLlama (LoRA) | SeEvo 3단계 | Python HDR + 설명 | 실시간 밀리초 응답 |

---

## 4. 공통 패턴 및 핵심 인사이트

### 4.1 공통 패턴

#### 패턴 1: LLM은 직접 스케줄러가 아닌 "메타 수준" 역할이 효과적

8편 중 7편에서 LLM은 **직접 스케줄링 결정을 내리지 않는다**. 대신:
- 디스패칭 **규칙의 코드**를 생성 (SeEvo, LLM4DRD, LLM4EO, HRC-LLM)
- 스케줄링 **결과를 분석**하고 전략을 제안 (ReflecSched, MAEF)
- DRL의 **보상 함수를 설계** (HFLLMDRL)

유일한 예외인 Starjob도 end-to-end 접근의 한계(최적해 대비 ~22% gap)를 보여주며, 메타 수준 활용이 더 효과적임을 간접 시사한다.

> **인사이트**: LLM은 "문제를 직접 푸는 것"보다 "문제를 푸는 방법을 만드는 것"에 더 적합하다.

#### 패턴 2: 진화 알고리즘과의 결합이 지배적

8편 중 6편이 **LLM + 진화적 탐색** 구조를 사용:
- Population 기반 진화 (SeEvo, LLM4EO, LLM4DRD, HRC-LLM, MAEF)
- Elite 선택 메커니즘 (HFLLMDRL)

LLM 단독으로는 탐색 공간을 체계적으로 커버하기 어렵기 때문에, 진화 알고리즘의 population 다양성 + LLM의 의미론적 이해를 결합하는 패턴이 반복된다.

> **인사이트**: LLM은 "지능적 crossover/mutation 연산자"로서 진화 알고리즘의 랜덤 탐색을 의미 수준 탐색으로 격상시킨다.

#### 패턴 3: "반성(Reflection)" 메커니즘이 핵심 차별점

거의 모든 논문에서 LLM의 **자기반성/분석 능력**을 활용:
- SeEvo: 3단계 반성 (co-evolution, self-evolution, collective)
- ReflecSched: 계층적 반성 (multi-horizon)
- LLM4EO: Perception → Analysis → Refinement
- LLM4DRD: LLM-S의 스케줄링 반성
- HFLLMDRL: Elite 평가를 통한 간접 반성

이는 단순히 "코드를 생성하라"가 아닌 **"왜 이것이 좋은지/나쁜지 분석하라"**는 프롬프팅이 핵심이라는 것을 의미한다.

> **인사이트**: Reflection 프롬프트가 generation 프롬프트보다 LLM 활용의 가치가 높다.

#### 패턴 4: 코드 생성이 주된 출력 형태

LLM의 출력은 대부분 **실행 가능한 Python 코드**:
- HDR 함수 (SeEvo, LLM4DRD, HRC-LLM)
- Gene selection 함수 (LLM4EO)
- 보상 함수 (HFLLMDRL)
- 스케줄 자체의 자연어 표현 (Starjob)

> **인사이트**: 코드 생성 능력이 LLM을 스케줄링에 활용하는 가장 실용적인 인터페이스다.

#### 패턴 5: 오프라인 진화 + 온라인 적용의 2-Phase 구조

실시간 스케줄링 적용을 목표로 하는 논문들(SeEvo, HRC-LLM, LLM4DRD)은 모두:
1. **오프라인**: LLM 호출 비용을 감수하며 고품질 규칙을 진화
2. **온라인**: 진화된 규칙을 밀리초 수준으로 실행

> **인사이트**: LLM의 추론 비용 문제를 "규칙 생성은 비싸지만, 규칙 실행은 저렴하다"는 구조로 해결한다.

### 4.2 차이점 및 트레이드오프

| 축 | 직접 생성 (Starjob) | 규칙 생성 (SeEvo류) | 분석/피드백 (ReflecSched) |
|---|---|---|---|
| **솔루션 품질** | 중간 (~22% gap) | 높음 | 높음 |
| **일반화** | 학습 분포에 의존 | 우수 (dynamic 환경) | 우수 (zero-shot) |
| **실시간성** | 추론 필요 | 밀리초 | LLM 호출 필요 |
| **LLM 비용** | 학습 시 1회 | 진화 시 다수 | 매 결정마다 |
| **학습 데이터 필요** | 130K 인스턴스 | 불필요 | 불필요 |
| **환경 변화 대응** | 재학습 필요 | 재진화 필요 | 즉시 적응 |

### 4.3 향후 연구 방향 (논문들의 공통 제안)

1. **다목적 최적화**: 대부분 makespan 단일 목적 → 납기지연, 에너지, 기계부하 등 다목적으로 확장 필요
2. **대규모 인스턴스**: 수백 기계, 수천 작업 규모의 산업 문제 검증 부족
3. **복합 동적 이벤트**: 기계 고장, 작업자 변동, 긴급 주문 등을 동시에 다루는 연구 필요
4. **오픈소스 LLM 활용**: GPT-4 API 의존도를 줄이고, 로컬 오픈소스 모델의 성능 검증 필요
5. **이론적 수렴 보장**: 경험적 성능은 우수하나, 수렴 보장이나 해 품질 bound가 부재
6. **상용화 갭**: 연구 벤치마크 → 실제 공장 환경 간의 격차 해소 필요

---

## 부록: 다운로드된 논문 PDF 목록

| 파일명 | 논문 |
|--------|------|
| `SeEvo_2024.pdf` | Automatic Programming via LLMs with Population Self-Evolution for DJSSP |
| `ReflecSched_2025.pdf` | ReflecSched: Solving DFJSP via LLM-Powered Hierarchical Reflection |
| `LLM4EO_2025.pdf` | Online Operator Design in Evolutionary Optimization for FJSP via LLMs |
| `LLM4DRD_2025.pdf` | LLM-Assisted Automatic Dispatching Rule Design for Dynamic FAFSP |
| `Starjob_2025.pdf` | Starjob: Dataset for LLM-Driven Job Shop Scheduling |
| `HFLLMDRL_2025.pdf` | LLM-Assisted DRL from Human Feedback for JSP |
| `LLMs_can_Schedule_2024.pdf` | LLMs can Schedule (참고 논문) |
| `HRC_LLM_Manufacturing_2025.pdf` | Leveraging LLMs for Scheduling in HRC-FMS |

> MAEF 논문은 ScienceDirect 유료 논문으로 PDF 다운로드 불가 (abstract 기반 분석)
