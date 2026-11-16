# AnalogVerifier

상용 아날로그 IC 데이터시트(PDF)에서 **하드웨어 지식 그래프(HKG)** 와 **포트 의존성 그래프(PDG)** 를 추출하고, **순수 물리 트랜지스터 수준(BJT, MOSFET, JFET, Diode, R/C/L)** 의 SPICE 넷리스트를 자율 합성한 뒤 **LTspice 4단계 인과 게이트**로 검증·진화시키는 폐루프(Closed-Loop) 자율 설계 프레임워크입니다.

---

## 1. 핵심 파이프라인

```mermaid
flowchart LR
    A["PDF 데이터시트"] --> B["Phase 1: HKG 추출<br/>(pdf_parser, hardware_kg_builder)"]
    B --> C["Phase 2: PDG & 전원 시퀀싱<br/>(pdg_extractor, pdg_fidelity_verifier)"]
    C --> D["Phase 3: Hermes × Harness² 합성<br/>(hermes_agent, netlist_validator)"]
    D --> E["Phase 4: PDG 4단계 물리 검증<br/>(deterministic_testbench, ltspice_runner)"]
    E -->|스펙 미달 시 피드백 루프| D
    E -->|100% 통과| F["검증된 SPICE 넷리스트 & 리포트"]
```

- **Phase 1 — PDF → HKG**: 데이터시트에서 핀 인터페이스 및 전기적 사양 표를 추출합니다. 사양 추출 결과가 비어 있으면 `HKGExtractionError`로 즉시 중단합니다.
- **Phase 2 — HKG → PDG**: 포트 간 인과 의존성과 전원 시퀀싱 순서를 추출·감사합니다.
- **Phase 3 — Hermes × Harness² 자율 합성**: `HermesAgent`와 `ToolDecisionRouter`가 6개 툴(`validate_netlist_syntax`, `verify_circuit_pdg_gate`, `retrieve_subcircuit_blueprint`, `save_subcircuit_blueprint`, `manage_memory`, `search_web_circuit_reference`)을 사용해 순수 물리 트랜지스터 넷리스트를 합성합니다.
- **Phase 4 — LTspice 인과 검증**: Stage 0(토폴로지) → Stage 1(전원/DC 바이어스) → Stage 2(DC 전달) → Stage 3(개별 스펙) 순으로 물리 시뮬레이션을 수행합니다.

---

## 2. 디렉터리 구조

```text
analogverifier/
├── ai_analog_designer/
│   ├── autonomous_design_agent.py      # 전체 E2E 파이프라인 오케스트레이터
│   ├── llm_client.py                   # 멀티 프로바이더 LLM 클라이언트 (wusrouter/nim/groq/openrouter)
│   ├── pdf_to_graph/                   # PDF 파싱, HKG/PDG 추출 및 감사
│   ├── hermes_core/                    # HermesAgent, ToolDecisionRouter, IEEE 레퍼런스 검색
│   ├── circuit_synthesis/              # SPICE 넷리스트 검증기 및 Harness² 라이브러리
│   ├── neuro_symbolic_verifier/        # LTspice 러너, PDG 테스트벤치, SymPy 오라클
│   ├── tracing/                        # ExecutionTracer + Arize Phoenix OTel & 브레이크포인트
│   └── web_studio/                     # 인터랙티브 Web Studio 서버
├── tests/                              # 단위/통합 테스트 스위트
├── testcases/                          # 상용 IC 데이터시트 PDF 모음
├── specs/                              # 기준 스펙 JSON
├── run_studio.py                       # Web Studio 실행 진입점
├── run_harness2_netlist_loop.py        # Dual-Harness² CLI 루프
└── run_interactive_designer.py         # 대화형 설계 CLI
```

---

## 3. 환경 설정 (`.env` 및 API 키 정책)

**필수 API 키가 설정되어 있지 않으면 하드코딩된 기본값을 쓰지 않고 즉시 `RuntimeError`로 실행을 차단합니다.**

프로젝트 루트(`.env`)에 사용할 프로바이더와 키를 설정하세요:

```ini
# LLM 프로바이더 선택: wusrouter | nim | groq | openrouter
LLM_PROVIDER=wusrouter

WUSROUTER_API_KEY=sk-ws-...
NVIDIA_API_KEY=nvapi-...
GROQ_API_KEY=gsk_...

# 학술 레퍼런스 검색 (IEEE Xplore / OpenAlex 전용, Tavily/Exa 미사용)
IEEE_API_KEY=...

# Arize Phoenix 로컬 트레이싱 (API 키 불필요)
PHOENIX_ENABLED=1
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces
PHOENIX_PROJECT_NAME=analogverifier
```

---

## 4. 설치 및 실행

### 가상환경 구성
```powershell
uv venv .venv --python 3.12
uv pip install -r requirements.txt arize-phoenix arize-phoenix-otel openinference-semantic-conventions opentelemetry-sdk opentelemetry-exporter-otlp pytest
```

### Web Studio 실행
```powershell
.\.venv\Scripts\python.exe run_studio.py
```

### Arize Phoenix 트레이싱 & 단계별 브레이크포인트 디버깅
1. **Phoenix UI 서버 실행** (`http://localhost:6006`):
   ```powershell
   .\.venv\Scripts\phoenix.exe serve
   ```
2. **브레이크포인트 활성화 후 실행** (`phase`, `turn`, `tool`, `llm` 조합 가능):
   ```powershell
   $env:DEBUG_BREAKPOINTS = "phase,turn,tool"
   .\.venv\Scripts\python.exe run_studio.py
   ```
   각 단계에서 `debug_snapshots/step_NNN_*.json`에 프롬프트, `messages`, 툴 입출력, 넷리스트, 라우터 결정 상태가 저장되며 터미널에서 일시정지합니다.

---

## 5. 테스트 실행
```powershell
.\.venv\Scripts\python.exe -m pytest tests --ignore=tests/test_web_studio_e2e_scenario.py --ignore=tests/test_web_studio_pdg.py -q
```
