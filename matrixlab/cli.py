import argparse
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd

from .acquire import DEFAULT_SYMBOLS, archive_documents, fetch_dataset
from .analytics import analyze, holdout_curve, performance
from .config import Settings
from .data import DataError, read_documents, read_prices
from .research import ResearchUnavailable, inspect_backend, screen
from .trading import Broker, TradingError, rebalance_orders


def main(argv=None):
    parser = argparse.ArgumentParser(description="Matrix Research Lab")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="检查JEVDB二进制与凭证状态，不发送模型请求")
    fetch = commands.add_parser("fetch", help="下载真实历史行情和当前公司简介")
    fetch.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    fetch.add_argument("--start", default="2021-01-01")
    fetch.add_argument("--end")
    fetch.add_argument("--no-profiles", action="store_true")
    archive = commands.add_parser("archive", help="获取指定日期之前的Wikipedia公司介绍版本，用于历史筛选")
    archive.add_argument("--asof", default="2024-12-31")
    archive.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    research = commands.add_parser("research")
    research.add_argument("query")
    research.add_argument("--asof", default=str(datetime.now(ZoneInfo("America/New_York")).date()))
    research.add_argument("--mode", choices=["keyword", "jevdb"], default="keyword")
    demo = commands.add_parser("demo", help="用真实行情演示矩阵分析、样本外比较及一次模拟建仓")
    demo.add_argument("--asof")
    demo.add_argument("--symbols", nargs="+")
    args = parser.parse_args(argv)
    settings = Settings.load()
    try:
        if args.command == "doctor":
            result = inspect_backend()
            result.update({"data_dir": str(settings.data_dir), "backend": settings.backend,
                           "credential_available": settings.credential_available})
        elif args.command == "fetch":
            result = fetch_dataset(settings.data_dir, args.symbols, args.start, args.end, not args.no_profiles)
        elif args.command == "archive":
            result = archive_documents(settings.data_dir, args.asof, args.symbols)
        elif args.command == "research":
            docs = read_documents(settings.data_dir / "documents.csv")
            run = screen(docs, args.query, args.asof, settings, args.mode)
            path = run.save(settings.data_dir / "research_runs")
            result = {"backend": run.backend, "inputs": run.inputs, "matches": len(run.matches), "record": str(path)}
        else:
            prices = read_prices(settings.data_dir / "prices.csv")
            days = sorted(prices.date.unique())
            day = pd.Timestamp(args.asof) if args.asof else pd.Timestamp(days[int(len(days) * 0.7)])
            symbols = args.symbols or sorted(prices.symbol.unique())
            risk = analyze(prices, symbols, day)
            curve = holdout_curve(prices, risk.weights, day)
            output = settings.data_dir / "demo" / str(uuid4())
            output.mkdir(parents=True)
            curve.to_csv(output / "holdout.csv")
            risk.covariance.to_csv(output / "covariance.csv")
            risk.weights.to_csv(output / "weights.csv")
            broker = Broker(output / "paper.sqlite3")
            broker.initialize(100000, day)
            _, positions, _, _ = broker.state()
            ticket = rebalance_orders(prices, risk.weights, day, 100000, positions)
            fills = broker.execute(ticket, day, prices, str(uuid4()))
            account, _, _, _ = broker.state()
            result = {"output": str(output), "signal_date": str(day.date()), "observations": len(risk.returns),
                      "annualized_volatility": risk.volatility, "condition_before": risk.condition_before,
                      "condition_after": risk.condition_after, "weights": risk.weights.to_dict(),
                      "holdout": performance(curve).to_dict(), "fills": len(fills), "cash": account["cash"],
                      "note": "复权价格模拟份额；当前公司简介未用于历史选股。关键词基线不属于JEVDB语义结果。"}
            (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except (DataError, TradingError, ResearchUnavailable, FileNotFoundError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
