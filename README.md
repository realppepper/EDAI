# EDAI × AnalogVerifier

**AI 기반 아날로그 회로 자동 설계 및 물리 검증 통합 플랫폼**

상용 아날로그 IC 데이터시트(PDF)에서 **하드웨어 지식 그래프(HKG)**와 **포트 의존성 그래프(PDG)**를 추출하고, **FLAN-T5/블록 기반 토폴로지 탐색 + `gm/ID` 결정론적 사이징 + 베이스 회로 초안**으로 출발점을 확보한 뒤, **Hermes × Harness² 폐루프**와 **LTspice / ngspice 4단계 인과 게이트**로 순수 물리 트랜지스터 수준(BJT, MOSFET, JFET, Diode, R/C/L)의 회로를 검증·진화시킵니다.

---

## 1. 통합 아키텍처

```mermaid
flowchart LR
    A["PDF 데이터시트 / 자연어"] --> B["Phase 1~2: HKG / PDG 추출 & 원문 검수"]
    B --> C["Phase 3-A: 초기 회로 확보<br/>(FLAN-T5 + gm/ID 사이징 / 베이스 초안 / IEEE MCP)"]
    C --> D["Phase 3-B: NetlistValidator + Hermes × Harness²"]
    D --> E["Phase 4: LTspice 4단계 게이트 / ngspice 스윕"]
    E -->|스펙 미달 시 피드백| D
    E -->|100% 통과| F["검증된 넷리스트 · 회로도 SVG · ZIP 리포트"]
```

- **백엔드 코어 (`analogverifier`)**: PDF→HKG/PDG 추출, `NetlistValidator` + `syntax_verifier_agent` 3차 문법 검증 루프, `HermesAgent` × `ToolDecisionRouter` (11종 툴), `Harness²` 대조 진화, LTspice 4단계 인과 게이트
- **토폴로지 & 사이징 (`jiyun` 통합)**: `flan_t5_topology.py` (FLAN-T5 + OP-Amp 블록 라이브러리), `gm_id_sizer.py` (GF180 6V 특성표 기반 `gm/ID` 사이징), `schematic_svg.py` (`netlistsvg` / Python SVG 회로도)
- **UI/UX & 스윕 (`seungcheol` 통합)**: Circuit Studio v03 기반 통합 웹 UI(`ai_analog_designer/web_studio/`), 원문 대조 검수(`base_circuit_generator.py`), 파라미터 스윕(`spice_sweep_engine.py`, `WHEN ... AT ...` P0 수정 포함)
- **MCP 서버 (`ai_analog_designer/mcp_server.py`) & IEEE MCP**: IEEE Xplore/OpenAlex 학술 논문 검색 및 핵심 설계·검증 도구를 FastMCP(`mcp>=2.0`)로 노출

---

## 2. 실행 및 테스트

### 가상환경 구성
```powershell
uv venv .venv --python 3.12
uv pip install -r requirements.txt pytest
```

### 통합 Web Studio 실행
```powershell
.\.venv\Scripts\python.exe run_studio.py
```
- 기본 통합 UI: `http://127.0.0.1:8080/` (seungcheol Circuit Studio UI/UX + PDG + 토폴로지/`gm/ID` + IEEE MCP + Hermes 자율 루프)
- 기존 다크 UI: `http://127.0.0.1:8080/classic`

### 통합 MCP 서버 실행 (stdio)
```powershell
.\.venv\Scripts\python.exe -m ai_analog_designer.mcp_server
```

### 통합 테스트 실행
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_edai_integration.py -v
```

---

## 3. 환경 설정 (`.env`)

필수 API 키가 설정되어 있지 않으면 하드코딩된 기본값을 쓰지 않고 즉시 `RuntimeError`로 실행을 차단합니다. 루트의 [`.env.example`](.env.example)을 `.env`로 복사해 사용할 프로바이더와 키를 설정하세요. 전체 외부 API·Fallback·로컬 바이너리 상세 정리는 [`docs/EXTERNAL_APIS.md`](docs/EXTERNAL_APIS.md)를 참고하세요.

```ini
# LLM 프로바이더 선택: wusrouter | nim | groq | openrouter
LLM_PROVIDER=wusrouter

WUSROUTER_API_KEY=sk-ws-...
NVIDIA_API_KEY=nvapi-...
GROQ_API_KEY=gsk_...
OPENROUTER_API_KEY=sk-or-...

# 학술 레퍼런스 & IEEE MCP
IEEE_API_KEY=...
# IEEE_MCP_COMMAND=python
# IEEE_MCP_ARGS=-m ai_analog_designer.mcp_server

# Arize Phoenix 로컬 트레이싱 (선택)
PHOENIX_ENABLED=1
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces
PHOENIX_PROJECT_NAME=analogverifier
```

---

## 4. 팀 (EDAI)

| 이름 | 역할 |
| --- | --- |
| 김지윤 (조장) | FLAN-T5 토폴로지 생성, `gm/ID` 자동 사이징, GF180/ngspice & 회로도 SVG |
| 박준석 | `analogverifier` 코어 (HKG/PDG, Hermes × Harness², 4단계 LTspice 검증, 통합 아키텍처) |
| 윤다훈 | OP-Amp 정량 검증 파이프라인 및 IEEE MCP 서버 프로토타입 |
| 곽승철 | Circuit Studio v03 웹 UI/UX, 출처 대조 검수, SPICE 파라미터 스윕 엔진 |

지도교수: 채주형 교수님
