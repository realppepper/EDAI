# EDAI

AI 기반 아날로그 회로 자동 설계 시스템

목표 성능 스펙만 입력하면 AI가 넷리스트를 생성하고, 오픈소스 시뮬레이터로 자동 검증한 뒤 목표 미달 시 재설계를 반복하는 시스템입니다.

## 현재 상태 (2026-11-11, 이 브랜치 기준)

데이터시트 하나에서 OP-Amp 회로 구조를 자동으로 정하는 단계까지 연결되어 있습니다.

```
데이터시트 PDF
  → (박준석 analogverifier) 특성표 HKG, 측정 계획, 핀 정보
  → 판정 항목·목표값 정리, PDG 핀 확인          spec_from_plan.py, pdg_check.py
  → FLAN-T5가 구조 후보 40개 생성                generate_candidates.py
  → 규칙 검사 → gm/ID 자동 크기 → ngspice 판정  select_structure.py
  → 통과 항목 수로 구조 선택 → 회로도          selection_curves.py, make_schematic_svg.py
  → 결과 페이지                                 make_selection_page.py
```

LM358B 결과: 후보 34개 → 규칙 통과 28 → 동작 12 (학습에 없던 구조 9) → 후보 1 선택, 판정 12개 중 7개 통과. 미달(이득, 출력 전류·출력 전압)은 크기 정하기 한계로 보고, 목표 기반 크기 최적화가 다음 과제입니다.

| 문서 | 내용 |
| --- | --- |
| [docs/박준석_시스템_연결.md](docs/박준석_시스템_연결.md) | analogverifier 결과를 어떻게 가져와 쓰는지, 발견한 문제, 같이 정할 것 |
| [docs/selection_lm358.html](docs/selection_lm358.html) | LM358B 구조 선택 전 과정 (내려받아 브라우저로 열기). 온라인: https://claude.ai/artifact/GCwRvsJoGBzT2eDYdz94tB (공유 요청 필요) |
| [docs/selection_tlv271.html](docs/selection_tlv271.html) | 같은 페이지, TLV271 (사람이 옮긴 스펙) |
| [docs/analogverifier_overview.html](docs/analogverifier_overview.html) | analogverifier 시스템 해설 |

### 실행 순서 (LM358B)

```bash
python spec_from_plan.py data/extraction/LM358B_SPEC_EVALUATION.json data/extraction/LM358B_knowledge_graph.json LM358B lm358
python pdg_check.py data/extraction/LM358B_knowledge_graph.json lm358
# 아래 넷은 WSL에서 ~/.venvs/edai/bin/python (ngspice 43, GF180 PDK, torch CPU)
python generate_candidates.py lm358     # 학습된 모델 models/flan_t5_structure 필요 (Drive 2026_2/flan_t5_structure, git 제외)
python select_structure.py lm358        # 출력단 1·5·20·50배, 수 시간
python selection_curves.py lm358
python make_schematic_svg.py lm358      # netlistsvg (WSL ~/netlistsvg)
python make_selection_page.py lm358
```

### 파일 지도

| 묶음 | 파일 | 역할 |
| --- | --- | --- |
| 구조 결정 파이프라인 | `spec_from_plan.py` | 측정 계획 → 판정 항목·목표값 (`spec_<부품>.json`), 모델 입력 문장 |
| | `spec_from_hkg.py` | 측정 계획 없이 HKG만으로 같은 일 (이전 방식, 단위 변환 함수 공용) |
| | `pdg_check.py` | 핀 정보로 PDG를 만들고 OP-Amp 5단자와 맞는지 확인 |
| | `generate_candidates.py` | 학습된 FLAN-T5로 구조 후보 생성 (CPU) |
| | `select_structure.py` | 규칙 검사, 크기 정하기, ngspice 판정, 순위 |
| | `selection_curves.py`, `make_schematic_svg.py`, `make_selection_page.py` | 파형 저장, 회로도(netlistsvg), 결과 페이지 |
| 학습 데이터 | `opamp_dataset.py` | AnalogGenie(ICLR 2025) 회로에서 OP-Amp 골라 구조 표로 |
| | `blocks/` | 직접 조립한 OP-Amp 블록 15종 |
| | `label_dataset.py` | 구조마다 크기를 정하고 15개 항목 측정 |
| | `make_train_data.py`, `colab/flan_t5_structure.ipynb` | 학습 문장 만들기, Colab 학습 (FLAN-T5-base, 20 에폭) |
| 공통 바탕 | `run_sim.py`, `tb_opamp_*.cir` | ngspice 실행, OP-Amp 테스트벤치 5종, 스펙 판정 |
| | `auto_size.py`, `netlist_table.py` | gm/ID 자동 크기, 구조 표 ↔ 넷리스트 |
| | `topology.py` | 블록 조립으로 구조 만들기 (블록 학습 데이터용) |
| | `device_table.py`, `devices_gf180.json` | GF180 소자 특성표 (gm/ID 조회용) |
| | `spec_tlv271.json` | 판정 항목 15개의 원본 정의 (TLV271 데이터시트를 손으로 옮김) |
| 데이터·결과 | `data/extraction/` | analogverifier 결과 파일 복사본 |
| | `data/train/`, `data/labels_*.json` | 학습 문장, 측정 데이터 |
| | `data/selection_*.json`, `data/schematics/`, `data/pdg_*.json` | 선택 결과, 회로도, 핀 확인 |
| 예전 실험 (현재 흐름에서 안 씀) | `cascode*`, `tb_cascode_*`, `spec_cascode.json` | Case 1 캐스코드 증폭기 |
| | `opamp_a.cir`, `opamp_b.cir`, `opamp_b.template`, `opamp_gen*`, `opamp_llm.cir` | 초기 OP-Amp 후보, LLM 직접 설계 시도 |
| | `llm_design.py`, `llm_topology.py`, `sizing.py`, `schematic.py`, `make_schematic.py` | LLM이 넷리스트를 직접 쓰던 방식 |
| | `ui_app.py`, `ui_components.py`, `ui_demo.py`, `iteration_log.md`, `*.html`(최상위) | 초기 Streamlit 화면, 기록, 중간발표 자료 |
| | `docs/story_*.html`, `docs/selection_story_template.html` | 영상식 설명 페이지 (사용 중단) |

## 배경

디지털 회로는 HDL 기반 LLM 자동화가 상당히 진전되었지만, 아날로그 회로는 성능 지표 간 강한 비선형·상호결합 특성과 정형화되지 않은 회로도 의존성 때문에 자동화가 훨씬 어렵습니다. AI를 활용한 아날로그 회로 자동 설계는 학계·산업 양쪽에서 아직 보편적으로 자리 잡지 못한 영역입니다.

## 프로젝트 범위

설계 루프(넷리스트 생성 → 시뮬레이션 → 정량 분석 → 재설계)까지 구현하며, 레이아웃/DRC·LVS 단계는 향후 과제로 제외합니다.

## 초기 계획 (2026-09 제안서)

지금 구현과 다른 부분이 있습니다. 현재 상태는 위 절을 보세요.

### 시스템 구성

| 모듈 | 설명 |
| --- | --- |
| AI 넷리스트 생성 | 목표 스펙을 바탕으로 회로 구조와 소자 값을 담은 넷리스트 생성 |
| 시뮬레이션 자동 실행 | 생성된 넷리스트를 오픈소스 시뮬레이터(Ngspice)로 자동 검증 |
| 정량 지표 계산 | 신호처리 스크립트가 위상마진·오버슈트·정착시간을 계산해 목표 스펙과 비교 |
| UI 대시보드 | 입력 스펙부터 시도 횟수, 파형, 달성 여부까지 시각화 |

### 설계 흐름

1. 목표 스펙 입력 (위상마진·오버슈트·정착시간 등)
2. AI 넷리스트 생성
3. 오픈소스 시뮬레이션 (Ngspice)
4. 정량 지표 계산·비교
5. 목표 미달 시 실패 원인을 근거로 AI 재설계 → 3단계로 반복

### 차별점

- 정량 계산(신호처리 스크립트)과 설계 판단(AI)의 역할 분리
- 실패 원인 기반 자동 재설계
- RAG로 회로 이론·설계 지식에 근거한 설계 제안
- 상용 EDA 없이 오픈소스 스택(Ngspice, PySpice)만으로 구현

### 평가 방법 및 목표 성능

Op-Amp, ADC 등 대표 회로에 목표 스펙을 여러 세트로 바꿔가며 파이프라인을 반복 실행하고, 목표 스펙 충족 성공률(Pass@1) **70~80% 이상**을 목표로 합니다.

### 수행 계획

| 주차 | 내용 |
| --- | --- |
| 1~3주 | 오픈소스 시뮬레이션 툴체인 구축, 대상 회로 종류 선정 |
| 4~7주 | AI 넷리스트 생성 모델 개발 (프롬프트 설계, RAG 지식베이스 구축) |
| 8~10주 | 시뮬레이션 자동화 및 결과 분석 스크립트 구현, 반복 재시도 로직 완성 |
| 11~13주 | 여러 회로 종류로 확장 검증, UI 대시보드 완성, 정량 평가 |
| 14주 | 결과 정리 및 보고서 작성 |
| 15주 | 최종 발표 준비 |

## 팀 (EDAI)

| 이름 | 역할 |
| --- | --- |
| 김지윤 (조장) | 총괄, 회로 구조 자동 결정 (구조 생성 모델·학습 데이터·크기 정하기·후보 선택) |
| 박준석 | 데이터시트 정보 추출(HKG)·측정 계획·PDG ([eethsc/analogverifier](https://github.com/eethsc/analogverifier)) |
| 윤다훈 | 모델 선택·전환 워크플로, 폐루프 실험 |
| 곽승철 | UI (EDAI Circuit Studio) |

지도교수: 채주형 교수님

## 협업 방법 (브랜치 워크플로우)

main 브랜치는 항상 정상 동작하는 상태로 유지하고, 각자 작업은 별도 브랜치에서 진행한 뒤 Pull Request로 합칩니다.

1. 저장소를 내 컴퓨터로 가져오기 (최초 1회)

   ```bash
   git clone https://github.com/realppepper/EDAI.git
   cd EDAI
   ```

2. 작업을 시작하기 전, 최신 main 코드를 받아오기

   ```bash
   git checkout main
   git pull origin main
   ```

3. 내 작업용 브랜치 만들기

   ```bash
   git checkout -b feature/브랜치이름
   ```

   예: `feature/netlist-gen`, `feature/simulation`, `feature/dashboard`, `feature/metric-analysis`

4. 코드 수정 후 커밋

   ```bash
   git add .
   git commit -m "작업 내용 설명"
   ```

5. 내 브랜치를 GitHub에 올리기

   ```bash
   git push origin feature/브랜치이름
   ```

6. GitHub 저장소 페이지에서 Pull Request 생성 → 팀원 리뷰 후 main에 merge

7. merge가 끝나면 로컬 main도 최신 상태로 갱신

   ```bash
   git checkout main
   git pull origin main
   ```

새 작업을 시작할 때마다 2~3번부터 다시 반복하면 됩니다. 한 브랜치에 너무 오래 머무르지 말고, 작은 단위로 자주 PR을 올리는 게 충돌을 줄이는 데 좋아요.

## 참고 문헌

- AnalogMaster: Large Language Model-based Automated Analog IC Design Framework from Image to Layout (2026)
- J. Gao, W. Cao, J. Yang, X. Zhang, "AnalogGenie: A Generative Engine for Automatic Discovery of Analog Circuit Topologies," ICLR 2025 (학습 데이터 출처, [github.com/xz-group/AnalogGenie](https://github.com/xz-group/AnalogGenie))
