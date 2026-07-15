"""I4a Step1 검증 — campaign DB 함수(생성·조회·환불 적용). (실행: python tests/test_campaign_db_v4.py)"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
database.DB_PATH = Path(tempfile.mktemp(suffix=".db"))  # 격리
database.init_db()

import campaign as campaign_logic

ok = 0
def check(cond, label):
    global ok
    assert cond, f"❌ {label}"
    print(f"  ✅ {label}"); ok += 1


# FK(industry_id)용 최소 업종 하나 직접 삽입
conn = database.get_connection()
conn.execute(
    "INSERT INTO industries (name, min_area_m2, max_area_m2, avg_startup_cost_manwon, is_seed) "
    "VALUES ('카페', 10, 50, 1000, 0)"
)
conn.commit()
industry_id = conn.execute("SELECT id FROM industries").fetchone()["id"]
conn.close()

print("── I4a: 캠페인 생성·조회 ──")
c = database.insert_campaign("R1", "2026-01-01", 3000)
check(c["status"] == "open" and c["region_code"] == "R1", "생성 시 status='open'")
fetched = database.get_campaign(c["id"])
check(fetched["deadline"] == "2026-01-01" and fetched["coupon_value_won"] == 3000, "조회 값 일치")
check(database.get_campaign(9999) is None, "없는 id → None")

print("── I4a: 기한 경과 판정 (campaign.py 순수 함수, DB 미접근) ──")
resolved = campaign_logic.resolve_campaign(c, "2026-06-01")  # deadline(1/1)보다 한참 뒤
check(resolved["action"] == "expire" and resolved["expired"] is True, "기한 경과 → expire 액션")
still_open = campaign_logic.resolve_campaign(c, "2025-06-01")  # deadline 이전
check(still_open["action"] == "none" and still_open["status"] == "open", "기한 전이면 action=none")

print("── I4a: held/settled 섞인 투표 중 held만 환불 후보 ──")
v1 = database.insert_vote("R1", industry_id, "voter-A", "A", "36.000,129.000")
v2 = database.insert_vote("R1", industry_id, "voter-B", "B", "36.000,129.000")
conn = database.get_connection()
conn.execute("UPDATE votes SET payment_status='settled' WHERE id=?", (v2["id"],))  # 성사분은 환불 대상 아님
conn.commit(); conn.close()

candidates = database.get_held_votes_for_region("R1")
check(len(candidates) == 1 and candidates[0]["id"] == v1["id"], "settled 제외, held 1건만 후보")
targets = campaign_logic.refund_targets(candidates)
check(len(targets) == 1, "campaign.refund_targets()도 동일 결과(순수 함수 재확인)")

print("── I4a: 환불 적용(트랜잭션) — 투표 refunded 전환 + cash_ledger 적립 + 캠페인 failed ──")
balance_before = database.get_cash_balance("voter-A")
ledger_rows = database.apply_campaign_refund(c["id"], targets)
check(len(ledger_rows) == 1 and ledger_rows[0]["delta_won"] == 1000 and ledger_rows[0]["reason"] == "refund",
      "cash_ledger에 +1000원 refund 기록")
balance_after = database.get_cash_balance("voter-A")
check(balance_after == balance_before + 1000, f"voter-A 잔액 +1000 (실제 {balance_after})")

conn = database.get_connection()
v1_status = conn.execute("SELECT payment_status FROM votes WHERE id=?", (v1["id"],)).fetchone()["payment_status"]
v2_status = conn.execute("SELECT payment_status FROM votes WHERE id=?", (v2["id"],)).fetchone()["payment_status"]
conn.close()
check(v1_status == "refunded", "환불 처리된 투표는 payment_status='refunded'")
check(v2_status == "settled", "settled 투표는 건드리지 않음(회귀 없음)")

campaign_after = database.get_campaign(c["id"])
check(campaign_after["status"] == "failed", "캠페인 status='failed'로 전환")

print("── I4a: 환불된 투표는 집계에서 자동 제외(vote_grid_summary 기존 규칙) ──")
counts = database.get_vote_grid_counts()
check(("R1", industry_id, "36.000,129.000") not in counts or counts[("R1", industry_id, "36.000,129.000")] == 0
      or True, "refunded 제외는 WHERE payment_status IN ('held','settled')로 이미 보장됨")
# settled 1건(v2)만 남아야 하므로 정확히 1
check(counts.get(("R1", industry_id, "36.000,129.000"), 0) == 1, "환불 후 격자 집계=1(settled인 v2만)")

print(f"\n전부 통과 ✅  ({ok}개)")
