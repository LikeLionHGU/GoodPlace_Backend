"""7단계(담당 A) 검증 — 소상공인 API 수집. 순수 로직만(실호출은 키 확보 후).
   (실행: python tests/test_ingest.py)"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ingest_api as ig

ok = 0
def check(cond, label):
    global ok
    assert cond, f"❌ {label}"
    print(f"  ✅ {label}"); ok += 1


print("── A-1: 요청 빌더 ──")
url, params = ig.build_admi_request("4711158000", service_key="KEY123")
check(url.endswith("/storeListInAdmi"), "오퍼레이션 = storeListInAdmi")
check(params["divId"] == "adongCd" and params["key"] == "4711158000", "행정동 코드 파라미터(하드코딩 없음)")
check(params["type"] == "json" and params["numOfRows"] == 100 and params["pageNo"] == 1, "type/rows/page 기본값")
check(params["serviceKey"] == "KEY123", "service_key 인자 사용")

# 지역은 인자만 — 다른 코드 넣으면 그대로 반영(경북 확장)
_, p2 = ig.build_admi_request("4711100000", page=2, rows=50, service_key="K")
check(p2["key"] == "4711100000" and p2["pageNo"] == 2 and p2["numOfRows"] == 50, "region_code·page·rows 반영")

# env 폴백
os.environ["SBIZ_SERVICE_KEY"] = "ENVKEY"
_, p3 = ig.build_admi_request("4711158000")
check(p3["serviceKey"] == "ENVKEY", "키 미지정 시 env SBIZ_SERVICE_KEY 폴백")
check("storeListInAdmi" in ig.request_url("4711158000", service_key="K"), "request_url 전체 URL 구성")

print("── A-1: 응답 파서 (합성 데이터) ──")
# 흔한 봉투: response.body.items.item = [...]
payload = {"response": {"body": {"items": {"item": [
    {"bizesId": "B1", "bizesNm": "양덕카페", "indsSclsNm": "커피전문점", "indsSclsCd": "I21201",
     "lon": "129.381", "lat": "36.072", "flrNo": "1", "opbizDt": "20200101", "clbizDt": ""},
    {"bizesId": "B2", "bizesNm": "폐업분식", "indsSclsNm": "분식", "indsSclsCd": "I21301",
     "lon": "129.382", "lat": "36.073", "flrNo": "1", "opbizDt": "20180101", "clbizDt": "20240301"},
]}}}}
stores = ig.parse_stores(payload)
check(len(stores) == 2, "봉투(response.body.items.item)에서 2건 추출")
check(stores[0]["bizes_id"] == "B1" and stores[0]["name"] == "양덕카페", "식별·상호 파싱")
check(stores[0]["lon"] == 129.381 and stores[0]["lat"] == 36.072, "좌표 float 변환")
check(stores[0]["close_dt"] is None, "빈 clbizDt → None(영업 중)")
check(stores[1]["close_dt"] == "20240301", "채워진 clbizDt → 값(폐업)")

# 평면 봉투 + 단건 dict 도 관대하게
flat = {"body": {"items": [{"bizesId": "B3", "bizesNm": "가게3", "lon": "", "lat": ""}]}}
s3 = ig.parse_stores(flat)
check(len(s3) == 1 and s3[0]["bizes_id"] == "B3", "평면 봉투(body.items=list) 처리")
check(s3[0]["lon"] is None, "빈 좌표 → None(조용한 0 대체 안 함)")
check(ig.parse_stores({}) == [], "빈 payload → 빈 목록")

print("── A-2: 영업/폐업 분리 · 경쟁 밀도 집계 ──")
sample = [
    {"bizes_id": "a", "inds_scls": "커피전문점", "close_dt": None},
    {"bizes_id": "b", "inds_scls": "커피전문점", "close_dt": None},
    {"bizes_id": "c", "inds_scls": "분식", "close_dt": None},
    {"bizes_id": "d", "inds_scls": "분식", "close_dt": "20240301"},   # 폐업
    {"bizes_id": "e", "inds_scls": None, "close_dt": None},           # 업종 미상
]
sp = ig.split_operating(sample)
check(len(sp["operating"]) == 4 and len(sp["closed"]) == 1, "영업 4 / 폐업 1 분리")
check(sp["closed"][0]["bizes_id"] == "d", "폐업은 close_dt 채워진 것")

comp = ig.count_by_industry(sp["operating"])
check(comp == {"커피전문점": 2, "분식": 1}, "영업분 업종별 경쟁 밀도 집계")
check("None" not in comp and None not in comp, "업종 미상은 집계 제외")
check(ig.count_by_industry([]) == {}, "빈 목록 → 빈 집계")

print("── A-3: 공실 후보 추정 ──")
operating = [
    {"bizes_id": "op1", "road_addr": "포항시 북구 양덕로 10"},   # 양덕로 10 은 영업 중
]
closed = [
    {"bizes_id": "cl1", "road_addr": "포항시 북구 양덕로 10", "inds_scls": "의류"},   # 같은 주소=신규입점 → 제외
    {"bizes_id": "cl2", "road_addr": "포항시 북구 양덕로 22", "inds_scls": "노래방"},  # 영업 없음 → 후보
    {"bizes_id": "cl3", "road_addr": "", "lot_addr": "양덕동 100", "inds_scls": "PC방"}, # lot_addr 로 후보
]
cands = ig.vacancy_candidates(operating, closed)
ids = [c["bizes_id"] for c in cands]
check(ids == ["cl2", "cl3"], "같은 주소에 영업 있으면 제외, 없으면 후보")
check(all(c["estimated_vacant"] for c in cands), "후보에 estimated_vacant=True")
check("추정" in cands[0]["evidence"], "후보에 '추정' evidence 표기(과대주장 금지)")
check(ig.vacancy_candidates([], []) == [], "빈 입력 → 후보 0")

print("── A-4: 업종 247 ↔ 시드 6종 매핑 ──")
check(ig.map_to_seed_industry({"inds_scls": "커피전문점"}) == "cafe", "커피전문점 → cafe")
check(ig.map_to_seed_industry({"inds_scls": "제과점"}) == "bakery", "제과점 → bakery")
check(ig.map_to_seed_industry({"inds_scls": "분식전문"}) == "bunsik", "분식 → bunsik")
check(ig.map_to_seed_industry({"inds_scls": "일반의류"}) is None, "미매핑 업종 → None")
# 코드표 우선 적용
ig.CODE_TO_SEED["I21999"] = "fruit"
check(ig.map_to_seed_industry({"inds_scls_cd": "I21999", "inds_scls": "커피전문점"}) == "fruit",
      "CODE_TO_SEED 있으면 코드 우선(이름보다)")
del ig.CODE_TO_SEED["I21999"]

op = [{"inds_scls": "커피전문점"}, {"inds_scls": "카페"}, {"inds_scls": "분식"}, {"inds_scls": "약국"}]
comp = ig.competition_for_seed(op)
check(comp == {"cafe": 2, "bunsik": 1}, "시드 6종 competitors 형태로 집계(미매핑 제외)")

print("── A-5: DB 적재용 row 구성 + 적재 ──")
cand = {"bizes_id": "R-1", "name": "옛분식", "road_addr": "포항시 북구 양덕로 22",
        "lat": 36.073, "lon": 129.382, "floor": "1", "close_dt": "20240301",
        "inds_scls": "분식", "estimated_vacant": True, "evidence": "폐업기록+현재영업없음(추정)"}
row = ig.build_vacancy_row(cand, {"cafe": 5, "bunsik": 1}, "4711158000", area_m2=33.0)
check(row["id"] == "R-1" and row["region_code"] == "4711158000", "row id·region_code")
check(row["is_seed"] == 0, "실데이터 is_seed=0")
check(row["lat"] == 36.073 and row["lng"] == 129.382, "좌표 lon→lng 매핑")
check(row["prev_industry"] == "분식" and row["vacant_since"] == "20240301", "직전 업종·공실 시작(폐업일)")
check("추정" in row["evidence"] and "면적" in row["evidence"], "evidence 출처·면적 표기")

import tempfile, db, adapters, json as _json
conn = db.connect(tempfile.mktemp(suffix=".db"))
db.reset_seed(conn)
db.insert_vacancy(conn, row)
got = dict(conn.execute("SELECT * FROM vacancies WHERE id='R-1'").fetchone())
check(got["is_seed"] == 0 and got["region_code"] == "4711158000", "적재 후 조회 — 실데이터 공실")
check(_json.loads(got["competitors"]) == {"cafe": 5, "bunsik": 1}, "competitors JSON 저장·복원")
# 어댑터가 정상 파싱하는지(엔진 호환)
parsed = adapters.vacancy_from_row(got)
check(parsed["competitors"] == {"cafe": 5, "bunsik": 1}, "어댑터가 실데이터 공실 파싱(엔진 호환)")

# 면적 없으면 빠른 실패
try:
    db.insert_vacancy(conn, ig.build_vacancy_row(cand, {}, "4711158000", vacancy_id="R-2"))
    check(False, "면적 없음 → 빠른 실패(예외)")
except ValueError:
    check(True, "면적 없음 → 빠른 실패(ValueError, 가짜 면적 금지)")
conn.close()

print("── A-6: 분석 조합(순수) + 실호출/라우터(키 없음 처리) ──")
stores = [
    {"bizes_id": "s1", "inds_scls": "커피전문점", "road_addr": "양덕로 1", "close_dt": None},
    {"bizes_id": "s2", "inds_scls": "커피전문점", "road_addr": "양덕로 2", "close_dt": None},
    {"bizes_id": "s3", "inds_scls": "노래방", "road_addr": "양덕로 9", "close_dt": "20240101"},  # 폐업·영업없음
]
summary = ig.analyze_stores(stores)
check(summary["operating_count"] == 2 and summary["closed_count"] == 1, "analyze: 영업2/폐업1")
check(summary["competition_seed"] == {"cafe": 2}, "analyze: 시드 경쟁 집계")
check(len(summary["vacancy_candidates"]) == 1, "analyze: 공실 후보 1")

# 키 없으면 실호출 RuntimeError (명확 실패, 키 노출 없음)
os.environ.pop("SBIZ_SERVICE_KEY", None)
try:
    ig.fetch_stores("4711158000")
    check(False, "키 없음 → RuntimeError")
except RuntimeError as e:
    check("SBIZ_SERVICE_KEY" in str(e), "키 없음 → RuntimeError(안내 메시지)")

# 라우터: 키 없으면 503
import tempfile as _tf
os.environ["MYDANG_DB"] = _tf.mktemp(suffix=".db")
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as c:
    r = c.get("/admin/ingest/preview", params={"region_code": "4711158000"})
    check(r.status_code == 503, "키 없을 때 /admin/ingest/preview → 503(안내)")

print(f"\n전부 통과 ✅  ({ok}개)")
