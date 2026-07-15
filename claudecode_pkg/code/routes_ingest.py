"""
7단계 — 소상공인 API 수집 미리보기 API (담당 A). 실호출은 SBIZ_SERVICE_KEY(.env) 필요.

- GET /admin/ingest/preview?region_code=... : dry-run. 실호출 → 영업/폐업/경쟁/공실후보 요약.
  **DB 에 적재하지 않는다** — 공실 확정에는 면적(건축물대장)·로드뷰 확인이 필요하기 때문(정직).
- 키 없으면 503(안내). 호출 실패면 502(키·원문 노출 없이 타입만).
- 지역 하드코딩 금지 — region_code 필수 인자.
"""
from fastapi import APIRouter, HTTPException, Query

import ingest_api

router = APIRouter()


@router.get("/admin/ingest/preview", summary="소상공인 API 수집 미리보기(dry-run · DB 미적재)")
def ingest_preview(region_code: str = Query(..., description="행정동 코드(필수). 양덕동은 인자"),
                   rows: int = 50):
    try:
        stores = ingest_api.fetch_stores(region_code, rows=rows)
    except RuntimeError as e:                     # 키 없음
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:                         # 호출/파싱 실패 — 키·원문 노출 금지
        raise HTTPException(status_code=502, detail=f"소상공인 API 호출 실패: {type(e).__name__}")

    summary = ingest_api.analyze_stores(stores)
    return {
        "region_code": region_code,
        "store_count": len(stores),
        "note": ("미리보기(dry-run) — DB 미적재. 공실 확정은 면적(건축물대장)·로드뷰 확인 필요. "
                 "경쟁 집계·공실 후보는 추정값."),
        **summary,
    }
