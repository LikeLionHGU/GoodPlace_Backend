"""P0 검증 — v2 스키마 additive 마이그레이션. (실행: python tests/test_v2_schema.py)
전환기: 기존 v1 컬럼/뷰는 유지(회귀 green), v2 신규만 추가."""
import os, sys, sqlite3, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import db

ok = 0
def check(cond, label):
    global ok
    assert cond, f"❌ {label}"
    print(f"  ✅ {label}"); ok += 1


def cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}

def has_table(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


print("── P0-a: 새 DB 스키마에 v2 반영 ──")
conn = db.connect(tempfile.mktemp(suffix=".db"))
db.init_db(conn)
vc = cols(conn, "vacancies")
check({"building_use", "facilities", "rent_terms", "source_tag"} <= vc, "vacancies 중개사 등록 컬럼 4종")
check(has_table(conn, "placements"), "placements 테이블 존재")
pc = cols(conn, "placements")
check({"vacancy_id", "industry_id", "status", "confirmed_by", "is_seed"} <= pc, "placements 필수 컬럼")
# v1 유지(회귀 안전) — 기존 컬럼·뷰 그대로
check("competitors" in vc and "area_m2" in vc, "v1 vacancies 컬럼 유지")
check(has_table(conn, "campaign") and "vote_counts_view" in
      {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'")},
      "v1 vote_counts_view·campaign 유지")
conn.close()

print("── P0-a: 낡은 DB 파일 마이그레이션(계약 규칙) ──")
p = tempfile.mktemp(suffix=".db")
raw = sqlite3.connect(p)
raw.executescript(  # v1 이전 스키마(신규 컬럼·placements 없음)
    "CREATE TABLE vacancies (id TEXT PRIMARY KEY, name TEXT NOT NULL, region_code TEXT NOT NULL,"
    " lat REAL NOT NULL, lng REAL NOT NULL, area_m2 REAL NOT NULL);"
    "CREATE TABLE votes (id INTEGER PRIMARY KEY AUTOINCREMENT, vacancy_id TEXT);")
raw.commit(); raw.close()

conn = db.connect(p)
db.init_db(conn)                       # executescript(IF NOT EXISTS) + _migrate
check("source_tag" in cols(conn, "vacancies"), "낡은 vacancies 에 컬럼 ALTER 반영")
check("voter_name" in cols(conn, "votes"), "낡은 votes 에 voter_name 반영(기존 이슈)")
check(has_table(conn, "placements"), "낡은 DB 에도 placements 생성")
db.init_db(conn)                       # 재실행 멱등
check("source_tag" in cols(conn, "vacancies"), "마이그레이션 멱등(재실행 안전)")
conn.close()

print("── P0-b: votes v2 컬럼 + 격자 집계뷰 ──")
conn = db.connect(tempfile.mktemp(suffix=".db"))
db.reset_seed(conn)
vcol = cols(conn, "votes")
check({"region_code", "voter_grid", "weight"} <= vcol, "votes v2 컬럼(region_code·voter_grid·weight)")
check("vote_grid_counts_view" in {r[0] for r in
      conn.execute("SELECT name FROM sqlite_master WHERE type='view'")}, "격자 집계뷰 존재")

# v2 표 직접 주입(공실 없이 동네+업종+격자). vacancy_id nullable 확인.
def add_v2_vote(iid, region, grid, weight, status="held"):
    conn.execute("INSERT INTO votes (industry_id, voter_id, region_code, voter_grid, weight, payment_status)"
                 " VALUES (?, 'u', ?, ?, ?, ?)", (iid, region, grid, weight, status))
add_v2_vote("cafe", "R1", "g1", 1.0)
add_v2_vote("cafe", "R1", "g1", 0.5)          # 같은 격자 → 합산
add_v2_vote("cafe", "R1", "g2", 1.0)          # 다른 격자
add_v2_vote("cafe", "R1", "g3", 1.0, "refunded")  # 환불 → 제외
conn.execute("INSERT INTO votes (industry_id, voter_id, region_code, weight) VALUES ('cafe','u','R1',1.0)")  # 격자 없음 → 제외
conn.commit()

gc = db.get_grid_counts(conn, region_code="R1", industry_id="cafe")
check(gc == {("cafe", "R1", "g1"): 1.5, ("cafe", "R1", "g2"): 1.0}, "격자별 weight 합(환불·무격자 제외)")
check(db.get_grid_counts(conn, region_code="R2") == {}, "다른 동네 → 빈 집계")
# v1 뷰도 그대로(회귀 안전) — vacancy_id 있는 v1 표만 셈
check(db.get_vote_counts(conn) == {}, "v1 vote_counts_view 는 v2 표(무 vacancy) 안 셈")
conn.close()

print(f"\n전부 통과 ✅  ({ok}개)")
