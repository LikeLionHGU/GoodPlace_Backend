"""I3 Step1 검증 — ai_explain v3 순수 로직(키 없이). (실행: python tests/test_ai_explain_v3.py)
facts_from_report(카드별)·화이트리스트·금칙어·보장표현·generate_explanation(키없음→None)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.pop("OPENAI_API_KEY", None)  # 순수 로직만 테스트 — 실제 네트워크 호출 없이 "키 없음" 분기 확인

import report
import ai_explain

ok = 0
def check(cond, label):
    global ok
    assert cond, f"❌ {label}"
    print(f"  ✅ {label}"); ok += 1


INDUSTRIES = [{"id": 1, "name": "카페", "min_area_m2": 20, "max_area_m2": 60,
               "avg_startup_cost_manwon": 5000, "licenses": None}]
VACANCIES = [
    {"id": 1, "name": "가까운 자리", "region_code": "R1", "lat": 36.050, "lng": 129.360,
     "area_m2": 30, "floor": "1층", "competitors": {"카페": 2}, "address": "R1 1번지", "is_seed": 1},
    {"id": 2, "name": "먼 자리", "region_code": "R1", "lat": 36.050, "lng": 129.360,
     "area_m2": 30, "floor": "지하", "competitors": {"카페": 5}, "address": "R1 2번지", "is_seed": 1},
]
GRID_VOTES_ALL = {("R1", 1, "36.050,129.360"): 12}

rep = report.build_report(1, "R1", VACANCIES, INDUSTRIES, GRID_VOTES_ALL)
top_card = rep["vacancies"][0]

print("── I3: facts_from_report (카드 하나) ──")
facts = ai_explain.facts_from_report(rep, top_card)
check(facts["동네"] == "R1" and facts["업종"] == "카페", "동네·업종 추출")
check(facts["공실"] == top_card["vacancy"]["name"], "공실 이름 추출")
check(facts["적합도_percent"] == top_card["adequacy_pct"], "적합도 추출")
check(facts["동네전체수요_명"] == rep["region_total_demand"]["count"], "동네전체수요 추출(리스트↔해설 일치)")
check(facts["대기고객_명"] == top_card["waiting_customers"]["count"], "대기고객 추출")
check(facts["쿠폰총액_원"] == top_card["waiting_customers"]["coupon_total_won"], "쿠폰총액 추출(재계산 아님, 리포트 값 그대로)")

print("── I3: allowed_numbers (화이트리스트 = facts 안의 수치 전부) ──")
allowed = ai_explain.allowed_numbers(facts)
check(float(facts["적합도_percent"]) in allowed, "적합도 화이트리스트에 있음")
check(float(facts["대기고객_명"]) in allowed, "대기고객 화이트리스트에 있음")
check("동네" not in {str(x) for x in allowed}, "문자열 필드는 화이트리스트에 안 들어감")

print("── I3: extract_numbers (천단위 콤마 처리) ──")
check(ai_explain.extract_numbers("쿠폰 총액 3,000원") == [3000.0], "콤마 숫자 파싱")
check(ai_explain.extract_numbers("적합도 42%") == [42.0], "정수 파싱")

print("── I3: validate — 금칙어·보장표현·화이트리스트 ──")
ok1, reason1 = ai_explain.validate("이 자리는 투자 가치가 있습니다.", allowed)
check(not ok1 and "금칙어" in reason1, "'투자' 단어 → 거부")
ok2, reason2 = ai_explain.validate("이 업종은 반드시 성공을 보장합니다.", allowed)
check(not ok2 and "보장" in reason2, "'보장합니다' → 거부")
ok3, _ = ai_explain.validate("AI는 성공을 보장하지 않습니다.", allowed)
check(ok3, "'보장하지 않습니다'(부정형) → 허용")
ok4, reason4 = ai_explain.validate(f"대기 고객은 {facts['대기고객_명']}명이고 매출은 999999명입니다.", allowed)
check(not ok4 and "화이트리스트" in reason4, "입력에 없는 숫자(999999) → 거부")
ok5, _ = ai_explain.validate(
    f"{facts['공실']}는 적합도 {facts['적합도_percent']}%, 대기 고객 {facts['대기고객_명']}명입니다.", allowed)
check(ok5, "입력 수치만 쓴 문장 → 허용")

print("── I3: build_messages (system+user, 입력은 facts JSON만) ──")
messages = ai_explain.build_messages(facts)
check(messages[0]["role"] == "system" and messages[1]["role"] == "user", "system+user 메시지 구성")
check(facts["공실"] in messages[1]["content"], "user 메시지에 facts 값 포함(새 값 생성 아님)")

print("── I3: generate_explanation — 키 없으면 None(네트워크 호출 없이) ──")
check(ai_explain.generate_explanation(rep, top_card) is None, "OPENAI_API_KEY 없음 → None")

print(f"\n전부 통과 ✅  ({ok}개)")
