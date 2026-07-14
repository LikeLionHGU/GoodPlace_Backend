"""
3·4단계 통합 — 배치 API. 얇은 연결층: 어댑터로 모아 engine.allocate() 를 그대로 호출.

- GET /allocation?region_code=... : 필수 region_code. 지역 하드코딩 금지(양덕동은 기본값 아님·인자).
- 응답은 엔진 산출을 축약 없이 그대로(배정·점수·breakdown·runners_up·weights·algorithm).
- 공실 없으면 빈 배열+200, 투표 0건이어도 정상 200.
- 성능 최적화 금지(캐싱·비동기·사전계산 X). 응답 시간만 측정해 로그로 남긴다.
"""
import logging
import time

from fastapi import APIRouter, Query

import adapters
import db
from engine import allocate

router = APIRouter()
log = logging.getLogger("myeongdang.allocation")


@router.get("/allocation", summary="지역별 겹침 해소 배치(엔진 산출 그대로)")
def get_allocation(region_code: str = Query(..., description="행정동/시군구 코드(필수). 양덕동은 인자이지 기본값이 아님")):
    t0 = time.perf_counter()
    conn = db.connect()
    try:
        vacancies, industries, vote_counts = adapters.load_allocation_inputs(conn, region_code)
    finally:
        conn.close()

    if not vacancies:               # 해당 지역 공실 없음 → 빈 배열 + 200(에러 아님)
        result = {"weights": None, "algorithm": None, "total_score": 0, "allocations": []}
    else:                           # 투표 0건이어도 엔진이 전 공실 점수 0으로 정상 반환
        result = allocate(vacancies, industries, vote_counts)

    elapsed_ms = (time.perf_counter() - t0) * 1000
    log.info("GET /allocation region_code=%s vacancies=%d votes=%d -> %.1f ms",
             region_code, len(vacancies), sum(vote_counts.values()), elapsed_ms)
    return {
        "region_code": region_code,
        "vacancy_count": len(vacancies),
        "elapsed_ms": round(elapsed_ms, 1),
        **result,
    }
