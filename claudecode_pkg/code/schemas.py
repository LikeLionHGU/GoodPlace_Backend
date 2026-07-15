"""응답용 Pydantic 모델 (자동 API 문서 및 타입 검증용)."""
from typing import Optional
from pydantic import BaseModel, Field


class Industry(BaseModel):
    id: int
    name: str
    min_area_m2: float
    max_area_m2: float
    avg_startup_cost_manwon: float
    inds_code: Optional[str] = None
    source: Optional[str] = None
    is_seed: int


class Vacancy(BaseModel):
    id: int
    name: str
    address: str
    region_code: str
    lat: float
    lng: float
    area_m2: float
    floor: Optional[str] = None  # v3: 카테고리형 '1층'/'2층이상'/'지하'
    vacant_since: Optional[str] = None
    prev_industry: Optional[str] = None
    competitors: dict
    evidence: Optional[str] = None
    building_use: Optional[str] = None
    facilities: dict
    rent_conditions: Optional[str] = None
    premium: Optional[str] = None
    is_seed: int


class VoteCreate(BaseModel):
    region_code: str
    industry_id: int
    voter_id: str
    voter_name: Optional[str] = Field(default=None, max_length=30)
    lat: float
    lng: float


class VoteOut(BaseModel):
    id: int
    region_code: str
    industry_id: int
    voter_id: str
    voter_name: Optional[str] = None
    voter_grid: str
    amount_won: int
    payment_status: str
    created_at: str
    is_seed: int


class VoteSummaryRow(BaseModel):
    region_code: str
    industry_id: int
    industry_name: str
    voter_grid: str
    vote_count: int


class VoteSummaryResponse(BaseModel):
    total_votes: int
    summary: list[VoteSummaryRow]


class VoteBatchCreate(BaseModel):
    region_code: str
    voter_id: str
    voter_name: Optional[str] = Field(default=None, max_length=30)
    lat: float
    lng: float
    industry_ids: list[int]


class VoteBatchResponse(BaseModel):
    voter_id: str
    voted_count: int
    total_charged_won: int
    votes: list[VoteOut]
    balance_after_won: int
    insufficient_balance: bool


class CashCreditRequest(BaseModel):
    voter_id: str
    amount_won: int
    reason: str
    ref_id: Optional[int] = None


class CashUseRequest(BaseModel):
    voter_id: str
    amount_won: int
    reason: str
    ref_id: Optional[int] = None


class CashLedgerOut(BaseModel):
    id: int
    voter_id: str
    delta_won: int
    reason: str
    ref_id: Optional[int] = None
    created_at: str
    balance: int


class CashBalanceResponse(BaseModel):
    voter_id: str
    balance: int


class RegionDemandRanking(BaseModel):
    industry_id: int
    industry_name: str
    vote_count: int
    rank: int


class RegionDemandResponse(BaseModel):
    region_code: str
    total_voters: int
    ranking: list[RegionDemandRanking]


class RegionSummary(BaseModel):
    region_code: str
    total_votes: int
