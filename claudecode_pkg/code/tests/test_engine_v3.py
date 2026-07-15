"""I1 검증 — 엔진 v3(거리감쇠 grid demand + floor_fit + 헝가리안). (실행: python tests/test_engine_v3.py)"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import engine

ok = 0
def check(cond, label):
    global ok
    assert cond, f"❌ {label}"
    print(f"  ✅ {label}"); ok += 1


print("── I1: 거리 감쇠 ──")
check(engine.distance_weight(0) == 1.0, "0m → 1.0")
check(engine.distance_weight(500) == 1.0, "500m(경계) → 1.0")
check(abs(engine.distance_weight(650) - 0.5) < 1e-9, "650m → 0.5(선형 중간)")
check(engine.distance_weight(800) == 0.0, "800m(경계) → 0")
check(engine.distance_weight(1000) == 0.0, ">800m → 0")
check(engine.distance_weight(600) > engine.distance_weight(700), "멀수록 감소(단조)")

print("── I1: floor_fit ──")
check(engine.floor_fit("1층") == 1.0, "1층 → 1.0")
check(engine.floor_fit("2층이상") == 0.7, "2층이상 → 0.7")
check(engine.floor_fit("지하") == 0.5, "지하 → 0.5")
check(engine.floor_fit(None) == 1.0, "미상 → 1.0(감점 없음)")

print("── I1: score 손계산 ──")
# 공실: 격자 중심과 정확히 같은 좌표에 두어 거리 0(감쇠 1.0). 카페 격자에 표 10.
vac = {"id": 1, "name": "V1", "lat": 36.050, "lng": 129.360, "area_m2": 30,
       "floor": "1층", "competitors": {}}
ind = {"id": 1, "name": "카페", "min_area_m2": 20, "max_area_m2": 60}
grid_votes = {(1, "36.050,129.360"): 10}
s = engine.score(vac, ind, [vac], grid_votes)
# demand=10×1.0=10, area_fit=1.0(30 in 20~60), comp=1.0(경쟁 없음), floor=1.0 → 10
check(s["score"] == 10.0, f"손계산 score=10.0 (실제 {s['score']})")
check(s["breakdown"]["floor_fit"] == 1.0 and s["breakdown"]["demand"] == 10.0, "breakdown demand·floor_fit")

# 층수만 2층이상으로 바꾸면 0.7배
s2 = engine.score({**vac, "floor": "2층이상"}, ind, [vac], grid_votes)
check(abs(s2["score"] - 7.0) < 1e-9, "2층이상이면 score×0.7 = 7.0")

# 면적 벗어나면 감점(하한 0.2). 5㎡ → area_fit=max(0.2, 5/20)=0.25
s3 = engine.score({**vac, "area_m2": 5}, ind, [vac], grid_votes)
check(abs(s3["breakdown"]["area_fit"] - 0.25) < 1e-9, "면적 미달 감점(5/20=0.25)")

print("── I1: 거리 감쇠가 공실별 수요를 가른다 ──")
# 같은 격자 표를 두 공실이 다른 거리에서 봄 → 가까운 쪽 demand 큼
near = {"id": 1, "name": "N", "lat": 36.050, "lng": 129.360, "area_m2": 30, "floor": "1층", "competitors": {}}
far = {"id": 2, "name": "F", "lat": 36.058, "lng": 129.360, "area_m2": 30, "floor": "1층", "competitors": {}}  # ~900m 북
gv = {(1, "36.050,129.360"): 10}
sn = engine.score(near, ind, [near, far], gv)["score"]
sf = engine.score(far, ind, [near, far], gv)["score"]
check(sn > sf, f"가까운 공실 demand 큼 (near {sn} > far {sf})")

print("── I1: 배치(겹침 해소) ──")
inds = [{"id": 1, "name": "카페", "min_area_m2": 20, "max_area_m2": 60},
        {"id": 2, "name": "분식", "min_area_m2": 15, "max_area_m2": 40}]
vacs = [near, far]
gv2 = {(1, "36.050,129.360"): 10, (2, "36.058,129.360"): 8}  # 카페는 near 근처, 분식은 far 근처
alloc = engine.allocate(vacs, inds, gv2)
assigned = {a["vacancy_id"]: a["industry_id"] for a in alloc["allocations"]}
check(len(set(assigned.values())) == len(assigned), "업종 겹침 없음")
check(len(alloc["allocations"]) == 2, "두 공실 모두 배정")
check(all("floor_fit" in a["breakdown"] for a in alloc["allocations"]), "배치 breakdown 에 floor_fit")
check(alloc["allocations"][0]["runners_up"], "차순위 포함")

print(f"\n전부 통과 ✅  ({ok}개)")
