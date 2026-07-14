"""
1단계 — DB 스키마·시드 적재·집계 인터페이스 (담당 A 몫).

- 스키마 = docs/AB공통_분담과통합계약.md 계약 그대로. 계약 대비 추가 2건(상대 통지·문서 갱신 대상):
  * industries.licenses — 리포트 ⑤ 필요 인허가 (CLAUDE.md 6절에서 추가 합의됨)
  * campaign.is_seed   — "모든 시드 행에 is_seed 표기" 요건 충족용
- 시드의 유일한 원본 = seed_dummy.py (INDUSTRIES·VACANCIES·CAMPAIGN).
  votes·cash_ledger 는 1단계에서 빈 상태(투표·모의결제 생성은 2단계).
  seed_dummy.VOTE_COUNTS 는 2단계 이후 집계 검증용 참고값 — DB에 넣지 않는다.
- B 엔진은 votes 원본을 모르고 get_vote_counts() 의
  {(vacancy_id, industry_id): 투표수} 집계 형태로만 읽는다(계약).
"""
import json
import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = str(Path(__file__).resolve().parent / "mydang.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS industries (
    id                      TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    min_area_m2             REAL NOT NULL,
    max_area_m2             REAL NOT NULL,
    avg_startup_cost_manwon INTEGER,
    inds_code               TEXT,
    source                  TEXT NOT NULL,
    is_seed                 INTEGER NOT NULL DEFAULT 0,
    licenses                TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vacancies (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    address       TEXT,
    region_code   TEXT NOT NULL,
    lat           REAL NOT NULL,
    lng           REAL NOT NULL,
    area_m2       REAL NOT NULL,
    floor         INTEGER,
    vacant_since  TEXT,
    prev_industry TEXT,
    competitors   TEXT NOT NULL DEFAULT '{}',  -- JSON: {industry_id: 경쟁점 수}
    evidence      TEXT,
    is_seed       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS votes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id     TEXT NOT NULL REFERENCES vacancies(id),
    industry_id    TEXT NOT NULL REFERENCES industries(id),
    voter_id       TEXT NOT NULL,
    voter_name     TEXT,                          -- 표시명(고객 명단용). 계약 밖 추가 — A/문서에 통지 필요
    amount_won     INTEGER NOT NULL DEFAULT 1000,
    payment_status TEXT NOT NULL DEFAULT 'held'
                   CHECK (payment_status IN ('held','settled','refunded','cash_credited')),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    is_seed        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cash_ledger (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    voter_id   TEXT NOT NULL,
    delta_won  INTEGER NOT NULL,               -- +적립 / -사용
    reason     TEXT NOT NULL CHECK (reason IN ('refund','vote','coupon')),
    ref_id     TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS campaign (
    id               TEXT PRIMARY KEY,
    region_code      TEXT NOT NULL,
    deadline         TEXT NOT NULL,
    coupon_value_won INTEGER NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('open','success','failed')),
    is_seed          INTEGER NOT NULL DEFAULT 0
);

-- 계약의 집계 뷰: (vacancy_id, industry_id) → 투표수.
-- 유효 표만 집계(held/settled). 환불·캐시전환 표를 수요로 세지 않기 위함(2단계에서 재확인).
CREATE VIEW IF NOT EXISTS vote_counts_view AS
    SELECT vacancy_id, industry_id, COUNT(*) AS vote_count
    FROM votes
    WHERE payment_status IN ('held', 'settled')
    GROUP BY vacancy_id, industry_id;
"""


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """DB 연결. 경로 우선순위: 인자 > 환경변수 MYDANG_DB > code/mydang.db"""
    path = db_path or os.environ.get("MYDANG_DB") or DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """테이블·뷰 생성(멱등)."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def reset_seed(conn: sqlite3.Connection) -> dict:
    """seed_dummy 를 그대로 재적재. votes·cash_ledger 는 비운다(1단계 계약).

    시드를 여기서 지어내지 않는다 — 원본은 seed_dummy.py 하나.
    """
    import seed_dummy

    init_db(conn)
    cur = conn.cursor()
    for table in ("votes", "cash_ledger", "campaign", "vacancies", "industries"):
        cur.execute(f"DELETE FROM {table}")

    cur.executemany(
        """INSERT INTO industries
           (id, name, min_area_m2, max_area_m2, avg_startup_cost_manwon,
            inds_code, source, is_seed, licenses)
           VALUES (:id, :name, :min_area_m2, :max_area_m2, :avg_startup_cost_manwon,
                   :inds_code, :source, :is_seed, :licenses)""",
        seed_dummy.INDUSTRIES,
    )
    cur.executemany(
        """INSERT INTO vacancies
           (id, name, address, region_code, lat, lng, area_m2, floor, vacant_since,
            prev_industry, competitors, evidence, is_seed)
           VALUES (:id, :name, :address, :region_code, :lat, :lng, :area_m2, :floor,
                   :vacant_since, :prev_industry, :competitors, :evidence, :is_seed)""",
        [{**v, "competitors": json.dumps(v["competitors"], ensure_ascii=False)}
         for v in seed_dummy.VACANCIES],
    )
    cur.execute(
        """INSERT INTO campaign (id, region_code, deadline, coupon_value_won, status, is_seed)
           VALUES (:id, :region_code, :deadline, :coupon_value_won, :status, 1)""",
        seed_dummy.CAMPAIGN,
    )
    conn.commit()
    return table_counts(conn)


def table_counts(conn: sqlite3.Connection) -> dict:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("industries", "vacancies", "votes", "cash_ledger", "campaign")}


def get_vote_counts(conn: sqlite3.Connection, region_code: str | None = None) -> dict:
    """B 엔진 계약 인터페이스: {(vacancy_id, industry_id): 투표수}.

    표가 없는 조합은 키가 없다(= 0으로 취급, seed_dummy.VOTE_COUNTS 와 같은 희소 형태).
    1단계에서는 votes 가 비어 있으므로 항상 빈 dict(전부 0).
    """
    sql = "SELECT vacancy_id, industry_id, vote_count FROM vote_counts_view"
    params: tuple = ()
    if region_code is not None:
        sql = """SELECT vc.vacancy_id, vc.industry_id, vc.vote_count
                 FROM vote_counts_view vc
                 JOIN vacancies v ON v.id = vc.vacancy_id
                 WHERE v.region_code = ?"""
        params = (region_code,)
    return {(r["vacancy_id"], r["industry_id"]): r["vote_count"]
            for r in conn.execute(sql, params)}


# ── 2단계: 투표(모의 결제) ────────────────────────────────────────────────
class NotFound(ValueError):
    """존재하지 않는 vacancy_id / industry_id (라우터에서 404로 변환)."""


def create_vote(conn, vacancy_id, industry_id, voter_id, voter_name=None, is_seed=0):
    """투표 1건 생성. 결제는 모의 — payment_status='held' 로만 기록(실PG 없음).

    금액은 서버가 VOTE_AMOUNT_WON 으로 고정(클라이언트가 못 정한다).
    없는 vacancy_id / industry_id 면 NotFound.
    """
    from config import VOTE_AMOUNT_WON

    if conn.execute("SELECT 1 FROM vacancies WHERE id=?", (vacancy_id,)).fetchone() is None:
        raise NotFound(f"없는 공실: {vacancy_id}")
    if conn.execute("SELECT 1 FROM industries WHERE id=?", (industry_id,)).fetchone() is None:
        raise NotFound(f"없는 업종: {industry_id}")

    cur = conn.execute(
        """INSERT INTO votes (vacancy_id, industry_id, voter_id, voter_name,
                              amount_won, payment_status, is_seed)
           VALUES (?, ?, ?, ?, ?, 'held', ?)""",
        (vacancy_id, industry_id, voter_id, voter_name, VOTE_AMOUNT_WON, int(is_seed)),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM votes WHERE id=?", (cur.lastrowid,)).fetchone())


# 집계에서 수요로 세는 결제 상태. refunded/cash_credited 는 제외(6단계 환불 규칙 대비 조건 자리).
COUNTED_STATUSES = ("held", "settled")


def votes_summary(conn, region_code=None):
    """전체·공실별·(공실,업종)별 집계 + 시드/실투표 구분.

    refunded 등 미집계 상태는 vote_counts_view 와 동일 기준으로 제외(계약 유지).
    """
    where = f"payment_status IN ({','.join('?' * len(COUNTED_STATUSES))})"
    params = list(COUNTED_STATUSES)
    join = ""
    if region_code is not None:
        join = "JOIN vacancies v ON v.id = votes.vacancy_id"
        where += " AND v.region_code = ?"
        params.append(region_code)

    def q(cols, group):
        return conn.execute(
            f"SELECT {cols} FROM votes {join} WHERE {where} GROUP BY {group}", params
        ).fetchall()

    total = conn.execute(
        f"SELECT COUNT(*) FROM votes {join} WHERE {where}", params
    ).fetchone()[0]
    by_vacancy = {r["vacancy_id"]: r["n"] for r in q("vacancy_id, COUNT(*) n", "vacancy_id")}
    by_seed = {("seed" if r["is_seed"] else "real"): r["n"]
               for r in q("is_seed, COUNT(*) n", "is_seed")}
    return {
        "total": total,
        "by_vacancy": by_vacancy,
        "by_seed": {"seed": by_seed.get("seed", 0), "real": by_seed.get("real", 0)},
        "counted_statuses": list(COUNTED_STATUSES),
    }


# ── 2단계: 캐시 원장(모의) — 뼈대만. 정책(교환비율·유효기간·재투표)은 config 에서 미확정 ──
def cash_add(conn, voter_id, delta_won, reason, ref_id=None):
    """캐시 원장에 적립(+)/사용(-) 1건 기록. reason ∈ refund/vote/coupon(계약 CHECK).

    금액 단위·교환비율·유효기간은 config.CASH_POLICY 에서 미확정(팀 결정 대기).
    """
    cur = conn.execute(
        "INSERT INTO cash_ledger (voter_id, delta_won, reason, ref_id) VALUES (?, ?, ?, ?)",
        (voter_id, int(delta_won), reason, ref_id),
    )
    conn.commit()
    return cur.lastrowid


def cash_balance(conn, voter_id):
    """사용자 잔액 = delta_won 합계(적립 - 사용). 만료 미반영(유효기간 미확정)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(delta_won), 0) AS bal FROM cash_ledger WHERE voter_id=?",
        (voter_id,),
    ).fetchone()
    return row["bal"]
