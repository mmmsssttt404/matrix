"""Native workbench layout informed by vn.py's docked monitors and trading panel.

The widgets use the project's own research/analytics/ledger, not vn.py engines.
"""
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from ..acquire import fetch_dataset
from ..data import DataError, data_quality, validate_documents, validate_prices
from ..trading import Order, TradingError, rebalance_orders
from .charts import PriceChart
from .dialogs import AccountDialog, ConnectionDialog
from .pages import PortfolioPage, ResearchPage
from .theme import DOWN, UP
from .widgets import Table, Work, button, label, panel
from .workspace import COMPANIES, Workspace


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.workspace = Workspace(settings)
        self.setWindowTitle("Matrix Workbench · 股票研究与模拟交易")
        self.setWindowIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon))
        self.resize(1500, 960)
        self.setMinimumSize(1160, 760)
        self._jobs = {}
        self.child_windows = []
        self.period = 126
        self._request_id = str(uuid4())
        self.build_menu()
        self.build_ui()
        self.workspace.changed.connect(self.refresh)
        self.workspace.date_changed.connect(self.refresh)
        self.workspace.date_changed.connect(self.portfolio.invalidate)
        self.workspace.symbol_changed.connect(self.refresh_symbol)
        self.refresh()

    def build_menu(self):
        bar = self.menuBar()
        bar.setNativeMenuBar(False)
        files = bar.addMenu("文件")
        for caption, shortcut, callback in [("打开工作区…", "Ctrl+O", self.open_workspace),
                                             ("导入行情CSV…", "", lambda: self.import_csv("prices")),
                                             ("导入公司资料…", "", lambda: self.import_csv("documents")),
                                             ("下载公开历史数据", "", self.download),
                                             ("导出成交记录…", "Ctrl+E", self.export_orders),
                                             ("退出", "Ctrl+Q", self.close)]:
            action = files.addAction(caption)
            if shortcut:
                action.setShortcut(shortcut)
            action.triggered.connect(callback)
        view = bar.addMenu("查看")
        for index, caption in enumerate(["行情工作台", "公司研究", "矩阵组合"]):
            action = view.addAction(caption)
            action.setShortcut(f"Ctrl+{index+1}")
            action.triggered.connect(lambda checked=False, i=index: self.navigate(i))
        help_menu = bar.addMenu("帮助")
        help_menu.addAction("价格与模拟规则", self.show_rules)
        help_menu.addAction("开源参考", self.show_sources)
        help_menu.addAction("关于Qt", QtWidgets.QApplication.aboutQt)

    def build_ui(self):
        root = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        top = QtWidgets.QFrame()
        top.setObjectName("topbar")
        top_row = QtWidgets.QHBoxLayout(top)
        top_row.setContentsMargins(17, 0, 12, 0)
        top_row.setSpacing(6)
        top_row.addWidget(label("MATRIX", "brand"))
        top_row.addWidget(label("WORKBENCH", "muted"))
        top_row.addSpacing(20)
        self.nav = []
        self.nav_group = QtWidgets.QButtonGroup(self)
        for i, text in enumerate(["行情工作台", "公司研究", "矩阵组合"]):
            item = button(text, lambda checked=False, index=i: self.navigate(index), "nav")
            item.setCheckable(True)
            self.nav_group.addButton(item)
            self.nav.append(item)
            top_row.addWidget(item)
        self.nav[0].setChecked(True)
        top_row.addStretch()
        top_row.addWidget(label("研究日期", "muted"))
        self.date = QtWidgets.QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setFixedWidth(125)
        self.date.dateChanged.connect(self.change_date)
        top_row.addWidget(self.date)
        top_row.addWidget(button("最新", self.latest))
        top_row.addSpacing(9)
        top_row.addWidget(button("连接设置", self.connections))
        layout.addWidget(top)
        self.notice = label()
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet("background:#392633;color:#f6b1bc;padding:9px 17px;")
        self.notice.hide()
        layout.addWidget(self.notice)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        horizontal = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        horizontal.setChildrenCollapsible(False)
        self.watch_panel, watch = panel()
        self.watch_panel.setMinimumWidth(230)
        self.watch_panel.setMaximumWidth(330)
        heading = QtWidgets.QHBoxLayout()
        self.watch_title = label("自选股票", "section")
        heading.addWidget(self.watch_title)
        heading.addStretch()
        heading.addWidget(label("USD", "muted"))
        watch.addLayout(heading)
        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText("搜索代码或公司")
        self.filter.textChanged.connect(self.refresh_watch)
        watch.addWidget(self.filter)
        self.watch = Table(formats={"最新": lambda v: f"{v:,.2f}", "涨跌幅": lambda v: f"{v:+.2%}"}, color_column="涨跌幅")
        self.watch.clicked.connect(self.select_watch)
        self.watch.verticalHeader().setDefaultSectionSize(39)
        watch.addWidget(self.watch, 1)
        self.snapshot = label("本地历史数据 · 非实时行情", "muted")
        self.snapshot.setWordWrap(True)
        watch.addWidget(self.snapshot)
        watch.addWidget(button("打开工作区", self.open_workspace))
        horizontal.addWidget(self.watch_panel)
        center = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        center.setChildrenCollapsible(False)
        self.pages = QtWidgets.QStackedWidget()
        self.pages.setMinimumWidth(580)
        self.market = self.build_market()
        self.research = ResearchPage(self.workspace, self.run_job)
        self.research.apply_selection.connect(lambda: self.navigate(2))
        self.portfolio = PortfolioPage(self.workspace, self.run_job)
        self.portfolio.calculated.connect(self.refresh_account)
        for page in [self.market, self.research, self.portfolio]:
            self.pages.addWidget(page)
        center.addWidget(self.pages)
        self.bottom = QtWidgets.QTabWidget()
        self.bottom.setMinimumHeight(150)
        self.positions = Table(formats={"复权现价": lambda v: f"{v:.2f}", "市值USD": lambda v: f"{v:,.2f}"})
        self.orders = Table(formats={"成交价": lambda v: f"{v:.4f}", "手续费": lambda v: f"{v:.2f}"})
        self.equity = Table(formats={"现金USD": lambda v: f"{v:,.2f}", "权益USD": lambda v: f"{v:,.2f}"})
        self.sources = Table()
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        for title, widget in [("持仓", self.positions), ("成交记录", self.orders), ("账户权益", self.equity), ("数据来源", self.sources), ("活动日志", self.log)]:
            self.bottom.addTab(widget, title)
        center.addWidget(self.bottom)
        center.setSizes([620, 200])
        horizontal.addWidget(center)
        self.trade_panel = self.build_trading()
        self.trade_panel.setMinimumWidth(260)
        self.trade_panel.setMaximumWidth(340)
        horizontal.addWidget(self.trade_panel)
        horizontal.setSizes([250, 925, 285])
        horizontal.setStretchFactor(1, 1)
        layout.addWidget(horizontal, 1)
        self.setCentralWidget(root)
        self.status = label("本地数据模式", "muted")
        self.statusBar().addWidget(self.status, 1)
        self.statusBar().addPermanentWidget(label("复权价格 / 模拟份额    ·    JEVDB Research", "muted"))

    def build_market(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 4)
        layout.setSpacing(6)
        head = QtWidgets.QHBoxLayout()
        self.symbol_title = label("—", "symbol")
        head.addWidget(self.symbol_title)
        self.company = label("", "muted")
        head.addWidget(self.company)
        head.addStretch()
        head.addWidget(label("美股 / 日线 / USD", "muted"))
        layout.addLayout(head)
        price = QtWidgets.QHBoxLayout()
        self.last = label("—", "price")
        self.change = label()
        price.addWidget(self.last)
        price.addWidget(self.change)
        price.addStretch()
        self.range_label = label("", "muted")
        price.addWidget(self.range_label)
        layout.addLayout(price)
        toolbar = QtWidgets.QHBoxLayout()
        group = QtWidgets.QButtonGroup(page)
        for text, count in [("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 252), ("全部", 10000)]:
            item = button(text, lambda checked=False, n=count: self.set_period(n), "range")
            item.setCheckable(True)
            item.setChecked(count == 126)
            group.addButton(item)
            toolbar.addWidget(item)
        toolbar.addStretch()
        toolbar.addWidget(label("MA20", "muted"))
        self.chart_type = QtWidgets.QComboBox()
        self.chart_type.addItems(["K线", "折线"])
        self.chart_type.currentIndexChanged.connect(self.refresh_symbol)
        toolbar.addWidget(self.chart_type)
        layout.addLayout(toolbar)
        self.ohlc = label("滚轮缩放 · 拖动平移 · 十字光标查看日线", "muted")
        self.ohlc.setMinimumHeight(23)
        layout.addWidget(self.ohlc)
        self.chart = PriceChart()
        self.chart.hover_text.connect(self.ohlc.setText)
        layout.addWidget(self.chart, 1)
        self.empty = QtWidgets.QWidget()
        empty = QtWidgets.QVBoxLayout(self.empty)
        empty.addStretch()
        empty.addWidget(label("建立你的股票研究工作区", "symbol"))
        empty.addWidget(label("下载真实历史数据，或导入已有CSV，开始研究与模拟交易。", "muted"))
        empty.addWidget(button("下载课程研究数据", self.download, "primary"))
        empty.addWidget(button("打开已有工作区", self.open_workspace))
        empty.addStretch()
        layout.addWidget(self.empty, 1)
        return page

    def build_trading(self):
        frame, layout = panel()
        heading = QtWidgets.QHBoxLayout()
        heading.addWidget(label("模拟账户", "section"))
        heading.addStretch()
        heading.addWidget(label("PAPER", "eyebrow"))
        layout.addLayout(heading)
        layout.addWidget(label("账户权益 · USD", "muted"))
        self.account_equity = label("—", "symbol")
        layout.addWidget(self.account_equity)
        self.account_cash = label("尚未创建模拟账户", "muted")
        self.account_cash.setWordWrap(True)
        layout.addWidget(self.account_cash)
        self.account_pnl = label("", "muted")
        layout.addWidget(self.account_pnl)
        self.create_account_button = button("创建模拟账户", self.create_account, "primary")
        layout.addWidget(self.create_account_button)
        self.clock = label("", "muted")
        layout.addWidget(self.clock)
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setStyleSheet("color:#30394c;")
        layout.addWidget(line)
        layout.addWidget(label("订单面板", "section"))
        self.order_symbol = label("—", "symbol")
        layout.addWidget(self.order_symbol)
        sides = QtWidgets.QHBoxLayout()
        self.side_group = QtWidgets.QButtonGroup(frame)
        self.buy_side = button("买入", lambda: self.set_side("BUY"))
        self.sell_side = button("卖出", lambda: self.set_side("SELL"))
        for item in [self.buy_side, self.sell_side]:
            item.setCheckable(True)
            self.side_group.addButton(item)
            sides.addWidget(item)
        self.buy_side.setChecked(True)
        self.side = "BUY"
        layout.addLayout(sides)
        form = QtWidgets.QFormLayout()
        self.quantity = QtWidgets.QSpinBox()
        self.quantity.setRange(1, 1000000000)
        self.quantity.setValue(10)
        self.quantity.valueChanged.connect(self.refresh_estimate)
        self.order_type = label("下一交易日开盘")
        form.addRow("撮合方式", self.order_type)
        form.addRow("模拟份额", self.quantity)
        layout.addLayout(form)
        self.estimate = label("参考金额 —", "muted")
        self.estimate.setWordWrap(True)
        layout.addWidget(self.estimate)
        self.costs = label("手续费与滑点在开户时设置", "muted")
        self.costs.setWordWrap(True)
        layout.addWidget(self.costs)
        self.submit = button("模拟买入", self.submit_order, "buy")
        layout.addWidget(self.submit)
        self.rebalance = button("按组合目标调仓…", self.preview_rebalance)
        layout.addWidget(self.rebalance)
        layout.addSpacing(8)
        self.advance = button("推进一个交易日", self.advance_day)
        layout.addWidget(self.advance)
        layout.addStretch()
        info = label("本地模拟 · 无杠杆 · 只做多\n使用复权份额，不连接真实券商。", "muted")
        info.setWordWrap(True)
        layout.addWidget(info)
        return frame

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        self.nav[index].setChecked(True)

    def refresh(self):
        ws = self.workspace
        ready = not ws.prices.empty
        self.chart.setVisible(ready)
        self.empty.setVisible(not ready)
        self.date.blockSignals(True)
        if ready:
            self.date.setMinimumDate(QtCore.QDate(ws.days[0].year, ws.days[0].month, ws.days[0].day))
            self.date.setDate(QtCore.QDate(ws.asof.year, ws.asof.month, ws.asof.day))
            self.snapshot.setText(f"数据截至 {ws.prices.date.max():%Y-%m-%d}\n历史快照 · 非实时行情")
            self.watch_title.setText(f"自选股票  /  {len(ws.symbols)}")
            quality = data_quality(ws.prices).rename(columns={"symbol": "代码", "rows": "日线条数", "first": "起始日期", "last": "截止日期", "missing_sessions": "缺失交易日"})
            for col in ["起始日期", "截止日期"]:
                quality[col] = quality[col].dt.strftime("%Y-%m-%d")
            self.sources.replace(quality)
            self.status.setText(f"研究日期 {ws.asof:%Y-%m-%d}    |    {len(ws.prices):,}条真实日线    |    {'语义服务地址已配置' if ws.settings.service_url else '本地数据模式'}")
        self.date.blockSignals(False)
        self.date.setEnabled(ready)
        self.create_account_button.setEnabled(ready)
        self.refresh_watch()
        self.refresh_symbol()
        self.refresh_account()

    def refresh_watch(self):
        frame = self.workspace.quotes()
        query = self.filter.text().strip().casefold()
        if query and not frame.empty:
            frame = frame.loc[frame["代码"].map(lambda s: query in s.casefold() or query in COMPANIES.get(s, "").casefold())]
        self.watch.replace(frame.reset_index(drop=True))
        self.watch.setColumnWidth(0, 65)
        self.watch.setColumnWidth(1, 77)
        header = self.watch.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for i, row in self.watch.frame_model.frame.iterrows():
            if row["代码"] == self.workspace.symbol:
                self.watch.selectRow(i)

    def select_watch(self, index):
        self.workspace.select(self.watch.frame_model.frame.iloc[index.row()]["代码"])

    def refresh_symbol(self, *args):
        ws = self.workspace
        frame = ws.series()
        if frame.empty:
            return
        last = frame.iloc[-1]
        previous = frame.iloc[-2].close if len(frame) > 1 else last.close
        difference, percent = last.close - previous, last.close / previous - 1
        self.symbol_title.setText(ws.symbol)
        self.company.setText(COMPANIES.get(ws.symbol, "") + "    /    复权价格")
        self.last.setText(f"{last.close:,.2f}")
        self.change.setText(f"{difference:+.2f}  ({percent:+.2%})")
        self.change.setStyleSheet(f"color:{UP if difference >= 0 else DOWN};font-size:14px;")
        self.range_label.setText(f"最高 {last.high:.2f}    最低 {last.low:.2f}")
        self.chart.set_frame(frame, self.period, "candles" if self.chart_type.currentIndex() == 0 else "line")
        self.order_symbol.setText(ws.symbol)
        self.refresh_estimate()

    def refresh_estimate(self, *args):
        frame = self.workspace.series()
        if not frame.empty:
            self.estimate.setText(f"收盘参考 ${frame.iloc[-1].close * self.quantity.value():,.2f}\n实际金额按下一日开盘与费用计算。")

    def refresh_account(self):
        ws = self.workspace
        exists = ws.broker.exists()
        self.create_account_button.setVisible(not exists)
        self.submit.setEnabled(exists)
        self.advance.setEnabled(exists)
        self.rebalance.setEnabled(False)
        if not exists:
            self.positions.replace(pd.DataFrame(columns=["代码", "持有份额", "复权现价", "市值USD"]))
            self.orders.replace(pd.DataFrame(columns=["成交日期", "代码", "方向", "份额", "成交价", "手续费"]))
            return
        account, positions, snapshots, orders = ws.broker.state()
        equity = float(snapshots.iloc[-1].equity)
        self.account_equity.setText(f"{equity:,.2f}")
        self.account_cash.setText(f"可用现金  ${account['cash']:,.2f}")
        pnl = equity - account["initial_cash"]
        self.account_pnl.setText(f"累计盈亏  {pnl:+,.2f}  ({pnl / account['initial_cash']:+.2%})")
        self.account_pnl.setStyleSheet(f"color:{UP if pnl >= 0 else DOWN};")
        self.clock.setText("模拟日期  " + account["clock"])
        self.costs.setText(f"手续费 {account['commission_bps']:g}bp · 滑点 {account['slippage_bps']:g}bp")
        aligned = ws.asof is not None and str(ws.asof.date()) == account["clock"]
        future = bool(not ws.prices.empty and (ws.prices.date > pd.Timestamp(account["clock"])).any())
        self.submit.setEnabled(aligned and future)
        self.advance.setEnabled(future)
        self.rebalance.setEnabled(aligned and future and ws.risk is not None)
        if not aligned:
            self.estimate.setText("研究日期与账户模拟日期不同。\n点击“推进”或切换研究日期后下单。")
        marks = ws.prices.loc[ws.prices.date.eq(pd.Timestamp(account["clock"]))].set_index("symbol").close
        displayed = positions.rename(columns={"symbol": "代码", "quantity": "持有份额"})
        displayed["复权现价"] = displayed["代码"].map(marks)
        displayed["市值USD"] = displayed["复权现价"] * displayed["持有份额"]
        self.positions.replace(displayed)
        columns = {"fill_date": "成交日期", "symbol": "代码", "side": "方向", "quantity": "份额", "price": "成交价", "fee": "手续费"}
        self.orders.replace(orders[list(columns)].rename(columns=columns).replace({"方向": {"BUY": "买入", "SELL": "卖出"}}))
        history = snapshots[["date", "cash", "equity"]].rename(columns={"date": "日期", "cash": "现金USD", "equity": "权益USD"})
        history["日期"] = history["日期"].dt.strftime("%Y-%m-%d")
        self.equity.replace(history)

    def change_date(self, date):
        if not self.workspace.prices.empty:
            self.workspace.set_date(date.toPython())

    def latest(self):
        if not self.workspace.prices.empty:
            self.workspace.set_date(self.workspace.prices.date.max())

    def set_period(self, count):
        self.period = count
        self.refresh_symbol()

    def set_side(self, side):
        self.side = side
        self.submit.setText("模拟买入" if side == "BUY" else "模拟卖出")
        self.submit.setObjectName("buy" if side == "BUY" else "sell")
        self.submit.style().unpolish(self.submit)
        self.submit.style().polish(self.submit)

    def create_account(self):
        if self.workspace.prices.empty:
            return
        if AccountDialog(self.workspace, self).exec():
            self.refresh_account()
            self.message("模拟账户已创建，开始日期已切换到历史回放起点。")

    def submit_order(self):
        try:
            fills = self.workspace.broker.execute([Order(self.workspace.symbol, self.side, self.quantity.value())], self.workspace.asof,
                                                   self.workspace.prices, self._request_id)
            self._request_id = str(uuid4())
            self.workspace.set_date(fills[0]["fill_date"])
            self.bottom.setCurrentIndex(1)
            self.message(f"{fills[0]['symbol']}已模拟成交：{fills[0]['quantity']}份，成交价{fills[0]['price']:.4f}。")
        except TradingError as exc:
            self.show_error(str(exc))

    def preview_rebalance(self):
        ws = self.workspace
        if ws.risk is None:
            return
        try:
            _, positions, snapshots, _ = ws.broker.state()
            ticket = rebalance_orders(ws.prices, ws.risk.weights, ws.asof, float(snapshots.iloc[-1].equity), positions)
            if not ticket:
                self.message("当前份额已接近目标配置，无需调仓。")
                return
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle("组合调仓预览")
            dialog.resize(520, 380)
            layout = QtWidgets.QVBoxLayout(dialog)
            layout.addWidget(label("按研究日收盘估算份额，预留5%现金；实际按次日开盘成交。", "muted"))
            table = Table(pd.DataFrame([asdict(o) for o in ticket]).rename(columns={"symbol": "代码", "side": "方向", "quantity": "份额"}))
            layout.addWidget(table)
            layout.addWidget(button("提交整批模拟订单", dialog.accept, "primary"))
            if dialog.exec():
                fills = ws.broker.execute(ticket, ws.asof, ws.prices, self._request_id)
                self._request_id = str(uuid4())
                ws.set_date(fills[0]["fill_date"])
                self.bottom.setCurrentIndex(1)
                self.message(f"整批调仓完成：{len(fills)}笔成交。")
        except TradingError as exc:
            self.show_error(str(exc))

    def advance_day(self):
        ws = self.workspace
        if not ws.broker.exists():
            return
        clock = pd.Timestamp(ws.broker.state()[0]["clock"])
        future = ws.prices.loc[ws.prices.date > clock, "date"]
        if not future.empty:
            try:
                ws.broker.advance(ws.prices, future.min())
                ws.set_date(future.min())
            except TradingError as exc:
                self.show_error(str(exc))

    def connections(self):
        ConnectionDialog(self.workspace, self).exec()
        self.refresh()

    def run_job(self, function, callback):
        if self._jobs:
            self.message("上一项任务正在执行。")
            return
        self.notice.hide()
        self.progress.show()
        self.pages.setEnabled(False)
        self.watch_panel.setEnabled(False)
        self.trade_panel.setEnabled(False)
        self.date.setEnabled(False)
        work = Work(function)
        identifier = str(uuid4())
        self._jobs[identifier] = work
        work.signals.result.connect(callback, QtCore.Qt.ConnectionType.QueuedConnection)
        work.signals.error.connect(self.show_error, QtCore.Qt.ConnectionType.QueuedConnection)
        work.signals.finished.connect(lambda: self.finish_job(identifier), QtCore.Qt.ConnectionType.QueuedConnection)
        QtCore.QThreadPool.globalInstance().start(work)

    def finish_job(self, identifier):
        self._jobs.pop(identifier, None)
        self.progress.hide()
        self.pages.setEnabled(True)
        self.watch_panel.setEnabled(True)
        self.trade_panel.setEnabled(True)
        self.date.setEnabled(not self.workspace.prices.empty)

    def message(self, text):
        self.log.appendPlainText(datetime.now().strftime("%H:%M:%S") + "  " + text)
        self.statusBar().showMessage(text, 12000)

    @QtCore.Slot(str)
    def show_error(self, text):
        self.notice.setText(text)
        self.notice.show()
        self.message(text)

    def download(self):
        self.run_job(lambda: fetch_dataset(self.workspace.settings.data_dir), self.downloaded)

    def downloaded(self, result):
        self.workspace.reload()
        self.message(f"已下载{result['rows']:,}条真实日线，{result['documents_downloaded']}份公司简介。")

    def open_workspace(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "打开工作区（含prices.csv）", str(self.workspace.settings.data_dir))
        if directory:
            try:
                window = MainWindow(type(self.workspace.settings)(Path(directory), self.workspace.settings.backend, self.workspace.settings.endpoint, self.workspace.settings.model,
                                                                  self.workspace.settings.service_url, self.workspace.settings.service_token))
                self.child_windows.append(window)
                window.show()
            except (OSError, ValueError) as exc:
                self.show_error(str(exc))

    def import_csv(self, kind):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "导入CSV", "", "CSV (*.csv)")
        if not path:
            return
        try:
            if kind == "prices" and self.workspace.broker.exists():
                raise DataError("已有模拟账户，请打开新工作区再导入另一份行情。")
            frame = validate_prices(pd.read_csv(path)) if kind == "prices" else validate_documents(pd.read_csv(path))
            target = self.workspace.settings.data_dir / (kind + ".csv")
            if kind == "documents" and not self.workspace.documents.empty:
                frame = validate_documents(pd.concat([self.workspace.documents, frame], ignore_index=True).drop_duplicates("doc_id"))
            temporary = target.with_suffix(".csv.part")
            frame.to_csv(temporary, index=False)
            temporary.replace(target)
            self.workspace.reload()
            self.message(f"已校验并导入{len(frame)}行数据。")
        except (OSError, ValueError) as exc:
            self.show_error(str(exc))

    def export_orders(self):
        if not self.workspace.broker.exists():
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "导出成交记录", "orders.csv", "CSV (*.csv)")
        if path:
            self.workspace.broker.state()[3].to_csv(path, index=False)

    def show_rules(self):
        QtWidgets.QMessageBox.information(self, "价格与模拟规则", "行情为总回报复权价格，持仓为整数模拟份额，不重复发放股息或调整拆股。\n\n信号日之后的首个交易日开盘撮合；买卖方向计入滑点，手续费单列。账户时钟只能前进，任何无效订单整批回滚。")

    def show_sources(self):
        QtWidgets.QMessageBox.information(self, "开源参考", "窗口排布与监视器联动参考vnpy/vnpy（MIT）。\nK线QPicture缓存绘制改写自pyqtgraph/pyqtgraph（MIT）。\n\n详细来源、改写范围和许可见仓库的docs/desktop-design.md与THIRD_PARTY_NOTICES.md。")
