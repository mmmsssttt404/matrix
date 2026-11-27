import pandas as pd
import pytest

from matrixlab.config import Settings
from matrixlab.data import DataError, validate_documents
from matrixlab.research import ResearchUnavailable, inspect_backend, screen


def _documents(rows):
    for index, row in enumerate(rows):
        row.setdefault("available_at", "2024-01-02T12:00:00Z")
        row.setdefault("retrieved_at", "2025-01-01T00:00:00Z")
        row.setdefault("source_url", f"https://example.org/{row['doc_id']}")
    return validate_documents(pd.DataFrame(rows))


def test_keyword_baseline_filters_future_documents(documents, tmp_path):
    settings = Settings(tmp_path, "jev", "", "")
    result = screen(documents, "cloud", "2024-06-01", settings)
    assert result.backend == "keyword_bm25"
    assert [r["doc_id"] for r in result.matches] == ["old"]
    assert result.matches[0]["match_score"] > 0
    assert result.inputs == 1
    assert result.save(tmp_path).exists()


def test_keyword_all_requires_every_term_and_bm25_ranks(tmp_path):
    documents = _documents([
        {"doc_id": "cloud", "symbol": "AAA", "title": "Cloud platform", "text": "cloud infrastructure"},
        {"doc_id": "software", "symbol": "BBB", "title": "Software company", "text": "enterprise software"},
        {"doc_id": "both", "symbol": "CCC", "title": "Cloud software", "text": "cloud software platform"},
    ])
    settings = Settings(tmp_path, "jev", "", "")
    strict = screen(documents, "cloud software", "2024-06-01", settings, "keyword", 100, "all")
    assert [row["doc_id"] for row in strict.matches] == ["both"]
    loose = screen(documents, "cloud software", "2024-06-01", settings, "keyword", 100, "any")
    assert {row["doc_id"] for row in loose.matches} == {"cloud", "software", "both"}
    assert loose.matches[0]["doc_id"] == "both"


def test_bm25_uses_full_corpus_idf_under_and_operator(tmp_path):
    # "common" appears in all 4 docs; "rare" appears in only 2 docs.
    # Under AND ("common rare"), doc_rare_heavy (2x rare, 1x common) must outrank
    # doc_common_heavy (1x rare, 2x common) because corpus IDF(rare) > IDF(common).
    documents = _documents([
        {"doc_id": "d1", "symbol": "AAA", "title": "common", "text": "common text one"},
        {"doc_id": "d2", "symbol": "BBB", "title": "common", "text": "common text two"},
        {"doc_id": "rare_heavy", "symbol": "CCC", "title": "rare", "text": "rare common item"},
        {"doc_id": "common_heavy", "symbol": "DDD", "title": "common", "text": "common rare item"},
    ])
    settings = Settings(tmp_path, "jev", "", "")
    result = screen(documents, "common rare", "2024-06-01", settings, "keyword", 100, "all")
    assert [row["doc_id"] for row in result.matches] == ["rare_heavy", "common_heavy"]
    assert result.matches[0]["match_score"] > result.matches[1]["match_score"]


def test_keyword_phrase_and_chinese_bigrams(tmp_path):
    documents = _documents([
        {"doc_id": "phrase", "symbol": "AAA", "title": "Cloud software", "text": "cloud software platform"},
        {"doc_id": "split", "symbol": "BBB", "title": "Cloud and software", "text": "cloud, enterprise software"},
        {"doc_id": "cn", "symbol": "CCC", "title": "云计算", "text": "云计算与软件服务"},
    ])
    settings = Settings(tmp_path, "jev", "", "")
    phrase = screen(documents, '"cloud software"', "2024-06-01", settings, "keyword", 100, "all")
    assert [row["doc_id"] for row in phrase.matches] == ["phrase"]
    chinese = screen(documents, "云计算", "2024-06-01", settings, "keyword", 100, "all")
    assert [row["doc_id"] for row in chinese.matches] == ["cn"]


def test_keyword_rejects_empty_and_invalid_operator(documents, tmp_path):
    settings = Settings(tmp_path, "jev", "", "")
    with pytest.raises(DataError, match="检索词"):
        screen(documents, "the and of", "2024-06-01", settings)
    with pytest.raises(DataError, match="匹配方式"):
        screen(documents, "cloud", "2024-06-01", settings, operator="xor")
    with pytest.raises(DataError, match="prune_k"):
        screen(documents, "cloud", "2024-06-01", settings, prune_k="6")
    with pytest.raises(DataError, match="choices"):
        screen(documents, "cloud", "2024-06-01", settings, choices="abc")
    with pytest.raises(DataError, match="空字节"):
        from matrixlab.research import _literal
        _literal("abc\x00def")


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


def test_real_jevdb_probability_choose_and_prune_first(tmp_path, monkeypatch):
    """Exercise jev_probability, jev_choose, and Prune-First cascade on real jevdb 0.1.0."""
    import json
    pytest.importorskip("jevdb")
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    docs = _documents([
        {"doc_id": "c1", "symbol": "AAA", "title": "Cloud leader", "text": "enterprise cloud platform infrastructure"},
        {"doc_id": "c2", "symbol": "BBB", "title": "Cloud tools", "text": "cloud developer tools"},
        {"doc_id": "c3", "symbol": "CCC", "title": "Beverage maker", "text": "carbonated soft drinks"},
        {"doc_id": "c4", "symbol": "DDD", "title": "Oil refiner", "text": "crude oil refining energy"},
    ])
    seen_counts = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen_counts.append(len(body["questions"]))
            answers = {}
            for key, q in body["questions"].items():
                text = str(q.get("instructions", {}).get("text", ""))
                if q.get("type") == "choice":
                    answers[key] = {"choice": "Technology & Cloud" if "cloud" in text else "Energy"}
                else:
                    answers[key] = {"noul": 0.92 if "platform" in text else (0.65 if "cloud" in text else 0.10)}
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
        prob = screen(docs, "cloud", "2024-06-01", settings, "jevdb", jev_op="probability", threshold=0.8)
        assert [r["doc_id"] for r in prob.matches] == ["c1"]
        assert prob.matches[0]["match_score"] == pytest.approx(0.92)

        chosen = screen(docs, "sector", "2024-06-01", settings, "jevdb", jev_op="choose")
        assert len(chosen.matches) == 4
        assert all("semantic_label" in r for r in chosen.matches)

        pruned = screen(docs, "cloud", "2024-06-01", settings, "jevdb", jev_op="prune_then_decide", prune_k=2)
        assert pruned.pruned_from == 4
        assert pruned.inputs == 2
        assert seen_counts[-1] == 2
        assert {r["doc_id"] for r in pruned.matches} == {"c1", "c2"}
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
