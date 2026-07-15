"""P4 검증 — AI 해설: 순수 로직(facts·화이트리스트·검증) + 키 없음 폴백 + 라우터 배선.
실제 GPT 호출은 키 확보 후 검증 대상(여기선 키 없이 돌아가는 안전장치를 검증). (실행: python tests/test_ai_explain.py)"""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ai_explain as ai
import report as report_mod
import seed_dummy as s

ok = 0
def check(cond, label):
    global ok
    assert cond, f"❌ {label}"
    print(f"  ✅ {label}"); ok += 1


REP = report_mod.build_report("V-A", s.VACANCIES, s.INDUSTRIES, s.VOTE_COUNTS, campaign=s.CAMPAIGN)
facts = ai.facts_from_report(REP)
allowed = ai.allowed_numbers(facts)

print("── P4: facts 추출 · 화이트리스트 ──")
check(facts["추천업종"] == REP["conclusion"]["recommended_industry"], "facts 추천업종 = 리포트 1순위")
check(facts["대기고객_명"] == REP["waiting_customers"]["count"], "facts 대기고객 = 리포트 값")
check(facts["쿠폰총액_원"] == facts["대기고객_명"] * facts["쿠폰단가_원"], "쿠폰총액 = 대기 × 단가(산수)")
check(float(facts["적합도_percent"]) in allowed, "적합도 %가 화이트리스트에 포함")

print("── P4: 숫자 추출 ──")
check(ai.extract_numbers("적합도 37%, 쿠폰 3,000원, 평균 2.1배") == [37.0, 3000.0, 2.1],
      "콤마·소수·% 숫자 파싱")
check(ai.extract_numbers("숫자 없음") == [], "숫자 없으면 빈 목록")

print("── P4: 검증(환각 억제) ──")
good = "이 자리는 반찬가게가 후보입니다. 대기 고객이 18명이고 적합도는 37%입니다."
check(ai.validate(good, allowed)[0], "허용 숫자만 → 통과")
check(not ai.validate("예상 매출은 5000만원입니다.", allowed)[0], "화이트리스트 밖 숫자 → 차단")
check(not ai.validate("이 업종은 성공을 보장합니다.", allowed)[0], "보장 표현 → 차단")
check(ai.validate("명당은 성공을 보장하지 않습니다.", allowed)[0], "부정형(보장하지 않) → 허용")
check(not ai.validate("펀딩으로 투자하세요.", allowed)[0], "금칙어(투자/펀딩) → 차단")
check(ai.validate("검증된 수요를 중심으로 후보를 봅니다.", allowed)[0], "숫자 없는 문장 → 통과")

print("── P4: 프롬프트 ──")
msgs = ai.build_messages(facts)
check(msgs[0]["role"] == "system" and "새로운 숫자" in msgs[0]["content"], "system 프롬프트에 환각 억제 지시")
check(msgs[1]["role"] == "user" and "반찬가게" in msgs[1]["content"], "user 메시지에 확정 수치 JSON")

print("── P4: 키 없음 폴백 ──")
saved = os.environ.pop("OPENAI_API_KEY", None)
check(ai.generate_explanation(REP) is None, "키 없으면 None(해설 없이 리포트만)")
if saved is not None:
    os.environ["OPENAI_API_KEY"] = saved

print("── P4: 라우터 배선(키 없음 → ai_explanation=null, 리포트 정상) ──")
os.environ.pop("OPENAI_API_KEY", None)
os.environ["MYDANG_DB"] = tempfile.mktemp(suffix=".db")
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as c:
    r = c.get("/report/V-A").json()
    check("ai_explanation" in r, "응답에 ai_explanation 키 존재")
    check(r["ai_explanation"] is None, "키 없을 때 ai_explanation = null")
    check(r["conclusion"]["recommended_industry"], "리포트 본문은 그대로 정상")

print(f"\n전부 통과 ✅  ({ok}개)")
