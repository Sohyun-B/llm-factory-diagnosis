"""
Phase 2: 프롬프트 빌더 (v2 — LLM 주도 방향 결정)

level0_results.json 전체를 서브에이전트에게 넘기고,
"어떤 신호가 중요한지"를 LLM 스스로 판단하게 한다.
Python이 필터링/임계값을 걸지 않는다.

Usage:
    python phase2_prompt_builder.py
    python phase2_prompt_builder.py --results-dir synthetic/results --data-dir synthetic/data
"""

import argparse
import json
import os


def load_results(results_dir: str) -> dict:
    path = os.path.join(results_dir, "level0_results.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_prompt(raw_json: str, data_dir: str, results_dir: str) -> str:
    abs_data = os.path.abspath(data_dir)
    abs_results = os.path.abspath(results_dir)

    return f"""# Phase 2: 규칙 발견 — LLM 주도 분석

## 역할

당신은 B2B 자재 발주 데이터에서 반복 패턴을 발견하는 분석 전문가입니다.

## 상황

Phase 1 통계 도구(`phase1_generic.py`)가 8개 레이어의 분석을 수행하여
아래에 raw JSON 결과를 생성했습니다.

**당신의 역할**: 이 통계 결과를 해석하여 "어떤 신호가 의미 있는지" 스스로 판단하고,
필요하면 원본 CSV 데이터를 직접 조회하여 심층 분석한 뒤, 최종 규칙을 작성하세요.

## 작업 단계

### 1단계: 통계 결과 해석
아래 JSON을 읽고, 각 분석 레이어에서 **당신이 보기에 의미 있는 신호**를 식별하세요.
어떤 임계값을 쓸지, 어떤 신호를 무시할지는 당신이 판단합니다.

### 2단계: 방향 결정 및 심층 조사
1단계에서 발견한 신호 중 더 파볼 것이 있으면,
아래 '데이터 접근' 섹션의 CSV 파일을 Read 도구로 직접 조회하세요.
예: "이 고객의 실제 발주 날짜를 확인하고 싶다" → orders.csv를 Read

### 3단계: 규칙 작성
1~2단계를 거쳐 발견한 패턴을 규칙으로 정리하세요.

## 규칙 발견 가이드

다음 유형의 패턴을 찾아보세요:
1. **주기적 발주**: 특정 고객-품목 조합이 일정 주기로 반복
2. **계절성**: 특정 시기에 수량이 증가하거나 감소
3. **교차 발주**: 고객 A 발주 후 고객 B가 따라서 발주
4. **동반 발주**: 특정 품목들이 같은 시점에 함께 주문
5. **이벤트 트리거**: 견적요청/샘플요청 후 발주로 이어지는 패턴
6. **조건부 발주**: 특정 조건(대형 발주, 특정 품목) 후 후속 발주
7. **추세 변화(drift)**: 발주 간격이나 수량이 시간에 따라 변화
8. **예외 패턴**: 공휴일, 특수 상황에서의 발주 시점 이동

## 주의사항

- 근거 없는 규칙을 만들지 마세요. 통계 수치로 뒷받침되지 않으면 '추가 관찰 필요'로 표시하세요.
- 너무 당연한 규칙(예: '대성기업은 자주 주문한다')은 피하세요.
- 규칙마다 confidence를 0.0~1.0으로 매기되, 표본 수가 적으면 낮게 주세요.
- **어떤 신호를 왜 중요하다고 판단했는지** 근거를 evidence에 남기세요.

---

## Phase 1 통계 결과 (Raw JSON)

아래는 `phase1_generic.py`가 출력한 전체 결과입니다.
필터링이나 가공 없이 그대로 제공합니다. 해석은 당신이 하세요.

```json
{raw_json}
```

---

## 데이터 접근

통계 결과만으로 부족하면 아래 원본 CSV를 Read 도구로 직접 조회하세요.

### 1. 발주 데이터 (`{abs_data}/orders.csv`)
- 컬럼: order_id, date, weekday, customer, item, category, quantity, unit, unit_price, total_amount
- 175건, 2025-04-02 ~ 2026-03-26

### 2. 이벤트 데이터 (`{abs_data}/events.csv`)
- 컬럼: date, customer, event_type, item, note
- 31건 (견적요청, 샘플요청, 가격문의, 납기확인)

### 3. 고객 데이터 (`{abs_data}/customers.csv`)
- 컬럼: customer, type, note
- 8개사, 유형: regular, quarterly, irregular, seasonal, random

### 4. 품목 데이터 (`{abs_data}/items.csv`)
- 컬럼: item, category, base_price, unit
- 12개 품목

---

## 출력

발견한 규칙을 아래 JSON 포맷으로 작성하여
`{abs_results}/llm_rules.json` 파일에 Write 도구로 저장하세요.

```json
{{
  "experiment": "v2_llm_directed",
  "timestamp": "작성 시점",
  "rules": [
    {{
      "id": "R1",
      "content": "규칙을 자연어로 서술",
      "confidence": 0.95,
      "evidence": "근거 수치/통계 설명 + 왜 이 신호가 중요하다고 판단했는지",
      "type": "periodic | seasonal | cross_customer | co_occurrence | event_trigger | conditional | drift | exception",
      "entities": {{"customer": "...", "item": "..."}}
    }}
  ]
}}
```

### type 분류 기준
- `periodic`: 일정 주기 반복 발주
- `seasonal`: 특정 계절/시기 수량 변화
- `cross_customer`: 고객 간 연쇄 발주
- `co_occurrence`: 품목 동반 발주
- `event_trigger`: 이벤트 후 발주 전환
- `conditional`: 특정 조건 충족 시 후속 발주
- `drift`: 시간에 따른 패턴 변화
- `exception`: 공휴일 등 예외 상황

### 주의
- entities에는 해당 규칙과 관련된 고객/품목을 가능한 한 명시하세요.
- 교차 발주의 경우 entities에 `from`, `to` 키를 사용하세요.
- 동반 발주의 경우 entities에 `items` 리스트를 사용하세요.
- confidence는 통계적 근거의 강도와 표본 수를 함께 고려하여 결정하세요.
"""


def main():
    parser = argparse.ArgumentParser(description="Phase 2: LLM 주도 규칙 발견 프롬프트 생성")
    parser.add_argument("--results-dir", default="synthetic/results",
                        help="level0_results.json이 있는 디렉토리 (기본: synthetic/results)")
    parser.add_argument("--data-dir", default="synthetic/data",
                        help="CSV 데이터 디렉토리 (기본: synthetic/data)")
    args = parser.parse_args()

    data = load_results(args.results_dir)
    raw_json = json.dumps(data, ensure_ascii=False, indent=2)

    prompt = build_prompt(raw_json, args.data_dir, args.results_dir)

    output_path = os.path.join(args.results_dir, "phase2_prompt.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(prompt)

    print(f"Prompt generated: {output_path}")
    print(f"  - Size: {len(prompt):,} bytes (raw JSON {len(raw_json):,} bytes included)")
    print(f"  - No filtering applied - LLM decides what matters")


if __name__ == "__main__":
    main()
