> 최신 진입점은 `run_datasheet_design.py start --session <새세션> --pdf <PDF> --target <모델명> --settings settings/generic_opamp_25c.json --env-file .env`입니다. [최초 설계](COLD_START.md), [운영 루프](CONTINUOUS_WORKFLOW.md), [이번 갱신](LATEST_UPDATE_20261118.md)을 함께 확인하세요. 아래 단계별 명령은 개별 단계 검사에도 사용합니다.

# 설치·실행·재개

## 환경과 테스트

확인 환경은 Windows, Python 3.12, LTspice입니다. Python 라이브러리는 `requirements.txt`에 있습니다. LTspice 프로그램과 NVIDIA/IEEE 키는 포함하지 않았습니다.

```powershell
cd EDAI_OpAmp_Rebuild
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

현재 공유본 검사 결과는 `docs/SHARE_MANIFEST.json`을 확인하세요. 원본 로컬 환경은418개를 통과했으며, 공유본에는 PDF/개인 실행 자료가 없어 일부 검사를 건너뜁니다. 이 검사는 API나 전체 EDA 실험을 자동 실행하지 않습니다.

`.env.example`을 참고해 `.env`를 직접 만듭니다. 기본 문서 파싱에는 `NVIDIA_API_KEY`를 사용합니다. `IEEE_API_KEY`는 선택 기능입니다. 설계 모델의 API 키나 모델명은 현재 연결돼 있지 않습니다.

## 원문 없이 먼저 가능한 EDA 확인

LTspice 위치는 자신의 설치 경로로 바꿉니다.

```powershell
$ltspice = "$env:LOCALAPPDATA\Programs\ADI\LTspice\LTspice.exe"
.\.venv\Scripts\python.exe run_testbench_validation.py --ltspice $ltspice
.\.venv\Scripts\python.exe run_opamp_testbench_validation.py --ltspice $ltspice
```

위 명령은 이론값이 알려진 기준 회로로 실행·측정 코드를 확인합니다. LM358B 사양 전체 달성이나 물리 op amp 자동 설계 시험이 아닙니다.

## PDF부터 시작하는 순서

원본 PDF를 `inputs/lm358.pdf` 등 로컬 위치에 준비합니다. 원래 실험은 68쪽짜리 LM358 계열 문서에서 LM358B를 선택했습니다. 문서가 개정되면 해시·페이지·행 ID가 달라질 수 있습니다.

```powershell
.\.venv\Scripts\python.exe run_pdf_overview.py --pdf inputs/lm358.pdf --target LM358B --output runs/lm358b_demo
.\.venv\Scripts\python.exe run_pdf_layout.py --run-dir runs/lm358b_demo --env-file .env
.\.venv\Scripts\python.exe run_spec_pipeline.py --run-dir runs/lm358b_demo
```

마지막 명령은 의미 주석을 기다릴 수 있습니다. `spec_pipeline/spec_02_input_packet.json`을 AI에게 주고 해당 행 ID에 맞는 주석을 작성합니다. 이후 생성되는 `spec_03_llm_input_packet.json`을 검토해 원문 대조 응답을 준비합니다. 아래 파일명은 **새로 작성할 파일의 예시**입니다.

```powershell
.\.venv\Scripts\python.exe run_spec_pipeline.py --run-dir runs/lm358b_demo --annotations manual_inputs/my_semantic_annotations.json --semantic-review manual_inputs/my_semantic_review.json
.\.venv\Scripts\python.exe run_chart_references.py --run-dir runs/lm358b_demo --review manual_inputs/my_chart_review.json
.\.venv\Scripts\python.exe run_hkg.py --run-dir runs/lm358b_demo
.\.venv\Scripts\python.exe run_pdg.py --run-dir runs/lm358b_demo
```

PDG의 첫 실행은 원문/노드 참조용 입력 패킷을 생성합니다. 그 패킷에 맞춘 주석 파일로 다시 실행합니다.

```powershell
.\.venv\Scripts\python.exe run_pdg.py --run-dir runs/lm358b_demo --annotations manual_inputs/my_pdg_annotations.json
.\.venv\Scripts\python.exe run_measurement_plan.py --run-dir runs/lm358b_demo --project-policy planning_inputs/my_project_policy.json
```

샘플 프로젝트 정책은 원래 HKG/PDG 지문에 묶여 있습니다. 새로 생성한 그래프와 다르면 `stale` 오류가 나는 것이 정상입니다. 원문/행/조건/목표 선택을 검토한 뒤 `input_hkg_fingerprint`와 `input_pdg_signature`를 새 그래프에 명시적으로 연결해야 합니다. 코드 함수는 `support.source_checks.fingerprint`, `pdg_04_schedule.pdg_signature`입니다. 다른 PDF라면 `row_decisions`부터 새로 검토해야 하며, 지문만 바꿔 검사를 통과시키면 안 됩니다.

`manual_inputs/lm358b_*.json`은 원래 검토 사례입니다. 새 원문/패킷에 맞는지 검사 없이 정답으로 적용하지 않습니다. 일부 문서의 `ready_for_design=false`는 검토 범위와 미확정 항목을 남기는 표시이므로 임의로 true로 바꾸지 않습니다.

## 전체 검증과 설계 루프

아래 명령은 앞 단계의 유효한 원문/그래프/검사 계획이 생성된 `run-dir`를 요구합니다. `examples`의 요약 JSON만 복사해서 대체할 수 없습니다.

```powershell
.\.venv\Scripts\python.exe run_verification_pipeline.py --run-dir runs/lm358b_demo --netlist examples/lm358b_25c/candidate_18p.inc --output-dir runs/verification_demo --ltspice $ltspice
.\.venv\Scripts\python.exe run_fixed_harness_loop.py start --run-dir runs/lm358b_demo --session runs/loop_demo --netlist examples/lm358b_25c/candidate_80p.inc --ltspice $ltspice --max-candidates 3
```

`max-candidates 3`은 최초 회로와 수정 후보 두 개입니다. 초기 회로가 목표를 이미 만족하면 요청 없이 종료될 수 있습니다.

`REQUEST_001.json`에 목표·시험 계약·현재 회로·피드백이 있습니다. 설계자가 `request_id`, 전체 ASCII `netlist`, `summary`, `changes`를 포함한 응답 JSON을 작성합니다. `hypotheses`와 `tradeoffs`도 함께 기록하는 형식입니다. 프로그램이 API로 자동 생성하는 단계는 아닙니다.

```powershell
.\.venv\Scripts\python.exe run_fixed_harness_loop.py submit --session runs/loop_demo --response my_response.json --ltspice $ltspice
.\.venv\Scripts\python.exe run_fixed_harness_loop.py status --session runs/loop_demo
.\.venv\Scripts\python.exe run_fixed_harness_loop.py resume --session runs/loop_demo --ltspice $ltspice
```

`start` 또는 `submit`에 `--defer-validation`을 넣으면 상태/후보 저장 후 검증 전에 멈춥니다. 검증 인프라 중단은 같은 후보를 보존하고 한 번 자동 재시도한 뒤 계속 실패하면 `validation_interrupted`로 멈춥니다. 이후 resume은 새 설계 제안 기회를 소모하지 않습니다. **측정이 정상 완료된 성능 미달**에는 이 인프라 재시도를 쓰지 않습니다.

완료 상태에서 `resume --session ...`은 LTspice 없이 BEST/REPORT를 복구할 수 있습니다. 같은 세션은 한 관리 프로세스에서 실행합니다. 코드를 수정한 뒤 과거 동결 세션을 강제로 재개하지 않습니다.

## 선택: IEEE 메타데이터 검색

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ieee.txt
```

`run_design_context.py --help`의 `--ieee-env-file`, `--mcp-deps`를 지정합니다. `--mcp-deps`는 MCP를 설치한 환경의 site-packages 경로입니다. 제목·초록 검색이며 원문 전체, 회로 식/소자값 추출이나 필수 설계 지침을 보장하지 않습니다. 현재 주 검증 루프에 매번 자동 연결된 검색도 아닙니다.

모든 명령은 `--help`로 실제 옵션을 확인할 수 있습니다. 오래된 `run_design_loop.py`, `run_extended_design_loop.py`는 개발 단계 보존용으로, 현재 주 루프는 `run_fixed_harness_loop.py`입니다.
