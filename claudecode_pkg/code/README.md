# 명당 백엔드 — 담당 B 엔진 (3·4·5단계)

계약(AB공통_분담과통합계약)의 순수 함수 계층. DB·프레임워크에 안 묶임. A 로더 + 얇은 라우터로 통합됨.

## 구성

| 파일 | 내용 |
|---|---|
| `engine.py` | 3단계 적합도 산식 `score()` + 4단계 겹침 해소 배치 `allocate()` |
| `report.py` | 5단계 창업 리포트 `build_report()` (07 스펙: 필수 5요소·출처 태그·비교 기준선·참고 비용·책임 범위 선긋기·포화 곡선 %) |
| `routes_report.py` | 5단계 리포트 API `GET /report/{vacancy_id}` (얇은 라우터, 지도 배치와 1순위 일치) |
| `seed_dummy.py` | 계약 스키마 그대로의 더미 시드 (전부 `is_seed=1`). 7단계에서 소상공인 API 실데이터로 교체 |
| `tests/test_engine.py` | 문서의 3·4·5단계 검증 기준을 assert (33개) |
| `demo.py` | 원플로우: 시드 투표 → 배치 → 리포트 출력 |

## 실행

```bash
python tests/test_engine.py   # 검증 33개
python demo.py                # 원플로우 데모
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

## ★ 남은 미확정 (팀 결정 대기)

1. **K 전역 고정 vs 캠페인별** + `BASELINE_TARGET_VOTES=30`(잠정) 실데이터 캘리브레이션. `report.py`.
2. **'인근' 반경 500m** 설계 초기값 — 실데이터로 민감도 검증. `nearby_radius_m`.
3. **층수 계수의 자리** — 참고 정보 유지 vs 산식에 켜기(상층 감점).
4. **시드 업종 6종·면적·창업비용·인허가** 값 발표 승인. `seed_dummy.py`.
5. **캐시(모의) 정책 3건**(6단계): 교환비율·유효기간·재투표 취급. `config.py` CASH_POLICY.

## 스키마 관련 A와 조율

- `industries.licenses`(인허가) — 계약 v2에 편입·구현됨(리포트 ⑤용).
- `vacancies.competitors`는 `{industry_id: 경쟁점 수}` JSON 문자열 전제 — 어댑터(`adapters.py`)가 dict로 파싱.
