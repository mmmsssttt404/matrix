from dotenv import load_dotenv
import pandas as pd
from PySide6 import QtCore

from ..config import Settings
from ..data import DOC_COLUMNS, read_documents, read_prices
from ..trading import Broker

COMPANIES = {"AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "AMZN": "Amazon",
             "GOOGL": "Alphabet", "META": "Meta Platforms", "JPM": "JPMorgan Chase", "JNJ": "Johnson & Johnson",
             "XOM": "Exxon Mobil", "PG": "Procter & Gamble", "KO": "Coca-Cola", "WMT": "Walmart"}


class Workspace(QtCore.QObject):
    changed = QtCore.Signal()
    symbol_changed = QtCore.Signal(str)
    date_changed = QtCore.Signal()

    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings or Settings.load()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        load_dotenv(self.settings.data_dir / ".desktop.env", override=False)
        loaded = Settings.load()
        self.settings = Settings(self.settings.data_dir, loaded.backend, loaded.endpoint, loaded.model, loaded.service_url, loaded.service_token)
        self.prices = pd.DataFrame()
        self.documents = pd.DataFrame(columns=DOC_COLUMNS)
        self.symbol = ""
        self.asof = None
        self.risk = None
        self.risk_asof = None
        self.selection_asof = None
        self.selected_symbols = []
        self.broker = Broker(self.settings.data_dir / "paper.sqlite3")
        self.reload()

    def reload(self):
        price_path = self.settings.data_dir / "prices.csv"
        self.prices = read_prices(price_path) if price_path.exists() else pd.DataFrame()
        docs = self.settings.data_dir / "documents.csv"
        if docs.exists() and len(pd.read_csv(docs)):
            self.documents = read_documents(docs)
        if not self.prices.empty:
            self.symbols = sorted(self.prices.symbol.unique())
            self.days = sorted(self.prices.date.unique())
            self.symbol = self.symbol if self.symbol in self.symbols else self.symbols[0]
            if self.asof is None:
                self.asof = pd.Timestamp(self.broker.state()[0]["clock"]) if self.broker.exists() else self.prices.date.max()
            self.selected_symbols = self.selected_symbols or self.symbols.copy()
        else:
            self.symbols, self.days = [], []
        self.risk = None
        self.changed.emit()

    def select(self, symbol):
        self.symbol = symbol
        self.symbol_changed.emit(symbol)

    def set_date(self, date):
        self.asof = pd.Timestamp(date).normalize()
        self.risk = None
        self.date_changed.emit()

    def series(self):
        if self.prices.empty:
            return pd.DataFrame()
        return self.prices.loc[(self.prices.symbol == self.symbol) & (self.prices.date <= self.asof)]

    def quotes(self):
        rows = []
        if self.prices.empty:
            return pd.DataFrame(columns=["代码", "最新", "涨跌幅"])
        for symbol in self.symbols:
            history = self.prices.loc[(self.prices.symbol == symbol) & (self.prices.date <= self.asof)]
            if history.empty:
                continue
            last = history.iloc[-1]
            change = last.close / history.iloc[-2].close - 1 if len(history) > 1 else 0
            rows.append({"代码": symbol, "最新": last.close, "涨跌幅": change})
        return pd.DataFrame(rows)
