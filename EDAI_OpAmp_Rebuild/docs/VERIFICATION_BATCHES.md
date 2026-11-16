# 고정 회로를 소규모 묶음으로 재검증하기

`run_extended_verification.py`의 `--case-id`를 반복해서 지정하면 해당 시험 조건만 실행한다. 선택 목록도 체크포인트에 고정되므로 재개할 때 바꿀 수 없다. 알 수 없는ID·중복ID는 거부한다.

## 부분 결과의 의미

- 전체 계획의 원래 조건 수와 미실행ID를 `RESULT.json`의 `batch`에 유지한다.
- 부분 실행은 `completed_selected_cases_diagnostic`라는 별도 상태다. 전체 파이프라인의 완료 상태로 취급되지 않는다.
- `source_cases_required`는 해당 실행에 요청한 조건 수다. `batch.full_plan_source_cases`는 원래 전체 조건 수이며 서로 다르다.
- `--case-id`가 없으면 기존 전체 실행 방식이 유지된다.
- 부분 결과의 최신 포인터는 `runs/verification_batches/LATEST.json`에 저장한다. 전체 검증의 최신 포인터를 덮어쓰지 않는다.
- 정상적으로 측정된 성능 미달과 실행 오류·측정 전제 실패를 구분해서 읽는다. 미실행은 합격이 아니다.

## 첫 묶음

고정 회로: `runs/harness_comparison/20261115_feedback_v2_one_round/cell_02/candidate.inc`.
이 회로는 과거58개 조건을 통과했던24pF 후보이며,27pF·30pF 후보와 다르다.

| 조건 | ID |
|---|---|
| 오프셋5V | CASE-e2c21174d75a55c8b0e0 |
| 오프셋15V | CASE-65a168f75eeb5fae0f78 |
| 오프셋36V | CASE-bc953a7cd0552b243791 |
| 대역폭5V | CASE-5a56359a665c7005dcb9 |
| 대역폭15V | CASE-6a10c68cdbe5e0271857 |

실행 기록: `runs/verification_batches/20261115_24p_batch01`.
`BATCH_PROTOCOL.json`에 실행 전 회로·원본 대장·코드 해시, 검사 조건과 정지 범위를 기록했다. 같은 폴더의 `code_snapshot`에 실행 코드를 보존했다.

최신 코드로 DUT 측정을 새로 수행하며 이전 DUT 파형이나 시동 추정값을 복사하지 않는다. 해석적으로 정답이 정해진 검사기 기준 회로의 결과만 물리적 동등성과 파일 해시를 확인한 뒤 재사용할 수 있다. 적용 계산 정책은 기존 `startup_seeded`, 개별 실행 제한은60초다. 시동 추정값 생성 실패 시 후속 계산 경로가 달라질 수 있으므로 실행 오류를 과거 대비 성능 저하로 단정하지 않는다.

첫 묶음 종료 후 다음 묶음을 자동 실행하지 않는다. 특정 조건을 다시 검사할 때는 원본 결과를 지키고 새 실행 폴더를 사용한다. 부분 결과로 나머지53개 검증 가능 조건이나 원래22개 미검증 항목을 합격 처리하지 않는다.
