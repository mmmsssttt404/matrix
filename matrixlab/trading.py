"""Atomic, idempotent educational trading on a single adjusted-price basis."""
from dataclasses import asdict, dataclass
from contextlib import contextmanager
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import numpy as np
import pandas as pd

from .data import DataError, PRICE_BASIS

SCALE = 1_000_000


def _money(value):
    return int((Decimal(str(value)) * SCALE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Order:
    symbol: str
    side: str
    quantity: int


class TradingError(ValueError):
    pass


class Broker:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS account (
                    id INTEGER PRIMARY KEY CHECK(id=1), cash INTEGER NOT NULL,
                    initial_cash INTEGER NOT NULL, clock TEXT NOT NULL,
                    commission_bps REAL NOT NULL, slippage_bps REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, quantity INTEGER NOT NULL CHECK(quantity>0));
                CREATE TABLE IF NOT EXISTS batches (request_id TEXT PRIMARY KEY, payload TEXT NOT NULL, result TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY, request_id TEXT NOT NULL,
                    signal_date TEXT NOT NULL, fill_date TEXT NOT NULL, symbol TEXT NOT NULL,
                    side TEXT NOT NULL, quantity INTEGER NOT NULL, price REAL NOT NULL,
                    fee REAL NOT NULL, notional REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS snapshots (
                    date TEXT PRIMARY KEY, cash REAL NOT NULL, market_value REAL NOT NULL, equity REAL NOT NULL);
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _account(db):
        row = db.execute("SELECT * FROM account WHERE id=1").fetchone()
        if row is None:
            raise TradingError("请先创建模拟账户。")
        return dict(row)

    def exists(self):
        with self._db() as db:
            return db.execute("SELECT 1 FROM account").fetchone() is not None

    def initialize(self, cash, start_date, commission_bps=10, slippage_bps=5):
        if not np.isfinite(cash) or cash <= 0 or cash > 1e9:
            raise TradingError("初始现金须为0—10亿美元之间的有限正数。")
        if not all(np.isfinite(x) and 0 <= x <= 1000 for x in [commission_bps, slippage_bps]):
            raise TradingError("手续费和滑点须为0—1000bp。")
        start = str(pd.Timestamp(start_date).date())
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM account").fetchone():
                raise TradingError("账户已存在；请使用另一个账本文件，不能覆盖既有交易。")
            db.execute("INSERT INTO account VALUES(1,?,?,?,?,?)", (_money(cash), _money(cash), start, commission_bps, slippage_bps))
            db.execute("INSERT INTO snapshots VALUES(?,?,0,?)", (start, cash, cash))

    @staticmethod
    def _snapshot(db, prices, day):
        account = Broker._account(db)
        rows = db.execute("SELECT * FROM positions ORDER BY symbol").fetchall()
        marks = prices.loc[prices.date.eq(pd.Timestamp(day))].set_index("symbol")
        market = 0
        for row in rows:
            if row["symbol"] not in marks.index:
                raise TradingError(f"{day}缺少{row['symbol']}估值行情，未推进账本。")
            market += _money(marks.at[row["symbol"], "close"]) * row["quantity"]
        cash = account["cash"] / SCALE
        db.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?)", (day, cash, market / SCALE, (account["cash"] + market) / SCALE))
        db.execute("UPDATE account SET clock=? WHERE id=1", (day,))

    def advance(self, prices, target_date):
        target = str(pd.Timestamp(target_date).date())
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            account = self._account(db)
            if target <= account["clock"]:
                raise TradingError("只能向未来推进模拟日期。")
            days = sorted(prices.loc[(prices.date > pd.Timestamp(account["clock"])) & (prices.date <= pd.Timestamp(target)), "date"].unique())
            if not days or str(pd.Timestamp(days[-1]).date()) != target:
                raise TradingError("目标日期必须有行情。")
            for day in days:
                self._snapshot(db, prices, str(pd.Timestamp(day).date()))

    def execute(self, orders, signal_date, prices, request_id):
        if not request_id or len(request_id) > 200 or not orders:
            raise TradingError("订单与请求编号不能为空。")
        seen = set()
        for order in orders:
            if not isinstance(order.quantity, int) or isinstance(order.quantity, bool) or not 0 < order.quantity <= 1_000_000_000:
                raise TradingError("数量必须为正整数模拟份额。")
            if order.side not in {"BUY", "SELL"} or order.symbol in seen:
                raise TradingError("买卖方向无效，或同一批次出现重复股票。")
            seen.add(order.symbol)
        if not prices.price_basis.eq(PRICE_BASIS).all():
            raise TradingError("交易价格必须采用统一复权基准。")
        signal = str(pd.Timestamp(signal_date).date())
        payload = json.dumps({"signal": signal, "orders": [asdict(o) for o in orders]}, sort_keys=True)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT * FROM batches WHERE request_id=?", (request_id,)).fetchone()
            if previous:
                if previous["payload"] != payload:
                    raise TradingError("请求编号已用于不同订单。")
                return json.loads(previous["result"])
            account = self._account(db)
            if signal != account["clock"]:
                raise TradingError("信号日期必须等于当前模拟日期，不能回溯或跳过时钟。")
            future = prices.loc[prices.date > pd.Timestamp(signal)]
            if future.empty:
                raise TradingError("尚无下一交易日行情，不能假设成交。")
            fill_date = str(future.date.min().date())
            quotes = future.loc[future.date.eq(pd.Timestamp(fill_date))].set_index("symbol")
            results = []
            # Sell before buying so a rebalance uses available proceeds within one transaction.
            for order in sorted(orders, key=lambda o: o.side == "BUY"):
                if order.symbol not in quotes.index:
                    raise TradingError(f"下一交易日缺少{order.symbol}开盘价。")
                factor = Decimal(1) + (Decimal(1) if order.side == "BUY" else Decimal(-1)) * Decimal(str(account["slippage_bps"])) / 10000
                price = (Decimal(str(quotes.at[order.symbol, "open"])) * factor).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                notional = price * order.quantity
                fee = (notional * Decimal(str(account["commission_bps"])) / 10000).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                holding = db.execute("SELECT quantity FROM positions WHERE symbol=?", (order.symbol,)).fetchone()
                quantity = holding[0] if holding else 0
                cash = self._account(db)["cash"]
                if order.side == "BUY":
                    if _money(notional + fee) > cash:
                        raise TradingError("现金不足，整批订单均未成交。")
                    cash -= _money(notional + fee)
                    quantity += order.quantity
                else:
                    if order.quantity > quantity:
                        raise TradingError("可卖持仓不足，整批订单均未成交。")
                    cash += _money(notional - fee)
                    quantity -= order.quantity
                db.execute("UPDATE account SET cash=? WHERE id=1", (cash,))
                if quantity:
                    db.execute("INSERT INTO positions VALUES(?,?) ON CONFLICT(symbol) DO UPDATE SET quantity=excluded.quantity", (order.symbol, quantity))
                else:
                    db.execute("DELETE FROM positions WHERE symbol=?", (order.symbol,))
                record = {"order_id": str(uuid4()), "request_id": request_id, "signal_date": signal,
                          "fill_date": fill_date, "symbol": order.symbol, "side": order.side,
                          "quantity": order.quantity, "price": float(price), "fee": float(fee), "notional": float(notional)}
                db.execute("INSERT INTO orders VALUES(:order_id,:request_id,:signal_date,:fill_date,:symbol,:side,:quantity,:price,:fee,:notional)", record)
                results.append(record)
            self._snapshot(db, prices, fill_date)
            db.execute("INSERT INTO batches VALUES(?,?,?)", (request_id, payload, json.dumps(results)))
            return results

    def state(self):
        with self._db() as db:
            account = self._account(db)
            account["cash"] /= SCALE
            account["initial_cash"] /= SCALE
            positions = pd.read_sql_query("SELECT * FROM positions ORDER BY symbol", db)
            history = pd.read_sql_query("SELECT * FROM snapshots ORDER BY date", db, parse_dates=["date"])
            orders = pd.read_sql_query("SELECT * FROM orders ORDER BY fill_date, rowid", db)
            return account, positions, history, orders


def rebalance_orders(prices, weights, asof, equity, positions, buffer=0.05):
    if not 0 <= buffer < 1 or not np.isfinite(equity) or equity <= 0:
        raise TradingError("资金或现金预留比例无效。")
    if (weights < 0).any() or not np.isfinite(weights).all() or not np.isclose(weights.sum(), 1):
        raise TradingError("目标权重须非负、有限且和为1。")
    closes = prices.loc[prices.date.eq(pd.Timestamp(asof))].set_index("symbol").close
    current = dict(zip(positions.symbol, positions.quantity))
    symbols = set(weights.index) | set(current)
    orders = []
    for symbol in sorted(symbols):
        if symbol not in closes:
            raise TradingError(f"{symbol}没有研究日收盘价，不能生成订单。")
        target = int(equity * (1 - buffer) * float(weights.get(symbol, 0)) / closes[symbol])
        difference = target - int(current.get(symbol, 0))
        if difference:
            orders.append(Order(symbol, "BUY" if difference > 0 else "SELL", abs(difference)))
    return orders
