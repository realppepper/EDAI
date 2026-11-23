# EDAI 구조 생성 시스템 (`edai/`)

OP-Amp 데이터시트 PDF 를 넣으면 분석(HKG·PDG) → 구조 후보 → 크기 정하기·측정 → 고치기 → 하네스 → 최종 회로도까지
한 번에 돌리고, 과정과 결과를 웹 화면으로 보여 준다.

- 데이터시트 분석과 하네스는 이 저장소 루트의 **박준석 시스템(`ai_analog_designer/`)을 불러 쓴다.** 고친 곳은 아래 시뮬레이터 부분뿐이다.
- 박준석 하네스는 원래 LTspice 로 시뮬레이션한다. 앞 단계(구조·크기)를 ngspice + GF180 PDK 로 만들었으므로
  하네스도 같은 기준이 되게 이 브랜치에서 박준석 파일 3개를 고쳤다 (`AV_SIMULATOR=ltspice` 면 LTspice 그대로):
  - `ai_analog_designer/neuro_symbolic_verifier/sim_backend.py` (새 파일): LTspice 문법 회로를 ngspice 로 옮겨 돌리고 LTspice 형식 `.log` 를 씀
  - `ltspice_runner.py`, `deterministic_testbench.py`: 시뮬레이터 호출을 `sim_backend.run_spice` 로
  - `hermes_core/hermes_workflow.py`: PDG 관문에서 실격한 회로는 0% 로 봐서 우리 씨앗 회로(설계도) 단계가 돌게

## 단계

| 단계 | 하는 일 | 코드 |
|---|---|---|
| 1. 데이터시트 분석 | PDF → HKG(스펙·핀), PDG, 측정 계획 → 판정 항목 | `extract_datasheet.py` (박준석 시스템 호출) |
| 2. 모델 구조 후보 | 스펙 문장 → FLAN-T5 가 구조 표 후보 여러 개 | `generate_candidates.py` |
| 3. 크기 정하기·측정 | 후보마다 원래 / 바이어스 정리 / 상보 뒤집기 / 쌓인 규칙 모양을 gm/ID 로 크기 정하고 ngspice 로 측정 | `select_structure.py --repair` |
| 4. 실패한 구조 고치기 | 스펙 절반 이상 통과하는 후보가 없으면: 규칙 자동 적용 → LLM 이 블록(입력단·출력단·보상·바이어스) 단위로 고침 → 통한 방법을 규칙으로 남김 | `structure_doctor.py`, `structure_blocks.py`, `structure_rules.py` |
| 5. 구조 고르기 | 입력 범위·이득 노드·통과 수로 순위 | `rank_v2.py` |
| 6. 규칙 적용 | 상보 뒤집기, 캐스코드 | `pipeline.py` |
| 7. 하네스 | 고른 회로를 씨앗으로 박준석 하네스가 LLM 으로 반복 개선 | `run_harness.py` |
| 8. 최종 회로도 | 하네스 전·후 회로도 SVG/PNG | `make_schematic_svg.py` |

LLM 은 NVIDIA 키로 부른다 (Claude 는 부르지 않음). LLM 에 보낸 내용과 받은 답은 실행 폴더의 `doctor/`, `harness/` 에 남는다.

## 처음 설치 (WSL Ubuntu 22.04)

1. ngspice 43 을 `~/ngspice` 에 (apt 의 36 은 GF180 모델을 못 읽음), GF180 PDK 를 `~/pdk/gf180mcu_fd_pr` 에
2. 회로도용 Node.js 를 `~/node`, netlistsvg 와 @resvg/resvg-js 를 `~/netlistsvg` 에 (`npm install netlistsvg @resvg/resvg-js`)
3. 파이썬 패키지: `python3 -m venv ~/.venvs/edai && ~/.venvs/edai/bin/pip install -r edai/requirements.txt`
4. 모델: 구글 드라이브 `2026_2/flan_t5_structure` 를 `edai/models/flan_t5_structure/` 에 풀기
5. 키: `edai/.env` (또는 저장소 루트 `.env`) 에 `NVIDIA_API_KEY=...` (각자 발급, git 에 올리지 않음)

## 실행

```bash
cd edai
~/.venvs/edai/bin/python ui_server.py      # 브라우저에서 http://localhost:8765
```

- **새 설계**: 데이터시트 PDF 를 끌어다 놓고 "설계 시작"
- **지난 결과 불러오기**: `edai/runs/` 아래 실행 폴더 목록. 팀원에게 받은 실행 폴더도 여기에 넣으면 보인다
- **다시 돌리기 / 멈추기**: 단계를 골라 그 단계부터 다시 (돌고 있으면 멈춘 뒤)
- 결과 화면은 실행 폴더의 `report.html` 이라 폴더만 있으면 더블클릭으로도 열린다

## 팀이 같이 쌓는 파일 (git 에 올림)

| 파일 | 내용 |
|---|---|
| `data/structure_rules.json` | LLM 이 쓴 구조 규칙 (조건 → 블록 변환). 다른 칩 2개에서 통하면 정식, 계속 안 통하면 폐기. `python structure_rules.py` 로 목록 |
| `data/structure_experience.json` | LLM 고치기 시도 기록 (통한 것·안 통한 것) |
| `data/fixed_structures.json` | 고쳐서 동작한 구조 (모델 재학습용) |

## 폴더

- `edai/` 바깥(저장소 루트)은 박준석 시스템 원본. `harness2_library/` 에는 하네스가 돌 때 우리 씨앗(`EDAI_<부품>`)이 잠깐 들어갔다가 지워진다
- `docs/비교실험_기록.md` 구조 정하기 방식 비교 실험 기록
