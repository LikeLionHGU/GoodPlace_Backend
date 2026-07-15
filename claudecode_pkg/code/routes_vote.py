"""
투표 생성/집계 API (v3 — 동네+업종 투표 전환).
담당 A(데이터·수집). B에게 넘기는 집계 형태는 (region_code, industry_id, voter_grid) -> 투표수로
database.get_vote_grid_counts() / vote_grid_summary 뷰가 안정적으로 유지한다.
"""
import math

from fastapi import APIRouter, HTTPException, Query, status

from database import industry_exists, insert_vote, insert_votes_batch, get_vote_summary_detail, get_cash_balance
from schemas import VoteCreate, VoteOut, VoteSummaryResponse, VoteBatchCreate, VoteBatchResponse

router = APIRouter()

GRID_SIZE_M = 200.0
_METERS_PER_DEG_LAT = 111_320.0


def snap_to_grid(lat: float, lng: float, grid_size_m: float = GRID_SIZE_M) -> str:
    """
    GPS 좌표를 200m 격자로 스냅한다. 정밀 원좌표는 저장하지 않는다 (개인정보 보호, 08번 §1).
    위경도 1도당 거리(m)는 위도에 따라 달라지므로 경도 스텝은 cos(lat) 보정을 적용한다.
    """
    lat_step_deg = grid_size_m / _METERS_PER_DEG_LAT
    lng_step_deg = grid_size_m / (_METERS_PER_DEG_LAT * math.cos(math.radians(lat)))

    snapped_lat = math.floor(lat / lat_step_deg) * lat_step_deg
    snapped_lng = math.floor(lng / lng_step_deg) * lng_step_deg
    return f"{snapped_lat:.3f},{snapped_lng:.3f}"


@router.post("/votes", response_model=VoteOut, status_code=status.HTTP_201_CREATED)
def create_vote(payload: VoteCreate):
    """
    동네+업종 투표 생성 (모의결제 held 상태로만 기록, 실제 청구 없음).
    amount_won은 항상 1,000원 고정 — 요청 바디로 받지 않고 서버가 강제한다.
    투표 시점 GPS(lat, lng)는 200m 격자로 스냅해서 voter_grid만 저장하고, 정밀 좌표는 버린다.

    주의: 1인 1표 제한·중복 투표 차단 등 어뷰징 방지는 MVP 범위 밖이다.
    실서비스 전환 전 반드시 추가로 구현이 필요하다 (여기서는 구현하지 않음).
    """
    if not industry_exists(payload.industry_id):
        raise HTTPException(status_code=404, detail="industry not found")

    voter_grid = snap_to_grid(payload.lat, payload.lng)
    return insert_vote(payload.region_code, payload.industry_id, payload.voter_id, payload.voter_name, voter_grid)


@router.post("/votes/batch", response_model=VoteBatchResponse, status_code=status.HTTP_201_CREATED)
def create_votes_batch(payload: VoteBatchCreate):
    """
    여러 세부 업종을 한 번에 담아 투표 + 냥 일괄 차감(cash_ledger, reason='vote').
    투표 시점 GPS는 한 번만 받아 200m 격자로 스냅하고, 담은 업종 전부에 같은 voter_grid를 적용한다.

    industry_ids 중 하나라도 없으면 404 — 사전 검증에서 걸러지므로 votes/cash_ledger에는
    아무것도 쓰이지 않는다. 실제 삽입(votes N건 + cash_ledger 차감 1건)은 insert_votes_batch()가
    하나의 DB 트랜잭션으로 묶어서, 중간에 문제가 생겨도 전부 롤백되게 한다.

    잔액 부족 처리: 모의결제 단계라 충전/초기지급 정책(05번 결정대기)이 아직 미정이다.
    여기서 잔액 부족을 이유로 투표를 막으면 정책이 정해지기 전까지 시연 자체가 막히므로,
    지금은 막지 않고 insufficient_balance 플래그로만 알려준다. 정책이 확정되면 그때 막는다.

    주의: 1인 1표 제한·중복 투표 차단 등 어뷰징 방지는 MVP 범위 밖이다 (구현하지 않음).
    """
    if not payload.industry_ids:
        raise HTTPException(status_code=400, detail="industry_ids must not be empty")

    for industry_id in payload.industry_ids:
        if not industry_exists(industry_id):
            raise HTTPException(status_code=404, detail=f"industry not found: {industry_id}")

    voter_grid = snap_to_grid(payload.lat, payload.lng)
    total_charged = 1000 * len(payload.industry_ids)
    insufficient = get_cash_balance(payload.voter_id) < total_charged

    votes, _ledger_row, balance_after = insert_votes_batch(
        payload.region_code, payload.industry_ids, payload.voter_id, payload.voter_name, voter_grid
    )

    return {
        "voter_id": payload.voter_id,
        "voted_count": len(votes),
        "total_charged_won": total_charged,
        "votes": votes,
        "balance_after_won": balance_after,
        "insufficient_balance": insufficient,
    }


@router.get("/votes/summary", response_model=VoteSummaryResponse)
def votes_summary(include_seed: bool = Query(default=True)):
    """
    동네·업종·격자별 투표 집계. B에게 넘어가는 핵심 재료(v3 계약)이므로 형태를 안정적으로 유지한다.
    held/settled만 집계 (refunded·cash_credited 제외). include_seed=false 면 실투표(is_seed=0)만.
    """
    summary, total = get_vote_summary_detail(include_seed=include_seed)
    return {"total_votes": total, "summary": summary}
