# 명당 백엔드 (v3 — 동네 투표 전환 통합본)

**11_현황_인수인계_v3통합.md가 현재 상태의 단일 진실.** A(데이터 계층)·B(엔진·산출)가 이 저장소에서
통합됐다. 투표는 공실이 아니라 **동네+업종**에 묶이고(`votes.region_code + industry_id + voter_grid`),
리포트는 "업종 클릭 → 추천 공실 1·2·3위"(구 v1의 "공실 클릭 → 추천 업종"에서 반전).

## 구성

| 파일 | 담당 | 내용 |
|---|---|---|
| `database.py` | A | v3 스키마(`schema_meta`로 버전 관리)·시드 로더·집계 `get_vote_grid_counts()` (B에게 주는 계약) |
| `seed.py` | A | 업종6·공실3(양덕동 임시 좌표)·동네 투표4, 전부 `is_seed=1` |
| `routes_vote.py` | A | 투표 API(다중선택 `/votes/batch`), GPS→200m 격자 `snap_to_grid`(원좌표 미저장) |
| `routes_cash.py` | A | 냥 캐시(적립/사용/잔액, 10원=1냥) |
| `routes_region.py` | A | 동네 수요 리스트 `GET /regions`, `GET /regions/{code}/demand` |
| `ingest_api.py` | A | 소상공인 상가정보 API 수집(`/admin/ingest`, `SBIZ_SERVICE_KEY`) |
| `engine.py` | B | 적합도 산식 `score()`(거리감쇠 demand×area_fit×competition×floor_fit) + 지도 배치 `allocate()`(헝가리안) |
| `report.py` | B | 리포트 v3 `build_report()` — 업종→공실 1·2·3위, 포화 곡선 %, 출처 태그, floor 근거 |
| `routes_report.py` | B/A | `POST /report`(리포트+AI 해설, 50냥 차감·A cash 연동) |
| `campaign.py` | B | 캠페인 판단(순수) `resolve_campaign` + 환불 대상 선별 `refund_targets` |
| `routes_campaign.py` | A | `POST /campaigns`, `GET /campaigns/{id}`, `POST /campaigns/{id}/resolve`(region 기반 환불) |
| `routes_map.py` | A | `POST /placements`, `/placements/{id}/open`, `GET /map`(공실 상태 vacant/preparing/open) |
| `ai_explain.py` | B | 확정 수치 → GPT 3~5문장. 숫자 화이트리스트·금칙어 검증, 키 없으면 조용히 None |
| `tests/` | 공동 | v3 회귀 8파일·135개 (아래 목록) |
| `demo_v3.py` | 공동 | 원플로우: 투표→동네 수요 리스트→업종 클릭→리포트+AI 해설 |

### tests/ 목록 (I0~I4, `run_all_v3.py`로 일괄 실행)

| 파일 | 개수 | 검증 대상 |
|---|---|---|
| `test_v3_data.py` | 14 | A 데이터계층(스키마·투표·격자·냥) |
| `test_engine_v3.py` | 19 | 거리감쇠 경계(500/800)·floor_fit·배치 겹침 |
| `test_report_v3.py` | 19 | 업종→공실 순위·동네 격리·score 동일성 |
| `test_ai_explain_v3.py` | 19 | facts 추출·금칙어·숫자 화이트리스트·키없음 폴백 |
| `test_report_route_v3.py` | 16 | `POST /report` 통합(50냥 차감·잔액부족 비차단) |
| `test_campaign_db_v4.py` | 14 | 캠페인 환불 DB 함수(held만 대상·트랜잭션) |
| `test_campaign_route_v4.py` | 22 | 캠페인 API 통합(기한 경과·멱등 재실행) |
| `test_map_route_v4.py` | 12 | 지도 상태 파생(vacant/preparing/open)·404·동네 격리 |

## 실행

```bash
cd claudecode_pkg/code
.venv/bin/uvicorn main:app --reload       # http://127.0.0.1:8000/docs (.env 자동 로드)
.venv/bin/python tests/run_all_v3.py      # v3 회귀 전체(135개) 일괄 실행
.venv/bin/python demo_v3.py               # 원플로우 콘솔 데모
```

## 계약 시그니처 (v3, 고정)

```python
database.get_vote_grid_counts() -> {(region_code, industry_id, voter_grid): 표수}   # A→B 계약
engine.score(vacancy, industry, grid_votes, weights=None) -> 점수 분해 dict
engine.allocate(vacancies, industries, vote_counts, weights=None, algo="auto") -> 배치결과
report.build_report(industry_id, region_code, vacancies, industries, grid_votes_all,
                     weights=None, campaign=None) -> 업종→공실 1·2·3위 dict | None
```
- `allocate`는 scipy 있으면 헝가리안(최적·확장), 없으면 전수탐색(최적)+그리디 폴백으로 자동 동작.
- `build_report`는 그 업종에 대한 공실별 `score()` 내림차순 상위 3개 — 단일 업종이라 `allocate` 겹침 해소 불필요.
- 리포트 score는 지도 배치(`allocate`)와 항상 동일 산식 사용(`test_report_v3.py`의 score 동일성 테스트로 보장).

## ✅ 확정 (되돌리려면 사람 승인 — CLAUDE.md 3절)

- **적합도 산식** `score = demand × area_fit × competition_factor × floor_fit`(v3, 거리감쇠 demand +
  floor_fit 곱연산 확정). 경쟁계수는 **동네 평균 대비 비율식**(절대 수 감점 아님).
- **거리감쇠** ≤500m 1.0 / 500~800m 선형 감쇠 / >800m 0. **floor_fit** 1층 1.0 / 2층이상 0.7 / 지하 0.5.
- **표시 적합도 %** = 포화 곡선 `100×s/(s+K)` 단조 변환, `K`는 하드코딩이 아니라 `report._saturation_k()`가
  합성 기준선(거리 0, `BASELINE_TARGET_VOTES=30`)으로 프로그램적으로 산출(v3, K=30.0). 100%는 구조적 미도달.
- **배치 알고리즘** 헝가리안 채택 + 전수탐색(최적)/그리디 자동 폴백. 리포트 score와 지도 배치 score는 항상 동일(`test_report_v3.py`로 회귀 보장).
- **캠페인·환불(v3, region 기반)** 기간제·목표 투표수 없음·기한 경과+미성사 → 그 동네(region_code)의 held 전건 환불(캐시 냥). 환불분은 집계 자동 제외. 재실행해도 중복 환불 없음(멱등).
- **지도 상태(v3, placements 파생)** 레코드 없음=`vacant` / `status='preparing'`=매칭됨·미개업(기본값) / `status='open'`=개업 확정.
- **AI 해설** 확정 수치(`facts_from_report(report, card)`)만 입력 → GPT 3~5문장. 숫자 화이트리스트+금칙어 검증, 실패·키없음 시 조용히 None(리포트는 그대로 반환). 키는 `.env`(OPENAI_API_KEY).
- **리포트 생성 비용** 50냥(500원) 차감, `POST /report` 호출 시 항상 차감 — 잔액 부족이어도 차단하지 않고 `insufficient_balance: true` 플래그만 표시(캐시 충전 정책 미확정이라 `/votes/batch`와 동일한 비차단 패턴 유지).

## ★ 남은 미확정 (팀 결정 대기)

1. **`BASELINE_TARGET_VOTES=30`** — 산출 방식(프로그램적 계산)은 확정, 값 자체는 잠정치. 실데이터 확보 후 캘리브레이션 필요. `report.py`.
2. **'인근' 반경 500/800m·floor_fit 0.7/0.5·경쟁 w2=1.0** — 설계 초기값, 실데이터 민감도 검증 대기.
3. **캠페인-투표 매핑** — `votes` 테이블에 `campaign_id`가 없어 환불 대상을 region_code로 근사한다(한 동네에 캠페인이 시간상 겹치지 않는다는 전제). 겹치는 캠페인이 필요해지면 스키마에 `campaign_id` 추가 필요.
4. **placements 성사 처리 관리자 확인 UX** — 지금은 `POST /placements`·`/placements/{id}/open` 최소 API만 존재(09번 보드 #11, 화면단 별도).
5. **시드 업종 6종·면적·창업비용·인허가** 값 발표 승인. `seed.py`.
6. **GPT 실호출 검증** — 순수 로직·배선·키없음 폴백은 완료. 실제 해설 품질/모델은 유효한 `OPENAI_API_KEY` 확보 후 검증 대기.

> 확정됨: 캐시 정책(1,000원=100냥, `won_to_nyang`/`nyang_to_won`), 스키마 버전 관리(`schema_meta`, 현재 `SCHEMA_VERSION=4`).

## 스키마 관련 A·B 조율

- `industries.licenses`(인허가) — 리포트 ⑤ 참고자료용.
- `vacancies.competitors`는 `{업종명: 경쟁점 수}` JSON 문자열 — 엔진이 업종명으로 조회해 dict로 파싱.
- `votes`는 v3에서 `vacancy_id`가 아니라 `region_code + industry_id + voter_grid`를 가진다(동네 투표 전환). B는 `database.get_vote_grid_counts()`로만 집계를 받는다 — votes 원본 스키마를 직접 알 필요 없음.
