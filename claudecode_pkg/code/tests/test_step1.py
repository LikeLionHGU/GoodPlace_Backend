"""
1단계 검증 — DB·시드·집계 인터페이스. 지시서의 검증 기준 9개를 그대로 assert.
실행: python tests/test_step1.py   (통과 시 전부 PASS, 실패 시 AssertionError)
임시 DB 파일을 새로 만들어 검증하므로 운영 DB(mydang.db)를 건드리지 않는다.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import db
import seed_dummy

ok = 0
def check(name, cond):
    global ok
    assert cond, f"❌ FAIL: {name}"
    ok += 1
    print(f"  ✅ {name}")


tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
conn = db.connect(tmp.name)
seeded = db.reset_seed(conn)

print("── 1단계: DB·시드 ──")
# ① 업종 시드 개수 일치
check("industries 개수 = seed_dummy.INDUSTRIES 개수",
      seeded["industries"] == len(seed_dummy.INDUSTRIES))
# ② 공실 시드 개수 일치
check("vacancies 개수 = seed_dummy.VACANCIES 개수",
      seeded["vacancies"] == len(seed_dummy.VACANCIES))
# ③ 면적 범위 정합
inds = [dict(r) for r in conn.execute("SELECT * FROM industries")]
check("모든 업종 min_area_m2 < max_area_m2",
      all(i["min_area_m2"] < i["max_area_m2"] for i in inds))
# ④ 공실 면적·좌표
vacs = [dict(r) for r in conn.execute("SELECT * FROM vacancies")]
check("모든 공실 area_m2 > 0, lat/lng 존재",
      all(v["area_m2"] > 0 and v["lat"] is not None and v["lng"] is not None for v in vacs))
# ⑤ competitors JSON 정합
ind_ids = {i["id"] for i in inds}
comps = [json.loads(v["competitors"]) for v in vacs]
check("competitors 업종 id 실재 + 경쟁점 수 음수 없음",
      all(set(c) <= ind_ids and all(n >= 0 for n in c.values()) for c in comps))
# ⑥ 시드 표기 (industries·vacancies·campaign 적재 행 전부)
camps = [dict(r) for r in conn.execute("SELECT * FROM campaign")]
check("모든 시드 행 is_seed=1",
      all(r["is_seed"] == 1 for r in inds + vacs + camps) and len(camps) == 1)
check("industries.source / vacancies.evidence SEED 표기",
      all(i["source"] == "SEED" for i in inds) and all(v["evidence"] == "SEED" for v in vacs))
# ⑦ licenses 컬럼
check("industries.licenses 존재하고 비어 있지 않음",
      all(("licenses" in i) and i["licenses"] for i in inds))
# ⑧ votes 빈 상태 (투표 생성은 2단계)
check("votes 테이블 존재·0건", seeded["votes"] == 0)
check("cash_ledger 테이블 존재·0건", seeded["cash_ledger"] == 0)

print("── 1단계: 집계 인터페이스 (계약: (vacancy_id, industry_id)→투표수) ──")
# ⑨ 집계 전부 0
vc = db.get_vote_counts(conn)
check("전 조합 투표수 0 (희소 dict — 없는 키 = 0)",
      all(vc.get((v["id"], i["id"]), 0) == 0 for v in vacs for i in inds))
vc_region = db.get_vote_counts(conn, region_code=vacs[0]["region_code"])
check("region_code 필터 집계도 전부 0", sum(vc_region.values()) == 0)
# 재적재 멱등
seeded2 = db.reset_seed(conn)
check("시드 재적재 멱등(개수 동일)", seeded2 == seeded)

print("── 1단계: 조회 API 응답 형태 ──")
os.environ["MYDANG_DB"] = tmp.name  # 라우트가 임시 DB를 보게
import routes_query
h = routes_query.health()
check("/health ok + 테이블 카운트", h["status"] == "ok" and h["table_counts"]["industries"] == len(inds))
li = routes_query.list_industries()
check("/industries 개수·인허가 포함",
      li["count"] == len(inds) and all(item["licenses"] for item in li["items"]))
lv = routes_query.list_vacancies()
check("/vacancies competitors dict + 투표 요약 0",
      lv["count"] == len(vacs)
      and all(isinstance(item["competitors"], dict) for item in lv["items"])
      and all(item["votes_total"] == 0 and item["votes_by_industry"] == {} for item in lv["items"]))
lv_r = routes_query.list_vacancies(region_code=vacs[0]["region_code"])
lv_none = routes_query.list_vacancies(region_code="0000000000")
check("/vacancies region_code 파라미터 동작", lv_r["count"] == len(vacs) and lv_none["count"] == 0)
rs = routes_query.reset_seed()
check("/admin/seed/reset 동작", rs["status"] == "reset" and rs["seeded"] == seeded)

conn.close()
os.unlink(tmp.name)
print(f"\n전부 통과 ✅  ({ok}개)")
