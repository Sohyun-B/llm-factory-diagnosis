# Step 2 계획: UCI Hydraulic — ML 다중 분류 + LLM 에이전트 가설 검증 루프

> 작성일: 2026-02-26
> 목적: "ML이 못하는 것을 LLM이 한다"는 구조를 처음으로 실현하는 단계
> 핵심 추가: LLM이 가설을 세우고, 검증을 위해 추가 분석을 스스로 요청함

---

## 1. Step 1과의 핵심 차이

| 항목 | Step 1 (AI4I) | Step 2 (Hydraulic) |
|------|--------------|-------------------|
| LLM이 하는 일 | 센서 수치 → 고장 유형 분류 | ML 결과 수신 → 가설 → 추가 분석 요청 → 결론 |
| ML의 역할 | 없음 | 4개 부품 분류기 + 에이전트가 요청하는 on-demand 분석 |
| LLM이 ML보다 나은 이유 | 없음 (ML이 더 잘함) | 가설 생성, 검증 전략 수립, 복합 판단 |
| 에이전트 구조 | 없음 | 멀티 라운드 tool calling 루프 |

---

## 2. 데이터셋 이해

### 구조
- **2,205 사이클** × 60초 단위 센서 기록
- 센서 파일 17개 (샘플링 주기가 센서마다 다름)

| 파일 | 센서 | 샘플링 | 단위 |
|------|------|--------|------|
| PS1~PS6 | 압력 | 100Hz | bar |
| EPS1 | 전력 | 100Hz | W |
| FS1, FS2 | 유량 | 10Hz | L/min |
| TS1~TS4 | 온도 | 1Hz | °C |
| VS1 | 진동 | 1Hz | mm/s |
| CE, CP, SE | 냉각 효율/전력/효율 | 1Hz | % |

- **레이블 파일 1개** (`profile.txt`): 사이클별 4개 부품 상태

### 레이블 의미

| 부품 | 레이블 값 | 의미 |
|------|----------|------|
| 냉각기 (Cooler) | 100 / 20 / 3 | 정상 / 성능 저하 / 고장 임박 |
| 밸브 (Valve) | 100 / 90 / 80 / 73 | 최적 / 경미한 지연 / 심각한 지연 / 고장 임박 |
| 내부 펌프 누수 (Pump) | 0 / 1 / 2 | 없음 / 약한 누수 / 심각한 누수 |
| 어큐뮬레이터 (Accumulator) | 130 / 115 / 100 / 90 | 최적 / 약간 저하 / 심각 저하 / 고장 임박 |

---

## 3. 핵심 아키텍처: 가설 검증 루프

### 전체 흐름

```
[사용자] "사이클 #1042 분석해줘"
    ↓
[에이전트 루프 시작]

--- Round 1: 기초 상태 파악 ---
LLM → classify_cooler(1042)    → 성능저하 (87%)
LLM → classify_valve(1042)     → 심각한 지연 (88%)
LLM → classify_pump(1042)      → 약한 누수 (79%)
LLM → classify_accumulator(1042) → 정상 (91%)

LLM 내부 추론:
  "밸브 지연 + 펌프 누수가 동시 발생.
   가설: 펌프 누수로 인한 압력 저하가 밸브 지연의 원인일 수 있음.
   이를 확인하려면 압력 센서(PS1~PS6)의 평균값이 정상 범위보다
   낮은지 봐야 함. 그 데이터가 없으니 추가 분석 요청."

--- Round 2: 가설 검증 ---
LLM → get_pressure_stats(1042)
  ← PS1 평균: 138.2 bar (정상 평균 155.4 대비 -11%)
     PS2 평균: 104.1 bar (정상 평균 118.3 대비 -12%)
     압력 변동계수(CV): 0.18 (정상 평균 0.09 대비 2배)

LLM 내부 추론:
  "압력이 전반적으로 낮고 변동이 크다. 가설 뒷받침됨.
   추가로: 이 정도 압력 저하가 냉각기 효율에도 영향 줬는지 확인."

--- Round 3: 추가 검증 ---
LLM → get_cooling_efficiency(1042)
  ← 냉각 효율(CE) 평균: 71.3% (정상 평균 91.2% 대비 -22%)

LLM 내부 추론:
  "냉각 효율 저하 확인. 압력 저하 → 유량 감소 → 냉각 효율 저하로
   이어지는 연쇄가 데이터로 확인됨. 충분한 근거 확보."

--- 루프 종료: finish_reason = "stop" ---

[LLM 최종 응답]
  근본 원인: 내부 펌프 누수 (확률 79%)
  연쇄 영향: 압력 11~12% 저하 → 밸브 심각 지연 + 냉각 효율 22% 저하
  불확실성: 펌프 누수 확률이 79%로 다소 낮음. 확진을 위해 실물 점검 필요
  권장 조치: 펌프 점검(즉시) → 밸브 교체(3일 내) → 냉각기 점검(1주 내)
```

### 루프 메커니즘 코드 구조

```python
messages = [system_prompt, user_message]

while True:
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=ALL_TOOLS,           # 고정 분류기 4개 + on-demand 분석 툴들
        tool_choice="auto",        # LLM이 자유롭게 선택
    )

    if response.choices[0].finish_reason == "stop":
        # LLM이 "더 이상 툴 안 써도 됨"이라고 판단 → 최종 답변 반환
        return response.choices[0].message.content

    elif response.choices[0].finish_reason == "tool_calls":
        # LLM이 툴 요청 → 실행 → 결과를 messages에 추가 → 루프 재진입
        tool_results = execute_tools(response.choices[0].message.tool_calls)
        messages.append(response.choices[0].message)         # LLM의 tool call 메시지
        messages.extend(tool_results)                        # 툴 실행 결과
        # → 다시 while 루프 상단으로
```

**핵심**: LLM이 `finish_reason == "stop"`을 낼 때까지 루프가 돌아감.
LLM이 "충분하다"고 판단하면 스스로 멈춤. 개발자가 언제 멈출지 결정하지 않음.

---

## 4. 툴 목록 설계

### Group A: 고정 진단 툴 (항상 존재, 에이전트가 필요 시 호출)

| 툴 이름 | 기능 | 반환값 |
|--------|------|--------|
| `classify_cooler(cycle_id)` | RF 모델로 냉각기 상태 분류 | {상태, 클래스별 확률} |
| `classify_valve(cycle_id)` | RF 모델로 밸브 상태 분류 | {상태, 클래스별 확률} |
| `classify_pump(cycle_id)` | RF 모델로 펌프 누수 분류 | {상태, 클래스별 확률} |
| `classify_accumulator(cycle_id)` | RF 모델로 어큐뮬레이터 분류 | {상태, 클래스별 확률} |

### Group B: On-demand 검증 툴 (LLM이 가설 검증 시 선택적으로 호출)

| 툴 이름 | 기능 | LLM이 왜 쓰는가 |
|--------|------|----------------|
| `get_pressure_stats(cycle_id)` | 압력 센서 6개의 평균, 표준편차, 정상 대비 편차 | "압력이 낮은지 확인하려고" |
| `get_flow_stats(cycle_id)` | 유량 센서 2개의 평균, 변동 | "유량 감소가 있는지 확인하려고" |
| `get_temperature_stats(cycle_id)` | 온도 센서 4개의 평균, 정상 대비 편차 | "온도 이상이 있는지 확인하려고" |
| `get_cooling_efficiency(cycle_id)` | CE/CP/SE 센서 평균 | "냉각 성능 저하 규모 확인하려고" |
| `compare_to_normal_baseline(cycle_id, sensor_group)` | 해당 사이클 vs. 정상 사이클 평균 비교 | "이게 얼마나 비정상인지 수치로 확인하려고" |
| `get_sensor_correlation(cycle_id, sensor_a, sensor_b)` | 두 센서 간 해당 사이클 내 상관계수 | "A가 B에 영향을 주는지 수치로 확인하려고" |
| `get_similar_cycles(cycle_id, n=5)` | 가장 유사한 과거 사이클 N개와 실제 레이블 | "비슷한 과거 사례에서 결과가 어땠는지 확인하려고" |
| `get_ml_feature_importance(component)` | 해당 부품 RF 모델의 feature importance 상위 5개 | "이 예측에서 어떤 센서가 결정적이었는지 확인하려고" |

**설계 원칙**:
- 툴은 결과만 반환, 해석은 LLM이 함
- 정상 baseline은 전체 사이클 중 4개 부품 모두 정상인 사이클들의 평균으로 사전 계산
- 모든 수치는 "정상 대비 %"를 함께 제공 (LLM이 판단하기 쉽도록)

---

## 5. 에이전트 방식 선택: 세 가지 옵션 비교

### 옵션 1: OpenAI Function Calling 직접 구현 (권장)

**동작 방식**:
```
개발자가 while 루프를 직접 작성 → OpenAI API 호출 → tool_calls 감지
→ 툴 실행 → messages에 결과 추가 → 재호출 → ... → stop 감지 → 종료
```

**장점**:
- 루프가 완전히 투명함 → 에이전트가 무슨 이유로 어떤 툴을 호출했는지 그대로 로그로 출력 가능
- 의존성 없음 (openai 패키지만 있으면 됨)
- 이 프로젝트의 가설 검증 루프를 정확히 구현 가능
- 이해하기 쉬움 → 나중에 커스터마이징 쉬움

**단점**:
- 루프, 에러 처리, 툴 실행 로직을 직접 작성해야 함 (하지만 복잡하지 않음)

**코드 규모**: agent.py 약 150~200줄

---

### 옵션 2: LangChain Agent

**동작 방식**:
```
LangChain이 루프를 대신 관리
개발자는 Tool 객체만 정의하고, AgentExecutor.run("분석해줘") 호출
```

**장점**:
- 루프, 메모리, 로깅이 프레임워크에 내장됨
- ReAct, OpenAI Functions Agent 등 다양한 에이전트 전략 선택 가능
- 더 복잡한 시스템(멀티 에이전트, 메모리 등)으로 확장하기 용이

**단점**:
- 추상화 레이어가 두꺼움 → 에이전트 내부에서 무슨 일이 일어나는지 파악하기 어려움
- LangChain 버전 변경이 잦고 API가 자주 바뀜
- 이 프로젝트 규모에서는 오버엔지니어링
- "가설을 세우고 검증한다"는 흐름을 LangChain이 따로 지원하지 않음 → 어차피 커스터마이징 필요

**코드 규모**: tool 정의 100줄 + LangChain 설정 50줄

---

### 옵션 3: 직접 파싱 (function calling 미사용)

**동작 방식**:
```
LLM에게 "추가 분석이 필요하면 [TOOL: tool_name] 형식으로 써줘"라고 지시
→ LLM 응답에서 [TOOL: ...] 패턴을 정규식으로 파싱 → 툴 실행 → 결과 재입력
```

**장점**: OpenAI 외 다른 LLM(Claude, Gemini 등)에도 동일한 코드 사용 가능

**단점**:
- 파싱이 깨질 수 있음 (LLM이 형식을 정확히 안 지킬 때)
- Function calling보다 신뢰성 낮음
- 멀티 툴 동시 호출이 어려움

---

### 결론: 옵션 1 (OpenAI Function Calling 직접 구현)

이유:
1. 가설 검증 루프가 "while → tool_calls 감지 → 실행 → 재호출"과 정확히 일치
2. Streamlit에서 에이전트 로그를 실시간으로 보여주려면 루프를 직접 제어해야 함
3. Step 1과 동일한 OpenAI 직접 호출 방식으로 일관성 유지
4. 복잡도가 낮아서 코드를 완전히 이해할 수 있음

---

## 6. 구현 단계

### Phase 1: 데이터 전처리 (`preprocess.py`)

**목표**: 60초 사이클의 시계열 → feature 벡터 1개 + 정상 baseline 계산

```
feature = [
  PS1_mean, PS1_std, PS1_max, PS1_min,  # 압력 (100Hz → 6000샘플 → 통계 4개)
  PS2_mean, PS2_std, PS2_max, PS2_min,
  ... (PS3~PS6)
  FS1_mean, FS1_std, FS1_max, FS1_min,  # 유량 (10Hz → 600샘플)
  FS2_mean, FS2_std, FS2_max, FS2_min,
  TS1_mean, TS1_std,                     # 온도 (1Hz → 60샘플, std만)
  ... (TS2~TS4)
  VS1_mean, VS1_std,
  CE_mean, CP_mean, SE_mean              # 냉각/효율 (1Hz)
]
```

추가로: 4개 부품 모두 정상인 사이클들의 baseline 평균 계산 후 `baseline.pkl`로 저장

---

### Phase 2: ML 모델 학습 (`train_models.py`)

**모델**: Random Forest (다중 클래스 확률 출력 지원)

| 모델 | 타겟 | 클래스 수 |
|------|------|----------|
| `model_cooler.pkl` | 냉각기 상태 | 3 |
| `model_valve.pkl` | 밸브 상태 | 4 |
| `model_pump.pkl` | 펌프 누수 | 3 |
| `model_accumulator.pkl` | 어큐뮬레이터 | 4 |

학습 후 각 모델 정확도, F1 점수, feature importance 출력 및 저장

---

### Phase 3: 에이전트 구현 (`agent.py`)

```
DiagnosticAgent 클래스
  ├── tools: Group A (4개 분류기) + Group B (8개 검증 툴) 정의
  ├── run(cycle_id): 멀티 라운드 while 루프
  │     while True:
  │       response = openai API 호출
  │       if finish_reason == "stop": return 최종 응답
  │       if finish_reason == "tool_calls":
  │           툴 실행 → messages 업데이트 → continue
  └── get_log(): 툴 호출 순서, 이유, 결과 반환 (UI용)
```

---

### Phase 4: Streamlit 앱 (`app.py`)

**화면 구성:**

```
┌─────────────────────────────────────────────────────────┐
│  [사이드바]                                              │
│  사이클 선택: [랜덤] or [수동 입력 #___]                 │
│  실제 정답 보기: [ON/OFF]                                │
│  배치 평가: [N개 실행]                                   │
├─────────────────────────────────────────────────────────┤
│  [메인]                                                  │
│  사이클 #1042  압력: 138.2 bar  유량: 12.1 L/min  온도: 52.3℃  │
│                                                         │
│  [에이전트 분석 실행] 버튼                               │
│                                                         │
│  ▼ 에이전트 실행 로그                                   │
│  [Round 1] classify_cooler 호출                         │
│  → 결과: 성능 저하 (87%)                                │
│  [Round 1] classify_valve 호출                          │
│  → 결과: 심각한 지연 (88%)                              │
│  [Round 1] classify_pump 호출                           │
│  → 결과: 약한 누수 (79%)                                │
│  [Round 2] get_pressure_stats 호출                      │
│  → 사유: "펌프 누수 → 압력 저하 가설 검증"              │  ← 이게 핵심
│  → 결과: PS1 평균 138.2 bar (정상 대비 -11%)            │
│  [Round 3] get_cooling_efficiency 호출                  │
│  → 사유: "압력 저하 → 냉각 효율 영향 확인"              │
│  → 결과: CE 71.3% (정상 대비 -22%)                      │
│                                                         │
│  ▼ LLM 최종 판단 (스트리밍)                             │
│  근본 원인: 내부 펌프 누수...                            │
│                                                         │
│  ▼ 정답 비교 (ON인 경우)                                │
│  냉각기: 예측 "성능저하" / 실제 "성능저하" ✓            │
│  밸브:   예측 "심각한지연" / 실제 "심각한지연" ✓        │
│  펌프:   예측 "약한누수" / 실제 "없음" ✗                │
└─────────────────────────────────────────────────────────┘
```

---

## 7. 파일 구조

```
step2_hydraulic_agent/
├── data/                          # UCI Hydraulic 원본 데이터 (수동 다운로드)
│   ├── PS1.txt ~ PS6.txt
│   ├── FS1.txt, FS2.txt
│   ├── TS1.txt ~ TS4.txt
│   ├── VS1.txt, EPS1.txt
│   ├── CE.txt, CP.txt, SE.txt
│   └── profile.txt
├── preprocess.py
├── train_models.py
├── models/
│   ├── model_cooler.pkl
│   ├── model_valve.pkl
│   ├── model_pump.pkl
│   ├── model_accumulator.pkl
│   ├── features.pkl               # 전처리된 feature 벡터 (2205 × N)
│   └── baseline.pkl               # 정상 사이클 평균값
├── agent.py
└── app.py
```

---

## 8. 검증 목표

| 검증 항목 | 방법 |
|----------|------|
| ML 4개 모델 개별 정확도 | train/test split 후 accuracy, F1 측정 |
| LLM 복합 판단 정확도 | 배치 평가: 예측 4개 부품 상태 vs. 실제 레이블 |
| LLM이 가설 검증 툴을 적절히 쓰는가 | 툴 호출 로그에서 "사유"가 가설과 일치하는지 정성 평가 |
| LLM이 가설을 수정하는가 | 추가 분석 결과가 가설과 다를 때 결론을 바꾸는지 확인 |
| LLM이 불확실성을 인식하는가 | 확률 낮은 케이스에서 "불확실" 언급 여부 |

---

## 9. 구현 순서

```
① 데이터 다운로드 (UCI 또는 Kaggle)
② preprocess.py → feature 벡터 + baseline 계산
③ train_models.py → 4개 모델 학습 + 성능 확인
④ agent.py → 툴 정의 + while 루프 구현
⑤ app.py → Streamlit UI
⑥ 검증 실험
```

---

*계획 완료. 구현 시작 전 데이터 다운로드 필요.*
