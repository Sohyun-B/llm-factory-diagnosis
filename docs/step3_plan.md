# Step 3 계획: MetroPT — 센서 + 정비 이벤트 로그 기반 LLM 에이전트

> 작성일: 2026-03-03
> 데이터셋: MetroPT (포르투 지하철 공기압축기)
> 핵심 추가: 이벤트 로그를 RAG로 구축해 LLM이 정비 이력까지 교차 참조하며 추론

---

## 1. Step 2와의 핵심 차이

| 항목 | Step 2 (UCI Hydraulic) | Step 3 (MetroPT) |
|------|----------------------|-----------------|
| 이상 레이블 | 4개 부품 상태 등급 | 실패 시작/종료 시각 + 실패 유형 텍스트 |
| 이벤트 로그 | **없음** | **실제 정비 보고서** (자연어) |
| LLM 추가 능력 | ML 결과 가설 검증 | ML 결과 + **과거 정비 이력 교차 추론** |
| RAG | 없음 | 이벤트 로그 벡터 DB → 동적 검색 |
| 검증 목표 | ML 예측이 센서로 뒷받침되는가 | 정비 이력이 현재 이상의 원인/맥락을 제공하는가 |

---

## 2. 데이터셋 이해

### 사용 버전: MetroPT (Zenodo 6854240) + MetroPT-3 (UCI 791)

| 버전 | 링크 | 행 수 | 기간 | 컬럼 |
|------|------|-------|------|------|
| MetroPT-3 (UCI) | https://archive.ics.uci.edu/dataset/791 | 1,516,948 | 2020년 2~8월 | 15개 |
| MetroPT (Zenodo) | https://zenodo.org/records/6854240 | 10,979,547 | 2022년 1~6월 | 20개 |
| MetroPT2 (Zenodo) | https://zenodo.org/records/7766691 | 7,116,940 | 2022년 이후 | 21개 |

→ **MetroPT-3 (UCI)** 로 시작: 크기가 적당하고 실험 구조가 단순

### 시스템 구조

포르투갈 포르투 지하철 열차의 **APU (Air Production Unit)** — 브레이크, 서스펜션, 도어에 공급할 압축 공기를 생산하는 장치

```
[공기 흡입] → [압축기(Compressor)] → [에어드라이어(Air Dryer)] → [저수지(Reservoir)]
                      ↓                        ↓
               오일 냉각 시스템          수분 제거 타워 A/B
                                              ↓
                                    [클라이언트] 브레이크/도어/서스펜션
```

### 센서 15개 (MetroPT-3 기준)

**아날로그 7개**

| 센서 | 단위 | 의미 |
|------|------|------|
| TP2 | bar | 압축기 내부 압력 |
| TP3 | bar | 공기압 패널 출력 압력 |
| H1 | bar | 사이클론 필터 압력 강하 |
| DV_pressure | bar | 에어드라이어 수분 배출 시 압력 강하 (0 = 정상 운전) |
| Reservoirs | bar | 공기탱크 압력 (TP3와 근사해야 정상) |
| Oil_Temperature | °C | 압축기 오일 온도 |
| Motor_Current | A | 모터 전류 (정지 ~0A, 무부하 ~4A, 부하 ~7A) |

**디지털 8개 (0/1 이진)**

| 센서 | 의미 |
|------|------|
| COMP | 압축기 흡입밸브 신호 (공기 흡입 없을 때 1) |
| DV_electric | 압축기 출구 밸브 제어 |
| TOWERS | 에어드라이어 타워 교대 방향 |
| MPG | 압력 8.2 bar 미만 시 압축기 기동 신호 |
| LPS | 압력 7 bar 미만 시 저압 알람 |
| Pressure_switch | 수분 배출 감지 신호 |
| Oil_Level | 오일 부족 알람 (부족 시 1) |
| Caudal_impulses | 저수지로 흐르는 공기량 펄스 |

### 이벤트 로그 (정비 보고서)

MetroPT-3 기준 실패 케이스:

| Nr. | 실패 유형 | 부품 | 시작 | 종료 |
|-----|----------|------|------|------|
| 1 | Air Leak | Clients (브레이크/도어 파이프) | 2020-04-18 00:00 | 2020-04-18 23:59 |
| 2 | Air Leak | Air Dryer | 2020-05-29 00:00 | 2020-05-29 23:59 |
| ... | ... | ... | ... | ... |

Zenodo 원본 추가 케이스:

| Nr. | 실패 유형 | 부품 | 시작 | 종료 |
|-----|----------|------|------|------|
| 1 | Air Leak | Clients | 2022-02-28 21:53 | 2022-03-01 02:00 |
| 2 | Air Leak | Air Dryer | 2022-03-23 14:54 | 2022-03-23 15:24 |
| 3 | Oil Leak | Compressor | 2022-05-30 12:00 | 2022-06-02 06:18 |

---

## 3. 핵심 아키텍처: 센서 + 이벤트 로그 교차 추론

### 전체 흐름

```
[사용자] "2022-05-31 14:00 시점 분석해줘"
    ↓
[에이전트 루프 시작]

--- Round 1: 기초 이상 탐지 ---
LLM → detect_anomaly(timestamp)
    ← ML 이상 탐지 결과:
       TP2 압력: 5.1 bar (정상 대비 -23%)
       Motor_Current: 8.4A (정상 부하 7A 초과)
       Oil_Temperature: 94°C (정상 대비 +18%)

LLM 내부 추론:
  "압력 저하 + 전류 과부하 + 온도 상승 동시 발생.
   Oil Leak 또는 Air Leak 가능성.
   이 시점 전후 정비 이력이 있는지 확인 필요."

--- Round 2: 이벤트 로그 RAG 검색 ---
LLM → search_maintenance_log("2022-05-31 전후 Oil Temperature 이상")
    ← [검색 결과]
       2022-05-30 12:00 | Oil Leak | Compressor | 정비 시작
       → "압축기 오일 누출 감지, 즉시 점검 필요"

LLM 내부 추론:
  "전날부터 Oil Leak 정비가 시작됐음.
   현재 분석 시점은 정비 중인 상태.
   오일 온도 상승 + 전류 증가는 오일 누출로 인한 윤활 부족이 원인."

--- Round 3: 유사 과거 사례 검색 ---
LLM → search_similar_failures("Oil Leak Compressor high temperature")
    ← [유사 사례]
       2022-03-23 Air Dryer Leak: TP3 정상, DV_pressure 이상
       2022-02-28 Clients Air Leak: LPS 알람 + Reservoirs 압력 저하
       → "Oil Leak 패턴: 온도 상승 + 전류 증가 선행, TP2 압력은 나중에 저하"

--- 루프 종료: finish_reason = "stop" ---

[LLM 최종 응답]
  근본 원인: 압축기 오일 누출 (전날 정비 기록으로 확인됨)
  센서 증거: 오일 온도 +18%, 전류 +20% (윤활 부족으로 인한 마찰 증가)
  정비 이력 교차: 2022-05-30부터 Oil Leak 정비 진행 중
  유사 사례: 과거 패턴과 일치 (온도→전류→압력 순서로 악화)
  권고: 정비 완료 후 TP2 압력과 Oil_Temperature 동시 모니터링 필요
```

---

## 4. 툴 목록 설계

### Group A: 고정 진단 툴

| 툴 이름 | 기능 | 반환값 |
|--------|------|--------|
| `detect_anomaly(timestamp)` | 해당 시점 센서값 + 정상 대비 편차 | {센서별 값, 편차%, 이상 여부} |
| `get_sensor_trend(timestamp, window_hours)` | 시점 전후 N시간 센서 트렌드 | {센서별 시계열 요약, 추세 방향} |
| `classify_failure_type(timestamp)` | ML 모델로 실패 유형 분류 | {예측 유형, 확률} |

### Group B: 이벤트 로그 RAG 툴 (Step 3 핵심 추가)

| 툴 이름 | 기능 | LLM이 왜 쓰는가 |
|--------|------|----------------|
| `search_maintenance_log(query, time_range)` | 자연어 쿼리로 정비 기록 벡터 검색 | "이 시점 전후 어떤 정비가 있었는지 확인" |
| `get_recent_events(timestamp, hours_before)` | 특정 시점 이전 N시간 이내 모든 이벤트 | "이상 발생 전 무슨 일이 있었는지 확인" |
| `search_similar_failures(description)` | 유사 실패 패턴 과거 사례 검색 | "비슷한 증상의 과거 사례 결과 확인" |

### Group C: 통계 분석 툴

| 툴 이름 | 기능 |
|--------|------|
| `get_pressure_stats(timestamp)` | TP2, TP3, Reservoirs 압력 통계 + 정상 대비 |
| `get_temperature_stats(timestamp)` | Oil_Temperature 추세 + 임계값 비교 |
| `get_electrical_stats(timestamp)` | Motor_Current 부하 패턴 분석 |
| `get_airflow_stats(timestamp)` | DV_pressure, H1 공기 흐름 통계 |

---

## 5. RAG 구축 방법

총 35개 문서를 3가지 타입으로 구성. 각 타입의 생성 방식이 완전히 다르다.

### 타입 1: `domain_knowledge` — 13건

**생성 방식: 수동 작성 (뇌피셜)**

UCI 데이터셋 설명 페이지와 MetroPT 논문에서 센서 의미와 정상값 범위를 읽고 직접 작성한 문장들. 실제 포르투 지하철 정비 매뉴얼 원문은 없다. 포함 내용:

| 항목 | 건수 |
|------|------|
| APU 시스템 구조 설명 | 1건 |
| 센서별 정상값 및 이상 의미 (TP2, TP3, Reservoirs, Oil_temp, Motor_current, LPS, Oil_level, DV_pressure) | 8건 |
| 고장 유형별 센서 패턴 (Air Leak 클라이언트, Air Leak 에어드라이어, Oil Leak 압축기) | 3건 |
| 정비 기준 (임계값, 2시간 전 감지 목표) | 1건 |

실제 프로젝트에서는 장비 매뉴얼 PDF, 기술 사양서, 운영 가이드 등을 파싱해서 사용해야 하는 위치다.

---

### 타입 2: `maintenance_report` — 2건

**생성 방식: 실제 데이터 → 텍스트 변환**

`failure_events.json`에 하드코딩된 MetroPT-3의 실제 정비 기록 2건을 텍스트 문서로 변환한다. 변환 시 `features.pkl`에서 해당 실패 구간의 센서 평균값과 정상 대비 편차를 자동 계산해서 함께 붙인다.

```
입력: { id: "F1", type: "Air_Leak", component: "Clients",
        start: "2020-04-18 00:00", end: "2020-04-18 23:59",
        description: "..." }
      + features.pkl의 해당 구간 센서값

출력: "[정비 보고서 F1] 실패 유형: Air_Leak | 부품: Clients |
       기간: 2020-04-18 00:00 ~ 2020-04-18 23:59 |
       설명: ... |
       센서 요약: TP3_mean=8.xxx(정상 대비 +x.x%), Reservoirs_mean=..."
```

MetroPT-3 데이터셋에 실패 케이스가 2건뿐이라 문서도 2건이다.

---

### 타입 3: `alarm_event` — 20건

**생성 방식: 센서 데이터 → 규칙 기반 자동 생성**

`features.pkl`에서 `LPS_rate > 0.5` (10분 윈도우에서 저압 알람이 50% 이상 발생)인 구간을 찾아 인접한 구간끼리 묶고, 각 구간을 텍스트 문서로 변환한다. 최대 20개.

```
조건: LPS_rate > 0.5 인 윈도우 → 인접 구간 묶기 (간격 700초 이내)

출력: "[LPS 저압 알람 구간 #1] 기간: 2020-04-18 06:00 ~ ... |
       TP3=8.xxx bar, Reservoirs=8.xxx bar, Motor_current=x.xxx A |
       저압 알람 지속 시간: N분"
```

**이 방식을 쓴 이유**: `maintenance_report`가 2건뿐이어서 `search_similar_failures`로 검색할 과거 사례가 부족하기 때문이다. LPS 알람이 Air Leak 발생 시 나타나는 신호이므로 "비슷한 증상이 있었던 과거 구간"으로 활용한다.

**한계**: 이 문서에는 라벨이 없다. LPS 알람이 실제 실패 때문인지, 단순 압력 변동인지 문서 자체가 구분하지 않는다. LLM이 이를 "과거 실패 사례"로 오해할 수 있다.

이 패턴은 실제로도 쓰인다 — 구조화된 알람 로그나 이벤트 로그를 자연어로 변환해 RAG에 넣는 방식(data-to-text)은 ERP/SCADA 시스템에서 관찰된다. 단, 실제 시스템에서는 각 이벤트에 정비 결과 라벨이 붙어있어 이 한계가 없다.

---

### 전체 구성 요약

| 타입 | 건수 | 출처 | 신뢰도 |
|------|------|------|--------|
| `domain_knowledge` | 13 | 수동 작성 (논문/데이터셋 설명 기반) | 낮음 — 실제 매뉴얼 아님 |
| `maintenance_report` | 2 | 실제 정비 기록 + 센서 요약 자동 계산 | 높음 — 실제 데이터 |
| `alarm_event` | 20 | LPS 알람 구간 규칙 기반 자동 생성 | 중간 — 라벨 없음 |

**RAG 품질의 핵심 병목은 `maintenance_report` 2건이다.** 실제 프로젝트였다면 수년치 정비 보고서가 수백~수천 건 있어야 할 위치다.

정비 기록 수가 적을 때 (수십 건):
- FAISS 인메모리 벡터 DB로 충분
- Zenodo 3개 버전 모두 합쳐도 이벤트 수십 건 수준

---

## 6. ML 모델 설계

MetroPT는 Step 2와 달리 **시점 기반 이상 감지**가 목표

| 모델 | 입력 | 출력 | 비고 |
|------|------|------|------|
| 정상/이상 분류기 | 시점 전후 N분 윈도우 센서값 | 이상 확률 | Random Forest 또는 Isolation Forest |
| 실패 유형 분류기 | 이상 감지된 시점 센서값 | Air Leak / Oil Leak | 레이블 수가 적어 simple RF |
| 이상 시점 탐지 | 전체 시계열 | 이상 시작 시각 | 통계적 제어 차트 또는 슬라이딩 윈도우 |

기업 요구 기준: **실패 2시간 전 감지** (MetroPT 논문 명시)

---

## 7. 파일 구조

```
step3_metropt_agent/
├── data/                      # 수동 다운로드 필요
│   ├── MetroPT3.csv           # UCI 다운로드
│   ├── dataset_train.csv      # Zenodo 6854240 (선택)
│   └── maintenance_reports/
│       ├── failures_uci.json  # MetroPT-3 실패 기록
│       └── failures_zenodo.json
├── preprocess.py              # 센서 윈도우 집계 + 정상 baseline
├── train_models.py            # 이상 감지 + 실패 유형 분류기
├── build_rag.py               # 이벤트 로그 → 벡터 DB 구축  ← 신규
├── models/
│   ├── anomaly_detector.pkl
│   ├── failure_classifier.pkl
│   ├── features.pkl
│   ├── baseline.pkl
│   └── vectorstore/           # FAISS 벡터 DB  ← 신규
├── agent.py
└── app.py
```

---

## 8. 검증 목표

| 검증 항목 | 방법 |
|----------|------|
| 이상 감지 선행 시간 | 실패 시작 몇 시간 전부터 이상 신호가 나타나는가 |
| ML 분류 정확도 | Air Leak / Oil Leak 분류 F1 |
| LLM이 정비 이력을 활용하는가 | 툴 로그에서 `search_maintenance_log` 호출 여부 + 호출 이유 |
| 정비 이력이 추론 품질을 높이는가 | RAG 있을 때 vs 없을 때 LLM 결론 비교 (ablation) |
| 유사 사례 추론 | 과거 패턴을 현재 케이스에 올바르게 연결하는가 |

---

## 9. Step 2와의 구조 비교

```
Step 2 에이전트:
  분류기(ML) → LLM 가설 → 센서 통계 검증 → 결론

Step 3 에이전트:
  이상 감지(ML) → LLM 가설 → 센서 통계 검증
                           → 정비 이력 RAG 검색      ← 추가
                           → 유사 사례 RAG 검색       ← 추가
                           → 결론 (3중 교차 근거)
```

---

## 10. 구현 순서

```
① MetroPT-3 (UCI) 다운로드
② preprocess.py → 시점별 센서 윈도우 통계 + 정상 baseline
③ train_models.py → 이상 감지 + 실패 유형 분류기
④ build_rag.py → 정비 보고서 + 유사 사례 벡터 DB 구축
⑤ agent.py → 툴 정의 + while 루프 (RAG 툴 포함)
⑥ app.py → Streamlit UI
⑦ ablation: RAG 있을 때 vs 없을 때 LLM 추론 품질 비교
```

---

*데이터셋 정보: docs/step3_dataset_candidates.md*
*산업계 사례: docs/industry_cases.md*

---

## 11. 워크플로우 선택 방식

### 에이전트가 툴을 선택하는 주체는 LLM이다

```python
# agent.py
response = self.client.chat.completions.create(
    model="gpt-4o",
    tools=TOOL_SCHEMAS,
    tool_choice="auto",   # ← LLM이 자율 결정
)
```

`tool_choice="auto"` → LLM이 매 라운드마다 "다음에 어떤 툴을 호출할지", "인자를 어떻게 채울지"를 스스로 결정한다. 코드 레벨에서 하드코딩된 툴 호출 순서는 없다.

### 단, 시스템 프롬프트로 행동을 강제한다

SYSTEM_PROMPT에 4단계 순서가 명시되어 있고, 이탈을 금지하는 규칙이 포함되어 있다:

```
1단계: detect_anomaly 호출 (항상 필수)
         → 이상 감지 시에만: classify_failure_type 호출
2단계: 가설 수립 + search_domain_knowledge 호출
3단계: get_sensor_trend + RAG 검색 툴 중 하나 이상 호출 (둘 다 필수)
4단계: 결론

"센서만으로 결론을 내리는 것은 허용되지 않습니다."
"이벤트 로그 검색 없이 결론을 내리는 것은 허용되지 않습니다."
```

`classify_failure_type`은 툴 설명 자체에 "이상이 감지된 경우"라는 조건이 명시되어 있다. 따라서 정상 구간을 분석할 때는 LLM이 이 툴을 건너뛴다. Round 1에서 두 Group A 툴이 항상 함께 호출되는 것이 아니다.

### 정상 판정 시 이후 단계 전체가 스킵된다

시스템 프롬프트의 2단계가 "**이상이 감지되면** 가능한 원인을 가설로 세우십시오"로 시작한다. 3단계(센서 검증 + RAG 검색)와 4단계(결론)는 모두 이 가설에서 파생되므로, `detect_anomaly`가 정상을 반환하면 LLM은 이후 툴을 전혀 호출하지 않고 바로 "정상" 결론을 반환한다.

"이벤트 로그 검색 없이 결론 금지" 규칙도 "가설을 검증할 때"가 전제이므로 정상 구간에서는 적용되지 않는다.

다만 이는 코드로 강제된 분기가 아니라 LLM이 프롬프트를 해석하는 결과다. 명시적인 `if is_anomaly: ... else: return` 구조가 에이전트 코드에 없으므로, LLM 응답에 따라 정상 구간에서도 RAG를 추가 호출할 가능성이 이론상 존재한다.

즉, 구조는 **소프트 강제(soft-constrained) LLM 선택**이다:
- 툴 선택의 주체 = LLM (하드코딩 아님)
- 특정 툴의 필수 호출 여부 = 프롬프트로 강제
- 툴 인자(timestamp, query 등) = LLM이 자유롭게 생성
- 루프 종료 시점 = LLM이 `finish_reason="stop"` 반환할 때까지 자율 결정

### 사용자 입력 방식 (app.py)

사용자가 선택하는 것은 **분석할 타임스탬프 하나뿐**이다.

| 입력 방법 | 내용 |
|----------|------|
| 직접 입력 | 텍스트 박스에 `YYYY-MM-DD HH:MM:SS` 형식으로 입력 |
| 랜덤(이상) 버튼 | `labels != "normal"` 인덱스에서 무작위 샘플링 |
| 랜덤(정상) 버튼 | `labels == "normal"` 인덱스에서 무작위 샘플링 |

타임스탬프가 결정되면 이후 모든 툴 호출과 추론은 에이전트가 자율 실행한다. 중간에 사용자가 개입하는 선택지는 없다.

---

## 12. 계획 대비 실제 구현 불일치

### 툴 목록

| 계획 (Section 4) | 실제 구현 | 상태 |
|-----------------|----------|------|
| Group A: `detect_anomaly` | 구현됨 | ✅ |
| Group A: `classify_failure_type` | 구현됨 | ✅ |
| Group A: `get_sensor_trend` | 구현됨 (Group C 흡수) | ✅ |
| Group B: `search_maintenance_log` | 구현됨 | ✅ |
| Group B: `get_recent_events` | 구현됨 | ✅ |
| Group B: `search_similar_failures` | 구현됨 | ✅ |
| Group C: `get_pressure_stats` | **미구현** — `get_sensor_trend`로 통합 | ❌ |
| Group C: `get_temperature_stats` | **미구현** — `get_sensor_trend`로 통합 | ❌ |
| Group C: `get_electrical_stats` | **미구현** — `get_sensor_trend`로 통합 | ❌ |
| Group C: `get_airflow_stats` | **미구현** — `get_sensor_trend`로 통합 | ❌ |
| (계획 없음) | `search_domain_knowledge` 추가 | ➕ |

Group C 통계 툴 4개는 `get_sensor_trend` 하나로 통합 구현됐다. 센서 그룹별로 분리하는 대신 주요 7개 센서를 한 번에 반환하는 구조.

### RAG 구현 방식

| 계획 | 실제 구현 |
|------|----------|
| langchain 사용 (`langchain.vectorstores.FAISS`, `langchain.embeddings.OpenAIEmbeddings`) | raw FAISS + OpenAI API 직접 호출 (langchain 미사용) |

### 데이터 및 이벤트

| 계획 | 실제 구현 |
|------|----------|
| `step3_metropt_agent/data/` 폴더에 데이터 저장 | `data/metropt+3+dataset/` (프로젝트 루트) |
| `maintenance_reports/failures_uci.json`, `failures_zenodo.json` 분리 | `models/failure_events.json` 단일 파일 |
| Zenodo 3개 케이스 포함 | MetroPT-3 UCI 2개 케이스만 (`F1: Air_Leak/Clients`, `F2: Air_Leak/Air_Dryer`) |

### ML 모델

| 계획 (Section 6) | 실제 구현 |
|-----------------|----------|
| 정상/이상 분류기 | 구현됨 (`anomaly_detector.pkl`) |
| 실패 유형 분류기 | 구현됨 (`failure_classifier.pkl`) |
| 이상 시점 탐지 (슬라이딩 윈도우) | **미구현** |
| (계획 없음) | `pre_labels.pkl` 추가 (3-class: normal/Air_Leak_Clients/Air_Leak_Air_Dryer) |

### 구현 순서 ⑦ ablation

계획의 마지막 단계인 "RAG 있을 때 vs 없을 때 LLM 추론 품질 비교" ablation은 **미구현**.

