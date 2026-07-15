"""
I4b — 지도 API: 공실별 상태(vacant/preparing/open)를 placements 기반으로 파생해 보여준다.

상태 정의(이번에 확정, database.py 주석 참고):
  vacant    — 그 공실에 placements 행이 아예 없음(아직 아무도 매칭 안 됨)
  preparing — placements 행 존재, status='preparing'(매칭됨, 아직 개업 전)
  open      — placements 행 존재, status='open'(개업 확정)

placements 행 자체를 만들고 상태를 'open'으로 확정하는 관리자 확인 흐름은
09번 구현 분담 보드 #11(성사 처리, 별도)이라 이 파일에는 최소한의 생성/전이 API만 둔다.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import (
    get_connection,
    insert_placement,
    update_placement_status,
    get_map_statuses,
    vacancy_exists,
    industry_exists,
)

router = APIRouter()


class PlacementCreate(BaseModel):
    region_code: str
    industry_id: int
    vacancy_id: int


@router.post("/placements")
def create_placement(payload: PlacementCreate):
    """성사 레코드 생성(모의). status='preparing'으로 시작."""
    if not industry_exists(payload.industry_id):
        raise HTTPException(status_code=404, detail="industry not found")
    if not vacancy_exists(payload.vacancy_id):
        raise HTTPException(status_code=404, detail="vacancy not found")
    return insert_placement(payload.region_code, payload.industry_id, payload.vacancy_id)


@router.post("/placements/{placement_id}/open")
def confirm_placement_open(placement_id: int):
    """개업 확정(모의 관리자 확인 버튼). status를 'open'으로 전이."""
    row = update_placement_status(placement_id, "open")
    if row is None:
        raise HTTPException(status_code=404, detail="placement not found")
    return row


@router.get("/map")
def get_map(region_code: str):
    """그 동네 공실 전체 + 파생된 지도 상태(vacant/preparing/open)."""
    conn = get_connection()
    try:
        vac_rows = conn.execute(
            "SELECT id, name, lat, lng FROM vacancies WHERE region_code = ? ORDER BY id", (region_code,)
        ).fetchall()
    finally:
        conn.close()

    statuses = get_map_statuses(region_code)
    return [
        {
            "vacancy_id": v["id"],
            "name": v["name"],
            "lat": v["lat"],
            "lng": v["lng"],
            "status": statuses.get(v["id"], "vacant"),
        }
        for v in vac_rows
    ]
