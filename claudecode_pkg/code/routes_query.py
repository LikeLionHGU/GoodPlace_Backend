"""
1단계 — 조회 API (담당 A 몫). 엔진(engine.py·report.py)은 연결하지 않는다(다음 단계).

- GET  /health            서버·DB 상태
- GET  /industries        업종 목록(면적·창업비용·인허가 포함)
- GET  /vacancies         공실 목록 + 공실별 투표 요약(1단계엔 votes 비어 있어 전부 0)
- POST /admin/seed/reset  seed_dummy 재적재(모의 데이터 초기화)

지역은 하드코딩하지 않고 region_code 쿼리 파라미터로 거른다(양덕동 첫 적용, 경북 확장).
"""
import json

from fastapi import APIRouter, HTTPException

import db

router = APIRouter()


@router.get("/health", summary="서버·DB 상태")
def health():
    try:
        conn = db.connect()
        try:
            counts = db.table_counts(conn)
        finally:
            conn.close()
    except Exception as e:  # DB 파일 손상 등
        raise HTTPException(status_code=503, detail=f"DB 접근 실패: {e}")
    return {"status": "ok", "db": "ok", "table_counts": counts}


@router.get("/industries", summary="업종 목록(면적·창업비용·인허가)")
def list_industries():
    conn = db.connect()
    try:
        rows = conn.execute("SELECT * FROM industries ORDER BY id").fetchall()
    finally:
        conn.close()
    return {"count": len(rows), "items": [dict(r) for r in rows]}


@router.get("/vacancies", summary="공실 목록(+투표 요약, region_code 필터)")
def list_vacancies(region_code: str | None = None):
    conn = db.connect()
    try:
        sql, params = "SELECT * FROM vacancies", ()
        if region_code is not None:
            sql, params = sql + " WHERE region_code = ?", (region_code,)
        rows = conn.execute(sql + " ORDER BY id", params).fetchall()
        vote_counts = db.get_vote_counts(conn, region_code)
    finally:
        conn.close()

    items = []
    for r in rows:
        v = dict(r)
        v["competitors"] = json.loads(v["competitors"])
        # 투표 요약 자리 — 1단계에서는 votes 가 비어 있어 전부 0
        by_industry = {iid: n for (vid, iid), n in vote_counts.items() if vid == v["id"]}
        v["votes_total"] = sum(by_industry.values())
        v["votes_by_industry"] = by_industry
        items.append(v)
    return {"count": len(items), "region_code": region_code, "items": items}


@router.post("/admin/seed/reset", summary="시드 재적재(seed_dummy 원본)")
def reset_seed():
    conn = db.connect()
    try:
        counts = db.reset_seed(conn)
    finally:
        conn.close()
    return {"status": "reset", "seeded": counts,
            "note": "votes·cash_ledger 는 1단계 계약대로 빈 상태(투표 생성은 2단계)"}
