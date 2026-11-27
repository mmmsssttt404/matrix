---
name: matrix-portfolio-risk
description: Matrix-analysis portfolio risk engine computing Gram covariance, Ledoit-Wolf shrinkage, long-only QP with KKT residual checks, Spinu convex Equal Risk Contribution (ERC), correlation PCA, and rolling out-of-sample backtests.
---

# Matrix Portfolio Risk Skill

## 1. 职责与风险等级
- **所属层级**：Action / Analytical Computation（确定性数值分析层）
- **风险等级**：`LOW_AUTO`（纯内存线性代数与凸优化计算，无外部副作用）

## 2. 工具契约（输入 → 输出）
- **入口**：`matrixlab.analytics.analyze`、`shrinkage_path`、`holdout_curve`、`rolling_holdout_curve`
- **输入**：
  - `prices`: 经 `validate_prices` 校验的 `total_return_adjusted` 日线行情
  - `symbols`: 不少于 2 只候选股票代码
  - `asof`: 拟合截止日期（严格仅用 `date <= asof` 的历史收盘价，杜绝未来函数）
  - `lookback`: 共同有效收益率样本条数（默认 252，至少 60，不向前填补缺失值）
  - `alpha` / `use_ledoit_wolf`: 手工收缩系数或 Ledoit-Wolf (2004) 解析最优收缩系数 $\alpha^*$
- **输出**：`RiskResult`（含 $\Sigma$、$\Sigma_\alpha$、$\kappa(\Sigma)\to\kappa(\Sigma_\alpha)$、特征值谱、PCA 解释方差与载荷、最小方差权重、无约束闭式解对照、KKT 残差、ERC 风险平价权重、边际/成分风险贡献分解）

## 3. 依赖、权限与安全边界
- **依赖**：`numpy`、`scipy`、`pandas`（均为 BSD-3-Clause 许可）
- **权限**：只读本地行情表，纯确定性数值计算，无网络与账本写权限
- **数学不变量校验**：
  - 样本协方差矩阵对称半正定（Gram 构造 $\Sigma = \frac{252}{T-1}X^TX$）；
  - 优化权重满足 $\sum_i w_i = 1, w_i \ge 0$ 且 KKT 互补松弛残差 $\max_i |\mu_i w_i| < 10^{-6}$；
  - 风险贡献满足欧拉分解 $\sum_i \mathrm{CTR}_i = \sigma_p$。
