"""
2단계 — 투표(모의 결제) · 집계 API (담당 A 몫).

- POST /votes          투표 1건 생성(1,000원 선결제, 모의). payment_status='held' 까지만.
- GET  /votes/summary  전체·공실별·시드/실 구분 집계.

결제는 모의(실PG·사업자등록 없음). 환불·정산 상태 전이는 6단계 — 여기서 만들지 않는다.
배치·리포트(엔진) 노출은 이 단계가 아니다.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from config import VOTER_NAME_MAX_LEN

router = APIRouter()


class VoteIn(BaseModel):
    """투표 입력. amount_won 은 **일부러 받지 않는다**(서버가 1,000원 고정).

    model_config extra 무시(기본) → 클라이언트가 amount_won 을 보내도 무시된다.
    """
    vacancy_id: str = Field(..., min_length=1)
    industry_id: str = Field(..., min_length=1)
    voter_id: str = Field(..., min_length=1, max_length=64, description="투표자 식별자")
    voter_name: str | None = Field(
        None, max_length=VOTER_NAME_MAX_LEN, description=f"표시명(≤{VOTER_NAME_MAX_LEN}자)")


@router.post("/votes", status_code=201,
             summary="투표 생성(1,000원 선결제·모의, held)",
             description="1표=1,000원 서버 고정. 결제는 모의(실PG 없음). "
                         "어뷰징 방지(1인 한도·중복 차단)는 MVP 범위 밖 — 실서비스 전 필요.")
def create_vote(body: VoteIn):
    conn = db.connect()
    try:
        row = db.create_vote(conn, body.vacancy_id, body.industry_id,
                             body.voter_id, body.voter_name, is_seed=0)
    except db.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        conn.close()
    return {"status": "held", "vote": row,
            "note": "모의 결제 — 실제 청구 없음. 상태 전이(환불·정산)는 6단계."}


@router.get("/votes/summary", summary="투표 집계(전체·공실별·시드/실 구분)")
def votes_summary(region_code: str | None = None):
    conn = db.connect()
    try:
        summary = db.votes_summary(conn, region_code)
    finally:
        conn.close()
    return {"region_code": region_code, **summary}
