"""
2단계 검증 — 투표(모의 결제)·집계·캐시 뼈대. 지시서 검증 기준 10개 + D(엔진 연결)를 assert.
실행: python tests/test_step2.py

HTTP 계층(201/404/422/금액 고정)은 새 의존성 없이 stdlib urllib + 실제 uvicorn 서브프로세스로 확인.
DB·캐시·엔진 연결은 함수 레벨로 확인. 임시 DB 파일을 써서 운영 DB를 건드리지 않는다.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(__file__)
CODE = os.path.join(HERE, "..")
sys.path.insert(0, CODE)

import db
from engine import allocate

ok = 0
def check(name, cond):
    global ok
    assert cond, f"❌ FAIL: {name}"
    ok += 1
    print(f"  ✅ {name}")


PORT = 8433
BASE = f"http://127.0.0.1:{PORT}"


def http(method, path, payload=None):
    """(status_code, body_dict) 반환. 4xx/5xx 도 예외 대신 코드로 돌려준다."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "null")


# ── 임시 DB + 실제 서버 기동 ──────────────────────────────────────────────
tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
env = {**os.environ, "MYDANG_DB": tmp.name}
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(PORT)],
                          cwd=CODE, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(80):
        try:
            if http("GET", "/health")[0] == 200:
                break
        except Exception:
            time.sleep(0.25)
    else:
        raise RuntimeError("서버가 뜨지 않음")

    conn = db.connect(tmp.name)            # 서버와 같은 파일을 검사용으로 연다
    print("── 2단계: 투표(모의 결제) HTTP ──")

    # ① 정상 투표 → 201, DB에 amount_won=1000 · held
    st, b = http("POST", "/votes",
                 {"vacancy_id": "V-A", "industry_id": "cafe",
                  "voter_id": "u1", "voter_name": "홍길동"})
    check("정상 투표 201", st == 201)
    vid = b["vote"]["id"]
    row = dict(conn.execute("SELECT * FROM votes WHERE id=?", (vid,)).fetchone())
    check("DB amount_won=1000·payment_status=held",
          row["amount_won"] == 1000 and row["payment_status"] == "held")

    # ② 없는 공실 / 업종 → 404
    check("없는 공실 404",
          http("POST", "/votes", {"vacancy_id": "NOPE", "industry_id": "cafe",
                                  "voter_id": "u1", "voter_name": "n"})[0] == 404)
    check("없는 업종 404",
          http("POST", "/votes", {"vacancy_id": "V-A", "industry_id": "NOPE",
                                  "voter_id": "u1", "voter_name": "n"})[0] == 404)

    # ④ voter_name 30자 초과 → 거부(422). 30자 정확은 허용.
    check("voter_name 31자 거부(422)",
          http("POST", "/votes", {"vacancy_id": "V-A", "industry_id": "cafe",
                                  "voter_id": "u1", "voter_name": "가" * 31})[0] == 422)
    check("voter_name 30자 허용(201)",
          http("POST", "/votes", {"vacancy_id": "V-A", "industry_id": "cafe",
                                  "voter_id": "u1", "voter_name": "가" * 30})[0] == 201)

    # ⑥ 클라이언트가 amount_won=9999 보내도 서버가 1000 고정
    st, b = http("POST", "/votes",
                 {"vacancy_id": "V-A", "industry_id": "cafe", "voter_id": "u1",
                  "voter_name": "x", "amount_won": 9999})
    forced = dict(conn.execute("SELECT amount_won FROM votes WHERE id=?",
                               (b["vote"]["id"],)).fetchone())
    check("amount_won 서버 고정(9999→1000)", st == 201 and forced["amount_won"] == 1000)

    print("── 2단계: 집계 ──")
    # ③ 알려진 실투표 세트 추가 → /votes/summary 총계·공실별 일치
    conn.execute("DELETE FROM votes"); conn.commit()   # 위 임시 표 비우고 통제된 세트로
    plan = {("V-A", "cafe"): 3, ("V-A", "banchan"): 2, ("V-B", "cafe"): 2, ("V-C", "bunsik"): 1}
    for (vc, ic), n in plan.items():
        for k in range(n):
            st, _ = http("POST", "/votes",
                         {"vacancy_id": vc, "industry_id": ic,
                          "voter_id": f"real-{vc}-{ic}-{k}", "voter_name": "표시"})
            assert st == 201
    N = sum(plan.values())
    _, summ = http("GET", "/votes/summary")
    check(f"/votes/summary 총계 = {N}", summ["total"] == N)
    exp_by_vac = {"V-A": 5, "V-B": 2, "V-C": 1}
    check("공실별 집계 정확", summ["by_vacancy"] == exp_by_vac)

    # ⑤ 시드 투표 vs 실투표 is_seed 구분 집계
    db.create_vote(conn, "V-D", "cafe", "seed-voter", "시드표", is_seed=1)
    db.create_vote(conn, "V-D", "cafe", "seed-voter2", "시드표", is_seed=1)
    _, summ2 = http("GET", "/votes/summary")
    check("is_seed 구분: real=N, seed=2",
          summ2["by_seed"] == {"real": N, "seed": 2} and summ2["total"] == N + 2)

    # ⑦ 집계 함수가 (vacancy_id, industry_id)→투표수 형태 유지
    vc_map = db.get_vote_counts(conn)
    check("get_vote_counts 키가 (vacancy_id, industry_id) 튜플",
          all(isinstance(k, tuple) and len(k) == 2 for k in vc_map))
    check("집계값이 실제 넣은 수와 일치(refunded 없음)",
          vc_map.get(("V-A", "cafe")) == 3 and vc_map.get(("V-C", "bunsik")) == 1
          and vc_map.get(("V-D", "cafe")) == 2)

    # refunded 제외 조건 자리 동작 확인: 한 건을 refunded 로 바꾸면 집계에서 빠진다
    conn.execute("UPDATE votes SET payment_status='refunded' "
                 "WHERE vacancy_id='V-C' AND industry_id='bunsik'"); conn.commit()
    check("refunded 표는 집계 제외", db.get_vote_counts(conn).get(("V-C", "bunsik"), 0) == 0)
    conn.execute("UPDATE votes SET payment_status='held' "
                 "WHERE vacancy_id='V-C' AND industry_id='bunsik'"); conn.commit()

    # GET /vacancies 투표 요약이 실제 값으로 채워짐(1단계엔 0이었음)
    _, vacs_resp = http("GET", "/vacancies")
    va = next(i for i in vacs_resp["items"] if i["id"] == "V-A")
    check("/vacancies 투표 요약 실값 반영(V-A total=5)",
          va["votes_total"] == 5 and va["votes_by_industry"].get("cafe") == 3)

    print("── 2단계: 캐시 원장(모의) 뼈대 ──")
    # ⑧ 적립 +N, 사용 -M → 잔액 N-M
    db.cash_add(conn, "wallet1", 3000, "refund", ref_id="vote-x")   # 적립(환불 모의)
    db.cash_add(conn, "wallet1", -1000, "coupon", ref_id="buy-y")   # 사용
    check("캐시 잔액 = 적립-사용 (3000-1000=2000)", db.cash_balance(conn, "wallet1") == 2000)
    check("타 사용자 잔액 0(격리)", db.cash_balance(conn, "other") == 0)

    print("── D: 집계 → 엔진 allocate() 연결 (테스트 안에서만) ──")
    inds = [dict(r) for r in conn.execute(
        "SELECT id,name,min_area_m2,max_area_m2 FROM industries")]
    vac_rows = [dict(r) for r in conn.execute("SELECT * FROM vacancies")]
    vacs = [{**v, "competitors": json.loads(v["competitors"])} for v in vac_rows]
    vote_counts = db.get_vote_counts(conn)               # DB 집계를 그대로
    res = allocate(vacs, inds, vote_counts)              # 엔진에 투입
    assigned = [a["industry_id"] for a in res["allocations"]]
    check("배치: 업종 겹침 없음", len(assigned) == len(set(assigned)))
    check("배치: 모든 공실 배정", len(res["allocations"]) == len(vacs))
    # direct_votes 가 DB 실제 투표수와 일치 (엔진과 DB가 같은 숫자를 봄)
    mism = [(a["vacancy_id"], a["industry_id"],
             a["breakdown"]["direct_votes"], vote_counts.get((a["vacancy_id"], a["industry_id"]), 0))
            for a in res["allocations"]
            if a["breakdown"]["direct_votes"] != vote_counts.get((a["vacancy_id"], a["industry_id"]), 0)]
    check("배치 direct_votes = DB 투표수(엔진·DB 일치)", mism == [])

    conn.close()
finally:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()

print("── 회귀 ──")
for name, path in [("test_engine 33개", "tests/test_engine.py"),
                   ("test_step1", "tests/test_step1.py")]:
    r = subprocess.run([sys.executable, path], cwd=CODE, env={**os.environ, "MYDANG_DB": tmp.name},
                       capture_output=True, text=True)
    check(f"회귀 {name} 통과(exit 0)", r.returncode == 0)

os.unlink(tmp.name)
print(f"\n전부 통과 ✅  ({ok}개)")
