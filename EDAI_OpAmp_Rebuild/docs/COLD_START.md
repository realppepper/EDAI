# 데이터시트부터 시작하는 경로

## 입력과 범위

새 진입점 `run_datasheet_design.py`는 PDF, 대상 제품명, 명시적인 공학적 설정을 받는다. 기존 회로 파일이나 성공 이력을 입력받는 인수는 없다. 고정 일반 MOS 모델과25°C·1채널·현재 구현된 검사 범위를 사용한다. 데이터시트가2채널 제품이어도 패키지와 채널 간 결합까지 구현했다는 뜻은 아니다.

설계용 모델 API 전송은 아직 연결하지 않았다. 코드가 단계별 요청을 만들고, 현재 채팅/이력 없는 에이전트가 응답 JSON을 작성한다. 문서 이미지 파싱은 기존 NVIDIA Nemotron Parse API를 이용한다. 키는 환경변수 또는 .env에서 읽으며 로그/상태에 키 값을 저장하지 않는다.

## 단계

```text
PDF 전체 탐색 → 후보 페이지 이미지/파싱 → 원문 고정 행
 → 의미 보완 → 독립 의미 검토 및 코드 대조
 → HKG → 출처 기반 PDG → 명시적 목표 선택/검사 계획
 → 현재 검사 범위의 설계 입력 승인
 → 최초 회로 요청(기존 회로·측정 이력 없음)
 → 최초 넷리스트 검증/전체 EDA
 → 기존 연속 운영 루프 자동 시작
```

문서 검토에서 수정 요구가 나오면 최초 설계로 넘어가지 않고 사양 보완 단계로 돌아간다. 모든 원문 행을 추적하고, 온도 파생 행과 온도 계수의 제외/연기 이유를 보존한다. 원문의 일반 `2V step`과 프로젝트가 선택한 입력 스텝은 구분한다. 전원 레일의 positive/negative 표기는 원문에 남기고 실제 DUT fixture에서는 V_plus/V_minus로 정규화한다. 알 수 없는 레일은 임의로 음전원으로 취급하지 않고 거부한다.

`ready_for_design=false`인 원문/그래프의 전역 상태를 true로 덮어쓰지 않는다. 별도 `DESIGN_ADMISSION.json`은 현재 구현된 검사에 필요한 검토된 부분만 승인한다. 지원되지 않는 검사에 포함된 원문 의미 불확실성은 별도 연기 목록에 남기며, 그 항목을 통과로 집계하지 않는다. 곡선 수치나 제조 적합성 전체를 승인한 것이 아니다.

## 명령

```powershell
python run_datasheet_design.py start --session runs/cold_start/new_job --pdf <원본.pdf> --target LM358B --settings settings/generic_opamp_25c.json --env-file <.env>
python run_datasheet_design.py status --session runs/cold_start/new_job
```

`NEXT_ACTION.json`의 status/pending_request에 따라 사양 보완, 의미 검토, PDG, 프로젝트 정책, 최초 회로 응답을 각각 작성한다. 각 기존 단계의 입력 fingerprint와 현재 요청의 해시를 지켜야 한다.

```powershell
python run_datasheet_design.py submit --session runs/cold_start/new_job --response <현재 단계 응답.json>
```

최초 회로 요청에는 사양, 시험 조건, 허용 모델, 단자/소자 규칙만 있다. 기존 성공 회로·시뮬레이션 결과·회로 생성 템플릿 본문은 제공하지 않는다. 최초 응답은 완전한 ASCII 넷리스트와 요청 ID/파일 SHA256으로 결합한다. 형식 오류는 기록하고 같은 응답을 덮어쓰지 않는다.

```powershell
python run_datasheet_design.py resume --session runs/cold_start/new_job --ltspice <LTspice.exe>
```

완료된 최초 전체 검증은 `<session>/initial/validation`에 저장한다. 그 결과를 기준으로 `<session>/workflow`를 자동 생성한다. 이후의 지침/회로 요청은 기존 `run_opamp_workflow.py`로 응답을 제출하며, 상태는 workflow/NEXT_ACTION.json에 표시한다. 이는 별도 수동 회로 이관이 아니라 같은 세션 아래 연결된 기존 제어기의 응답 API를 사용하는 것이다.

```powershell
python run_opamp_workflow.py propose --session runs/cold_start/new_job/workflow --response <지침 응답.json>
python run_opamp_workflow.py submit --session runs/cold_start/new_job/workflow --response <회로 응답.json> --defer-validation
python run_datasheet_design.py resume --session runs/cold_start/new_job --ltspice <LTspice.exe>
```

마지막 resume은 저장된 최초 검증을 다시 시뮬레이션하지 않고, 진행 중인 연결 워크플로를 재개한다. 코드·PDF·설정·접수 응답이 달라지면 동결 검사가 중단한다. 성공과 예산 종료를 구분한다.

## 코드

- `startup_01_initial_design.py`: 현재 검사 범위의 출처 검토 승인, 이력 없는 최초 요청/응답 검증.
- `startup_02_datasheet.py`: 문서 단계의 응답 전달, 오류/중단 상태, 최초 EDA와 기존 워크플로 연결.
- `run_datasheet_design.py`: 시작/응답/재개/상태 진입점.
- `settings/generic_opamp_25c.json`: 명시적 프로젝트 측정 설정. 원문 사양이나 과거 성공 회로의 값이 아니다.
- `tests/test_cold_start.py`: 원문 불확실성의 범위 구분, 최초 요청의 이력 부재, 모델/요청 결합, 단계 생략 방지, 수정 응답 복구, 원문 스텝/레일 해석 검증.

문서 의미 검토는 오류를 줄이는 절차이지 완전한 정확성 증명은 아니다. 현재 하나의 LM358B PDF에 대한 실제 확인 기록과 새 최초 회로의 결과는 실행 폴더의 보고서에서 구분한다. 다른 데이터시트에서도 같은 인터페이스를 쓰지만, 새로운 표 형식·사양·측정 어댑터는 추가 검증이 필요하다.
