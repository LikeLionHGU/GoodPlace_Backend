"""
동네 수요 리스트 API (09_구현_분담_보드.md #3).
주민·창업자 공용 진입점 — 동네를 고르면 그 동네의 업종별 득표 순위를 보여준다.
조회 전용(읽기만). 기존 votes/vote_grid_summary 스키마 위에 얹는다 (스키마 변경 없음).
"""
from fastapi import APIRouter, Query

from database import get_region_demand, get_regions_summary
from schemas import RegionDemandResponse, RegionSummary

router = APIRouter(prefix="/regions")


@router.get("", response_model=list[RegionSummary])
def list_regions():
    """votes에 존재하는 region_code 목록 + 동네별 총 투표 수 (동네 검색 드롭다운용)."""
    return get_regions_summary()


@router.get("/{region_code}/demand", response_model=RegionDemandResponse)
def region_demand(region_code: str, include_seed: bool = Query(default=True)):
    """
    그 동네의 업종별 득표 순위(vote_count 내림차순, 동점이면 industry_id 오름차순).
    투표가 없는 동네도 404가 아니라 total_voters=0, ranking=[] 로 반환한다.
    """
    total_voters, ranking = get_region_demand(region_code, include_seed=include_seed)
    return {"region_code": region_code, "total_voters": total_voters, "ranking": ranking}
