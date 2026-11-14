# 조원 파트와 연결할 때

## 이미 연결된 부분과 남은 부분

사양 추출 → HKG/PDG → 검사 계획 → 회로 설계·검증·피드백 전달은 연결했습니다. 의미 검토와 수정안의 LLM 판단은 JSON 파일로 주고받습니다. 조원 UI, 블록 조합, 설계 API/모델 라우팅, Harness²는 별도로 연결할 부분입니다.

## 권장 확인 지점

| 연결할 파트 | 먼저 볼 코드/계약 |
|---|---|
| 사양 추출 보완 | `spec_01_build_rows`, `spec_02_enrich_rows`, `spec_03_verify_sources`의 같은 행 ID |
| 데이터/사양 UI | `hkg_query`의 연결 문맥, `plan_02_measurements`의 조건/목표/사례 |
| 모델 API | `harness_02_request.make_request/validate_response`의 JSON 계약 |
| 블록 조합 | 완성된 후보를 전체 `netlist`로 반환하고 현재 DUT 경계를 만족시키기 |
| 실행 결과 UI | `STATE.json`, `BEST.json`, `REPORT.md`, 최종 `LEDGER.json` |
| 지침 개선 | `harness/fixed_v1.json`, `harness_01_fixed`, `harness_02_request` |

## 현재 DUT 경계

`.subckt FIRSTAMP P N VP VM OUT`의 명시적 포트와 동결 GNM/GPM 모델을 유지합니다. 내부는 수치 M/R/C 소자로 구성하며 MOS 단자는4개입니다. `VM/VP`를 사용하고 내부 외부접지0을 쓰지 않습니다. 현재 기동 검사의 `BIAS` 관측 노드도 필요합니다. 테스트벤치의 기준/자극용 이상 소자와 DUT 규칙은 다릅니다.

다른 PDK, 모델, 블록 인터페이스를 사용하려면 규칙을 몰래 우회하지 말고 새 설계/검사 정책으로 검증해야 합니다. PDG의 제품 핀 번호가 이 단일 채널 DUT의 핀 바인딩을 자동 확정하지 않습니다.

## 응답과 상태

설계 요청에는 읽기 전용 목표·조건·현재 회로·측정 결과·실제 검사 계약과 `request_id`가 있습니다. 응답은 같은 ID, 전체 넷리스트, 변경 설명을 반환합니다. 원문 목표나 검사기 파일을 수정해서 통과시키면 안 됩니다.

| 상태 | 의미 |
|---|---|
| `validating_initial` | 최초 회로 저장 후 검사 중 |
| `awaiting_chat_designer` | 다음 설계 응답을 기다림 |
| `validating_candidate` | 받은 후보를 검사 중 |
| `validation_interrupted` | 검증 작업 중단. 같은 후보·기존 최선 보존, resume 가능 |
| `implemented_scope_passed` | 구현돼 검증 가능한 범위의 목표 통과 |
| `candidate_budget_exhausted` | 정한 후보 예산 종료 |
| `invalid_response_budget_exhausted` | 응답 형식 오류 예산 종료 |

중단은 설계 미달과 다릅니다. 완료된 판정에도 `passed_sampled_model_case`, `failed_in_model`, `execution_error`, `unverified_adapter`, `unverified_model`이 구분됩니다. UI에서 모두 성공/실패 두 값으로 합치지 않는 것이 좋습니다.

## 파일과 버전

`STATE.json`이 기준이고 best/report는 복구 가능한 조회 자료입니다. 동시에 같은 세션을 관리하는 프로세스는 하나로 두고, UI가 결과 파일을 오래 잠그지 않도록 합니다. 임시 파일이 있다고 준비 완료로 보지 않습니다. 원문·계획·코드·회로가 바뀌면 과거 기록을 덮어쓰지 않고 새 세션으로 시작합니다.

이 공유 폴더의 `tests/fixtures`는 독립 구조 테스트용, `examples`는 읽기용 결과 요약입니다. 둘을 실제 실행 완료 `runs/`로 가장해서 넣지 않습니다. 이전 과거 루프와 현재 고정 하네스 루프도 구분합니다.
