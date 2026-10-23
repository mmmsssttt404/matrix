# Third-party references and notices

The native desktop layout was informed by vn.py's main window, monitor tables and selection-to-order workflow. Its engine code is not embedded. The candlestick QPicture drawing in `matrixlab/desktop/charts.py` is adapted from pyqtgraph's custom graphics item example, with per-candle colors, safe body widths, session axes, volume linkage and a crosshair added.

- vn.py: https://github.com/vnpy/vnpy/blob/master/vnpy/trader/ui/mainwindow.py
- vn.py monitors: https://github.com/vnpy/vnpy/blob/master/vnpy/trader/ui/widget.py
- pyqtgraph candle example: https://github.com/pyqtgraph/pyqtgraph/blob/master/pyqtgraph/examples/customGraphicsItem.py

## vn.py — MIT

Copyright (c) 2015-present, Xiaoyou Chen

## pyqtgraph — MIT

Copyright (c) 2012 University of North Carolina at Chapel Hill
Luke Campagnola

The following MIT terms apply to the referenced MIT works and adapted pyqtgraph example:

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Qt for Python / PySide6

Qt for Python is dynamically linked. This application uses Qt Widgets from PySide6 Essentials, under the applicable LGPL terms, not proprietary Qt modules. Keep the accompanying Qt libraries replaceable and retain the license texts under `packaging/licenses/` and the bundled license directory. Qt and PySide source code and notices are available at https://code.qt.io/cgit/pyside/pyside-setup.git/ and https://code.qt.io/cgit/qt/qtbase.git/ . The application also exposes Qt's own About Qt notice.

## Other runtime libraries

NumPy, SciPy, pandas, Arrow, DuckDB, python-dotenv and yfinance retain their respective licenses and binary distribution notices. Source links and responsibilities are recorded in `docs/tools.md`. PyInstaller's bootloader is distributed under its license with the bundling exception; the PyInstaller notice is included with the build resources. Historical market data and company documents are not embedded in the executable or public repository.

TradingView is a visual workflow reference only. Its proprietary interface code, branding and assets are not copied.
