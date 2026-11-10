import argparse
import os
from pathlib import Path
import sys

from PySide6 import QtCore, QtGui, QtWidgets

from ..config import Settings
from .theme import STYLESHEET
from .window import MainWindow


def main(argv=None):
    parser = argparse.ArgumentParser(description="Matrix Workbench native desktop")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--screenshot", type=Path, help="Save the actual rendered window and exit")
    parser.add_argument("--self-test-report", type=Path, help="Run a frozen-build check in a new test workspace and exit")
    args = parser.parse_args(argv)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName("MatrixWorkbench")
    app.setOrganizationName("MatrixLab")
    app.setStyle("Fusion")
    families = QtGui.QFontDatabase.families()
    family = next((x for x in ["Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "Segoe UI"] if x in families), "Arial")
    app.setFont(QtGui.QFont(family, 9))
    app.setStyleSheet(STYLESHEET)
    if args.workspace:
        os.environ["MATRIX_DATA_DIR"] = str(args.workspace.resolve())
    elif getattr(sys, "frozen", False):
        os.environ.setdefault("MATRIX_DATA_DIR", str(Path(QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.AppLocalDataLocation)) / "workspace"))
    window = MainWindow(Settings.load())
    window.show()
    if args.self_test_report:
        def self_check():
            import json
            import pandas as pd
            from ..analytics import analyze
            from ..research import screen
            from ..trading import Order
            try:
                ws = window.workspace
                if ws.broker.exists() or ws.prices.empty:
                    raise RuntimeError("Frozen check requires a new workspace with test data and no account")
                day = pd.Timestamp(ws.days[int(len(ws.days) * .7)])
                risk = analyze(ws.prices, ws.symbols, day)
                run = screen(ws.documents, "fixture", day, ws.settings, "keyword")
                ws.broker.initialize(100000, day)
                ws.set_date(day)
                window.refresh_account()
                window.quantity.setValue(1)
                window.submit_order()
                assert len(ws.broker.state()[3]) == 1
                assert abs(risk.weights.sum() - 1) < 1e-7
                assert run.matches
                report = {"ok": True, "platform": sys.platform, "checks": ["native-window", "matrix", "keyword", "paper-order"]}
                code = 0
            except Exception as exc:
                report, code = {"ok": False, "error": str(exc)}, 1
            args.self_test_report.parent.mkdir(parents=True, exist_ok=True)
            args.self_test_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            window.close()
            app.exit(code)
        QtCore.QTimer.singleShot(200, self_check)
    elif args.screenshot:
        def capture():
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(args.screenshot))
            app.quit()
        QtCore.QTimer.singleShot(1000, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
