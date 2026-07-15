# 명당 백엔드 — 담당 B 엔진 (3·4·5·6단계 + AI 해설)

계약(AB공통_분담과통합계약)의 순수 함수 계층. DB·프레임워크에 안 묶임. A 로더 + 얇은 라우터로 통합됨.

## 구성

| 파일 | 내용 |
|---|---|
| `engine.py` | 3단계 적합도 산식 `score()` + 4단계 겹침 해소 배치 `allocate()` |
| `report.py` | 5단계 창업 리포트 `build_report()` (07 스펙: 필수 5요소·출처 태그·비교 기준선·참고 비용·책임 범위 선긋기·포화 곡선 %) |
| `routes_report.py` | 5단계 리포트 API `GET /report/{vacancy_id}` (지도 배치와 1순위 일치, AI 해설 첨부) |
| `campaign.py` | 6단계 캠페인 판단(순수) `resolve_campaign` + 환불 대상 선별 `refund_targets` |
| `routes_campaign.py` | 6단계 API `GET /campaigns`, `POST /campaigns/{id}/resolve`(기한 경과·미성사 → 전건 환불) |
| `ai_explain.py` | AI 해설(P4): 확정 수치 → GPT 자연어 3~5문장. 숫자 화이트리스트·금칙어 검증, 키 없으면 None |
| `seed_dummy.py` | 계약 스키마 그대로의 더미 시드 (전부 `is_seed=1`). 7단계에서 소상공인 API 실데이터로 교체 |
| `tests/` | test_engine(33)·step1(18)·step2(21)·step34(25)·step6(17)·ai_explain(18) = 132개 |
| `demo.py` | 원플로우: 시드 투표 → 배치 → 리포트 출력 |

## 실행

```bash
# 회귀 6종(132개) — venv 파이썬으로
for t in test_engine test_step1 test_step2 test_step34 test_step6 test_ai_explain; do python tests/$t.py; done
python demo.py                # 원플로우 데모
uvicorn main:app --reload     # http://127.0.0.1:8000/docs
```

## 계약 시그니처 (고정)

```python
allocate(vacancies, industries, vote_counts, weights=None, algo="auto") -> 배치결과
build_report(vacancy_id, vacancies, industries, vote_counts, weights=None, campaign=None, allocation=None) -> 5칸 리포트  # 없는 공실 → None
```
- `vote_counts`는 `{(vacancy_id, industry_id): 투표수}` 형태로만 받는다 (votes 원본 구조 모름).
- 배치 응답에 점수 분해·차순위·사용 가중치 항상 포함 (심사 방어용).
- `allocate`는 scipy 있으면 헝가리안(최적·확장), 없으면 전수탐색(최적)+그리디 폴백으로 자동 동작 → 어디서도 실행됨.
- 리포트 1순위 = 배치 배정 업종 (지도 핀과 리포트 일치).

## ✅ 확정 (되돌리려면 사람 승인 — CLAUDE.md 3절)

- **적합도 산식** `score = demand × area_fit × competition_factor`. 경쟁계수는 **동네 평균 대비 비율식**(절대 수 감점 아님).
- **표시 적합도 %** = 포화 곡선 `100×s/(s+K)` 단조 변환. 이전의 '4요소 가중합(수요40/경쟁30/입지20/면적10)'은 곱셈 엔진과 순위가 역전돼 **폐기**. 100%는 구조적 미도달.
- **가중치** `w1=0.4`, `w2=1.0` (설계 초기값 — 실데이터 확보 후 캘리브레이션 여지). `engine.py` DEFAULT_WEIGHTS.
- **배치 알고리즘** 헝가리안 채택 + 전수탐색(최적)/그리디 자동 폴백.
- **캠페인·환불(6단계)** 기간제·목표 투표수 없음·기한 경과+미성사 → held 전건 환불(캐시 냥). 환불분은 집계 제외.
- **AI 해설(P4)** 확정 수치만 입력 → GPT 3~5문장. 숫자 화이트리스트+금칙어 검증, 실패·키없음 시 None(리포트는 그대로). 키는 `.env`(OPENAI_API_KEY).

## ★ 남은 미확정 (팀 결정 대기)

1. **K 전역 고정 vs 캠페인별** + `BASELINE_TARGET_VOTES=30`(잠정) 실데이터 캘리브레이션. `report.py`.
2. **'인근' 반경 500m** 설계 초기값 — 실데이터로 민감도 검증. `nearby_radius_m`.
3. **층수 계수의 자리** — 참고 정보 유지 vs 산식에 켜기(상층 감점).
4. **시드 업종 6종·면적·창업비용·인허가** 값 발표 승인. `seed_dummy.py`.
5. **GPT 실호출 검증** — 순수 로직·배선·키없음 폴백은 완료. 실제 해설 품질/모델은 키(OPENAI_API_KEY) 확보 후 검증.

> 확정됨: 캐시 정책 3건(1,000원=100냥·만료없음·재투표 동일취급, `config.CASH_POLICY`).

## 스키마 관련 A와 조율

- `industries.licenses`(인허가) — 계약 v2에 편입·구현됨(리포트 ⑤용).
- `vacancies.competitors`는 `{industry_id: 경쟁점 수}` JSON 문자열 전제 — 어댑터(`adapters.py`)가 dict로 파싱.
