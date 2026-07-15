"""
설정·상수 한 곳 모음. 캐시(모의) 정책 3건은 2026-07-15 팀 결정으로 확정됐다.
정책이 또 바뀌면 여기 한 곳만 바꾼다(다른 곳에 흩어 쓰지 말 것).
"""

# ── 캐시(모의) 정책 — 2026-07-15 팀 결정 확정 ─────────────────────────────
# 결제·환불은 전부 모의(실PG·사업자등록 없음). 캐시 화폐 단위는 '냥'(엽전 느낌).
# 원장(cash_ledger.delta_won)은 A 스키마 계약대로 '원'으로 저장하고, 냥은 파생 표시 단위다.
CASH_UNIT = "냥"

CASH_POLICY = {
    # ① 교환비율 확정: 1,000원 = 100냥 → 1냥 = 10원.
    #    환불 1건(1,000원 선결제) = 100냥. 원장엔 원(delta_won)으로 기록, 냥은 표시 시 환산.
    "won_per_nyang": 10,                      # 확정 — 1냥 = 10원

    # ② 유효기간(만료): 없음(확정). MVP에 만료 로직을 두지 않는다.
    "expiry_days": None,                      # 확정 — 만료 없음

    # ③ 캐시로 재투표 시: 현금 투표와 동일하게 수요로 집계(확정).
    #    → 캐시 투표도 payment_status='held' 로 vote_counts_view 에 함께 잡힌다.
    "cash_vote_same_as_cash_payment": True,   # 확정 — 동일 취급
}

# ── 투표(모의 결제) 고정값 ────────────────────────────────────────────────
VOTE_AMOUNT_WON = 1000          # 1표 = 1,000원 선결제(서버 고정, 클라이언트가 못 바꿈)
VOTER_NAME_MAX_LEN = 30         # 표시명 길이 제한

# ── 소상공인 상가(상권)정보 API (7단계 · 담당 A) ─────────────────────────────
# 서비스 ID B553077. serviceKey 는 코드에 넣지 않는다 → 환경변수 SBIZ_SERVICE_KEY 에만.
# 지역은 하드코딩 금지 — region_code(행정동 코드)를 인자로 받는다(양덕동은 첫 적용지).
SBIZ_API_BASE = "http://apis.data.go.kr/B553077/api/open/sdsc2"
SBIZ_DEFAULT_ROWS = 100         # 페이지당 건수(대량은 페이징 — 명세서 참조)

# ── v2 격자·투표·냥 (전환 P1) ────────────────────────────────────────────
# GRID_DEG: GPS→200m 격자 반올림 단위(위도 기준 근사). 설계 초기값 — 실데이터 조정 대상.
#   정밀 좌표를 저장하지 않고 격자 셀로만 저장(민감정보 최소화 · 08번 §1).
GRID_DEG = 0.0018

CASH_PER_VOTE_NYANG = 100        # 업종 1개 투표 = 100냥(=1,000원)
CASH_PER_REPORT_NYANG = 50       # 리포트 생성 = 50냥(=500원)

# 다중투표 수요 카운트: A 데이터계층은 배치 투표를 각 1건으로 센다(현행). 1/N 가중은 미구현(향후).
MULTI_VOTE_COUNT_MODE = "full"

# ── 층수 적합 계수 floor_fit (v3 산식) — 곱셈 계수 ────────────────────────
# A의 floor 카테고리('1층'/'2층이상'/'지하') 기준. 미등록/미상 → 1.0(감점 없음).
# 설계 초기값(근거: 국토계획 논문상 1층/상층 공실·매출 차이). 0.7·0.5 는 실데이터 조정 대상.
FLOOR_FIT = {"1층": 1.0, "2층이상": 0.7, "지하": 0.5}

# 거리 감쇠 수요(v3): ≤full_m 가중 1.0 / full~zero 선형 / >zero 제외. 설계 초기값.
DECAY_FULL_M = 500
DECAY_ZERO_M = 800


# ── .env 로더 (stdlib · 외부 의존성 없음) ────────────────────────────────
def load_env_file(path=None):
    """code/.env 를 읽어 os.environ 에 채운다. 이미 설정된 값은 덮지 않는다(setdefault).

    키는 이 파일에서 os.environ 으로만 들어온다 — 코드·로그·저장소에 평문 금지.
    main.py(서버 기동)에서 호출. 테스트/CLI 는 셸 환경변수를 그대로 쓴다.
    """
    import os
    p = path or os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(p):
        return
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
