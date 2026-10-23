import pytest

from matrixlab.config import Settings
from matrixlab.data import DataError
from matrixlab.research import ResearchUnavailable, inspect_backend, screen


def test_keyword_baseline_filters_future_documents(documents, tmp_path):
    settings = Settings(tmp_path, "jev", "", "")
    result = screen(documents, "cloud", "2024-06-01", settings)
    assert result.backend == "keyword_baseline"
    assert [r["doc_id"] for r in result.matches] == ["old"]
    assert result.inputs == 1
    assert result.save(tmp_path).exists()


def test_no_key_never_returns_fabricated_semantics(documents, tmp_path, monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    settings = Settings(tmp_path, "jev", "", "")
    with pytest.raises(ResearchUnavailable, match="密钥"):
        screen(documents, "cloud", "2024-06-01", settings, "jevdb")


def test_real_jevdb_binary_loads_without_model_calls():
    pytest.importorskip("jevdb")
    info = inspect_backend()
    assert info["jevdb"] == "0.1.0"
    assert {"jev_holds", "jev_choose", "jev_score"} <= set(info["functions"])


def test_no_historical_document_is_an_explicit_error(documents, tmp_path):
    with pytest.raises(DataError, match="研究日期"):
        screen(documents, "cloud", "2020-01-01", Settings(tmp_path, "jev", "", ""))


def test_mixed_iso_timestamp_formats_are_accepted(documents):
    from matrixlab.data import validate_documents

    frame = documents.copy()
    frame["available_at"] = ["2024-01-02T12:00:00Z", "2024-07-02T12:00:00.123456+00:00"]
    parsed = validate_documents(frame)
    assert parsed.available_at.notna().all()


def test_real_jevdb_sql_and_transport_with_local_test_service(documents, tmp_path, monkeypatch):
    """Deterministic localhost fixture, not a model or a demo result.

    Protocol reference: PDAIS/JEVDB tools/standin/jev_standin.py (MIT).
    """
    import json
    pytest.importorskip("jevdb")
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            answers = {key: {"noul": .9} for key in body["questions"]}
            payload = json.dumps({"answers": answers, "model": "localhost-test-fixture", "usage": {"input_tokens": 1}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    monkeypatch.setenv("JEV_API_KEY", "localhost-test-placeholder")
    settings = Settings(tmp_path, "jev", f"http://127.0.0.1:{server.server_port}/v1/", "")
    try:
        result = screen(documents, "cloud'); DROP TABLE documents; --", "2024-06-01", settings, "jevdb")
        assert result.backend == "jevdb_jev"
        assert [r["doc_id"] for r in result.matches] == ["old"]
        assert requests and "future" not in json.dumps(requests)
        assert result.stats
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
