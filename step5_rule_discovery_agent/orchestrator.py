"""
Orchestrator v3: 확실한 것은 ML이 바로 결과로, LLM은 해석/조합/예외 추적

Flow:
    ML 기초통계 → ML 자동발견 (확실한 패턴 직접 추출)
        → Step 1: LLM이 자동발견 해석 + 나머지 신호에서 추가 가설
            → ML 추가 가설 검증 → Step 2: 전체에서 예외 추적
                → ML 예외 조사 → Step 3: 깊은 가설
                    → ML 검증 → Step 4: 종합 Rule Card

Usage:
    python orchestrator.py --data-dir synthetic/data
    python orchestrator.py --data-dir synthetic/data --skip-phase1
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ML 도구 직접 import
sys.path.insert(0, BASE_DIR)
from phase2_investigate import run_request as run_analysis, load_data
from phase3_test import run_test
from signal_extractor import summarize as summarize_level0, extract_auto_findings


# ============================================================
# 대화 관리
# ============================================================

class Conversation:
    """하나의 LLM 대화 세션. 전체 수사 과정이 이 대화 안에서 이어진다."""

    def __init__(self, system_prompt: str, model: str = "gpt-4o"):
        self.model = model
        self.messages = [{"role": "system", "content": system_prompt}]
        self.client = OpenAI()

    def say(self, user_message: str) -> str:
        self.messages.append({"role": "user", "content": user_message})
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            temperature=0.7,
            max_tokens=16000,
        )
        reply = response.choices[0].message.content
        self.messages.append({"role": "assistant", "content": reply})
        return reply

    def message_count(self) -> int:
        return len(self.messages)

    def save_transcript(self, path: str):
        lines = []
        for msg in self.messages:
            role = msg["role"].upper()
            lines.append(f"## {role}\n\n{msg['content']}\n\n---\n")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


def extract_json(text: str) -> dict:
    """LLM 응답에서 JSON 추출. 여러 블록이 있으면 하나로 병합."""
    blocks = re.findall(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if blocks:
        merged = {}
        for block in blocks:
            try:
                parsed = json.loads(block)
                if isinstance(parsed, dict):
                    merged.update(parsed)
            except json.JSONDecodeError:
                continue
        if merged:
            return merged
    # fallback: 전체 텍스트에서 JSON 추출
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    raise ValueError(f"JSON 추출 실패: {text[:200]}...")


# ============================================================
# 시스템 프롬프트
# ============================================================

SYSTEM_PROMPT = """당신은 B2B 자재 발주 데이터에서 숨겨진 패턴을 발견하는 탐정입니다.
이 대화는 ML 도구와의 공동 수사입니다.

## 역할 분담
- ML이 이미 확인한 패턴("자동 발견")은 사실로 받아들이세요 — 재검증 불필요
- 당신의 역할: 자동 발견을 **해석**하고, **조합**하고, **예외**를 찾고, ML이 못 찾은 **새 패턴**을 가설로 세우는 것

## 수사 흐름
1. ML 자동 발견 검토 + 나머지 신호에서 추가 가설
2. 자동 발견 + 검증된 가설에서 예외 추적
3. 예외의 원인을 파고들어 깊은 가설 생성
4. 모든 증거를 종합하여 Rule Card 작성

## 원칙
- "왜?"를 계속 물어보세요
- 자동 발견끼리 **연결**이 있는지 보세요 (예: A의 예외가 B로 설명되는가?)
- 불일치는 버리지 말고 파고드세요"""


# ============================================================
# 도구 설명
# ============================================================

VERIFY_TOOLS = """## 검증 도구 (가설을 테스트할 때 사용)
⚠️ 아래 9가지 test_type만 사용 가능합니다.

- cross_customer_binary: A 발주 후 B 발주 이진 검정
  params: trigger_customer, trigger_item?, effect_customer, effect_item?, lag_window=[min,max]
- quantity_comparison: 두 그룹 간 수량 비교 (Mann-Whitney U)
  params: customer, item, split_condition={max_interval: N}
- conditional_trigger: 대량 발주(qty>=N) 후 다른 고객 반응 비교
  params: trigger_customer, trigger_item, min_quantity(필수!), effect_customer, effect_item, time_window
- drift_after_cleaning: 교란 제거 후 trend 재검정
  params: customer, item, remove_precursor="고객/품목"(예: "한진산업/STS304"), remove_lag_max
- periodicity_test: 특정 주기 가설 검정
  params: customer, item(필수), expected_period, tolerance_pct(기본15)
- seasonal_split: 분기별 패턴 강도 비교
  params: from_customer, to_customer, split_by="quarter", lag_min, lag_max
- event_conversion: 이벤트→주문 전환율 검정
  params: customer, event_type, target_item?, max_lag(기본30)
- time_concentration: 특정 요일/주차 집중 검정
  params: customer, item?, expected_weekday(0=월~6=일)?, expected_week(1~5)?
- co_occurrence_test: 같은 주 동반 발주 검정
  params: item_a, item_b, customer?"""

INVESTIGATE_TOOLS = """## 조사 도구 (데이터를 더 깊이 파볼 때 사용)
- precursor_check: 짧은 간격 주문의 선행자 확인
  params: customer, item, target_max_interval(기본5), look_back_days(기본7)
- cross_customer_detail: 두 고객 간 주문일 상세 매칭
  params: from_customer, to_customer, from_item?, to_item?, lag_min(기본1), lag_max(기본7)
- quantity_anomaly: 이상 수량 주문 식별
  params: customer?, item?, threshold_pct(기본50)
- conditional_trigger: A 조건 → B 효과 검정
  params: trigger_customer, trigger_item, trigger_condition={min_quantity:N}, effect_customer, effect_item, time_window(기본30)
- drift_detail: 교란 제거 후 drift 재검정
  params: customer, item, remove_precursor?("고객/품목"), remove_lag_max(기본5)
- alternation_check: 품목 교대 패턴 확인
  params: customer, items=["품목A","품목B"]
- event_lead_detail: 이벤트→주문 전환 상세
  params: customer?, event_type?, lag_max(기본30)
- seasonal_shift: 분기/월별 패턴 비교
  params: customer?, item?, split_by("quarter"|"month")"""


# ============================================================
# Step 1: 자동 발견 해석 + 추가 가설
# ============================================================

def format_auto_findings(findings: list[dict]) -> str:
    """자동 발견을 LLM이 읽을 수 있는 형태로 포맷"""
    lines = []
    for f in findings:
        conf = f["confidence"]
        lines.append(f"- **{f['id']}** [{f['type']}] (신뢰도 {conf:.0%}): {f['statement']}")
    return "\n".join(lines)


def step1_interpret_and_hypothesize(conv, auto_findings, summary):
    af_text = format_auto_findings(auto_findings)

    prompt = f"""수사를 시작합니다.

## ML 자동 발견 ({len(auto_findings)}개)
ML이 통계적으로 확인한 패턴입니다. 이것들은 사실로 받아들이세요.

{af_text}

## 당신의 할 일

### 1. 자동 발견 해석
- 각 자동 발견이 **비즈니스 맥락에서 무엇을 의미**하는지 해석하세요
- 자동 발견끼리 **연결**이 있는지 보세요
  - 예: AF-004(대성기업 14일 주기) + AF-006(한진산업 발주 직후 대성기업 짧은간격) → "대성기업은 격주로 발주하되, 한진산업 대량 발주 시 추가 긴급 발주"
  - 예: AF-015(한진산업 대량→세진테크 STS316) + AF-001~003(세진테크 91일 주기) → "세진테크 정기 발주 외에 한진 대량 발주 반응으로 STS316 추가"

### 2. 나머지 신호에서 추가 가설
자동 발견에 포함되지 않은 신호들(아래 요약 테이블)에서 추가 가설을 세우세요.
자동 발견이 이미 커버한 것은 다시 가설로 만들지 마세요.

{VERIFY_TOOLS}

## 출력 (하나의 JSON 블록):
```json
{{
  "interpretations": [
    {{
      "finding_ids": ["AF-001", "AF-004"],
      "connection": "이 발견들이 어떻게 연결되는지",
      "business_meaning": "비즈니스 맥락에서의 의미"
    }}
  ],
  "additional_hypotheses": [
    {{
      "id": "H-1",
      "statement": "자동 발견에 없는 새 가설",
      "test_type": "위 도구 중 선택",
      "params": {{ ... }},
      "expected_if_true": "맞다면 결과"
    }}
  ]
}}
```

추가 가설은 자동 발견이 커버하지 않는 영역에서만 세우세요.
연결 해석에 집중하세요 — 여기가 LLM의 핵심 가치입니다.

## ML 기초 통계 요약 (전체 데이터)

{summary}"""

    print("  LLM 호출 중...")
    raw = conv.say(prompt)
    parsed = extract_json(raw)
    n_i = len(parsed.get("interpretations", []))
    n_h = len(parsed.get("additional_hypotheses", []))
    print(f"  → 연결 해석 {n_i}개, 추가 가설 {n_h}개")
    return raw, parsed


# ============================================================
# Step 2: 예외 추적
# ============================================================

def step2_track_exceptions(conv, auto_findings, verify_results):
    af_text = format_auto_findings(auto_findings)

    prompt = f"""추가 가설 검증이 완료되었습니다.

## 핵심 지시
이제 **모든 확인된 패턴(자동 발견 + 검증된 가설) 안에서 예외를 찾으세요**.

### 자동 발견 ({len(auto_findings)}개) — 이미 확인됨:
{af_text}

### 예외 찾기 가이드:
- AF-004: "대성기업 14일 주기인데, 부성분 5건(2.8일)은 왜?"
- AF-006: "한진산업 발주 직후 3/5건인데, 나머지 2건은 왜 다른 선행자?"
- AF-010: "14일→17일 drift인데, 어디서부터 변했나? 특정 시점이 있나?"
- AF-011: "견적요청 100% 전환인데, 88% 품목일치 — 12%는 왜 다른 품목?"
- AF-015: "한진산업 대량→세진테크 3건인데, 대량 발주가 더 많았을 텐데 나머지는?"

{INVESTIGATE_TOOLS}

## 출력 (하나의 JSON 블록):
```json
{{
  "verification_summary": "검증 결과 전체 해석",
  "exceptions": [
    {{
      "id": "EX-1",
      "source": "AF-004 또는 H-1 등",
      "description": "어떤 데이터가 패턴을 따르지 않는지",
      "why_interesting": "왜 중요한지"
    }}
  ],
  "investigation_requests": [
    {{
      "id": "INV-1",
      "exception_id": "EX-1",
      "question": "조사할 질문",
      "analysis_type": "위 도구에서 선택",
      "params": {{ ... }}
    }}
  ]
}}
```

예외와 조사 요청은 **많을수록 좋습니다** (최소 5개).

## 추가 가설 검증 결과
```json
{json.dumps(verify_results, ensure_ascii=False, indent=2)}
```"""

    print("  LLM 호출 중...")
    raw = conv.say(prompt)
    parsed = extract_json(raw)
    n_ex = len(parsed.get("exceptions", []))
    n_i = len(parsed.get("investigation_requests", []))
    print(f"  → 예외 {n_ex}개, 조사 요청 {n_i}개")
    return raw, parsed


# ============================================================
# Step 3: 깊은 가설
# ============================================================

def step3_deep_hypotheses(conv, investigation_results):
    prompt = f"""예외 조사가 완료되었습니다.

## 핵심 지시
이 단계가 수사의 핵심입니다.
자동 발견(확실한 것)은 이미 있습니다.
**자동 발견끼리의 연결, 예외의 원인, 당연하지 않은 패턴**을 가설화하세요.

좋은 깊은 가설의 예:
- "대성기업 부성분(2.8일)은 한진산업 STS304 발주에 대한 하청 긴급 반응이다"
- "세진테크 STS316이 91일이 아닌 이유는 한진산업 대량발주에 반응하기 때문이다"
- "대성기업의 drift(14→17일)는 7월 이후 수요 감소에 의한 것이다"

{VERIFY_TOOLS}

## 출력 (하나의 JSON 블록):
```json
{{
  "exception_interpretation": "예외 조사 결과 해석",
  "insights": ["새로 알게 된 것"],
  "deep_hypotheses": [
    {{
      "id": "DH-1",
      "origin": "어떤 예외/조사에서 파생",
      "statement": "깊은 가설",
      "test_type": "위 도구 중 선택",
      "params": {{ ... }},
      "expected_if_true": "맞다면 결과"
    }}
  ]
}}
```

## 예외 조사 결과
```json
{json.dumps(investigation_results, ensure_ascii=False, indent=2)}
```"""

    print("  LLM 호출 중...")
    raw = conv.say(prompt)
    parsed = extract_json(raw)
    n_dh = len(parsed.get("deep_hypotheses", []))
    print(f"  → 깊은 가설 {n_dh}개")
    return raw, parsed


# ============================================================
# Step 4: 최종 종합 → Rule Card
# ============================================================

def step4_synthesize(conv, auto_findings, deep_results):
    af_json = json.dumps(auto_findings, ensure_ascii=False, indent=2)

    prompt = f"""수사를 마무리할 시간입니다.

## 증거 소스
1. **ML 자동 발견** (가장 확실): 아래 JSON 참조
2. **LLM 해석/조합**: 자동 발견 간의 연결
3. **예외 추적 + 깊은 가설 검증**: 이전 단계 결과

## 자동 발견 (이것들은 반드시 Rule Card에 포함):
```json
{af_json}
```

## 상세 검증 결과:
```json
{json.dumps(deep_results, ensure_ascii=False, indent=2)}
```

## Rule Card 포맷
```json
{{
  "rule_cards": [
    {{
      "id": "RULE-001",
      "content": "패턴을 자연어로 서술",
      "type": "periodic | cross_customer | event_trigger | drift | time_concentration | association | co_occurrence",
      "entities": {{ "customer": "...", "item": "..." }},
      "confidence": {{
        "score": 0.0~1.0,
        "natural_language": "거의 확실하다 | 가능성이 높은 편이다 | 불확실하다",
        "basis": "근거 요약"
      }},
      "evidence": {{
        "auto_finding": "ML 자동 발견 ID (있으면)",
        "llm_interpretation": "LLM이 추가한 해석",
        "exceptions": "알려진 예외"
      }},
      "related_rules": ["관련 규칙 ID"],
      "verification_plan": {{
        "method": "향후 검증 방법",
        "frequency": "monthly | quarterly"
      }}
    }}
  ],
  "investigation_summary": "전체 수사 요약",
  "open_questions": ["아직 답을 못 찾은 질문"]
}}
```

## 주의
- 자동 발견(AF-xxx)은 confidence 기준으로 **모두** Rule Card에 포함하세요
- 유사한 자동 발견은 하나의 Rule Card로 합치세요 (예: AF-001~003 → 하나)
- 자동 발견 간의 연결도 Rule Card로 만드세요
- 깊은 가설 중 confirmed/partially_confirmed도 포함
- confidence 기준: 자동 발견 conf 그대로 사용, LLM 추가 해석은 -0.1"""

    print("  LLM 호출 중...")
    raw = conv.say(prompt)
    parsed = extract_json(raw)
    n_r = len(parsed.get("rule_cards", []))
    print(f"  → Rule Card {n_r}개")
    return raw, parsed


# ============================================================
# ML 실행 헬퍼
# ============================================================

def run_hypothesis_tests(hypotheses, orders, events=None):
    """가설 목록 → phase3 검증"""
    results = {}
    for hyp in hypotheses:
        hyp_id = hyp["id"]
        print(f"    [{hyp_id}] {hyp.get('statement', '')}...")
        result = run_test(hyp, orders, events=events)
        results[hyp_id] = result
        print(f"      → {result.get('verdict', '?')}")
    return results


def run_investigations(requests, orders, events):
    """조사 요청 → phase2 분석"""
    results = {}
    for req in requests:
        req_id = req["id"]
        print(f"    [{req_id}] {req.get('question', '')}...")
        result = run_analysis(req, orders, events)
        results[req_id] = {
            "question": req.get("question", ""),
            "analysis_type": req.get("analysis_type", ""),
            "result": result,
        }
        summary = result.get("summary", result.get("error", "done"))
        print(f"      → {summary}")
    return results


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="LLM 주도 탐구 파이프라인 v3")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--skip-phase1", action="store_true")
    parser.add_argument("--model", default="gpt-4o")
    args = parser.parse_args()

    data_dir = os.path.abspath(args.data_dir)
    output_dir = os.path.abspath(args.output_dir) if args.output_dir else \
        os.path.join(os.path.dirname(data_dir), "results")
    os.makedirs(output_dir, exist_ok=True)

    print(f"데이터: {data_dir}")
    print(f"출력:  {output_dir}")
    print(f"모델:  {args.model}")
    print(f"시작:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 데이터 로드
    orders, events = load_data(data_dir)
    print(f"주문 {len(orders)}건, 이벤트 {len(events) if events is not None else 0}건")

    # Phase 1 (고정 ML)
    level0_path = os.path.join(output_dir, "level0_results.json")
    if args.skip_phase1 and os.path.exists(level0_path):
        print("Phase 1 스킵 (기존 결과 사용)")
    else:
        print("\n기초 통계 분석 실행 중...")
        script = os.path.join(BASE_DIR, "phase1_generic.py")
        cmd = [sys.executable, script, "--data-dir", data_dir, "--output-dir", output_dir]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            print(f"실패:\n{result.stderr}")
            sys.exit(1)

    with open(level0_path, "r", encoding="utf-8") as f:
        level0 = json.load(f)

    # ────────────────────────────────────────
    # ML 자동 발견
    # ────────────────────────────────────────
    print("\n" + "=" * 60)
    print("ML 자동 발견 추출")
    print("=" * 60)
    auto_findings = extract_auto_findings(level0)
    print(f"  → {len(auto_findings)}개 자동 발견")
    for af in auto_findings:
        print(f"    [{af['id']}] ({af['type']}, {af['confidence']:.0%}) {af['statement']}")

    summary = summarize_level0(level0)

    # 수사 기록
    investigation = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "model": args.model,
            "data_dir": data_dir,
        },
        "auto_findings": auto_findings,
        "steps": [],
    }

    conv = Conversation(SYSTEM_PROMPT, model=args.model)

    # ────────────────────────────────────────
    # Step 1: 해석 + 추가 가설
    # ────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Step 1: 자동 발견 해석 + 추가 가설")
    print("=" * 60)
    raw1, parsed1 = step1_interpret_and_hypothesize(conv, auto_findings, summary)

    additional_hyps = parsed1.get("additional_hypotheses", [])
    verify_results = {}
    if additional_hyps:
        print(f"\n  [ML] 추가 가설 {len(additional_hyps)}개 검증 중...")
        verify_results = run_hypothesis_tests(additional_hyps, orders, events)

    investigation["steps"].append({
        "id": 1, "name": "해석 + 추가 가설",
        "llm_raw": raw1, "llm_parsed": parsed1,
        "ml_action": "hypothesis_test",
        "ml_results": verify_results,
    })

    # ────────────────────────────────────────
    # Step 2: 예외 추적
    # ────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Step 2: 예외 추적")
    print("=" * 60)
    raw2, parsed2 = step2_track_exceptions(conv, auto_findings, verify_results)

    print("\n  [ML] 예외 조사 중...")
    inv_results = run_investigations(
        parsed2.get("investigation_requests", []), orders, events)

    investigation["steps"].append({
        "id": 2, "name": "예외 추적",
        "llm_raw": raw2, "llm_parsed": parsed2,
        "ml_action": "investigation",
        "ml_results": inv_results,
    })

    # ────────────────────────────────────────
    # Step 3: 깊은 가설
    # ────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Step 3: 깊은 가설")
    print("=" * 60)
    raw3, parsed3 = step3_deep_hypotheses(conv, inv_results)

    deep_results = {}
    deep_hyps = parsed3.get("deep_hypotheses", [])
    if deep_hyps:
        print(f"\n  [ML] 깊은 가설 {len(deep_hyps)}개 검증 중...")
        deep_results = run_hypothesis_tests(deep_hyps, orders, events)

    investigation["steps"].append({
        "id": 3, "name": "깊은 가설",
        "llm_raw": raw3, "llm_parsed": parsed3,
        "ml_action": "hypothesis_test",
        "ml_results": deep_results,
    })

    # ────────────────────────────────────────
    # Step 4: 종합
    # ────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Step 4: 최종 종합")
    print("=" * 60)
    raw4, parsed4 = step4_synthesize(conv, auto_findings, deep_results)

    investigation["steps"].append({
        "id": 4, "name": "종합",
        "llm_raw": raw4, "llm_parsed": parsed4,
        "ml_action": None,
        "ml_results": None,
    })

    # ────────────────────────────────────────
    # 저장
    # ────────────────────────────────────────
    inv_path = os.path.join(output_dir, "investigation.json")
    with open(inv_path, "w", encoding="utf-8") as f:
        json.dump(investigation, f, ensure_ascii=False, indent=2, default=str)

    rule_cards_path = os.path.join(output_dir, "rule_cards.json")
    with open(rule_cards_path, "w", encoding="utf-8") as f:
        json.dump(parsed4, f, ensure_ascii=False, indent=2)

    transcript_path = os.path.join(output_dir, "conversation_transcript.md")
    conv.save_transcript(transcript_path)

    print("\n" + "=" * 60)
    print("수사 완료")
    print("=" * 60)
    print(f"  자동 발견:   {len(auto_findings)}개")
    print(f"  Rule Cards: {len(parsed4.get('rule_cards', []))}개")
    print(f"  수사 기록:   {inv_path}")
    print(f"  대화 메시지: {conv.message_count()}개")
    print(f"  종료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
