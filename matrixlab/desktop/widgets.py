from collections.abc import Callable

import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from .theme import DOWN, TEXT, UP


def label(text="", role=None):
    widget = QtWidgets.QLabel(text)
    if role:
        widget.setObjectName(role)
    return widget


def button(text, callback=None, role=None):
    widget = QtWidgets.QPushButton(text)
    if role:
        widget.setObjectName(role)
    if callback:
        widget.clicked.connect(callback)
    return widget


def panel():
    frame = QtWidgets.QFrame()
    frame.setObjectName("panel")
    layout = QtWidgets.QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(9)
    return frame, layout


class FrameModel(QtCore.QAbstractTableModel):
    """A compact read-only Qt model with numeric sort and complete-value tooltips."""
    def __init__(self, frame=None, formats=None, color_column=None, parent=None):
        super().__init__(parent)
        self.frame = frame if frame is not None else pd.DataFrame()
        self.formats = formats or {}
        self.color_column = color_column

    def replace(self, frame):
        self.beginResetModel()
        self.frame = frame.copy()
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.frame)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.frame.columns)

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role == QtCore.Qt.ItemDataRole.DisplayRole and orientation == QtCore.Qt.Orientation.Horizontal:
            return str(self.frame.columns[section])
        return None

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        value = self.frame.iat[index.row(), index.column()]
        column = self.frame.columns[index.column()]
        if role in (QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.ToolTipRole):
            if pd.isna(value):
                return "—"
            if column in self.formats:
                return self.formats[column](value)
            return str(value)
        if role == QtCore.Qt.ItemDataRole.TextAlignmentRole:
            return int(QtCore.Qt.AlignmentFlag.AlignVCenter | (QtCore.Qt.AlignmentFlag.AlignLeft if index.column() == 0 else QtCore.Qt.AlignmentFlag.AlignRight))
        if role == QtCore.Qt.ItemDataRole.ForegroundRole and column == self.color_column:
            return QtGui.QColor(UP if float(value) >= 0 else DOWN)
        return None

    def sort(self, column, order=QtCore.Qt.SortOrder.AscendingOrder):
        if not len(self.frame):
            return
        self.layoutAboutToBeChanged.emit()
        self.frame = self.frame.sort_values(self.frame.columns[column], ascending=order == QtCore.Qt.SortOrder.AscendingOrder, kind="stable").reset_index(drop=True)
        self.layoutChanged.emit()


class Table(QtWidgets.QTableView):
    def __init__(self, frame=None, formats=None, color_column=None, parent=None):
        super().__init__(parent)
        self.frame_model = FrameModel(frame, formats, color_column, self)
        self.setModel(self.frame_model)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(34)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setMinimumSectionSize(65)
        self.setWordWrap(False)
        self.placeholder = QtWidgets.QLabel("暂无记录", self.viewport())
        self.placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet("color:#6e7c96;background:transparent;")
        self.placeholder.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.placeholder.setVisible(self.frame_model.frame.empty)

    def replace(self, frame):
        self.frame_model.replace(frame)
        self.resizeColumnsToContents()
        self.placeholder.setVisible(frame.empty)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "placeholder"):
            self.placeholder.setGeometry(self.viewport().rect())


class WorkSignals(QtCore.QObject):
    result = QtCore.Signal(object)
    error = QtCore.Signal(str)
    finished = QtCore.Signal()


class Work(QtCore.QRunnable):
    def __init__(self, function: Callable):
        super().__init__()
        self.function = function
        self.signals = WorkSignals()

    def run(self):
        try:
            self.signals.result.emit(self.function())
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()
