"""
3·4단계 통합 — 어댑터(DB row → 엔진 입력). 얇은 연결층.

원칙: 엔진(engine.py)은 순수 함수·확정본이다. 엔진이 불편해도 엔진을 고치지 않고 여기서 맞춘다.
- vacancies.competitors 는 DB에 **JSON 문자열**로 저장돼 있다 → 반드시 dict 로 파싱.
  (문자열째 넘기면 경쟁계수가 에러 없이 틀어진다. 그래서 파싱을 이 한 곳으로 강제한다.)
- 투표는 2단계 집계 (vacancy_id, industry_id)→투표수 를 그대로 쓴다(계약 형태 불변).
  refunded 제외는 db.get_vote_counts(=vote_counts_view: held/settled) 에서 이미 걸린다.
"""
import json


def _parse_competitors(raw) -> dict:
    """competitors 원본(JSON 문자열/dict/None) → dict. 숫자만 남긴다."""
    if raw is None or raw == "":
        return {}
    obj = raw if isinstance(raw, dict) else json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError(f"competitors 가 dict/JSON객체가 아님: {raw!r}")
    return obj


def vacancy_from_row(row) -> dict:
    """DB vacancies row(sqlite3.Row/dict) → 엔진 입력 dict."""
    r = dict(row)
    return {
        "id": r["id"],
        "name": r["name"],
        "lat": r["lat"],
        "lng": r["lng"],
        "area_m2": r["area_m2"],
        "floor": r.get("floor"),
        "competitors": _parse_competitors(r.get("competitors")),   # ★ JSON 문자열 → dict
        "address": r.get("address"),
        "prev_industry": r.get("prev_industry"),
        "vacant_since": r.get("vacant_since"),
        "is_seed": r.get("is_seed"),
    }


def industry_from_row(row) -> dict:
    """DB industries row → 엔진 입력 dict."""
    r = dict(row)
    return {
        "id": r["id"],
        "name": r["name"],
        "min_area_m2": r["min_area_m2"],
        "max_area_m2": r["max_area_m2"],
        "avg_startup_cost_manwon": r.get("avg_startup_cost_manwon"),
        "licenses": r.get("licenses"),
        "is_seed": r.get("is_seed"),
    }


def load_allocation_inputs(conn, region_code):
    """해당 region_code 의 (vacancies, industries, vote_counts) 를 엔진 입력 형태로 모아 반환.

    - vacancies: region_code 로 필터(지역 하드코딩 없음, 인자만 사용).
    - industries: 업종 기준표는 전역(지역 무관).
    - vote_counts: db.get_vote_counts(region_code) — refunded 제외 유지.
    """
    import db

    vac_rows = conn.execute(
        "SELECT * FROM vacancies WHERE region_code = ? ORDER BY id", (region_code,)
    ).fetchall()
    ind_rows = conn.execute("SELECT * FROM industries ORDER BY id").fetchall()
    vacancies = [vacancy_from_row(r) for r in vac_rows]
    industries = [industry_from_row(r) for r in ind_rows]
    vote_counts = db.get_vote_counts(conn, region_code)
    return vacancies, industries, vote_counts
