"""
명당 창업 리포트 생성기 (담당 B · 5단계)

기준 문서: 07_창업리포트_스펙 (필수 5요소·순서 고정·정보과잉 배제·비용 참고값·출처 태그)
시안: 명당_창업리포트_예시.html
LLM 미사용 — 서버가 결정적으로 채운다(챗봇 없음 = 환각 통제).

계약 시그니처: build_report(vacancy_id, vacancies, industries, vote_counts) -> 5칸 리포트
없는 공실이면 None (라우터가 404 처리).

────────────────────────────────────────────────────────────────────────────
표시 적합도 % (5단계에서 확정 — 이전의 '4요소 가중합'을 폐기하고 통일)
    pct = 100 × s / (s + SATURATION_K)      (s = engine.allocate/score 의 곱셈 점수)
- % 는 엔진 점수 s 의 '단조 변환'이다. 요소(수요·면적·경쟁)를 다시 조합하지 않는다.
  요소를 재조합하면 곱셈(엔진)과 다른 계산이 되어 순위 역전이 생기기 때문(폐기 이유).
- 100% 는 구조적으로 나오지 않는다(버그 아님·의도). "AI는 성공을 보장하지 않습니다"와 정합.
- 입지(층수)는 % 에 넣지 않는다: 엔진 산식에 입지 항이 없으므로 통일의 자연스러운 결과.
  층수는 참고 정보로만 표시(E). 층수 계수의 '자리'는 docs 에 미확정으로 남김.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations
from engine import score, allocate, DEFAULT_WEIGHTS

DISCLAIMER = ("AI는 성공을 보장하지 않습니다. 검증된 수요와 개업일 첫 손님까지가 명당의 책임이며, "
              "이후 운영과 품질은 창업자의 몫입니다.")

FOOT_TRAFFIC_ABSENCE = "유동인구는 공개 데이터가 없어 제공하지 않습니다."
FOOT_TRAFFIC_INSTEAD = ("대신 명당은 추정 지표가 아니라, 이미 1,000원을 선결제해 지갑을 연 "
                        "대기 고객 수를 그대로 제공합니다.")


# ── 포화 K (표시 % 의 기준값) ────────────────────────────────────────────────
# ★ 자의적 상수 금지. K = '기준 케이스'를 engine 산식에 실제로 통과시켜 나온 점수.
#   기준 케이스: 캠페인 목표 투표수 달성 + 면적 적합 1.0 + 경쟁이 동네 평균 수준(계수 1.0).
#   함정: demand = 직접표 + 0.4×인근표 이므로 "목표수 × 계수"로 K 를 잡으면 % 가 과대해진다.
#         → 이웃 없는 기준 자리를 만들어 engine.score 로 실제 점수를 뽑는다.
#   계산: 이웃 0 → demand = 목표수. area 범위 안 → area_fit=1.0.
#         경쟁점=동네평균(자기 혼자라 avg=자기값) → ratio=1.0 → competition_factor=1.0.
#         따라서 s = 목표수 × 1.0 × 1.0 = 목표수. (아래에서 engine 으로 검산해 K 확정)
#
# ★ 미확정 — 팀 결정 대기: K 를 '캠페인별'로 둘지 '전역 고정'할지.
#   캠페인별로 두면 지역 간 % 비교가 무의미해진다(같은 60%가 다른 수요를 뜻함).
#   지금은 전역 고정을 '잠정' 채택한다(확정 아님). 실데이터 확보 시 아래 절차로 재산출.
#
# ★ 실데이터 캘리브레이션 절차(양덕동 실데이터 확보 후):
#   1) 양덕동 캠페인의 실제 '목표 투표수'(성공 임계치)를 BASELINE_TARGET_VOTES 로 넣는다.
#   2) 기준 케이스를 engine.score 에 통과시켜 K 를 재산출(코드가 자동으로 함).
#   3) 상위 공실들의 pct 분포가 의도한 눈금(목표 달성=50%대)에 오는지 확인, 필요 시 목표수 조정.
#   4) 캠페인별 K 로 갈지 전역 K 로 갈지 팀 결정 후 확정.
BASELINE_TARGET_VOTES = 30      # 잠정 — 캠페인 목표 투표수(미확정). 실데이터로 교체 대상.


def _saturation_k(weights=None) -> float:
    """기준 케이스를 engine.score 에 실제로 통과시켜 K 를 산출(하드코딩 아님)."""
    base_vac = {"id": "__baseline__", "name": "기준자리", "lat": 0.0, "lng": 0.0,
                "area_m2": 50, "competitors": {"__ind__": 1}}
    base_ind = {"id": "__ind__", "name": "기준업종", "min_area_m2": 10, "max_area_m2": 100}
    base_votes = {("__baseline__", "__ind__"): BASELINE_TARGET_VOTES}
    # 이웃 없음(단일 공실) → demand=목표수, area_fit=1.0, competition_factor=1.0
    s = score(base_vac, base_ind, [base_vac], base_votes, weights)
    return s["score"]


SATURATION_K = _saturation_k()   # 기준 케이스 = 목표 30표 → K = 30.0 (engine 검산값)


def _pct(engine_score: float) -> int:
    """엔진 점수 s → 표시 적합도 %(0~100 미만). 단조 증가, 100 미도달.

    내림(floor)을 쓴다: 참값 100×s/(s+K) 는 항상 <100 이지만 반올림은 극단값에서 100 이
    될 수 있다. 내림이면 어떤 s 에서도 ≤99 가 보장돼 "구조적으로 100 미도달"과 정합.
    """
    denom = engine_score + SATURATION_K
    if denom <= 0:
        return 0
    return int(100 * engine_score / denom)


# ── 포화 플래그 (F) ─────────────────────────────────────────────────────────
def _saturation_flag(competition_ratio: float) -> str:
    """동네 평균 대비 배수(engine breakdown 의 competition_ratio)로 상태.
    경계값 확정: ratio == 1.0 → 기회, ratio == 2.0 → 포화.
        ratio <= 1      → 기회
        1 <  ratio < 2  → 주의
        ratio >= 2      → 포화
    veto 하지 않는다(포화여도 추천에서 빼지 않음). 보여주되 경고.
    """
    if competition_ratio >= 2:
        return "포화"
    if competition_ratio > 1:
        return "주의"
    return "기회"


def _tag(value, tag):
    """값에 출처 태그를 붙인다. tag ∈ {실측, API, 예시, 업종평균, 파생}."""
    return {"value": value, "source": tag}


def _rank_industries(vacancy, industries, vacancies, vote_counts, weights):
    """미배정 공실 폴백용 로컬 랭킹(배정된 공실은 allocate 결과를 그대로 쓴다)."""
    scored = []
    for ind in industries:
        s = score(vacancy, ind, vacancies, vote_counts, weights)
        scored.append((ind, s["score"], s["breakdown"]))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def build_report(vacancy_id, vacancies, industries, vote_counts,
                 weights=None, campaign=None, allocation=None) -> dict | None:
    """
    리포트의 '1순위 추천' = 배치(allocate) 결과의 배정 업종. 지도 핀과 리포트를 일치시킨다.
    (리포트가 공실별로 점수를 다시 매기면 엔진이 없앤 겹침이 되살아나므로, 배치 결과를 기준으로 삼는다.)
    배치 근거 값은 engine breakdown 에서 그대로 가져오고, 리포트가 다시 계산하지 않는다.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    vacancy = next((v for v in vacancies if v["id"] == vacancy_id), None)
    if vacancy is None:
        return None  # 라우터에서 404

    if allocation is None:
        allocation = allocate(vacancies, industries, vote_counts, w)
    alloc_row = next((a for a in allocation["allocations"] if a["vacancy_id"] == vacancy_id), None)

    if alloc_row is not None:
        # 배정 업종을 1순위로. 차순위는 엔진이 준 runners_up 을 그대로(재랭킹 금지).
        top_ind = next(i for i in industries if i["id"] == alloc_row["industry_id"])
        top_bd = alloc_row["breakdown"]
        top_score = alloc_row["score"]
        runners = [{"name": r["name"], "adequacy_pct": _pct(r["score"])}
                   for r in alloc_row.get("runners_up", [])]
    else:
        # 미배정 공실(업종<공실 등)일 때만 로컬 랭킹으로 폴백.
        ranked = _rank_industries(vacancy, industries, vacancies, vote_counts, w)
        top_ind, top_score, top_bd = ranked[0]
        runners = [{"name": ind["name"], "adequacy_pct": _pct(sc)} for ind, sc, _ in ranked[1:3]]

    # ── 표시 값: 전부 engine breakdown 에서 (리포트가 다시 계산하지 않음) ──
    adequacy = _pct(top_score)
    direct_votes = top_bd["direct_votes"]
    nearby_weighted = top_bd["nearby_weighted"]
    demand = top_bd["demand"]
    area_fit_v = top_bd["area_fit"]
    comp_factor = top_bd["competition_factor"]
    comp_count = top_bd["competitor_count"]
    avg_comp = top_bd["neighborhood_avg"]
    ratio = top_bd["competition_ratio"]
    flag = _saturation_flag(ratio)

    waiting = direct_votes                              # 대기 고객 = 이 공실·추천업종 직접 투표수
    coupon_value = (campaign or {}).get("coupon_value_won", 3000)

    # ── G. 경고를 한 줄 결론 옆에(스크롤 전에 보이게) ──
    headline = f"이 공실에는 {top_ind['name']}, 적합도 {adequacy}%"
    warning = None
    if flag in ("주의", "포화"):
        warning = f"⚠ 경쟁 {flag}(동네 평균의 {ratio}배)"
        headline = f"{headline} · {warning}"

    # ── 필수 5요소 (07 스펙 순서 고정) ───────────────────────────────────
    return {
        "vacancy": {
            "id": vacancy["id"], "name": vacancy["name"],
            "address": _tag(vacancy.get("address", ""), "예시" if vacancy.get("is_seed") else "실측"),
        },
        # ① 한 줄 결론 + 종합 적합도 (경고 동반)
        "conclusion": {
            "headline": headline,
            "recommended_industry": top_ind["name"],
            "adequacy_pct": adequacy,
            "saturation_flag": flag,
            "warning": warning,          # 주의/포화일 때만 값, 기회면 None
            "one_liner": (f"주민 {waiting}명이 선결제로 원했고, "
                          f"반경 {int(w['nearby_radius_m'])}m 안에 {top_ind['name']}가 {comp_count}개입니다."),
        },
        # ② 검증된 수요 = 대기 고객 수 (리포트의 심장)
        "waiting_customers": {
            "count": waiting,
            "label": "개업일 첫 손님 · 이미 지갑을 연 수요",
            "coupon_value_won": coupon_value,
            "source": "API",   # 실제 투표 집계에서 옴 (시드면 seed 집계)
        },
        # ③ 배치 근거 (AI 판단) — engine 곱셈 3요소 분해 그대로
        "reasoning": {
            "adequacy_pct": adequacy,
            "adequacy_basis": "적합도 = 수요 × 면적적합 × 경쟁보정 점수를 0~100 지수로 변환한 값",
            "engine_score": top_score,
            "factors": {
                "수요": {"direct_votes": direct_votes,
                       "nearby_weighted": nearby_weighted, "demand": demand},
                "면적 적합": {"score01": area_fit_v},
                "경쟁 보정": {"score01": comp_factor,
                           "competition_ratio": ratio, "neighborhood_avg": avg_comp},
            },
            "runners_up": runners,
            "disclaimer": DISCLAIMER,
        },
        # ④ 주변 경쟁 (비교 기준선 필수 · engine breakdown 값)
        "competition": {
            "industry": top_ind["name"],
            "radius_m": int(w["nearby_radius_m"]),
            "count": _tag(comp_count, "API"),
            "neighborhood_avg": _tag(avg_comp, "파생"),   # 동네 평균 (비교 기준선 — 단독 숫자 금지)
            "competition_ratio": ratio,
            "saturation_flag": flag,
            "reading": (f"추천 업종({top_ind['name']}) {comp_count}곳 · 동네 평균 {avg_comp}곳"
                        f"(평균의 {ratio}배) → {flag}."),
        },
        # ⑤ 참고 비용 + 인허가 (접어두는 보조 정보 · 참고값). 층수·직전업종·공실기간은 참고 정보로만.
        "reference": {
            "vacancy_info": {
                "area_m2": _tag(vacancy.get("area_m2"), "실측" if not vacancy.get("is_seed") else "예시"),
                "floor": _tag(vacancy.get("floor"), "실측" if not vacancy.get("is_seed") else "예시"),
                "prev_industry": _tag(vacancy.get("prev_industry"), "API"),
                "vacant_since": _tag(vacancy.get("vacant_since"), "API"),
            },
            "startup_cost_manwon": _tag(top_ind.get("avg_startup_cost_manwon"), "업종평균"),
            "cost_caveat": ("초기비용은 소상공인시장진흥공단 업종 평균 기준입니다. "
                            "실제 비용은 점포 상태·권리금·인테리어 수준에 따라 크게 달라지므로 참고값으로만 보세요."),
            "licenses": _tag(top_ind.get("licenses", "확인 필요"), "업종평균"),
            "cta": "이 자리 중개사에게 연결하기 (계약은 지역 공인중개사가 진행 · 명당은 검증된 수요와 첫 손님을 전달)",
        },
        # 유동인구 — 정직하게 비우고 정면돌파(D). 추정·대체 지표 만들지 않음.
        "foot_traffic": {
            "available": False,
            "note": FOOT_TRAFFIC_ABSENCE,
            "instead": FOOT_TRAFFIC_INSTEAD,
        },
        "tags_legend": {"실측": "팀 현장/로드뷰 확인", "API": "소상공인 상가정보 API 확인값",
                        "예시": "시연용 예시값(공개 데이터 없음)", "업종평균": "공단 통계 평균",
                        "파생": "수집값으로 산출한 파생 지표"},
    }
