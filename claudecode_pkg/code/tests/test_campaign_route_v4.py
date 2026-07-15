"""I4a Step2 검증 — POST /campaigns, /campaigns/{id}/resolve 라우터 통합. (실행: python tests/test_campaign_route_v4.py)"""
import os, sys, tempfile, warnings
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

os.environ["OPENAI_API_KEY"] = ""

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
    region = "REG-CAMPAIGN-TEST"

    print("── I4a: 캠페인 생성·조회 ──")
    r = c.post("/campaigns", json={"region_code": region, "deadline": "2026-01-01", "coupon_value_won": 3000})
    check(r.status_code == 200 and r.json()["status"] == "open", "생성 200·status=open")
    cid = r.json()["id"]
    check(c.get(f"/campaigns/{cid}").json()["region_code"] == region, "조회 일치")
    check(c.get("/campaigns/999999").status_code == 404, "없는 캠페인 404")

    print("── I4a: 기간 중이면 resolve해도 변화 없음 ──")
    r_open = c.post(f"/campaigns/{cid}/resolve", params={"as_of": "2025-06-01"})  # deadline(2026-01-01) 이전
    check(r_open.json()["action"] == "none" and r_open.json()["status"] == "open", "기간 중 → action=none")
    check(r_open.json()["refunded_count"] == 0, "환불 0건(기간 중)")

    print("── I4a: 이 동네에 held 투표 3건 만들어두기 ──")
    for i in range(3):
        vr = c.post("/votes", json={"region_code": region, "industry_id": cafe_id,
                                    "voter_id": f"voter-{i}", "voter_name": f"user{i}",
                                    "lat": 36.05, "lng": 129.36})
        check(vr.status_code == 201, f"투표 {i} 생성")
    demand_before = c.get(f"/regions/{region}/demand").json()
    check(demand_before["total_voters"] == 3, "환불 전 동네 수요=3")

    print("── I4a: 기한 경과 → resolve 시 전건 환불 ──")
    r_expired = c.post(f"/campaigns/{cid}/resolve", params={"as_of": "2026-06-01"})  # deadline 지남
    body = r_expired.json()
    check(body["action"] == "expire" and body["status"] == "failed" or body["expired"] is True, "기한 경과 판정")
    check(body["refunded_count"] == 3, f"3건 환불 (실제 {body['refunded_count']})")
    check(body["refunded_total_won"] == 3000, f"환불 총액 3000원 (실제 {body['refunded_total_won']})")

    print("── I4a: 환불 후 캐시 잔액·동네 수요 반영 확인 ──")
    for i in range(3):
        bal = c.get("/cash/balance", params={"voter_id": f"voter-{i}"}).json()["balance"]
        check(bal == 1000, f"voter-{i} 잔액 1000원 (실제 {bal})")
    demand_after = c.get(f"/regions/{region}/demand").json()
    check(demand_after["total_voters"] == 0, "환불 후 동네 수요=0(refunded 집계 제외)")

    print("── I4a: 캠페인 status='failed' 확인, 재실행해도 중복 환불 없음(멱등) ──")
    check(c.get(f"/campaigns/{cid}").json()["status"] == "failed", "캠페인 failed 전환")
    r_again = c.post(f"/campaigns/{cid}/resolve", params={"as_of": "2026-06-01"})
    check(r_again.json()["action"] == "none", "이미 종료된 캠페인 재실행 → action=none")
    check(r_again.json()["refunded_count"] == 0, "재실행 시 추가 환불 0건(중복 방지)")
    for i in range(3):
        bal = c.get("/cash/balance", params={"voter_id": f"voter-{i}"}).json()["balance"]
        check(bal == 1000, f"voter-{i} 잔액 여전히 1000원(중복 적립 없음, 실제 {bal})")

print(f"\n전부 통과 ✅  ({ok}개)")
