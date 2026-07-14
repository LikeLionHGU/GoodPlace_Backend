# 명당 백엔드 — 담당 B 엔진 (3·4·5단계)

계약(AB공통_분담과통합계약)의 순수 함수 계층. DB·프레임워크에 안 묶임. A 로더 + 얇은 라우터만 붙이면 통합.

## 구성

| 파일 | 내용 |
|---|---|
| `engine.py` | 3단계 적합도 산식 `score()` + 4단계 겹침 해소 배치 `allocate()` |
| `report.py` | 5단계 창업 리포트 `build_report()` (07 스펙: 필수 5요소·출처 태그·비교 기준선·참고 비용·책임 범위 선긋기) |
| `seed_dummy.py` | 계약 스키마 그대로의 더미 시드 (전부 `is_seed=1`). 7단계에서 소상공인 API 실데이터로 교체 |
| `tests/test_engine.py` | 문서의 3·4·5단계 검증 기준을 assert (28개) |
| `demo.py` | 원플로우: 시드 투표 → 배치 → 리포트 출력 |

## 실행

```bash
python tests/test_engine.py   # 검증 28개
python demo.py                # 원플로우 데모
```

## 계약 시그니처 (고정)

```python
allocate(vacancies, industries, vote_counts, weights=None, algo="auto") -> 배치결과
build_report(vacancy_id, vacancies, industries, vote_counts, allocation=None) -> 5칸 리포트  # 없는 공실 → None
```
- `vote_counts`는 `{(vacancy_id, industry_id): 투표수}` 형태로만 받는다 (votes 원본 구조 모름).
- 배치 응답에 점수 분해·차순위·사용 가중치 항상 포함 (심사 방어용).
- `allocate`는 scipy 있으면 헝가리안(최적·확장), 없으면 전수탐색(최적)+그리디 폴백으로 자동 동작 → 어디서도 실행됨.
- 리포트 1순위 = 배치 배정 업종 (지도 핀과 리포트 일치).

## ★ 팀 결정 대기 (코드에 반영해야 확정되는 것)

1. **적합도 산식 이원화** — 배치 랭킹은 3요소 곱셈식(03번), 리포트 표시 적합도 %는 4요소 가중합(07 스펙: 수요40/경쟁30/입지20/면적10). 통일할지 / 의도적 분리 유지할지. (`report.py` REPORT_WEIGHTS)
2. **가중치 초기값** w1=0.4·w2=0.3 잠정 + 한 줄 근거. (`engine.py` DEFAULT_WEIGHTS)
3. **배치 알고리즘** 헝가리안 채택 vs 공실 수 제한 — 양덕동 실제 공실 규모 보고 확정. (코드는 둘 다 지원)
4. **수요 정규화 기준** 리포트 수요항 만점 기준 `DEMAND_FULL_VOTES=40` 잠정.
5. **'인근'의 정의** 반경 500m 잠정. (`nearby_radius_m`)
6. **시드 업종 6종·면적·창업비용·인허가** 값 발표 승인 (`seed_dummy.py`).

## 스키마 관련 A와 조율

- `industries`에 **인허가(licenses) 컬럼 없음** — 02번이 지적한 누락. 리포트 ⑤에 필요하니 A의 industries 테이블에 추가 필요. (현재 더미엔 임시로 넣어둠)
- `vacancies.competitors`는 `{industry_id: 경쟁점 수}` JSON 형태 전제로 계산.
