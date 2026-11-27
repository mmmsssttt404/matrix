"""Auditable four-layer agentic workflow harness (Preamble, Plan, Retrieve, Act)
with Human-in-the-Loop risk tiers aligned with Matrix Analysis Lec0."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from uuid import uuid4

import pandas as pd

from .analytics import analyze, holdout_curve, performance
from .data import DataError
from .research import screen
from .trading import Broker, rebalance_orders

RISK_LOW = "LOW_AUTO"
RISK_MEDIUM = "MEDIUM_CONFIRM"
RISK_HIGH = "HIGH_EXPLICIT_APPROVAL"


@dataclass
class TraceStep:
    step: int
    layer: str
    skill: str
    action: str
    risk_tier: str
    status: str
    elapsed_seconds: float
    summary: dict


@dataclass
class AgentTrace:
    trace_id: str
    created_at: str
    user_query: str
    asof: str
    mode: str
    jev_op: str
    strategy: str
    approved_execution: bool
    steps: list
    selected_symbols: list
    diagnostics: dict
    proposed_orders: list
    fills: list

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"agent-trace-{self.trace_id}.json"
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return path


def run_workflow(
    prices,
    documents,
    user_query,
    asof,
    settings,
    *,
    mode="keyword",
    operator="all",
    jev_op="holds",
    threshold=0.5,
    prune_k=None,
    lookback=252,
    alpha=0.05,
    use_ledoit_wolf=True,
    strategy="min_var",
    broker_path=None,
    initial_cash=100000.0,
    approve_execution=False,
    include_holdout=False,
):
    """Execute end-to-end research -> matrix risk -> order proposal -> gated execution.

    Risk tiers follow explicit human control boundaries:
      - LOW_AUTO: research screening, covariance/PCA/KKT diagnostics
      - MEDIUM_CONFIRM: rebalance ticket construction (preview only)
      - HIGH_EXPLICIT_APPROVAL: SQLite ledger mutation (requires approve_execution=True)
    """
    if strategy not in {"min_var", "erc"}:
        raise DataError(f"不支持的组合优化策略：{strategy}（仅支持 min_var / erc）。")
    trace_id = str(uuid4())
    steps = []
    asof_ts = pd.Timestamp(asof)
    asof_str = str(asof_ts.date())

    # Step 1: Reasoning / Planning
    t0 = time.perf_counter()
    plan = [
        {"skill": "matrix-stock-research", "goal": f"Filter documents available before {asof_str}"},
        {"skill": "matrix-portfolio-risk", "goal": "Estimate covariance, shrinkage, QP/ERC weights & KKT residuals"},
        {"skill": "matrix-paper-broker", "goal": "Generate rebalance ticket and gate execution on explicit approval"},
    ]
    steps.append(asdict(TraceStep(
        1, "Reasoning/Planning", "orchestrator", "decompose_request", RISK_LOW, "completed",
        round(time.perf_counter() - t0, 4), {"plan": plan},
    )))

    # Step 2: Retrieval / Context (matrix-stock-research skill)
    t0 = time.perf_counter()
    research_run = screen(
        documents, user_query, asof_str, settings, mode=mode, max_documents=200,
        operator=operator, jev_op=jev_op, threshold=threshold, prune_k=prune_k,
    )
    available_symbols = set(prices.loc[prices.date <= asof_ts, "symbol"].unique())
    selected = sorted({row["symbol"] for row in research_run.matches} & available_symbols)
    steps.append(asdict(TraceStep(
        2, "Retrieval/Context", "matrix-stock-research", f"screen({mode}/{jev_op})", RISK_LOW, "completed",
        round(time.perf_counter() - t0, 4),
        {
            "backend": research_run.backend,
            "inputs_evaluated": research_run.inputs,
            "pruned_from": research_run.pruned_from,
            "prune_fallback": research_run.prune_fallback,
            "matched_documents": len(research_run.matches),
            "selected_symbols": selected,
        },
    )))
    if len(selected) < 2:
        raise DataError(f"筛选仅命中 {len(selected)} 只有行情的公司（{selected}），至少需要 2 只才能构建组合。")

    # Step 3: Action / Analytical Computation (matrix-portfolio-risk skill)
    t0 = time.perf_counter()
    risk = analyze(prices, selected, asof_str, lookback=lookback, alpha=alpha, use_ledoit_wolf=use_ledoit_wolf)
    target_weights = risk.risk_parity_weights if strategy == "erc" else risk.weights
    diagnostics = {
        "symbols": selected,
        "strategy": strategy,
        "observations": len(risk.returns),
        "alpha_used": round(risk.alpha, 6),
        "ledoit_wolf_alpha": round(risk.ledoit_wolf_alpha, 6),
        "volatility": round(risk.volatility, 6),
        "regularized_volatility": round(risk.regularized_volatility, 6),
        "condition_before": round(risk.condition_before, 4),
        "condition_after": round(risk.condition_after, 4),
        "min_eigenvalue_raw": round(float(risk.eigenvalues.min()), 6),
        "min_eigenvalue_regularized": round(float(risk.regularized_eigenvalues.min()), 6),
        "pc1_explained": round(float(risk.explained_variance[0]), 6),
        "kkt_primal_error": risk.kkt_primal_error,
        "kkt_dual_violation": risk.kkt_dual_violation,
        "kkt_complementarity_error": risk.kkt_complementarity_error,
        "weights": {k: round(float(v), 6) for k, v in risk.weights.items()},
        "erc_weights": {k: round(float(v), 6) for k, v in risk.risk_parity_weights.items()},
        "target_weights": {k: round(float(v), 6) for k, v in target_weights.items()},
    }
    if include_holdout:
        try:
            curve = holdout_curve(prices, target_weights, asof_str)
            diagnostics["holdout_performance"] = performance(curve).round(6).to_dict()
        except DataError:
            diagnostics["holdout_performance"] = None
    else:
        diagnostics["holdout_performance"] = None
    steps.append(asdict(TraceStep(
        3, "Action/Execution", "matrix-portfolio-risk", f"analyze_portfolio({strategy})", RISK_LOW, "completed",
        round(time.perf_counter() - t0, 4), diagnostics,
    )))

    # Step 4: Medium-Risk Order Proposal (matrix-paper-broker skill — strictly read-only)
    t0 = time.perf_counter()
    target_broker_path = Path(broker_path) if broker_path else settings.data_dir / "agent_runs" / f"{trace_id}.sqlite3"
    broker = None
    if target_broker_path.exists():
        broker = Broker(target_broker_path)
    if broker is not None and broker.exists():
        account, positions, snapshots, _ = broker.state()
        if account["clock"] != asof_str:
            raise DataError(f"已有账本时钟 {account['clock']} 与研究日期 {asof_str} 不一致，已中止以避免跨时点调仓。")
        equity = float(snapshots.iloc[-1].equity)
        clock = account["clock"]
    else:
        positions = pd.DataFrame(columns=["symbol", "quantity"])
        equity = float(initial_cash)
        clock = asof_str
    ticket = rebalance_orders(prices, target_weights, asof_str, equity, positions)
    proposed = [asdict(order) for order in ticket]
    steps.append(asdict(TraceStep(
        4, "Action/Execution", "matrix-paper-broker", f"propose_rebalance({strategy})", RISK_MEDIUM, "awaiting_confirmation",
        round(time.perf_counter() - t0, 4), {"strategy": strategy, "order_count": len(proposed), "orders": proposed, "account_clock": clock},
    )))

    # Step 5: High-Risk Ledger Execution (Explicit Approval Gate)
    fills = []
    t0 = time.perf_counter()
    if approve_execution:
        if broker is None:
            broker = Broker(target_broker_path)
        if not broker.exists():
            broker.initialize(initial_cash, asof_str)
        if ticket:
            fills = broker.execute(ticket, asof_str, prices, f"agent-{trace_id}")
        steps.append(asdict(TraceStep(
            5, "Action/Execution", "matrix-paper-broker", "execute_orders", RISK_HIGH, "executed",
            round(time.perf_counter() - t0, 4), {"fills_count": len(fills), "fills": fills},
        )))
    else:
        steps.append(asdict(TraceStep(
            5, "Action/Execution", "matrix-paper-broker", "execute_orders", RISK_HIGH, "blocked_pending_human_approval",
            round(time.perf_counter() - t0, 4), {"reason": "High-risk ledger mutation requires explicit approve_execution=True."},
        )))

    return AgentTrace(
        trace_id=trace_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        user_query=user_query,
        asof=asof_str,
        mode=mode,
        jev_op=jev_op,
        strategy=strategy,
        approved_execution=bool(approve_execution),
        steps=steps,
        selected_symbols=selected,
        diagnostics=diagnostics,
        proposed_orders=proposed,
        fills=fills,
    )
