from PySide6 import QtCore
import pandas as pd
import pytest

from matrixlab.config import Settings
from matrixlab.desktop.dialogs import AccountDialog
from matrixlab.desktop.theme import STYLESHEET
from matrixlab.desktop.window import MainWindow


@pytest.fixture
def desktop(prices, documents, tmp_path, monkeypatch, qtbot, qapp):
    monkeypatch.setenv("MATRIX_DATA_DIR", str(tmp_path))
    prices.to_csv(tmp_path / "prices.csv", index=False)
    documents.to_csv(tmp_path / "documents.csv", index=False)
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(STYLESHEET)
    window = MainWindow(Settings(tmp_path, "jev", "", ""))
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)
    return window


def test_native_watchlist_selection_and_width(desktop, qtbot):
    assert desktop.watch.frame_model.rowCount() == 3
    desktop.watch.selectRow(1)
    desktop.select_watch(desktop.watch.frame_model.index(1, 0))
    assert desktop.symbol_title.text() == "BBB"
    assert set(desktop.chart.frame.symbol) == {"BBB"}
    qtbot.waitUntil(lambda: desktop.watch.horizontalHeader().length() <= desktop.watch.viewport().width())
    desktop.filter.setText("CCC")
    assert desktop.watch.frame_model.rowCount() == 1


def test_native_keyword_research_to_portfolio(desktop, qtbot):
    desktop.navigate(1)
    qtbot.mouseClick(desktop.research.search, QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not desktop._jobs, timeout=10000)
    assert desktop.research.run.backend == "keyword_baseline"
    assert len(desktop.research.run.matches) == 2
    qtbot.mouseClick(desktop.research.apply, QtCore.Qt.MouseButton.LeftButton)
    assert desktop.pages.currentIndex() == 2
    assert desktop.workspace.selected_symbols == ["AAA", "BBB"]
    qtbot.mouseClick(desktop.portfolio.calculate, QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not desktop._jobs, timeout=10000)
    assert desktop.workspace.risk is not None
    assert desktop.workspace.risk.weights.sum() == pytest.approx(1)


def test_native_account_order_and_clock(desktop, qtbot):
    ws = desktop.workspace
    assert not desktop.submit.isEnabled()
    dialog = AccountDialog(ws, desktop)
    qtbot.addWidget(dialog)
    day = pd.Timestamp(ws.days[80])
    dialog.start.setDate(QtCore.QDate(day.year, day.month, day.day))
    dialog.create()
    desktop.refresh_account()
    assert ws.broker.exists() and desktop.submit.isEnabled()
    qtbot.mouseClick(desktop.submit, QtCore.Qt.MouseButton.LeftButton)
    assert desktop.orders.frame_model.rowCount() == 1
    assert desktop.positions.frame_model.rowCount() == 1
    assert pd.Timestamp(ws.broker.state()[0]["clock"]) > day
    assert desktop.bottom.currentIndex() == 1


def test_native_empty_workspace_uses_real_data_actions(tmp_path, monkeypatch, qtbot):
    monkeypatch.setenv("MATRIX_DATA_DIR", str(tmp_path))
    window = MainWindow(Settings(tmp_path, "jev", "", ""))
    qtbot.addWidget(window)
    window.show()
    assert window.empty.isVisible()
    assert not window.chart.isVisible()
    assert window.watch.frame_model.rowCount() == 0
