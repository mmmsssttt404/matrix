import json

import pytest

from matrixlab.agent import RISK_HIGH, run_workflow
from matrixlab.config import Settings
from matrixlab.trading import Broker


def test_agent_workflow_blocks_high_risk_execution_without_approval(prices, documents, tmp_path):
    day = str(prices.date.unique()[-30].date())
    broker_path = tmp_path / "paper.sqlite3"
    settings = Settings(tmp_path, "jev", "", "")
    trace = run_workflow(
        prices, documents, "cloud", day, settings,
        mode="keyword", operator="any", use_ledoit_wolf=True,
        broker_path=broker_path, approve_execution=False,
    )
    assert trace.selected_symbols == ["AAA", "BBB"]
    assert trace.approved_execution is False
    assert trace.fills == []
    assert trace.proposed_orders
    assert not broker_path.exists()
    assert trace.diagnostics["holdout_performance"] is None
    assert trace.steps[-1]["risk_tier"] == RISK_HIGH
    assert trace.steps[-1]["status"] == "blocked_pending_human_approval"
    saved = trace.save(tmp_path / "traces")
    assert json.loads(saved.read_text(encoding="utf-8"))["trace_id"] == trace.trace_id


def test_agent_workflow_executes_atomically_with_explicit_approval(prices, documents, tmp_path):
    day = str(prices.date.unique()[-30].date())
    broker_path = tmp_path / "paper.sqlite3"
    settings = Settings(tmp_path, "jev", "", "")
    trace = run_workflow(
        prices, documents, "cloud", day, settings,
        mode="keyword", operator="any", use_ledoit_wolf=True,
        broker_path=broker_path, approve_execution=True,
    )
    assert trace.approved_execution is True
    assert len(trace.fills) >= 1
    assert Broker(broker_path).exists()
    assert trace.diagnostics["kkt_complementarity_error"] < 1e-6
    assert 0.0 <= trace.diagnostics["ledoit_wolf_alpha"] <= 1.0
    assert trace.steps[-1]["status"] == "executed"


def test_agent_workflow_rejects_mismatched_broker_clock(prices, documents, tmp_path):
    from matrixlab.data import DataError

    day1 = str(prices.date.unique()[-30].date())
    day2 = str(prices.date.unique()[-25].date())
    broker_path = tmp_path / "paper.sqlite3"
    Broker(broker_path).initialize(100000.0, day2)
    settings = Settings(tmp_path, "jev", "", "")
    with pytest.raises(DataError, match="时钟"):
        run_workflow(
            prices, documents, "cloud", day1, settings,
            mode="keyword", operator="any", broker_path=broker_path, approve_execution=False,
        )
