from dataclasses import asdict
import json

import pandas as pd
from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg

from ..analytics import analyze, holdout_curve, performance
from ..data import DataError
from ..research import screen
from .charts import EquityChart
from .dialogs import SourceDialog, StockDialog
from .widgets import Table, button, label, panel


class ResearchPage(QtWidgets.QWidget):
    apply_selection = QtCore.Signal()

    def __init__(self, workspace, run_job, parent=None):
        super().__init__(parent)
        self.workspace, self.run_job = workspace, run_job
        self.run = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        header = QtWidgets.QHBoxLayout()
        header.addWidget(label("公司研究", "section"))
        header.addStretch()
        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(["离线关键词", "JEVDB语义"])
        header.addWidget(self.mode)
        layout.addLayout(header)
        self.query = QtWidgets.QPlainTextEdit("cloud software")
        self.query.setPlaceholderText("输入研究条件，例如：提供云计算服务的公司")
        self.query.setMaximumHeight(84)
        layout.addWidget(self.query)
        actions = QtWidgets.QHBoxLayout()
        self.search = button("检索公司资料", self.search_now, "primary")
        self.search.setObjectName("researchSearch")
        actions.addWidget(self.search)
        self.apply = button("加入组合研究", self.apply_now)
        self.apply.setEnabled(False)
        actions.addWidget(self.apply)
        actions.addStretch()
        actions.addWidget(button("导出记录", self.export))
        layout.addLayout(actions)
        self.summary = label("使用顶部研究日期过滤资料，双击结果查看原文与来源。", "muted")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = Table()
        self.table.doubleClicked.connect(self.open_source)
        layout.addWidget(self.table, 1)

    def search_now(self):
        if self.workspace.documents.empty:
            self.summary.setText("工作区没有公司资料。请从“文件”导入资料CSV，或下载课程数据。")
            return
        query, day = self.query.toPlainText(), self.workspace.asof
        mode = "keyword" if self.mode.currentIndex() == 0 else "jevdb"
        self.run_job(lambda: screen(self.workspace.documents, query, day, self.workspace.settings, mode), self.render)

    def render(self, run):
        self.run = run
        run.save(self.workspace.settings.data_dir / "research_runs")
        rows = [{"公司": r["symbol"], "资料标题": r["title"], "可用日期": pd.Timestamp(r["available_at"]).strftime("%Y-%m-%d"), "来源": r["source_url"]} for r in run.matches]
        self.table.replace(pd.DataFrame(rows, columns=["公司", "资料标题", "可用日期", "来源"]))
        self.table.setColumnWidth(0, 75)
        self.table.setColumnWidth(1, 230)
        self.summary.setText(f"{'离线关键词匹配' if run.backend == 'keyword_baseline' else 'JEVDB语义查询'} · {run.asof} · 检查{run.inputs}份资料 · 命中{len(run.matches)}份 · {run.elapsed_seconds:.2f}秒")
        self.apply.setEnabled(len({r["symbol"] for r in run.matches} & set(self.workspace.symbols)) >= 2)

    def apply_now(self):
        if self.run:
            self.workspace.selected_symbols = sorted({r["symbol"] for r in self.run.matches} & set(self.workspace.symbols))
            self.workspace.selection_asof = pd.Timestamp(self.run.asof)
            self.workspace.set_date(self.run.asof)
            self.apply_selection.emit()

    def open_source(self, index):
        if self.run and index.row() < len(self.run.matches):
            SourceDialog(self.run.matches[index.row()], self).exec()

    def export(self):
        if not self.run:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "导出研究记录", "research.json", "JSON (*.json)")
        if path:
            from pathlib import Path
            Path(path).write_text(json.dumps(asdict(self.run), ensure_ascii=False, indent=2, default=str), encoding="utf-8")


class PortfolioPage(QtWidgets.QWidget):
    calculated = QtCore.Signal()

    def __init__(self, workspace, run_job, parent=None):
        super().__init__(parent)
        self.workspace, self.run_job = workspace, run_job
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        controls = QtWidgets.QHBoxLayout()
        self.stocks = button("组合股票池", self.pick_stocks)
        controls.addWidget(self.stocks)
        controls.addWidget(label("回看", "muted"))
        self.lookback = QtWidgets.QSpinBox()
        self.lookback.setRange(60, 1260)
        self.lookback.setValue(252)
        self.lookback.setSuffix(" 日")
        self.lookback.setFixedWidth(92)
        controls.addWidget(self.lookback)
        controls.addWidget(label("收缩α", "muted"))
        self.alpha = QtWidgets.QDoubleSpinBox()
        self.alpha.setRange(0, 1)
        self.alpha.setSingleStep(.01)
        self.alpha.setValue(.05)
        self.alpha.setFixedWidth(75)
        controls.addWidget(self.alpha)
        controls.addStretch()
        self.calculate = button("计算组合", self.calculate_now, "primary")
        controls.addWidget(self.calculate)
        layout.addLayout(controls)
        stats = QtWidgets.QHBoxLayout()
        self.stat_values = []
        for caption in ["组合年化波动率", "有效收益率样本", "收缩后条件数"]:
            frame, box = panel()
            box.addWidget(label(caption, "muted"))
            value = label("—", "symbol")
            self.stat_values.append(value)
            box.addWidget(value)
            stats.addWidget(frame)
        layout.addLayout(stats)
        middle = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        weight_frame, weight_box = panel()
        weight_box.addWidget(label("目标配置 · 只做多", "section"))
        self.weights = Table(formats={"目标权重": lambda v: f"{v:.2%}"})
        weight_box.addWidget(self.weights)
        weight_box.addWidget(button("导出权重", self.export_weights))
        middle.addWidget(weight_frame)
        heat_frame, heat_box = panel()
        heat_box.addWidget(label("协方差矩阵 · 年化", "section"))
        self.heat = pg.PlotWidget()
        self.heat.setMenuEnabled(False)
        self.heat.hideButtons()
        self.heat.setAspectLocked()
        self.heat.setMouseEnabled(False, False)
        heat_box.addWidget(self.heat)
        self.diagnostics = label("Gram矩阵 / 半正定性 / 协方差收缩", "muted")
        self.diagnostics.setWordWrap(True)
        heat_box.addWidget(self.diagnostics)
        middle.addWidget(heat_frame)
        middle.setSizes([205, 420])
        layout.addWidget(middle, 3)
        layout.addWidget(label("样本外比较 · 次日开盘建仓，随后持有", "section"))
        self.curve = EquityChart()
        self.curve.setMinimumHeight(130)
        layout.addWidget(self.curve, 2)
        self.summary = label("选择股票后计算，研究日期与行情工作台共用。", "muted")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.lookback.valueChanged.connect(self.invalidate)
        self.alpha.valueChanged.connect(self.invalidate)

    def invalidate(self, *args):
        self.workspace.risk = None
        for value in self.stat_values:
            value.setText("—")
        self.summary.setText("输入已变更，请重新计算组合。")

    def pick_stocks(self):
        dialog = StockDialog(self.workspace, self)
        if dialog.exec():
            self.workspace.selected_symbols = dialog.selected
            self.workspace.selection_asof = None
            self.invalidate()

    def calculate_now(self):
        day = self.workspace.asof
        if self.workspace.selection_asof is not None and day < self.workspace.selection_asof:
            self.summary.setText("研究日期早于选股资料可用时间，已停止计算。")
            return
        symbols, lookback, alpha = self.workspace.selected_symbols.copy(), self.lookback.value(), self.alpha.value()
        self.run_job(lambda: (day, analyze(self.workspace.prices, symbols, day, lookback, alpha)), self.render)

    def render(self, result):
        day, risk = result
        if day != self.workspace.asof:
            return
        self.workspace.risk, self.workspace.risk_asof = risk, day
        for widget, text in zip(self.stat_values, [f"{risk.volatility:.2%}", str(len(risk.returns)), f"{risk.condition_after:.2f}"]):
            widget.setText(text)
        self.weights.replace(risk.weights.rename("目标权重").rename_axis("股票").reset_index())
        self.heat.clear()
        matrix = risk.covariance.to_numpy()
        image = pg.ImageItem(matrix.T)
        colors = pg.ColorMap([0, .5, 1], ["#1e2848", "#466aa0", "#81c5d3"])
        image.setLookupTable(colors.getLookupTable())
        image.setLevels((float(matrix.min()), float(matrix.max())))
        self.heat.addItem(image)
        ticks = [(i + .5, str(s)) for i, s in enumerate(risk.weights.index)]
        for side in ["left", "bottom"]:
            self.heat.getAxis(side).setTicks([ticks])
            self.heat.getAxis(side).setStyle(tickFont=pg.QtGui.QFont("Arial", 8))
        self.heat.autoRange()
        self.diagnostics.setText(f"条件数 {risk.condition_before:.2f} → {risk.condition_after:.2f}    最小特征值 {risk.eigenvalues.min():.4f}")
        try:
            curve = holdout_curve(self.workspace.prices, risk.weights, day)
            self.curve.set_frame(curve)
            metrics = performance(curve)
            self.summary.setText(f"{day:%Y-%m-%d}拟合 · 样本外累计收益 {metrics.iloc[0, 0]:.2%} / 等权 {metrics.iloc[1, 0]:.2%} · 首笔总成本15bp · 可分份额比较")
        except DataError as exc:
            self.curve.clear()
            self.summary.setText(str(exc))
        self.calculated.emit()

    def export_weights(self):
        if self.workspace.risk is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "导出权重", "weights.csv", "CSV (*.csv)")
        if path:
            self.workspace.risk.weights.to_csv(path)
