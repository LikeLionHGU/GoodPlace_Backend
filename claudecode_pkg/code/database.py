"""
DB 연결 및 스키마 정의 (v3 — 동네 투표 전환).
스키마는 AB공통_분담과통합계약.md / 08_리포트_공실등록_확정명세.md 기준.

v3 변경 요지:
- votes: vacancy_id 제거. region_code(동네)+voter_grid(200m 격자)+voter_name 추가.
  주민은 이제 '공실'이 아니라 '동네+업종'에 투표한다.
- vacancies: floor를 카테고리(1층/2층이상/지하)로 변경, building_use·facilities·
  rent_conditions·premium 추가 (중개사 등록 필드, 출처 태그 '중개사등록').
- placements: 신규 (성사된 창업 기록 — 로직은 6단계, 여기서는 스키마만 선생성).

마이그레이션 방식: votes 컬럼 제거·floor 타입 변경 등 ALTER TABLE로 안전하게 이관하기 힘든
변경이 많아, schema_meta에 버전을 기록해두고 버전이 낮으면 전체 재생성한다
(AB공통 문서의 "컬럼 추가 시 마이그레이션 절차 명시" 요구 충족). 현재 DB는 시드/테스트
데이터만 있으므로 재생성해도 데이터 손실 우려가 없다.
"""
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "meongdang.db"
SCHEMA_VERSION = 4


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS industries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    min_area_m2 REAL NOT NULL,
    max_area_m2 REAL NOT NULL,
    avg_startup_cost_manwon REAL NOT NULL,
    inds_code TEXT,               -- 247분류 매핑 코드. 매핑표 작업 전이라 임시로 빈 값/임시값
    source TEXT,
    is_seed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    region_code TEXT NOT NULL,    -- 행정동/시군구 코드. 경북 확장 키 (하드코딩 금지, 데이터로 관리)
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    area_m2 REAL NOT NULL,
    floor TEXT,                   -- v3: 카테고리형 '1층'/'2층이상'/'지하' (출처: 중개사등록)
    vacant_since TEXT,
    prev_industry TEXT,
    competitors TEXT NOT NULL DEFAULT '{}',  -- JSON 문자열: 업종별 경쟁점 수
    evidence TEXT,
    building_use TEXT,            -- v3 신규: 건물 용도 (출처: 중개사등록)
    facilities TEXT NOT NULL DEFAULT '{}',  -- v3 신규: JSON {상하수도/환기후드/가스/화장실/주차: bool} (출처: 중개사등록)
    rent_conditions TEXT,         -- v3 신규: 임대조건 텍스트 (출처: 중개사등록)
    premium TEXT,                 -- v3 신규: 권리금 유무/값. 없으면 '문의' (출처: 중개사등록)
    is_seed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region_code TEXT NOT NULL,     -- v3: 동네(행정동) 키 — 공실이 아니라 동네+업종에 투표
    industry_id INTEGER NOT NULL REFERENCES industries(id),
    voter_id TEXT NOT NULL,
    voter_name TEXT,               -- 표시명 ≤30자, 고객 명단용
    voter_grid TEXT NOT NULL,      -- v3: 투표 시점 GPS를 200m 격자로 스냅한 좌표 문자열. 정밀 원좌표는 저장 안 함
    amount_won INTEGER NOT NULL DEFAULT 1000,
    payment_status TEXT NOT NULL DEFAULT 'held',  -- held/settled/refunded/cash_credited/free
                                                    -- free = 결제 자체가 없는 진짜 무료 투표(캠페인 환불 대상 아님, amount_won=0)
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_seed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cash_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    voter_id TEXT NOT NULL,
    delta_won INTEGER NOT NULL,      -- +적립/-사용. 화면 표기는 '냥'(10원=1냥), 저장은 원 그대로 (won_to_nyang/nyang_to_won 참고)
    reason TEXT NOT NULL,            -- refund/vote/coupon/report 만 허용 (현금 인출 없음 — 규제 방어)
                                      -- report = 리포트 생성 비용(50냥, I3에서 추가)
    ref_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS campaign (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region_code TEXT NOT NULL,
    deadline TEXT,
    coupon_value_won INTEGER NOT NULL DEFAULT 1000,
    status TEXT NOT NULL DEFAULT 'open'  -- open/success/failed
);

CREATE TABLE IF NOT EXISTS placements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region_code TEXT NOT NULL,
    industry_id INTEGER NOT NULL REFERENCES industries(id),
    vacancy_id INTEGER NOT NULL REFERENCES vacancies(id),  -- 어느 공실에 성사됐는지
    status TEXT NOT NULL DEFAULT 'preparing',  -- I4b 확정: preparing(매칭됨·미개업)/open(개업 확정)
                                                -- 이 행이 아예 없으면 지도상 'vacant'(공실 그대로)로 파생
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_seed INTEGER NOT NULL DEFAULT 0
);
"""

# B가 필요로 하는 v3 집계 계약: (region_code, industry_id, voter_grid) -> 투표수.
# 공실별 demand(거리감쇠)는 B가 각 공실 좌표와 voter_grid 좌표 간 거리로 가중합을 계산한다 (08번 §2).
# held/settled/free만 집계 (refunded·cash_credited는 수요로 세지 않음 — AB공통 v2 계약).
# free(무료 투표)도 결제는 없지만 수요 신호로는 여전히 유효하므로 집계엔 포함한다.
VOTE_GRID_SUMMARY_VIEW = """
CREATE VIEW vote_grid_summary AS
    SELECT region_code, industry_id, voter_grid, COUNT(*) AS vote_count
    FROM votes
    WHERE payment_status IN ('held', 'settled', 'free')
    GROUP BY region_code, industry_id, voter_grid;
"""


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _get_schema_version(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "schema_meta"):
        return 0
    row = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
    return int(row["value"]) if row else 0


def init_db() -> None:
    conn = get_connection()
    try:
        version = _get_schema_version(conn)
        if version < SCHEMA_VERSION:
            conn.execute("DROP VIEW IF EXISTS vote_grid_summary")
            conn.execute("DROP VIEW IF EXISTS vote_summary")  # v2 이하 잔여 뷰 정리
            for table in ["placements", "votes", "cash_ledger", "campaign", "vacancies", "industries"]:
                conn.execute(f"DROP TABLE IF EXISTS {table}")

        conn.executescript(SCHEMA)
        conn.execute("DROP VIEW IF EXISTS vote_grid_summary")
        conn.executescript(VOTE_GRID_SUMMARY_VIEW)

        conn.execute("DELETE FROM schema_meta WHERE key = 'version'")
        conn.execute("INSERT INTO schema_meta (key, value) VALUES ('version', ?)", (str(SCHEMA_VERSION),))
        conn.commit()
    finally:
        conn.close()


def get_vote_grid_counts() -> dict:
    """B에게 줄 v3 집계 함수: {(region_code, industry_id, voter_grid): 투표수}"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT region_code, industry_id, voter_grid, vote_count FROM vote_grid_summary"
        ).fetchall()
        return {(r["region_code"], r["industry_id"], r["voter_grid"]): r["vote_count"] for r in rows}
    finally:
        conn.close()


def vacancy_exists(vacancy_id: int) -> bool:
    conn = get_connection()
    try:
        row = conn.execute("SELECT 1 FROM vacancies WHERE id = ?", (vacancy_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def industry_exists(industry_id: int) -> bool:
    conn = get_connection()
    try:
        row = conn.execute("SELECT 1 FROM industries WHERE id = ?", (industry_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def insert_vote(
    region_code: str, industry_id: int, voter_id: str, voter_name: Optional[str], voter_grid: str,
    free: bool = False,
) -> dict:
    """1,000원 고정·모의결제(held)·실투표(is_seed=0)로 기록한다.
    free=True면 결제 없이 amount_won=0·payment_status='free'로 기록(캠페인 환불 대상 아님)."""
    amount_won = 0 if free else 1000
    payment_status = "free" if free else "held"
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO votes (region_code, industry_id, voter_id, voter_name, voter_grid, amount_won, payment_status, is_seed)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (region_code, industry_id, voter_id, voter_name, voter_grid, amount_won, payment_status),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM votes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def insert_votes_batch(
    region_code: str,
    industry_ids: list[int],
    voter_id: str,
    voter_name: Optional[str],
    voter_grid: str,
    free: bool = False,
) -> tuple[list[dict], Optional[dict], int]:
    """
    여러 업종을 한 번에 투표 + (free가 아니면) 냥 일괄 차감(cash_ledger)을 하나의 트랜잭션으로 묶는다.
    호출부(routes_vote)가 industry_ids 존재를 이미 사전 검증하지만, 혹시 검증과 삽입 사이에
    끼어드는 문제(FK 위반 등)가 있어도 전부 롤백되도록 커밋 전까지는 아무것도 확정하지 않는다.
    free=True면 결제 자체가 없다 - amount_won=0·payment_status='free'로만 기록하고 cash_ledger는
    건드리지 않는다(차감도 없고 잔액도 그대로).
    반환: (삽입된 votes 목록, cash_ledger 차감 행(free면 None), 차감 후 잔액(free면 기존 잔액 그대로))
    """
    amount_won = 0 if free else 1000
    payment_status = "free" if free else "held"
    conn = get_connection()
    try:
        votes = []
        for industry_id in industry_ids:
            cur = conn.execute(
                """
                INSERT INTO votes (region_code, industry_id, voter_id, voter_name, voter_grid, amount_won, payment_status, is_seed)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (region_code, industry_id, voter_id, voter_name, voter_grid, amount_won, payment_status),
            )
            row = conn.execute("SELECT * FROM votes WHERE id = ?", (cur.lastrowid,)).fetchone()
            votes.append(dict(row))

        if free:
            ledger_row = None
            balance_after = conn.execute(
                "SELECT COALESCE(SUM(delta_won), 0) AS balance FROM cash_ledger WHERE voter_id = ?",
                (voter_id,),
            ).fetchone()["balance"]
        else:
            total_charged = 1000 * len(industry_ids)
            cur = conn.execute(
                "INSERT INTO cash_ledger (voter_id, delta_won, reason, ref_id) VALUES (?, ?, 'vote', NULL)",
                (voter_id, -total_charged),
            )
            ledger_row = dict(conn.execute("SELECT * FROM cash_ledger WHERE id = ?", (cur.lastrowid,)).fetchone())
            balance_after = conn.execute(
                "SELECT COALESCE(SUM(delta_won), 0) AS balance FROM cash_ledger WHERE voter_id = ?",
                (voter_id,),
            ).fetchone()["balance"]

        conn.commit()
        return votes, ledger_row, balance_after
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_vote_summary_detail(include_seed: bool = True) -> tuple[list[dict], int]:
    """
    /votes/summary 용 상세 집계: (region_code, industry_id, industry_name, voter_grid, vote_count) 목록 + 총계.
    held/settled만 포함 (refunded·cash_credited 제외). include_seed=False 면 실투표(is_seed=0)만 집계.
    """
    conn = get_connection()
    try:
        query = """
            SELECT v.region_code AS region_code, v.industry_id AS industry_id,
                   i.name AS industry_name, v.voter_grid AS voter_grid, COUNT(*) AS vote_count
            FROM votes v
            JOIN industries i ON i.id = v.industry_id
            WHERE v.payment_status IN ('held', 'settled', 'free')
        """
        if not include_seed:
            query += " AND v.is_seed = 0"
        query += " GROUP BY v.region_code, v.industry_id, i.name, v.voter_grid ORDER BY v.region_code, v.industry_id, v.voter_grid"

        rows = conn.execute(query).fetchall()
        summary = [dict(r) for r in rows]
        total = sum(r["vote_count"] for r in summary)
        return summary, total
    finally:
        conn.close()


def get_region_demand(region_code: str, include_seed: bool = True) -> tuple[int, list[dict]]:
    """
    동네 수요 리스트: 그 동네(region_code)의 업종별 득표 순위.
    held/settled만 집계 (refunded·cash_credited 제외 — vote_grid_summary와 동일 규칙).
    투표가 없는 업종은 포함하지 않는다.
    """
    conn = get_connection()
    try:
        query = """
            SELECT v.industry_id AS industry_id, i.name AS industry_name, COUNT(*) AS vote_count
            FROM votes v
            JOIN industries i ON i.id = v.industry_id
            WHERE v.region_code = ? AND v.payment_status IN ('held', 'settled', 'free')
        """
        params: list = [region_code]
        if not include_seed:
            query += " AND v.is_seed = 0"
        query += " GROUP BY v.industry_id, i.name ORDER BY vote_count DESC, v.industry_id ASC"

        rows = conn.execute(query, params).fetchall()
        ranking = [
            {
                "industry_id": r["industry_id"],
                "industry_name": r["industry_name"],
                "vote_count": r["vote_count"],
                "rank": idx + 1,
            }
            for idx, r in enumerate(rows)
        ]
        total_voters = sum(r["vote_count"] for r in rows)
        return total_voters, ranking
    finally:
        conn.close()


def get_regions_summary() -> list[dict]:
    """votes에 존재하는 region_code 목록 + 각 동네 총 투표 수 (held/settled만)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT region_code, COUNT(*) AS total_votes
            FROM votes
            WHERE payment_status IN ('held', 'settled', 'free')
            GROUP BY region_code
            ORDER BY region_code
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_cash_balance(voter_id: str) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(delta_won), 0) AS balance FROM cash_ledger WHERE voter_id = ?",
            (voter_id,),
        ).fetchone()
        return row["balance"]
    finally:
        conn.close()


def insert_cash_ledger(voter_id: str, delta_won: int, reason: str, ref_id: Optional[int]) -> dict:
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO cash_ledger (voter_id, delta_won, reason, ref_id)
            VALUES (?, ?, ?, ?)
            """,
            (voter_id, delta_won, reason, ref_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM cash_ledger WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


# 냥 환산 헬퍼. 화면 표기는 '냥', 저장은 원(won) 그대로 유지한다.
# 교환비율·유효기간 등 캐시 정책은 팀 미정(05번 결정대기) — 우선 10원=1냥 고정 환율만 반영.
def won_to_nyang(won: int) -> int:
    return won // 10


def nyang_to_won(nyang: int) -> int:
    return nyang * 10


# ── I4a: 캠페인 생성·조회·환불 적용 (담당 A — campaign.py의 순수 판정을 그대로 소비) ──────
def insert_campaign(region_code: str, deadline: str, coupon_value_won: int = 1000) -> dict:
    """캠페인 생성. status는 항상 'open'으로 시작(팀 확정: 기간제·목표 투표수 없음)."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO campaign (region_code, deadline, coupon_value_won, status) VALUES (?, ?, ?, 'open')",
            (region_code, deadline, coupon_value_won),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM campaign WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_campaign(campaign_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM campaign WHERE id = ?", (campaign_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_held_votes_for_region(region_code: str) -> list[dict]:
    """환불 판정 후보(그 동네의 held 투표). 실제 환불 대상 선별은 campaign.refund_targets()가 한다."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM votes WHERE region_code = ? AND payment_status = 'held'", (region_code,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def apply_campaign_refund(campaign_id: int, votes: list[dict]) -> list[dict]:
    """
    캠페인 기한 경과·미성사 환불 적용 — 하나의 트랜잭션으로 원자적 처리:
      1) 넘겨받은 각 투표를 payment_status='refunded'로 전환(집계·재환불 방지 — vote_grid_summary가 자동 제외)
      2) cash_ledger에 +적립(reason='refund', ref_id=투표 id)
      3) campaign.status='failed'
    votes는 campaign.refund_targets()로 이미 걸러진 held 투표만 들어온다는 전제(순수 판정은 B 몫).
    """
    conn = get_connection()
    try:
        ledger_rows = []
        for v in votes:
            conn.execute("UPDATE votes SET payment_status = 'refunded' WHERE id = ?", (v["id"],))
            cur = conn.execute(
                "INSERT INTO cash_ledger (voter_id, delta_won, reason, ref_id) VALUES (?, ?, 'refund', ?)",
                (v["voter_id"], v["amount_won"], v["id"]),
            )
            ledger_rows.append(
                dict(conn.execute("SELECT * FROM cash_ledger WHERE id = ?", (cur.lastrowid,)).fetchone())
            )
        conn.execute("UPDATE campaign SET status = 'failed' WHERE id = ?", (campaign_id,))
        conn.commit()
        return ledger_rows
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── I4b: 지도 /map — placements 기반 상태 파생 (담당 A) ─────────────────────────
def insert_placement(region_code: str, industry_id: int, vacancy_id: int) -> dict:
    """성사 레코드 생성. status='preparing'으로 시작(매칭됨·아직 개업 전).
    실제 '관리자 확인 버튼(모의)'을 통한 성사 처리 흐름은 09번 보드 #11(별도)."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO placements (region_code, industry_id, vacancy_id, status) VALUES (?, ?, ?, 'preparing')",
            (region_code, industry_id, vacancy_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM placements WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_placement_status(placement_id: int, status: str) -> dict:
    """status는 'preparing' 또는 'open'만 허용(그 외는 스키마 계약 위반)."""
    if status not in ("preparing", "open"):
        raise ValueError(f"허용되지 않는 placement status: {status!r} (preparing/open만 가능)")
    conn = get_connection()
    try:
        conn.execute("UPDATE placements SET status = ? WHERE id = ?", (status, placement_id))
        conn.commit()
        row = conn.execute("SELECT * FROM placements WHERE id = ?", (placement_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_map_statuses(region_code: str) -> dict:
    """
    그 동네 공실별 지도 상태: {vacancy_id: 'vacant'|'preparing'|'open'}.
    placements 행이 없는 공실은 'vacant'(공실 그대로). 한 공실에 행이 여러 개면
    가장 최근(id 최댓값) 것을 기준으로 한다.
    """
    conn = get_connection()
    try:
        vac_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM vacancies WHERE region_code = ?", (region_code,)
        ).fetchall()]
        rows = conn.execute(
            "SELECT vacancy_id, status FROM placements WHERE region_code = ? ORDER BY id ASC", (region_code,)
        ).fetchall()
        latest_status = {}
        for r in rows:
            latest_status[r["vacancy_id"]] = r["status"]  # ORDER BY id ASC라 마지막에 덮어써진 값이 최신
        return {vid: latest_status.get(vid, "vacant") for vid in vac_ids}
    finally:
        conn.close()
