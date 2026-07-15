"""I3 Step2 검증 — POST /report 라우터 통합 테스트. (실행: python tests/test_report_route_v3.py)
404 케이스·50냥 차감·키 없으면 해설 null·동네수요 리스트와 수치 일치."""
import os, sys, tempfile, warnings
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

os.environ["OPENAI_API_KEY"] = ""  # .env 의 플레이스홀더가 setdefault로 덮어쓰지 못하게 미리 "없음"으로 고정
                                    # (실제 네트워크 호출 없이 "키 없음" 분기를 결정적으로 테스트)

import database
database.DB_PATH = Path(tempfile.mktemp(suffix=".db"))  # 격리

from fastapi.testclient import TestClient
import main

ok = 0
def check(cond, label):
    global ok
    assert cond, f"❌ {label}"
    print(f"  ✅ {label}"); ok += 1


with TestClient(main.app) as c:
    inds = c.get("/industries").json()
    cafe_id = inds[0]["id"]
    region_code = c.get("/regions").json()[0]["region_code"]  # 시드 지역(양덕동 임시 코드)

    print("── I3: POST /report 정상 케이스 ──")
    r = c.post("/report", json={"industry_id": cafe_id, "region_code": region_code, "voter_id": "founder-1"})
    check(r.status_code == 200, "POST /report 200")
    body = r.json()
    check(body["industry"]["id"] == cafe_id, "요청 업종과 응답 일치")
    check(len(body["vacancies"]) >= 1, "추천 공실 카드 1개 이상")
    check(all("lat" in card["vacancy"] and "lng" in card["vacancy"] for card in body["vacancies"]), "카드마다 좌표 포함")
    check(all(card["adequacy_pct"] <= 99 for card in body["vacancies"]), "적합도 100 미도달")

    print("── I3: 키 없으면 해설 null(리포트 본문은 그대로) ──")
    check(all(card["ai_explanation"] is None for card in body["vacancies"]), "ai_explanation 전부 None")
    check("headline" in body and "region_total_demand" in body, "리포트 본문 필드 정상 유지")

    print("── I3: 동네수요 리스트 ↔ 리포트 수치 일치 ──")
    demand = c.get(f"/regions/{region_code}/demand").json()
    cafe_row = next(x for x in demand["ranking"] if x["industry_id"] == cafe_id)
    check(body["region_total_demand"]["count"] == cafe_row["vote_count"],
          f"리포트 region_total_demand({body['region_total_demand']['count']}) == "
          f"동네수요 리스트 카페 표수({cafe_row['vote_count']})")

    print("── I3: 50냥(500원) 차감 확인 ──")
    balance_before = c.get("/cash/balance", params={"voter_id": "founder-2"}).json()["balance"]
    c.post("/cash/credit", json={"voter_id": "founder-2", "amount_won": 5000, "reason": "refund"})
    r2 = c.post("/report", json={"industry_id": cafe_id, "region_code": region_code, "voter_id": "founder-2"})
    check(r2.json()["charge"]["charged_won"] == 500 and r2.json()["charge"]["charged_nyang"] == 50, "50냥=500원 차감액 표기")
    balance_after = c.get("/cash/balance", params={"voter_id": "founder-2"}).json()["balance"]
    check(balance_after == 5000 - 500, f"잔액 5000→4500 (실제 {balance_after})")
    check(r2.json()["charge"]["insufficient_balance"] is False, "잔액 충분하면 insufficient_balance=False")

    print("── I3: 잔액 부족해도 막지 않고 플래그만(기존 /votes/batch 정책과 동일) ──")
    r3 = c.post("/report", json={"industry_id": cafe_id, "region_code": region_code, "voter_id": "founder-broke"})
    check(r3.status_code == 200, "잔액 0이어도 리포트는 생성됨(200)")
    check(r3.json()["charge"]["insufficient_balance"] is True, "insufficient_balance=True 플래그")

    print("── I3: 없는 업종/동네는 404, 과금 안 됨 ──")
    r4 = c.post("/report", json={"industry_id": 9999, "region_code": region_code, "voter_id": "founder-3"})
    check(r4.status_code == 404, "없는 industry_id → 404")
    r5 = c.post("/report", json={"industry_id": cafe_id, "region_code": "NO-SUCH-REGION", "voter_id": "founder-3"})
    check(r5.status_code == 404, "공실 없는 동네 → 404")
    check(c.get("/cash/balance", params={"voter_id": "founder-3"}).json()["balance"] == 0,
          "404 케이스는 과금 안 됨(잔액 그대로 0)")

print(f"\n전부 통과 ✅  ({ok}개)")
