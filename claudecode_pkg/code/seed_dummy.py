"""
더미 시드 데이터 — 계약(AB공통) 스키마 그대로.
A 데이터가 없어도 B가 3·4·5단계를 완성·검증하기 위한 것. 전부 is_seed=1 / SEED.
※ 값은 발표 승인 전 임시. 시드 업종 6종·면적·창업비용은 1단계에서 팀 승인 대상.
※ 좌표는 양덕동 인근 예시. 실데이터는 7단계(소상공인 API)에서 교체.
"""

# industries: id, name, min_area_m2, max_area_m2, avg_startup_cost_manwon, inds_code, source, is_seed, licenses
INDUSTRIES = [
    {"id": "cafe",    "name": "카페",     "min_area_m2": 30, "max_area_m2": 120, "avg_startup_cost_manwon": 7000, "inds_code": "I2", "source": "SEED", "is_seed": 1, "licenses": "휴게음식점 영업신고"},
    {"id": "bakery",  "name": "베이커리", "min_area_m2": 25, "max_area_m2": 100, "avg_startup_cost_manwon": 6500, "inds_code": "I2", "source": "SEED", "is_seed": 1, "licenses": "즉석판매제조가공업 신고"},
    {"id": "bunsik",  "name": "분식",     "min_area_m2": 20, "max_area_m2": 66,  "avg_startup_cost_manwon": 4500, "inds_code": "I2", "source": "SEED", "is_seed": 1, "licenses": "일반음식점 영업신고"},
    {"id": "book",    "name": "서점문구", "min_area_m2": 33, "max_area_m2": 165, "avg_startup_cost_manwon": 5000, "inds_code": "G2", "source": "SEED", "is_seed": 1, "licenses": "사업자등록(신고 없음)"},
    {"id": "banchan", "name": "반찬가게", "min_area_m2": 16, "max_area_m2": 50,  "avg_startup_cost_manwon": 4000, "inds_code": "G2", "source": "SEED", "is_seed": 1, "licenses": "즉석판매제조가공업 신고"},
    {"id": "fruit",   "name": "과일가게", "min_area_m2": 16, "max_area_m2": 60,  "avg_startup_cost_manwon": 3500, "inds_code": "G2", "source": "SEED", "is_seed": 1, "licenses": "사업자등록(신고 없음)"},
]

# vacancies: id, name, address, region_code, lat, lng, area_m2, floor, vacant_since,
#            prev_industry, competitors(JSON: {industry_id: 경쟁점수}), evidence, is_seed
VACANCIES = [
    {"id": "V-A", "name": "양덕동 A공실", "address": "포항시 북구 양덕로 (예시)",
     "region_code": "4711158000", "lat": 36.0725, "lng": 129.3810,
     "area_m2": 40, "floor": 1, "vacant_since": "2024-03",
     "prev_industry": "의류점",
     "competitors": {"cafe": 12, "bakery": 3, "bunsik": 4, "book": 1, "banchan": 1, "fruit": 2},
     "evidence": "SEED", "is_seed": 1},
    {"id": "V-B", "name": "양덕동 B공실", "address": "포항시 북구 양덕로 (예시)",
     "region_code": "4711158000", "lat": 36.0731, "lng": 129.3822,
     "area_m2": 90, "floor": 1, "vacant_since": "2023-11",
     "prev_industry": "노래방",
     "competitors": {"cafe": 12, "bakery": 3, "bunsik": 4, "book": 0, "banchan": 1, "fruit": 2},
     "evidence": "SEED", "is_seed": 1},
    {"id": "V-C", "name": "양덕동 C공실", "address": "포항시 북구 양덕로 (예시)",
     "region_code": "4711158000", "lat": 36.0740, "lng": 129.3805,
     "area_m2": 22, "floor": 1, "vacant_since": "2022-08",
     "prev_industry": "휴대폰매장",
     "competitors": {"cafe": 12, "bakery": 3, "bunsik": 4, "book": 1, "banchan": 0, "fruit": 1},
     "evidence": "SEED", "is_seed": 1},
    {"id": "V-D", "name": "양덕동 D공실", "address": "포항시 북구 양덕로 (예시)",
     "region_code": "4711158000", "lat": 36.0748, "lng": 129.3831,
     "area_m2": 60, "floor": 2, "vacant_since": "2024-09",
     "prev_industry": "PC방",
     "competitors": {"cafe": 12, "bakery": 3, "bunsik": 4, "book": 1, "banchan": 1, "fruit": 2},
     "evidence": "SEED", "is_seed": 1},
]

# vote_counts: {(vacancy_id, industry_id): 투표수}
# 일부러 여러 공실에서 '카페'가 1위가 되도록 → 4단계 겹침 해소가 실제로 동작하는지 검증.
VOTE_COUNTS = {
    ("V-A", "cafe"): 33, ("V-A", "banchan"): 18, ("V-A", "fruit"): 9,  ("V-A", "bakery"): 6,
    ("V-B", "cafe"): 30, ("V-B", "bakery"): 22, ("V-B", "book"): 12,   ("V-B", "bunsik"): 5,
    ("V-C", "cafe"): 24, ("V-C", "bunsik"): 20, ("V-C", "banchan"): 7, ("V-C", "fruit"): 4,
    ("V-D", "cafe"): 28, ("V-D", "book"): 15,   ("V-D", "banchan"): 9, ("V-D", "bakery"): 8,
}

CAMPAIGN = {"id": "C-yangdeok", "region_code": "4711158000",
            "deadline": "2026-09-30", "coupon_value_won": 3000, "status": "open"}
