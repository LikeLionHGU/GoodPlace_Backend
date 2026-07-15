"""
명당 백엔드 - 담당 A (데이터·수집)
1단계: DB·시드·조회 API
"""
import json
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

import config
config.load_env_file()          # code/.env 의 키(OPENAI/SBIZ)를 os.environ 으로. 키는 코드에 두지 않는다.

from database import init_db, get_connection
from seed import insert_seed
from schemas import Industry, Vacancy
import routes_vote
import routes_cash
import routes_region
import routes_report
import routes_campaign
import routes_map
import ingest_api

app = FastAPI(title="명당 백엔드 - 담당 A")

# 프런트(GoodPlace_Front, 정적 파일 - 로컬 개발 서버)에서 브라우저로 직접 호출하기 위한 CORS 허용.
# 로컬 개발용 origin만 허용 — 배포 시 실제 프런트 도메인으로 좁혀야 한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500", "http://127.0.0.1:5500",
        "http://localhost:8080", "http://127.0.0.1:8080",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_vote.router)
app.include_router(routes_cash.router)
app.include_router(routes_region.router)
app.include_router(routes_report.router)
app.include_router(routes_campaign.router)
app.include_router(routes_map.router)
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
