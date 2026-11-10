"""Qt charts. Candle QPicture caching is adapted from pyqtgraph's MIT example.

Source: pyqtgraph/examples/customGraphicsItem.py. See THIRD_PARTY_NOTICES.md.
"""
import numpy as np
import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from .theme import BACKGROUND, BLUE, DOWN, MUTED, UP

pg.setConfigOptions(antialias=True, background=BACKGROUND, foreground=MUTED)


class SessionAxis(pg.AxisItem):
    def __init__(self, dates=None, **kwargs):
        super().__init__(**kwargs)
        self.dates = list(dates) if dates is not None else []
        self.setStyle(tickFont=QtGui.QFont("Arial", 9), autoExpandTextSpace=True)

    def tickStrings(self, values, scale, spacing):
        return [pd.Timestamp(self.dates[int(round(v))]).strftime("%y/%m/%d") if 0 <= int(round(v)) < len(self.dates) else "" for v in values]


class Candles(pg.GraphicsObject):
    def __init__(self, frame):
        super().__init__()
        self.picture = QtGui.QPicture()
        painter = QtGui.QPainter(self.picture)
        for i, row in enumerate(frame.itertuples()):
            color = UP if row.close >= row.open else DOWN
            painter.setPen(pg.mkPen(color, width=1))
            painter.setBrush(pg.mkBrush(color))
            painter.drawLine(QtCore.QPointF(i, row.low), QtCore.QPointF(i, row.high))
            body = max(abs(row.close - row.open), row.close * 0.0002)
            painter.drawRect(QtCore.QRectF(i - .32, min(row.open, row.close), .64, body))
        painter.end()

    def paint(self, painter, *args):
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QtCore.QRectF(self.picture.boundingRect())


class VolumeAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [f"{v / 1e6:g}M" if abs(v) >= 1e6 else f"{v / 1e3:g}K" if abs(v) >= 1e3 else f"{v:g}" for v in values]


class PriceChart(QtWidgets.QWidget):
    hover_text = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.axis = SessionAxis(orientation="bottom")
        self.volume_axis = SessionAxis(orientation="bottom")
        self.price = pg.PlotWidget(axisItems={"bottom": self.axis})
        self.volume = pg.PlotWidget(axisItems={"bottom": self.volume_axis, "left": VolumeAxis(orientation="left")})
        self.volume.setFixedHeight(108)
        for plot in [self.price, self.volume]:
            plot.showGrid(x=True, y=True, alpha=.13)
            plot.hideButtons()
            plot.setMenuEnabled(False)
            plot.getAxis("left").setWidth(60)
            plot.getAxis("left").setPen(pg.mkPen("#343c4f"))
            plot.getAxis("bottom").setPen(pg.mkPen("#343c4f"))
            plot.setMouseEnabled(x=True, y=False)
        self.price.getAxis("bottom").setStyle(showValues=False)
        self.volume.setXLink(self.price)
        self.volume.setLabel("left", "成交量")
        layout.addWidget(self.price, 1)
        layout.addWidget(self.volume)
        self.frame = pd.DataFrame()
        self.proxy = pg.SignalProxy(self.price.scene().sigMouseMoved, rateLimit=30, slot=self._hover)

    def set_frame(self, frame, count=126, style="candles"):
        self.frame = frame.reset_index(drop=True)
        self.axis.dates = self.frame.date.tolist()
        self.volume_axis.dates = self.frame.date.tolist()
        self.price.clear()
        self.volume.clear()
        if self.frame.empty:
            return
        x = np.arange(len(self.frame))
        if style == "candles":
            self.price.addItem(Candles(self.frame))
        else:
            self.price.plot(x, self.frame.close.to_numpy(), pen=pg.mkPen(BLUE, width=1.7))
        colors = [pg.mkBrush(UP if c >= o else DOWN) for o, c in zip(self.frame.open, self.frame.close)]
        self.volume.addItem(pg.BarGraphItem(x=x, height=self.frame.volume.to_numpy(), width=.65, brushes=colors, pen=None))
        ma = self.frame.close.rolling(20).mean()
        self.price.plot(x, ma.to_numpy(), pen=pg.mkPen("#dfb56e", width=1.1), connect="finite")
        self.vertical = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#778498", style=QtCore.Qt.PenStyle.DashLine))
        self.horizontal = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#778498", style=QtCore.Qt.PenStyle.DashLine))
        self.price.addItem(self.vertical, ignoreBounds=True)
        self.price.addItem(self.horizontal, ignoreBounds=True)
        self.price.addItem(pg.InfiniteLine(pos=float(self.frame.iloc[-1].close), angle=0, pen=pg.mkPen(UP, style=QtCore.Qt.PenStyle.DotLine)))
        start = max(0, len(self.frame) - count)
        visible = self.frame.iloc[start:]
        self.price.setXRange(start - 1, len(self.frame) + 2, padding=0)
        low, high = visible.low.min(), visible.high.max()
        self.price.setYRange(low, high, padding=.12)
        self.volume.setYRange(0, max(1, visible.volume.max()), padding=.05)
        self.price.setLimits(xMin=-1, xMax=len(self.frame) + 3)
        self.hover_text.emit(self._description(len(self.frame) - 1))

    def _description(self, i):
        row = self.frame.iloc[i]
        return f"{row.date:%Y-%m-%d}    开 {row.open:.2f}    高 {row.high:.2f}    低 {row.low:.2f}    收 {row.close:.2f}    成交量 {row.volume / 1e6:.2f}M"

    def _hover(self, args):
        if self.frame.empty:
            return
        point = args[0]
        if self.price.sceneBoundingRect().contains(point):
            value = self.price.plotItem.vb.mapSceneToView(point)
            i = min(max(int(round(value.x())), 0), len(self.frame) - 1)
            self.vertical.setPos(i)
            self.horizontal.setPos(value.y())
            self.hover_text.emit(self._description(i))


class EquityChart(pg.PlotWidget):
    def __init__(self, parent=None):
        self.axis = SessionAxis(orientation="bottom")
        super().__init__(parent, axisItems={"bottom": self.axis})
        self.showGrid(x=True, y=True, alpha=.12)
        self.setMenuEnabled(False)
        self.hideButtons()

    def set_frame(self, curve):
        self.clear()
        if curve.empty:
            return
        self.axis.dates = curve.index.tolist()
        self.addLegend(offset=(12, 10))
        for i, column in enumerate(curve):
            self.plot(np.arange(len(curve)), curve[column].to_numpy(), name=str(column), pen=pg.mkPen([BLUE, "#d8b874", UP][i % 3], width=1.7))
        self.enableAutoRange()
