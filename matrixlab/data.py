"""Strict input contracts. No invented prices or implicit missing-price filling."""
import re

import numpy as np
import pandas as pd


class DataError(ValueError):
    pass


PRICE_BASIS = "total_return_adjusted"
PRICE_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "volume", "price_basis", "source_url", "retrieved_at"]
DOC_COLUMNS = ["doc_id", "symbol", "title", "text", "available_at", "source_url", "retrieved_at"]


def _required(frame, columns):
    missing = set(columns) - set(frame.columns)
    if missing:
        raise DataError("缺少字段：" + ", ".join(sorted(missing)))
    if frame.empty:
        raise DataError("输入数据为空。")


def _text(frame, columns):
    for column in columns:
        if frame[column].isna().any() or frame[column].astype(str).str.strip().eq("").any():
            raise DataError(f"{column}不能有空值。")
        frame[column] = frame[column].astype(str).str.strip()


def validate_prices(frame):
    _required(frame, PRICE_COLUMNS)
    frame = frame.copy()
    _text(frame, ["symbol", "price_basis", "source_url", "retrieved_at"])
    frame["symbol"] = frame.symbol.str.upper()
    if not frame.symbol.map(lambda s: bool(re.fullmatch(r"[A-Z0-9.^=-]{1,20}", s))).all():
        raise DataError("股票代码格式不正确。")
    try:
        frame["date"] = pd.to_datetime(frame.date, errors="raise").dt.normalize()
        if frame.date.dt.tz is not None:
            raise DataError("date须为不带时区的交易所日历日期。")
        pd.to_datetime(frame.retrieved_at, utc=True, errors="raise", format="mixed")
        frame[["open", "high", "low", "close", "volume"]] = frame[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="raise")
    except (ValueError, TypeError) as exc:
        raise DataError("日期或数值格式不正确。") from exc
    if frame.date.isna().any() or frame.duplicated(["symbol", "date"]).any():
        raise DataError("日期缺失或同一股票有重复日线。")
    values = frame[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values[:, :4] <= 0).any() or (values[:, 4] < 0).any():
        raise DataError("价格须为有限正数，成交量须为有限非负数。")
    if ((frame.low > frame[["open", "close"]].min(axis=1) + 1e-7) | (frame.high < frame[["open", "close"]].max(axis=1) - 1e-7) | (frame.high < frame.low)).any():
        raise DataError("OHLC高低价关系不正确。")
    if not frame.price_basis.eq(PRICE_BASIS).all():
        raise DataError("首版仅接受total_return_adjusted复权价格，不能混用未复权行情。")
    if not frame.source_url.str.match(r"https?://").all():
        raise DataError("每条行情必须提供HTTP来源链接。")
    return frame.sort_values(["date", "symbol"]).reset_index(drop=True)


def validate_documents(frame):
    _required(frame, DOC_COLUMNS)
    frame = frame.copy()
    _text(frame, DOC_COLUMNS)
    frame["symbol"] = frame.symbol.str.upper()
    if frame.doc_id.duplicated().any():
        raise DataError("doc_id必须唯一。")
    try:
        frame["available_at"] = pd.to_datetime(frame.available_at, utc=True, errors="raise", format="mixed")
        retrieved = pd.to_datetime(frame.retrieved_at, utc=True, errors="raise", format="mixed")
    except (ValueError, TypeError) as exc:
        raise DataError("资料时间须为有效时间。") from exc
    if (frame.available_at > retrieved).any():
        raise DataError("资料可用时间不能晚于实际获取时间。")
    if not frame.source_url.str.match(r"https?://").all():
        raise DataError("资料须有HTTP来源链接。")
    if frame.text.str.len().gt(12000).any():
        raise DataError("单条资料不超过12000字符，请先切分长文档。")
    return frame.sort_values(["available_at", "symbol"]).reset_index(drop=True)


def read_prices(path):
    return validate_prices(pd.read_csv(path))


def read_documents(path):
    return validate_documents(pd.read_csv(path))


def data_quality(prices):
    days = prices.date.nunique()
    grouped = prices.groupby("symbol").agg(rows=("date", "size"), first=("date", "min"), last=("date", "max"))
    grouped["missing_sessions"] = days - grouped.rows
    return grouped.reset_index()


def cutoff_utc(day):
    # Research date denotes the end of that New York market day.
    return (pd.Timestamp(day).normalize() + pd.Timedelta(days=1)).tz_localize("America/New_York").tz_convert("UTC")
