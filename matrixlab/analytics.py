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
    correlation: pd.DataFrame | None = None
    pca_eigenvalues: np.ndarray | None = None
    pca_loadings: pd.DataFrame | None = None
    explained_variance: np.ndarray | None = None
    risk_contributions: pd.Series | None = None
    risk_share: pd.Series | None = None
    closed_form_weights: pd.Series | None = None
    closed_form_feasible: bool = False
    closed_form_gap: float = 0.0
    positive_definite: bool = False

    @property
    def volatility(self):
        return float(np.sqrt(self.weights.to_numpy() @ self.covariance.to_numpy() @ self.weights.to_numpy()))

    @property
    def regularized_volatility(self):
        return float(np.sqrt(self.weights.to_numpy() @ self.regularized.to_numpy() @ self.weights.to_numpy()))


def analyze(prices, symbols, asof, lookback=252, alpha=0.05, min_observations=60):
    symbols = list(dict.fromkeys(symbols))
    if len(symbols) < 2 or not 0 <= alpha <= 1 or lookback < min_observations:
        raise DataError("至少选择两只股票，收缩系数为0—1，回看长度不少于最小样本数。")
    prior = prices.loc[(prices.date <= pd.Timestamp(asof)) & prices.symbol.isin(symbols)]
    wide = prior.pivot(index="date", columns="symbol", values="close").reindex(columns=symbols)
    complete = wide.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    valid = complete.dropna()
    if len(valid) < min_observations:
        raise DataError(f"共同有效收益率仅{len(valid)}行，至少需要{min_observations}行；不自动填补缺失价格。")
    returns = valid.tail(lookback)
    window = complete.loc[complete.index >= returns.index[0]]
    excluded = int(window.isna().any(axis=1).sum())
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
    eigenvalues = np.linalg.eigvalsh(covariance)
    positive_definite = bool(eigenvalues.min() > 0)
    correlation = returns.corr()
    if not np.isfinite(correlation.to_numpy()).all():
        raise DataError("相关系数矩阵含缺失值，无法做PCA。")
    pca_eigenvalues, pca_vectors = np.linalg.eigh(correlation.to_numpy())
    order = np.argsort(pca_eigenvalues)[::-1]
    pca_eigenvalues = np.clip(pca_eigenvalues[order], 0, None)
    pca_vectors = pca_vectors[:, order]
    for column in range(pca_vectors.shape[1]):
        if pca_vectors[np.argmax(np.abs(pca_vectors[:, column])), column] < 0:
            pca_vectors[:, column] *= -1
    explained = pca_eigenvalues / pca_eigenvalues.sum()
    pca_loadings = pd.DataFrame(pca_vectors, index=symbols,
                                columns=[f"PC{i + 1}" for i in range(n)])
    sigma = float(np.sqrt(weights @ covariance @ weights))
    if sigma <= 0:
        raise DataError("组合波动率为零，无法分解风险贡献。")
    marginal = covariance @ weights / sigma
    contributions = pd.Series(weights * marginal, index=symbols, name="risk_contribution")
    risk_share = pd.Series(contributions / sigma, index=symbols, name="risk_share")
    try:
        inverse = np.linalg.solve(regularized, np.ones(n))
        closed_form = inverse / inverse.sum()
        closed_form_feasible = bool((closed_form >= -1e-8).all())
        closed_form_gap = float(closed_form @ regularized @ closed_form - weights @ regularized @ weights)
    except np.linalg.LinAlgError:
        closed_form = np.full(n, np.nan)
        closed_form_feasible = False
        closed_form_gap = float("nan")
    return RiskResult(
        returns=returns,
        covariance=pd.DataFrame(covariance, index=symbols, columns=symbols),
        regularized=pd.DataFrame(regularized, index=symbols, columns=symbols),
        weights=pd.Series(weights, index=symbols, name="weight"),
        eigenvalues=eigenvalues,
        condition_before=float(np.linalg.cond(covariance)),
        condition_after=float(np.linalg.cond(regularized)),
        alpha=alpha,
        excluded_rows=excluded,
        correlation=correlation,
        pca_eigenvalues=pca_eigenvalues,
        pca_loadings=pca_loadings,
        explained_variance=explained,
        risk_contributions=contributions,
        risk_share=risk_share,
        closed_form_weights=pd.Series(closed_form, index=symbols, name="closed_form_weight"),
        closed_form_feasible=closed_form_feasible,
        closed_form_gap=closed_form_gap,
        positive_definite=positive_definite,
    )


def shrinkage_path(prices, symbols, asof, lookback=252, alphas=None):
    """Condition number and weight concentration along the shrinkage path."""
    alphas = [0, .05, .1, .2, .3, .5, .75, 1] if alphas is None else list(alphas)
    if not alphas or any(not 0 <= alpha <= 1 for alpha in alphas):
        raise DataError("收缩路径的alpha须在0—1之间。")
    rows = []
    for alpha in alphas:
        result = analyze(prices, symbols, asof, lookback, alpha)
        rows.append({"alpha": alpha,
                     "condition": result.condition_after,
                     "min_eigenvalue": float(result.eigenvalues.min()),
                     "volatility": result.volatility,
                     "max_weight": float(result.weights.max())})
    return pd.DataFrame(rows)


def holdout_curve(prices, weights, signal_date, end_date=None, cost_bps=15):
    """Buy once at the next session's adjusted open; then hold drifting weights."""
    if not np.isfinite(cost_bps) or not 0 <= cost_bps < 10000:
        raise DataError("成本须为0—10000bp之间的有限数。")
    if (weights < 0).any() or not np.isclose(weights.sum(), 1):
        raise DataError("权重须非负且和为1。")
    end = pd.Timestamp(end_date) if end_date is not None else prices.date.max()
    future = prices.loc[(prices.date > pd.Timestamp(signal_date)) & (prices.date <= end) & prices.symbol.isin(weights.index)]
    calendar = sorted(future.date.unique())
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
    if len(curve) < 2:
        raise DataError("样本外曲线至少需要两行才能计算绩效。")
    drawdown = curve.divide(curve.cummax()) - 1
    growth = curve.iloc[-1] / curve.iloc[0] - 1
    periods = len(curve) - 1
    annual = growth.apply(lambda value: (1 + value) ** (252 / periods) - 1 if 1 + value > 0 else np.nan)
    daily = curve.pct_change().dropna(how="all")
    volatility = daily.std(ddof=1) * np.sqrt(252)
    sharpe = annual / volatility.replace(0, np.nan)
    return pd.DataFrame({"累计收益": growth, "最大回撤": drawdown.min(),
                         "年化收益": annual, "年化波动率": volatility, "夏普比率": sharpe})
