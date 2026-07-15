"""
7단계 — 소상공인 상가(상권)정보 API 수집 (담당 A). 명세: docs/소상공인_상가정보_API_명세서.md

정직한 전제(명세서가 [확인필요]로 둔 것 — 실호출로만 확정):
- serviceKey 는 코드에 두지 않는다 → 환경변수 SBIZ_SERVICE_KEY 에만. 없으면 실호출 불가.
  요청 빌더·응답 파서 같은 순수 로직은 키 없이 합성 데이터로 검증한다.
- 파라미터명(divId/key)·응답 봉투 구조·clbizDt 채움 여부·양덕동 행정동 코드는 첫 실호출로 확정.
- 지역 하드코딩 금지 — region_code(행정동 코드) 인자만 사용(양덕동은 첫 적용지, 경북 확장).

이 모듈은 순수 변환(요청 구성·응답 파싱)만 담당한다. 실제 HTTP 호출·DB 적재는 이후 단계.
"""
import os
from urllib.parse import urlencode

from config import SBIZ_API_BASE, SBIZ_DEFAULT_ROWS


# ── A-1: 요청 빌더 ────────────────────────────────────────────────────────
def build_admi_request(region_code, page=1, rows=SBIZ_DEFAULT_ROWS, service_key=None):
    """storeListInAdmi(행정동 기준 점포 목록) 요청 (url, params) 구성. 순수.

    service_key 미지정 시 환경변수 SBIZ_SERVICE_KEY 사용(코드·로그에 평문 금지).
    지역은 region_code(행정동 코드) 인자만 — 하드코딩 없음.
    """
    key = service_key or os.environ.get("SBIZ_SERVICE_KEY")
    params = {
        "serviceKey": key,
        "divId": "adongCd",      # 행정동 기준 [명세서 확인]
        "key": region_code,      # 행정동 코드(인자) — 양덕동은 첫 적용지
        "numOfRows": rows,
        "pageNo": page,
        "type": "json",
    }
    return f"{SBIZ_API_BASE}/storeListInAdmi", params


def request_url(region_code, page=1, rows=SBIZ_DEFAULT_ROWS, service_key=None):
    """디버그·검증용 전체 URL 문자열."""
    url, params = build_admi_request(region_code, page, rows, service_key)
    return f"{url}?{urlencode(params)}"


# ── A-1: 응답 파서 ────────────────────────────────────────────────────────
def _to_float(v):
    """좌표 등 숫자 문자열 → float. 빈값/None → None(조용한 0 대체 금지)."""
    if v is None or v == "":
        return None
    return float(v)


def extract_items(payload: dict) -> list:
    """data.go.kr JSON 봉투에서 점포 레코드 목록을 꺼낸다.

    봉투 구조는 구현마다 조금 다르다([확인필요]) — 흔한 형태를 관대하게 처리:
      {"response": {"body": {"items": {"item": [...]}}}} / {"body": {"items": [...]}} / 평면.
    """
    node = payload.get("response", payload) if isinstance(payload, dict) else {}
    body = node.get("body", node) if isinstance(node, dict) else {}
    items = body.get("items", body.get("item", [])) if isinstance(body, dict) else []
    if isinstance(items, dict):          # {"item": [...]} 또는 {"item": {...}}
        items = items.get("item", [])
    if isinstance(items, dict):          # 단건이 dict 로 온 경우
        items = [items]
    return items or []


def parse_store(rec: dict) -> dict:
    """점포 레코드(원본 필드) → 엔진/DB 친화 정규화 dict. 필드명은 명세서 [확인]."""
    return {
        "bizes_id": rec.get("bizesId"),
        "name": rec.get("bizesNm"),
        "inds_lcls": rec.get("indsLclsNm"),
        "inds_mcls": rec.get("indsMclsNm"),
        "inds_scls": rec.get("indsSclsNm"),
        "inds_scls_cd": rec.get("indsSclsCd"),
        "ksic_cd": rec.get("ksicCd"),
        "adong_cd": rec.get("adongCd"),
        "road_addr": rec.get("rdnmAdr"),
        "lot_addr": rec.get("lnoAdr"),
        "floor": rec.get("flrNo"),
        "lon": _to_float(rec.get("lon")),
        "lat": _to_float(rec.get("lat")),
        "open_dt": rec.get("opbizDt") or None,
        "close_dt": rec.get("clbizDt") or None,   # 채워짐=폐업 / 빔=영업 중 [확인필요]
    }


def parse_stores(payload: dict) -> list:
    """응답 payload → 정규화 점포 목록."""
    return [parse_store(r) for r in extract_items(payload)]


# ── A-2: 영업/폐업 분리 · 경쟁 밀도 집계 ──────────────────────────────────
def split_operating(stores: list) -> dict:
    """close_dt 유무로 영업/폐업 분리. close_dt 빔=영업 중 / 값=폐업 [확인필요].

    영업분 → 업종 구성·경쟁 밀도 입력. 폐업분 → 공실 후보·직전 업종(A-3).
    """
    operating, closed = [], []
    for s in stores:
        (closed if s.get("close_dt") else operating).append(s)
    return {"operating": operating, "closed": closed}


def count_by_industry(stores: list, key: str = "inds_scls") -> dict:
    """업종별 점포 수 집계 = 경쟁 밀도 입력. 기본 소분류 업종명(inds_scls) 기준.

    업종값이 없는(None/빈) 레코드는 세지 않는다(조용히 'None' 버킷 만들지 않기).
    """
    counts: dict = {}
    for s in stores:
        v = s.get(key)
        if v:
            counts[v] = counts.get(v, 0) + 1
    return counts


# ── A-3: 공실 후보 추정 (폐업 − 현재영업 대조) ─────────────────────────────
def _norm_addr(s):
    """주소 정규화(공백 제거). 대조 키 — 빈값은 None."""
    return (s or "").replace(" ", "").strip() or None


def vacancy_candidates(operating: list, closed: list) -> list:
    """폐업 점포 중 '같은 주소에 현재 영업 점포가 없는' 것 = 공실 후보(추정).

    ★ 명세서 원칙: API 는 공실을 직접 주지 않는다. 폐업 기록 + 현재 영업 목록 대조로 '추정'하고,
      실제 확정은 로드뷰·건축물대장(수작업). 그래서 각 후보에 estimated_vacant=True 와 evidence 표기.
    주소 = road_addr(없으면 lot_addr) 정규화. 같은 주소에 영업 점포가 있으면 신규 입점으로 보고 제외.
    """
    occupied = {_norm_addr(s.get("road_addr") or s.get("lot_addr")) for s in operating}
    occupied.discard(None)
    out = []
    for s in closed:
        addr = _norm_addr(s.get("road_addr") or s.get("lot_addr"))
        if addr is None or addr in occupied:
            continue
        out.append({**s, "estimated_vacant": True,
                    "evidence": "폐업기록+현재영업없음(추정 — 로드뷰·건축물대장 확인 필요)"})
    return out


# ── A-4: 업종 247코드 ↔ 시드 6종 매핑 ─────────────────────────────────────
# 정확한 247 소분류 '코드' 매핑은 업종분류(2302) xlsx 확보 후 확정(명세서 §6, [확인필요]).
# 그 전까지는 소분류 업종'명' 키워드로 매핑한다. 코드표가 오면 CODE_TO_SEED 를 채워 우선 적용.
INDUSTRY_KEYWORDS = {
    "cafe":    ["커피", "카페", "다방"],
    "bakery":  ["제과", "제빵", "베이커리", "빵"],
    "bunsik":  ["분식", "김밥", "떡볶이"],
    "book":    ["서점", "책방", "문구"],
    "banchan": ["반찬"],
    "fruit":   ["과일", "청과"],
}
CODE_TO_SEED: dict = {}   # 예: {"I21201": "cafe"} — 247 코드표 확보 후 채움(우선 적용)


def map_to_seed_industry(store: dict):
    """점포 → 우리 시드 업종 id(cafe/bakery/...) 또는 None(미매핑).

    247 코드가 CODE_TO_SEED 에 있으면 코드 우선, 없으면 소분류 업종명 키워드로 매핑.
    """
    code = store.get("inds_scls_cd")
    if code and code in CODE_TO_SEED:
        return CODE_TO_SEED[code]
    name = store.get("inds_scls") or ""
    for iid, kws in INDUSTRY_KEYWORDS.items():
        if any(k in name for k in kws):
            return iid
    return None


def competition_for_seed(operating: list) -> dict:
    """영업 점포를 시드 6종으로 매핑해 {industry_id: 경쟁점 수} 집계.

    반환 형태 = 엔진이 읽는 vacancies.competitors({industry_id: 경쟁점수})와 동일.
    미매핑 업종(우리 6종 밖)은 세지 않는다.
    """
    counts: dict = {}
    for s in operating:
        iid = map_to_seed_industry(s)
        if iid:
            counts[iid] = counts.get(iid, 0) + 1
    return counts


# ── A-5: DB 적재용 공실 row 구성 (출처·region_code·is_seed=0) ──────────────
def build_vacancy_row(candidate: dict, competition: dict, region_code: str,
                      *, vacancy_id=None, area_m2=None, name=None) -> dict:
    """공실 후보(추정) + 경쟁 집계 → vacancies row dict(실데이터 is_seed=0).

    ★ 면적(area_m2)은 소상공인 API 에 없다 → 건축물대장/실측으로 채워 인자로 넘긴다.
      None 이면 적재(insert) 단계에서 빠른 실패 — 가짜 면적을 지어내지 않는다(정직성).
    competitors 는 시드 6종 형태({industry_id: 경쟁점수}). evidence 에 출처·추정 표기.
    vacant_since 는 폐업일(공실 시작 추정). 지역은 region_code 인자만(하드코딩 없음).
    """
    return {
        "id": vacancy_id or candidate.get("bizes_id"),
        "name": name or candidate.get("name") or "(무명 공실)",
        "address": candidate.get("road_addr") or candidate.get("lot_addr"),
        "region_code": region_code,
        "lat": candidate.get("lat"),
        "lng": candidate.get("lon"),
        "area_m2": area_m2,                              # 건축물대장/실측 필요(API 없음)
        "floor": candidate.get("floor"),
        "vacant_since": candidate.get("close_dt"),       # 폐업일 ≈ 공실 시작(추정)
        "prev_industry": candidate.get("inds_scls"),
        "competitors": competition,                      # {industry_id: 경쟁점수}
        "evidence": (candidate.get("evidence", "소상공인 API 추정")
                     + " · 면적=건축물대장/실측"),
        "is_seed": 0,
    }


# ── A-6: 분석 조합(순수) + 실호출(키 필요) ────────────────────────────────
def analyze_stores(stores: list) -> dict:
    """정규화 점포 목록 → 수집 요약(영업/폐업/경쟁/공실후보). 순수 — 실호출과 분리해 검증 가능."""
    sp = split_operating(stores)
    return {
        "operating_count": len(sp["operating"]),
        "closed_count": len(sp["closed"]),
        "competition_raw": count_by_industry(sp["operating"]),      # 소분류명 기준
        "competition_seed": competition_for_seed(sp["operating"]),  # 시드 6종 기준
        "vacancy_candidates": vacancy_candidates(sp["operating"], sp["closed"]),
    }


def fetch_stores(region_code, *, page=1, rows=SBIZ_DEFAULT_ROWS, service_key=None, timeout=20.0):
    """소상공인 API 실호출 → 정규화 점포 목록. 키 없으면 RuntimeError(명확 실패).

    ★ 실호출 검증은 serviceKey 확보 후. 파라미터명·응답 봉투·인코딩/디코딩 키 구분은 [확인필요]
      (Decoding 키 사용 시 params 이중 인코딩 주의 — 첫 호출로 확정).
    키·원문 body 는 예외 메시지에 노출하지 않는다.
    """
    key = service_key or os.environ.get("SBIZ_SERVICE_KEY")
    if not key:
        raise RuntimeError("SBIZ_SERVICE_KEY 없음 — .env 에 키 설정 후 실호출 가능")
    import httpx
    url, params = build_admi_request(region_code, page, rows, key)
    resp = httpx.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return parse_stores(resp.json())
