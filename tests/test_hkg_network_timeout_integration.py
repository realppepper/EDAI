"""End-to-end HKG recovery test using a real local SSE HTTP connection.

This deliberately stalls the fast and capable model requests past their socket
deadline.  It verifies the production HTTP client, model fallback, page-level
frontier recovery, and non-empty HKG output together -- not just mocks.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ai_analog_designer.llm_client import LLMClient
from ai_analog_designer.pdf_to_graph.hardware_kg_builder import (
    HardwareKnowledgeGraphBuilder,
)


class _TimeoutThenRecoverHandler(BaseHTTPRequestHandler):
    calls = []
    lock = threading.Lock()

    def log_message(self, *_args):
        pass

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        model = payload["model"]
        prompt = "\n".join(str(item.get("content", "")) for item in payload.get("messages", []))
        with self.lock:
            self.calls.append(model)

        # Pin extraction is independent of this test's delayed spec route.
        if "PIN INTERFACE" in prompt:
            response = {
                "ic_device": {"name": "TIMEOUT_TEST", "category": "ANALOG"},
                "pins": [{"name": "IN", "pin_number": "1", "role": "SIGNAL", "direction": "INPUT"}],
                "port_dependencies": [],
                "functional_blocks": [],
            }
        elif model != "frontier-model":
            # The client has a 0.15 s socket deadline in this test.  Waiting
            # before headers exercises a real urllib socket timeout.
            time.sleep(0.4)
            return
        else:
            response = {
                "electrical_parameters": [
                    {"symbol": "VOS", "name": "Input offset voltage", "category": "ELECTRICAL", "typ": 1.0, "unit": "mV"}
                ]
            }

        event = json.dumps({"choices": [{"delta": {"content": json.dumps(response)}}]})
        body = f"data: {event}\n\ndata: [DONE]\n\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _parsed_document():
    return {
        "source_file": "timeout-test.pdf",
        "pages": {
            1: {"text": "Pin configuration", "layout_text": "Pin configuration", "classes": ["pin_configuration"]},
            2: {"text": "Electrical characteristics MIN TYP MAX", "layout_text": "Electrical characteristics MIN TYP MAX", "classes": ["electrical"]},
        },
    }


def test_real_socket_timeouts_recover_on_frontier_page_retry(monkeypatch):
    for name in (
        "LLM_MODEL", "LLM_FALLBACK_MODELS", "LLM_EXTRACT_MODEL",
        "LLM_HERMES_MODEL", "LLM_SYNTH_MODEL", "LLM_TB_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TimeoutThenRecoverHandler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    _TimeoutThenRecoverHandler.calls = []
    try:
        monkeypatch.setenv("LLM_FAST_MODEL", "fast-model")
        monkeypatch.setenv("LLM_CAPABLE_MODEL", "capable-model")
        monkeypatch.setenv("LLM_FRONTIER_MODEL", "frontier-model")
        client = LLMClient(
            provider="nim",
            api_key="test-key",
            base_url=f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
            request_timeout=0.15,
            first_token_timeout=0.15,
        )
        data = HardwareKnowledgeGraphBuilder(llm_client=client, parallel_spec_calls=1).extract_raw(_parsed_document())
    finally:
        server.shutdown()
        server.server_close()

    assert [row["symbol"] for row in data["electrical_parameters"]] == ["VOS"]
    assert "fast-model" in _TimeoutThenRecoverHandler.calls
    assert "capable-model" in _TimeoutThenRecoverHandler.calls
    assert "frontier-model" in _TimeoutThenRecoverHandler.calls
    assert data["provenance"]["failed_spec_pages"] == []
