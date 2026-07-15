"""
시드 데이터: 업종 6종 + 육거리 공실 6곳 + 동네 투표 435건 (v3 — 동네 투표 전환).
전부 is_seed=1 로 표시하여 실데이터와 구분한다 (시연 정직성 요건).
면적/창업비용/공실 상세/투표는 전부 임시값 -> 나중에 실제 통계·소상공인 API(7단계)로 교체 예정.
"""
import json
import random

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

# region_code: 육거리 임시 코드. 실제 행정표준코드 확정 전까지 사용하는 placeholder (7단계에서 확정 예정).
# 상수명(YANGDEOK)은 내부 식별자일 뿐 화면에 노출되지 않으므로 그대로 두고, 노출되는
# 동네 이름은 프론트 REGION_DISPLAY_NAMES에서 "육거리"로 매핑한다.
YANGDEOK_REGION_CODE = "47111-YANGDEOK-TEMP"

# 좌표·면적·층·이전업종·중개사 등록 필드 전부 임시값 (육거리 근처 좌표만 그럴듯하게 배치).
SEED_VACANCIES = [
    {
        "name": "육거리 1번 공실",
        "address": "경북 포항시 북구 육거리 123-4",
        "region_code": YANGDEOK_REGION_CODE,
        "lat": 36.0521,
        "lng": 129.3612,
        "area_m2": 33,
        "floor": "1층",
        "vacant_since": "2026-04-01",
        "prev_industry": "편의점",
        "competitors": json.dumps({"카페": 2, "분식": 1, "반찬": 1}),
        "evidence": "임시값 - 7단계 소상공인 API 수집 전까지 placeholder",
        "building_use": "근린생활시설(임시값)",
        "facilities": json.dumps({
            "상하수도": {"가능": True}, "환기후드": {"가능": False}, "가스": {"가능": False},
            "화장실": {"가능": True, "비고": "내부 단독"},
            "주차": {"가능": False, "비고": ""},
        }),
        "rent_conditions": "보증금 1000/월세 60만원(임시값)",
        "premium": "무권리금(임시값)",
    },
    {
        "name": "육거리 2번 공실",
        "address": "경북 포항시 북구 육거리 456-7",
        "region_code": YANGDEOK_REGION_CODE,
        "lat": 36.0498,
        "lng": 129.3578,
        "area_m2": 45,
        "floor": "1층",
        "vacant_since": "2026-02-15",
        "prev_industry": "치킨집",
        "competitors": json.dumps({"카페": 1, "베이커리": 1, "반찬": 2}),
        "evidence": "임시값 - 7단계 소상공인 API 수집 전까지 placeholder",
        "building_use": "근린생활시설(임시값)",
        "facilities": json.dumps({
            "상하수도": {"가능": True}, "환기후드": {"가능": True}, "가스": {"가능": True},
            "화장실": {"가능": True, "비고": "내부 단독"},
            "주차": {"가능": True, "비고": "건물 부설 2대"},
        }),
        "rent_conditions": "보증금 2000/월세 120만원(임시값)",
        "premium": "권리금 3000만원(임시값)",
    },
    {
        "name": "육거리 3번 공실",
        "address": "경북 포항시 북구 육거리 789-1",
        "region_code": YANGDEOK_REGION_CODE,
        "lat": 36.0537,
        "lng": 129.3645,
        "area_m2": 22,
        "floor": "2층이상",
        "vacant_since": "2026-05-20",
        "prev_industry": "미용실",
        "competitors": json.dumps({"분식": 2, "서점문구": 1}),
        "evidence": "임시값 - 7단계 소상공인 API 수집 전까지 placeholder",
        "building_use": "근린생활시설(임시값)",
        "facilities": json.dumps({
            "상하수도": {"가능": True}, "환기후드": {"가능": False}, "가스": {"가능": False},
            "화장실": {"가능": True, "비고": "공용(건물 공동)"},
            "주차": {"가능": False, "비고": ""},
        }),
        "rent_conditions": "보증금 500/월세 40만원(임시값)",
        "premium": "문의(임시값)",
    },
    # 아래 3곳은 리포트 A/B/C 후보가 서로 다른 위치로 나오도록 추가한 것(공실 3곳뿐이면
    # 업종별 추천이 같은 건물로 겹치는 경우가 많았음). 동 전체 스케일로 서로 떨어뜨려 배치.
    {
        "name": "육거리 4번 공실",
        "address": "경북 포항시 북구 육거리 234-5",
        "region_code": YANGDEOK_REGION_CODE,
        "lat": 36.0455,
        "lng": 129.3660,
        "area_m2": 28,
        "floor": "1층",
        "vacant_since": "2026-03-10",
        "prev_industry": "서점",
        "competitors": json.dumps({"카페": 1, "베이커리": 2, "과일": 1}),
        "evidence": "임시값 - 7단계 소상공인 API 수집 전까지 placeholder",
        "building_use": "근린생활시설(임시값)",
        "facilities": json.dumps({
            "상하수도": {"가능": True}, "환기후드": {"가능": False}, "가스": {"가능": False},
            "화장실": {"가능": True, "비고": "내부 단독"},
            "주차": {"가능": True, "비고": "노상 1대"},
        }),
        "rent_conditions": "보증금 800/월세 50만원(임시값)",
        "premium": "무권리금(임시값)",
    },
    {
        "name": "육거리 5번 공실",
        "address": "경북 포항시 북구 육거리 567-8",
        "region_code": YANGDEOK_REGION_CODE,
        "lat": 36.0475,
        "lng": 129.3700,
        "area_m2": 60,
        "floor": "1층",
        "vacant_since": "2026-01-20",
        "prev_industry": "빵집",
        "competitors": json.dumps({"카페": 3, "베이커리": 1}),
        "evidence": "임시값 - 7단계 소상공인 API 수집 전까지 placeholder",
        "building_use": "근린생활시설(임시값)",
        "facilities": json.dumps({
            "상하수도": {"가능": True}, "환기후드": {"가능": True}, "가스": {"가능": True},
            "화장실": {"가능": True, "비고": "내부 단독"},
            "주차": {"가능": True, "비고": "건물 부설 3대"},
        }),
        "rent_conditions": "보증금 1500/월세 90만원(임시값)",
        "premium": "권리금 1000만원(임시값)",
    },
    {
        "name": "육거리 6번 공실",
        "address": "경북 포항시 북구 육거리 890-2",
        "region_code": YANGDEOK_REGION_CODE,
        "lat": 36.0555,
        "lng": 129.3560,
        "area_m2": 18,
        "floor": "1층",
        "vacant_since": "2026-05-01",
        "prev_industry": "분식집",
        "competitors": json.dumps({"분식": 1, "과일": 2}),
        "evidence": "임시값 - 7단계 소상공인 API 수집 전까지 placeholder",
        "building_use": "근린생활시설(임시값)",
        "facilities": json.dumps({
            "상하수도": {"가능": True}, "환기후드": {"가능": False}, "가스": {"가능": False},
            "화장실": {"가능": False, "비고": ""},
            "주차": {"가능": False, "비고": ""},
        }),
        "rent_conditions": "보증금 300/월세 30만원(임시값)",
        "premium": "무권리금(임시값)",
    },
]

# 동네 투표 시드 (v3 신규). industry_id는 위 SEED_INDUSTRIES 삽입 순서를 그대로 참조한다.
# 업종마다 투표를 특정 공실 근처에 몰아서, 리포트 A/B/C가 서로 다른 공실로 나뉘도록 설계했다
# (카페→1번, 분식→6번, 베이커리→5번, 과일→4번 이 각자의 1순위가 되도록 그 공실 근처에 집중 배치).
# 총 투표 인원이 400~500명 규모여야 "주민 수요가 실제로 있다"는 리포트가 설득력 있어 보이므로,
# 업종별로 표를 늘려 총합 435표로 맞췄다(시드값 고정 - 서버 재기동해도 같은 배치가 나오게).
_SEED_RNG = random.Random(42)

_VOTER_NAME_POOL = [
    "김양덕", "이동네", "정커피", "한라떼", "박분식", "윤떡볶", "장튀김", "최과일", "임식빵",
    "강사과", "조참외", "서문구", "나반찬", "오떡집", "윤빵순", "김붕어", "이만두", "박호떡",
    "정찐빵", "한크림", "서화과", "나채소", "오과채", "윤딸기", "김수박", "이참외", "박포도",
    "정귤", "한바나나", "서서점", "나잡지", "오만화", "윤동화", "김소설", "이시집", "박연필",
    "정공책", "한스티커", "서밑반찬", "나김치", "오나물", "윤젓갈", "김장아찌", "이깍두기", "박콩나물",
    "정메밀", "한냉면", "서라면", "나칼국수", "오우동", "윤짜장", "김짬뽕", "이돈까스", "박카레",
]


def _cluster_votes(industry_id: int, count: int, center_lat: float, center_lng: float, start_idx: int) -> list[dict]:
    """center 근처(±0.0009도 ≈ 100m 지터)에 count명을 몰아서 투표하는 시드 행 생성."""
    votes = []
    for i in range(count):
        idx = start_idx + i
        votes.append({
            "region_code": YANGDEOK_REGION_CODE,
            "industry_id": industry_id,
            "voter_id": f"seed-voter-{idx}",
            "voter_name": _VOTER_NAME_POOL[(idx - 1) % len(_VOTER_NAME_POOL)],
            "lat": center_lat + _SEED_RNG.uniform(-0.0009, 0.0009),
            "lng": center_lng + _SEED_RNG.uniform(-0.0009, 0.0009),
        })
    return votes


SEED_VOTES = (
    _cluster_votes(1, 140, 36.0521, 129.3612, 1)     # 카페(1) - 육거리 1번 공실 근처 → 카페 수요 1위
    + _cluster_votes(3, 110, 36.0555, 129.3560, 141)  # 분식(3) - 육거리 6번 공실 근처
    + _cluster_votes(2, 85, 36.0475, 129.3700, 251)   # 베이커리(2) - 육거리 5번 공실 근처
    + _cluster_votes(6, 50, 36.0455, 129.3660, 336)   # 과일(6) - 육거리 4번 공실 근처
    + _cluster_votes(4, 25, 36.0537, 129.3645, 386)   # 서점문구(4) - 육거리 3번 공실 근처
    + _cluster_votes(5, 25, 36.0498, 129.3578, 411)   # 반찬(5) - 육거리 2번 공실 근처
)


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
