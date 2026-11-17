# Optuna 고정 토폴로지 사이징 — 선택 기능

## 설치와 범위

2026-11-17 Optuna 5.1.0을 프로젝트의 `.optuna_deps/`에 설치했다.
공용 Python 패키지는 변경하지 않았고 이 폴더는 Git에서 제외한다.
CLI는 이 폴더가 있으면 사용하며, 다른 환경에서는 `requirements-optuna.txt`를 설치하면 된다.

```powershell
python -m pip install --target .optuna_deps -r requirements-optuna.txt
```

현재는 일반 MOS 모델의 `FIRSTAMP` 단일 서브서킷과 BIAS 노드를 사용하는 기동 어댑터를 대상으로 한다.
PDK나 임의의 다른 토폴로지에 바로 적용되는 범용 사이징 엔진이라고 주장하지 않는다.
공정 모델 카드나 토폴로지를 바꾸지 않고, 설정에 명시한 R/C 값 또는 MOS W/L만 조정한다.

## 파일

| 파일 | 역할 |
|---|---|
| `run_optuna_sizing.py` | 설치 확인, 입력 고정, Optuna/SQLite, 후보 보존, 최종 검증 연결 |
| `opamp_pipeline/optuna_01_parameters.py` | 탐색 범위·소자 그룹 검증, 한정된 파라미터 편집, 전력 목적함수 |
| `opamp_pipeline/optuna_02_screening.py` | 기존 HKG/PDG/검사 계획 확인, 기동·선별 시뮬레이션, 기존 계약·측정·판정 재사용 |
| `opamp_pipeline/optuna_03_loop_bridge.py` | 기존 설계 루프의 호출 조건, 예산, Optuna 실행·검증 및 LLM 반환 |
| `opamp_pipeline/optuna_04_designer.py` | LLM이 제안한 변수·범위·근거와 요청/후보 바인딩 검사 |
| `opamp_pipeline/optuna_05_acceptance.py` | 전력 동률 처리, 전체 구현 범위 판정, 제한된 후보 재검증 |
| `opamp_pipeline/optuna_06_startup.py` | 완전한 기동 파형의 수치 판정 및 기동 보완 근거 확인 |
| `settings/optuna_tl071_pilot.json` | TL071C 사례용 명시적 변수/범위·선별 항목 설정 |
| `requirements-optuna.txt` | 선택 의존성 버전 |

## 첫 실험의 정의

- 기존 TL071C 목표와 30V/25°C 시험 조건을 유지한다.
- RBREF 바이어스 저항, CCOMP 보상 커패시터, MINL/MINR 공통 폭의 세 변수를 탐색한다.
- 차동쌍은 같은 변수로 함께 바꾸며, 단자 연결·모델 카드·기타 소자는 유지한다.
- 기본 회로 파라미터를 첫 시행으로 넣는다. 최초 회로는 별도 파일로 보존한다.
- 기동을 확인하고, 소스 계획에 있는 IQ·GBW·위상여유·양방향 슬루율로 후보를 선별한다.
- 선별 항목을 만족하는 후보 가운데 샘플링한 전원 조건의 최대 정지 전력(mW)을 최소화한다.
- 선별 미달은 Optuna 제약 위반으로 기록한다. 모델 미검증/측정 오류를 통과로 취급하지 않는다.
- 조건 계약 오류는 최적화 중단 사유이며, 시뮬레이터 실행 실패를 물리적 사양 미달로 단정하지 않는다.
- `--validate-best`를 주면 후보 순위에 따라 기존 전체 검증을 실행한다. 첫 후보가 미달하면 다음 후보를 확인하며 기본 최대3개다.
- 선별만 통과한 후보는 최종 회로로 자동 채택하지 않는다. 원본 회로도 교체하지 않는다.

## 실행 예시

프로젝트 루트에서 Python과 기존 검증 의존성을 사용할 수 있는 환경으로 실행한다.

```powershell
python run_optuna_sizing.py `
  --netlist runs/cold_start/20261117_tl071/final/TL071C_PS_generic_FINAL.inc `
  --run-dir runs/cold_start/20261117_tl071/document `
  --config settings/optuna_tl071_pilot.json `
  --output-dir runs/optuna_sizing/my_study `
  --ltspice "C:/Users/wowyo/AppData/Local/Programs/ADI/LTspice/LTspice.exe" `
  --trials 4 --time-budget 180 --bench-timeout 20 --validate-best
```

`--trials`는 추가 횟수가 아니라 기준 회로와 실패를 포함한 최대 누적 시행 수다.
탐색 시간 예산은 시행 사이에서 확인하며 기준 회로 교정과 최종 검증 시간은 별도다.
한 시행 중에도 각 시뮬레이션의 timeout은 적용된다. 총 실행 시간이 time-budget과 정확히 일치하지는 않는다.

## 보존과 재개

- `study.sqlite3`: Optuna 시행·파라미터·제약 기록
- `INPUTS.json`: 원본/계획/설정/검사 코드와 환경 서명
- `trials/trial_####/`: 후보 넷리스트, 기동·측정 데크, raw/log, 계약 영수증, 선별 결과
- `best_screened.inc`: 호환성을 유지한 출력 이름. 전체 검증을 요청했다면 그 결과로 선택한 복사본이며 자동 채택을 의미하지 않음
- `RESULT.json`: 진행 상태·후보 이력·선별 목적값·최종 검증 연결

같은 명령에 `--resume`를 붙이면 저장된 시행을 이어간다.
입력·설정·코드가 바뀌면 기존 결과를 보존하고 새로운 출력 폴더에서 시작한다.
중단 당시 RUNNING 시행은 실패로 남기고 그 산출물을 덮어쓰지 않는다.
SQLite는 이력을 보존하지만 sampler RNG는 seed에서 다시 만들므로,
중단하지 않은 실행과 재개 실행의 다음 후보가 완전히 같다는 보장은 하지 않는다.
효과 비교 실험은 동일한 초기 회로/목표/예산/seed로 새 연구를 시작해 비교한다.

## 해석상의 한계

소수 시행은 설치·연결 확인용이다. 최적해, 하네스 효과, LLM 대비 우위를 입증하지 않는다.
토큰 절감 효과도 이번 실험에서 측정하지 않는다. 설계 API를 호출하지 않는다.
전체 검증에서도 일반 모델의 미검증 항목은 그대로 남는다.
별도 추가 정착시간 과제 등 선별/전체 기본 계획 밖의 요구사항을 만족했다고 주장하지 않는다.

공식 문서: https://optuna.readthedocs.io/en/stable/tutorial/10_key_features/001_first.html

저장·재개: https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/001_rdb.html

## 기존 루프 연결

이제 별도 실행 도구뿐 아니라 `harness_03_loop.advance()`의 선택 단계로 연결돼 있다.
기본값은 꺼져 있으며 새 세션 시작 시 `--optuna-config`로 켠다.

```powershell
python run_fixed_harness_loop.py start `
  --session runs/my_connected_loop `
  --netlist path/to/initial.inc `
  --run-dir path/to/datasheet_run `
  --ltspice path/to/LTspice.exe `
  --optuna-config settings/optuna_tl071_pilot.json `
  --optuna-trials 4 --optuna-rounds 1 --max-candidates 3
```

연결 정책은 다음과 같다.

1. 기존 검증으로 현재 동작·측정 상태와 목표 미달을 확인한다. 이번 버전은 초기 경량 검사만 따로 분리하지 않았다.
2. 구현된 검증 범위가 이미 만족되면 Optuna 없이 종료한다. 제조사 전체 사양 통과를 의미하지 않는다.
3. 기동 통과 후 유효한 수치 미달이 있거나, 현재 회로와 일치하는 완전한 기동 파형으로 기동 미달을 확인한 경우 변수 탐색을 제안할 수 있다.
4. 선별4종 밖의 유효한 수치 미달도 탐색을 허용한다. 실행/측정 오류나 유효하지 않은 측정 전제는 사양 미달 점수로 바꾸지 않는다.
5. Optuna 후보는 현재 하네스와 원래 계획으로 전체 검증한다. 첫 후보가 미달하면 예산 내 다음 후보를 검사한다. 선별 통과만으로 채택하지 않는다.
6. 미해결이면 기존 LLM 요청에 `numeric_sizing_feedback`을 첨부한다.
7. 기본 최적화 호출은 세션당1회다. 추가 LLM 수정 뒤 무제한 재호출하지 않는다.

LLM 설계 API는 여전히 호출하지 않는다. 현재 채팅이 기존 REQUEST/RESPONSE 형식으로 설계 역할을 맡는다.
source target/검사/하네스는 유지하고, Optuna는 소자 파라미터만 조정한다. 이전 통과 항목을 잃은 후보는 best로 올리지 않는다.
변수와 범위는 해당 회로의 현재 값과 일치해야 한다. 설정이 맞지 않으면 임의로 보정하지 않고 설계자에게 돌려준다.

`run_opamp_workflow.py` 및 `run_datasheet_design.py`의 새 세션 시작에도 같은 Optuna 설정/예산 옵션을 전달할 수 있다.
전체 PDF/API 추출 경로를 이번 연결 시험에서 새로 실행한 것은 아니다.
Harness² 워크플로에서의 물리적 개선이 지침 개선의 인과 효과를 입증하는 것은 아니며,
숫자 조정 결과는 `origin=optuna_numeric_repair`로 구분한다.

중단된 최적화는 `run_fixed_harness_loop.py resume --session ... --ltspice ...`로 재개한다.
완료 worker 결과를 이미 등록했다면 진행 상태를 복구하며 worker를 중복 호출하지 않는다.
실행 중인 과거 세션의 코드 서명을 바꿔 이 기능을 주입하지 않고 새 세션을 사용한다.

연결 시험 중 실제 중단·재개에서 RUNNING 시행을 별도 행으로 다시 추가하던 표시 오류를 발견했다.
현재는 같은 trial 번호의 기존 레코드를 `interrupted_execution`으로 갱신해 시행 수가 늘어나지 않는다.
수정 전 중단 시험은 과거 기록으로 유지하며, 현재 코드의 새 세션으로 중복 없는 실제 시행 수를 확인했다.
이력 레코드 수와 실제 SQLite 시행 수를 혼동해 최적화 성능을 평가하지 않는다.

## 미달 정도 전달 방식 보완

Optuna에 전달하는 제약은 `failed_screening_cases` 하나에서 `signed_normalized_per_test_v1`로 변경했다.
원래 합격 기준과 전력 목적함수는 바꾸지 않았다.

- 하한 조건: `(목표 - 측정값) / abs(목표)`
- 상한 조건: `(측정값 - 목표) / abs(목표)`
- 양수는 미달,0이하는 만족이다. 단위 변환에 따라 점수가 달라지지 않는다.
- 각 전원·방향·검사 규칙을 별도 제약으로 전달한다. 통과한 방향의 여유로 미달 방향을 상쇄하지 않는다.
- 영(0) 목표는 별도 양의 normalization_scale이 없으면 점수를 임의로 만들지 않는다.
- 미측정,미검증 모델,잘못된 측정 전제는 유효한 물리 미달 정도로 취급하지 않는다.
- 후보별 `CONSTRAINT_FEEDBACK.json`에 규칙·목표·측정값·정규화 미달·합계/최댓값을 남긴다.

합격 후보의 선택 목적은 여전히 정지 전력 최소화다. 제약 거리 보완이 최적해나 적은 시행 내의 해결을 보장하지 않는다.
코드 버전이 달라졌으므로 기존 동결 연구를 강제 재개하지 않고 새 출력 폴더로 비교한다.

## LLM이 변수와 범위를 제안하는 모드

새 세션에서 고정 `--optuna-config` 대신 `--optuna-from-designer`를 지정한다.
두 옵션은 함께 사용하지 않는다. `run_opamp_workflow.py`와 `run_datasheet_design.py`에도 같은 옵션이 있다.

```powershell
python run_fixed_harness_loop.py start `
  --session runs/my_designer_sizing `
  --netlist path/to/initial.inc --run-dir path/to/datasheet_run `
  --ltspice path/to/LTspice.exe `
  --optuna-from-designer --optuna-trials 5 --optuna-rounds 1
```

유효한 수치 미달이 있으면 기존 LLM 요청에 `numeric_sizing_proposal`을 추가한다.
LLM은 회로를 직접 수정하는 기존 응답 또는 다음 숫자 탐색 제안을 선택할 수 있다.
현재 채팅이 LLM 역할을 맡으며 설계 API를 자동 호출하지는 않는다.

```json
{
  "action": "propose_sizing",
  "request_id": "요청의 ID",
  "request_sha256": "요청 파일의 SHA256",
  "based_on_candidate_sha256": "요청에 있는 candidate_file_sha256",
  "sizing_proposal": {
    "reason": "관찰한 미달과 변수 선택의 가설",
    "evidence_case_ids": ["실제 미달 사례 ID"],
    "risks": ["성능 저하 가능성과 재검사할 항목"],
    "trials": 3,
    "parameters": [
      {"name": "compensation_F", "elements": ["CCOMP"], "field": "value",
       "low": 2e-11, "high": 8.4e-11, "log": true,
       "reason": "이 소자 그룹과 범위를 선택한 근거"}
    ]
  }
}
```

형식 검사를 통과하면 코드가 현재 넷리스트에서 baseline 값을 읽고 설정 파일을 생성한다.
알 수 없는 소자,모델/연결 편집,목표 변경,NaN/무한 범위,예산 초과,오래된 요청/다른 후보를 거부한다.
소자 묶음의 현재 값 일치·범위는 검사하지만,선택 자체가 회로적으로 최적인지는 증명하지 않는다.
허용 필드는 단순 R/C 값과 MOS W/L이고 단위는 각각Ohm/F/m다.

이번 버전은 현재값을 범위에 포함해야 한다. 시작 회로 평가가 시행 예산에 포함되는 기존 방식과 일치시키기 위한 제약이다.
예를 들어 현재84pF에서20..40pF만 제안하면 거부하며,코드가 몰래 범위를 늘리지 않는다.
현재값을 제외한 탐색 구간을 쓰려면 시작 회로 평가/예산 처리를 분리하는 후속 보완이 필요하다.

승인된 요청·응답·생성 설정은 `sizing_proposals/proposal_###/`에 별도 보존한다.
같은 응답을 다시 제출해도 최적화를 중복 실행하지 않는다.
미해결 시 이전 요청을 덮어쓰지 않고 다음 요청에 실제 Optuna 이력을 첨부한다.
최선 후보는 기존 전체 검증과 회귀 검사 후에만 루프 후보로 등록한다.

## 2026-11-17 연결 정책 보완

기동 검사는 부분 선별 항목의 전원만이 아니라 원래 검사 계획에 존재하는 모든 전원점에서 실행한다.
기동 미달은 내부 전압의 마지막20µs 변동, 출력 중간 전압 오차, BIAS 활성 기준을 각각 정규화해 제약으로 전달한다.
불완전/비유한 파형이나 시뮬레이터 실패는 시행 실패로 남기고 물리적 미달 거리를 만들지 않는다.
미달 기동 파형은 이후 성능 측정의 초기 추정값으로 사용하지 않는다.

기동에 실패한 시행은 전력을 측정하지 않으므로 `objective_power_mW`는 null이다.
이 시행의 Optuna 값은 명시적으로 `startup_constraint_violation_not_power`이며 전력값과 구별한다.
이 시행은 항상 기동 제약을 위반하므로 합격 후보가 될 수 없다.
기동 통과 후에는 기존 정지 전력 목적함수와 IQ/GBW/PM/SR 제약을 사용한다.
LLM은 `startup_repair_eligible` 요청에서 `OPERATIONAL-STARTUP`을 근거로 R/C 또는 W/L 범위를 제안할 수 있다.
실패 원인이 파라미터만으로 해결 가능한지는 여전히 가설이며 구조 변경이 필요하면 LLM에 돌아간다.

전력이 `max(1e-6mW, 최저 전력의1e-6배)` 이내로 차이나면 동률로 취급한다.
동률 후보는 선별한 성능 중 가장 작은 정규화 여유가 큰 순서로, 그것도 같으면 시행 번호순으로 선택한다.
이 허용 오차는 후보 순위에만 적용하며 원래 사양의 합격 기준을 완화하지 않는다.

전체 검증은 동일한 하네스의 `qualified_measurement_families`와 필수 기동 게이트로 판정한다.
22개 미검증 항목은 그대로 남기며, 단일 채널 한계 등 범위 밖 `unverified_adapter`가 있다는 이유로
구현 범위를 모두 통과한 후보를 잘못 실패로 표시하던 요약 판정도 바로잡았다.
범위 안에서 측정 누락/오류가 난 후보는 수치적 개선 후보로 선택하지 않는다.

전체 재검증 후보 예산은 `--validation-candidates`(기본3, 허용1..20)으로 제한한다.
모두 미달하면 실제 전체 검사에서 미해결 조건이 적은 유효 후보와 이력을 반환하되 성공으로 판정하지 않는다.
전체 측정이 유효한 후보가 하나도 없으면 `completed_no_qualified_full_candidate`로 반환한다.
각 후보의 `full_validation_trial_N/`과 판정 이력을 보존하고, 재개 시 완료된 전체 검증은 서명/원자료를 확인해 중복 실행하지 않는다.
기존 연구는 코드 서명이 달라졌으므로 새 출력 폴더에서 진행한다.
