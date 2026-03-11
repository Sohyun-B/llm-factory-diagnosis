```json
{
  "rule_cards": [
    {
      "id": "RULE-001",
      "content": "대성기업의 AL6061 주문 간격이 짧을 때, 한진산업의 STS304 주문이 선행하는 경우가 많다.",
      "type": "conditional",
      "entities": { "customer": "대성기업", "item": "AL6061" },
      "confidence": {
        "score": 0.67,
        "natural_language": "가능성이 높은 편이다",
        "basis": "한진산업의 STS304 주문 후 5일 이내에 대성기업의 AL6061 주문이 발생하는 비율이 높음"
      },
      "evidence": {
        "phase1": "대성기업/AL6061의 짧은 주문 간격 중 한진산업/STS304가 자주 선행함",
        "phase2": "짧은 간격 4건 중 상위 선행자: 한진산업/STS304 (4건, 100%)",
        "phase3": "8/12건에서 한진산업의 STS304 주문이 선행"
      },
      "verification": {
        "method": "향후 대성기업의 AL6061 주문 패턴과 한진산업의 STS304 주문의 시간적 관계를 모니터링",
        "frequency": "quarterly"
      },
      "exceptions": ["한진산업의 STS304 주문이 없을 때"],
      "related_rules": [],
      "rejected_hypotheses": []
    },
    {
      "id": "RULE-002",
      "content": "세진테크의 AL5052, CARBON_STEEL, STS304의 동일한 주문 간격은 내부 프로세스에 의해 발생할 가능성이 높다.",
      "type": "periodic",
      "entities": { "customer": "세진테크", "item": "AL5052, CARBON_STEEL, STS304" },
      "confidence": {
        "score": 1.0,
        "natural_language": "거의 확실하다",
        "basis": "모든 간격이 91일로 확인됨"
      },
      "evidence": {
        "phase1": "세진테크의 AL5052, CARBON_STEEL, STS304의 주문 간격이 91일로 동일",
        "phase2": "외부 트리거 없음",
        "phase3": "91일 주기로 주문 패턴이 확인됨"
      },
      "verification": {
        "method": "세진테크의 향후 주문 데이터를 통해 91일 주기가 유지되는지 확인",
        "frequency": "quarterly"
      },
      "exceptions": [],
      "related_rules": [],
      "rejected_hypotheses": []
    },
    {
      "id": "RULE-003",
      "content": "동아전자의 견적요청 이벤트 후, 해당 품목의 주문 전환이 높은 확률로 발생한다.",
      "type": "event_trigger",
      "entities": { "customer": "동아전자", "item": "GASKET_A, PTFE_SHEET, SS_NUT_M10" },
      "confidence": {
        "score": 0.92,
        "natural_language": "거의 확실하다",
        "basis": "견적요청 후 8건 중 7건이 품목 일치하여 주문 전환됨"
      },
      "evidence": {
        "phase1": "동아전자의 견적요청 후 주문 전환 관찰",
        "phase2": "이벤트 8건 중 8건 후속 주문, 품목 일치율 88%",
        "phase3": "N/A"
      },
      "verification": {
        "method": "향후 견적요청 이벤트 후 주문 전환율을 모니터링",
        "frequency": "monthly"
      },
      "exceptions": ["품목 불일치 시"],
      "related_rules": [],
      "rejected_hypotheses": []
    }
  ],
  "summary": "이번 분석에서는 대성기업의 AL6061과 한진산업의 STS304 주문의 관계, 세진테크의 특정 품목에 대한 주기적 주문 패턴, 동아전자의 견적요청 후 주문 전환 패턴을 발견하였다. 이러한 패턴들은 향후 주문 예측과 재고 관리에 중요한 인사이트를 제공할 수 있다."
}
```