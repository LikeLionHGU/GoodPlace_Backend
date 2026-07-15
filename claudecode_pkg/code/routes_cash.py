"""
2단계 — 캐시(모의) 뼈대.
교환비율·유효기간·재투표 시 현금 동일취급 여부는 팀 미정 (담당_A_가이드 '결정 대기' 참고).
지금은 1캐시=1원 단순 적립/차감만 구현하고, 정책은 나중에 확장한다.
"""
from fastapi import APIRouter, HTTPException, Query

from database import get_cash_balance, insert_cash_ledger
from schemas import CashCreditRequest, CashUseRequest, CashLedgerOut, CashBalanceResponse

router = APIRouter(prefix="/cash")


@router.post("/credit", response_model=CashLedgerOut)
def credit_cash(payload: CashCreditRequest):
    """캐시 적립 (예: 환불 시 현금 대신 적립). delta_won은 항상 양수로 기록된다."""
    row = insert_cash_ledger(payload.voter_id, payload.amount_won, payload.reason, payload.ref_id)
    balance = get_cash_balance(payload.voter_id)
    return {**row, "balance": balance}


@router.post("/use", response_model=CashLedgerOut)
def use_cash(payload: CashUseRequest):
    """캐시 사용 (재투표/쿠폰구매). 잔액보다 많이 쓰려 하면 400."""
    balance = get_cash_balance(payload.voter_id)
    if payload.amount_won > balance:
        raise HTTPException(status_code=400, detail="insufficient cash balance")

    row = insert_cash_ledger(payload.voter_id, -payload.amount_won, payload.reason, payload.ref_id)
    new_balance = get_cash_balance(payload.voter_id)
    return {**row, "balance": new_balance}


@router.get("/balance", response_model=CashBalanceResponse)
def cash_balance(voter_id: str = Query(...)):
    return {"voter_id": voter_id, "balance": get_cash_balance(voter_id)}
