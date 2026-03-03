# Step 3 데이터셋 후보 조사

> 작성일: 2026-03-03
> 조건: 센서 시계열 + 이벤트 로그(타임스탬프 포함)가 **둘 다** 존재하는 공개 데이터셋
> 도메인: 공장 한정 아님

---

## 선정 기준

| 기준 | 설명 |
|------|------|
| 센서 데이터 | 수치형 시계열, 여러 사이클 또는 여러 장비 |
| 이벤트 로그 | 타임스탬프 + 텍스트 설명 (정비 기록, 알람 로그, 오류 로그 등) |
| 타임라인 정렬 | 센서와 이벤트 로그를 같은 시간축에 정렬 가능한가 |
| 접근성 | 무료 직접 다운로드 가능 |

---

## 1순위 — MetroPT

**포르투 지하철 공기압축기 (철도 도메인)**

| 항목 | 내용 |
|------|------|
| 다운로드 (UCI) | https://archive.ics.uci.edu/dataset/791/metropt+3+dataset |
| 다운로드 (Zenodo) | https://zenodo.org/records/6854240 |
| 논문 | https://www.nature.com/articles/s41597-022-01877-3 |
| 라이선스 | 무료 직접 다운로드 |

### 센서 데이터
- 포르투갈 포르투 지하철 열차의 공기 생산 장치(APU) 컴프레서
- 수집 기간: 2020년 2월 ~ 8월
- 총 **1,516,948개** 데이터 포인트, 샘플링 0.1 Hz (10초마다)
- **15개 피처**
  - 아날로그 7개: TP2, TP3 (압력), DV_pressure, H1, Towers, LPS, TL
  - 디지털 8개: MPG, LPS, 압력 스위치, 오일 레벨 등

### 이벤트 로그
- 회사 제공 **실제 정비 보고서** (텍스트)
- 포함 필드: 실패 시작 시각, 종료 시각, 실패 유형, 심각도, 보고서 번호

```
Failure #1 | 2020-04-18 00:00 ~ 23:59 | Air leak | High stress
Failure #2 | 2020-05-29 00:00 ~ 23:59 | Air leak | High stress
...
```

### 왜 1순위인가
- 센서 타임스탬프와 정비 보고서 타임스탬프가 완벽하게 정렬 가능
- 이벤트 로그가 단순 코드가 아닌 **자연어 텍스트**
- 파일 구조가 단순 (센서 CSV + 정비 이력 텍스트)
- 규모가 적당 (너무 크지 않음)

---

## 2순위 — CoMoPI

**포장 공장 기계 (제조 도메인)**

| 항목 | 내용 |
|------|------|
| 다운로드 (Zenodo) | https://zenodo.org/records/7572501 |
| 관련 데이터셋 ALPI | https://ieee-dataport.org/open-access/alarm-logs-packaging-industry-alpi |
| 라이선스 | 무료 직접 다운로드 |

### 센서 데이터
- 포장기계 **8대**의 밀봉 모듈 센서
- 수집 기간: 2022년 7월 ~ 2023년 1월
- **16개 센서값** (AE, BE, AF, BF, APP, BPP, AP, BP, ALE, BLE 등)
- 10분 윈도우 집계
- 파일: `industrial_dataset_sensors_10m_agg.csv`
  - 컬럼: `_serial` (기계 ID), `_time` (타임스탬프), 센서값 16개

### 이벤트 로그
- **알람 CSV + 경고 CSV** 별도 파일
- 알람 코드 16종 (AL_17, AL_18, AL_40 ~ AL_54)
- **AL_53, AL_54**: 실제 고장 조건 알람 (예측 타겟으로 활용 가능)

### 파일 구조
```
industrial_dataset_sensors_10m_agg.csv  ← 센서 시계열
industrial_dataset_alarms.csv           ← 알람 로그 (타임스탬프 + 코드)
industrial_dataset_warnings.csv         ← 경고 로그 (타임스탬프 + 코드)
```

### 왜 2순위인가
- 파일 3개 구조로 가장 단순하고 즉시 사용 가능
- 센서/알람/경고 모두 `_time` 기준으로 직접 정렬 가능
- 제조 도메인이라 이 프로젝트 목적과 맥락이 맞음
- 단점: 알람이 코드 형태라 자연어 텍스트보다 LLM 활용 여지가 적음

---

## 3순위 — Hill of Towie SCADA

**스코틀랜드 풍력발전단지 (에너지 도메인)**

| 항목 | 내용 |
|------|------|
| 다운로드 (Zenodo) | https://zenodo.org/records/14870023 |
| 오픈소스 분석 코드 | https://github.com/resgroup/hill-of-towie-open-source-analysis |
| 라이선스 | CC-BY-4.0, 무료 직접 다운로드 |

### 센서 데이터
- 스코틀랜드 Hill of Towie 풍력발전단지 **터빈 21기**
- Siemens SWT-2.3-VS-82 터빈
- 수집 기간: 2016년 1월 ~ 2024년 8월 (**8년 이상**)
- 10분 평균 SCADA 통계값
- 수십 개 신호: 풍속, 출력, RPM, 온도, 진동 등

### 이벤트 로그
- 동일 SCADA 시스템 추출 **알람 로그**
- 파일: `*_description.csv` — 알람 코드별 텍스트 설명 포함
- UTC 타임스탬프 기준으로 센서 데이터와 정렬 가능

### 왜 3순위인가
- 데이터 규모가 크고 장기간 실제 운영 데이터 (신뢰도 높음)
- 분석용 오픈소스 코드가 제공되어 시작이 쉬움
- 단점: 규모가 커서 전처리 부담이 있고, 알람 텍스트 수준이 MetroPT보다 낮음

---

## 참고 — Kelmarsh / Penmanshiel 풍력발전단지

Hill of Towie와 동일한 구조의 추가 풍력 데이터셋 (비교 실험에 활용 가능)

| 항목 | 내용 |
|------|------|
| Kelmarsh (Zenodo) | https://zenodo.org/records/5841834 |
| Penmanshiel (Zenodo) | https://zenodo.org/records/5946808 |
| 구성 | Kelmarsh: 터빈 6기 / Penmanshiel: 터빈 14기, 2016~2021 |

---

## 참고 — RCAEval (IT 인프라 도메인)

제조 도메인은 아니지만 로그 품질과 실험 구조가 가장 완성도 높음

| 항목 | 내용 |
|------|------|
| GitHub | https://github.com/phamquiluan/RCAEval |
| Zenodo | https://zenodo.org/records/14590730 |
| Figshare | https://figshare.com/articles/dataset/RCAEval_A_Benchmark_for_Root_Cause_Analysis_of_Microservice_Systems/31048672 |

- **735개** 마이크로서비스 실패 케이스
- 메트릭(센서 역할) + 애플리케이션 로그 + 트레이스 3종 동시 제공
- 로그: 컨테이너 stdout (타임스탬프 + 자유형 텍스트)
- 단점: IT 도메인이라 물리적 의미 추론과는 거리가 있음

---

## 최종 비교

| 데이터셋 | 도메인 | 센서 | 이벤트 로그 | 타임라인 정렬 | 다운로드 |
|----------|--------|------|------------|--------------|----------|
| **MetroPT** | 철도 | ★★★★★ | ★★★★★ (자연어) | ★★★★★ | 직접 |
| **CoMoPI** | 제조 | ★★★☆☆ | ★★★★☆ (알람코드) | ★★★★★ | 직접 |
| **Hill of Towie** | 풍력 | ★★★★★ | ★★★★☆ (알람코드+설명) | ★★★★★ | 직접 |
| Kelmarsh/Penmanshiel | 풍력 | ★★★★☆ | ★★★☆☆ | ★★★★☆ | 직접 |
| RCAEval | IT | ★★★★☆ | ★★★★★ (자유형 로그) | ★★★★☆ | 직접 |

---

## 다음 단계

데이터셋 선택 후:
1. 데이터 구조 분석 및 전처리 설계
2. 센서 데이터 → 이상 감지 ML 모델 학습
3. 이벤트 로그 → 벡터 DB(FAISS/Chroma) 구축
4. LLM 에이전트: ML 결과 + 이벤트 로그 RAG + 센서 통계 툴로 가설 검증 루프

---

*참고: industry_cases.md — 산업계 구현 사례*
*참고: datasets.md — 전체 데이터셋 목록*
