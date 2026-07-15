"""
5단계 — 창업 리포트 API. 얇은 연결층: 어댑터로 모아 report.build_report() 를 그대로 호출.

- GET /report/{vacancy_id} : 공실 하나의 창업 리포트(5요소).
- 없는 공실이면 404.
- 리포트 1순위 = 지도 배치의 배정 업종(핀 일치). 그래서 배치를 그 공실의 region_code
  '전체'로 돌려 build_report 에 넘긴다(리포트가 공실별로 재랭킹하면 겹침이 되살아나므로 금지).
- 리포트는 점수를 다시 매기지 않는다 — 값은 engine breakdown 그대로(report.py 담당).
- ai_explanation: 확정 수치 기반 AI 해설(P4). 키(OPENAI_API_KEY) 없으면 None(리포트는 그대로).
  ?explain=false 로 끌 수 있음.
"""
import logging

from fastapi import APIRouter, HTTPException

import adapters
import ai_explain
import db
from report import build_report

router = APIRouter()
log = logging.getLogger("myeongdang.report")


@router.get("/report/{vacancy_id}", summary="공실 창업 리포트(5요소 · 지도 배치와 1순위 일치)")
def get_report(vacancy_id: str, explain: bool = True):
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT region_code FROM vacancies WHERE id = ?", (vacancy_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"없는 공실: {vacancy_id}")
        region_code = row["region_code"]
        # 배치 일치를 위해 그 지역 전체를 로드(build_report 가 내부에서 allocate 한다).
        vacancies, industries, vote_counts = adapters.load_allocation_inputs(conn, region_code)
        camp = conn.execute(
            "SELECT * FROM campaign WHERE region_code = ? AND status = 'open' "
            "ORDER BY deadline LIMIT 1",
            (region_code,),
        ).fetchone()
    finally:
        conn.close()

    campaign = dict(camp) if camp is not None else None
    report = build_report(vacancy_id, vacancies, industries, vote_counts, campaign=campaign)
    if report is None:              # region 필터로 사라진 경우 등 방어
        raise HTTPException(status_code=404, detail=f"없는 공실: {vacancy_id}")
    # AI 해설(P4): 키 있으면 확정 수치 기반 3~5문장, 없으면 None(리포트는 그대로 — 조용한 대체 금지).
    report["ai_explanation"] = ai_explain.generate_explanation(report) if explain else None
    log.info("GET /report/%s region_code=%s -> %s (ai=%s)",
             vacancy_id, region_code, report["conclusion"]["recommended_industry"],
             bool(report["ai_explanation"]))
    return report
