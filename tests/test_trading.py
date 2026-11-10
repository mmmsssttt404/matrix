from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
import pytest

from matrixlab.trading import Broker, Order, TradingError


def test_next_open_costs_cash_positions_and_idempotency(prices, tmp_path):
    day = prices.date.unique()[80]
    broker = Broker(tmp_path / "paper.sqlite3")
    broker.initialize(100000, day, commission_bps=10, slippage_bps=5)
    ticket = [Order("AAA", "BUY", 10)]
    result = broker.execute(ticket, day, prices, "one-click")
    assert broker.execute(ticket, day, prices, "one-click") == result
    account, positions, _, records = broker.state()
    assert len(records) == 1
    assert positions.iloc[0].quantity == 10
    next_day = prices.loc[prices.date > day, "date"].min()
    opening = prices.loc[(prices.date == next_day) & (prices.symbol == "AAA"), "open"].iloc[0]
    expected_price = (Decimal(str(opening)) * Decimal("1.0005")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    fee = (expected_price * 10 * Decimal("0.001")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert result[0]["price"] == float(expected_price)
    assert result[0]["fill_date"] == str(next_day.date())
    assert account["cash"] == pytest.approx(100000 - float(expected_price * 10 + fee))


def test_entire_batch_rolls_back(prices, tmp_path):
    day = prices.date.unique()[80]
    broker = Broker(tmp_path / "paper.sqlite3")
    broker.initialize(1000, day)
    with pytest.raises(TradingError, match="现金不足"):
        broker.execute([Order("AAA", "BUY", 1), Order("BBB", "BUY", 100000)], day, prices, "batch")
    account, positions, snapshots, records = broker.state()
    assert account["cash"] == 1000
    assert positions.empty and records.empty and len(snapshots) == 1


def test_invalid_orders_and_clock_rejected(prices, tmp_path):
    day = prices.date.unique()[80]
    broker = Broker(tmp_path / "paper.sqlite3")
    broker.initialize(100000, day)
    for order in [Order("AAA", "BUY", 0), Order("AAA", "BUY", -1), Order("AAA", "BUY", 1.5), Order("AAA", "SELL", 1)]:
        with pytest.raises(TradingError):
            broker.execute([order], day, prices, str(order))
    with pytest.raises(TradingError, match="当前模拟日期"):
        broker.execute([Order("AAA", "BUY", 1)], prices.date.unique()[79], prices, "past")
    with pytest.raises(TradingError, match="下一交易日"):
        broker.advance(prices, prices.date.max())
        broker.execute([Order("AAA", "BUY", 1)], prices.date.max(), prices, "no-future")


def test_concurrent_duplicate_is_only_filled_once(prices, tmp_path):
    day = prices.date.unique()[80]
    path = tmp_path / "paper.sqlite3"
    broker = Broker(path)
    broker.initialize(100000, day)
    ticket = [Order("AAA", "BUY", 2)]
    def submit(_):
        return Broker(path).execute(ticket, day, prices, "same-request")
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.map(submit, range(2))
    assert a == b
    _, positions, _, records = broker.state()
    assert len(records) == 1 and positions.iloc[0].quantity == 2


def test_missing_mark_rolls_back_clock(prices, tmp_path):
    day = prices.date.unique()[80]
    broker = Broker(tmp_path / "paper.sqlite3")
    broker.initialize(100000, day)
    broker.execute([Order("AAA", "BUY", 1)], day, prices, "buy")
    before = broker.state()[0]["clock"]
    target = prices.date.unique()[83]
    missing = prices.loc[~((prices.symbol == "AAA") & (prices.date == target))]
    with pytest.raises(TradingError, match="估值行情"):
        broker.advance(missing, target)
    assert broker.state()[0]["clock"] == before


def test_sell_credits_net_proceeds_and_removes_closed_position(prices, tmp_path):
    day = prices.date.unique()[80]
    broker = Broker(tmp_path / "paper.sqlite3")
    broker.initialize(100000, day)
    broker.execute([Order("AAA", "BUY", 2)], day, prices, "buy")
    before = broker.state()[0]
    fills = broker.execute([Order("AAA", "SELL", 2)], before["clock"], prices, "sell")
    account, positions, _, orders = broker.state()
    assert positions.empty and len(orders) == 2
    assert account["cash"] == pytest.approx(before["cash"] + fills[0]["notional"] - fills[0]["fee"])
    with pytest.raises(TradingError, match="不同订单"):
        broker.execute([Order("AAA", "BUY", 3)], day, prices, "buy")
