import argparse
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd

from .acquire import DEFAULT_SYMBOLS, archive_documents, fetch_dataset
from .agent import run_workflow
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
    research = commands.add_parser("research", help="按研究日期截断执行关键词或JEVDB语义筛选")
    research.add_argument("query")
    research.add_argument("--asof", default=str(datetime.now(ZoneInfo("America/New_York")).date()))
    research.add_argument("--mode", choices=["keyword", "jevdb"], default="keyword")
    research.add_argument("--operator", choices=["all", "any"], default="all")
    research.add_argument("--jev-op", choices=["holds", "probability", "choose", "score", "prune_then_decide"], default="holds")
    research.add_argument("--threshold", type=float, default=0.5)
    research.add_argument("--prune-k", type=int, default=None)
    agent_cmd = commands.add_parser("agent", help="运行四层Agent工作流：研究筛选→矩阵风控→调仓提案→显式审批撮合")
    agent_cmd.add_argument("query")
    agent_cmd.add_argument("--asof", default="2025-01-27")
    agent_cmd.add_argument("--mode", choices=["keyword", "jevdb"], default="keyword")
    agent_cmd.add_argument("--operator", choices=["all", "any"], default="all")
    agent_cmd.add_argument("--jev-op", choices=["holds", "probability", "choose", "score", "prune_then_decide"], default="holds")
    agent_cmd.add_argument("--threshold", type=float, default=0.5)
    agent_cmd.add_argument("--prune-k", type=int, default=None)
    agent_cmd.add_argument("--fixed-alpha", type=float, default=None, help="指定固定收缩系数；默认使用Ledoit-Wolf最优收缩")
    agent_cmd.add_argument("--approve", action="store_true", help="显式批准高风险模拟下单写入SQLite账本")
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
            run = screen(docs, args.query, args.asof, settings, args.mode,
                         operator=args.operator, jev_op=args.jev_op,
                         threshold=args.threshold, prune_k=args.prune_k)
            path = run.save(settings.data_dir / "research_runs")
            result = {"backend": run.backend, "jev_op": run.jev_op, "inputs": run.inputs,
                      "pruned_from": run.pruned_from, "matches": len(run.matches), "record": str(path)}
        elif args.command == "agent":
            prices = read_prices(settings.data_dir / "prices.csv")
            docs = read_documents(settings.data_dir / "documents.csv")
            trace = run_workflow(
                prices, docs, args.query, args.asof, settings,
                mode=args.mode, operator=args.operator, jev_op=args.jev_op,
                threshold=args.threshold, prune_k=args.prune_k,
                alpha=0.05 if args.fixed_alpha is None else args.fixed_alpha,
                use_ledoit_wolf=args.fixed_alpha is None,
                approve_execution=args.approve,
            )
            path = trace.save(settings.data_dir / "agent_runs")
            result = {"trace_id": trace.trace_id, "selected_symbols": trace.selected_symbols,
                      "approved_execution": trace.approved_execution, "proposed_orders": len(trace.proposed_orders),
                      "fills": len(trace.fills), "record": str(path)}
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
                      "condition_after": risk.condition_after, "ledoit_wolf_alpha": risk.ledoit_wolf_alpha,
                      "kkt_complementarity_error": risk.kkt_complementarity_error,
                      "weights": risk.weights.to_dict(),
                      "holdout": performance(curve).to_dict(), "fills": len(fills), "cash": account["cash"],
                      "note": "复权价格模拟份额；当前公司简介未用于历史选股。关键词基线不属于JEVDB语义结果。"}
            (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except (DataError, TradingError, ResearchUnavailable, FileNotFoundError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
