"""
시드 데이터: 업종 6종 + 양덕동 공실 3곳 + 동네 투표 4건 (v3 — 동네 투표 전환).
전부 is_seed=1 로 표시하여 실데이터와 구분한다 (시연 정직성 요건).
면적/창업비용/공실 상세/투표는 전부 임시값 -> 나중에 실제 통계·소상공인 API(7단계)로 교체 예정.
"""
import json

from database import get_connection
from routes_vote import snap_to_grid

# 임시값: 실제 통계로 교체 예정. inds_code(247분류)는 매핑표 작업 전이라 빈 값으로 둔다.
SEED_INDUSTRIES = [
    {
        "name": "카페",
        "min_area_m2": 20,
        "max_area_m2": 60,
        "avg_startup_cost_manwon": 5000,
        "inds_code": "",  # TODO: 247분류 매핑 필요 (소상공인_상가정보_API_명세서 §6 참고)
        "source": "임시값(시드)",
    },
    {
        "name": "베이커리",
        "min_area_m2": 25,
        "max_area_m2": 70,
        "avg_startup_cost_manwon": 6000,
        "inds_code": "",
        "source": "임시값(시드)",
    },
    {
        "name": "분식",
        "min_area_m2": 15,
        "max_area_m2": 40,
        "avg_startup_cost_manwon": 3000,
        "inds_code": "",
        "source": "임시값(시드)",
    },
    {
        "name": "서점문구",
        "min_area_m2": 20,
        "max_area_m2": 50,
        "avg_startup_cost_manwon": 4000,
        "inds_code": "",
        "source": "임시값(시드)",
    },
    {
        "name": "반찬",
        "min_area_m2": 10,
        "max_area_m2": 30,
        "avg_startup_cost_manwon": 2500,
        "inds_code": "",
        "source": "임시값(시드)",
    },
    {
        "name": "과일",
        "min_area_m2": 10,
        "max_area_m2": 30,
        "avg_startup_cost_manwon": 2000,
        "inds_code": "",
        "source": "임시값(시드)",
    },
]
# 시드 삽입 순서 = industries.id 순서 (1=카페, 2=베이커리, 3=분식, 4=서점문구, 5=반찬, 6=과일).
# 아래 SEED_VOTES가 이 순서에 의존하므로 순서를 바꾸지 말 것.

# region_code: 양덕동 임시 코드. 실제 행정표준코드 확정 전까지 사용하는 placeholder (7단계에서 확정 예정).
YANGDEOK_REGION_CODE = "47111-YANGDEOK-TEMP"

# 좌표·면적·층·이전업종·중개사 등록 필드 전부 임시값 (양덕동 근처 좌표만 그럴듯하게 배치).
SEED_VACANCIES = [
    {
        "name": "양덕 1번 공실(임시)",
        "address": "경북 포항시 북구 양덕동 123-4 (임시주소)",
        "region_code": YANGDEOK_REGION_CODE,
        "lat": 36.0521,
        "lng": 129.3612,
        "area_m2": 33,
        "floor": "1층",
        "vacant_since": "2026-04-01",
        "prev_industry": "편의점",
        "competitors": "{}",
        "evidence": "임시값 - 7단계 소상공인 API 수집 전까지 placeholder",
        "building_use": "근린생활시설(임시값)",
        "facilities": json.dumps(
            {"상하수도": True, "환기후드": False, "가스": False, "화장실": True, "주차": False}
        ),
        "rent_conditions": "보증금 1000/월세 60만원(임시값)",
        "premium": "무권리금(임시값)",
    },
    {
        "name": "양덕 2번 공실(임시)",
        "address": "경북 포항시 북구 양덕동 456-7 (임시주소)",
        "region_code": YANGDEOK_REGION_CODE,
        "lat": 36.0498,
        "lng": 129.3578,
        "area_m2": 45,
        "floor": "1층",
        "vacant_since": "2026-02-15",
        "prev_industry": "치킨집",
        "competitors": "{}",
        "evidence": "임시값 - 7단계 소상공인 API 수집 전까지 placeholder",
        "building_use": "근린생활시설(임시값)",
        "facilities": json.dumps(
            {"상하수도": True, "환기후드": True, "가스": True, "화장실": True, "주차": True}
        ),
        "rent_conditions": "보증금 2000/월세 120만원(임시값)",
        "premium": "권리금 3000만원(임시값)",
    },
    {
        "name": "양덕 3번 공실(임시)",
        "address": "경북 포항시 북구 양덕동 789-1 (임시주소)",
        "region_code": YANGDEOK_REGION_CODE,
        "lat": 36.0537,
        "lng": 129.3645,
        "area_m2": 22,
        "floor": "2층이상",
        "vacant_since": "2026-05-20",
        "prev_industry": "미용실",
        "competitors": "{}",
        "evidence": "임시값 - 7단계 소상공인 API 수집 전까지 placeholder",
        "building_use": "근린생활시설(임시값)",
        "facilities": json.dumps(
            {"상하수도": True, "환기후드": False, "가스": False, "화장실": True, "주차": False}
        ),
        "rent_conditions": "보증금 500/월세 40만원(임시값)",
        "premium": "문의(임시값)",
    },
]

# 동네 투표 시드 (v3 신규). industry_id는 위 SEED_INDUSTRIES 삽입 순서를 그대로 참조한다.
# 좌표는 공실 근처에서 조금씩 흩어 놓아 격자(voter_grid)가 최소 2개 이상 나뉘도록 했다.
SEED_VOTES = [
    {"region_code": YANGDEOK_REGION_CODE, "industry_id": 1, "voter_id": "seed-voter-1", "voter_name": "김양덕", "lat": 36.0521, "lng": 129.3612},  # 카페
    {"region_code": YANGDEOK_REGION_CODE, "industry_id": 1, "voter_id": "seed-voter-2", "voter_name": "이동네", "lat": 36.0499, "lng": 129.3579},  # 카페, 다른 격자
    {"region_code": YANGDEOK_REGION_CODE, "industry_id": 3, "voter_id": "seed-voter-3", "voter_name": "박분식", "lat": 36.0538, "lng": 129.3644},  # 분식
    {"region_code": YANGDEOK_REGION_CODE, "industry_id": 6, "voter_id": "seed-voter-4", "voter_name": "최과일", "lat": 36.0510, "lng": 129.3600},  # 과일
]


def insert_seed() -> None:
    """이미 시드가 있으면 재삽입하지 않는다 (idempotent)."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT COUNT(*) AS c FROM industries WHERE is_seed = 1"
        ).fetchone()["c"]
        if existing == 0:
            conn.executemany(
                """
                INSERT INTO industries
                    (name, min_area_m2, max_area_m2, avg_startup_cost_manwon, inds_code, source, is_seed)
                VALUES (:name, :min_area_m2, :max_area_m2, :avg_startup_cost_manwon, :inds_code, :source, 1)
                """,
                SEED_INDUSTRIES,
            )

        existing_vac = conn.execute(
            "SELECT COUNT(*) AS c FROM vacancies WHERE is_seed = 1"
        ).fetchone()["c"]
        if existing_vac == 0:
            conn.executemany(
                """
                INSERT INTO vacancies
                    (name, address, region_code, lat, lng, area_m2, floor,
                     vacant_since, prev_industry, competitors, evidence,
                     building_use, facilities, rent_conditions, premium, is_seed)
                VALUES (:name, :address, :region_code, :lat, :lng, :area_m2, :floor,
                        :vacant_since, :prev_industry, :competitors, :evidence,
                        :building_use, :facilities, :rent_conditions, :premium, 1)
                """,
                SEED_VACANCIES,
            )

        existing_votes = conn.execute(
            "SELECT COUNT(*) AS c FROM votes WHERE is_seed = 1"
        ).fetchone()["c"]
        if existing_votes == 0:
            rows = [
                {
                    "region_code": v["region_code"],
                    "industry_id": v["industry_id"],
                    "voter_id": v["voter_id"],
                    "voter_name": v["voter_name"],
                    "voter_grid": snap_to_grid(v["lat"], v["lng"]),
                }
                for v in SEED_VOTES
            ]
            conn.executemany(
                """
                INSERT INTO votes
                    (region_code, industry_id, voter_id, voter_name, voter_grid, amount_won, payment_status, is_seed)
                VALUES (:region_code, :industry_id, :voter_id, :voter_name, :voter_grid, 1000, 'held', 1)
                """,
                rows,
            )

        conn.commit()
    finally:
        conn.close()
