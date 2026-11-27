"""Auditable four-layer agentic workflow harness (Preamble, Plan, Retrieve, Act)
with Human-in-the-Loop risk tiers aligned with Matrix Analysis Lec0."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import escape
import json
import math
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
    matched_documents: list = field(default_factory=list)

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"agent-trace-{self.trace_id}.json"
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return path

    def export_html_report(self, directory):
        """Render a self-contained, offline-readable HTML audit report with local evidence."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "trace.json").write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )

        def html_table(rows):
            if not rows:
                return "<p class='muted'>无记录</p>"
            return pd.DataFrame(rows).to_html(index=False, escape=True, border=0)

        status_zh = {
            "completed": "已完成",
            "awaiting_confirmation": "待人工确认",
            "blocked_pending_human_approval": "已拦截（等待人工显式审批）",
            "executed": "已人工批准并原子成交",
        }
        strat_zh = "风险平价（Spinu 凸 ERC）" if self.strategy == "erc" else "只做多最小方差（QP）"
        step_rows = [
            {
                "步骤": s["step"],
                "架构层级": s["layer"],
                "Skill": s["skill"],
                "动作": s["action"],
                "风险等级": s["risk_tier"],
                "状态": status_zh.get(s["status"], s["status"]),
                "耗时(s)": f"{s['elapsed_seconds']:.4f}",
            }
            for s in self.steps
        ]
        ev_rows = [
            {
                "公司": d.get("symbol", ""),
                "资料标题": d.get("title", ""),
                "可用时间": str(d.get("available_at", "")),
                "来源链接": d.get("source_url", ""),
            }
            for d in self.matched_documents
        ]
        diag = self.diagnostics or {}
        qp_w = diag.get("weights", {})
        erc_w = diag.get("erc_weights", {})
        tgt_w = diag.get("target_weights", qp_w)
        weight_rows = [
            {
                "股票": sym,
                "最小方差(QP)": f"{qp_w.get(sym, 0.0):.2%}",
                "风险平价(ERC)": f"{erc_w.get(sym, 0.0):.2%}",
                "本次执行目标权重": f"{tgt_w.get(sym, 0.0):.2%}",
            }
            for sym in self.selected_symbols
        ]
        order_rows = [
            {
                "股票": o["symbol"],
                "方向": "买入" if o["side"] == "BUY" else "卖出",
                "模拟份额": o["quantity"],
            }
            for o in self.proposed_orders
        ]
        fill_rows = [
            {
                "成交日期": f["fill_date"],
                "股票": f["symbol"],
                "方向": "买入" if f["side"] == "BUY" else "卖出",
                "模拟份额": f["quantity"],
                "含滑点成交价(USD)": f"{f['price']:.4f}",
                "手续费(USD)": f"{f['fee']:.2f}",
                "成交金额(USD)": f"{f['notional']:.4f}",
            }
            for f in self.fills
        ]
        holdout_rows = []
        hp = diag.get("holdout_performance")
        if isinstance(hp, dict) and hp:
            # hp is column -> {strategy: value}
            strats = list(next(iter(hp.values())).keys())
            for st in strats:
                row = {"策略": st}
                for metric, vals in hp.items():
                    v = vals.get(st)
                    if v is None or (isinstance(v, float) and not math.isfinite(v)):
                        row[metric] = "—"
                    elif metric == "夏普比率":
                        row[metric] = f"{v:.3f}"
                    else:
                        row[metric] = f"{v:.2%}"
                holdout_rows.append(row)

        kkt_val = diag.get("kkt_complementarity_error")
        kkt_str = f"{kkt_val:.2e}" if isinstance(kkt_val, (int, float)) else "—"
        approval_banner = (
            "已获人工显式批准（HIGH_EXPLICIT_APPROVAL），按所见即所得清单完成 SQLite 原子撮合。"
            if self.approved_execution
            else "当前为只读预览报告（未写入 paper.sqlite3 账本）；需在桌面端点击“人工批准并执行撮合”或 CLI 传 --approve 方可执行。"
        )
        html_doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Matrix Workbench · 四层 Agent 审计与演示报告</title>
<style>
body{{font:15px/1.7 system-ui,'PingFang SC','Microsoft YaHei',sans-serif;color:#1e293b;background:#f1f5f9;margin:0}}
main{{max-width:1080px;margin:28px auto;background:#fff;padding:32px;border-radius:12px;box-shadow:0 2px 12px rgba(15,23,42,.06)}}
h1{{font-size:24px;color:#0f172a;border-bottom:2px solid #2563eb;padding-bottom:8px;margin-top:0}}
h2{{font-size:18px;margin-top:28px;color:#1e3a8a}}
.muted{{color:#64748b}}.box{{background:#f8fafc;border-left:4px solid #2563eb;padding:10px 14px;border-radius:4px;margin:12px 0}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid #e2e8f0;overflow-wrap:anywhere;max-width:380px}}
th{{background:#eff6ff;color:#1e3a8a}}@media print{{body{{background:#fff}}main{{margin:0;box-shadow:none;padding:0}}}}
</style></head><body><main>
<p class="muted">MATRIX WORKBENCH · 中国科学院大学《矩阵分析与应用》课程大作业可复查演示报告</p>
<h1>用户需求 → 四层 Agent 工具调用 → 矩阵风控 → 模拟订单</h1>
<div class="box">
<b>研究条件：</b>{escape(self.user_query)}<br>
<b>研究日期 (asof)：</b>{escape(self.asof)} · <b>检索模式：</b>{escape(self.mode)} ({escape(self.jev_op)}) · <b>组合策略：</b>{escape(strat_zh)}<br>
<b>Trace ID：</b>{escape(self.trace_id)} · <b>生成时间 (UTC)：</b>{escape(self.created_at)}
</div>
<p class="muted">{escape(approval_banner)}</p>
<h2>1. 四层 Agent 执行轨迹与风险分级门控</h2>
<div class="scroll">{html_table(step_rows)}</div>
<h2>2. 防穿越筛选依据（仅评估 available_at &lt; 研究日美东日末）</h2>
<div class="scroll">{html_table(ev_rows)}</div>
<h2>3. 矩阵协方差收缩、KKT 残差与权重对照</h2>
<p>有效共同收益率样本：<b>{diag.get('observations', '—')}</b> · 实际收缩系数 α：<b>{diag.get('alpha_used', '—')}</b>（Ledoit-Wolf 最优 α* = <b>{diag.get('ledoit_wolf_alpha', '—')}</b>）· 条件数：<b>{diag.get('condition_before', '—')} → {diag.get('condition_after', '—')}</b> · KKT 互补残差：<b>{kkt_str}</b> · PC1 解释方差：<b>{diag.get('pc1_explained', 0):.2%}</b></p>
<div class="scroll">{html_table(weight_rows)}</div>
<h2>4. 样本外表现对照（仅诊断展示，不参与权重拟合）</h2>
<div class="scroll">{html_table(holdout_rows) if holdout_rows else "<p class='muted'>本次运行未启用样本外对比（可通过 include_holdout=True 开启）。</p>"}</div>
<h2>5. 模拟调仓提案与原子成交明细</h2>
<div class="scroll">{html_table(order_rows)}</div>
<h3>实际成交记录（次日复权开盘价撮合，先卖后买）</h3>
<div class="scroll">{html_table(fill_rows)}</div>
<p class="muted">本报告完全离线自包含，不载入任何外部脚本，亦不导出 API 密钥或访问令牌；完整结构化记录保存在同目录 <a href="trace.json">trace.json</a>。</p>
</main></body></html>"""
        out_path = directory / "report.html"
        out_path.write_text(html_doc, encoding="utf-8")
        return out_path


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
        matched_documents=[
            {k: row.get(k) for k in ("doc_id", "symbol", "title", "available_at", "source_url", "match_score")}
            for row in research_run.matches
        ],
    )
