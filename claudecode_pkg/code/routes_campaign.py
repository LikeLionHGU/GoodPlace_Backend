"""
6단계 — 캠페인·환불(모의) API. 얇은 연결층: campaign.resolve_campaign(판단·순수) + db(실행).

- GET  /campaigns                     캠페인 목록 + 각 기한 판단(now=오늘 기준).
- POST /campaigns/{campaign_id}/resolve  기한 경과·미성사면 실패 처리 = held 투표 전건 환불(캐시 냥 적립).

결제·환불 전부 모의(실PG 없음). 환불 = 캐시(냥) 적립. 성사(success)는 외부/관리자 신호(7단계) —
여기서는 '기한 경과·미성사 → 실패·환불' 경로만 판단·실행한다.
now 쿼리 파라미터는 시연용(기한 후 상황 재현). 없으면 서버 오늘.
"""
from datetime import date

from fastapi import APIRouter, HTTPException, Query

import campaign as campaign_logic
import config
import db

router = APIRouter()


def _to_nyang(won: int) -> int:
    return won // config.CASH_POLICY["won_per_nyang"]


@router.get("/campaigns", summary="캠페인 목록 + 기한 판단")
def list_campaigns(region_code: str | None = None, now: str | None = None):
    today = now or date.today().isoformat()
    conn = db.connect()
    try:
        camps = db.list_campaigns(conn, region_code)
    finally:
        conn.close()
    items = [{**c, "resolution": campaign_logic.resolve_campaign(c, today)} for c in camps]
    return {"now": today, "region_code": region_code, "count": len(items), "items": items}


@router.post("/campaigns/{campaign_id}/resolve",
             summary="캠페인 기한 판단·실패 시 전건 환불(모의)")
def resolve_campaign(campaign_id: str, now: str | None = None):
    today = now or date.today().isoformat()
    conn = db.connect()
    try:
        camp = db.get_campaign(conn, campaign_id)
        if camp is None:
            raise HTTPException(status_code=404, detail=f"없는 캠페인: {campaign_id}")
        resolution = campaign_logic.resolve_campaign(camp, today)
        if resolution["action"] == "expire":
            result = db.refund_campaign_votes(conn, camp)      # held→refunded + 캐시 적립 + failed
        else:
            result = {"campaign_id": campaign_id, "refunded_count": 0, "cash_won": 0}
    finally:
        conn.close()
    return {
        "now": today,
        "resolution": resolution,
        "refunded_count": result["refunded_count"],
        "cash_refunded_won": result["cash_won"],
        "cash_refunded_nyang": _to_nyang(result["cash_won"]),
        "note": "모의 환불 — 실제 청구/입금 없음. 환불은 캐시(냥) 적립.",
    }
