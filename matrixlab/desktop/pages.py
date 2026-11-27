from dataclasses import asdict
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from ..agent import RISK_HIGH, run_workflow
from ..analytics import analyze, holdout_curve, performance, rolling_holdout_curve, shrinkage_path
from ..data import DataError
from ..research import screen
from ..trading import Order, TradingError
from .charts import EquityChart
from .dialogs import SourceDialog, StockDialog
from .widgets import Table, button, label, panel


class ResearchPage(QtWidgets.QWidget):
    apply_selection = QtCore.Signal()
    state_changed = QtCore.Signal()

    def __init__(self, workspace, run_job, parent=None):
        super().__init__(parent)
        self.workspace, self.run_job = workspace, run_job
        self.run = None
        self._generation = 0
        self._run_context = None
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
        self.jev_op.addItems(["jev_holds 布尔", "jev_probability 置信度", "jev_choose 行业分类", "jev_score 打分排序", "Prune-First 剪枝"])
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
        self.prune_k = QtWidgets.QSpinBox()
        self.prune_k.setRange(1, 50)
        self.prune_k.setValue(3)
        self.prune_k.setPrefix("K=")
        self.prune_k.setFixedWidth(66)
        self.prune_k.setToolTip("Prune-First 第一阶段 BM25 粗排保留候选文档数（消融最优 K=3）")
        header.addWidget(self.prune_k)
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
        self.query.textChanged.connect(self.invalidate)
        self.mode.currentIndexChanged.connect(self.invalidate)
        self.operator.currentIndexChanged.connect(self.invalidate)
        self.jev_op.currentIndexChanged.connect(self.invalidate)
        self.threshold.valueChanged.connect(self.invalidate)
        self.prune_k.valueChanged.connect(self.invalidate)
        workspace.date_changed.connect(self.invalidate)
        workspace.changed.connect(self.invalidate)
        self._sync_controls()

    def context(self):
        return (
            self._generation,
            self.workspace.revision,
            self.workspace.asof,
            self.query.toPlainText(),
            self.mode.currentIndex(),
            self.operator.currentIndex(),
            self.jev_op.currentIndex(),
            round(self.threshold.value(), 4),
            self.prune_k.value(),
            self.workspace.settings,
        )

    def invalidate(self, *args):
        self._generation += 1
        self.run = self._run_context = None
        self.apply.setEnabled(False)
        self.table.replace(pd.DataFrame())
        self.summary.setText("研究日期、条件或数据已变更，请重新检索公司资料。")
        self.state_changed.emit()

    def _sync_controls(self):
        is_jev = self.mode.currentIndex() == 1
        self.operator.setEnabled(not is_jev)
        self.jev_op.setEnabled(is_jev)
        self.threshold.setEnabled(is_jev and self.jev_op.currentIndex() == 1)
        self.prune_k.setEnabled(is_jev and self.jev_op.currentIndex() == 4)

    def search_now(self):
        self.invalidate()
        if self.workspace.documents.empty:
            self.summary.setText("工作区没有公司资料。请从“文件”导入资料CSV，或下载课程数据。")
            return
        query, day = self.query.toPlainText(), self.workspace.asof
        mode = "keyword" if self.mode.currentIndex() == 0 else "jevdb"
        operator = "all" if self.operator.currentIndex() == 0 else "any"
        jev_ops = ["holds", "probability", "choose", "score", "prune_then_decide"]
        jev_op = jev_ops[self.jev_op.currentIndex()]
        threshold = self.threshold.value()
        prune_k = self.prune_k.value() if jev_op == "prune_then_decide" else None
        context = self.context()
        docs = self.workspace.documents.copy(deep=True)
        settings = self.workspace.settings
        self.summary.setText("正在检索公司资料，完成后可将命中股票加入组合。")
        self.run_job(
            lambda: screen(
                docs, query, day, settings,
                mode, 100, operator, jev_op=jev_op, threshold=threshold, prune_k=prune_k,
            ),
            lambda run: self.render(run, context),
        )

    def render(self, run, context=None):
        if context is not None and context != self.context():
            return
        self.run = run
        self._run_context = context if context is not None else self.context()
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
        usable = len({r["symbol"] for r in run.matches} & set(self.workspace.symbols))
        self.summary.setText(
            f"{mode} · {run.asof} · 评估{run.inputs}份资料{prune_note} · 命中{len(run.matches)}份 / 可用{usable}只 · {run.elapsed_seconds:.2f}秒"
        )
        self.apply.setEnabled(usable >= 2)
        self.state_changed.emit()

    def apply_now(self):
        if not self.run or self._run_context != self.context():
            self.invalidate()
            return
        symbols = sorted({r["symbol"] for r in self.run.matches} & set(self.workspace.symbols))
        if len(symbols) < 2:
            return
        self.workspace.set_date(self.run.asof)
        self.workspace.set_selection(symbols, self.run.asof)
        self.apply_selection.emit()
        self.state_changed.emit()

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
    state_changed = QtCore.Signal()

    def __init__(self, workspace, run_job, parent=None):
        super().__init__(parent)
        self.workspace, self.run_job = workspace, run_job
        self._generation = 0
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
        controls.addWidget(label("调仓目标", "muted"))
        self.strategy = QtWidgets.QComboBox()
        self.strategy.addItems(["最小方差(QP)", "风险平价(ERC)"])
        self.strategy.setToolTip("切换右侧“按组合目标调仓”与风险分解采用的目标权重")
        controls.addWidget(self.strategy)
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
        self.strategy.currentIndexChanged.connect(self._change_strategy)
        workspace.selection_changed.connect(self.invalidate)
        workspace.changed.connect(self.invalidate)

    def context(self):
        return (
            self._generation,
            self.workspace.revision,
            self.workspace.asof,
            tuple(self.workspace.selected_symbols),
            self.workspace.selection_asof,
            self.lookback.value(),
            round(self.alpha.value(), 4),
            self.use_lw.isChecked(),
        )

    def _toggle_lw(self, checked):
        self.alpha.setEnabled(not checked)
        self.invalidate()

    def _change_strategy(self, index):
        self.workspace.risk_strategy = "erc" if index == 1 else "min_var"
        if self.workspace.risk is not None:
            self._refresh_risk_breakdown(self.workspace.risk)
            self.calculated.emit()
            self.state_changed.emit()

    def _refresh_risk_breakdown(self, risk):
        weights = self.workspace.target_weights
        cov = risk.regularized if self.workspace.risk_strategy == "erc" else risk.covariance
        w_vec = weights.to_numpy(dtype=float)
        c_mat = cov.to_numpy(dtype=float)
        vol = float(np.sqrt(max(float(w_vec @ c_mat @ w_vec), 0.0)))
        ctr = (w_vec * (c_mat @ w_vec) / vol) if vol > 0 else np.zeros_like(w_vec)
        share = (ctr / vol) if vol > 0 else np.zeros_like(w_vec)
        self.risk_table.replace(pd.DataFrame({
            "股票": weights.index,
            "权重": w_vec,
            "风险贡献": ctr,
            "风险占比": share,
        }))

    def invalidate(self, *args):
        self._generation += 1
        self.workspace.clear_risk()
        for value in self.stat_values:
            value.setText("—")
        for tbl in (self.weights, self.risk_table, self.pca_table, self.loadings_table, self.shrink_table, self.perf_table):
            tbl.replace(pd.DataFrame())
        self.heat.clear()
        for side in ("left", "bottom"):
            self.heat.getAxis(side).setTicks([])
        self.curve.clear()
        self.diagnostics.setText("Gram矩阵 / 半正定性 / 协方差收缩 / KKT残差 · 待重新计算")
        self.summary.setText("输入已变更，请重新计算组合。")
        self.state_changed.emit()

    def pick_stocks(self):
        dialog = StockDialog(self.workspace, self)
        if dialog.exec():
            self.workspace.set_selection(dialog.selected)

    def calculate_now(self):
        self.invalidate()
        day = self.workspace.asof
        if day is None or len(self.workspace.selected_symbols) < 2:
            self.summary.setText("请先载入行情，并选择至少两只股票。")
            return
        if self.workspace.selection_asof is not None and day < self.workspace.selection_asof:
            self.summary.setText("研究日期早于选股资料可用时间，已停止计算。")
            return
        symbols = self.workspace.selected_symbols.copy()
        lookback, alpha, use_lw = self.lookback.value(), self.alpha.value(), self.use_lw.isChecked()
        prices = self.workspace.prices.copy(deep=True)
        context = self.context()

        def job():
            risk = analyze(prices, symbols, day, lookback, alpha, use_ledoit_wolf=use_lw)
            path = shrinkage_path(prices, symbols, day, lookback)
            return day, risk, path

        self.run_job(job, lambda result: self.render(result, context))

    def render(self, result, context=None):
        day, risk, path = result
        if context is not None and context != self.context():
            return
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
        self._refresh_risk_breakdown(risk)
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
        self.state_changed.emit()

    def run_rolling(self):
        day = self.workspace.asof
        if self.workspace.prices.empty or day is None:
            return
        if self.workspace.selection_asof is not None and day < self.workspace.selection_asof:
            self.summary.setText("研究日期早于选股资料可用时间，已停止滚动回测。")
            return
        symbols = self.workspace.selected_symbols.copy()
        lookback, alpha = self.lookback.value(), self.alpha.value()
        prices = self.workspace.prices.copy(deep=True)
        context = self.context()
        self.run_job(
            lambda: (day, *rolling_holdout_curve(prices, symbols, day, lookback=lookback, alpha=alpha)),
            lambda res: self._render_rolling(res, context),
        )

    def _render_rolling(self, result, context=None):
        day, curve, turnover = result
        if context is not None and context != self.context():
            return
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
        risk = self.workspace.risk
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "导出权重与诊断", "weights.csv", "CSV (*.csv)")
        if path:
            pd.DataFrame({
                "symbol": risk.weights.index,
                "min_var_weight": risk.weights.to_numpy(),
                "closed_form_weight": risk.closed_form_weights.to_numpy(),
                "erc_weight": risk.risk_parity_weights.to_numpy(),
                "risk_contribution": risk.risk_contributions.to_numpy(),
                "risk_share": risk.risk_share.to_numpy(),
            }).to_csv(path, index=False)


class AgentPage(QtWidgets.QWidget):
    """Four-layer Agentic workflow console with explicit human approval gate."""

    executed = QtCore.Signal(str)
    state_changed = QtCore.Signal()

    def __init__(self, workspace, run_job, parent=None):
        super().__init__(parent)
        self.workspace, self.run_job = workspace, run_job
        self.trace = None
        self._generation = 0
        self.report_path = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)

        header = QtWidgets.QHBoxLayout()
        header.addWidget(label("Agent 四层工作流", "section"))
        header.addStretch()
        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(["离线关键词", "JEVDB语义"])
        header.addWidget(self.mode)
        self.operator = QtWidgets.QComboBox()
        self.operator.addItems(["OR任意词", "AND全部词"])
        header.addWidget(self.operator)
        self.jev_op = QtWidgets.QComboBox()
        self.jev_op.addItems(["jev_holds 布尔", "jev_probability 置信度", "jev_choose 行业分类", "jev_score 打分排序", "Prune-First 剪枝"])
        header.addWidget(self.jev_op)
        self.strategy = QtWidgets.QComboBox()
        self.strategy.addItems(["最小方差(QP)", "风险平价(ERC)"])
        header.addWidget(self.strategy)
        self.use_lw = QtWidgets.QCheckBox("Ledoit-Wolf α*")
        self.use_lw.setChecked(True)
        header.addWidget(self.use_lw)
        layout.addLayout(header)

        self.query = QtWidgets.QPlainTextEdit("cloud software")
        self.query.setPlaceholderText("输入自然语言研究需求，系统按 Preamble → Plan → Retrieve → Risk → Proposal 编排，执行写入需人工显式审批。")
        self.query.setMaximumHeight(48)
        layout.addWidget(self.query)

        actions = QtWidgets.QHBoxLayout()
        self.preview_btn = button("运行四层工作流（预览）", self.run_preview, "primary")
        self.preview_btn.setObjectName("agentPreview")
        actions.addWidget(self.preview_btn)
        self.approve_btn = button("人工批准并执行撮合", self.approve_now, "buy")
        self.approve_btn.setObjectName("agentApprove")
        self.approve_btn.setEnabled(False)
        actions.addWidget(self.approve_btn)
        actions.addStretch()
        self.export_html_btn = button("生成可复查 HTML 报告", self.export_html)
        self.export_html_btn.setEnabled(False)
        actions.addWidget(self.export_html_btn)
        self.export_btn = button("导出审计轨迹 JSON", self.export_trace)
        self.export_btn.setEnabled(False)
        actions.addWidget(self.export_btn)
        layout.addLayout(actions)

        self.summary = label("遵循 Lec0 四层架构与三级人工风控：预览阶段严格只读、零落盘，仅点击“人工批准并执行撮合”后才原子写入 SQLite 账本。", "muted")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        trace_panel, trace_box = panel()
        trace_box.addWidget(label("四层执行轨迹与风险分级门控（LOW_AUTO / MEDIUM_CONFIRM / HIGH_EXPLICIT_APPROVAL）", "section"))
        self.steps_table = Table()
        trace_box.addWidget(self.steps_table)
        splitter.addWidget(trace_panel)

        order_panel, order_box = panel()
        order_box.addWidget(label("调仓提案预览 / 原子撮合成交明细（次日复权开盘价 + 单列手续费与滑点）", "section"))
        self.orders_table = Table(formats={"目标权重": lambda v: f"{v:.2%}" if pd.notna(v) else "—"})
        order_box.addWidget(self.orders_table)
        splitter.addWidget(order_panel)
        splitter.setSizes([270, 230])
        layout.addWidget(splitter, 1)

        self.mode.currentIndexChanged.connect(self._sync_controls)
        self.query.textChanged.connect(self.invalidate)
        self.mode.currentIndexChanged.connect(self.invalidate)
        self.operator.currentIndexChanged.connect(self.invalidate)
        self.jev_op.currentIndexChanged.connect(self.invalidate)
        self.strategy.currentIndexChanged.connect(self.invalidate)
        self.use_lw.toggled.connect(self.invalidate)
        workspace.changed.connect(self.invalidate)
        self._sync_controls()

    def context(self):
        return (
            self._generation,
            self.workspace.revision,
            self.workspace.asof,
            self.query.toPlainText(),
            self.mode.currentIndex(),
            self.operator.currentIndex(),
            self.jev_op.currentIndex(),
            self.strategy.currentIndex(),
            self.use_lw.isChecked(),
        )

    def _sync_controls(self):
        is_jev = self.mode.currentIndex() == 1
        self.operator.setEnabled(not is_jev)
        self.jev_op.setEnabled(is_jev)

    def invalidate(self, *args):
        self._generation += 1
        if self.trace is not None and not self.trace.approved_execution:
            self.trace = None
            self.report_path = None
            self.approve_btn.setEnabled(False)
            self.export_btn.setEnabled(False)
            self.export_html_btn.setEnabled(False)
            self.steps_table.replace(pd.DataFrame())
            self.orders_table.replace(pd.DataFrame())
            self.state_changed.emit()

    def run_preview(self):
        self.invalidate()
        if self.workspace.prices.empty or self.workspace.documents.empty:
            self.summary.setText("当前工作区缺少行情或公司资料，请先下载数据或导入 CSV。")
            return
        query = self.query.toPlainText().strip()
        day = str(self.workspace.asof.date())
        mode = "keyword" if self.mode.currentIndex() == 0 else "jevdb"
        operator = "any" if self.operator.currentIndex() == 0 else "all"
        jev_ops = ["holds", "probability", "choose", "score", "prune_then_decide"]
        jev_op = jev_ops[self.jev_op.currentIndex()]
        prune_k = 3 if jev_op == "prune_then_decide" else None
        strategy = "erc" if self.strategy.currentIndex() == 1 else "min_var"
        use_lw = self.use_lw.isChecked()
        broker_path = self.workspace.broker.path
        prices = self.workspace.prices.copy(deep=True)
        docs = self.workspace.documents.copy(deep=True)
        settings = self.workspace.settings
        context = self.context()

        self.run_job(
            lambda: run_workflow(
                prices,
                docs,
                query,
                day,
                settings,
                mode=mode,
                operator=operator,
                jev_op=jev_op,
                prune_k=prune_k,
                use_ledoit_wolf=use_lw,
                strategy=strategy,
                broker_path=broker_path,
                approve_execution=False,
                include_holdout=True,
            ),
            lambda trace: self.render_trace(trace, context),
        )

    def _summarize_step(self, step):
        s = step["summary"]
        action = step["action"]
        if action == "decompose_request":
            return f"拆解 {len(s.get('plan', []))} 个 Skill 任务"
        if action.startswith("screen("):
            syms = ",".join(s.get("selected_symbols", []))
            return f"评估 {s.get('inputs_evaluated', 0)} 份 → 命中 {len(s.get('selected_symbols', []))} 股 ({syms})"
        if action.startswith("analyze_portfolio"):
            return (
                f"策略={s.get('strategy')} · α={s.get('alpha_used')} · κ={s.get('condition_before')}→{s.get('condition_after')}"
                f" · KKT={s.get('kkt_complementarity_error'):.2e}"
            )
        if action.startswith("propose_rebalance"):
            return f"生成 {s.get('order_count', 0)} 笔调仓单（账户时钟 {s.get('account_clock')}）"
        if step["status"] == "executed":
            return f"已人工审批并原子成交 {s.get('fills_count', 0)} 笔"
        return "等待人工显式审批（未写入 paper.sqlite3）"

    def render_trace(self, trace, context=None):
        if context is not None and context != self.context():
            return
        self.trace = trace
        trace.save(self.workspace.settings.data_dir / "agent_runs")
        status_map = {
            "completed": "已完成",
            "awaiting_confirmation": "待确认",
            "blocked_pending_human_approval": "已拦截(待审批)",
            "executed": "已审批成交",
        }
        step_rows = [
            {
                "#": s["step"],
                "层级 · Skill": f"{s['layer'].split('/')[0]} · {s['skill'].replace('matrix-', '')}",
                "风险等级": s["risk_tier"],
                "状态": status_map.get(s["status"], s["status"]),
                "执行摘要与耗时": f"{self._summarize_step(s)} ({s['elapsed_seconds']:.2f}s)",
            }
            for s in trace.steps
        ]
        self.steps_table.replace(pd.DataFrame(step_rows))
        self.steps_table.resizeColumnsToContents()
        self.steps_table.horizontalHeader().setStretchLastSection(True)

        target_w = trace.diagnostics.get("target_weights", trace.diagnostics.get("weights", {}))
        if trace.fills:
            order_rows = [
                {
                    "代码": f["symbol"],
                    "方向": "买入" if f["side"] == "BUY" else "卖出",
                    "份额": f["quantity"],
                    "目标权重": target_w.get(f["symbol"]),
                    "状态/成交": f"已成交 @ {f['price']:.4f} (费 {f['fee']:.2f}, 日期 {f['fill_date']})",
                }
                for f in trace.fills
            ]
        else:
            order_rows = [
                {
                    "代码": o["symbol"],
                    "方向": "买入" if o["side"] == "BUY" else "卖出",
                    "份额": o["quantity"],
                    "目标权重": target_w.get(o["symbol"]),
                    "状态/成交": "待人工审批（按次日开盘价撮合）",
                }
                for o in trace.proposed_orders
            ]
        self.orders_table.replace(pd.DataFrame(order_rows, columns=["代码", "方向", "份额", "目标权重", "状态/成交"]))
        self.orders_table.resizeColumnsToContents()

        strat_name = "风险平价(ERC)" if trace.strategy == "erc" else "最小方差(QP)"
        status_zh = "已人工批准并写入 SQLite 账本" if trace.approved_execution else "预览完成（高风险写入已拦截，等待人工批准）"
        self.summary.setText(
            f"Trace {trace.trace_id[:8]} · {trace.asof} · 策略 {strat_name} · 选中 {len(trace.selected_symbols)} 股 "
            f"({', '.join(trace.selected_symbols)}) · α={trace.diagnostics['alpha_used']:.4f} · "
            f"KKT={trace.diagnostics['kkt_complementarity_error']:.2e} · {status_zh}"
        )
        self.export_btn.setEnabled(True)
        self.export_html_btn.setEnabled(True)
        has_future = bool((self.workspace.prices.date > pd.Timestamp(trace.asof)).any())
        self.approve_btn.setEnabled((not trace.approved_execution) and bool(trace.proposed_orders) and has_future)
        self.state_changed.emit()

    def approve_now(self, confirm=True):
        if self.trace is None or self.trace.approved_execution or not self.trace.proposed_orders:
            return
        if self.workspace.asof is None or str(self.workspace.asof.date()) != self.trace.asof:
            self.summary.setText("顶部研究日期已变更，请重新运行工作流预览后再审批。")
            self.approve_btn.setEnabled(False)
            return
        strat_name = "风险平价(ERC)" if self.trace.strategy == "erc" else "最小方差(QP)"
        if confirm:
            answer = QtWidgets.QMessageBox.question(
                self,
                "高风险操作人工审批确认（HIGH_EXPLICIT_APPROVAL）",
                f"确认按预览结果写入本地模拟交易账本（paper.sqlite3）？\n\n"
                f"研究日期：{self.trace.asof}\n"
                f"优化策略：{strat_name}\n"
                f"待执行订单：{len(self.trace.proposed_orders)} 笔（先卖后买、次日复权开盘价撮合、整批原子事务）\n"
                f"如尚未建户，将自动以 $100,000 在 {self.trace.asof} 初始化模拟账户。",
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        t0 = time.perf_counter()
        try:
            broker = self.workspace.broker
            if broker.exists():
                clock = broker.state()[0]["clock"]
                if clock != self.trace.asof:
                    raise TradingError(f"当前账户模拟日期为 {clock}，与预览日期 {self.trace.asof} 不一致。")
            else:
                broker.initialize(100000.0, self.trace.asof)
            ticket = [Order(o["symbol"], o["side"], int(o["quantity"])) for o in self.trace.proposed_orders]
            fills = broker.execute(ticket, self.trace.asof, self.workspace.prices, f"agent-{self.trace.trace_id}")
        except (TradingError, DataError) as exc:
            self.summary.setText(f"审批执行中止：{exc}")
            return

        self.trace.approved_execution = True
        self.trace.fills = fills
        self.trace.steps[-1] = {
            "step": 5,
            "layer": "Action/Execution",
            "skill": "matrix-paper-broker",
            "action": "execute_orders",
            "risk_tier": RISK_HIGH,
            "status": "executed",
            "elapsed_seconds": round(time.perf_counter() - t0, 4),
            "summary": {"fills_count": len(fills), "fills": fills},
        }
        self.render_trace(self.trace)
        if fills:
            self.executed.emit(fills[0]["fill_date"])

    def export_html(self, open_browser=True):
        if not self.trace:
            return None
        out_dir = self.workspace.settings.data_dir / "agent_reports" / self.trace.trace_id[:8]
        html_path = self.trace.export_html_report(out_dir)
        self.report_path = html_path
        self.summary.setText(f"离线可复查 HTML 报告已生成：{html_path}")
        if open_browser and QtWidgets.QApplication.platformName() != "offscreen":
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(html_path.resolve())))
        return html_path

    def export_trace(self):
        if not self.trace:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "导出 Agent 审计轨迹", f"agent-trace-{self.trace.trace_id[:8]}.json", "JSON (*.json)")
        if path:
            Path(path).write_text(json.dumps(asdict(self.trace), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
