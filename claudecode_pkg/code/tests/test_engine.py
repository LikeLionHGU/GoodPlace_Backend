"""
검증 테스트 — 인수인계 문서(03·담당_B·개발계획서)의 단계별 '검증 기준'을 그대로 assert.
실행: python tests/test_engine.py   (통과 시 전부 PASS, 실패 시 AssertionError)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine import (area_fit, competition_factor, score, allocate,
                    _assign_exhaustive, _assign_greedy, _score_matrix, DEFAULT_WEIGHTS)
from report import build_report
from seed_dummy import INDUSTRIES, VACANCIES, VOTE_COUNTS, CAMPAIGN

ok = 0
def check(name, cond):
    global ok
    assert cond, f"❌ FAIL: {name}"
    ok += 1
    print(f"  ✅ {name}")


print("── 3단계: 적합도 산식 (단위 테스트) ──")
# ① 면적 범위 안 1.0, 미달·초과 시 비율 감점, 하한 0.2
check("area_fit 범위 안 = 1.0", area_fit(50, 30, 120) == 1.0)
check("area_fit 미달 시 비율(area/min)", abs(area_fit(15, 30, 120) - 0.5) < 1e-9)
check("area_fit 초과 시 비율(max/area)", abs(area_fit(240, 30, 120) - 0.5) < 1e-9)
check("area_fit 하한 0.2 준수", area_fit(1, 30, 120) == 0.2 and area_fit(99999, 30, 120) == 0.2)
# ② 경쟁: 동네 평균 대비 비율. 평균 이하는 감점 0, 평균 초과분에만 단조 감소
check("competition 평균 이하(0/avg2)면 감점 없음 1.0", competition_factor(0, 2, 1.0) == 1.0)
check("competition 평균과 같으면(2/avg2) 1.0", competition_factor(2, 2, 1.0) == 1.0)
c_2x = competition_factor(4, 2, 1.0)   # 평균 2배
c_3x = competition_factor(6, 2, 1.0)   # 평균 3배
check("competition 평균 2배에서 0.5(반토막)", abs(c_2x - 0.5) < 1e-9)
check("competition 초과분 클수록 단조 감소(2배>3배)", c_2x > c_3x)
check("competition 동네평균 0이면 감점 없음", competition_factor(5, 0, 1.0) == 1.0)
# ③ 인근 가중이 직접 투표보다 작게 반영 (w1<1)
check("w1 0.4 < 1 (인근 < 직접)", DEFAULT_WEIGHTS["w1"] < 1.0)
check("w2 확정값 1.0 (평균 2배에서 반토막)", DEFAULT_WEIGHTS["w2"] == 1.0)
# ④ 투표 0이면 점수 0
empty_score = score(VACANCIES[0], INDUSTRIES[0], VACANCIES, {}, {})["score"]
check("투표 0건이면 점수 0", empty_score == 0.0)
# ⑤ 손계산 1건 일치 — V-A × 카페 (새 경쟁식)
#   직접=33, 인근(B30+C24+D28=82)*0.4=32.8 → demand=65.8
#   area_fit(40 in 30~120)=1.0
#   카페 경쟁: 모든 공실 12곳 → 동네평균 12, ratio=1.0(평균과 같음) → 계수 1.0
#   score = 65.8 * 1.0 * 1.0 = 65.8
s = score(VACANCIES[0], INDUSTRIES[0], VACANCIES, VOTE_COUNTS, {})
hand = round((33 + 0.4 * (30 + 24 + 28)) * 1.0 * 1.0, 4)
check(f"손계산 일치 (V-A×카페 = {hand})", s["score"] == hand)
check("분해에 동네평균·비율 노출(포화 플래그용)",
      "neighborhood_avg" in s["breakdown"] and "competition_ratio" in s["breakdown"])
check("score 분해(breakdown) 동봉", set(s["breakdown"]) >= {"direct_votes", "nearby_weighted", "area_fit", "competition_factor"})


print("── 4단계: 겹침 해소 배치 ──")
res = allocate(VACANCIES, INDUSTRIES, VOTE_COUNTS)
assigned = [a["industry_id"] for a in res["allocations"]]
check("모든 공실 배정됨", len(res["allocations"]) == len(VACANCIES))
check("업종 겹침 없음(배정 업종 유일)", len(assigned) == len(set(assigned)))
check("응답에 사용 가중치 포함", "w1" in res["weights"] and "w2" in res["weights"])
check("응답에 알고리즘 표기", bool(res["algorithm"]))
check("각 배치에 breakdown 포함", all("breakdown" in a for a in res["allocations"]))
check("각 배치에 차순위(runners_up) 포함", all(len(a["runners_up"]) >= 1 for a in res["allocations"]))

# 극단 케이스: 모든 공실 1위가 동일 업종이어도 겹침 없이 배치
extreme_votes = {(v["id"], "cafe"): 50 for v in VACANCIES}
ext = allocate(VACANCIES, INDUSTRIES, extreme_votes)
ext_assigned = [a["industry_id"] for a in ext["allocations"]]
check("극단(전부 카페 1위)에서도 겹침 없음", len(ext_assigned) == len(set(ext_assigned)))
check("극단 케이스: 카페는 한 공실만", ext_assigned.count("cafe") == 1)

# 전수 탐색 총점 ≥ 그리디 총점 (최적성)
vac_ids = [v["id"] for v in VACANCIES]
ind_ids = [i["id"] for i in INDUSTRIES]
matrix, _ = _score_matrix(VACANCIES, INDUSTRIES, VOTE_COUNTS, DEFAULT_WEIGHTS)
_, exh_total = _assign_exhaustive(vac_ids, ind_ids, matrix)
_, grd_total = _assign_greedy(vac_ids, ind_ids, matrix)
check(f"전수탐색 총점 ≥ 그리디 (exh {round(exh_total,2)} ≥ grd {round(grd_total,2)})", exh_total >= grd_total - 1e-9)


print("── 5단계: 창업 리포트 (5요소) ──")
rep = build_report("V-A", VACANCIES, INDUSTRIES, VOTE_COUNTS, campaign=CAMPAIGN)
required = ["conclusion", "waiting_customers", "reasoning", "competition", "reference"]
check("필수 5요소 전부 존재", all(k in rep for k in required))
# 교차 일치: 대기 고객 수 = 해당 공실·추천 업종 직접 투표수
top_ind = None
for a in res["allocations"]:
    pass
rec_ind_name = rep["conclusion"]["recommended_industry"]
rec_id = next(i["id"] for i in INDUSTRIES if i["name"] == rec_ind_name)
check("대기 고객 수 = 추천 업종 직접 투표수(교차 일치)",
      rep["waiting_customers"]["count"] == VOTE_COUNTS.get(("V-A", rec_id), 0))
check("종합 적합도 % 존재(0~100)", 0 <= rep["conclusion"]["adequacy_pct"] <= 100)
check("배치 근거 3요소(수요/면적적합/경쟁보정 — engine 곱셈식 분해)",
      set(rep["reasoning"]["factors"]) == {"수요", "면적 적합", "경쟁 보정"})
check("주변 경쟁에 비교 기준선(동네 평균) 존재", "neighborhood_avg" in rep["competition"])
check("비용은 참고값 단서 포함", "참고값" in rep["reference"]["cost_caveat"])
check("값에 출처 태그 존재", rep["reference"]["startup_cost_manwon"]["source"] == "업종평균")
check("책임 범위 선긋기 문구 존재", "보장하지 않습니다" in rep["reasoning"]["disclaimer"])
check("없는 공실이면 None(404)", build_report("V-없음", VACANCIES, INDUSTRIES, VOTE_COUNTS) is None)


print(f"\n총 {ok}개 검증 전부 통과 ✅")
