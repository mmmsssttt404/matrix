import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from matrixlab.config import Settings
from matrixlab.research import ResearchUnavailable, screen
from matrixlab.service import make_server


def test_gateway_requires_token_and_reports_missing_model(documents, tmp_path, monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    server = make_server("127.0.0.1", 0, Settings(tmp_path, "jev", "", ""), "test-token")
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        with pytest.raises(HTTPError) as rejected:
            urlopen(url + "/health")
        assert rejected.value.code == 401
        request = Request(url + "/health", headers={"Authorization": "Bearer test-token"})
        with urlopen(request) as response:
            assert json.load(response)["credential_available"] is False
        remote = Settings(tmp_path, "jev", "", "", url, "test-token")
        with pytest.raises(ResearchUnavailable, match="语义服务请求失败"):
            screen(documents, "cloud", "2024-06-01", remote, "jevdb")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_remote_plain_http_cannot_send_tokens(documents, tmp_path):
    remote = Settings(tmp_path, "jev", "", "", "http://example.org", "test-token")
    with pytest.raises(ResearchUnavailable, match="HTTPS"):
        screen(documents, "cloud", "2024-06-01", remote, "jevdb")
