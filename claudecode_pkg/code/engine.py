"""
명당 배치 엔진 (담당 B · v3 — 동네 투표 전환 반영)

순수 함수. DB 미접근. 인자로 받은 것만 계산 → A 데이터계층과 독립, 더미로 테스트.

v3 산식(08번 §2 · floor_fit 지시):
    score = demand × area_fit × competition_factor × floor_fit
      demand             = Σ (그 업종에 투표한 격자의 표수 × 거리감쇠(공실↔격자중심))
        거리감쇠 w(d): d≤500 → 1.0 / 500<d≤800 → 1−(d−500)/300 / d>800 → 0
      area_fit           = 면적 범위 안 1.0, 벗어나면 비율 감점(하한 0.2)
      competition_factor = 동네 평균 대비 비율식(w2=1.0). 경쟁은 vacancy.competitors[업종명]
      floor_fit          = 층수 계수(1층 1.0/2층이상 0.7/지하 0.5, 미상 1.0)

집계 계약(A): grid_votes = {(industry_id, voter_grid): 표수}  (그 region 으로 필터된 것).
  voter_grid 는 "lat,lng" 격자 스냅 문자열 → 파싱해 공실과의 거리를 잰다.

배치(4단계 자산 유지): 같은 업종을 두 공실에 배정 안 하는 배정 문제.
  scipy 헝가리안 → 없으면 전수탐색(최적) → 그리디 자동 폴백.
"""
from __future__ import annotations
from itertools import permutations
from math import radians, sin, cos, asin, sqrt

import config

# ── 파라미터 (config 에서, 설계 초기값) ───────────────────────────────────
DEFAULT_WEIGHTS = {
    "w2": 1.0,                 # 경쟁 감점 강도. 동네 평균 2배에서 계수 0.5
    "area_fit_floor": 0.2,     # 면적 부적합 하한
    "decay_full_m": config.DECAY_FULL_M,   # 이 거리까지 가중 1.0
    "decay_zero_m": config.DECAY_ZERO_M,   # 이 거리부터 가중 0
}
_EXHAUSTIVE_LIMIT = 200_000    # 전수 탐색 상한(순열 수)


def _haversine_m(lat1, lng1, lat2, lng2) -> float:
    r = 6_371_000.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lng2 - lng1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _parse_grid(cell: str) -> tuple:
    """voter_grid "lat,lng" → (lat, lng) 격자 대표 좌표."""
    lat, lng = cell.split(",")
    return float(lat), float(lng)


# ── 3단계: 산식 구성요소 ──────────────────────────────────────────────────
def distance_weight(d: float, full: float = 500, zero: float = 800) -> float:
    """거리 감쇠 가중. ≤full → 1.0 / full~zero 선형 / ≥zero → 0."""
    if d <= full:
        return 1.0
    if d >= zero:
        return 0.0
    return 1.0 - (d - full) / (zero - full)


def area_fit(area_m2, min_area, max_area, floor=0.2) -> float:
    """면적 범위 안 1.0, 벗어나면 비율 감점(하한 floor)."""
    if area_m2 <= 0:
        return floor
    if min_area <= area_m2 <= max_area:
        return 1.0
    ratio = area_m2 / min_area if area_m2 < min_area else max_area / area_m2
    return max(floor, ratio)


def competition_factor(competitor_count, neighborhood_avg, w2) -> float:
    """경쟁 감점 — 동네 평균 대비 비율. 평균 이하 무감점, 초과분만 감점.
    ratio = count/avg. ratio≤1 → 1.0 / ratio>1 → 1/(1+w2×(ratio−1)). avg=0 → 1.0."""
    if neighborhood_avg <= 0:
        return 1.0
    ratio = max(0, competitor_count) / neighborhood_avg
    return 1.0 / (1.0 + w2 * max(0.0, ratio - 1.0))


def floor_fit(floor) -> float:
    """층수 계수. A의 카테고리('1층'/'2층이상'/'지하'). 미상/미등록 → 1.0(감점 없음)."""
    if not floor:
        return 1.0
    return config.FLOOR_FIT.get(floor, 1.0)


def demand(vacancy, industry_id, grid_votes, weights) -> tuple:
    """(demand, 반경내 표수 원시합, 500m 이내 표수) — 거리감쇠 수요.

    grid_votes = {(industry_id, voter_grid): 표수}. 이 공실 좌표에서 각 격자중심까지 거리로 감쇠.
    """
    full, zero = weights["decay_full_m"], weights["decay_zero_m"]
    dmd = raw = within = 0.0
    for (iid, cell), n in grid_votes.items():
        if iid != industry_id:
            continue
        glat, glng = _parse_grid(cell)
        d = _haversine_m(vacancy["lat"], vacancy["lng"], glat, glng)
        dw = distance_weight(d, full, zero)
        if dw > 0:
            dmd += n * dw
            raw += n
            if d <= full:
                within += n
    return dmd, raw, within


def neighborhood_avg_competitors(industry_name, vacancies) -> float:
    """그 업종의 동네 평균 경쟁점 수. competitors 는 {업종명: 수}(A ingest 형태)."""
    counts = [(v.get("competitors") or {}).get(industry_name, 0) for v in vacancies]
    return round(sum(counts) / len(counts), 2) if counts else 0.0


def score(vacancy, industry, vacancies, grid_votes, weights=None) -> dict:
    """한 (공실, 업종) 쌍의 적합도 + 분해(breakdown). 심사 방어용으로 분해 항상 동봉."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    iid = industry["id"]
    iname = industry["name"]
    dmd, raw, within = demand(vacancy, iid, grid_votes, w)
    af = area_fit(vacancy["area_m2"], industry["min_area_m2"], industry["max_area_m2"],
                  w["area_fit_floor"])
    comp_count = (vacancy.get("competitors") or {}).get(iname, 0)
    avg = neighborhood_avg_competitors(iname, vacancies)
    cf = competition_factor(comp_count, avg, w["w2"])
    ratio = round(comp_count / avg, 2) if avg > 0 else 0.0
    ff = floor_fit(vacancy.get("floor"))
    return {
        "score": round(dmd * af * cf * ff, 4),
        "breakdown": {
            "demand": round(dmd, 3),
            "raw_voters": round(raw, 3),
            "within_500m": round(within, 3),
            "area_fit": round(af, 3),
            "competitor_count": comp_count,
            "neighborhood_avg": avg,
            "competition_ratio": ratio,        # 리포트 포화 플래그가 이 값을 씀
            "competition_factor": round(cf, 3),
            "floor": vacancy.get("floor"),
            "floor_fit": ff,
        },
    }


def _score_matrix(vacancies, industries, grid_votes, weights):
    matrix, detail = {}, {}
    for v in vacancies:
        for ind in industries:
            s = score(v, ind, vacancies, grid_votes, weights)
            matrix[(v["id"], ind["id"])] = s["score"]
            detail[(v["id"], ind["id"])] = s["breakdown"]
    return matrix, detail


# ── 4단계: 겹침 해소 배치 (자산 유지) ─────────────────────────────────────
def _perm_count(n_vac, n_ind):
    n, r, out = n_ind, n_vac, 1
    for k in range(r):
        out *= (n - k)
        if out > _EXHAUSTIVE_LIMIT:
            return out
    return out


def _assign_exhaustive(vac_ids, ind_ids, matrix):
    best, best_total = None, float("-inf")
    for combo in permutations(ind_ids, len(vac_ids)):
        total = sum(matrix[(v, i)] for v, i in zip(vac_ids, combo))
        if total > best_total:
            best_total, best = total, combo
    return dict(zip(vac_ids, best)), best_total


def _assign_greedy(vac_ids, ind_ids, matrix):
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
    from scipy.optimize import linear_sum_assignment
    import numpy as np
    cost = np.array([[-matrix[(v, i)] for i in ind_ids] for v in vac_ids])
    rows, cols = linear_sum_assignment(cost)
    res = {vac_ids[r]: ind_ids[c] for r, c in zip(rows, cols)}
    return res, sum(matrix[(v, i)] for v, i in res.items())


def allocate(vacancies, industries, grid_votes, weights=None, algo="auto") -> dict:
    """공실별로 업종을 겹침 없이 배정(지도 전체 배치). 반환에 분해·차순위·가중치·알고리즘 동봉."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    vac_ids = [v["id"] for v in vacancies]
    ind_ids = [i["id"] for i in industries]
    ind_by_id = {i["id"]: i for i in industries}
    vac_by_id = {v["id"]: v for v in vacancies}
    matrix, detail = _score_matrix(vacancies, industries, grid_votes, w)

    if len(ind_ids) < len(vac_ids):
        assign, total = _assign_greedy(vac_ids, ind_ids, matrix)
        used_algo = "greedy(업종<공실)"
    else:
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
        ranked = sorted(ind_ids, key=lambda i: matrix[(vid, i)], reverse=True)
        runners = [{"industry_id": i, "name": ind_by_id[i]["name"], "score": matrix[(vid, i)]}
                   for i in ranked if i != iid][:2]
        allocations.append({
            "vacancy_id": vid,
            "vacancy_name": vac_by_id[vid]["name"],
            "industry_id": iid,
            "industry_name": ind_by_id[iid]["name"],
            "score": matrix[(vid, iid)],
            "breakdown": detail[(vid, iid)],
            "runners_up": runners,
        })
    return {"weights": w, "algorithm": used_algo,
            "total_score": round(total, 4), "allocations": allocations}
