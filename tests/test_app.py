from pathlib import Path

from streamlit.testing.v1 import AppTest


def click(app, label):
    next(item for item in app.button if item.label == label).click().run(timeout=30)
    assert not app.exception


def test_ui_matrix_and_account_flow(prices, documents, tmp_path, monkeypatch):
    monkeypatch.setenv("MATRIX_DATA_DIR", str(tmp_path))
    prices.to_csv(tmp_path / "prices.csv", index=False)
    documents.to_csv(tmp_path / "documents.csv", index=False)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    assert not app.exception
    click(app, "计算矩阵与最小方差组合")
    assert "risk" in app.session_state
    click(app, "创建本地模拟账户")
    assert (tmp_path / "paper.sqlite3").exists()
    click(app, "提交并推进至下一交易日")
    assert app.session_state["last_fills"][0]["quantity"] == 1


def test_ui_empty_workspace_has_actionable_instructions(tmp_path, monkeypatch):
    monkeypatch.setenv("MATRIX_DATA_DIR", str(tmp_path))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    assert not app.exception
    assert any("先下载真实行情" in item.value for item in app.info)
