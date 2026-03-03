# 제조업 LLM 에이전트 실사례 조사

> 작성일: 2026-03-03
> 목적: 다음 개발 단계 설계를 위한 산업계 현황 파악
> 범위: 2024~2026년 실제 배포 또는 상용 출시 사례 위주

---

## 공통 아키텍처 패턴

거의 모든 사례가 동일한 구조를 따른다.

```
[센서/OT 데이터]          [이벤트 로그 / 정비 이력]   [도메인 문서 / 매뉴얼]
       ↓                           ↓                          ↓
[ML 이상 탐지]             [벡터 DB / KG (RAG)]         [SOP / FMEA DB]
       ↓                           ↓                          ↓
       └──────────── [LLM 에이전트] ──────────────────────────┘
                            │
                    가설 생성 → 툴 호출 → 검증 → 결론
                            │
              [근본 원인 + 권고 조치 → CMMS/ERP 연동]
```

**핵심 역할 분리**: ML은 수치 이상 감지, LLM은 원인 해석·가설 검증·자연어 출력

---

## 기업별 사례

---

### 1. AWS + Amazon Bedrock

**상태**: 상용 아키텍처 (AWS Blog 공개)

**구조**
```
Amazon Lookout for Equipment (ML)
  → 센서 이상 감지 + 이상 점수 생성
       ↓ Lambda 자동 트리거
Amazon Bedrock (Claude)
  → 이상 시점 전후 정비 로그 RAG 검색
  → 매뉴얼·설비 이미지 멀티모달 통합
  → 근본 원인 추론 + 정비 권고 생성
```

**이벤트 로그 활용 방식**
- 이상 감지 이벤트 발생 시 Lambda가 자동으로 Bedrock에 프롬프트 생성
- 해당 시점 전후의 정비 로그·알람 이력을 자동 교차 검토
- 구조화 센서 데이터 + 비정형 정비 기록을 동일 컨텍스트에 통합

**특이점**
- 이벤트 드리븐: 사람이 개입 없이 이상 → 분석 → 권고까지 자동 파이프라인
- Claude의 멀티모달 능력으로 설비 이미지도 진단 컨텍스트에 포함

---

### 2. IBM — Maximo Application Suite (MAS) + watsonx

**상태**: 상용 GA (MAS 9.0: 2024년, 9.1: 2025년 6월)

**구조**
```
Maximo Monitor (ML 이상 감지)
Maximo Health / Predict (고장 예측, 잔여수명 추정)
        ↓
중간 마이크로서비스 (RAG 레이어)
  → FMEA DB (800개 설비 유형, 58,000개 고장 모드)
  → 과거 Work Order, 정비 이력
        ↓
watsonx.ai (IBM Granite / Llama / Mistral 선택)
  → Work Order Intelligence: 고장 코드·원인 코드 자동 추천
  → Failure Mode Builder: 신규 자산 FMEA 자동 생성
  → Job Plan Automation: 정비 절차서 자동 작성
  → 자연어 질의: "최근 에너지 생산량이 어떻게 됐나?"
```

**이벤트 로그 활용 방식**
- 25년간 축적한 FMEA DB를 RAG로 연결 → 유사 고장 사례 즉시 검색
- 작업 지시서(Work Order) 이력 전체를 LLM 컨텍스트에 주입

**특이점**
- **드론-to-Fix 파이프라인**: 드론 촬영 이미지 → Visual Inspection(ML) → 이상 감지 → watsonx가 Work Order 자동 생성 → 작업자 배정까지 완전 자동화
- LLM 선택 자유: 동일 플랫폼에서 IBM Granite, Meta Llama, Mistral 중 선택 가능

---

### 3. Palantir — AIP (Artificial Intelligence Platform)

**상태**: 상용 배포 다수 (Boeing Defense 12개 공장, Airbus Skywise 등)

**구조**
```
Palantir Foundry (데이터 통합 + ML 파이프라인)
        ↓
Palantir Ontology
  → 설비·공정·인원·문서가 구조화된 객체로 연결
  → 객체 권한이 LLM 컨텍스트에 그대로 적용
        ↓
AIP Agent Studio (LLM 에이전트)
  → Neuro-Symbolic AI: Ontology 객체를 직접 참조
  → 기술 문서 → 인터랙티브 제조 가이던스 자동 변환
  → 멀티스텝 에이전트 워크플로우 실행
```

**이벤트 로그 활용 방식**
- 모든 운영 이벤트가 Ontology 객체로 구조화되어 LLM이 직접 참조
- 비정형 기술 문서를 에이전트가 실시간으로 파싱해 가이던스 제공

**특이점**
- **Neuro-Symbolic AI**: 수치 연산은 별도 계산기 툴 호출, LLM은 추론만 담당 → 환각 최소화
- **권한 연동**: 사람이 못 보는 데이터는 LLM도 못 봄 (보안)
- **Air-gapped 배포 지원**: 인터넷 없는 방산 공장 환경 대응

---

### 4. Siemens — Industrial Copilot + Senseye

**상태**: 상용 제품 (Operations Copilot 2025, Senseye 기배포)

**구조**
```
Siemens 설비 센서 + MES 데이터
        ↓
Senseye Maintenance Copilot
  → 전문 기술 지식 없이도 장비 진단 가능한 에이전트
  → ML 이상 감지 결과를 자연어로 설명
        ↓
Operations Copilot (Azure OpenAI 백엔드)
  → 자연어로 기계 데이터 쿼리
  → 오류 해결 안내
        ↓
Industrial Foundation Model (개발 중)
  → 150 페타바이트 엔지니어링 데이터로 훈련한 산업 특화 파운데이션 모델
```

**특이점**
- Microsoft와 공동 Azure OpenAI 백엔드를 공유하는 파트너 생태계 구조
- 자체 파운데이션 모델 개발 → 장기적으로 GPT 의존도 탈피 목표

---

### 5. ABB — Ability Genix Copilot

**상태**: 상용 GA (2024년, Verdantix 2025 Leader 선정)

**구조**
```
OT 데이터 (DCS/SCADA 실시간 센서)
ET 데이터 (엔지니어링 설계 도면)
IT 데이터 (ERP 트랜잭션)
        ↓
Genix 플랫폼 (3레이어 통합)
        ↓
GPT-4 기반 Genix Copilot
  → 업종별(화학/금속/시멘트/전력) 자연어 인사이트
  → APM(자산성능관리) ML 결과 설명
  → 운영·유지보수 데이터 기반 액션 권고
```

**특이점**
- **ET(엔지니어링 데이터) 통합**이 타사와 차별점: 설계 도면 데이터까지 LLM 컨텍스트에 포함
- 운영·유지보수 비용 40% 절감, 생산 효율 30% 향상 고객 사례 보고

---

### 6. Rockwell Automation — FactoryTalk + NVIDIA Nemotron

**상태**: FactoryTalk Copilot 상용 출시(2024), 엣지 SLM 2026년 예정

**구조**
```
PLC 래더 로직 / HMI 데이터
        ↓
FactoryTalk Analytics (ML)
  → LogixAI: 이상 감지
  → VisionAI: 생산 라인 비전 검사
  → GuardianAI: 설비 보호
        ↓
FactoryTalk Copilot (Azure OpenAI)
  → 자연어 프롬프트로 래더 로직 생성·설명·트러블슈팅
        ↓ (2026년 예정)
NVIDIA Nemotron-Nano-9B 엣지 SLM
  → Air-gapped 공장, HMI 패널에서 오프라인 구동
```

**특이점**
- **엣지 SLM 전략**: 클라우드 없이 공장 현장 디바이스에서 직접 구동
- NVIDIA NeMo로 FactoryTalk 전용 도메인 파인튜닝

---

### 7. Honeywell — Forge + Google Gemini AI Agents

**상태**: 2024년 10월 파트너십 발표, 2025년 상용 배포

**구조**
```
Honeywell Forge (IIoT 플랫폼)
  → 센서, 이미지, 비디오, 텍스트 멀티모달 데이터
        ↓
클라우드: Google Vertex AI (Gemini Pro)
  → 설계 자동화 에이전트
  → 정비 문서 검색 및 안내 에이전트
        ↓
엣지: Qualcomm + Gemini Nano (오프라인)
  → 현장 기술자 음성 기반 가이드 워크플로우
  → 인터넷 없이 경보 어시스트
```

**특이점**
- **클라우드 + 엣지 이중 에이전트**: 인터넷 연결 유무에 따라 자동 전환
- 멀티모달: 이미지·비디오·음성·센서 수치를 단일 에이전트가 처리

---

### 8. SAP — Joule + S/4HANA Manufacturing

**상태**: 상용 GA (Joule 2024년, Joule Studio 2026년 Q1)

**구조**
```
SAP S/4HANA (ERP 전사 데이터)
SAP Leonardo IoT (센서 데이터)
        ↓
SAP Knowledge Graph
  → 비즈니스 프로세스 의미론이 LLM 컨텍스트로 주입
        ↓
SAP Joule (LLM 코파일럿)
  → ML 이상 징후 → 자연어 설명 + 정비 권고
  → SAP PM Work Order 자동 생성 및 우선순위 결정
  → 공급망 계획 자연어 커스터마이징
```

**특이점**
- **Knowledge Graph 주입**: ERP의 비즈니스 프로세스 의미론이 직접 LLM 컨텍스트에 포함
- **MCP + A2A 프로토콜**: 타사 에이전트와 상호운용성 표준 채택 (2026년)

---

### 9. Schneider Electric + AVEVA

**상태**: 자사 공장 실 배포 완료

**실적**
- 예측 AI로 완전 공장 중단 3건 사전 방지
- AVEVA Discrete Lean Management: 70개 이상 제조 사이트 배포, 생산성 10% 향상, 다운타임 대응 속도 70% 개선

**구조**
```
AVEVA AI (이상 감지 ML)
        ↓
Microsoft Azure AI Foundry (공동 개발)
  → 자연어 공장 데이터 질의
  → 래더 로직 등 코드 생성 자동화
  → 복잡한 운영 프로세스 단순화
```

---

## 비교 요약

| 기업 | 배포 상태 | LLM 핵심 역할 | 이벤트 로그 활용 | 특이점 |
|------|-----------|--------------|-----------------|--------|
| **AWS** | 상용 아키텍처 공개 | 이상 후 자동 RCA | 알람 이력 RAG | 이벤트 드리븐 완전 자동화 |
| **IBM Maximo** | 상용 GA | Work Order 자동 생성 | 25년 FMEA DB RAG | 드론-to-Fix 파이프라인 |
| **Palantir AIP** | 상용, 방산 다수 | 에이전트 워크플로우 | Ontology 객체화 | 권한 연동, Air-gapped |
| **Siemens** | 상용 | 자연어 진단 안내 | 정비 이력 | 자체 파운데이션 모델 개발 |
| **ABB Genix** | 상용 GA | 업종별 인사이트 | APM 이력 | ET 설계 데이터 통합 |
| **Rockwell** | 상용 + 예정 | 코드 생성/설명 | 로직 이력 | 엣지 SLM (오프라인) |
| **Honeywell** | 2025 배포 | 설계·정비 에이전트 | 정비 문서 RAG | 클라우드+엣지 이중 |
| **SAP Joule** | 상용 GA | 워크플로우 자동화 | ERP 전사 이력 | Knowledge Graph 주입 |
| **Schneider+AVEVA** | 자사 공장 실적 | NL 질의, 코드 생성 | 운영 이력 | 공장 중단 3건 방지 |

---

## 현재 공통 한계

| 한계 | 내용 |
|------|------|
| **시계열 직접 처리 불가** | FFT/통계로 변환해야 해서 정보 손실 발생. 시계열 전용 FM(TimesFM, Chronos)과 결합은 초기 단계 |
| **환각** | 신규 고장 유형에서 틀린 원인을 확신 있게 출력. SOP·RAG로 억제하지만 완전 해결 안 됨 |
| **복합 고장 인과 추론** | 상관관계를 인과관계로 오해. 인과 그래프(Causal Graph) 결합은 연구 단계 |
| **실시간 불가** | 추론 지연 수 초~수십 초. 이상 감지는 ML, LLM은 사후 분석으로 역할 고정 |
| **도메인 지식 유지보수** | KG/RAG 벡터 DB를 공정 변경 시마다 수동 갱신 필요 |

---

## 다음 단계 설계에 대한 시사점

현재 이 프로젝트(Step 1~2)와 산업계 사례의 차이:

| 항목 | 현재 (Step 1~2) | 산업계 |
|------|----------------|--------|
| 이상 감지 | ML 분류기 | ML 이상 점수 스트림 |
| **이벤트 로그** | **없음** | **RAG로 벡터 DB에서 검색** |
| 도메인 지식 | 시스템 프롬프트 직접 기술 | KG 또는 RAG 동적 주입 |
| 에이전트 제약 | 없음 | SOP 주입으로 환각 억제 |
| 출력 활용 | UI 표시 | CMMS/ERP 자동 연동 |

**가장 임팩트가 큰 다음 추가 요소**: 이벤트 로그 + RAG
센서 데이터만으로는 "측정값이 이상하다"는 것만 알 수 있지만,
정비 로그가 있으면 "3일 전 펌프 씰 교체 후 다시 유량 이상" 같은 인과 연쇄를 추론 가능하다.

---

*참고 논문/자료는 datasets.md와 별도로 관리*
