"""I2 검증 — 리포트 v3(업종→공실 순위). (실행: python tests/test_report_v3.py)
동네수요 리스트↔리포트 수치 일치·좌표 반환·포화% 100 미도달·score=engine 동일성."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import engine
import report

ok = 0
def check(cond, label):
    global ok
    assert cond, f"❌ {label}"
    print(f"  ✅ {label}"); ok += 1


INDUSTRIES = [
    {"id": 1, "name": "카페", "min_area_m2": 20, "max_area_m2": 60,
     "avg_startup_cost_manwon": 5000, "licenses": None},
    {"id": 2, "name": "분식", "min_area_m2": 15, "max_area_m2": 40,
     "avg_startup_cost_manwon": 3000, "licenses": "일반음식점 신고"},
]

VACANCIES = [
    {"id": 1, "name": "가까운 자리", "region_code": "R1", "lat": 36.050, "lng": 129.360,
     "area_m2": 30, "floor": "1층", "competitors": {"카페": 2}, "address": "R1 1번지", "is_seed": 1},
    {"id": 2, "name": "먼 자리", "region_code": "R1", "lat": 36.058, "lng": 129.360,  # ~900m 북
     "area_m2": 30, "floor": "지하", "competitors": {"카페": 2}, "address": "R1 2번지", "is_seed": 1},
    {"id": 3, "name": "다른 동네 자리", "region_code": "R2", "lat": 36.050, "lng": 129.360,
     "area_m2": 30, "floor": "1층", "competitors": {}, "address": "R2 1번지", "is_seed": 1},
]

# A 계약 형태 그대로: {(region_code, industry_id, voter_grid): 표수}. R2 표는 R1 리포트에 절대 섞이면 안 됨.
GRID_VOTES_ALL = {
    ("R1", 1, "36.050,129.360"): 10,   # 카페, "가까운 자리"와 같은 격자(거리 0)
    ("R1", 2, "36.050,129.360"): 4,    # 분식
    ("R2", 1, "36.050,129.360"): 999,  # 다른 동네 — R1 리포트에 절대 섞이면 안 됨
}


print("── I2: 기본 리포트 구조 ──")
rep = report.build_report(1, "R1", VACANCIES, INDUSTRIES, GRID_VOTES_ALL)
check(rep is not None, "R1 카페 리포트 생성됨")
check(rep["industry"]["name"] == "카페", "업종 이름")
check(len(rep["vacancies"]) == 2, "R1 소속 공실만 2곳(다른 동네 제외)")

print("── I2: 좌표 반환 ──")
for card in rep["vacancies"]:
    check("lat" in card["vacancy"] and "lng" in card["vacancy"], f"공실 {card['vacancy']['id']} 좌표 포함")

print("── I2: 순위 = score 내림차순, 가까운 자리가 1위 ──")
check(rep["vacancies"][0]["rank"] == 1 and rep["vacancies"][1]["rank"] == 2, "rank 1·2 부여")
check(rep["vacancies"][0]["vacancy"]["name"] == "가까운 자리", "가까운 자리가 1위(거리감쇠로 demand 큼)")
check(rep["vacancies"][0]["engine_score"] >= rep["vacancies"][1]["engine_score"], "score 내림차순")

print("── I2: 동네수요 리스트 ↔ 리포트 수치 일치 (다른 동네 표 안 섞임) ──")
# database.get_region_demand()와 동일 규칙(그 region의 그 업종 표 원시합)으로 직접 계산해 대조.
expected_region_total = sum(n for (rc, iid, _g), n in GRID_VOTES_ALL.items() if rc == "R1" and iid == 1)
check(rep["region_total_demand"]["count"] == expected_region_total == 10,
      f"region_total_demand=10 (R2의 999 안 섞임, 실제 {rep['region_total_demand']['count']})")

print("── I2: 포화 % 100 미도달 ──")
huge_votes = {("R1", 1, "36.050,129.360"): 1_000_000}
rep_huge = report.build_report(1, "R1", VACANCIES, INDUSTRIES, huge_votes)
check(all(c["adequacy_pct"] <= 99 for c in rep_huge["vacancies"]), "표 100만건이어도 적합도 ≤99%")
check(report._pct(0) == 0, "score=0 → 0%")

print("── I2: score = engine 동일성 (지도 배치와 같은 함수·같은 값) ──")
# build_report가 만든 grid_votes(이 동네만 필터)로 engine.score를 직접 호출한 값과 카드의 engine_score가 같아야 한다.
region_vacs = [v for v in VACANCIES if v["region_code"] == "R1"]
grid_votes_r1 = report._region_grid_votes(1, "R1", GRID_VOTES_ALL)
cafe = INDUSTRIES[0]
direct = {v["id"]: engine.score(v, cafe, region_vacs, grid_votes_r1)["score"] for v in region_vacs}
for card in rep["vacancies"]:
    vid = card["vacancy"]["id"]
    check(abs(card["engine_score"] - direct[vid]) < 1e-9,
          f"공실{vid} 리포트 score == engine.score 직접호출 ({card['engine_score']} == {direct[vid]})")

print("── I2: floor_fit이 이제 적합도%에 반영됨(v1과 달라진 점) ──")
# demand>0인 '가까운 자리'(id=1, 거리 0 → demand=10)와 층만 지하인 쌍둥이 공실을 비교.
# ('먼 자리'는 거리 900m로 감쇠 0이라 floor_fit을 곱해도 0×0.5=0이 되어 이 비교에 못 씀.)
twin_basement = {**VACANCIES[0], "id": 99, "floor": "지하"}
rep_twin = report.build_report(1, "R1", region_vacs + [twin_basement], INDUSTRIES, GRID_VOTES_ALL)
card_1f = next(c for c in rep_twin["vacancies"] if c["vacancy"]["id"] == 1)
card_basement = next(c for c in rep_twin["vacancies"] if c["vacancy"]["id"] == 99)
check(card_1f["engine_score"] > card_basement["engine_score"], "1층이 지하보다 score 높음(floor_fit 반영)")
check(card_basement["floor_basis"]["floor_fit"] == 0.5, "지하 floor_fit=0.5 노출")

print("── I2: 없는 업종/동네는 None(404) ──")
check(report.build_report(9999, "R1", VACANCIES, INDUSTRIES, GRID_VOTES_ALL) is None, "없는 industry_id → None")
check(report.build_report(1, "NO-SUCH-REGION", VACANCIES, INDUSTRIES, GRID_VOTES_ALL) is None, "공실 없는 동네 → None")

print("── I2: DISCLAIMER·유동인구 정직 부재 유지 (절대 규칙) ──")
check("보장하지 않습니다" in rep["disclaimer"], "DISCLAIMER 문구 유지")
check(rep["foot_traffic"]["available"] is False, "유동인구 미제공 명시")

print(f"\n전부 통과 ✅  ({ok}개)")
