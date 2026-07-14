"""
명당 백엔드 — FastAPI 앱 (1단계: DB·시드·조회 API).

실행:  cd code && ../.venv/bin/uvicorn main:app --reload
문서:  http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

import db
from routes_query import router
from routes_vote import router as vote_router
from routes_allocation import router as allocation_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.connect()
    try:
        db.init_db(conn)
        if db.table_counts(conn)["industries"] == 0:  # 최초 기동 시 자동 시드
            db.reset_seed(conn)
    finally:
        conn.close()
    yield


app = FastAPI(
    title="명당 API",
    description="주민 수요 검증 기반 AI 창업 의사결정 플랫폼 — 쿠폰 선구매(선결제) 투표 데이터 기반. "
                "1단계: DB·시드·조회 API (결제는 모의, 시드는 전부 SEED 표기).",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(vote_router)
app.include_router(allocation_router)
