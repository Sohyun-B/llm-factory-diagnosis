"""
합성 자재 발주 데이터 생성기
- 고객 8개, 품목 12개, 12개월치
- 의도적으로 심어둔 패턴 (난이도별 분류):

=== 쉬운 패턴 (Level 1 — 통계 도구만으로 발견 가능) ===
P1. 한진산업: STS304를 매월 첫째 주에 ~100kg 주문 (주기성)
P2. 봄(3~5월) 전체 수요 약 30% 증가 (계절성)
P3. 대성기업: 격주로 AL6061 발주 (주기성)

=== 중간 패턴 (Level 2~3 — 통계 단서 + LLM 해석 필요) ===
P4. 한진산업 발주 후 2~4일 내에 대성기업이 AL6061 발주 (교차 패턴, 하청 관계)
P5. 공휴일이 월초에 끼면 한진산업 발주가 둘째 주로 밀림 (예외 조건)
P6. 세진테크: 분기 시작 달(1,4,7,10월)에 대량 발주 (분기 패턴)
P7. STS304와 CU_PIPE가 같은 주에 동반 발주되는 빈도 높음 (품목 연관)

=== 어려운 패턴 (Level 4 — 맥락 추론 필요) ===
P8. 동아전자: 발주 전 1~2주에 견적 요청이 선행 (선행 지표)
P9. 한진산업 발주량이 150kg 이상일 때 → 다음 달 세진테크 대량 발주 확률 높음 (간접 선행)
P10. 7월 이후 대성기업 격주 패턴이 서서히 3주 간격으로 변함 (Gradual Drift)

=== 노이즈 ===
- 모든 패턴에 ±20% 수량 노이즈
- 랜덤 발주 (패턴 없는 거래) 20% 섞임
- 일부 고객은 불규칙 발주 (패턴 없음)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import os

np.random.seed(42)
random.seed(42)

# === 기본 설정 ===
START_DATE = datetime(2025, 4, 1)
END_DATE = datetime(2026, 3, 31)  # 12개월

CUSTOMERS = {
    "한진산업": {"type": "regular", "note": "주요 고객, 월초 정기 발주"},
    "대성기업": {"type": "regular", "note": "격주 발주, 한진산업 하청"},
    "세진테크": {"type": "quarterly", "note": "분기 시작 대량 발주"},
    "동아전자": {"type": "irregular", "note": "견적 후 발주"},
    "삼호금속": {"type": "random", "note": "비정기 소량 발주"},
    "우진소재": {"type": "seasonal", "note": "봄/가을 집중"},
    "태광스틸": {"type": "random", "note": "비정기 발주"},
    "명성산업": {"type": "regular", "note": "월 2회 정기"},
}

ITEMS = {
    "STS304": {"category": "스테인리스", "base_price": 4500, "unit": "kg"},
    "STS316": {"category": "스테인리스", "base_price": 6200, "unit": "kg"},
    "AL6061": {"category": "알루미늄", "base_price": 3800, "unit": "kg"},
    "AL5052": {"category": "알루미늄", "base_price": 3500, "unit": "kg"},
    "CU_PIPE": {"category": "동", "base_price": 12000, "unit": "m"},
    "CU_PLATE": {"category": "동", "base_price": 15000, "unit": "kg"},
    "SS_BOLT_M10": {"category": "체결부품", "base_price": 250, "unit": "ea"},
    "SS_NUT_M10": {"category": "체결부품", "base_price": 120, "unit": "ea"},
    "GASKET_A": {"category": "실링", "base_price": 8500, "unit": "ea"},
    "PTFE_SHEET": {"category": "실링", "base_price": 32000, "unit": "장"},
    "CARBON_STEEL": {"category": "탄소강", "base_price": 2800, "unit": "kg"},
    "PIPE_SCH40": {"category": "배관", "base_price": 18000, "unit": "m"},
}

# 공휴일 목록 (한국 2025~2026)
HOLIDAYS = [
    datetime(2025, 5, 1),   # 근로자의 날
    datetime(2025, 5, 5),   # 어린이날
    datetime(2025, 5, 6),   # 대체휴일
    datetime(2025, 6, 6),   # 현충일
    datetime(2025, 8, 15),  # 광복절
    datetime(2025, 9, 6),   # 추석
    datetime(2025, 9, 7),
    datetime(2025, 9, 8),
    datetime(2025, 10, 3),  # 개천절
    datetime(2025, 10, 9),  # 한글날
    datetime(2025, 12, 25), # 크리스마스
    datetime(2026, 1, 1),   # 신정
    datetime(2026, 1, 28),  # 설날
    datetime(2026, 1, 29),
    datetime(2026, 1, 30),
    datetime(2026, 3, 1),   # 삼일절
]

HOLIDAY_SET = set(h.date() for h in HOLIDAYS)

orders = []
events = []  # 견적 요청, 가격 문의 등
order_id = 1000


def add_noise_qty(base_qty, noise_pct=0.2):
    """수량에 ±noise_pct 노이즈 추가"""
    factor = 1 + np.random.uniform(-noise_pct, noise_pct)
    return max(1, round(base_qty * factor))


def get_first_business_day(year, month, week=1):
    """해당 월의 N번째 주 첫 영업일 반환"""
    first = datetime(year, month, 1)
    # 첫째 주 월요일 찾기
    days_ahead = 0 - first.weekday()  # 월요일
    if days_ahead < 0:
        days_ahead += 7
    monday = first + timedelta(days=days_ahead)
    target = monday + timedelta(weeks=week - 1)

    # 주말/공휴일이면 다음 영업일
    while target.weekday() >= 5 or target.date() in HOLIDAY_SET:
        target += timedelta(days=1)
    return target


def is_holiday_in_first_week(year, month):
    """해당 월 첫째 주(1~7일)에 공휴일이 있는지"""
    for day in range(1, 8):
        try:
            d = datetime(year, month, day).date()
            if d in HOLIDAY_SET:
                return True
        except ValueError:
            pass
    return False


def seasonal_factor(date):
    """봄(3~5월) 30% 증가, 나머지 기본"""
    month = date.month
    if month in [3, 4, 5]:
        return 1.3
    elif month in [11, 12, 1]:
        return 0.85
    return 1.0


def add_order(date, customer, item, qty, pattern_tag=None):
    """발주 추가"""
    global order_id
    price = ITEMS[item]["base_price"]
    # 봄철 가격 상승 (STS316 특히)
    if item == "STS316" and date.month in [3, 4, 5]:
        price = round(price * 1.15)
    # 약간의 가격 변동
    price = round(price * (1 + np.random.uniform(-0.03, 0.03)))

    orders.append({
        "order_id": f"ORD-{order_id}",
        "date": date.strftime("%Y-%m-%d"),
        "weekday": ["월", "화", "수", "목", "금", "토", "일"][date.weekday()],
        "customer": customer,
        "item": item,
        "category": ITEMS[item]["category"],
        "quantity": qty,
        "unit": ITEMS[item]["unit"],
        "unit_price": price,
        "total_amount": qty * price,
        "_pattern": pattern_tag,  # 정답 레이블 (평가용, 실제론 비공개)
    })
    order_id += 1
    return date


def add_event(date, customer, event_type, item=None, note=""):
    """이벤트(견적요청, 가격문의 등) 추가"""
    events.append({
        "date": date.strftime("%Y-%m-%d"),
        "customer": customer,
        "event_type": event_type,
        "item": item,
        "note": note,
    })


# ============================================================
# P1. 한진산업: 매월 첫째 주 STS304 ~100kg
# P5. 공휴일이 월초에 끼면 둘째 주로 밀림
# P7. STS304 주문 시 CU_PIPE 동반 발주 (60% 확률)
# P9. 발주량 150kg 이상이면 다음 달 세진테크 대량 발주 신호
# ============================================================
hanjin_large_months = []  # P9 추적용

current = START_DATE
while current <= END_DATE:
    year, month = current.year, current.month

    # P5: 공휴일이 첫째 주에 끼면 둘째 주로 밀림
    if is_holiday_in_first_week(year, month):
        order_date = get_first_business_day(year, month, week=2)
        pattern = "P1+P5"
    else:
        order_date = get_first_business_day(year, month, week=1)
        pattern = "P1"

    if order_date > END_DATE:
        break

    # 기본 100kg + 봄 시즌 증가 + 노이즈
    base_qty = 100
    qty = add_noise_qty(base_qty * seasonal_factor(order_date), 0.15)

    # P9: 가끔 대형 발주 (150kg+)
    if month in [4, 10] or (month == 1 and year == 2026):
        qty = add_noise_qty(160, 0.1)
        hanjin_large_months.append((year, month))

    add_order(order_date, "한진산업", "STS304", qty, pattern)

    # P7: STS304 주문 시 CU_PIPE 동반 (60%)
    if random.random() < 0.6:
        cu_date = order_date + timedelta(days=random.randint(0, 2))
        if cu_date.weekday() >= 5:
            cu_date += timedelta(days=7 - cu_date.weekday())
        add_order(cu_date, "한진산업", "CU_PIPE", add_noise_qty(20, 0.2), "P7")

    # 다음 달로
    if month == 12:
        current = datetime(year + 1, 1, 1)
    else:
        current = datetime(year, month + 1, 1)


# ============================================================
# P3. 대성기업: 격주 AL6061
# P4. 한진산업 발주 후 2~4일 뒤 대성기업 발주 (교차 패턴)
# P10. 7월 이후 격주 → 점진적으로 3주 간격으로 변화
# ============================================================
daesung_date = START_DATE + timedelta(days=2)  # 4/3 시작
interval = 14  # 2주 간격

while daesung_date <= END_DATE:
    # P10: 7월 이후 간격이 점진적으로 늘어남
    if daesung_date >= datetime(2025, 7, 1):
        months_since_july = (daesung_date.year - 2025) * 12 + daesung_date.month - 7
        interval = min(21, 14 + months_since_july)  # 14일 → 최대 21일

    # 영업일 조정
    actual_date = daesung_date
    while actual_date.weekday() >= 5:
        actual_date += timedelta(days=1)

    qty = add_noise_qty(50 * seasonal_factor(actual_date), 0.2)
    add_order(actual_date, "대성기업", "AL6061", qty, "P3" + ("+P10" if interval > 14 else ""))

    daesung_date += timedelta(days=interval + random.randint(-1, 1))

# P4: 한진산업 발주 후 2~4일 뒤 대성기업 추가 발주 (70% 확률)
hanjin_orders = [o for o in orders if o["customer"] == "한진산업" and o["item"] == "STS304"]
for ho in hanjin_orders:
    if random.random() < 0.70:
        delay = random.randint(2, 4)
        follow_date = datetime.strptime(ho["date"], "%Y-%m-%d") + timedelta(days=delay)
        while follow_date.weekday() >= 5:
            follow_date += timedelta(days=1)
        if follow_date <= END_DATE:
            qty = add_noise_qty(30, 0.25)
            add_order(follow_date, "대성기업", "AL6061", qty, "P4")


# ============================================================
# P6. 세진테크: 분기 시작 달(1,4,7,10월) 대량 발주
# P9. 한진산업 대형 발주 다음 달에 세진테크 추가 대량 발주
# ============================================================
for year in [2025, 2026]:
    for month in [1, 4, 7, 10]:
        if datetime(year, month, 1) < START_DATE or datetime(year, month, 1) > END_DATE:
            continue
        order_date = get_first_business_day(year, month, week=2)
        if order_date <= END_DATE:
            # 여러 품목 대량 발주
            add_order(order_date, "세진테크", "STS304",
                      add_noise_qty(200, 0.15), "P6")
            add_order(order_date + timedelta(days=1), "세진테크", "AL5052",
                      add_noise_qty(150, 0.15), "P6")
            add_order(order_date + timedelta(days=1), "세진테크", "CARBON_STEEL",
                      add_noise_qty(300, 0.15), "P6")

# P9: 한진산업 대형 발주 다음 달 세진테크 추가 발주
for (y, m) in hanjin_large_months:
    next_m = m + 1 if m < 12 else 1
    next_y = y if m < 12 else y + 1
    if datetime(next_y, next_m, 1) <= END_DATE:
        order_date = get_first_business_day(next_y, next_m, week=3)
        if order_date <= END_DATE:
            add_order(order_date, "세진테크", "STS316",
                      add_noise_qty(100, 0.2), "P9")


# ============================================================
# P8. 동아전자: 견적 요청 1~2주 후 발주
# ============================================================
dongah_schedule = [
    datetime(2025, 4, 15), datetime(2025, 6, 10), datetime(2025, 7, 22),
    datetime(2025, 9, 5), datetime(2025, 10, 20), datetime(2025, 12, 8),
    datetime(2026, 2, 3), datetime(2026, 3, 10),
]

for quote_date in dongah_schedule:
    if quote_date > END_DATE:
        break
    # 견적 요청 이벤트
    item = random.choice(["SS_BOLT_M10", "SS_NUT_M10", "GASKET_A", "PTFE_SHEET"])
    add_event(quote_date, "동아전자", "견적요청", item, f"{item} 단가 문의")

    # 1~2주 후 발주 (85% 확률)
    if random.random() < 0.85:
        delay = random.randint(7, 14)
        order_date = quote_date + timedelta(days=delay)
        while order_date.weekday() >= 5:
            order_date += timedelta(days=1)
        if order_date <= END_DATE:
            qty = add_noise_qty(random.choice([50, 100, 200]), 0.2)
            add_order(order_date, "동아전자", item, qty, "P8")
            # 가끔 추가 품목도 같이 주문
            if random.random() < 0.4:
                extra = random.choice(["SS_BOLT_M10", "SS_NUT_M10"])
                add_order(order_date, "동아전자", extra,
                          add_noise_qty(100, 0.3), "P8_extra")


# ============================================================
# 명성산업: 월 2회 정기 (15일 간격, 비교적 단순)
# ============================================================
ms_date = START_DATE + timedelta(days=4)
while ms_date <= END_DATE:
    actual = ms_date
    while actual.weekday() >= 5:
        actual += timedelta(days=1)
    item = random.choice(["PIPE_SCH40", "CARBON_STEEL"])
    qty = add_noise_qty(80 if item == "CARBON_STEEL" else 15, 0.2)
    add_order(actual, "명성산업", item, qty, "regular")
    ms_date += timedelta(days=15 + random.randint(-1, 1))


# ============================================================
# 우진소재: 봄/가을 집중 (3~5월, 9~11월)
# ============================================================
for year in [2025, 2026]:
    for month in [3, 4, 5, 9, 10, 11]:
        if datetime(year, month, 1) < START_DATE or datetime(year, month, 1) > END_DATE:
            continue
        n_orders = random.randint(2, 4)
        for _ in range(n_orders):
            day = random.randint(1, 28)
            d = datetime(year, month, day)
            while d.weekday() >= 5:
                d += timedelta(days=1)
            if d <= END_DATE:
                item = random.choice(["STS316", "AL6061", "CU_PLATE"])
                qty = add_noise_qty(random.choice([30, 50, 70]), 0.25)
                add_order(d, "우진소재", item, qty, "seasonal")


# ============================================================
# 노이즈: 삼호금속, 태광스틸 — 불규칙 소량 발주
# ============================================================
for customer in ["삼호금속", "태광스틸"]:
    n_orders = random.randint(15, 25)
    for _ in range(n_orders):
        d = START_DATE + timedelta(days=random.randint(0, 364))
        while d.weekday() >= 5:
            d += timedelta(days=1)
        if d <= END_DATE:
            item = random.choice(list(ITEMS.keys()))
            qty = add_noise_qty(random.randint(10, 60), 0.3)
            add_order(d, customer, item, qty, "noise")

# 추가 노이즈: 기존 고객의 비정기 발주
for _ in range(30):
    customer = random.choice(list(CUSTOMERS.keys()))
    d = START_DATE + timedelta(days=random.randint(0, 364))
    while d.weekday() >= 5:
        d += timedelta(days=1)
    if d <= END_DATE:
        item = random.choice(list(ITEMS.keys()))
        qty = add_noise_qty(random.randint(5, 40), 0.3)
        add_order(d, customer, item, qty, "noise")


# ============================================================
# 추가 이벤트: 가격 문의, 샘플 요청 등
# ============================================================
# 한진산업: 대형 발주 전에 가격 문의
for (y, m) in hanjin_large_months:
    inquiry_date = datetime(y, m, 1) - timedelta(days=random.randint(10, 20))
    if inquiry_date >= START_DATE:
        add_event(inquiry_date, "한진산업", "가격문의", "STS304", "대량 구매 단가 문의")
        if random.random() < 0.5:
            add_event(inquiry_date + timedelta(days=2), "한진산업", "가격문의", "STS316", "STS316 단가도 확인")

# 랜덤 이벤트
for _ in range(20):
    d = START_DATE + timedelta(days=random.randint(0, 364))
    customer = random.choice(list(CUSTOMERS.keys()))
    etype = random.choice(["가격문의", "샘플요청", "납기확인"])
    item = random.choice(list(ITEMS.keys()))
    add_event(d, customer, etype, item, "")


# ============================================================
# 저장
# ============================================================
df_orders = pd.DataFrame(orders).drop(columns=["_pattern"])
df_orders = df_orders.sort_values("date").reset_index(drop=True)

df_orders_with_label = pd.DataFrame(orders)
df_orders_with_label = df_orders_with_label.sort_values("date").reset_index(drop=True)

df_events = pd.DataFrame(events)
df_events = df_events.sort_values("date").reset_index(drop=True)

# 고객 마스터
df_customers = pd.DataFrame([
    {"customer": k, **v} for k, v in CUSTOMERS.items()
])

# 품목 마스터
df_items = pd.DataFrame([
    {"item": k, **v} for k, v in ITEMS.items()
])

out_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(out_dir, "data")
os.makedirs(data_dir, exist_ok=True)

df_orders.to_csv(os.path.join(data_dir, "orders.csv"), index=False, encoding="utf-8-sig")
df_orders_with_label.to_csv(os.path.join(data_dir, "orders_with_labels.csv"), index=False, encoding="utf-8-sig")
df_events.to_csv(os.path.join(data_dir, "events.csv"), index=False, encoding="utf-8-sig")
df_customers.to_csv(os.path.join(data_dir, "customers.csv"), index=False, encoding="utf-8-sig")
df_items.to_csv(os.path.join(data_dir, "items.csv"), index=False, encoding="utf-8-sig")

print(f"=== 데이터 생성 완료 ===")
print(f"발주 건수: {len(df_orders)}")
print(f"이벤트 건수: {len(df_events)}")
print(f"고객 수: {len(df_customers)}")
print(f"품목 수: {len(df_items)}")
print(f"\n고객별 발주 건수:")
print(df_orders.groupby("customer").size().sort_values(ascending=False).to_string())
print(f"\n품목별 발주 건수:")
print(df_orders.groupby("item").size().sort_values(ascending=False).to_string())
print(f"\n월별 발주 건수:")
df_orders["month"] = pd.to_datetime(df_orders["date"]).dt.to_period("M")
print(df_orders.groupby("month").size().to_string())
print(f"\n심어둔 패턴 분포 (정답 레이블):")
print(df_orders_with_label["_pattern"].value_counts().to_string())
