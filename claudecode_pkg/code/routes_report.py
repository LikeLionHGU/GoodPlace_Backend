"""
I3 — 리포트 v3 노출 API: POST /report (industry_id+region_code, 50냥 차감).
담당 B(리포트 로직은 report.py·ai_explain.py 그대로) + A cash 연동(routes_report 레이어에서 얇게 연결).

흐름: 업종/공실/투표집계를 DB에서 로드 → report.build_report()(순수 함수) → 없으면 404.
있으면 카드마다 ai_explain.generate_explanation() 으로 해설 붙이고(키 없으면 null),
그 다음에만 cash_ledger 50냥(=500원) 차감(reason='report'). 존재하지 않는 리포트에 과금하지 않는다.

잔액 부족 처리: routes_vote.py의 /votes/batch와 동일한 정책 — 모의결제 단계라 충전 정책이
아직 미정이므로 막지 않고 insufficient_balance 플래그로만 알려준다(일관성 유지).
"""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config
from database import get_connection, get_vote_grid_counts, get_cash_balance, insert_cash_ledger, nyang_to_won
from report import build_report
from ai_explain import generate_explanation

router = APIRouter()

REPORT_COST_NYANG = config.CASH_PER_REPORT_NYANG   # 50냥
REPORT_COST_WON = nyang_to_won(REPORT_COST_NYANG)  # 500원


class ReportRequest(BaseModel):
    industry_id: int
    region_code: str
    voter_id: str


def _load_industries(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM industries ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def _load_vacancies(conn, region_code: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM vacancies WHERE region_code = ? ORDER BY id", (region_code,)
    ).fetchall()
    vacancies = []
    for r in rows:
        v = dict(r)
        v["competitors"] = json.loads(v["competitors"])  # engine은 dict를 기대(JSON 문자열 그대로 넘기면 안 됨)
        vacancies.append(v)
    return vacancies


@router.post("/report")
def get_report(payload: ReportRequest):
    conn = get_connection()
    try:
        industries = _load_industries(conn)
        vacancies = _load_vacancies(conn, payload.region_code)
    finally:
        conn.close()

    grid_votes_all = get_vote_grid_counts()

    rep = build_report(payload.industry_id, payload.region_code, vacancies, industries, grid_votes_all)
    if rep is None:
        raise HTTPException(status_code=404, detail="industry not found, or no vacancies in region")

    for card in rep["vacancies"]:
        card["ai_explanation"] = generate_explanation(rep, card)

    insufficient = get_cash_balance(payload.voter_id) < REPORT_COST_WON
    insert_cash_ledger(payload.voter_id, -REPORT_COST_WON, "report", None)
    balance_after = get_cash_balance(payload.voter_id)

    rep["charge"] = {
        "charged_won": REPORT_COST_WON,
        "charged_nyang": REPORT_COST_NYANG,
        "balance_after_won": balance_after,
        "insufficient_balance": insufficient,
    }
    return rep
