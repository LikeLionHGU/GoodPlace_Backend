"""
명당 백엔드 - 담당 A (데이터·수집)
1단계: DB·시드·조회 API
"""
import json
from typing import Optional

from fastapi import FastAPI, Query

import config
config.load_env_file()          # code/.env 의 키(OPENAI/SBIZ)를 os.environ 으로. 키는 코드에 두지 않는다.

from database import init_db, get_connection
from seed import insert_seed
from schemas import Industry, Vacancy
import routes_vote
import routes_cash
import routes_region
import routes_report
import ingest_api

app = FastAPI(title="명당 백엔드 - 담당 A")
app.include_router(routes_vote.router)
app.include_router(routes_cash.router)
app.include_router(routes_region.router)
app.include_router(routes_report.router)
app.include_router(ingest_api.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    insert_seed()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/industries", response_model=list[Industry])
def list_industries():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM industries ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/vacancies", response_model=list[Vacancy])
def list_vacancies(region_code: Optional[str] = Query(default=None)):
    """
    v3: 투표가 더 이상 공실에 직접 묶이지 않으므로(동네+업종 투표로 전환)
    여기서는 등록된 공실 정보만 반환한다. 공실별 수요(거리감쇠)는 B의 엔진이 계산한다.
    """
    conn = get_connection()
    try:
        if region_code:
            vac_rows = conn.execute(
                "SELECT * FROM vacancies WHERE region_code = ? ORDER BY id", (region_code,)
            ).fetchall()
        else:
            vac_rows = conn.execute("SELECT * FROM vacancies ORDER BY id").fetchall()

        result = []
        for vac in vac_rows:
            vac_dict = dict(vac)
            vac_dict["competitors"] = json.loads(vac_dict["competitors"])
            vac_dict["facilities"] = json.loads(vac_dict["facilities"])
            result.append(vac_dict)

        return result
    finally:
        conn.close()
