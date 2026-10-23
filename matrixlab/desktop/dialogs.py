import os
import sys

from dotenv import set_key
import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from ..config import Settings
from ..trading import TradingError
from .widgets import button, label


class AccountDialog(QtWidgets.QDialog):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.setWindowTitle("创建模拟账户")
        self.setMinimumWidth(430)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(label("设置资金与历史回放起点", "section"))
        form = QtWidgets.QFormLayout()
        self.cash = QtWidgets.QDoubleSpinBox()
        self.cash.setRange(100, 1e9)
        self.cash.setDecimals(2)
        self.cash.setValue(100000)
        self.cash.setSuffix(" USD")
        default = pd.Timestamp(workspace.days[int(len(workspace.days) * .7)])
        if workspace.risk_asof is not None:
            default = workspace.risk_asof
        self.start = QtWidgets.QDateEdit(QtCore.QDate(default.year, default.month, default.day))
        self.start.setCalendarPopup(True)
        self.start.setDisplayFormat("yyyy-MM-dd")
        self.fee = QtWidgets.QDoubleSpinBox()
        self.slip = QtWidgets.QDoubleSpinBox()
        for widget, value in [(self.fee, 10), (self.slip, 5)]:
            widget.setRange(0, 1000)
            widget.setValue(value)
            widget.setSuffix(" bp")
        for caption, widget in [("初始资金", self.cash), ("起始交易日", self.start), ("手续费", self.fee), ("滑点", self.slip)]:
            form.addRow(caption, widget)
        layout.addLayout(form)
        hint = label("整数模拟份额 · 统一复权价格 · 下一交易日开盘撮合", "muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.error = label()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        layout.addWidget(button("创建账户", self.create, "primary"))

    def create(self):
        day = pd.Timestamp(self.start.date().toPython())
        if day not in self.workspace.days:
            self.error.setText("请选择有行情的交易日。")
            return
        try:
            self.workspace.broker.initialize(self.cash.value(), day, self.fee.value(), self.slip.value())
            self.workspace.set_date(day)
            self.accept()
        except TradingError as exc:
            self.error.setText(str(exc))


class ConnectionDialog(QtWidgets.QDialog):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.setWindowTitle("语义服务连接")
        self.setMinimumWidth(500)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(label("JEVDB语义查询", "section"))
        hint = label("Windows端连接Linux上的JEVDB服务。行情、关键词研究和模拟交易可以在本机离线使用。", "muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QtWidgets.QFormLayout()
        self.url = QtWidgets.QLineEdit(workspace.settings.service_url)
        self.url.setPlaceholderText("https://你的语义服务地址")
        self.token = QtWidgets.QLineEdit(workspace.settings.service_token)
        self.token.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        form.addRow("服务地址", self.url)
        form.addRow("访问令牌", self.token)
        layout.addLayout(form)
        self.local = {}
        if sys.platform.startswith("linux"):
            group = QtWidgets.QGroupBox("本机Linux模型配置（可选）")
            local = QtWidgets.QFormLayout(group)
            for key, title, value in [("JEV_API_KEY", "Jev API密钥", os.getenv("JEV_API_KEY", "")),
                                      ("MATRIX_API_ENDPOINT", "兼容接口地址", workspace.settings.endpoint),
                                      ("MATRIX_API_MODEL", "兼容模型名称", workspace.settings.model),
                                      ("OPENAI_API_KEY", "兼容接口密钥", os.getenv("OPENAI_API_KEY", ""))]:
                edit = QtWidgets.QLineEdit(value)
                if "KEY" in key:
                    edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
                local.addRow(title, edit)
                self.local[key] = edit
            self.backend = QtWidgets.QComboBox()
            self.backend.addItems(["jev", "llm"])
            self.backend.setCurrentText(workspace.settings.backend)
            local.addRow("本机后端", self.backend)
            layout.addWidget(group)
        layout.addWidget(label("凭证仅保存在当前工作区的本地配置文件。", "muted"))
        layout.addWidget(button("保存连接设置", self.save, "primary"))

    def save(self):
        values = {"MATRIX_JEVDB_SERVICE_URL": self.url.text().strip(), "MATRIX_JEVDB_SERVICE_TOKEN": self.token.text().strip()}
        values.update({k: v.text().strip() for k, v in self.local.items()})
        if self.local:
            values["MATRIX_BACKEND"] = self.backend.currentText()
        path = self.workspace.settings.data_dir / ".desktop.env"
        for key, value in values.items():
            set_key(path, key, value)
            os.environ[key] = value
        loaded = Settings.load()
        self.workspace.settings = Settings(self.workspace.settings.data_dir, loaded.backend, loaded.endpoint, loaded.model, loaded.service_url, loaded.service_token)
        self.accept()


class StockDialog(QtWidgets.QDialog):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.setWindowTitle("组合股票池")
        self.resize(330, 440)
        layout = QtWidgets.QVBoxLayout(self)
        self.list = QtWidgets.QListWidget()
        for symbol in workspace.symbols:
            item = QtWidgets.QListWidgetItem(symbol)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Checked if symbol in workspace.selected_symbols else QtCore.Qt.CheckState.Unchecked)
            self.list.addItem(item)
        layout.addWidget(self.list)
        self.message = label("至少选择两只股票。", "muted")
        layout.addWidget(self.message)
        layout.addWidget(button("应用股票池", self.apply, "primary"))
        self.selected = []

    def apply(self):
        self.selected = [self.list.item(i).text() for i in range(self.list.count()) if self.list.item(i).checkState() == QtCore.Qt.CheckState.Checked]
        if len(self.selected) >= 2:
            self.accept()


class SourceDialog(QtWidgets.QDialog):
    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.setWindowTitle("研究依据 · " + record["symbol"])
        self.resize(740, 550)
        layout = QtWidgets.QVBoxLayout(self)
        title = label(record["title"], "section")
        title.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(label("资料可用时间：" + str(record["available_at"]), "muted"))
        text = QtWidgets.QTextBrowser()
        text.setPlainText(record["text"])
        layout.addWidget(text)
        layout.addWidget(button("在浏览器打开原始来源", lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl(record["source_url"]))))
