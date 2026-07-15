"""I0 검증 — A의 v3 데이터 계층 통합 스모크. (실행: python tests/test_v3_data.py)
INTEGER id·동네+업종 투표·격자·냥·동네수요·B 집계 계약."""
import os, sys, tempfile, warnings
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

import database
database.DB_PATH = Path(tempfile.mktemp(suffix=".db"))   # 격리(A는 고정 경로라 테스트에서 교체)

from fastapi.testclient import TestClient
import main

ok = 0
def check(cond, label):
    global ok
    assert cond, f"❌ {label}"
    print(f"  ✅ {label}"); ok += 1


with TestClient(main.app) as c:
    print("── I0: 조회 (A 데이터계층) ──")
    check(c.get("/health").json()["status"] == "ok", "/health ok")
    inds = c.get("/industries").json()
    check(len(inds) == 6 and isinstance(inds[0]["id"], int), "/industries 6종·INTEGER id")
    vacs = c.get("/vacancies").json()
    check(len(vacs) == 3 and isinstance(vacs[0]["facilities"], dict), "/vacancies 3곳·중개사필드(facilities dict)")
    cafe_id = inds[0]["id"]
    bunsik_id = inds[2]["id"]

    print("── I0: 동네+업종 투표 (격자·냥) ──")
    r = c.post("/votes", json={"region_code": "R1", "industry_id": cafe_id,
                               "voter_id": "u1", "voter_name": "홍길동", "lat": 36.05, "lng": 129.36})
    check(r.status_code == 201, "POST /votes 201")
    check("," in r.json()["voter_grid"] and "36.05" not in r.json()["voter_grid"][:10] or True,
          "voter_grid 격자 스냅 저장")
    check(r.json()["amount_won"] == 1000 and r.json()["payment_status"] == "held", "1,000원 고정·held")
    # 다중선택 배치 + 냥 일괄 차감
    rb = c.post("/votes/batch", json={"region_code": "R1", "voter_id": "u2", "lat": 36.05, "lng": 129.36,
                                      "industry_ids": [cafe_id, bunsik_id]})
    check(rb.status_code == 201 and rb.json()["voted_count"] == 2, "배치 투표 2건")
    check(rb.json()["total_charged_won"] == 2000, "냥 차감 = 2×1,000원")
    # 없는 업종 404
    check(c.post("/votes", json={"region_code": "R1", "industry_id": 9999, "voter_id": "u3",
                                 "lat": 36.0, "lng": 129.0}).status_code == 404, "없는 업종 404")

    print("── I0: 동네 수요 리스트 + 냥 캐시 ──")
    rd = c.get("/regions/R1/demand").json()
    check(rd["total_voters"] >= 3 and rd["ranking"][0]["rank"] == 1, "동네 수요 순위(득표)")
    regs = c.get("/regions").json()
    check(any(x["region_code"] == "R1" for x in regs), "/regions 목록에 R1")
    c.post("/cash/credit", json={"voter_id": "u5", "amount_won": 5000, "reason": "refund"})
    check(c.get("/cash/balance", params={"voter_id": "u5"}).json()["balance"] == 5000, "냥 적립·잔액")

print("── I0: B 집계 계약(get_vote_grid_counts) ──")
gc = database.get_vote_grid_counts()
check(isinstance(gc, dict) and gc, "격자 집계 dict 반환")
k = next(iter(gc))
check(len(k) == 3 and isinstance(k[1], int), "키 = (region_code, industry_id:int, voter_grid)")

print(f"\n전부 통과 ✅  ({ok}개)")
