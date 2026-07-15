# A·B 공통 — 분담 경계와 통합 계약 (양쪽 모두 필독)

> ⚠️ **스키마 v3 예정(2026.07.14 동네 투표 전환).** votes에서 vacancy_id 제거 + voter_grid 추가, vacancies에 중개사 등록 필드 확장 — **08번 §4·§6이 목표 스키마.** 전환 P1에서 이 문서를 v3로 갱신. 그 외 경계·순수함수·통합 규칙은 유효.


백엔드를 두 명(A·B)이 나눠 만들고 나중에 합친다. 충돌 없이 합치려면 **경계와 데이터 계약**을 먼저 지켜야 한다. 이 문서는 A·B 양쪽 zip에 모두 들어 있으며, 여기 적힌 스키마·규칙은 양쪽이 동일하게 따른다.

## 분담 경계

| | 담당 A — 데이터·수집 | 담당 B — 엔진·산출 |
|---|---|---|
| 한 줄 | 데이터가 **들어오는** 쪽 | 데이터가 **나가는** 쪽 |
| 맡는 단계 | 1(DB·시드) · 2(투표·모의결제·캐시) · 7(API 수집·지역확장) | 3(적합도 산식) · 4(겹침 해소 배치) · 5(리포트) · 6(캠페인·환불 로직) |
| 핵심 모듈 | DB 스키마, 소상공인 API 연동, 투표/결제 흐름, 지역 파라미터화 | 배치 엔진, 리포트 생성기, 캠페인 상태 로직 |
| 만지는 파일(예) | `database.py`, `ingest_api.py`, `routes_vote.py` | `engine.py`, `report.py`, `routes_allocation.py` |

**두 사람이 만나는 유일한 지점 = DB 스키마.** A가 채우고 B가 읽는다. 스키마만 아래대로 합의하면 각자 독립 개발 후 붙일 수 있다.

## 데이터 계약 (DB 스키마 — 양쪽 고정 · v2: mini-main 구현 반영)

합치기 전에 이 스키마를 양쪽이 동일하게 쓴다. 컬럼 추가가 필요하면 상대에게 알리고 이 문서를 갱신한 뒤 반영한다(한쪽이 임의로 바꾸지 않는다). **v2 갱신: 구현 중 추가 합의된 3건(굵게)과 TEXT형 id를 계약에 편입.**

```
industries (업종 기준표)      -- A가 적재, B가 읽음. id는 TEXT(예: "cafe")
  id, name, min_area_m2, max_area_m2, avg_startup_cost_manwon,
  inds_code(247체계 매핑), source, is_seed, **licenses(필요 인허가 — 리포트 ⑤용)**

vacancies (공실)             -- A가 적재, B가 읽음. id는 TEXT(예: "V-A")
  id, name, address, region_code(행정동/시군구 — 경북확장 키), lat, lng,
  area_m2, floor, vacant_since, prev_industry(이전 업종),
  competitors(JSON 문자열: {industry_id: 경쟁점 수} — B 어댑터가 dict로 파싱), evidence, is_seed

votes (투표)                 -- A가 적재, B가 집계해서 읽음
  id, vacancy_id(FK), industry_id(FK), voter_id, **voter_name(표시명 ≤30자 — 고객 명단용)**,
  amount_won(서버 1000 고정), payment_status(held/settled/refunded/cash_credited),
  created_at, is_seed

cash_ledger (캐시 원장, 모의) -- A 담당
  id, voter_id, delta_won(+적립/-사용), reason(refund/vote/coupon), ref_id, created_at

campaign (캠페인)            -- B가 상태 판단, A가 생성
  id, region_code, deadline, coupon_value_won, status(open/success/failed), **is_seed**
```

**B가 A에게 요구하는 읽기 형태(집계 뷰 — 구현됨):** `vote_counts_view`가 `(vacancy_id, industry_id) → 투표수`를 보장한다. **집계는 payment_status IN ('held','settled')만** — 환불(refunded)·캐시전환(cash_credited) 표는 수요로 세지 않는다(6단계 환불 규칙과 산식 정확도의 전제). B는 이 집계와 vacancies/industries만으로 배치·리포트를 계산한다(votes 원본 테이블 구조에 의존하지 않기).

**⚠️ 마이그레이션 규칙(신규):** 스키마에 컬럼을 추가할 때 `CREATE TABLE IF NOT EXISTS`만으로는 기존 DB 파일에 반영되지 않는다(voter_name 이슈로 실증). 컬럼 추가 시 ALTER TABLE 마이그레이션을 함께 제공하거나 DB 재생성 절차를 명시할 것.

## 인터페이스 계약 (합칠 때 시그니처 고정)

B의 엔진은 순수 함수로 만들어 A의 데이터 소스와 분리한다.

```
allocate(vacancies: list, industries: list, vote_counts: dict) -> 배치결과
build_report(vacancy_id, vacancies, industries, vote_counts) -> 5칸 리포트
```

- B는 위 함수만 책임진다. DB에서 데이터를 꺼내는 것은 A가 만든 로더가 하고, B 함수는 인자로 받은 것만 계산한다. → B는 DB 없이도 더미 데이터로 단위 테스트 가능, A는 엔진 없이도 수집·투표 테스트 가능.
- 합칠 때: A의 로더 → B의 함수 → API 응답으로 연결하는 얇은 라우터만 추가하면 된다.

## 공통 규칙 (양쪽 동일)

- **단계별로 만들고 검증 후 진행.** 각 단계 = 만드는 것 → 검증 기준 → 통과 후 다음.
- 시드 데이터는 전부 `is_seed=1`/`SEED` 표기 (가상 데이터 지양 요건).
- 서비스명 **명당**. 용어: 투자·펀딩 금지 → 선결제·쿠폰 선구매.
- 결제는 **모의**(플로우만, 실PG·사업자등록 없음). 환불은 **캐시 적립(모의)** — 재투표·쿠폰 구매에 사용.
- 지역은 **하드코딩 금지, region_code로 파라미터화** (양덕동 첫 적용, 경북 확장).
- 스택은 양쪽 동일하게 (다음 대화에서 재확정). 같은 스택·같은 스키마가 통합의 전제.

## 통합 순서 (합칠 때)

1. 스키마 일치 확인 (이 문서 기준)
2. A의 로더 + B의 순수 함수를 라우터로 연결
3. 각자 단계 테스트를 합쳐서 전체 재실행
4. 원플로우 리허설: 수집 → 투표 → 배치 → 리포트 1회 정상 (= MVP 완료 기준)

## 함께 읽을 문서

이 zip의 나머지 문서(00~06 인수인계, 개발계획서, API 명세서 등)는 A·B 공통 배경이다. 담당별 상세는 각 zip의 `담당_A_가이드.md` 또는 `담당_B_가이드.md` 참조.
