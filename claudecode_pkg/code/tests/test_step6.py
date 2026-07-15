"""6단계 검증 — 캠페인 판단(순수) · 환불 대상 선별. (실행: python tests/test_step6.py)"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import campaign

ok = 0
def check(cond, label):
    global ok
    assert cond, f"❌ {label}"
    print(f"  ✅ {label}"); ok += 1


CAMP = {"id": "C-x", "region_code": "R1", "deadline": "2026-09-30",
        "coupon_value_won": 3000, "status": "open"}

print("── 6단계: 캠페인 기한 판단 (순수) ──")
# 기한 전 → 진행 중, 환불 없음
r = campaign.resolve_campaign(CAMP, "2026-07-15")
check(r["action"] == "none" and not r["expired"], "기한 전: action=none·진행 중")

# 기한 당일 → 경과로 취급(>=), 실패·환불
r = campaign.resolve_campaign(CAMP, "2026-09-30")
check(r["action"] == "expire" and r["expired"], "기한 당일(==deadline): action=expire")

# 기한 후 → 실패·환불
r = campaign.resolve_campaign(CAMP, "2026-10-01")
check(r["action"] == "expire", "기한 후: action=expire(전건 환불)")

# 이미 성사(success) → 종료, 환불 없음
r = campaign.resolve_campaign({**CAMP, "status": "success"}, "2026-10-01")
check(r["action"] == "none" and r["status"] == "success", "성사 캠페인: action=none(환불 안 함)")

# 이미 실패(failed) → 종료, 재환불 없음(멱등)
r = campaign.resolve_campaign({**CAMP, "status": "failed"}, "2026-10-01")
check(r["action"] == "none" and r["status"] == "failed", "실패 캠페인: action=none(재환불 없음)")

print("── 6단계: 환불 대상 선별 (순수) ──")
votes = [
    {"id": 1, "payment_status": "held"},
    {"id": 2, "payment_status": "held"},
    {"id": 3, "payment_status": "settled"},       # 성사 확정분 — 환불 대상 아님
    {"id": 4, "payment_status": "refunded"},       # 이미 환불 — 제외
    {"id": 5, "payment_status": "cash_credited"},  # 캐시 전환 — 제외
]
targets = campaign.refund_targets(votes)
check([v["id"] for v in targets] == [1, 2], "held 만 환불 대상(settled/refunded/cash_credited 제외)")
check(campaign.refund_targets([]) == [], "빈 목록 → 환불 대상 0건")

# ── 조각 2: DB 환불 실행 (모의) ──
import tempfile
import db
import config

print("── 6단계: 환불 실행 (DB · 모의) ──")
conn = db.connect(tempfile.mktemp(suffix=".db"))
db.reset_seed(conn)                                   # 시드 캠페인: region 4711158000, deadline 2026-09-30
camp = db.get_campaign(conn, "C-yangdeok")
# held 투표 3건 주입(양덕동 공실)
for i in range(3):
    db.create_vote(conn, "V-A", "cafe", f"voter-{i}", is_seed=0)

# 기한 전: resolve=none → 환불하지 않는다
r = campaign.resolve_campaign(camp, "2026-08-01")
check(r["action"] == "none", "기한 전: 환불 실행 안 함(action=none)")
check(db.get_campaign(conn, "C-yangdeok")["status"] == "open", "기한 전: 캠페인 open 유지")

# 기한 후: resolve=expire → 환불 실행
r = campaign.resolve_campaign(camp, "2026-10-01")
check(r["action"] == "expire", "기한 후: action=expire")
res = db.refund_campaign_votes(conn, camp)
check(res["refunded_count"] == 3, "기한 후: held 3건 전건 환불")
check(res["cash_won"] == 3000, "환불 캐시 = 3×1,000원 = 3,000원(=300냥)")

# 상태 전이 확인
statuses = [row["payment_status"] for row in conn.execute("SELECT payment_status FROM votes")]
check(all(s == "refunded" for s in statuses), "held → refunded 전건 전이")
check(db.get_campaign(conn, "C-yangdeok")["status"] == "failed", "캠페인 → failed")

# 캐시 적립(원장) + 냥 환산
bal = db.cash_balance(conn, "voter-0")
nyang = bal // config.CASH_POLICY["won_per_nyang"]
check(bal == 1000 and nyang == 100, "voter-0 캐시 잔액 1,000원 = 100냥")

# 환불분은 수요 집계에서 제외 (vote_counts_view = held/settled 만)
vc = db.get_vote_counts(conn, "4711158000")
check(sum(vc.values()) == 0, "환불분은 vote_counts_view 집계에서 제외(0)")

# 멱등: 이미 failed → 재실행해도 0건
res2 = db.refund_campaign_votes(conn, db.get_campaign(conn, "C-yangdeok"))
check(res2["refunded_count"] == 0, "재실행 멱등(추가 환불 0건)")
conn.close()

print(f"\n전부 통과 ✅  ({ok}개)")
