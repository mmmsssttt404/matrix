"""Regression tests for v0.4.0 engineering hardening, provenance verification,
stale-state guards, and offline self-contained HTML workflow reports."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from uuid import uuid4

import pandas as pd
import pytest
from PySide6 import QtCore

from matrixlab.agent import run_workflow
from matrixlab.analytics import holdout_curve
from matrixlab.config import Settings
from matrixlab.data import DataError, cutoff_utc, validate_documents, validate_prices
from matrixlab.desktop.dialogs import AccountDialog
from matrixlab.desktop.theme import STYLESHEET
from matrixlab.desktop.window import MainWindow
from matrixlab.research import ResearchUnavailable, screen
from matrixlab.trading import Broker, Order, TradingError


def test_data_rejects_nat_and_timezone_naive_timestamps(prices, documents):
    bad_docs = documents.copy()
    bad_docs["available_at"] = bad_docs["available_at"].astype(str)
    bad_docs.loc[0, "available_at"] = "2024-01-02T12:00:00"  # naive (no tz)
    with pytest.raises(DataError, match="时区"):
        validate_documents(bad_docs)

    bad_docs2 = documents.copy()
    bad_docs2["available_at"] = bad_docs2["available_at"].astype(str)
    bad_docs2.loc[0, "available_at"] = "NaT"
    with pytest.raises(DataError, match="NaT"):
        validate_documents(bad_docs2)

    bad_prices = prices.copy()
    bad_prices.loc[0, "retrieved_at"] = "2025-01-01 00:00:00"  # naive
    with pytest.raises(DataError, match="时区"):
        validate_prices(bad_prices)

    with pytest.raises(DataError, match="日历日期"):
        cutoff_utc("2025-01-27T15:00:00")
    with pytest.raises(DataError, match="日历日期"):
        cutoff_utc("2025-01-27T00:00:00Z")


def test_trading_rejects_subprecision_cash_and_zero_quantized_price(prices, tmp_path):
    broker = Broker(tmp_path / "paper.sqlite3")
    day = str(prices.date.unique()[10].date())
    with pytest.raises(TradingError, match="最小精度"):
        broker.initialize(1e-9, day)

    broker.initialize(1000.0, day)
    tiny_prices = prices.copy()
    next_day = prices.loc[prices.date > pd.Timestamp(day), "date"].min()
    tiny_prices.loc[(tiny_prices.date == next_day) & (tiny_prices.symbol == "AAA"), "open"] = 1e-6
    with pytest.raises(TradingError, match="成交精度"):
        broker.execute([Order("AAA", "BUY", 1)], day, tiny_prices, "req-zero-px")


def test_holdout_uses_full_market_calendar_before_filtering_holdings(prices):
    day = prices.date.unique()[-10]
    next_day = prices.date.unique()[-9]
    # Remove BOTH held symbols AAA & BBB on next_day while CCC still trades
    trimmed = prices.loc[~((prices.date == next_day) & (prices.symbol.isin(["AAA", "BBB"])))]
    weights = pd.Series({"AAA": 0.5, "BBB": 0.5})
    with pytest.raises(DataError, match="缺少开盘价"):
        holdout_curve(trimmed, weights, day)


def test_remote_screen_rejects_tampered_evidence(documents, tmp_path):
    tampered_payload = None

    class TamperingHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            nonlocal tampered_payload
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            doc = dict(body["documents"][0])
            doc["source_url"] = "https://evil.example/forged"
            tampered_payload = {
                "run_id": str(uuid4()),
                "backend": "jevdb_llm",
                "query": body["query"],
                "asof": body["asof"],
                "inputs": len(body["documents"]),
                "elapsed_seconds": 0.1,
                "matches": [doc],
                "created_at": "2025-01-27T00:00:00+00:00",
                "stats": [],
                "operator": body["operator"],
            }
            raw = json.dumps(tampered_payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), TamperingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        settings = Settings(tmp_path, "llm", "", "", service_url=f"http://127.0.0.1:{port}", service_token="tok")
        with pytest.raises(ResearchUnavailable):
            screen(documents, "cloud", "2024-08-01", settings, mode="jevdb")
    finally:
        server.shutdown()
        server.server_close()


def test_agent_export_html_report_is_self_contained(prices, documents, tmp_path):
    day = str(prices.date.unique()[-30].date())
    settings = Settings(tmp_path, "jev", "", "")
    trace = run_workflow(
        prices, documents, "cloud", day, settings,
        mode="keyword", operator="any", strategy="erc",
        broker_path=tmp_path / "paper.sqlite3", approve_execution=False, include_holdout=True,
    )
    html_path = trace.export_html_report(tmp_path / "html-out")
    assert html_path.is_file()
    assert (tmp_path / "html-out" / "trace.json").is_file()
    content = html_path.read_text(encoding="utf-8")
    assert "HIGH_EXPLICIT_APPROVAL" in content
    assert "<script" not in content.lower()
    assert "AAA" in content and "BBB" in content


def test_desktop_stale_invalidation_same_day_account_and_html_report(prices, documents, tmp_path, monkeypatch, qtbot, qapp):
    monkeypatch.setenv("MATRIX_DATA_DIR", str(tmp_path))
    prices.to_csv(tmp_path / "prices.csv", index=False)
    documents.to_csv(tmp_path / "documents.csv", index=False)
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(STYLESHEET)
    win = MainWindow(Settings(tmp_path, "jev", "", ""))
    qtbot.addWidget(win)
    win.show()

    # 1. Research -> editing query invalidates stale results immediately
    win.navigate(1)
    qtbot.mouseClick(win.research.search, QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not win._jobs, timeout=10000)
    assert win.research.apply.isEnabled()
    win.research.query.setPlainText("other query")
    assert win.research.run is None
    assert not win.research.apply.isEnabled()
    assert win.research.table.frame_model.rowCount() == 0

    # 2. Portfolio -> creating account on the SAME day preserves valid computed risk
    day = pd.Timestamp(win.workspace.days[-30])
    win.workspace.set_date(day)
    win.navigate(2)
    qtbot.mouseClick(win.portfolio.calculate, QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not win._jobs, timeout=10000)
    assert win.workspace.risk is not None
    dialog = AccountDialog(win.workspace, win)
    qtbot.addWidget(dialog)
    dialog.start.setDate(QtCore.QDate(day.year, day.month, day.day))
    dialog.create()
    assert win.workspace.risk is not None  # preserved!

    # 3. Agent tab -> preview + offline HTML report button
    win.navigate(3)
    win.agent.query.setPlainText("cloud")
    qtbot.mouseClick(win.agent.preview_btn, QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not win._jobs, timeout=10000)
    assert win.agent.export_html_btn.isEnabled()
    report_path = win.agent.export_html(open_browser=False)
    assert report_path is not None and report_path.is_file()
    assert "下一步" in win.workflow.text()
