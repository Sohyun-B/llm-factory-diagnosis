# Step 4 계획: Hill of Towie — 풍력 터빈 다중 장비 이상 진단

> 작성일: 2026-03-04
> 데이터셋: Hill of Towie SCADA (Zenodo 14870023)
> 핵심 추가: 단일 장비 → 다중 장비(Fleet) 비교 기반 이상 진단
> 상태: 초안 (데이터셋 분석 전)

---

## 1. Step 3과의 핵심 차이

| 항목 | Step 3 (MetroPT) | Step 4 (Hill of Towie) |
|------|-----------------|----------------------|
| 장비 수 | 단일 APU | 터빈 21기 |
| 데이터 기간 | 7개월 | 8.7년 (2016~2024) |
| 변수 수 | 15개 | 655개 |
| 이벤트 로그 | 자연어 정비 보고서 4건 | 알람 코드 + description.csv 텍스트 |
| 새로운 진단 축 | 없음 | 이웃 터빈 비교 (fleet-level) |
| 이상의 기준 | 정상 baseline 대비 편차 | 파워 커브 이탈 + 이웃 터빈 비교 |

Step 1~3은 단일 장비의 센서 이상을 감지하고 원인을 추론했다.
Step 4는 "같은 바람을 받는 21기 중 이 터빈만 왜 출력이 낮은가?"라는
fleet-level 비교를 핵심 진단 축으로 추가한다.

---

## 2. 데이터셋 개요

| 항목 | 내용 |
|------|------|
| 출처 | Zenodo 14870023 |
| 라이선스 | CC-BY-4.0 |
| 터빈 | 21기 (Siemens SWT-2.3-VS-82, 정격 2.3 MW, 로터 82m) |
| 기간 | 2016년 1월 ~ 2024년 8월 (8.7년) |
| 샘플링 | 10분 평균 통계 |
| 변수 수 | 655개 |
| 총 크기 | 12.6 GB (연도별 zip) |
| 분석 코드 | https://github.com/resgroup/hill-of-towie-open-source-analysis |

### 파일 구성 (연도별 zip)
```
2021.zip
├── 10분 SCADA 통계  ← 터빈별 센서값
└── 알람 로그        ← 알람 코드 + 타임스탬프
*_description.csv    ← 알람 코드별 텍스트 설명 (별도 다운로드)
Hill_of_Towie_turbine_metadata.csv ← 터빈 좌표/ID
Hill_of_Towie_ShutdownDuration.zip ← 다운타임 기록
```

### 주요 센서 신호 (10분 통계)
- **Active Power** (avg/std): 발전량 — 핵심 성능 지표
- **Wind Speed** (avg/std): 풍속
- **Generator RPM** (avg): 발전기 회전수
- **Pitch Angle A/B/C** (avg): 블레이드 3개의 피치각
- **Yaw** (avg/min/max): 요각 (풍향 추적)
- **Ambient Temperature** (avg): 주변 온도

---

## 3. 핵심 진단 축

### 축 1: 파워 커브 이탈 감지
정상 터빈은 풍속과 출력 사이에 안정적인 곡선이 존재한다.
같은 풍속에서 출력이 기대값보다 낮으면 블레이드 오염, 피치 오류, 발전기 이상을 의심한다.

```
풍속 8 m/s → 정상 출력: ~1,200 kW
풍속 8 m/s → 실제 출력:   ~800 kW  → 파워 커브 이탈
```

### 축 2: 이웃 터빈 비교 (Fleet Comparison)
같은 단지의 터빈들은 비슷한 바람을 받는다.
특정 시점에 한 터빈만 출력이 낮으면 바람 탓이 아니라 장비 이상이다.

```
같은 시점:
  T01: 풍속 8 m/s → 출력 1,150 kW (정상)
  T07: 풍속 8 m/s → 출력   720 kW (이상)
  T14: 풍속 8 m/s → 출력 1,180 kW (정상)
  → T07만 이탈 → 장비 문제 가능성
```

### 축 3: 알람 로그 RAG
알람 코드 + description.csv 텍스트 → 벡터 DB
LLM이 센서 이상과 관련된 알람 이력을 교차 검색.

---

## 4. 툴 목록 설계

### Group A: 진단 툴 (항상 호출)
| 툴 | 기능 |
|---|------|
| `detect_power_curve_deviation` | 파워 커브 이탈 감지 — 풍속 대비 출력 편차 |
| `compare_fleet` | 같은 시점 이웃 터빈들의 출력 비교 |

### Group B: 센서 분석 툴
| 툴 | 기능 |
|---|------|
| `get_sensor_trend` | 특정 시점 전후 센서 트렌드 |
| `get_pitch_stats` | 블레이드 피치각 통계 (A/B/C 불균형 감지) |
| `get_rpm_stats` | 발전기 RPM 패턴 분석 |

### Group C: RAG 툴
| 툴 | 기능 |
|---|------|
| `search_alarm_log` | 알람 코드 → 설명 텍스트 RAG 검색 |
| `search_domain_knowledge` | 풍력 터빈 도메인 지식 검색 |

---

## 5. ML 모델 설계

| 모델 | 입력 | 출력 |
|------|------|------|
| 파워 커브 이탈 감지기 | (풍속, 출력, 온도, RPM) | 이탈 점수 |
| 이상 분류기 | 이탈 패턴 피처 | 블레이드 / 피치 / 발전기 / 기타 |

이상 감지 방법 후보:
- 파워 커브 정규화 후 잔차(residual) 기반
- Isolation Forest
- 이웃 터빈 대비 출력 비율 기반

---

## 6. RAG 문서 구성 (초안)

| 타입 | 출처 | 건수 (예상) |
|------|------|-----------|
| `alarm_description` | description.csv — 알람 코드별 텍스트 | 실제 확인 필요 |
| `alarm_event` | 실제 알람 발생 이력 (타임스탬프 포함) | 실제 확인 필요 |
| `domain_knowledge` | 풍력 터빈 도메인 지식 (수동 작성) | ~15건 |

---

## 7. 파일 구조

```
step4_hilltowie_agent/
├── data/                      ← 2021.zip 압축 해제
├── preprocess.py              ← 파워 커브 정규화 + fleet 비교 피처
├── train_models.py            ← 이상 감지 모델 학습
├── build_rag.py               ← 알람 description + 이벤트 → 벡터 DB
├── models/
│   ├── power_curve_model.pkl
│   ├── anomaly_detector.pkl
│   └── vectorstore/
├── agent.py
└── app.py
```

---

## 8. 검증 목표

| 항목 | 방법 |
|------|------|
| 파워 커브 이탈 감지 정확도 | 다운타임 기록(ShutdownDuration)과 비교 |
| Fleet 비교의 유효성 | 이웃 터빈 출력과 비교해 이상 구간 식별 |
| 알람 RAG 활용 여부 | 툴 로그에서 search_alarm_log 호출 + 내용 |

---

## 9. 데이터 범위 결정

전체 12.6 GB는 과도하므로 2021년 1년치 (~1.5 GB)로 시작.
21기 전체 터빈 포함 (fleet 비교가 핵심이라 터빈 수 축소 불가).

---

## 10. 실제 데이터 분석 결과 반영 — 계획 최종 수정사항

> 2021.zip 전체 분석 완료 기준 (2026-03-04)

### 10-1. 알람 로그 재평가 (중요 — 초기 예상과 크게 다름)

**초기 예상**: description.csv 12개 코드 = 알람 전체
**실제**: 284개 고유 알람 코드, 2021년 799,369건

description.csv는 12개 "주요" 코드만 기술한 것이며, 실제 데이터에는 훨씬 풍부한 알람이 존재한다.
다만 272개 미기술 코드는 의미를 알 수 없어 RAG 문서로 직접 활용하기 어렵다.

**코드 20, 25가 전체의 83%** → 정상 발전기 운전 사이클 신호 (진단 불필요)
**실제 이상 관련 코드**: 3xxx(피치/드라이브트레인), 8xxx(환경 정지), 5xxx(제어), 1xxx(계통) 계열

→ **RAG 전략 수정**:
- 12개 기술된 알람: 환경 원인 확인 용도 (얼음, 강풍)
- 미기술 알람: 코드 범위만 RAG에 포함, 발생 패턴으로 이상 신호 판단
- 알람 이벤트 문서: 시간대별 알람 발생 밀도 + 코드 계열 요약 자동 생성

→ **이상 감지의 주요 신호**: **파워 커브 이탈 + 온도 이상** (알람은 보조)

### 10-2. 온도 센서 현황 수정 (description.csv와 실제 불일치)

| 항목 | description.csv 기술 | 실제 데이터 |
|------|---------------------|------------|
| 발전기 권선 온도 | 6개 (1U1~2W1) | **3개** (Gen1U1Tm, Gen1V1Tm, Gen1W1Tm) |
| 발전기 베어링 온도 | 4개 (GenBeG/R/I/O) | **2개** (GenBeGTm, GenBeRTm) |
| 추가 온도 (비기술) | — | BrkTmpGn, ConvWTmp, DeltaTmp, ReacU/V/WTmp, GFilB1/2/3Tm, A1/A3/A9/A21 계열 |

→ `get_temperature_stats` 툴 설계 시 실제 컬럼명 사용 필요

### 10-3. tblSCTurIntern — 거의 활용 불가

15컬럼 중 유의미한 신호: 피치 기준값(`wtc_AnaPiRef_mean`), 밸브 전압(`wtc_ValSuppV_mean`)만.
진단 툴에서 제외 (tblSCTurbine의 PitchRef_Blade 신호로 대체).

### 10-4. ShutdownDuration — 레이블로 적합

- 포맷: `[TimeStamp_StartFormat(UTC), TurbineName(T01~T21), ShutdownDuration(초,0~600)]`
- 2021년 정지 구간 비율: 5% (56,699 / 1,103,760)
- 이상 감지 모델의 검증 레이블로 직접 사용 가능
- 정지 원인 구분 없음 → `tblSCTurFlag.wtc_ScEnvSto_timeon` (환경) vs `wtc_ScTurSto_timeon` (장비) 비교 필요

### 10-5. 최종 툴 목록

#### Group A: 기초 진단 (항상 호출)
| 툴 | 기능 |
|---|------|
| `detect_power_curve_deviation` | 파워 커브 이탈 감지 (풍속 대비 출력 편차) |
| `compare_fleet` | 같은 시점 이웃 터빈 출력 비교 |
| `check_environmental_condition` | 환경 정지 알람 여부 확인 (얼음·강풍·저풍속) |

#### Group B: 심층 분석 툴
| 툴 | 기능 |
|---|------|
| `get_sensor_trend` | 특정 시점 전후 주요 센서 트렌드 |
| `get_temperature_stats` | 발전기·기어박스·베어링 온도 이상 분석 (실제 3+2+4개 컬럼) |
| `get_pitch_stats` | 블레이드 A/B/C 피치각 불균형 감지 (PitcPos vs PitchRef 비교) |
| `get_rpm_stats` | 발전기/주축 RPM 패턴 분석 |

#### Group C: RAG 툴
| 툴 | 기능 |
|---|------|
| `search_alarm_history` | 해당 시점 전후 알람 발생 이력 조회 (코드 + 계열 설명) |
| `search_domain_knowledge` | 풍력 터빈 도메인 지식 검색 |

### 10-6. 최종 RAG 문서 구성

| 타입 | 내용 | 건수 | 비고 |
|------|------|------|------|
| `alarm_description` | 12개 기술된 알람 코드 설명 | 12건 | description.csv 직접 변환 |
| `alarm_event` | 정지 유발 알람 발생 구간 요약 | 자동 (다수) | MetroPT LPS 방식 동일, ScTurSto/ScEnvSto_timeon > 0 구간 |
| `domain_knowledge` | 풍력 터빈 도메인 지식 | ~20건 | 파워 커브, 베어링 열화, 얼음 패턴, 피치 불균형 등 |

### 10-7. 확인된 사항 (미결 사항 해소)

| 항목 | 결과 |
|------|------|
| zip 내부 파일 형식 | 월별 CSV: `tblXxx_2021_MM.csv` (156개 파일/년) |
| tblAlarmLog 컬럼 | `[TimeOn, TimeOff, StationNr, Alarmcode]` — TimeOff NaN 88% |
| 알람 코드 실제 수 | **284개** (description.csv의 12개는 일부) |
| ShutdownDuration 포맷 | `[TimeStamp_StartFormat(UTC), TurbineName, ShutdownDuration(초)]` |
| 결측값 비율 (핵심 신호) | 풍속·RPM·피치·발전량 모두 **0% 결측** |
| tblSCTurIntern 내용 | 15컬럼, 피치기준값·밸브전압만 유의미 — 진단 활용 제한 |
