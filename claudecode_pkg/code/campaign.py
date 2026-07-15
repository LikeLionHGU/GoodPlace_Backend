"""
6단계 — 캠페인 상태 판단 · 환불 대상 선별 (담당 B · 순수 함수)

캠페인 모델(팀 확정 2026-07-15):
- 기간제(분기·3개월). **목표 투표수 없음** — 기간 동안 선결제 투표(쿠폰 선구매)를 모은다.
- 성사(success) = 기간 안에 창업자가 나타나 매칭됨(외부/관리자 신호로 status='success').
  성사 시 투표는 settled — 쿠폰 확정 = 개업일 첫 손님.
- 실패(failed) = 기한(deadline) 경과했는데 성사 없음 → held 투표 전건 환불(모의 캐시 적립).
- B는 성사 여부를 판정하지 않는다(외부 신호 존중). B의 몫 = 기한 판단 + 환불 대상 선별.
  실제 상태 쓰기·원장 기록(cash_add)은 apply 계층(db)에서 한다 — 여기는 순수 함수.

용어: '투자/펀딩' 아님 → 선결제·쿠폰 선구매. 환불 = 캐시(냥) 적립(모의).
"""
from datetime import date

# 환불 대상이 되는 투표 상태. settled(성사 확정분)·이미 환불된 표는 제외.
REFUNDABLE_STATUSES = ("held",)


def _as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(v)


def resolve_campaign(campaign: dict, now) -> dict:
    """캠페인이 지금 무엇을 해야 하는지 판단(순수 · DB 미접근).

    반환: {status, action, expired, reason}
      - status 가 success/failed → 종료됨(action='none')
      - open & now < deadline     → 진행 중(action='none')
      - open & now >= deadline     → 기한 경과·미성사 → action='expire'(→ failed·전건 환불)
    """
    status = campaign["status"]
    deadline = _as_date(campaign["deadline"])
    today = _as_date(now)

    if status in ("success", "failed"):
        return {"status": status, "action": "none", "expired": today >= deadline,
                "reason": f"이미 종료된 캠페인({status})"}
    if today < deadline:
        return {"status": "open", "action": "none", "expired": False,
                "reason": "기간 중 — 선결제 투표 수집 중"}
    return {"status": "open", "action": "expire", "expired": True,
            "reason": "기한 경과·미성사 → 실패 처리·held 투표 전건 환불"}


def refund_targets(votes: list) -> list:
    """환불 대상 투표 선별(순수). held 상태만 고른다(settled/refunded/cash_credited 제외).

    votes = 투표 행 dict 목록(각각 payment_status 포함). 반환은 그중 held 인 것들.
    """
    return [v for v in votes if v.get("payment_status") in REFUNDABLE_STATUSES]
