"""
3·4단계 통합 검증 — 어댑터 + 배치 API. 지시서 9개 기준을 실제 실행으로 대조.
실행: python tests/test_step34.py

HTTP 계층은 새 의존성 없이 stdlib urllib + 실제 uvicorn 서브프로세스. 임시 DB로 운영 DB 불간섭.
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

import adapters
import db
from engine import allocate

ok = 0
def check(name, cond):
    global ok
    assert cond, f"❌ FAIL: {name}"
    ok += 1
    print(f"  ✅ {name}")


PORT = 8511
BASE = f"http://127.0.0.1:{PORT}"
REGION = "4711158000"          # 양덕동 시드 지역 (테스트가 인자로 넘김 — 코드 기본값 아님)


def http(method, path):
    req = urllib.request.Request(BASE + path, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "null")


def post_vote(vc, ic, k, seed=0, status="held"):
    conn = db.connect(DB)
    try:
        row = db.create_vote(conn, vc, ic, f"v-{vc}-{ic}-{k}", "표시", is_seed=seed)
        if status != "held":
            conn.execute("UPDATE votes SET payment_status=? WHERE id=?", (status, row["id"]))
            conn.commit()
    finally:
        conn.close()


tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
DB = tmp.name
env = {**os.environ, "MYDANG_DB": DB}
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(PORT)],
                          cwd=CODE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(80):
        try:
            if http("GET", "/health")[0] == 200:
                break
        except Exception:
            time.sleep(0.25)
    else:
        raise RuntimeError("서버가 뜨지 않음")

    conn = db.connect(DB)

    print("── ① 어댑터 competitors JSON→dict 파싱 ──")
    raw = conn.execute("SELECT competitors FROM vacancies WHERE id='V-A'").fetchone()["competitors"]
    check("DB competitors 원본이 문자열", isinstance(raw, str))
    row = conn.execute("SELECT * FROM vacancies WHERE id='V-A'").fetchone()
    adapted = adapters.vacancy_from_row(row)
    check("어댑터 출력 competitors 는 dict", isinstance(adapted["competitors"], dict))
    check("파싱값 == json.loads(원본) (문자열째면 실패)",
          adapted["competitors"] == json.loads(raw) and adapted["competitors"]["cafe"] == 12)

    print("── 통제된 투표 세트 삽입 ──")
    plan = {("V-A", "banchan"): 5, ("V-A", "cafe"): 3, ("V-B", "bakery"): 6,
            ("V-C", "bunsik"): 7, ("V-D", "book"): 4}
    for (vc, ic), n in plan.items():
        for k in range(n):
            post_vote(vc, ic, k)
    # 환불 1건(집계 제외 확인용): V-A/banchan 에 1건 넣고 refunded 처리
    post_vote("V-A", "banchan", 99, status="refunded")

    print("── ②③④⑦ /allocation 호출 & 엔진 직접호출 대조 ──")
    st, resp = http("GET", f"/allocation?region_code={REGION}")
    check("/allocation 200", st == 200)

    # ⑦ 같은 입력으로 engine.allocate() 직접 호출 → 배정·점수 정확히 일치
    vacs, inds, vc_counts = adapters.load_allocation_inputs(conn, REGION)
    direct = allocate(vacs, inds, vc_counts)
    api_pairs = [(a["vacancy_id"], a["industry_id"], a["score"]) for a in resp["allocations"]]
    eng_pairs = [(a["vacancy_id"], a["industry_id"], a["score"]) for a in direct["allocations"]]
    check("⑦ API 배정·점수 == 엔진 직접호출(어댑터 무왜곡)", api_pairs == eng_pairs)
    check("⑦ breakdown 도 동일",
          [a["breakdown"] for a in resp["allocations"]] == [a["breakdown"] for a in direct["allocations"]])

    # ② direct_votes == DB 실제 투표수(환불 제외)
    expect = {k: v for k, v in plan.items()}          # refunded 는 세지 않음
    mism = []
    for a in resp["allocations"]:
        key = (a["vacancy_id"], a["industry_id"])
        if a["breakdown"]["direct_votes"] != expect.get(key, 0):
            mism.append((key, a["breakdown"]["direct_votes"], expect.get(key, 0)))
    check("② breakdown.direct_votes == DB 투표수(환불 제외)", mism == [])
    # 환불이 실제로 빠졌는지: V-A/banchan 직접표는 5 여야(환불 1건 제외)
    va = next(a for a in resp["allocations"] if a["vacancy_id"] == "V-A")
    # (V-A 배정이 banchan 이 아닐 수 있으니 집계로 직접 확인)
    check("환불(refunded) 투표 집계 제외", vc_counts.get(("V-A", "banchan")) == 5)

    # ③ 겹침 없음
    assigned = [a["industry_id"] for a in resp["allocations"]]
    check("③ 배정 업종 전부 유일(겹침 없음)", len(assigned) == len(set(assigned)))
    check("③ 모든 공실 배정", len(resp["allocations"]) == len(vacs))

    # ④ 필수 필드
    check("④ weights 포함", isinstance(resp.get("weights"), dict) and resp["weights"]["w1"] == 0.4)
    check("④ algorithm 포함", bool(resp.get("algorithm")))
    need = {"direct_votes", "nearby_weighted", "area_fit", "competitor_count",
            "neighborhood_avg", "competition_ratio", "competition_factor"}
    check("④ breakdown 7요소 포함", need <= set(resp["allocations"][0]["breakdown"]))
    check("④ runners_up 포함", "runners_up" in resp["allocations"][0])

    # ①-실증: competitor_count·neighborhood_avg 가 DB 원본 손계산과 일치(문자열째면 틀어짐)
    a0 = resp["allocations"][0]
    iid = a0["industry_id"]
    comps = [json.loads(r["competitors"]).get(iid, 0)
             for r in conn.execute("SELECT competitors FROM vacancies WHERE region_code=?", (REGION,))]
    hand_avg = round(sum(comps) / len(comps), 2)
    hand_cc = json.loads(conn.execute("SELECT competitors FROM vacancies WHERE id=?",
                                      (a0["vacancy_id"],)).fetchone()["competitors"]).get(iid, 0)
    check(f"①실증 competitor_count 손계산 일치({hand_cc})", a0["breakdown"]["competitor_count"] == hand_cc)
    check(f"①실증 neighborhood_avg 손계산 일치({hand_avg})", a0["breakdown"]["neighborhood_avg"] == hand_avg)

    print("── ⑤ region_code 파라미터화 ──")
    # 다른 지역에 공실 하나 심으면 대상이 달라짐
    conn.execute("""INSERT INTO vacancies (id,name,address,region_code,lat,lng,area_m2,floor,
                    vacant_since,prev_industry,competitors,evidence,is_seed)
                    VALUES ('X-1','타지역공실','주소','9999999999',36.1,129.4,50,1,'2025-01',
                    '기타','{"cafe":1}','SEED',1)"""); conn.commit()
    _, other = http("GET", "/allocation?region_code=9999999999")
    check("⑤ region_code 바꾸면 대상 공실 달라짐",
          [a["vacancy_id"] for a in other["allocations"]] == ["X-1"])
    st_empty, empty = http("GET", "/allocation?region_code=0000000000")
    check("⑤ 없는 region_code → 빈 배열 + 200", st_empty == 200 and empty["allocations"] == [])
    # region_code 필수
    st_missing, _ = http("GET", "/allocation")
    check("⑤ region_code 누락 → 422(필수)", st_missing == 422)

    print("── ⑥ 투표 0건 정상 응답 ──")
    conn.execute("DELETE FROM votes"); conn.commit()
    st0, zero = http("GET", f"/allocation?region_code={REGION}")
    check("⑥ 투표 0건 → 200", st0 == 200)
    check("⑥ 전 공실 점수 0", all(a["score"] == 0.0 for a in zero["allocations"])
          and len(zero["allocations"]) == 4)

    print("── 성능 로그(측정만) ──")
    check("elapsed_ms 응답에 포함(측정됨)", isinstance(zero.get("elapsed_ms"), (int, float)))
    print(f"    /allocation elapsed_ms = {zero['elapsed_ms']} ms")

    conn.close()
finally:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()

print("── ⑧⑨ 회귀 ──")
for name, path in [("test_engine 33", "tests/test_engine.py"),
                   ("test_step1", "tests/test_step1.py"),
                   ("test_step2", "tests/test_step2.py")]:
    r = subprocess.run([sys.executable, path], cwd=CODE,
                       env={**os.environ, "MYDANG_DB": DB}, capture_output=True, text=True)
    check(f"회귀 {name} 통과(exit 0)", r.returncode == 0)

os.unlink(DB)
print(f"\n전부 통과 ✅  ({ok}개)")
