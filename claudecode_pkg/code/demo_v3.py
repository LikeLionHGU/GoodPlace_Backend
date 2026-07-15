"""
I5 — 원플로우 데모(v3): 시드 투표 → 동네 수요 리스트 → 업종 클릭 → 공실 리포트(+AI 해설).
09번 보드 #16(시연 리허설)의 콘솔판. 실행: python demo_v3.py

주의: OPENAI_API_KEY가 없거나 비어있으면 ai_explanation은 None으로 나온다(정상 동작 — ai_explain.py의
"키 없으면 조용히 null" 정책). 실제 해설 문장까지 보려면 .env에 유효한 키를 넣고 다시 실행.
"""
import os
import tempfile
from pathlib import Path

# .env의 OPENAI_API_KEY가 아직 placeholder 텍스트라면(진짜 키 미입력) config.load_env_file()의
# setdefault가 그걸 "키 있음"으로 오인해 실제 네트워크 호출을 시도한다. 진짜 키가 있으면 이 줄을
# 지우고 실행하면 AI 해설 실제 문장까지 볼 수 있다.
if not os.environ.get("OPENAI_API_KEY", "").startswith("sk-"):
    os.environ["OPENAI_API_KEY"] = ""

import database
database.DB_PATH = Path(tempfile.mktemp(suffix=".db"))  # 실제 meongdang.db를 건드리지 않는다

from fastapi.testclient import TestClient
import main

VOTER_ID = "demo-voter"


def line(title: str) -> None:
    print(f"\n{'─' * 8} {title} {'─' * 8}")


with TestClient(main.app) as c:
    line("1. 동네 목록 (주민이 진입)")
    regions = c.get("/regions").json()
    for r in regions:
        print(f"  {r['region_code']}  총 투표 {r['total_votes']}건")
    region_code = regions[0]["region_code"]

    line(f"2. 동네 수요 리스트 — {region_code}")
    demand = c.get(f"/regions/{region_code}/demand").json()
    print(f"  총 투표자 {demand['total_voters']}명")
    for row in demand["ranking"]:
        print(f"  {row['rank']}위  {row['industry_name']:<8} 득표 {row['vote_count']}표")

    top_industry = demand["ranking"][0]
    industry_id = top_industry["industry_id"]
    line(f"3. 창업자가 1위 업종 클릭 — {top_industry['industry_name']}(id={industry_id})")

    balance_before = c.get("/cash/balance", params={"voter_id": VOTER_ID}).json()["balance"]
    print(f"  리포트 조회 전 잔액: {balance_before}원")

    r = c.post("/report", json={"industry_id": industry_id, "region_code": region_code, "voter_id": VOTER_ID})
    if r.status_code != 200:
        print(f"  리포트 생성 실패: {r.status_code} {r.json()}")
    else:
        report = r.json()
        line("4. 리포트 결과 (공실 추천 1·2·3위)")
        print(f"  {report['headline']}")
        print(f"  동네 전체 수요: {report['region_total_demand']['count']}명 ({report['region_total_demand']['source']})")
        for card in report["vacancies"]:
            print(f"\n  [{card['rank']}위] {card['vacancy']['name']} — 적합도 {card['adequacy_pct']}%")
            print(f"    반경 내 대기고객: {card['waiting_customers']['count']}명 "
                  f"(쿠폰 총액 {card['waiting_customers']['coupon_total_won']}원)")
            print(f"    경쟁: {card['competition']['count']['value']}곳 "
                  f"(동네평균 {card['competition']['neighborhood_avg']['value']:.1f}곳 대비 "
                  f"{card['competition']['competition_ratio']:.2f}배)")
            print(f"    층 근거: {card['floor_basis']['reading']}")
            explanation = card.get("ai_explanation")
            print(f"    AI 해설: {explanation if explanation else '(키 없음 — 수치만 표시, 폴백 정상 동작)'}")

        line("5. 리포트 생성 비용 차감 (50냥)")
        charge = report["charge"]
        print(f"  차감: {charge['charged_won']}원 ({charge['charged_nyang']}냥)"
              f" → 차감 후 잔액 {charge['balance_after_won']}원"
              f"{'  [잔액 부족 — 비차단 정책]' if charge['insufficient_balance'] else ''}")

print("\n원플로우 데모 완료 ✅  (투표→수요리스트→업종클릭→리포트+AI해설, 09번 보드 #16 대응)")
