import numpy as np
import pandas as pd
import pytest

from matrixlab.analytics import analyze, holdout_curve, performance, shrinkage_path
from matrixlab.data import DataError, validate_prices


def test_gram_covariance_and_feasible_minimum(prices):
    day = prices.date.unique()[120]
    result = analyze(prices, ["AAA", "BBB", "CCC"], day)
    manual = np.cov(result.returns.to_numpy(), rowvar=False, ddof=1) * 252
    np.testing.assert_allclose(result.covariance, manual)
    assert result.eigenvalues.min() >= -1e-10
    assert result.weights.sum() == pytest.approx(1)
    assert (result.weights >= 0).all()
    equal = np.full(3, 1 / 3)
    weights = result.weights.to_numpy()
    reg = result.regularized.to_numpy()
    assert weights @ reg @ weights <= equal @ reg @ equal + 1e-9


def test_pca_and_risk_contribution_decomposition(prices):
    day = prices.date.unique()[120]
    result = analyze(prices, ["AAA", "BBB", "CCC"], day)
    assert result.positive_definite
    assert result.pca_loadings.shape == (3, 3)
    assert result.pca_eigenvalues.sum() == pytest.approx(3)
    assert result.explained_variance.sum() == pytest.approx(1)
    np.testing.assert_allclose(result.pca_loadings.to_numpy().T @ result.pca_loadings.to_numpy(),
                               np.eye(3), atol=1e-8)
    assert result.risk_contributions.sum() == pytest.approx(result.volatility)
    assert result.risk_share.sum() == pytest.approx(1)


def test_closed_form_solution_matches_qp_when_long_only(prices):
    day = prices.date.unique()[120]
    result = analyze(prices, ["AAA", "BBB", "CCC"], day, alpha=.5)
    if result.closed_form_feasible:
        np.testing.assert_allclose(result.weights, result.closed_form_weights, atol=1e-4)
        assert result.closed_form_gap == pytest.approx(0, abs=1e-8)
    else:
        assert result.closed_form_weights.min() < 0
        assert result.closed_form_gap <= 1e-8


def test_shrinkage_path_endpoints(prices):
    day = prices.date.unique()[120]
    path = shrinkage_path(prices, ["AAA", "BBB", "CCC"], day, alphas=[0, 1])
    unshrunk = analyze(prices, ["AAA", "BBB", "CCC"], day, alpha=0)
    assert path.loc[0, "condition"] == pytest.approx(unshrunk.condition_after)
    assert path.loc[1, "condition"] == pytest.approx(1)
    equal = analyze(prices, ["AAA", "BBB", "CCC"], day, alpha=1).weights
    np.testing.assert_allclose(equal, np.full(3, 1 / 3), atol=1e-6)


def test_performance_reports_annualized_metrics():
    curve = pd.DataFrame({"portfolio": [1, 1.1, 1.21]})
    result = performance(curve)
    assert result.loc["portfolio", "累计收益"] == pytest.approx(.21)
    assert result.loc["portfolio", "最大回撤"] == pytest.approx(0)
    assert result.loc["portfolio", "年化收益"] == pytest.approx(1.21 ** (252 / 2) - 1)
    assert result.loc["portfolio", "夏普比率"] > 0


def test_future_prices_do_not_change_fit(prices):
    day = prices.date.unique()[120]
    expected = analyze(prices, ["AAA", "BBB", "CCC"], day)
    changed = prices.copy()
    changed.loc[changed.date > day, ["open", "high", "low", "close"]] *= 8
    actual = analyze(changed, ["AAA", "BBB", "CCC"], day)
    np.testing.assert_allclose(expected.weights, actual.weights)
    np.testing.assert_allclose(expected.covariance, actual.covariance)


def test_missing_quotes_not_forward_filled(prices):
    day = prices.date.unique()[120]
    sparse = prices.loc[~((prices.symbol == "BBB") & (prices.date <= day))]
    with pytest.raises(DataError, match="共同有效"):
        analyze(sparse, ["AAA", "BBB"], day)


def test_holdout_uses_next_open_not_previous_close(prices):
    day = prices.date.unique()[120]
    weights = pd.Series({"AAA": .5, "BBB": .5})
    curve = holdout_curve(prices, weights, day, cost_bps=0)
    entry = prices.loc[prices.date.eq(curve.index[1])].set_index("symbol")
    assert curve.iloc[0, 0] == 1
    expected = (entry.loc[weights.index, "close"] / entry.loc[weights.index, "open"]).mean()
    assert curve.iloc[1, 0] == pytest.approx(expected)
    assert curve.index[1] > day


@pytest.mark.parametrize("mutation", ["duplicate", "negative", "infinite", "basis"])
def test_price_contract_rejects_bad_inputs(prices, mutation):
    frame = prices.copy()
    if mutation == "duplicate":
        frame = pd.concat([frame, frame.iloc[:1]])
    elif mutation == "negative":
        frame.loc[0, "close"] = -1
    elif mutation == "infinite":
        frame.loc[0, "open"] = np.inf
    else:
        frame.loc[0, "price_basis"] = "unadjusted"
    with pytest.raises(DataError):
        validate_prices(frame)
