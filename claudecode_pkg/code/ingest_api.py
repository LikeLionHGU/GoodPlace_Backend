"""
7단계 — 소상공인 상가정보 API(B553077) 수집·지역 확장.
담당 A(데이터·수집). 명세서: docs/명당_backend_A/소상공인_상가정보_API_명세서.md

중요:
- 이 API는 "영업 중인 점포"가 기본이며, 공실 여부를 직접 알려주지 않는다.
  폐업 데이터(clbizDt)는 어디까지나 "공실 후보"일 뿐, 로드뷰·건축물대장 대조 전까지
  공실로 단정하지 않는다.
- serviceKey는 환경변수(DATA_GO_KR_SERVICE_KEY)에서만 읽는다. 코드/깃에 하드코딩 금지.
- region_code는 좌표(lat, lng)·반경(radius)과 함께 호출부에서 파라미터로 받는다.
  양덕동은 첫 적용지일 뿐이며, 하드코딩된 값이 아니다 (경북 어디든 좌표만 바꾸면 수집됨).
"""
import os
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

BASE_URL = "https://apis.data.go.kr/B553077/api/open/sdsc2"
SERVICE_KEY_ENV = "SBIZ_SERVICE_KEY"   # .env 의 키 이름과 통일(우리 스택)


def _get_service_key() -> str:
    key = os.environ.get(SERVICE_KEY_ENV)
    if not key:
        raise RuntimeError(
            f"환경변수 {SERVICE_KEY_ENV} 가 설정되어 있지 않습니다. "
            f"공공데이터포털에서 발급받은 서비스키(Decoding 원문)를 "
            f'터미널에서 `export {SERVICE_KEY_ENV}="발급받은_키"` 로 설정한 뒤 서버를 실행하세요.'
        )
    return key


def _parse_items(data: dict) -> tuple[list[dict], Optional[int]]:
    """
    data.go.kr 공공데이터 API 특유의 응답 포맷을 방어적으로 파싱한다.
    - 'body' 래핑이 없는 경우도 있어 get으로 안전하게 처리
    - item이 1건이면 dict, 여러 건이면 list로 오는 흔한 케이스를 정규화
    """
    body = data.get("body", data)
    total_count = body.get("totalCount")
    items = body.get("items")

    if items is None:
        return [], total_count

    item = items.get("item", []) if isinstance(items, dict) else items
    if isinstance(item, dict):
        item = [item]
    return item, total_count


def fetch_stores_in_radius(
    lat: float,
    lng: float,
    radius: int,
    num_of_rows: int = 1000,
    service_key: Optional[str] = None,
) -> list[dict]:
    """
    storeListInRadius 로 좌표(lat, lng) 반경(radius, m) 내 점포를 전량 수집한다.
    cx=경도(lng), cy=위도(lat) 순서 주의 (명세서 §3-1, §7).
    totalCount 기준으로 필요한 만큼 페이징을 순회한다.
    """
    key = service_key or _get_service_key()
    stores: list[dict] = []
    page_no = 1

    while True:
        params = {
            "serviceKey": key,
            "cx": lng,
            "cy": lat,
            "radius": radius,
            "type": "json",
            "numOfRows": num_of_rows,
            "pageNo": page_no,
        }
        resp = httpx.get(f"{BASE_URL}/storeListInRadius", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        items, total_count = _parse_items(data)
        stores.extend(items)

        if not items or total_count is None or len(stores) >= total_count:
            break
        page_no += 1

    return stores


def is_closed(store: dict) -> bool:
    """
    clbizDt(폐업일)가 채워져 있으면 폐업으로 본다.

    [확인됨 2026-07-15] storeListInRadius 실제 호출 결과, 응답 header.columns(38개 필드)에
    opbizDt/clbizDt 자체가 없다 — 이 오퍼레이션은 개업/폐업 이력을 아예 반환하지 않는다
    (명세서의 [확인필요] 항목이 "미제공"으로 확인됨). 따라서 현재는 항상 폐업 0건으로 나온다.
    폐업 이력이 필요하면 storeListByDate 등 다른 오퍼레이션을 별도로 조사해야 한다 (다음 작업).
    """
    return bool(store.get("clbizDt"))


def split_active_closed(stores: list[dict]) -> tuple[list[dict], list[dict]]:
    """영업 중 / 폐업(=공실 후보 출발점) 분리."""
    active = [s for s in stores if not is_closed(s)]
    closed = [s for s in stores if is_closed(s)]
    return active, closed


def count_competitors(stores: list[dict], key_field: str = "indsSclsNm") -> dict:
    """
    영업 중인 점포를 업종(기본: 소분류명)별로 집계.
    vacancies.competitors 컬럼(JSON)에 그대로 넣을 수 있는 형태: {"카페": 12, "편의점": 5}
    """
    counts: dict = {}
    for s in stores:
        name = s.get(key_field) or "미분류"
        counts[name] = counts.get(name, 0) + 1
    return counts


def build_vacancy_candidates(closed_stores: list[dict]) -> list[dict]:
    """
    폐업 점포 -> 공실 '후보' 목록.
    공실 확정이 아니다 (같은 주소에 신규 점포가 들어왔을 수 있음) —
    로드뷰·건축물대장 대조는 다음 작업으로 남긴다.
    """
    candidates = []
    for s in closed_stores:
        candidates.append(
            {
                "name": s.get("bizesNm"),
                "address": s.get("rdnmAdr") or s.get("lnoAdr"),
                "lat": s.get("lat"),
                "lng": s.get("lon"),
                "floor": s.get("flrNo"),
                "prev_industry": s.get("indsSclsNm"),
                "closed_date": s.get("clbizDt"),
                "is_confirmed_vacancy": False,
            }
        )
    return candidates


# ---- API 라우터 ----

router = APIRouter(prefix="/admin")


class IngestRequest(BaseModel):
    region_code: str
    lat: float
    lng: float
    radius: int = 500


class IngestResponse(BaseModel):
    region_code: str
    lat: float
    lng: float
    radius: int
    total_collected: int
    active_count: int
    closed_count: int
    competitors: dict
    vacancy_candidates: list[dict]
    note: str


@router.post("/ingest", response_model=IngestResponse)
def ingest(payload: IngestRequest):
    """
    지정한 좌표 반경의 점포를 소상공인 API로 수집해 영업/폐업 분리·경쟁점 집계만 반환한다.
    DB에는 적재하지 않는다 (공실 확정은 로드뷰·건축물대장 대조 후 별도 작업).
    region_code는 하드코딩이 아니라 호출 시 파라미터로 받으며, 이후 실제 vacancies 적재 시 그대로 쓰인다.
    """
    try:
        stores = fetch_stores_in_radius(payload.lat, payload.lng, payload.radius)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"소상공인 API 호출 실패: {type(e).__name__}")

    active, closed = split_active_closed(stores)
    competitors = count_competitors(active)
    candidates = build_vacancy_candidates(closed)

    return {
        "region_code": payload.region_code,
        "lat": payload.lat,
        "lng": payload.lng,
        "radius": payload.radius,
        "total_collected": len(stores),
        "active_count": len(active),
        "closed_count": len(closed),
        "competitors": competitors,
        "vacancy_candidates": candidates,
        "note": (
            "이 응답은 수집·분석 요약이며 DB에 적재되지 않았습니다. "
            "공실 확정은 로드뷰·건축물대장 대조 후 별도 작업으로 vacancies 테이블에 반영합니다."
        ),
    }
