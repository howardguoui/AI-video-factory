"""Shared fixtures: a fake OpenAI-compatible chat server standing in for Ollama."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class FakeChatServer:
    """
    Serves POST /v1/chat/completions in the OpenAI response shape. Each request is
    answered by `reply(texts, system_prompt) -> str`, where `texts` is the JSON list
    the translator sent as the user message. Every request is recorded in `calls`.
    """

    def __init__(self):
        self.calls: list[dict] = []
        self.reply = lambda texts, system: json.dumps([f"T:{t}" for t in texts], ensure_ascii=False)
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 (http.server API)
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                server.calls.append(body)
                messages = {m["role"]: m["content"] for m in body["messages"]}
                content = server.reply(json.loads(messages["user"]), messages["system"])
                payload = json.dumps({
                    "id": f"chatcmpl-{len(server.calls)}",
                    "object": "chat.completion",
                    "created": 0,
                    "model": body["model"],
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }],
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self._httpd.server_address[1]}/v1"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def close(self):
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture
def fake_llm(monkeypatch):
    from app.config import settings

    server = FakeChatServer()
    monkeypatch.setattr(settings, "ollama_base_url", server.base_url)
    yield server
    server.close()
