"""Optional Linux JEVDB gateway for native Windows clients. No trading endpoints."""
import argparse
from dataclasses import asdict
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os

import pandas as pd

from .config import Settings
from .data import DataError, validate_documents
from .research import ResearchUnavailable, screen


def make_server(host, port, settings=None, token=None):
    settings = settings or Settings.load()
    settings = Settings(settings.data_dir, settings.backend, settings.endpoint, settings.model)
    token = token or os.getenv("MATRIX_JEVDB_SERVICE_TOKEN", "")
    if not token:
        raise ValueError("启动语义服务前必须配置MATRIX_JEVDB_SERVICE_TOKEN。")

    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, payload):
            raw = json.dumps(payload, ensure_ascii=False, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self):
            return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)

        def do_GET(self):
            if not self.authorized():
                return self.reply(401, {"error": "unauthorized"})
            self.reply(200 if self.path == "/health" else 404,
                       {"service": "matrix-jevdb", "credential_available": settings.credential_available})

        def do_POST(self):
            if not self.authorized():
                return self.reply(401, {"error": "unauthorized"})
            if self.path != "/research":
                return self.reply(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4_000_000:
                    return self.reply(413, {"error": "request too large"})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body["documents"], list) or len(body["documents"]) > 200:
                    raise DataError("最多200条资料。")
                docs = validate_documents(pd.DataFrame(body["documents"]))
                run = screen(docs, str(body["query"]), body["asof"], settings, "jevdb", int(body.get("max_documents", 100)))
                self.reply(200, asdict(run))
            except ResearchUnavailable:
                self.reply(503, {"error": "model service unavailable"})
            except (ValueError, KeyError, TypeError):
                self.reply(400, {"error": "invalid research request"})

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description="Linux JEVDB service for Windows clients")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    with make_server(args.host, args.port) as server:
        print(f"JEVDB service listening on {args.host}:{args.port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
