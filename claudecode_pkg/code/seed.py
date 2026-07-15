"""
시드 데이터: 업종 6대분류×8세부(48종) + 양덕동 공실 3곳 + 동네 투표 4건 (v3 — 동네 투표 전환).
전부 is_seed=1 로 표시하여 실데이터와 구분한다 (시연 정직성 요건).
면적/창업비용/공실 상세/투표는 전부 임시값 -> 나중에 실제 통계·소상공인 API(7단계)로 교체 예정.

48종 이름은 GoodPlace_Front(js/vacancies.js CATEGORY_TAXONOMY)의 헤더 "투표하기" 패널이 쓰는
세부업종명과 정확히 일치해야 한다 - 프론트는 이 이름으로 industry_id를 조회한다(대분류는 프론트에만
있고 이 스키마엔 카테고리 컬럼이 없어 이름만 맞추면 된다).
"""
import json

from database import get_connection
from routes_vote import snap_to_grid

# 임시값: 실제 통계로 교체 예정. inds_code(247분류)는 매핑표 작업 전이라 빈 값으로 둔다.
SEED_INDUSTRIES = [
    # 음식점 (1~8)
    {"name": "햄버거", "min_area_m2": 15, "max_area_m2": 40, "avg_startup_cost_manwon": 4000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "치킨", "min_area_m2": 15, "max_area_m2": 35, "avg_startup_cost_manwon": 3500, "inds_code": "", "source": "임시값(시드)"},
    {"name": "피자", "min_area_m2": 15, "max_area_m2": 40, "avg_startup_cost_manwon": 4000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "한식", "min_area_m2": 20, "max_area_m2": 60, "avg_startup_cost_manwon": 5000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "분식", "min_area_m2": 15, "max_area_m2": 40, "avg_startup_cost_manwon": 3000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "중식", "min_area_m2": 20, "max_area_m2": 50, "avg_startup_cost_manwon": 4500, "inds_code": "", "source": "임시값(시드)"},
    {"name": "고기·구이", "min_area_m2": 25, "max_area_m2": 70, "avg_startup_cost_manwon": 6500, "inds_code": "", "source": "임시값(시드)"},
    {"name": "양식", "min_area_m2": 20, "max_area_m2": 60, "avg_startup_cost_manwon": 5500, "inds_code": "", "source": "임시값(시드)"},
    # 카페 (9~16)
    {"name": "디저트 카페", "min_area_m2": 20, "max_area_m2": 60, "avg_startup_cost_manwon": 5000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "베이커리", "min_area_m2": 25, "max_area_m2": 70, "avg_startup_cost_manwon": 6000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "프랜차이즈 카페", "min_area_m2": 25, "max_area_m2": 70, "avg_startup_cost_manwon": 6500, "inds_code": "", "source": "임시값(시드)"},
    {"name": "개인 카페", "min_area_m2": 15, "max_area_m2": 45, "avg_startup_cost_manwon": 4500, "inds_code": "", "source": "임시값(시드)"},
    {"name": "브런치 카페", "min_area_m2": 25, "max_area_m2": 65, "avg_startup_cost_manwon": 5500, "inds_code": "", "source": "임시값(시드)"},
    {"name": "애견 카페", "min_area_m2": 30, "max_area_m2": 80, "avg_startup_cost_manwon": 6000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "테이크아웃 전문", "min_area_m2": 10, "max_area_m2": 25, "avg_startup_cost_manwon": 3000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "차·티 전문점", "min_area_m2": 15, "max_area_m2": 40, "avg_startup_cost_manwon": 4000, "inds_code": "", "source": "임시값(시드)"},
    # 여가시설 (17~24)
    {"name": "헬스장", "min_area_m2": 60, "max_area_m2": 200, "avg_startup_cost_manwon": 10000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "필라테스", "min_area_m2": 30, "max_area_m2": 80, "avg_startup_cost_manwon": 6000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "스크린골프", "min_area_m2": 50, "max_area_m2": 120, "avg_startup_cost_manwon": 15000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "PC방", "min_area_m2": 60, "max_area_m2": 200, "avg_startup_cost_manwon": 12000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "당구장", "min_area_m2": 40, "max_area_m2": 100, "avg_startup_cost_manwon": 8000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "볼링장", "min_area_m2": 150, "max_area_m2": 400, "avg_startup_cost_manwon": 30000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "만화카페", "min_area_m2": 40, "max_area_m2": 100, "avg_startup_cost_manwon": 7000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "방탈출카페", "min_area_m2": 30, "max_area_m2": 80, "avg_startup_cost_manwon": 6500, "inds_code": "", "source": "임시값(시드)"},
    # 소매 (25~32)
    {"name": "편의점", "min_area_m2": 20, "max_area_m2": 50, "avg_startup_cost_manwon": 8000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "옷가게", "min_area_m2": 15, "max_area_m2": 45, "avg_startup_cost_manwon": 4000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "문구점", "min_area_m2": 15, "max_area_m2": 40, "avg_startup_cost_manwon": 3000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "잡화점", "min_area_m2": 15, "max_area_m2": 40, "avg_startup_cost_manwon": 3000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "꽃집", "min_area_m2": 10, "max_area_m2": 25, "avg_startup_cost_manwon": 2500, "inds_code": "", "source": "임시값(시드)"},
    {"name": "화장품가게", "min_area_m2": 15, "max_area_m2": 35, "avg_startup_cost_manwon": 3500, "inds_code": "", "source": "임시값(시드)"},
    {"name": "신발가게", "min_area_m2": 15, "max_area_m2": 40, "avg_startup_cost_manwon": 3500, "inds_code": "", "source": "임시값(시드)"},
    {"name": "안경점", "min_area_m2": 10, "max_area_m2": 30, "avg_startup_cost_manwon": 4000, "inds_code": "", "source": "임시값(시드)"},
    # 생활서비스 (33~40)
    {"name": "세탁소", "min_area_m2": 10, "max_area_m2": 30, "avg_startup_cost_manwon": 3000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "부동산", "min_area_m2": 10, "max_area_m2": 25, "avg_startup_cost_manwon": 2000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "미용실", "min_area_m2": 15, "max_area_m2": 40, "avg_startup_cost_manwon": 4500, "inds_code": "", "source": "임시값(시드)"},
    {"name": "인쇄소", "min_area_m2": 10, "max_area_m2": 30, "avg_startup_cost_manwon": 3000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "네일샵", "min_area_m2": 10, "max_area_m2": 25, "avg_startup_cost_manwon": 2500, "inds_code": "", "source": "임시값(시드)"},
    {"name": "사진관", "min_area_m2": 15, "max_area_m2": 35, "avg_startup_cost_manwon": 3500, "inds_code": "", "source": "임시값(시드)"},
    {"name": "휴대폰매장", "min_area_m2": 10, "max_area_m2": 30, "avg_startup_cost_manwon": 4000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "열쇠·수선", "min_area_m2": 5, "max_area_m2": 15, "avg_startup_cost_manwon": 1500, "inds_code": "", "source": "임시값(시드)"},
    # 의료 (41~48)
    {"name": "약국", "min_area_m2": 20, "max_area_m2": 50, "avg_startup_cost_manwon": 8000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "한의원", "min_area_m2": 30, "max_area_m2": 80, "avg_startup_cost_manwon": 12000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "치과", "min_area_m2": 40, "max_area_m2": 100, "avg_startup_cost_manwon": 20000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "동물병원", "min_area_m2": 30, "max_area_m2": 80, "avg_startup_cost_manwon": 15000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "피부과", "min_area_m2": 30, "max_area_m2": 80, "avg_startup_cost_manwon": 18000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "정형외과", "min_area_m2": 40, "max_area_m2": 100, "avg_startup_cost_manwon": 20000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "안과", "min_area_m2": 40, "max_area_m2": 100, "avg_startup_cost_manwon": 20000, "inds_code": "", "source": "임시값(시드)"},
    {"name": "산부인과", "min_area_m2": 50, "max_area_m2": 120, "avg_startup_cost_manwon": 25000, "inds_code": "", "source": "임시값(시드)"},
]
# 시드 삽입 순서 = industries.id 순서 (1~8=음식점, 9~16=카페, 17~24=여가시설,
# 25~32=소매, 33~40=생활서비스, 41~48=의료). 아래 SEED_VOTES가 이 순서에 의존하므로 순서를 바꾸지 말 것.

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

# 동네 투표 시드 (v3 신규). industry_id는 위 SEED_INDUSTRIES 삽입 순서를 그대로 참조한다
# (1=햄버거, 5=분식, 29=꽃집 - 48종 확장 전엔 각각 카페/분식/과일이었던 자리).
# id=1에 투표를 남겨두는 건 우연이 아니다 - tests/test_report_route_v3.py가 inds[0](=id 1)에
# 이미 시드 투표가 있다고 가정하고 그 값으로 리포트 수치를 검증한다.
# 좌표는 공실 근처에서 조금씩 흩어 놓아 격자(voter_grid)가 최소 2개 이상 나뉘도록 했다.
SEED_VOTES = [
    {"region_code": YANGDEOK_REGION_CODE, "industry_id": 1, "voter_id": "seed-voter-1", "voter_name": "김양덕", "lat": 36.0521, "lng": 129.3612},  # 햄버거
    {"region_code": YANGDEOK_REGION_CODE, "industry_id": 1, "voter_id": "seed-voter-2", "voter_name": "이동네", "lat": 36.0499, "lng": 129.3579},  # 햄버거, 다른 격자
    {"region_code": YANGDEOK_REGION_CODE, "industry_id": 5, "voter_id": "seed-voter-3", "voter_name": "박분식", "lat": 36.0538, "lng": 129.3644},  # 분식
    {"region_code": YANGDEOK_REGION_CODE, "industry_id": 29, "voter_id": "seed-voter-4", "voter_name": "최과일", "lat": 36.0510, "lng": 129.3600},  # 꽃집
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
