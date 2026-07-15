"""I4b 검증 — GET /map, POST /placements, /placements/{id}/open. (실행: python tests/test_map_route_v4.py)"""
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
    vacs = c.get("/vacancies").json()
    region = vacs[0]["region_code"]
    vac_ids = [v["id"] for v in vacs]

    print("── I4b: 아무 placements도 없으면 전부 vacant ──")
    m0 = c.get("/map", params={"region_code": region}).json()
    check(len(m0) == len(vacs), "동네 공실 수만큼 반환")
    check(all(row["status"] == "vacant" for row in m0), "전부 vacant")
    check(all("lat" in row and "lng" in row for row in m0), "좌표 포함")

    print("── I4b: placements 생성 → preparing ──")
    r = c.post("/placements", json={"region_code": region, "industry_id": cafe_id, "vacancy_id": vac_ids[0]})
    check(r.status_code == 200 and r.json()["status"] == "preparing", "생성 시 status=preparing")
    pid = r.json()["id"]
    m1 = c.get("/map", params={"region_code": region}).json()
    row0 = next(x for x in m1 if x["vacancy_id"] == vac_ids[0])
    check(row0["status"] == "preparing", "그 공실만 preparing")
    others_vacant = all(x["status"] == "vacant" for x in m1 if x["vacancy_id"] != vac_ids[0])
    check(others_vacant, "나머지 공실은 여전히 vacant")

    print("── I4b: 개업 확정 → open ──")
    r_open = c.post(f"/placements/{pid}/open")
    check(r_open.status_code == 200 and r_open.json()["status"] == "open", "확인 버튼 → status=open")
    m2 = c.get("/map", params={"region_code": region}).json()
    row0_2 = next(x for x in m2 if x["vacancy_id"] == vac_ids[0])
    check(row0_2["status"] == "open", "지도에 open 반영")

    print("── I4b: 없는 업종/공실로 placements 생성 시 404 ──")
    check(c.post("/placements", json={"region_code": region, "industry_id": 9999, "vacancy_id": vac_ids[0]}).status_code == 404,
          "없는 industry_id → 404")
    check(c.post("/placements", json={"region_code": region, "industry_id": cafe_id, "vacancy_id": 9999}).status_code == 404,
          "없는 vacancy_id → 404")
    check(c.post("/placements/999999/open").status_code == 404, "없는 placement id로 open → 404")

    print("── I4b: 다른 동네는 영향 없음(동네별 격리) ──")
    m_other = c.get("/map", params={"region_code": "NO-SUCH-REGION"}).json()
    check(m_other == [], "공실 없는 동네는 빈 리스트")

print(f"\n전부 통과 ✅  ({ok}개)")
