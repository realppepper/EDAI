# External APIs & Local Runtime Dependencies

이 문서는 `EDAI × AnalogVerifier` (`main` 브랜치)를 실행·유지보수할 때 필요한 모든 **외부 API**와 **로컬 외부 도구/바이너리**를 한곳에 정리한 레퍼런스입니다.  
설정은 루트 [`.env.example`](../.env.example)을 `.env`로 복사해 관리합니다.

---

## 1. 외부 HTTP / MCP API

| 구분 | 서비스 / API | 기본 엔드포인트 | 인증 환경변수 | 필수 여부 | 사용 모듈 및 Fallback |
| --- | --- | --- | --- | --- | --- |
| **LLM 추론**<br>*(택1 필수)* | **NVIDIA NIM** | `https://integrate.api.nvidia.com/v1/chat/completions` (`NIM_BASE_URL`) | `NVIDIA_API_KEY` | **택1 필수**<br>*(키 존재 시 1순위)* | `ai_analog_designer/llm_client.py` — HKG/PDG 추출, Hermes, Harness², 동적 테스트벤치, Base 회로 생성 |
| **LLM 추론**<br>*(택1 필수)* | **OpenRouter** | `https://openrouter.ai/api/v1/chat/completions` (`OPENROUTER_BASE_URL`) | `OPENROUTER_API_KEY` | **택1 필수**<br>*(`NVIDIA_API_KEY` 미설정 시 기본값)* | `ai_analog_designer/llm_client.py` — `LLM_PROVIDER=openrouter` 시 사용 (`usage.include` 비용 추적 지원) |
| **LLM 추론**<br>*(택1 필수)* | **Groq** | `https://api.groq.com/openai/v1/chat/completions` (`GROQ_BASE_URL`) | `GROQ_API_KEY` | **택1 필수** | `ai_analog_designer/llm_client.py` — `LLM_PROVIDER=groq` 시 사용 (`HardwareKnowledgeGraphBuilder`에서 single-shot 스펙 추출 자동 활성화) |
| **LLM 추론**<br>*(택1 필수)* | **WusRouter** | `https://wusrouter.com/v1/chat/completions` (`WUSROUTER_BASE_URL`) | `WUSROUTER_API_KEY` | **택1 필수** | `ai_analog_designer/llm_client.py` — `LLM_PROVIDER=wusrouter` 시 사용. `HARNESS2_IMPROVER_PROVIDER` / `HARNESS2_SYNTHESIZER_PROVIDER` 분리 지정 시 해당 키도 필요 |
| **PDF VLM 파서** | **NVIDIA NIM (`nvidia/nemotron-parse`)** | `https://integrate.api.nvidia.com/v1/chat/completions` | `NVIDIA_API_KEY` | **선택** *(권장)* | `ai_analog_designer/pdf_to_graph/pdf_parser.py` — PDF 페이지 이미지 기반 표/LaTeX 파싱. 미설정·실패 시 `PyMuPDF` 로컬 텍스트로 fallback |
| **학술 논문 검색** | **IEEE Xplore API** | `https://ieeexploreapi.ieee.org/api/v1/search/articles` | `IEEE_API_KEY` | **전체 파이프라인 필수** / Web Studio 선택 | `ai_analog_designer/hermes_core/web_reference_search.py` — `AutonomousAnalogDesignAgent`, `HermesAnalogTools`, `Harness2CircuitArchitect` 초기화 시 키가 없으면 `RuntimeError` 발생 |
| **학술 논문 Fallback** | **OpenAlex Works API** | `https://api.openalex.org/works` | 없음 (무키) | **자동 Fallback** | `web_reference_search.py`, `ieee_mcp_client.py` — IEEE Xplore 결과 부재 시 또는 Web Studio `/api/ieee/search`·MCP `search_ieee_papers`에서 키/MCP 미설정 시 동작 |
| **외부 IEEE MCP** | **외부 IEEE MCP 서버** (stdio) | `IEEE_MCP_COMMAND` + `IEEE_MCP_ARGS` | 서버 구현 의존 | **선택** | `ai_analog_designer/hermes_core/ieee_mcp_client.py` — 미설정 시 `IEEE_API_KEY` → OpenAlex 순으로 fallback |
| **에이전트 라우터** | **Jev Remote Router API** | `JEV_ENDPOINT` | `JEV_API_KEY` (Bearer) | **선택** | `ai_analog_designer/hermes_core/tool_decision_router.py` — 미설정/실패 시 내장 로컬 규칙 기반 System-1 라우터 사용 |
| **트레이싱 / 관측성** | **Arize Phoenix (OTLP/HTTP)** | `http://localhost:6006/v1/traces` (`PHOENIX_COLLECTOR_ENDPOINT`) | 없음 | **선택** | `ai_analog_designer/tracing/phoenix_tracer.py` — `PHOENIX_ENABLED=1`이고 `opentelemetry` 패키지 설치 시 전송, 아니면 no-op |

> **참고 (비활성화된 검색 엔진)**: `ai_analog_designer/hermes_core/web_reference_search.py`에 `search_tavily()`(`https://api.tavily.com/search`)와 `search_exa()`(`https://api.exa.ai/search`) 메서드가 남아 있으나, `search()`에서는 의도적으로 제외되어 호출되지 않으므로 `TAVILY_API_KEY` / `EXA_API_KEY`는 필요하지 않습니다.

---

## 2. 로컬 외부 바이너리 / 모델 (비-API)

| 도구 / 데이터 | 환경변수 | 필수 여부 | 용도 및 Fallback |
| --- | --- | --- | --- |
| **LTspice** (`LTspice.exe`) | `LTSPICE_EXE`, `LTSPICE_PATH` | **물리 검증 시 필수** (Windows 기본) | `spice_sweep_engine.py`(`LTSPICE_EXE`), `ltspice_runner.py`(`LTSPICE_PATH`) — 4단계 인과 검증 및 파라미터 스윕 |
| **ngspice + GF180 PDK** | `EDAI_NGSPICE`, `EDAI_PDK_DIR` | **조건부 필수** (Linux/스윕/ngspice `gm/ID`) | `ngspice_runner.py`, `gm_id_sizer.py` — 미설치 시 `gm/ID`는 내장 `devices_gf180.json` 해석 계산으로 fallback |
| **Node.js + `netlistsvg`** | `EDAI_NODE`, `EDAI_NETLISTSVG` | **선택** | `schematic_svg.py` — 미설치 시 내장 Python SVG 렌더러로 fallback |
| **FLAN-T5 로컬 가중치** | `EDAI_MODEL_DIR` | **선택** | `flan_t5_topology.py` — 미설정 시 내장 Op-Amp 블록 라이브러리·템플릿으로 fallback |
