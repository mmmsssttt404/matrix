from dataclasses import asdict
import json

import pandas as pd
from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg

from ..analytics import analyze, holdout_curve, performance, rolling_holdout_curve, shrinkage_path
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
        self.operator = QtWidgets.QComboBox()
        self.operator.addItems(["AND全部词", "OR任意词"])
        header.addWidget(self.operator)
        self.jev_op = QtWidgets.QComboBox()
        self.jev_op.addItems(["jev_holds 布尔", "jev_probability 置信度", "jev_choose 行业分类", "Prune-First 剪枝"])
        self.jev_op.setToolTip("仅在 JEVDB 语义模式下生效")
        header.addWidget(self.jev_op)
        self.threshold = QtWidgets.QDoubleSpinBox()
        self.threshold.setRange(0.0, 1.0)
        self.threshold.setSingleStep(0.05)
        self.threshold.setValue(0.50)
        self.threshold.setPrefix("τ≥")
        self.threshold.setFixedWidth(82)
        self.threshold.setToolTip("jev_probability 置信度截断阈值")
        header.addWidget(self.threshold)
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
        self.mode.currentIndexChanged.connect(self._sync_controls)
        self.jev_op.currentIndexChanged.connect(self._sync_controls)
        self._sync_controls()

    def _sync_controls(self):
        is_jev = self.mode.currentIndex() == 1
        self.operator.setEnabled(not is_jev)
        self.jev_op.setEnabled(is_jev)
        self.threshold.setEnabled(is_jev and self.jev_op.currentIndex() == 1)

    def search_now(self):
        if self.workspace.documents.empty:
            self.summary.setText("工作区没有公司资料。请从“文件”导入资料CSV，或下载课程数据。")
            return
        query, day = self.query.toPlainText(), self.workspace.asof
        mode = "keyword" if self.mode.currentIndex() == 0 else "jevdb"
        operator = "all" if self.operator.currentIndex() == 0 else "any"
        jev_ops = ["holds", "probability", "choose", "prune_then_decide"]
        jev_op = jev_ops[self.jev_op.currentIndex()]
        threshold = self.threshold.value()
        prune_k = 6 if jev_op == "prune_then_decide" else None
        self.run_job(
            lambda: screen(
                self.workspace.documents, query, day, self.workspace.settings,
                mode, 100, operator, jev_op=jev_op, threshold=threshold, prune_k=prune_k,
            ),
            self.render,
        )

    def render(self, run):
        self.run = run
        run.save(self.workspace.settings.data_dir / "research_runs")
        rows = []
        for r in run.matches:
            score_val = r.get("match_score", "")
            if isinstance(score_val, float):
                score_val = f"{score_val:.3f}"
            rows.append({
                "公司": r["symbol"],
                "相关度/标签": r.get("semantic_label") or score_val,
                "资料标题": r["title"],
                "可用日期": pd.Timestamp(r["available_at"]).strftime("%Y-%m-%d"),
                "来源": r["source_url"],
            })
        self.table.replace(pd.DataFrame(rows, columns=["公司", "相关度/标签", "资料标题", "可用日期", "来源"]))
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 95)
        self.table.setColumnWidth(2, 220)
        mode = "离线关键词BM25" if run.backend.startswith("keyword") else f"JEVDB语义({run.jev_op})"
        prune_note = ""
        if run.pruned_from is not None:
            prune_note = (f" · 粗排命中不足，已回退全量({run.inputs})" if run.prune_fallback
                          else f" · 粗排剪枝 {run.pruned_from}→{run.inputs}")
        self.summary.setText(
            f"{mode} · {run.asof} · 评估{run.inputs}份资料{prune_note} · 命中{len(run.matches)}份 · {run.elapsed_seconds:.2f}秒"
        )
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
        self.use_lw = QtWidgets.QCheckBox("Ledoit-Wolf最优α*")
        self.use_lw.setToolTip("自动采用Ledoit-Wolf(2004)解析最优收缩强度")
        controls.addWidget(self.use_lw)
        controls.addStretch()
        self.calculate = button("计算组合", self.calculate_now, "primary")
        controls.addWidget(self.calculate)
        layout.addLayout(controls)

        stats = QtWidgets.QHBoxLayout()
        self.stat_values = []
        for caption in ["年化波动率(原始Σ / 收缩Σ)", "有效收益率样本", "条件数(原→缩)", "Ledoit-Wolf α* / 有效N"]:
            frame, box = panel()
            box.addWidget(label(caption, "muted"))
            value = label("—", "symbol")
            self.stat_values.append(value)
            box.addWidget(value)
            stats.addWidget(frame)
        layout.addLayout(stats)

        self.tabs = QtWidgets.QTabWidget()
        # Tab 1: Weights, Risk Contribution & Covariance Heatmap
        tab_cov = QtWidgets.QWidget()
        cov_layout = QtWidgets.QVBoxLayout(tab_cov)
        middle = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        weight_frame, weight_box = panel()
        weight_box.addWidget(label("权重对照 · 只做多QP / 闭式解 / ERC风险平价", "section"))
        self.weights = Table(formats={
            "目标权重": lambda v: f"{v:.2%}",
            "闭式解": lambda v: f"{v:.2%}" if pd.notna(v) else "—",
            "ERC风险平价": lambda v: f"{v:.2%}",
        })
        weight_box.addWidget(self.weights)
        weight_box.addWidget(label("风险贡献 · 欧拉分解 (Σ CTR = σ_p)", "muted"))
        self.risk_table = Table(formats={
            "权重": lambda v: f"{v:.2%}",
            "风险贡献": lambda v: f"{v:.2%}",
            "风险占比": lambda v: f"{v:.2%}",
        })
        weight_box.addWidget(self.risk_table)
        weight_box.addWidget(button("导出权重", self.export_weights))
        middle.addWidget(weight_frame)
        heat_frame, heat_box = panel()
        heat_box.addWidget(label("协方差矩阵 · 年化", "section"))
        self.heat = pg.PlotWidget()
        self.heat.setMenuEnabled(False)
        self.heat.hideButtons()
        self.heat.setAspectLocked(False)
        self.heat.setMouseEnabled(False, False)
        heat_box.addWidget(self.heat)
        self.diagnostics = label("Gram矩阵 / 半正定性 / 协方差收缩 / KKT残差", "muted")
        self.diagnostics.setWordWrap(True)
        heat_box.addWidget(self.diagnostics)
        middle.addWidget(heat_frame)
        middle.setSizes([280, 420])
        cov_layout.addWidget(middle, 1)
        self.tabs.addTab(tab_cov, "权重与协方差")

        # Tab 2: PCA Spectrum & Shrinkage Path
        tab_pca = QtWidgets.QWidget()
        pca_layout = QtWidgets.QHBoxLayout(tab_pca)
        pca_left, pca_lbox = panel()
        pca_lbox.addWidget(label("相关系数矩阵 PCA 解释方差", "section"))
        self.pca_table = Table(formats={
            "特征值": lambda v: f"{v:.4f}",
            "解释方差": lambda v: f"{v:.2%}",
            "累计解释": lambda v: f"{v:.2%}",
        })
        pca_lbox.addWidget(self.pca_table)
        pca_lbox.addWidget(label("前3主成分载荷", "muted"))
        self.loadings_table = Table(formats={
            "PC1": lambda v: f"{v:+.3f}",
            "PC2": lambda v: f"{v:+.3f}",
            "PC3": lambda v: f"{v:+.3f}",
        })
        pca_lbox.addWidget(self.loadings_table)
        pca_layout.addWidget(pca_left, 1)
        pca_right, pca_rbox = panel()
        pca_rbox.addWidget(label("协方差收缩路径 (Σ_α 谱演化)", "section"))
        self.shrink_table = Table(formats={
            "α": lambda v: f"{v:.2f}",
            "条件数": lambda v: f"{v:.2f}",
            "λ_min(缩)": lambda v: f"{v:.4f}",
            "原波动率": lambda v: f"{v:.2%}",
            "最大权重": lambda v: f"{v:.2%}",
            "有效N": lambda v: f"{v:.2f}",
        })
        pca_rbox.addWidget(self.shrink_table)
        pca_layout.addWidget(pca_right, 1)
        self.tabs.addTab(tab_pca, "PCA与收缩路径")

        # Tab 3: Out-of-Sample & Rolling Backtest + Performance Table
        tab_bt = QtWidgets.QWidget()
        bt_layout = QtWidgets.QVBoxLayout(tab_bt)
        bt_top = QtWidgets.QHBoxLayout()
        bt_top.addWidget(label("样本外比较 · 次日开盘建仓（单次持有 / 月度滚动）", "section"))
        bt_top.addStretch()
        self.rolling_btn = button("运行月度滚动对比(含ERC与LW)", self.run_rolling)
        bt_top.addWidget(self.rolling_btn)
        bt_layout.addLayout(bt_top)
        self.curve = EquityChart()
        self.curve.setMinimumHeight(170)
        bt_layout.addWidget(self.curve, 2)
        self.perf_table = Table(formats={
            "累计收益": lambda v: f"{v:.2%}",
            "最大回撤": lambda v: f"{v:.2%}",
            "年化收益": lambda v: f"{v:.2%}",
            "年化波动率": lambda v: f"{v:.2%}",
            "夏普比率": lambda v: f"{v:.2f}" if pd.notna(v) else "—",
            "累计单边换手": lambda v: f"{v:.1%}",
            "年化换手率": lambda v: f"{v:.1%}",
        })
        bt_layout.addWidget(self.perf_table, 1)
        self.tabs.addTab(tab_bt, "样本外与滚动回测")

        layout.addWidget(self.tabs, 1)
        self.summary = label("选择股票后计算，研究日期与行情工作台共用。", "muted")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.lookback.valueChanged.connect(self.invalidate)
        self.alpha.valueChanged.connect(self.invalidate)
        self.use_lw.toggled.connect(self._toggle_lw)

    def _toggle_lw(self, checked):
        self.alpha.setEnabled(not checked)
        self.invalidate()

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
        symbols = self.workspace.selected_symbols.copy()
        lookback, alpha, use_lw = self.lookback.value(), self.alpha.value(), self.use_lw.isChecked()

        def job():
            risk = analyze(self.workspace.prices, symbols, day, lookback, alpha, use_ledoit_wolf=use_lw)
            path = shrinkage_path(self.workspace.prices, symbols, day, lookback)
            return day, risk, path

        self.run_job(job, self.render)

    def render(self, result):
        day, risk, path = result
        if day != self.workspace.asof:
            return
        self.workspace.risk, self.workspace.risk_asof = risk, day
        for widget, text in zip(self.stat_values, [
            f"{risk.volatility:.2%} / {risk.regularized_volatility:.2%}",
            str(len(risk.returns)),
            f"{risk.condition_before:.1f} → {risk.condition_after:.1f}",
            f"{risk.ledoit_wolf_alpha:.3f} / {risk.effective_n:.1f}",
        ]):
            widget.setText(text)
        self.weights.replace(pd.DataFrame({
            "股票": risk.weights.index,
            "目标权重": risk.weights.to_numpy(),
            "闭式解": risk.closed_form_weights.to_numpy(),
            "ERC风险平价": risk.risk_parity_weights.to_numpy(),
        }))
        self.risk_table.replace(pd.DataFrame({
            "股票": risk.weights.index,
            "权重": risk.weights.to_numpy(),
            "风险贡献": risk.risk_contributions.to_numpy(),
            "风险占比": risk.risk_share.to_numpy(),
        }))
        pca_df = pd.DataFrame({
            "主成分": [f"PC{i + 1}" for i in range(len(risk.pca_eigenvalues))],
            "特征值": risk.pca_eigenvalues,
            "解释方差": risk.explained_variance,
            "累计解释": risk.explained_variance.cumsum(),
        })
        self.pca_table.replace(pca_df)
        cols = list(risk.pca_loadings.columns[:min(3, risk.pca_loadings.shape[1])])
        load_df = risk.pca_loadings[cols].reset_index().rename(columns={"index": "股票"})
        self.loadings_table.replace(load_df)
        self.shrink_table.replace(path.rename(columns={
            "alpha": "α", "condition": "条件数", "min_eigenvalue": "λ_min(缩)",
            "volatility": "原波动率", "max_weight": "最大权重", "effective_n": "有效N",
        })[["α", "条件数", "λ_min(缩)", "原波动率", "最大权重", "有效N"]])
        self.shrink_table.resizeColumnsToContents()

        self.heat.clear()
        matrix = risk.covariance.to_numpy()
        image = pg.ImageItem(matrix.T)
        colors = pg.ColorMap([0, .5, 1], ["#1e2848", "#466aa0", "#81c5d3"])
        image.setLookupTable(colors.getLookupTable())
        image.setLevels((float(matrix.min()), float(matrix.max())))
        self.heat.addItem(image)
        self.heat.getAxis("left").setTicks([[(i + .5, f"{i+1} {s}") for i, s in enumerate(risk.weights.index)]])
        self.heat.getAxis("bottom").setTicks([[(i + .5, str(i + 1)) for i in range(len(risk.weights))]])
        for side in ["left", "bottom"]:
            self.heat.getAxis(side).setStyle(tickFont=pg.QtGui.QFont("Arial", 8))
        self.heat.autoRange()
        closure = ("闭式解满足非负约束" if risk.closed_form_feasible
                   else f"闭式解含负权重 {risk.closed_form_weights.min():.1%}，非负约束起作用")
        top = risk.explained_variance
        self.diagnostics.setText(
            f"α={risk.alpha:.3f} · 条件数 {risk.condition_before:.2f} → {risk.condition_after:.2f}"
            f" · λ_min {risk.eigenvalues.min():.4f} → {risk.regularized_eigenvalues.min():.4f}"
            f" · {'正定' if risk.positive_definite else '半正定'}\n"
            f"PC1 {top[0]:.1%} / 前两主成分 {top[:2].sum():.1%} · {closure}"
            f" · KKT互补残差 {risk.kkt_complementarity_error:.2e}"
        )
        try:
            curve = holdout_curve(self.workspace.prices, risk.weights, day)
            self.curve.set_frame(curve)
            metrics = performance(curve).reset_index().rename(columns={"index": "策略"})
            self.perf_table.replace(metrics)
            self.summary.setText(
                f"{day:%Y-%m-%d}拟合 · 样本外累计收益 {metrics.iloc[0]['累计收益']:.2%} / 等权 {metrics.iloc[1]['累计收益']:.2%}"
                f" · 夏普 {metrics.iloc[0]['夏普比率']:.2f} / {metrics.iloc[1]['夏普比率']:.2f} · 首笔总成本15bp"
            )
        except DataError as exc:
            self.curve.clear()
            self.perf_table.replace(pd.DataFrame())
            self.summary.setText(str(exc))
        self.calculated.emit()

    def run_rolling(self):
        day = self.workspace.asof
        if self.workspace.prices.empty or day is None:
            return
        if self.workspace.selection_asof is not None and day < self.workspace.selection_asof:
            self.summary.setText("研究日期早于选股资料可用时间，已停止滚动回测。")
            return
        symbols = self.workspace.selected_symbols.copy()
        lookback, alpha = self.lookback.value(), self.alpha.value()
        self.run_job(
            lambda: (day, *rolling_holdout_curve(self.workspace.prices, symbols, day, lookback=lookback, alpha=alpha)),
            self._render_rolling,
        )

    def _render_rolling(self, result):
        day, curve, turnover = result
        if day != self.workspace.asof:
            return
        self.curve.set_frame(curve)
        perf = performance(curve).join(turnover).reset_index().rename(columns={"index": "策略"})
        self.perf_table.replace(perf)
        self.tabs.setCurrentIndex(2)
        self.summary.setText(
            f"月度滚动调仓对比完成（调仓{int(turnover['调仓次数'].iloc[0])}次，单边交易成本15bp，次日开盘撮合）。"
        )

    def export_weights(self):
        if self.workspace.risk is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "导出权重", "weights.csv", "CSV (*.csv)")
        if path:
            self.workspace.risk.weights.to_csv(path)
