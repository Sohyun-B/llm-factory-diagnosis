# Hill of Towie SCADA 데이터셋

> 출처: Zenodo 14870023 (CC-BY-4.0)
> 분석 코드: https://github.com/resgroup/hill-of-towie-open-source-analysis
> 작성 기준: 2021.zip 실제 파일 직접 분석 결과 (2026-03-04)

---

## 1. 개요

| 항목 | 내용 |
|------|------|
| 풍력단지 | Hill of Towie (스코틀랜드) |
| 터빈 | 21기, Siemens SWT-2.3-VS-82 |
| 정격 출력 | 2,300 kW (2.3 MW) |
| 허브 높이 | 59 m |
| 로터 직경 | 82 m |
| 상업 운전 시작 | 2012-05-12 (전 기기 동일) |
| 수집 기간 | 2016년 1월 ~ 2024년 8월 (8.7년) |
| 샘플링 | 10분 평균 통계 |
| 총 크기 | 12.6 GB (연도별 zip) |
| 라이선스 | CC-BY-4.0 |

---

## 2. 터빈 위치 (T01~T21)

모든 터빈이 스코틀랜드 Hill of Towie 단지에 위치. 위도 57.499~57.517°N, 경도 3.034~3.089°W 범위.

| ID | 위도 | 경도 | Station ID |
|----|------|------|------------|
| T01 | 57.4992 | -3.0867 | 2304510 |
| T02 | 57.4963 | -3.0828 | 2304511 |
| T03 | 57.5021 | -3.0890 | 2304512 |
| T04 | 57.5020 | -3.0821 | 2304513 |
| T05 | 57.4989 | -3.0781 | 2304514 |
| T06 | 57.5002 | -3.0713 | 2304515 |
| T07 | 57.5051 | -3.0859 | 2304516 |
| T08 | 57.5047 | -3.0775 | 2304517 |
| T09 | 57.5083 | -3.0826 | 2304518 |
| T10 | 57.5054 | -3.0707 | 2304519 |
| T11 | 57.5118 | -3.0807 | 2304520 |
| T12 | 57.5108 | -3.0737 | 2304521 |
| T13 | 57.5167 | -3.0781 | 2304522 |
| T14 | 57.5138 | -3.0749 | 2304523 |
| T15 | 57.4994 | -3.0628 | 2304524 |
| T16 | 57.5051 | -3.0533 | 2304525 |
| T17 | 57.5066 | -3.0478 | 2304526 |
| T18 | 57.5043 | -3.0412 | 2304527 |
| T19 | 57.5086 | -3.0417 | 2304528 |
| T20 | 57.5120 | -3.0404 | 2304529 |
| T21 | 57.5098 | -3.0347 | 2304530 |

---

## 3. 파일 구조

```
Zenodo 14870023/
├── 2016.zip ~ 2024.zip          ← 연도별 데이터 (각 1.3~1.5 GB)
│   └── tblXxx_YYYY_MM.csv       ← 테이블별 월별 CSV (연도당 156개 파일)
├── Hill_of_Towie_ShutdownDuration.zip  ← 다운타임 기록 (18.9 MB)
├── Hill_of_Towie_turbine_metadata.csv  ← 터빈 위치/스펙
├── Hill_of_Towie_tables_description.csv
├── Hill_of_Towie_turbine_fields_description.csv
├── Hill_of_Towie_grid_fields_description.csv
├── Hill_of_Towie_alarms_description.csv
└── Hill_of_Towie_AeroUp_install_dates.csv
```

### 연도별 zip 내부 테이블 구조 (실제 확인)

| 테이블명 | 실제 행 수 (2021년) | 컬럼 수 | 내용 |
|----------|--------------------|---------|----- |
| `tblAlarmLog` | 799,369 | 4 | 알람/이벤트 로그 |
| `tblSCTurGrid` | 93,277 | 52 | 발전·전력 계통 측정값 (10분) |
| `tblSCTurPress` | 확인 | 46 | 압력 측정값 (10분) |
| `tblSCTurTemp` | 93,277 | 126 | 온도 측정값 (10분) |
| `tblSCTurbine` | 1,091,166 | 85 | 풍속·RPM·피치·요 등 (10분) |
| `tblSCTurFlag` | 93,277 | 44 | 운전 상태 시간 정보 (10분) |
| `tblSCTurDigiIn` | — | — | 디지털 입력 신호 |
| `tblSCTurDigiOut` | — | — | 디지털 출력 신호 |
| `tblSCTurCount` | — | — | 카운터 신호 |
| `tblSCTurIntern` | 93,286 | 15 | 기타 내부 신호 (최소) |
| `tblDailySummary` | — | — | 일별 집계 |
| `tblGrid` | — | — | 계통 모니터링 스테이션 |
| `tblGridScientific` | — | — | 계통 모니터링 + 계산값 |

**참고**: tblSCTurbine은 21기 전체 포함이므로 93,277 × 21 ≒ 1,091,166행.
나머지 10분 테이블은 93,277행 = 21기 × ~4,442 타임스탬프.

---

## 4. 핵심 센서 필드 (실제 컬럼명 기준)

각 10분 통계 테이블은 `min / max / mean / stddev` 4개 suffix를 가진다.
일부 신호는 추가로 `endvalue` (구간 마지막 값) 또는 `counts` (전환 횟수) suffix를 가진다.

### 4-1. 주요 운전 신호 (tblSCTurbine, 85컬럼)

| 컬럼명 (mean 기준) | 설명 | 단위 |
|---------------------|------|------|
| `wtc_AcWindSp_mean` | 풍속 (활성 풍속계) | m/s |
| `wtc_PrWindSp_mean` | 풍속 (1차 풍속계) | m/s |
| `wtc_SeWindSp_mean` | 풍속 (2차 풍속계) | m/s |
| `wtc_ActualWindDirection_mean` | 실제 풍향 | deg |
| `wtc_NacelPos_mean` | 나셀 요각 (북 기준) | deg |
| `wtc_YawPos_mean` | 요 위치 | deg |
| `wtc_GenRpm_mean` | 발전기 RPM | rpm |
| `wtc_MainSRpm_mean` | 주축 RPM | rpm |
| `wtc_PitcPosA_mean` | 블레이드 A 피치각 | deg |
| `wtc_PitcPosB_mean` | 블레이드 B 피치각 | deg |
| `wtc_PitcPosC_mean` | 블레이드 C 피치각 | deg |
| `wtc_PitchRef_BladeA_mean` | 블레이드 A 피치 명령값 | deg |
| `wtc_PitchRef_BladeB_mean` | 블레이드 B 피치 명령값 | deg |
| `wtc_PitchRef_BladeC_mean` | 블레이드 C 피치 명령값 | deg |
| `wtc_TwrHumid_mean` | 타워 내부 습도 | % |
| `wtc_TetAnFrq_mean` | 타워 진동 주파수 | Hz |
| `wtc_TowerFrq_mean` | 타워 고유 주파수 | Hz |

**결측값**: 주요 신호(풍속, RPM, 피치각) 모두 0% 결측 (2021년 기준)

### 4-2. 발전·전력 신호 (tblSCTurGrid, 52컬럼)

| 컬럼명 | 설명 | 단위 |
|--------|------|------|
| `wtc_ActPower_mean` | 활성 전력 (발전량) | kW |
| `wtc_ActPower_endvalue` | 구간 마지막 출력값 | kW |
| `wtc_RawPower_mean` | 원시 전력 (보정 전) | kW |
| `wtc_ReactPwr_mean` | 무효 전력 | kVar |
| `wtc_CosPhi_mean` | 역률 | - |
| `wtc_GridFreq_mean` | 계통 주파수 | Hz |
| `wtc_AmpPhR/S/T_mean` | 전류 R/S/T상 | A |
| `wtc_VoltPhR/S/T_mean` | 전압 R/S/T상 | V |
| `wtc_ActRegSt_endvalue` | 활성 제어 상태 | - |

**결측값**: wtc_ActPower_mean, wtc_CosPhi_mean 모두 0% 결측

### 4-3. 온도 신호 (tblSCTurTemp, 126컬럼) — 진단 핵심

**실제 확인된 온도 신호 (description.csv 기술과 일부 다름)**

| 컬럼명 (mean) | 설명 | 비고 |
|---------------|------|------|
| `wtc_AmbieTmp_mean` | 주변(외부) 온도 | |
| `wtc_Gen1U1Tm_mean` | 발전기 1U 권선 온도 | |
| `wtc_Gen1V1Tm_mean` | 발전기 1V 권선 온도 | |
| `wtc_Gen1W1Tm_mean` | 발전기 1W 권선 온도 | description.csv에는 6개로 기술되었으나 실제 3개 |
| `wtc_GenBeGTm_mean` | 발전기 베어링 G측 온도 | |
| `wtc_GenBeRTm_mean` | 발전기 베어링 R측 온도 | description.csv에는 4개로 기술되었으나 실제 2개 |
| `wtc_GeOilTmp_mean` | 기어박스 오일 온도 | |
| `wtc_HSGenTmp_mean` | 기어박스 HS 베어링 (발전기측) | |
| `wtc_HSRotTmp_mean` | 기어박스 HS 베어링 (로터측) | |
| `wtc_IMSGenTm_mean` | 기어박스 IMS 베어링 (발전기측) | |
| `wtc_IMSRotTm_mean` | 기어박스 IMS 베어링 (로터측) | |
| `wtc_MainBTmp_mean` | 주 베어링 온도 | |
| `wtc_HubTemp_mean` | 허브 온도 | |
| `wtc_NacelTmp_mean` | 나셀 내부 온도 | |
| `wtc_HydOilTm_mean` | 피치 유압 오일 온도 | |
| `wtc_TraOilTF_mean` | 변압기 오일 온도 | |
| `wtc_TraRooTF_mean` | 변압기실 온도 | |
| `wtc_ConvWTmp_mean` | 컨버터 냉각수 온도 | |
| `wtc_BrkTmpGn_mean` | 브레이크 온도 (발전기측) | |
| `wtc_DeltaTmp_mean` | 델타 온도 (차이) | |
| `wtc_ReacUTmp_mean` / `ReacVTmp` / `ReacWTmp` | 리액터 U/V/W 온도 | |
| `wtc_GFilB1Tm_mean` / `GFilB2Tm` / `GFilB3Tm` | 발전기 필터 블레이드 온도 | |
| `wtc_A1ExtTmp_mean` | 외부 온도 A1 | |
| `wtc_A3LefTmp_mean` / `A3RigTmp` | A3 좌/우 온도 | |
| `wtc_A9IntTmp_mean` | 내부 온도 A9 | |
| `wtc_A21IntTm_mean` | 내부 온도 A21 | |

### 4-4. 압력 신호 (tblSCTurPress, 46컬럼)

| 컬럼명 | 설명 | 단위 |
|--------|------|------|
| `wtc_BrakPres_mean` | 브레이크 오일 압력 | bar |
| `wtc_GearPres_mean` | 기어 오일 압력 | bar |
| `wtc_HubPresA/B/C_mean` | 허브 유압 A/B/C (피치 실린더) | bar |
| `wtc_HydPress_mean` | 유압 시스템 압력 | bar |
| `wtc_InlPrBef_mean` | 인렛 필터 전 압력 | bar |
| `wtc_InlPrAft_mean` | 인렛 필터 후 압력 | bar |
| `wtc_OfflPres_mean` | 오프라인 압력 | bar |
| `wtc_InvPress_mean` | 인버터 냉각수 압력 | bar |
| `wtc_BrAccPrs_mean` | 브레이크 어큐뮬레이터 압력 | bar |

### 4-5. 운전 상태 플래그 (tblSCTurFlag, 44컬럼)

| 컬럼명 | 설명 | 단위 |
|--------|------|------|
| `wtc_ScInOper_timeon` | 해당 10분 구간 중 운전 시간 | 초 |
| `wtc_ScReToOp_timeon` | 운전 대기 상태 시간 | 초 |
| `wtc_ScTurSto_timeon` | 터빈 에러 활성 시간 | 초 |
| `wtc_ScEnvSto_timeon` | 환경 조건 정지 시간 | 초 |
| `wtc_ScComSto_timeon` | 통신 정지 시간 | 초 |
| `wtc_ScGrdSto_timeon` | 계통 정지 시간 | 초 |
| `wtc_ScBrakOp_timeon` | 브레이크 동작 시간 | 초 |
| `wtc_ScWindIR_timeon` | 풍속 감지 시간 | 초 |
| `wtc_OpCode_endvalue` | 운전 코드 (상태 요약) | - |
| `wtc_AlarmCde_endvalue` | 현재 알람 코드 | - |
| `wtc_Turbstat_endvalue` | 터빈 전체 상태 | - |
| `wtc_ScYawOpe_counts` | 요 동작 횟수 | - |
| `wtc_ScAStart_counts` | 자동 기동 횟수 | - |

### 4-6. 내부 신호 (tblSCTurIntern, 15컬럼) — 최소

| 컬럼명 | 설명 |
|--------|------|
| `wtc_ValSuppV_mean` | 밸브 공급 전압 |
| `wtc_AnaPiRef_mean` | 아날로그 피치 기준값 |
| `wtc_DataLink_RecvSec_mean` | 데이터 링크 수신 시간 |
| `wtc_OrStpDat_Status_endvalue` | 운영 정지 데이터 상태 |
| `wtc_OrStpDat_LampStat_endvalue` | 운영 정지 데이터 램프 상태 |

---

## 5. 알람 로그 (tblAlarmLog) — 실제 확인 결과

### 실제 구조

| 컬럼 | 설명 | 비고 |
|------|------|------|
| `TimeOn` | 알람 시작 시각 (UTC) | 예: `2021-01-03 22:15:45` |
| `TimeOff` | 알람 종료 시각 (UTC) | **NaN이 88%** — 대부분 종료 미기록 |
| `StationNr` | 터빈 식별자 | Station ID (2304510=T01 ~ 2304530=T21) |
| `Alarmcode` | 알람 코드 | 정수 |

### 실제 알람 규모 (2021년)

| 항목 | 수치 |
|------|------|
| 총 알람 행 수 | 799,369건 |
| 고유 알람 코드 수 | **284개** |
| TimeOff = NaN 비율 | 88% (704,258건) |
| description.csv 기술 코드 | 12개 (전체의 4%) |

### description.csv에 기술된 12개 알람 코드

alarms_description.csv는 12개 "주요" 코드만 기술함. 실제 데이터에는 284개의 고유 코드가 존재.

| 알람 코드 | 설명 | 정지 여부 | 2021년 발생 횟수 |
|-----------|------|----------|-|
| 20 | Large generator Cut-in | 아니오 | 331,825 (정상 운전 사이클) |
| 25 | Fast cut-out of generator | 아니오 | 331,821 (정상 운전 사이클) |
| 102 | Ice detection | 아니오 | 3 |
| 1005 | Availability - low wind | **정지** | 1,857 |
| 3130 | Pitch lubrication | **정지** | 1,401 |
| 8000 | Windspeed too high to operate | **정지** | 51 |
| 8210 | Stopped, due to icing | **정지** | 0 (미발생) |
| 8230 | Ice detection: Low torque | **정지** | 91 |
| 8234 | Ice detection: No cut in | **정지** | 0 (미발생) |
| 8235 | Ice Detect: Stopped | **정지** | 0 (미발생) |
| 8236 | Ice Detect: Stopped, De-Ice | **정지** | 0 (미발생) |
| 10105 | Stopped, untwisting cables | **정지** | 634 |

### 주요 미기술 알람 코드 (top 발생 코드)

| 알람 코드 | 2021년 발생 횟수 | 코드 계열 추정 |
|-----------|----------------|----------------|
| 50346 | 73,631 | 5xxxx 계열: 제어 시스템 |
| 115 | 6,531 | 1xx: 발전기/계통 |
| 127 | 5,526 | 1xx: 발전기/계통 |
| 111 | 4,216 | 1xx: 발전기/계통 |
| 68, 67, 69 | 각 2,408 | 피치 시스템 |
| 3xxx 계열 | 다수 | 피치/드라이브트레인 |
| 13xxx, 14xxx, 15xxx 계열 | 다수 | 외부 모니터링 시스템 |

**중요 관찰**: 코드 20(발전기 cut-in)과 25(cut-out)가 전체 알람의 83%를 차지하며 이는 **정상 운전 사이클** 신호. 실제 이상/정지 관련 코드는 3xxx, 5xxx, 7xxx, 8xxx, 1xxx 계열에 존재.

---

## 6. ShutdownDuration (다운타임 기록)

### 구조 (실제 확인)

| 컬럼 | 설명 |
|------|------|
| `TimeStamp_StartFormat` | 10분 구간 시작 시각 (UTC timezone-aware) |
| `TurbineName` | 터빈 이름 (T01~T21) |
| `ShutdownDuration` | 해당 10분 구간 중 정지 시간 (초, 0~600) |

### 통계

| 항목 | 수치 |
|------|------|
| 전체 기간 행 수 | 9,574,005 (2016~2024 전체) |
| 2021년 행 수 | 1,103,760 = 21기 × 52,560 구간 |
| 2021년 비정지 구간 | 95% (ShutdownDuration = 0) |
| 2021년 정지 구간 | 56,699건 (5%) |
| ShutdownDuration 최대값 | 600초 (전체 10분 구간 정지) |

### 활용 방법

이상 감지 모델의 레이블로 사용:
- `ShutdownDuration = 0`: 정상 운전
- `ShutdownDuration > 0`: 해당 구간에 정지 발생 (부분 또는 전체)
- `ShutdownDuration = 600`: 10분 전체 정지

`tblSCTurFlag.wtc_ScTurSto_timeon`과 교차 검증 가능.

---

## 7. 추가 파일

### AeroUp_install_dates.csv
- 일부 터빈에 AeroUp(블레이드 선단 개조) 설치 일자 기록
- 설치 전후 파워 커브 비교 분석에 활용 (GitHub 분석 코드의 주요 활용 목적)
- Step 4에서는 직접 활용하지 않음 (2021년 데이터 기준)

---

## 8. 이 데이터셋의 특성과 한계

### 강점
- 8.7년 장기 실제 운영 데이터 (신뢰도 높음)
- 21기 fleet 비교 가능
- 온도 센서가 풍부 (발전기 권선 3개, 베어링 2개, 기어박스 4개, 기타 다수)
- ShutdownDuration으로 이상 감지 검증 가능
- 알람 로그가 예상보다 풍부 — 284개 고유 코드, 2021년 약 80만 건
- 타임스탬프 모두 UTC로 통일

### 한계
- description.csv에 12개 알람만 설명됨 (나머지 272개 코드는 설명 없음)
- 실제 정비 기록(MetroPT의 failure_events 같은 것) 없음
- 장비 이상의 정답 라벨 없음 — 이상 감지 결과를 ShutdownDuration과 비교
- tblSCTurTemp: description.csv가 6개 발전기 권선 온도, 4개 베어링 온도로 기술했으나 실제는 3개 권선, 2개 베어링 온도
- tblSCTurIntern: 15컬럼으로 매우 제한적 (피치 기준값, 밸브 전압만 유의미)

---

## 9. Step 4에서의 활용 방향

| 역할 | MetroPT (Step 3) | Hill of Towie (Step 4) |
|------|-----------------|----------------------|
| RAG 핵심 문서 | 정비 보고서 (자연어) | 알람 코드 설명(12개) + 이벤트 이력(284코드) + 도메인 지식 |
| 이상의 기준 | 단일 장비 baseline 대비 | **파워 커브 이탈 + 이웃 터빈 비교** |
| LLM 추론 핵심 | 센서 이상 원인 추론 | **왜 이 터빈만 출력이 낮은가** |
| 온도 정보 | Oil temperature 1개 | 발전기/기어박스/베어링 등 20개 이상 |
| 알람 로그 | LPS 알람 4건 | 284 코드, 연 80만 건 (미기술 코드 포함) |

장비 이상 감지는 **파워 커브 이탈**과 **온도 이상**이 주요 신호.
알람 로그는 "이 구간에 환경적/시스템적 원인이 있었는가"를 확인하는 용도.
미기술 알람 코드는 코드 번호 계열로 유형을 추정하거나 발생 패턴만 활용.
