"""
시드 데이터: 업종 6종 + 양덕동 공실 3곳 + 동네 투표 4건 (v3 — 동네 투표 전환).
전부 is_seed=1 로 표시하여 실데이터와 구분한다 (시연 정직성 요건).
면적/창업비용/공실 상세/투표는 전부 임시값 -> 나중에 실제 통계·소상공인 API(7단계)로 교체 예정.
"""
import json

from database import get_connection
from routes_vote import snap_to_grid

# 임시값: 실제 통계로 교체 예정. inds_code(247분류)는 매핑표 작업 전이라 빈 값으로 둔다.
# 프런트 CATEGORY_TAXONOMY(6대분류 × 8세부 = 48종)와 이름이 정확히 일치해야 한다
# (프런트가 업종명→id 조회로 투표하므로). 이름 변경 시 프런트 vacancies.js와 함께 고칠 것.
def _ind(name, mn, mx, cost):
    return {"name": name, "min_area_m2": mn, "max_area_m2": mx,
            "avg_startup_cost_manwon": cost, "inds_code": "", "source": "임시값(시드)"}


SEED_INDUSTRIES = [
    # 음식점 (1~8)
    _ind("햄버거", 20, 50, 4000), _ind("치킨", 20, 50, 4500), _ind("피자", 25, 60, 5000), _ind("한식", 30, 80, 5000),
    _ind("분식", 15, 40, 3000), _ind("중식", 30, 70, 5000), _ind("고기·구이", 40, 100, 7000), _ind("양식", 30, 70, 6000),
    # 카페 (9~16)
    _ind("디저트 카페", 20, 50, 4500), _ind("베이커리", 25, 70, 6000), _ind("프랜차이즈 카페", 25, 60, 8000), _ind("개인 카페", 20, 50, 4000),
    _ind("브런치 카페", 30, 70, 5500), _ind("애견 카페", 40, 90, 6000), _ind("테이크아웃 전문", 10, 25, 2500), _ind("차·티 전문점", 20, 50, 4000),
    # 여가시설 (17~24)
    _ind("헬스장", 100, 300, 10000), _ind("필라테스", 60, 150, 7000), _ind("스크린골프", 100, 250, 12000), _ind("PC방", 100, 250, 10000),
    _ind("당구장", 80, 200, 7000), _ind("볼링장", 200, 500, 20000), _ind("만화카페", 60, 150, 5000), _ind("방탈출카페", 60, 150, 6000),
    # 소매 (25~32)
    _ind("편의점", 20, 50, 6000), _ind("옷가게", 20, 60, 4000), _ind("문구점", 20, 50, 3000), _ind("잡화점", 20, 50, 3000),
    _ind("꽃집", 15, 40, 3000), _ind("화장품가게", 20, 50, 5000), _ind("신발가게", 20, 60, 4000), _ind("안경점", 20, 50, 5000),
    # 생활서비스 (33~40)
    _ind("세탁소", 15, 40, 3000), _ind("부동산", 15, 40, 2500), _ind("미용실", 25, 70, 5000), _ind("인쇄소", 20, 50, 3500),
    _ind("네일샵", 15, 40, 3000), _ind("사진관", 25, 60, 4000), _ind("휴대폰매장", 20, 50, 4000), _ind("열쇠·수선", 5, 20, 1500),
    # 의료 (41~48)
    _ind("약국", 20, 50, 5000), _ind("한의원", 60, 150, 8000), _ind("치과", 60, 150, 10000), _ind("동물병원", 60, 150, 8000),
    _ind("피부과", 60, 150, 10000), _ind("정형외과", 100, 250, 15000), _ind("안과", 60, 150, 10000), _ind("산부인과", 100, 250, 15000),
]
# 시드 삽입 순서 = industries.id 순서 (1=햄버거 … 9=디저트 카페 … 25=편의점 … 48=산부인과).
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
    {"region_code": YANGDEOK_REGION_CODE, "industry_id": 9, "voter_id": "seed-voter-1", "voter_name": "김양덕", "lat": 36.0521, "lng": 129.3612},  # 디저트 카페
    {"region_code": YANGDEOK_REGION_CODE, "industry_id": 9, "voter_id": "seed-voter-2", "voter_name": "이동네", "lat": 36.0499, "lng": 129.3579},  # 디저트 카페, 다른 격자
    {"region_code": YANGDEOK_REGION_CODE, "industry_id": 4, "voter_id": "seed-voter-3", "voter_name": "박한식", "lat": 36.0538, "lng": 129.3644},  # 한식
    {"region_code": YANGDEOK_REGION_CODE, "industry_id": 25, "voter_id": "seed-voter-4", "voter_name": "최편의", "lat": 36.0510, "lng": 129.3600},  # 편의점
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
