"""
명당 배치 엔진 (담당 B · 3·4단계)

계약(AB공통_분담과통합계약):
    allocate(vacancies, industries, vote_counts) -> 배치결과
순수 함수. DB 직접 접근 금지. 인자로 받은 것만 계산.
vote_counts 는 {(vacancy_id, industry_id): 투표수} 형태로만 받는다 (votes 원본 구조 모름).

산식(03_배치엔진과_적합도산식 · 담당_B_가이드):
    score(공실, 업종) = demand × area_fit × competition_factor
        demand             = 직접 투표수 + w1 × 같은 업종의 '인근' 공실 투표수
        area_fit           = 면적 범위 안 1.0, 벗어나면 비율 감점(하한 0.2)
        competition_factor = 1 / (1 + w2 × 주변 동일업종 경쟁점 수)
    w1·w2 는 잠정값 — 팀 결정 대기(03·05번). 아래 DEFAULT_WEIGHTS 한 곳에서만 바꾼다.

배치(4단계): 같은 업종을 두 공실에 배정하지 않는 배정(assignment) 문제.
    규모가 작으면 전수 탐색(최적 보장), 크면 그리디 폴백.
    scipy 가 있으면 헝가리안으로 자동 교체(최적·확장). 없으면 위 두 방식으로 동작.
    → "헝가리안 vs 공실 수 제한" 은 여전히 팀 결정 대기지만, 코드는 둘 다 지원해 둔다.
"""

from __future__ import annotations
from itertools import permutations
from math import radians, sin, cos, asin, sqrt

# ── 잠정 파라미터 (팀 결정 대기 — 여기서만 수정) ─────────────────────────
DEFAULT_WEIGHTS = {
    "w1": 0.4,          # 인근 공실 같은 업종 투표 가중. 직접 표=1차 신호, 인근 표=보조 신호(절반 이하)
    "w2": 1.0,          # 경쟁 감점 강도. 동네 평균의 2배에서 수요 반토막(0.5). 정상 밀도는 존중, 명백한 포화만 감점
    "nearby_radius_m": 500,   # '인근'의 정의: 이 반경 안의 다른 공실
    "area_fit_floor": 0.2,    # 면적 부적합 하한
}
# 전수 탐색 상한(순열 수). 초과 시 그리디/헝가리안으로.
_EXHAUSTIVE_LIMIT = 200_000


# ── 거리 (인근 공실 판정용) ──────────────────────────────────────────────
def _haversine_m(lat1, lng1, lat2, lng2) -> float:
    r = 6_371_000.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lng2 - lng1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


# ── 3단계: 산식 구성요소 (전부 단독 테스트 가능) ─────────────────────────
def area_fit(area_m2: float, min_area: float, max_area: float, floor: float = 0.2) -> float:
    """면적 범위 안 1.0, 벗어나면 비율 감점(하한 floor). 벗어날수록 단조감소."""
    if area_m2 <= 0:
        return floor
    if min_area <= area_m2 <= max_area:
        return 1.0
    ratio = area_m2 / min_area if area_m2 < min_area else max_area / area_m2
    return max(floor, ratio)


def competition_factor(competitor_count: int, neighborhood_avg: float, w2: float) -> float:
    """
    경쟁 감점 — 절대 수가 아니라 '동네 평균 대비 비율'로.
        ratio = competitor_count / neighborhood_avg
        평균 이하(ratio<=1) → 감점 0 (계수 1.0, 경쟁 공백/정상 밀도)
        평균 초과(ratio>1)  → 초과분에만 감점: 1 / (1 + w2 × (ratio-1))
    이유: 카페 3곳(흔함)과 세탁소 3곳(드묾)을 같게 깎으면 안 됨. 업종별 정상 밀도를 반영한다.
    w2=1.0 이면 평균의 2배에서 계수 0.5(수요 반토막). neighborhood_avg=0 이면 감점 없음.
    """
    if neighborhood_avg <= 0:
        return 1.0
    ratio = max(0, competitor_count) / neighborhood_avg
    return 1.0 / (1.0 + w2 * max(0.0, ratio - 1.0))


def demand(vacancy, industry_id, vacancies, vote_counts, w1, radius_m) -> tuple[int, float]:
    """(직접 투표수, 인근 가중분) 반환 → 합이 demand."""
    direct = vote_counts.get((vacancy["id"], industry_id), 0)
    nearby = 0
    for other in vacancies:
        if other["id"] == vacancy["id"]:
            continue
        d = _haversine_m(vacancy["lat"], vacancy["lng"], other["lat"], other["lng"])
        if d <= radius_m:
            nearby += vote_counts.get((other["id"], industry_id), 0)
    return direct, w1 * nearby


def neighborhood_avg_competitors(industry_id, vacancies) -> float:
    """그 업종의 동네 평균 경쟁점 수 (경쟁계수 기준선 + 리포트 비교 기준선 공용)."""
    counts = [(v.get("competitors") or {}).get(industry_id, 0) for v in vacancies]
    return round(sum(counts) / len(counts), 2) if counts else 0.0


def score(vacancy, industry, vacancies, vote_counts, weights=None) -> dict:
    """한 (공실, 업종) 쌍의 적합도 점수 + 분해(breakdown). 심사 방어용으로 분해를 항상 동봉."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    direct, nearby_w = demand(vacancy, industry["id"], vacancies, vote_counts,
                              w["w1"], w["nearby_radius_m"])
    dmd = direct + nearby_w
    af = area_fit(vacancy["area_m2"], industry["min_area_m2"], industry["max_area_m2"],
                  w["area_fit_floor"])
    comp_count = (vacancy.get("competitors") or {}).get(industry["id"], 0)
    avg = neighborhood_avg_competitors(industry["id"], vacancies)
    cf = competition_factor(comp_count, avg, w["w2"])
    ratio = round(comp_count / avg, 2) if avg > 0 else 0.0
    return {
        "score": round(dmd * af * cf, 4),
        "breakdown": {
            "direct_votes": direct,
            "nearby_weighted": round(nearby_w, 3),
            "demand": round(dmd, 3),
            "area_fit": round(af, 3),
            "competitor_count": comp_count,
            "neighborhood_avg": avg,
            "competition_ratio": ratio,      # 동네 평균 대비 배수 (리포트 포화 플래그가 이 값을 씀)
            "competition_factor": round(cf, 3),
        },
    }


def _score_matrix(vacancies, industries, vote_counts, weights):
    """V×I 점수 행렬 + 분해 캐시."""
    matrix, detail = {}, {}
    for v in vacancies:
        for ind in industries:
            s = score(v, ind, vacancies, vote_counts, weights)
            matrix[(v["id"], ind["id"])] = s["score"]
            detail[(v["id"], ind["id"])] = s["breakdown"]
    return matrix, detail


# ── 4단계: 겹침 해소 배치 ────────────────────────────────────────────────
def _perm_count(n_vac, n_ind):
    """P(n_ind, n_vac) 대략 — 전수 탐색 감당 여부 판정용."""
    n, r, out = n_ind, n_vac, 1
    for k in range(r):
        out *= (n - k)
        if out > _EXHAUSTIVE_LIMIT:
            return out
    return out


def _assign_exhaustive(vac_ids, ind_ids, matrix):
    """전수 탐색 — 업종 중복 없이 총점 최대(최적 보장)."""
    best, best_total = None, float("-inf")
    for combo in permutations(ind_ids, len(vac_ids)):
        total = sum(matrix[(v, i)] for v, i in zip(vac_ids, combo))
        if total > best_total:
            best_total, best = total, combo
    return dict(zip(vac_ids, best)), best_total


def _assign_greedy(vac_ids, ind_ids, matrix):
    """그리디 폴백 — (공실,업종) 점수 내림차순, 빈 공실·안 쓴 업종이면 배정. 최적 보장 X."""
    pairs = sorted(((matrix[(v, i)], v, i) for v in vac_ids for i in ind_ids),
                   key=lambda x: x[0], reverse=True)
    used_v, used_i, res = set(), set(), {}
    for _, v, i in pairs:
        if v in used_v or i in used_i:
            continue
        res[v] = i
        used_v.add(v); used_i.add(i)
    return res, sum(matrix[(v, i)] for v, i in res.items())


def _assign_hungarian(vac_ids, ind_ids, matrix):
    """헝가리안(scipy) — 있으면 사용. 최대화라 음수로 뒤집는다. 없으면 ImportError."""
    from scipy.optimize import linear_sum_assignment  # 선택 의존
    import numpy as np
    cost = np.array([[-matrix[(v, i)] for i in ind_ids] for v in vac_ids])
    rows, cols = linear_sum_assignment(cost)
    res = {vac_ids[r]: ind_ids[c] for r, c in zip(rows, cols)}
    return res, sum(matrix[(v, i)] for v, i in res.items())


def allocate(vacancies, industries, vote_counts, weights=None, algo="auto") -> dict:
    """
    공실별로 업종을 겹침 없이 배정. 계약 시그니처.
    반환: {
      "weights": 사용 가중치,
      "algorithm": 실제 사용 알고리즘,
      "total_score": 총점,
      "allocations": [ {vacancy_id, vacancy_name, industry_id, industry_name,
                        score, breakdown, runners_up:[{industry_id,name,score}...] } ... ]
    }
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    vac_ids = [v["id"] for v in vacancies]
    ind_ids = [i["id"] for i in industries]
    ind_by_id = {i["id"]: i for i in industries}
    vac_by_id = {v["id"]: v for v in vacancies}
    matrix, detail = _score_matrix(vacancies, industries, vote_counts, w)

    if len(ind_ids) < len(vac_ids):
        # 업종이 공실보다 적으면 일부 공실은 미배정 — 점수 상위 공실부터 채운다(그리디 성격).
        assign, total = _assign_greedy(vac_ids, ind_ids, matrix)
        used_algo = "greedy(업종<공실)"
    else:
        chosen = algo
        if algo == "auto":
            try:
                assign, total = _assign_hungarian(vac_ids, ind_ids, matrix)
                used_algo = "hungarian(scipy)"
            except Exception:
                if _perm_count(len(vac_ids), len(ind_ids)) <= _EXHAUSTIVE_LIMIT:
                    assign, total = _assign_exhaustive(vac_ids, ind_ids, matrix)
                    used_algo = "exhaustive(최적)"
                else:
                    assign, total = _assign_greedy(vac_ids, ind_ids, matrix)
                    used_algo = "greedy(폴백)"
        elif algo == "exhaustive":
            assign, total = _assign_exhaustive(vac_ids, ind_ids, matrix); used_algo = "exhaustive(최적)"
        elif algo == "greedy":
            assign, total = _assign_greedy(vac_ids, ind_ids, matrix); used_algo = "greedy"
        elif algo == "hungarian":
            assign, total = _assign_hungarian(vac_ids, ind_ids, matrix); used_algo = "hungarian(scipy)"
        else:
            raise ValueError(f"알 수 없는 algo: {algo}")

    allocations = []
    for v in vacancies:
        vid = v["id"]
        if vid not in assign:
            continue
        iid = assign[vid]
        # 차순위: 이 공실 기준 점수 상위(배정된 업종 제외) 2개
        ranked = sorted(ind_ids, key=lambda i: matrix[(vid, i)], reverse=True)
        runners = [{"industry_id": i, "name": ind_by_id[i]["name"],
                    "score": matrix[(vid, i)]} for i in ranked if i != iid][:2]
        allocations.append({
            "vacancy_id": vid,
            "vacancy_name": vac_by_id[vid]["name"],
            "industry_id": iid,
            "industry_name": ind_by_id[iid]["name"],
            "score": matrix[(vid, iid)],
            "breakdown": detail[(vid, iid)],
            "runners_up": runners,
        })
    return {
        "weights": w,
        "algorithm": used_algo,
        "total_score": round(total, 4),
        "allocations": allocations,
    }
