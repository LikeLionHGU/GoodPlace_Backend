"""
I4a — 캠페인 생성·조회·환불 적용 API.
캠페인 상태 판단(기한 경과 여부)과 환불 대상 선별은 campaign.py의 순수 함수를 그대로 쓴다.
여기(routes_campaign.py)는 DB 연동(생성/조회/실제 반영)만 담당한다 — 09번 보드의 "A: cash_ledger
기록 API" 역할과 같은 성격.

주의(region 기반 설계의 전제): votes 테이블에는 campaign_id가 없다(스키마 고정, region_code만 있음).
그래서 "그 캠페인의 환불 대상"은 실제로는 "그 동네(region_code)의 held 투표 전체"로 계산한다.
한 동네에 시간이 겹치지 않는 캠페인이 하나씩만 진행된다는 전제(분기제)에서는 문제 없지만,
같은 동네에 캠페인이 겹치면 부정확해질 수 있다 — 스키마에 campaign_id를 추가하기 전까지의 알려진 한계.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database import insert_campaign, get_campaign, get_held_votes_for_region, apply_campaign_refund
import campaign as campaign_logic

router = APIRouter(prefix="/campaigns")


class CampaignCreate(BaseModel):
    region_code: str
    deadline: str          # "YYYY-MM-DD"
    coupon_value_won: int = 1000


@router.post("")
def create_campaign(payload: CampaignCreate):
    return insert_campaign(payload.region_code, payload.deadline, payload.coupon_value_won)


@router.get("/{campaign_id}")
def get_campaign_route(campaign_id: int):
    c = get_campaign(campaign_id)
    if c is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return c


@router.post("/{campaign_id}/resolve")
def resolve_campaign_route(campaign_id: int, as_of: Optional[str] = Query(default=None)):
    """
    캠페인 상태를 판단(campaign.resolve_campaign)하고, 기한 경과·미성사면 그 동네의 held 투표
    전건을 환불 적용한다(database.apply_campaign_refund). 이미 종료됐거나 기간 중이면 변경 없음.
    as_of: 기준일 override("YYYY-MM-DD") — 테스트/시연용. 생략하면 오늘 날짜.
    """
    c = get_campaign(campaign_id)
    if c is None:
        raise HTTPException(status_code=404, detail="campaign not found")

    today = as_of or date.today().isoformat()
    resolution = campaign_logic.resolve_campaign(c, today)

    result = {"campaign_id": campaign_id, **resolution, "refunded_count": 0, "refunded_total_won": 0}
    if resolution["action"] == "expire":
        held = get_held_votes_for_region(c["region_code"])
        targets = campaign_logic.refund_targets(held)
        ledger_rows = apply_campaign_refund(campaign_id, targets)
        result["refunded_count"] = len(ledger_rows)
        result["refunded_total_won"] = sum(r["delta_won"] for r in ledger_rows)

    return result
