"""本地 JSON Schema 兼容层：把 JEVDB 的 json_schema 请求转成 json_object。

JEVDB 0.1.0 的 llm 后端固定发送
`response_format={"type":"json_schema","json_schema":{...,"strict":true}}`，
而 DeepSeek 等兼容服务只接受 `{"type":"json_object"}`。本代理把 schema
写进提示词，校验返回值并按需重试；语义判断仍由上游模型完成，不是伪造结果。

启动（WSL）：
    DEEPSEEK_API_KEY=... python scripts/jev_llm_proxy.py --port 8111

然后把 JEVDB 的端点指向 http://127.0.0.1:8111/v1/。
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = os.environ.get("UPSTREAM_BASE", "https://api.deepseek.com/v1").rstrip("/")
DEFAULT_MODEL = os.environ.get("UPSTREAM_MODEL", "deepseek-flash")
LOG_PATH = Path(os.environ.get("PROXY_LOG", "/tmp/jev_proxy.jsonl"))
MAX_ATTEMPTS = int(os.environ.get("PROXY_ATTEMPTS", "3"))


def _api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("UPSTREAM_API_KEY")
    if key:
        return key
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("缺少上游密钥：设置 DEEPSEEK_API_KEY 或 .env 中的 OPENAI_API_KEY")


KEY = _api_key()


def _check(value, schema) -> str | None:
    if not isinstance(value, dict):
        return "顶层必须是 JSON 对象"
    for key in schema.get("required", []):
        if key not in value:
            return "缺少必需字段 " + key
    for key, sub in (schema.get("properties") or {}).items():
        if key in value and sub.get("type") == "array" and not isinstance(value[key], list):
            return key + " 必须是数组"
    return None


def _call(body):
    request = urllib.request.Request(
        UPSTREAM + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def _log(record):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _reply(self, code, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._reply(200, {"ok": True, "upstream": UPSTREAM})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        started = time.perf_counter()
        schema = None
        response_format = body.get("response_format") or {}
        if response_format.get("type") == "json_schema":
            schema = (response_format.get("json_schema") or {}).get("schema")
            instruction = (
                "Return only one JSON object, without prose or Markdown code fences. "
                "It must validate against this JSON Schema:\n"
                + json.dumps(schema, ensure_ascii=False)
            )
            messages = body.get("messages") or []
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] = str(messages[0].get("content", "")) + "\n\n" + instruction
            else:
                messages.insert(0, {"role": "system", "content": instruction})
            body["messages"] = messages
            body["response_format"] = {"type": "json_object"}
        body.setdefault("model", DEFAULT_MODEL)
        body.setdefault("max_tokens", 2048)
        body.setdefault("temperature", 0)

        result = None
        problem = None
        attempts = 0
        trail = []
        for attempts in range(1, MAX_ATTEMPTS + 1):
            snippet = ""
            try:
                result = _call(body)
                message = ((result.get("choices") or [{}])[0].get("message") or {})
                content = _strip_fence(message.get("content") or "")
                snippet = content[:160]
                parsed = json.loads(content) if content else None
                problem = _check(parsed, schema) if schema else (None if parsed is not None else "空内容")
                if problem is None:
                    break
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
                problem = "上游错误：" + str(exc)
            trail.append({"attempt": attempts, "problem": problem, "snippet": snippet})
            body["temperature"] = 0
            body["messages"] = body["messages"] + [{
                "role": "user",
                "content": "Your previous answer was invalid (" + str(problem) + "). Return only the JSON object.",
            }]
            time.sleep(0.5)

        usage = (result or {}).get("usage") or {}
        _log({
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "model": body.get("model"),
            "schema": bool(schema),
            "attempts": attempts,
            "ok": problem is None,
            "problem": problem,
            "seconds": round(time.perf_counter() - started, 2),
            "usage": usage,
            "trail": trail,
        })
        if result is None or problem is not None:
            self._reply(502, {"error": {"message": "proxy could not satisfy schema: " + str(problem),
                                        "type": "proxy_error"}})
            return
        self._reply(200, result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8111)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("proxy listening on http://127.0.0.1:%d/v1/ -> %s" % (args.port, UPSTREAM), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
