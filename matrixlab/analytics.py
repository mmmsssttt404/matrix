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
    regularized_eigenvalues: np.ndarray | None = None
    ledoit_wolf_alpha: float = 0.0
    risk_parity_weights: pd.Series | None = None
    kkt_primal_error: float = 0.0
    kkt_dual_violation: float = 0.0
    kkt_complementarity_error: float = 0.0

    @property
    def volatility(self):
        return float(np.sqrt(max(0.0, float(self.weights.to_numpy() @ self.covariance.to_numpy() @ self.weights.to_numpy()))))

    @property
    def regularized_volatility(self):
        return float(np.sqrt(max(0.0, float(self.weights.to_numpy() @ self.regularized.to_numpy() @ self.weights.to_numpy()))))

    @property
    def effective_n(self):
        denom = float(np.sum(self.weights.to_numpy() ** 2))
        return 1.0 / denom if denom > 0 else 0.0


def ledoit_wolf_shrinkage(centered):
    """Exact Ledoit-Wolf (2004, JMVA) analytical optimal shrinkage toward mu*I.

    Scale-invariant with respect to annualization; returns alpha* in [0, 1].
    """
    x = np.asarray(centered, dtype=float)
    t, n = x.shape
    if t < 2 or n < 1:
        return 0.0
    sample = (x.T @ x) / t
    mu = float(np.trace(sample)) / n
    frob_sq = float(np.sum(sample * sample))
    diff = sample - mu * np.eye(n)
    delta_sq = float(np.sum(diff * diff)) / n
    if delta_sq <= 1e-18 * max(frob_sq / n, 1e-30):
        return 1.0
    row_norms_sq = np.sum(x * x, axis=1)
    # Sum_t ||x_t x_t^T - S||_F^2 = Sum_t ||x_t||_2^4 - T ||S||_F^2 >= 0
    beta_bar_sq = max(0.0, (float(np.sum(row_norms_sq ** 2)) - t * frob_sq) / (t * t * n))
    beta_sq = min(beta_bar_sq, delta_sq)
    return float(np.clip(beta_sq / delta_sq, 0.0, 1.0))


def _solve_erc(regularized, symbols):
    """Equal Risk Contribution (Risk Parity) via Spinu (2013) convex log-barrier."""
    sigma = np.asarray(regularized, dtype=float)
    n = len(symbols)
    scale = float(np.trace(sigma)) / n
    mat = sigma / scale
    y0 = np.full(n, 1.0 / np.sqrt(max(float(np.mean(np.diag(mat))), 1e-12)))

    def obj(y):
        return 0.5 * float(y @ mat @ y) - float(np.sum(np.log(y))) / n

    def grad(y):
        return mat @ y - (1.0 / n) / y

    res = minimize(obj, y0, jac=grad, method="L-BFGS-B", bounds=[(1e-9, None)] * n,
                   options={"ftol": 1e-14, "gtol": 1e-10, "maxiter": 1000})
    if not res.success or not np.isfinite(res.x).all() or res.x.sum() <= 0:
        # Fallback to inverse-volatility weighting if barrier fails on degenerate input.
        inv_vol = 1.0 / np.sqrt(np.maximum(np.diag(sigma), 1e-12))
        w = inv_vol / inv_vol.sum()
    else:
        w = np.maximum(res.x, 0.0)
        w /= w.sum()
    return pd.Series(w, index=symbols, name="erc_weight")


def analyze(prices, symbols, asof, lookback=252, alpha=0.05, min_observations=60, use_ledoit_wolf=False):
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
    lw_alpha = ledoit_wolf_shrinkage(centered)
    effective_alpha = lw_alpha if use_ledoit_wolf else float(alpha)
    regularized = (1 - effective_alpha) * covariance + effective_alpha * target * np.eye(len(symbols))
    # Normalize objective scale so SLSQP's tolerance does not stop at equal weights.
    scaled = regularized / target
    n = len(symbols)
    result = minimize(lambda w: float(w @ scaled @ w), np.full(n, 1 / n),
                      jac=lambda w: 2 * scaled @ w, method="SLSQP", bounds=[(0, 1)] * n,
                      constraints={"type": "eq", "fun": lambda w: w.sum() - 1,
                                   "jac": lambda w: np.ones(n)},
                      options={"ftol": 1e-12, "maxiter": 1000})
    if not result.success or abs(result.x.sum() - 1) > 1e-7 or result.x.min() < -1e-8:
        raise DataError("组合优化未收敛：" + str(result.message))
    weights = np.maximum(result.x, 0)
    weights /= weights.sum()
    # KKT verification on min w^T Sigma_alpha w s.t. 1^T w = 1, w >= 0:
    # 2 Sigma_alpha w + lambda * 1 - mu = 0, mu >= 0, mu_i * w_i = 0.
    grad_opt = 2.0 * (regularized @ weights)
    lam_opt = -float(weights @ grad_opt)
    mu_opt = grad_opt + lam_opt
    kkt_primal_error = float(max(abs(weights.sum() - 1.0), max(0.0, -weights.min())))
    kkt_dual_violation = float(max(0.0, -mu_opt.min()))
    kkt_complementarity_error = float(np.max(np.abs(mu_opt * weights)))
    eigenvalues = np.linalg.eigvalsh(covariance)
    regularized_eigenvalues = np.linalg.eigvalsh(regularized)
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
    var_raw = float(weights @ covariance @ weights)
    if not np.isfinite(var_raw) or var_raw <= 0:
        raise DataError("组合波动率为零，无法分解风险贡献。")
    sigma = float(np.sqrt(var_raw))
    marginal = covariance @ weights / sigma
    contributions = pd.Series(weights * marginal, index=symbols, name="risk_contribution")
    risk_share = pd.Series(contributions / sigma, index=symbols, name="risk_share")
    erc_weights = _solve_erc(regularized, symbols)
    try:
        inverse = np.linalg.solve(regularized, np.ones(n))
        denom = float(inverse.sum())
        if not np.isfinite(denom) or abs(denom) <= 1e-12:
            raise np.linalg.LinAlgError("Degenerate closed-form denominator")
        closed_form = inverse / denom
        if not np.isfinite(closed_form).all():
            raise np.linalg.LinAlgError("Non-finite closed-form weights")
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
        alpha=effective_alpha,
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
        regularized_eigenvalues=regularized_eigenvalues,
        ledoit_wolf_alpha=lw_alpha,
        risk_parity_weights=erc_weights,
        kkt_primal_error=kkt_primal_error,
        kkt_dual_violation=kkt_dual_violation,
        kkt_complementarity_error=kkt_complementarity_error,
    )


def shrinkage_path(prices, symbols, asof, lookback=252, alphas=None):
    """Condition number, regularized min eigenvalue, and concentration along shrinkage path."""
    alphas = [0, .05, .1, .2, .3, .5, .75, 1] if alphas is None else list(alphas)
    if not alphas or any(not 0 <= alpha <= 1 for alpha in alphas):
        raise DataError("收缩路径的alpha须在0—1之间。")
    rows = []
    for alpha in alphas:
        result = analyze(prices, symbols, asof, lookback, alpha)
        rows.append({"alpha": alpha,
                     "condition": result.condition_after,
                     "min_eigenvalue": float(result.regularized_eigenvalues.min()),
                     "max_eigenvalue": float(result.regularized_eigenvalues.max()),
                     "volatility": result.volatility,
                     "regularized_volatility": result.regularized_volatility,
                     "max_weight": float(result.weights.max()),
                     "effective_n": result.effective_n})
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


def rolling_holdout_curve(prices, symbols, signal_date, end_date=None, lookback=252,
                          alpha=0.05, rebalance_every=21, cost_bps=15, min_observations=60):
    """Out-of-sample periodic rebalancing with strict next-open execution and turnover cost."""
    symbols = list(dict.fromkeys(symbols))
    if len(symbols) < 2 or rebalance_every < 5 or not 0 <= cost_bps < 10000:
        raise DataError("滚动回测至少需要两只股票，调仓周期不少于5个交易日，成本须为0—10000bp。")
    end = pd.Timestamp(end_date) if end_date is not None else prices.date.max()
    future = prices.loc[(prices.date > pd.Timestamp(signal_date)) & (prices.date <= end) & prices.symbol.isin(symbols)]
    calendar = sorted(future.date.unique())
    if not calendar:
        raise DataError("研究日之后没有可供样本外滚动回测的行情。")
    opens = future.pivot(index="date", columns="symbol", values="open").reindex(index=calendar, columns=symbols)
    closes = future.pivot(index="date", columns="symbol", values="close").reindex(index=calendar, columns=symbols)
    if opens.isna().any().any() or closes.isna().any().any():
        raise DataError("滚动回测区间存在缺失行情，不能自动填充。")
    strategies = ["最小方差(固定α)", "最小方差(Ledoit-Wolf)", "风险平价(ERC)", "等权滚动"]
    cost_rate = cost_bps / 10000.0
    n = len(symbols)
    nav = {name: 1.0 for name in strategies}
    shares = {name: np.zeros(n, dtype=float) for name in strategies}
    turnover = {name: 0.0 for name in strategies}
    rebalance_count = 0
    rows = []
    dates = [pd.Timestamp(signal_date)]
    rows.append(dict(nav))
    for idx, day in enumerate(calendar):
        open_px = opens.loc[day].to_numpy(dtype=float)
        close_px = closes.loc[day].to_numpy(dtype=float)
        if idx % rebalance_every == 0:
            rebalance_count += 1
            asof_day = pd.Timestamp(signal_date) if idx == 0 else pd.Timestamp(calendar[idx - 1])
            fixed = analyze(prices, symbols, asof_day, lookback, alpha, min_observations, use_ledoit_wolf=False)
            lw = analyze(prices, symbols, asof_day, lookback, alpha, min_observations, use_ledoit_wolf=True)
            targets = {
                "最小方差(固定α)": fixed.weights.to_numpy(dtype=float),
                "最小方差(Ledoit-Wolf)": lw.weights.to_numpy(dtype=float),
                "风险平价(ERC)": fixed.risk_parity_weights.to_numpy(dtype=float),
                "等权滚动": np.full(n, 1.0 / n, dtype=float),
            }
            for name in strategies:
                pre_value = nav[name] if idx == 0 else float(shares[name] @ open_px)
                if pre_value <= 0:
                    shares[name] = np.zeros(n, dtype=float)
                    continue
                cur_w = np.zeros(n, dtype=float) if idx == 0 else (shares[name] * open_px) / pre_value
                trade_turnover = 0.5 * float(np.sum(np.abs(targets[name] - cur_w)))
                gross_traded_notional = float(np.sum(np.abs(targets[name] - cur_w))) if idx > 0 else 1.0
                turnover[name] += trade_turnover if idx > 0 else 0.0
                net_value = (pre_value / (1.0 + cost_rate)) if idx == 0 else pre_value * max(0.0, 1.0 - cost_rate * gross_traded_notional)
                shares[name] = (net_value * targets[name]) / open_px
        for name in strategies:
            nav[name] = float(shares[name] @ close_px)
        dates.append(pd.Timestamp(day))
        rows.append(dict(nav))
    curve = pd.DataFrame(rows, index=pd.DatetimeIndex(dates, name="date"))
    years = max(len(calendar) / 252.0, 1e-6)
    summary = pd.DataFrame({
        "调仓次数": [rebalance_count] * len(strategies),
        "累计单边换手": [turnover[s] for s in strategies],
        "年化换手率": [turnover[s] / years for s in strategies],
    }, index=strategies)
    return curve, summary


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
