# -*- coding: utf-8 -*-
"""원플로우 데모: 시드 투표 → 배치 → 리포트. (실행: python demo.py)"""
import json
from engine import allocate
from report import build_report
from seed_dummy import INDUSTRIES, VACANCIES, VOTE_COUNTS, CAMPAIGN

print("="*60)
print(" 배치 결과 (겹침 해소)  ·  알고리즘:", end=" ")
res = allocate(VACANCIES, INDUSTRIES, VOTE_COUNTS)
print(res["algorithm"], "· 총점", res["total_score"])
print("="*60)
for a in res["allocations"]:
    bd = a["breakdown"]
    ru = ", ".join(f"{r['name']}({r['score']})" for r in a["runners_up"])
    print(f"[{a['vacancy_name']}] → {a['industry_name']}  (점수 {a['score']})")
    print(f"    직접표 {bd['direct_votes']} + 인근가중 {bd['nearby_weighted']} "
          f"= 수요 {bd['demand']} | 면적적합 {bd['area_fit']} | 경쟁계수 {bd['competition_factor']}(경쟁 {bd['competitor_count']}곳)")
    print(f"    차순위: {ru}")

print("\n" + "="*60)
print(" 창업 리포트 — 양덕동 A공실")
print("="*60)
rep = build_report("V-A", VACANCIES, INDUSTRIES, VOTE_COUNTS, campaign=CAMPAIGN)
c = rep["conclusion"]; wc = rep["waiting_customers"]; cm = rep["competition"]
print(f"① {c['headline']}")
print(f"   \"{c['one_liner']}\"")
print(f"② 선결제 대기 고객: {wc['count']}명  — {wc['label']}  (쿠폰 {wc['coupon_value_won']:,}원) [{wc['source']}]")
print("③ 배치 근거 (엔진 곱셈 3요소):")
rs = rep["reasoning"]; fac = rs["factors"]
dm = fac["수요"]
print(f"     수요 · 직접표 {dm['direct_votes']} + 인근가중 {dm['nearby_weighted']} = 수요 {dm['demand']}")
print(f"     면적 적합 · {fac['면적 적합']['score01']}")
cp = fac["경쟁 보정"]
print(f"     경쟁 보정 · {cp['score01']} (동네 평균 대비 {cp['competition_ratio']}배)")
print(f"   ⚠ {rs['disclaimer']}")
print(f"④ 주변 경쟁: {cm['industry']} {cm['count']['value']}곳(동네 평균 {cm['neighborhood_avg']['value']}) · {cm['reading']}")
ref = rep["reference"]
print(f"⑤ 참고 비용: 약 {ref['startup_cost_manwon']['value']}만원 [{ref['startup_cost_manwon']['source']}] · 인허가: {ref['licenses']['value']}")
print(f"   {ref['cta']}")
