# 우리 설계 루프에 맞춘 하네스²

2026-11-15. 조원 코드의 지침 제안→시험→채택 구조를 참고해 별도 외부 제어기를 구현했다. 조원 파일은 수정하지 않았고 코드를 그대로 가져오지 않았다.

## 흐름

```text
완료된 전체 검증 파이프라인과 현재 회로
 → 원본 회로·지침·사양·코드·결과 동결
 → 미달이 없으면 종료(no_unmet_cases)
 → 현재 채팅이 조건부 지침 변경안 1~2개 제안
 → 기존 지침(control)과 각 변경 지침으로 동일 출발 회로에서 수정 1회씩
 → 기존 전체 검증 파이프라인으로 각 회로 측정
 → 코드가 결과 대조
 → 엄격한 개선이면 시험한 지침 버전 전체를 로컬 채택, 아니면 기존 지침 유지
```

사양 추출·HKG·PDG·검사 계획·측정 코드·MOS 모델·실패/미검증 판정 규칙은 바꾸지 않는다. 현재 설계자와 지침 제안자 역할은 채팅이 맡는다. API 호출과 자동 모델 전환은 추가하지 않았다.

기존 `run_fixed_harness_loop.py`는 고정 지침으로 회로를 수정하는 실행기로 유지했다. 새 진입점 `run_harness2_loop.py`가 그 실행기를 호출한다. 외부 단계의 `harness2_enabled`는 true이고, 각 내부 실행의 지침은 고정되므로 내부 정책의 같은 플래그는 false이다. 이는 내부 루프에서 임의로 지침을 바꾸지 못하도록 역할을 나눈 것이다.

## 원본 구현에서 바꾼 부분

| 항목 | 우리 코드의 동작 |
|---|---|
| 변경 범위 | C3 조건부 설계 점검, C5 토폴로지 지식, C6 계산 지침에 규칙 추가만 허용 |
| 변경 불가 | 원래 규칙, C1/C2/C4/C7/C8, 판정 기준, 모델, 측정·재시도 정책, 검증 범위 |
| 추가 규칙 | 적용 조건·관측 근거 case ID·예상 효과·악화 가능성 필수 |
| 비교 기회 | 동일 회로·동일 기준 결과·같은 전체 검사, 각 분기 수정 1회 |
| 채택 조건 | 기존 지침 분기보다 실패 조건 집합이 엄격히 줄고, 원래 통과 조건 상실·판정 불가능한 필수 조건이 없어야 함 |
| 동률/오류 | 기존 지침 유지. 대조 실행 자체가 유효하지 않아도 채택하지 않음 |
| 지침 합성 | 미검증 합성을 하지 않음. 시험한 버전 전체만 선택 |
| 경험 축적 | 실패 후보의 메모리를 다른 지침에 섞지 않음. 전역 라이브러리 자동 주입 없음 |
| 원본 보존 | 세션 내부 ACTIVE.json만 선택 결과를 기록. 기본 정책 파일과 이전 실행은 그대로 유지 |
| 복구 | 같은 후보의 검증 재개는 기존 실행기 이용. 결정 후 원본 회로·지침으로 수동 rollback 가능 |

대조 분기는 대규모 성능 평가가 아니라 같은 수정 기회에서 지침 채택을 판단하는 최소 절차이다. 한번의 채택은 해당 과제의 근거이며 일반적인 성공률 향상을 입증하지 않는다. 자유로운 문장 자체의 물리적 타당성은 코드가 증명하지 못하므로, 강제된 회로 경계와 시뮬레이션을 통해 검사한다.

## 코드

- `opamp_pipeline/harness_06_evolution.py`: 동결, 지침 변경안 검사, 분기 실행 연결, 채택·복구.
- `run_harness2_loop.py`: 실행 진입점.
- `opamp_pipeline/harness_03_loop.py`: 기존 회로 수정/측정 실행기. 이번 작업에서는 수정하지 않음.
- `tests/test_harness_evolution.py`: 잘못된 변경·판정·중단·해시·복구 및 실제 파일 전달 경로 검사.

## 사용 순서

완료된 세 단계(core→impedance→overload)의 검증 폴더가 필요하다. 개별 측정 묶음이나 오래된 코드의 결과를 완전한 검증으로 인정하지 않는다. `check_chain`으로 코드·교정·회로·사양·결과의 연결을 검사한다. 코드 변경 때문에 기존 결과의 근거가 유효하지 않으면 새 기준 측정을 먼저 수행해야 한다.

```powershell
python run_harness2_loop.py start --session runs/harness2/my_round --baseline-pipeline <완료된 validation 폴더> --netlist <해당 candidate.inc> --run-dir runs/lm358b_overview_20261112
```

미달이 있으면 `PROPOSE_REQUEST.json`이 생성된다. 현재 채팅이 이 파일의 응답 형식에 맞게 지침 제안 JSON을 작성한다. 요청 ID와 파일 SHA256을 모두 반영해야 한다.

```powershell
python run_harness2_loop.py propose --session runs/harness2/my_round --response <지침 제안 JSON>
```

`branches/control/loop/REQUEST_001.json` 및 `branches/<변경안ID>/loop/REQUEST_001.json`이 생성된다. 각 요청으로 회로 수정 응답을 만들고 다음 명령으로 제출한다. `<분기명>`은 `control` 또는 변경안 ID이다.

```powershell
python run_harness2_loop.py submit --session runs/harness2/my_round --branch <분기명> --response <회로 수정 응답 JSON> --defer-validation
python run_harness2_loop.py resume --session runs/harness2/my_round --branch <분기명> --ltspice <LTspice.exe>
```

현재 컴퓨터에서는 LTspice 실행을 정상 Windows 실행 환경에서 수행한다. 검증 오류로 중단됐다면 같은 resume 경로를 사용하며, 새 지침/회로 제안으로 계산하지 않는다. 모든 분기의 수정 1회가 완료돼야 결정할 수 있다.

```powershell
python run_harness2_loop.py decide --session runs/harness2/my_round
python run_harness2_loop.py status --session runs/harness2/my_round
python run_harness2_loop.py rollback --session runs/harness2/my_round --reason "되돌리는 이유"
```

`DECISION.json`에는 모든 분기의 평가 근거를, `ACTIVE.json`에는 선택한 지침·회로·결과 경로와 해시를 보존한다. 이 버전을 이후 별도 실행에 사용할 때는 ACTIVE의 policy_path와 candidate_path를 기존 실행기의 `--harness`, `--netlist`에 지정한다. 전역 기본값을 자동으로 덮어쓰지 않는다. rollback은 원본 기준 회로와 지침으로 돌아가며 이전 결정 기록은 남긴다.

## 이번 확인의 범위

- 지침·요청 검증, 동률과 회귀 거부, 미검증 항목 통과 방지, 분기 준비 중단/재개, 결정·복구를 검사했다.
- 실제 요청 파일→지침 변경안→기존 회로 루프 요청→회로 응답→검증 재개→선택 경로도 자동 검사했다. 이 검사의 EDA 실행 및 결과 체인 부분은 주입한 시험 결과이며 실제 회로 성능 실험이 아니다.
- 실제23.5pF 회로의 완전한 검증 근거를 새 진입점으로 읽어58조건 통과/22조건 미검증을 확인하고, 미달이 없으므로 변경안을 만들지 않는 종료 경로를 확인했다.
- 오래된32pF 실행은 DC 검사 코드 변경으로 체인 검증에서 거부됨을 확인했다. 그 결과를 최신 코드의 실험으로 포장하거나 검사 경계를 느슨하게 하지 않았다.
- 새 지침을 실제 미달 회로에 적용한 LTspice 비교 실행과 하네스² 성능 향상 검증은 아직 하지 않았다. 토큰과 비용은 null이다.

근거는 `runs/harness2/20261115_implementation/` 및 `runs/harness2/20261115_success_gate/`에 보존한다.


## 첫 실제 실행 추가

이후32pF 기준을 최신 코드로 새 측정하고, 지침 변경안1개와 기존 지침을 각각 수정1회씩 시험했다. 두 분기 모두 같은23.5pF를 제안했고 각자 새 LTspice 전체 검증에서58통과/22미검증을 얻었다. 동률로 기존 지침 유지가 결정됐다. 이전에 적은 “아직 실제 실행 전”은 구현 직후 상태이며, 이번에 실제 제안→검증→선택 경로를 확인했다. 같은 비맹검 설계자가 같은 후보를 내었으므로 지침 성능 향상은 입증하지 못했다. 상세: `runs/harness2/20261115_first_live_round/REPORT.md`.


## 자동 채택 정책2 보완

이후 독립 비교에서 정상 측정된 대조의 새 미달까지 대조 사용 불가로 묶는 문제를 확인했다. outcome의 comparison_usable과 실제 선택 eligible을 분리해, 측정이 유효한 나쁜 대조가 좋은 변경 후보를 막지 않도록 했다. 측정 불가 대조/변경 후보 회귀는 계속 차단한다. 자동 검사248개 통과. 이전 세션은 동결 상태로 보존하고 일반 load의 코드 변경 방어는 유지했다. 변경 전 코드와 모든 원래 입력/결과를 확인하는 별도 재판정 스크립트로task03의58/58 변경 지침을 채택했다. 전역 기본 지침은 변경하지 않았다. 근거와task02 실패 분석: `runs/harness2/20261115_adoption_fix_analysis/REPORT.md`.
