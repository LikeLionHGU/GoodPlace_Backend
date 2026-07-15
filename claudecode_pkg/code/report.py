"""
명당 창업 리포트 생성기 (담당 B · I2 — 동네 투표 전환 v3)

기준 문서: 08_리포트_공실등록_확정명세 §3(업종→공실 구조) · 07_창업리포트_스펙(5요소·정보과잉 배제)
LLM 미사용 — 서버가 결정적으로 채운다(챗봇 없음 = 환각 통제). AI 해설은 ai_explain.py(I3)가 별도로 얹는다.

v3 전환의 핵심: 주어가 뒤집혔다.
  (v1) "이 공실에 어느 업종?" → (v3) "이 업종에 어느 공실?"
주민은 이제 공실이 아니라 '동네+업종'에 투표하므로, 창업자는 업종을 먼저 고르고
그 업종에 대한 추천 공실 1·2·3위를 본다. 단일 업종만 다루므로 공실 간 겹침 문제가 없다
→ allocate()(지도 전체 배치용)를 쓰지 않고, 그 업종에 대해서만 공실별 score를 계산해 정렬한다.

계약 시그니처: build_report(industry_id, region_code, vacancies, industries, grid_votes_all,
                           weights=None, campaign=None) -> dict | None
  - grid_votes_all = database.get_vote_grid_counts() 그대로: {(region_code, industry_id, voter_grid): 표수}
    (A 원본 계약 형태를 그대로 받아 이 함수 안에서 region 필터 + engine 형태로 재구성한다.
     엔진(engine.py)은 순수 함수 원칙을 유지 — DB 접근은 여전히 라우터가 하고, 여기 report.py도
     인자로 받은 것만 계산한다.)
  - 없는 industry_id 또는 그 동네에 공실이 없으면 None (라우터가 404 처리).
  - 같은 (공실, 업종) 쌍이면 engine.allocate()의 내부 점수 행렬과 항상 같은 값이 나온다
    (둘 다 동일한 engine.score()를 동일 입력으로 호출하기 때문 — 재계산 다른 공식 금지).

────────────────────────────────────────────────────────────────────────────
표시 적합도 % (v1에서 확정된 것을 유지)
    pct = 100 × s / (s + SATURATION_K)      (s = engine.score() 의 곱셈 점수)
- % 는 엔진 점수 s 의 '단조 변환'이다. 요소(수요·면적·경쟁·층수)를 다시 조합하지 않는다.
- 100% 는 구조적으로 나오지 않는다(버그 아님·의도). "AI는 성공을 보장하지 않습니다"와 정합.
- v3 변경점: engine v3 의 score 는 floor_fit 을 이미 곱셈에 포함한다
  (score = demand × area_fit × competition_factor × floor_fit). 그래서 v1 문서의
  "층수는 %에 안 넣는다"는 더는 사실이 아니다 — 적합도 %에 층수 효과가 이미 반영돼 있다.
  floor_basis 는 그 반영된 값을 "왜"로 보여주는 참고 정보다(별도 가산이 아니라 이미 곱된 근거 설명).
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations
import json

from engine import score, DEFAULT_WEIGHTS

DISCLAIMER = ("AI는 성공을 보장하지 않습니다. 검증된 수요와 개업일 첫 손님까지가 명당의 책임이며, "
              "이후 운영과 품질은 창업자의 몫입니다.")

FOOT_TRAFFIC_ABSENCE = "유동인구는 공개 데이터가 없어 제공하지 않습니다."
FOOT_TRAFFIC_INSTEAD = ("대신 명당은 추정 지표가 아니라, 이미 1,000원을 선결제해 지갑을 연 "
                        "대기 고객 수를 그대로 제공합니다.")

NOT_ANSWERED_CHECKLIST = ["권리금", "실제 임대조건(협상 결과)", "현장 관찰(채광·유동 동선 등)", "상세·정밀 설비"]


# ── 포화 K (표시 % 의 기준값) ────────────────────────────────────────────────
# ★ 자의적 상수 금지. K = '기준 케이스'를 engine v3 score() 에 실제로 통과시켜 나온 점수.
#   기준 케이스: 이웃 없는 단독 공실 + 목표 투표수 전부가 거리 0(감쇠 1.0)에 있음
#   + 면적 적합(area_fit=1.0) + 경쟁 없음(competition_factor=1.0) + 층수 미상(floor_fit=1.0).
#   → s = 목표수 × 1.0 × 1.0 × 1.0 = 목표수. (아래에서 engine 으로 검산해 K 확정, 하드코딩 아님)
#
# ★ 미확정 — 팀 결정 대기(08번 §5·§6): K 를 '캠페인별'로 둘지 '전역 고정'할지.
#   지금은 전역 고정을 '잠정' 채택한다(확정 아님). 실데이터 확보 시 아래 절차로 재산출.
# ★ 실데이터 캘리브레이션 절차(양덕동 실데이터 확보 후):
#   1) 실제 '목표 투표수'를 BASELINE_TARGET_VOTES 로 교체.
#   2) 기준 케이스를 engine.score 에 통과시켜 K 를 재산출(코드가 자동으로 함).
#   3) 상위 공실들의 pct 분포가 의도한 눈금에 오는지 확인 후 팀 결정으로 확정.
BASELINE_TARGET_VOTES = 30      # 잠정 — 캠페인 목표 투표수(미확정). 실데이터로 교체 대상.


def _saturation_k(weights=None) -> float:
    """기준 케이스를 engine v3 score() 에 실제로 통과시켜 K 를 산출(하드코딩 아님)."""
    base_vac = {"id": "__baseline__", "name": "기준자리", "lat": 0.0, "lng": 0.0,
                "area_m2": 50, "floor": None, "competitors": {}}
    base_ind = {"id": "__ind__", "name": "기준업종", "min_area_m2": 10, "max_area_m2": 100}
    # 격자를 공실과 정확히 같은 좌표에 둬서 거리 0(감쇠 1.0) → demand = 목표수 그대로.
    base_grid_votes = {(base_ind["id"], "0.000,0.000"): BASELINE_TARGET_VOTES}
    s = score(base_vac, base_ind, [base_vac], base_grid_votes, weights)
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


# ── 포화 플래그 ───────────────────────────────────────────────────────────
def _saturation_flag(competition_ratio: float) -> str:
    """동네 평균 대비 배수(engine breakdown 의 competition_ratio)로 상태.
    경계값: ratio <= 1 → 기회 / 1 < ratio < 2 → 주의 / ratio >= 2 → 포화.
    veto 하지 않는다(포화여도 추천에서 빼지 않음). 보여주되 경고.
    """
    if competition_ratio >= 2:
        return "포화"
    if competition_ratio > 1:
        return "주의"
    return "기회"


def _tag(value, tag):
    """값에 출처 태그를 붙인다. tag ∈ {실측, API, 예시, 업종평균, 파생, 중개사등록, 확인 필요}."""
    return {"value": value, "source": tag}


def _region_grid_votes(industry_id, region_code, grid_votes_all) -> dict:
    """A 계약 형태 {(region_code, industry_id, voter_grid): 표수} → engine 입력 {(industry_id, voter_grid): 표수}.
    이 동네(region_code) 것만 남긴다(엔진에 다른 동네 표가 섞여 들어가지 않도록 — 08번 §6 주의사항).
    """
    return {
        (iid, grid): n
        for (rc, iid, grid), n in grid_votes_all.items()
        if rc == region_code
    }


def build_report(industry_id, region_code, vacancies, industries, grid_votes_all,
                 weights=None, campaign=None) -> dict | None:
    """
    업종 클릭 → 그 업종에 대한 추천 공실 1·2·3위 (08번 §3 "업종→공실" 구조).
    순위는 그 업종에 대한 공실별 score 내림차순(단일 업종이라 겹침 없음 — allocate 불필요).
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}

    industry = next((i for i in industries if i["id"] == industry_id), None)
    if industry is None:
        return None  # 라우터에서 404

    region_vacancies = [v for v in vacancies if v.get("region_code") == region_code]
    if not region_vacancies:
        return None  # 라우터에서 404 (그 동네에 등록된 공실이 없음)

    grid_votes = _region_grid_votes(industry_id, region_code, grid_votes_all)

    scored = []
    for vac in region_vacancies:
        s = score(vac, industry, region_vacancies, grid_votes, w)
        scored.append((vac, s["score"], s["breakdown"]))
    scored.sort(key=lambda x: x[1], reverse=True)

    # 동네 전체 수요 — 공실 무관, 이 업종에 투표한 전체 인원(원시 합, 거리감쇠 없음).
    # A의 get_region_demand() 와 같은 규칙(held/settled만)으로 계산되므로 수치가 일치해야 한다.
    region_total_demand = sum(n for (iid, _grid), n in grid_votes.items() if iid == industry_id)
    coupon_value = (campaign or {}).get("coupon_value_won", 3000)

    cards = []
    for rank, (vac, sc, bd) in enumerate(scored[:3], start=1):
        adequacy = _pct(sc)
        ratio = bd["competition_ratio"]
        flag = _saturation_flag(ratio)
        waiting = bd["raw_voters"]  # 대기 고객 = 이 공실 반경(감쇠 범위 내) 투표자 원시 수

        # 창업자가 실제로 궁금해하는 시설 여부(화장실·하수구 등) — DB엔 이미 공실마다 다른 값이
        # 시드돼 있었지만(seed.py facilities) 지금까지 API 응답에 노출되지 않아 프론트가 전부
        # 고정값으로 흉내 냈다. 여기서부터 공실별 실제 값(가능 여부 + 화장실 유형/주차 대수 같은
        # 세부 비고)을 그대로 내려준다.
        raw_facilities = vac.get("facilities")
        fac = json.loads(raw_facilities) if isinstance(raw_facilities, str) else (raw_facilities or {})
        fac_source = "중개사등록" if raw_facilities else "확인 필요"

        def _fac_field(key: str) -> dict:
            v = fac.get(key)
            if isinstance(v, dict):
                return {"value": bool(v.get("가능")), "detail": v.get("비고", ""), "source": fac_source}
            return {"value": bool(v), "detail": "", "source": fac_source}

        cards.append({
            "rank": rank,
            "vacancy": {
                "id": vac["id"], "name": vac["name"],
                "lat": vac["lat"], "lng": vac["lng"],
                "address": _tag(vac.get("address", ""), "예시" if vac.get("is_seed") else "실측"),
            },
            "adequacy_pct": adequacy,
            "engine_score": sc,
            # 행동 범위 수요 — "동네 N명 중 이 자리 반경엔 M명"(공실마다 다름 = 위치 추천의 핵심 근거)
            "action_range_demand": {
                "raw_voters": bd["raw_voters"],
                "within_500m": bd["within_500m"],
                "weighted_demand": bd["demand"],
                "reading": f"동네 {region_total_demand}명 중 이 자리 반경엔 {int(bd['raw_voters'])}명",
            },
            "competition": {
                "industry": industry["name"],
                "count": _tag(bd["competitor_count"], "API"),
                "neighborhood_avg": _tag(bd["neighborhood_avg"], "파생"),
                "competition_ratio": ratio,
                "saturation_flag": flag,
                # "평균의 0.85배" 같은 배수 표현이 무슨 뜻인지 바로 안 와닿는다는 피드백 반영 —
                # 원시 개수(비교 근거)는 남기고, 판정 이유는 배수 대신 쉬운 말로 풀어쓴다.
                "reading": (
                    f"이 근처에 {industry['name']}가 {bd['competitor_count']}곳 있어요"
                    f"(동네 평균 {bd['neighborhood_avg']}곳). "
                    + (
                        "동네 평균보다 적어서 경쟁 부담이 적어요."
                        if flag == "기회"
                        else "동네 평균보다 조금 많아서 경쟁이 있는 편이에요."
                        if flag == "주의"
                        else "동네 평균보다 훨씬 많아서 경쟁이 심한 편이에요."
                    )
                ),
            },
            "area_fit": {
                "area_m2": _tag(vac.get("area_m2"), "실측" if not vac.get("is_seed") else "예시"),
                "industry_range_m2": [industry["min_area_m2"], industry["max_area_m2"]],
                "score01": bd["area_fit"],
            },
            # floor 근거 — floor_fit은 이미 adequacy_pct(score) 곱셈에 반영됨. 여기선 "왜"만 설명.
            "floor_basis": {
                "floor": _tag(vac.get("floor"), "중개사등록" if vac.get("floor") else "확인 필요"),
                "floor_fit": bd["floor_fit"],
                "reading": (f"층수 계수 {bd['floor_fit']}배가 적합도에 이미 반영됨"
                            if vac.get("floor") else "층 정보 미등록 — 확인 필요(계수 1.0 처리)"),
            },
            "waiting_customers": {
                "count": waiting,
                "label": "개업일 첫 손님 후보 · 이미 지갑을 연 대기 고객",
                "coupon_value_won": coupon_value,
                "coupon_total_won": round(waiting * coupon_value),
                "source": "API",
            },
            "facilities": {
                "toilet": _fac_field("화장실"),
                "water_drain": _fac_field("상하수도"),
                "gas": _fac_field("가스"),
                "vent_hood": _fac_field("환기후드"),
                "parking": _fac_field("주차"),
            },
        })

    return {
        "region_code": region_code,
        "industry": {"id": industry["id"], "name": industry["name"]},
        "headline": f"{region_code} {industry['name']}, 추천 공실 {len(cards)}곳",
        # 동네 전체 수요 (업종 단위·공실 무관) — 08번 §3 상단 항목
        "region_total_demand": {
            "count": region_total_demand,
            "label": f"{region_code}에서 {industry['name']}를 원한 주민 수",
            "source": "API",
        },
        "vacancies": cards,
        # ── 하단 공통 (공실 무관) ──
        "reference": {
            "startup_cost_manwon": _tag(industry.get("avg_startup_cost_manwon"), "업종평균"),
            "cost_caveat": ("초기비용은 소상공인시장진흥공단 업종 평균 기준입니다. "
                            "실제 비용은 점포 상태·권리금·인테리어 수준에 따라 크게 달라지므로 참고값으로만 보세요."),
            "licenses": _tag(industry.get("licenses", "확인 필요"), "업종평균"),
        },
        "not_answered": NOT_ANSWERED_CHECKLIST,
        "foot_traffic": {
            "available": False,
            "note": FOOT_TRAFFIC_ABSENCE,
            "instead": FOOT_TRAFFIC_INSTEAD,
        },
        "disclaimer": DISCLAIMER,
        "cta": "이 자리 중개사에게 연결하기 (계약은 지역 공인중개사가 진행 · 명당은 검증된 수요와 첫 손님을 전달)",
        "tags_legend": {"실측": "팀 현장/로드뷰 확인", "API": "소상공인 상가정보 API 확인값",
                        "예시": "시연용 예시값(공개 데이터 없음)", "업종평균": "공단 통계 평균",
                        "파생": "수집값으로 산출한 파생 지표", "중개사등록": "중개사 입력값",
                        "확인 필요": "데이터 미등록 — 직접 확인 필요"},
    }
