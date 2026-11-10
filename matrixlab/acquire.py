"""Download real data, retaining sources and conservative availability times."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

from .data import DOC_COLUMNS, PRICE_BASIS, DataError, validate_documents, validate_prices

DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "JNJ", "XOM", "PG", "KO", "WMT"]
WIKI_TITLES = dict(zip(DEFAULT_SYMBOLS, ["Apple Inc.", "Microsoft", "Nvidia", "Amazon (company)",
    "Alphabet Inc.", "Meta Platforms", "JPMorgan Chase", "Johnson & Johnson", "ExxonMobil",
    "Procter & Gamble", "The Coca-Cola Company", "Walmart"]))


def download_history(symbol, start="2021-01-01", end=None):
    start_day = pd.Timestamp(start)
    end_day = pd.Timestamp(end) if end else pd.Timestamp(datetime.now(ZoneInfo("America/New_York")).date())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?" + urlencode({
        "period1": int(start_day.tz_localize("UTC").timestamp()),
        "period2": int(end_day.tz_localize("UTC").timestamp()), "interval": "1d", "events": "div,splits"})
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 MatrixResearchLab/0.1"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload["chart"].get("error"):
        raise DataError(f"{symbol}行情接口报错。")
    result = payload["chart"]["result"][0]
    if result["meta"].get("currency") != "USD":
        raise DataError("首版模拟账本仅支持美元计价行情。")
    quote = result["indicators"]["quote"][0]
    frame = pd.DataFrame({name: quote[name] for name in ["open", "high", "low", "close", "volume"]})
    adjusted = pd.Series(result["indicators"]["adjclose"][0]["adjclose"])
    ratio = adjusted / frame.close
    for name in ["open", "high", "low", "close"]:
        frame[name] *= ratio
    market_tz = result["meta"].get("exchangeTimezoneName", "America/New_York")
    frame["date"] = pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_convert(market_tz).tz_localize(None).normalize()
    frame["symbol"] = symbol
    frame["price_basis"] = PRICE_BASIS
    frame["source_url"] = url
    frame["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    today_ny = pd.Timestamp(datetime.now(ZoneInfo("America/New_York")).date())
    # Never include today's potentially incomplete daily bar; missing values fail validation.
    frame = frame.loc[(frame.date < min(end_day, today_ny)) & (frame.date >= start_day)]
    return validate_prices(frame)


def download_profile(symbol):
    import yfinance as yf

    info = yf.Ticker(symbol).get_info()
    summary = info.get("longBusinessSummary")
    if not summary:
        raise DataError(f"{symbol}没有返回公司简介。")
    retrieved = datetime.now(timezone.utc).isoformat()
    # A current profile has no defensible historical release time. Use retrieval time.
    return {"doc_id": f"yahoo-profile-{symbol}-{retrieved}", "symbol": symbol,
            "title": " | ".join(str(info.get(k, "")) for k in ["longName", "sector", "industry"]),
            "text": summary[:12000], "available_at": retrieved,
            "source_url": f"https://finance.yahoo.com/quote/{symbol}/profile/", "retrieved_at": retrieved}


def fetch_dataset(directory, symbols=None, start="2021-01-01", end=None, profiles=True):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    from .trading import Broker

    if (directory / "paper.sqlite3").exists() and Broker(directory / "paper.sqlite3").exists():
        raise DataError("本工作区已有模拟账本，请在新的MATRIX_DATA_DIR中下载，避免修改账本的价格基准。")
    symbols = [s.upper() for s in (symbols or DEFAULT_SYMBOLS)]
    errors, price_frames, documents = [], [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks = {pool.submit(download_history, s, start, end): (s, "prices") for s in symbols}
        if profiles:
            tasks.update({pool.submit(download_profile, s): (s, "profile") for s in symbols})
        for task in as_completed(tasks):
            symbol, kind = tasks[task]
            try:
                result = task.result()
                (price_frames if kind == "prices" else documents).append(result)
            except Exception as exc:
                errors.append({"symbol": symbol, "kind": kind, "error": type(exc).__name__})
    if not price_frames:
        raise DataError("所有行情下载失败。请使用CSV导入；不会生成替代行情。")
    prices = validate_prices(pd.concat(price_frames, ignore_index=True))
    price_path = directory / "prices.csv"
    temp = price_path.with_suffix(".csv.part")
    prices.to_csv(temp, index=False)
    temp.replace(price_path)
    if documents:
        doc_frames = [pd.DataFrame(documents)]
        if (directory / "documents.csv").exists():
            doc_frames.append(pd.read_csv(directory / "documents.csv"))
        docs = validate_documents(pd.concat(doc_frames, ignore_index=True).drop_duplicates("doc_id"))
        temp = directory / "documents.csv.part"
        docs.to_csv(temp, index=False)
        temp.replace(directory / "documents.csv")
    elif not (directory / "documents.csv").exists():
        pd.DataFrame(columns=DOC_COLUMNS).to_csv(directory / "documents.csv", index=False)
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "symbols": sorted(prices.symbol.unique().tolist()),
                "rows": len(prices), "documents_downloaded": len(documents), "start": str(prices.date.min().date()),
                "end": str(prices.date.max().date()), "errors": errors, "price_basis": PRICE_BASIS,
                "notes": "行情为供应商回溯修订后的复权快照。当前简介available_at为获取时间，不可回用于历史筛选。"}
    (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def download_archived_description(symbol, asof):
    """Fetch a specific Wikipedia revision, never backdate a current profile."""
    from bs4 import BeautifulSoup

    def request(params):
        url = "https://en.wikipedia.org/w/api.php?" + urlencode({"format": "json", **params})
        with urlopen(Request(url, headers={"User-Agent": "MatrixResearchLab/0.1 educational research"}), timeout=30) as response:
            return json.load(response)

    result = request({"action": "query", "prop": "revisions", "titles": WIKI_TITLES[symbol],
                      "rvprop": "ids|timestamp", "rvstart": str(pd.Timestamp(asof).date()) + "T23:59:59Z", "rvlimit": 1})
    page = next(iter(result["query"]["pages"].values()))
    revision = page["revisions"][0]
    parsed = request({"action": "parse", "oldid": revision["revid"], "prop": "text", "disablelimitreport": 1})
    soup = BeautifulSoup(parsed["parse"]["text"]["*"], "html.parser")
    container = soup.select_one(".mw-parser-output") or soup
    paragraphs = [p.get_text(" ", strip=True) for p in container.find_all("p", recursive=False)]
    text = "\n".join([p for p in paragraphs if len(p) > 100][:5])[:10000]
    if not text:
        raise DataError("历史版本未返回可用正文。")
    return {"doc_id": f"wikipedia-{symbol}-{revision['revid']}", "symbol": symbol,
            "title": page["title"] + " · archived introduction", "text": text,
            "available_at": revision["timestamp"], "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "source_url": f"https://en.wikipedia.org/w/index.php?oldid={revision['revid']}"}


def archive_documents(directory, asof="2024-12-31", symbols=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    symbols = symbols or DEFAULT_SYMBOLS
    documents, errors = [], []
    cache = directory / "archive_sources"
    cache.mkdir(exist_ok=True)

    def archived(symbol):
        path = cache / f"{symbol}-{pd.Timestamp(asof).date()}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        record = download_archived_description(symbol, asof)
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return record

    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks = {pool.submit(archived, s): s for s in symbols}
        for task in as_completed(tasks):
            try:
                documents.append(task.result())
            except Exception as exc:
                errors.append({"symbol": tasks[task], "error": type(exc).__name__})
    if not documents:
        raise DataError("历史资料获取失败，不能用当前简介冒充。")
    path = directory / "documents.csv"
    frames = [pd.DataFrame(documents)]
    if path.exists():
        frames.append(pd.read_csv(path))
    merged = pd.concat(frames, ignore_index=True).drop_duplicates("doc_id")
    merged = validate_documents(merged)
    part = path.with_suffix(".csv.part")
    merged.to_csv(part, index=False)
    part.replace(path)
    report = {"archived_documents": len(documents), "asof": asof, "errors": errors,
              "source": "Wikipedia historical revision IDs; attribution retained in source_url"}
    (directory / "archive-manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
