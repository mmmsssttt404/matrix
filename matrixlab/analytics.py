from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .data import DataError


@dataclass
class RiskResult:
    returns: pd.DataFrame
    covariance: pd.DataFrame
    regularized: pd.DataFrame
    weights: pd.Series
    eigenvalues: np.ndarray
    condition_before: float
    condition_after: float
    alpha: float
    excluded_rows: int

    @property
    def volatility(self):
        return float(np.sqrt(self.weights.to_numpy() @ self.covariance.to_numpy() @ self.weights.to_numpy()))


def analyze(prices, symbols, asof, lookback=252, alpha=0.05, min_observations=60):
    symbols = list(dict.fromkeys(symbols))
    if len(symbols) < 2 or not 0 <= alpha <= 1 or lookback < min_observations:
        raise DataError("至少选择两只股票，收缩系数为0—1，回看长度不少于最小样本数。")
    prior = prices.loc[(prices.date <= pd.Timestamp(asof)) & prices.symbol.isin(symbols)]
    wide = prior.pivot(index="date", columns="symbol", values="close").reindex(columns=symbols)
    complete = wide.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    excluded = int(complete.isna().any(axis=1).sum())
    returns = complete.dropna().tail(lookback)
    if len(returns) < min_observations:
        raise DataError(f"共同有效收益率仅{len(returns)}行，至少需要{min_observations}行；不自动填补缺失价格。")
    centered = returns.to_numpy() - returns.to_numpy().mean(axis=0)
    covariance = centered.T @ centered / (len(returns) - 1) * 252
    target = np.trace(covariance) / len(symbols)
    if not np.isfinite(covariance).all() or target <= 1e-16:
        raise DataError("收益率缺乏有效波动，无法估计组合风险。")
    regularized = (1 - alpha) * covariance + alpha * target * np.eye(len(symbols))
    # Normalize objective scale so SLSQP's tolerance does not stop at equal weights.
    scaled = regularized / target
    n = len(symbols)
    result = minimize(lambda w: float(w @ scaled @ w), np.full(n, 1 / n),
                      jac=lambda w: 2 * scaled @ w, method="SLSQP", bounds=[(0, 1)] * n,
                      constraints={"type": "eq", "fun": lambda w: w.sum() - 1,
                                   "jac": lambda w: np.ones(n)},
                      options={"ftol": 1e-11, "maxiter": 1000})
    if not result.success or abs(result.x.sum() - 1) > 1e-7 or result.x.min() < -1e-8:
        raise DataError("组合优化未收敛：" + str(result.message))
    weights = np.maximum(result.x, 0)
    weights /= weights.sum()
    return RiskResult(returns, pd.DataFrame(covariance, index=symbols, columns=symbols),
                      pd.DataFrame(regularized, index=symbols, columns=symbols),
                      pd.Series(weights, index=symbols, name="weight"),
                      np.linalg.eigvalsh(covariance), float(np.linalg.cond(covariance)),
                      float(np.linalg.cond(regularized)), alpha, excluded)


def holdout_curve(prices, weights, signal_date, end_date=None, cost_bps=15):
    """Buy once at the next session's adjusted open; then hold drifting weights."""
    if not np.isfinite(cost_bps) or not 0 <= cost_bps < 10000:
        raise DataError("成本须为0—10000bp之间的有限数。")
    if (weights < 0).any() or not np.isclose(weights.sum(), 1):
        raise DataError("权重须非负且和为1。")
    end = pd.Timestamp(end_date) if end_date is not None else prices.date.max()
    future = prices.loc[(prices.date > pd.Timestamp(signal_date)) & (prices.date <= end) & prices.symbol.isin(weights.index)]
    calendar = sorted(prices.loc[(prices.date > pd.Timestamp(signal_date)) & (prices.date <= end), "date"].unique())
    if not calendar:
        raise DataError("研究日之后没有可供样本外检验的行情。")
    first = pd.Timestamp(calendar[0])
    entry = future.loc[future.date.eq(first)].set_index("symbol").reindex(weights.index)
    if entry.open.isna().any():
        raise DataError("下一交易日有股票缺少开盘价，不能用更晚价格代替。")
    closes = future.pivot(index="date", columns="symbol", values="close").reindex(index=calendar, columns=weights.index)
    if closes.isna().any().any():
        raise DataError("样本外持仓期间有缺失行情，不能自动填充估值。")
    relatives = closes.divide(entry.open, axis=1)
    invested = 1 / (1 + cost_bps / 10000)
    curve = pd.DataFrame({"最小方差组合": relatives @ weights * invested,
                          "等权组合": relatives.mean(axis=1) * invested})
    curve.index.name = "date"
    initial = pd.DataFrame({c: [1.0] for c in curve}, index=[pd.Timestamp(signal_date)])
    initial.index.name = "date"
    return pd.concat([initial, curve])


def performance(curve):
    drawdown = curve.divide(curve.cummax()) - 1
    return pd.DataFrame({"累计收益": curve.iloc[-1] / curve.iloc[0] - 1,
                         "最大回撤": drawdown.min()})
