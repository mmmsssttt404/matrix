# 成员贡献记录

本项目由 **5 人小组**协作完成，由组长**吕云迪**负责统筹与最终提交。分工遵循课程大作业“3～5 人一组、明确职责边界、结合 multi-agent 核验并保留独立判断证据”的要求。

## 1. 组内分工与主要贡献表

| 成员 | 角色 | 主要负责模块 / 文件 / 提交 | 独立核验、关键决策与修正证据 | 报告与演示贡献 | 个人自述（文字版） |
|---|---|---|---|---|---|
| **吕云迪** | **组长**（`mmmsssttt404`） | 系统总体架构、Qt 原生四大桌面工作台（`matrixlab/desktop/`）、SQLite 原子模拟交易账本（`matrixlab/trading.py`）、四层 Agentic 编排与离线 HTML 审计报告（`matrixlab/agent.py`、`skills/`）、Ledoit-Wolf / Spinu ERC / KKT / 滚动回测引擎（`matrixlab/analytics.py`）、CI 与 Windows 打包发布（`packaging/`、`.github/workflows/`）以及双题整合 | 独立核验 JEVDB `0.1.0` 与 Palimpzest 架构差异；主导多 Agent 交叉审计与工程加固，修复收缩路径 $\lambda_{\min}$、全语料 BM25 IDF、夏普格式、全市场日历对齐、桌面端异步代际防串改、Agent 预览零落盘与所见即所得审批等全部缺陷 | 负责总报告架构、四大工作台演示、最终打包与 GitHub Release 发布 | 见 [member-self-statements.md](member-self-statements.md) 第一节 |
| **徐瑞** | 组员（`xuruiz`） | 40 条人工标注评估集（`evaluation/documents.csv`、`labels.csv`、`evaluate.py`）、AND/OR + BM25 检索基线、DeepSeek JSON Schema 兼容适配层（`scripts/jev_llm_proxy.py`）、PCA/风险贡献/闭式解诊断及二轮项目报告（PR #2 `f465c6c`） | 完成 WSL2 Ubuntu 24.04 下 `jevdb==0.1.0` 加载验证，定位 Typesafe `HTTP 451` 地区限制与 DeepSeek `json_schema` `HTTP 400` 协议不兼容，完成 40 条真实语义查询评估与 `Prune-First (K=3)` 消融误差分析（`docs/verification/jevdb-smoke-2026-11-25.md`） | 负责评估体系设计、误差分析与总报告第 4–5 节主体撰写 | 见 [member-self-statements.md](member-self-statements.md) 第二节 |
| **闫涛** | 组员 | 题目一《矩阵分析》第八章（`Lec9`）书稿修订稿核心推导（`manuscript/chapter8_eigenvalues_and_psd_revised.md` §8.1–8.3：特征系统、Gerschgorin 缩放、PageRank 幂迭代、Schur 酉三角化、Rayleigh–Ritz / Courant–Fischer / Weyl 补全） | 逐页比对 `lec9.pdf` 全 32 页与 Carl D. Meyer (2000) 第 7 章原书 PDF，定位 `Lec9` 第 24 页漏写核心公式及 8 页 10 处勘误，整理 32 页逐页体检总览表并复核 Strang (2019) 与 Horn & Johnson (2013) 定理引用 | 负责题目一第八章理论证明润色与修改说明整理 | 见 [member-self-statements.md](member-self-statements.md) 第三节 |
| **吴昀泽** | 组员 | 题目一第八章 §8.4–8.5（正定/半正定辨析、$3\times 3$ 全整数 Cholesky/$LDL^T$ 例、Sylvester 惯性定律、美股协方差实证与全部 10 道习题）、第五/六章 SVD 联动专题（`manuscript/chapter5_6_norms_svd_supplement.md`）及验算绘图脚本（`manuscript/verify_manuscript_math.py`） | 构造 $\mathrm{diag}(0,-1)$ 与 $\mathrm{diag}(1,0)$ 双反例，厘清奇异半正定阵精确 $LDL^T$/$R^TR$ 存在性与浮点主元分解边界；实证 12 股收益率矩阵 SVD（$\kappa_2(X)^2=\kappa_2(\Sigma)$）；运行 `verify_manuscript_math.py` 完成全部 10 题与 4 张配图校验 | 负责题目一习题精解、4 张高清配图与数学验算交付 | 见 [member-self-statements.md](member-self-statements.md) 第四节 |
| **李晨** | 组员 | 开源 Skills 库调研与许可安全审计（`docs/tools.md`、`THIRD_PARTY_NOTICES.md`）、防未来函数与工程加固回归测试（`tests/test_trading.py`、`tests/test_agent.py`、`tests/test_hardening_and_reports.py`）、运行手册与 Windows 启动脚本（`docs/runbook.md`、`docs/windows.md`、`scripts/start-windows.ps1`） | 梳理 JEVDB/DuckDB/PySide6/yfinance/Wikipedia/OpenBB 许可与数据再分发边界；复核严格时区/NaT 校验、远程证据防篡改、模拟交易原子回滚、时钟单调性、幂等请求号与 `Prune-First` 消融可复现性 | 负责工具与许可审计章节、运行手册及演示材料校对 | 见 [member-self-statements.md](member-self-statements.md) 第五节 |

## 2. AI 工具辅助披露与 Multi-Agent 核验摘要

- **开发与写作辅助**：项目开发与书稿修订过程中使用了大模型编程助手、Context7 接口检索及 Python 数值验算工具辅助生成初稿；所有数学推导、参考文献页码、代码逻辑与测试边界均经小组成员独立复核及自动化测试验证。
- **真实语义模型评估验证**：已完成 40 条人工标注查询的真实 DeepSeek 兼容端点 JEVDB 评估与 `Prune-First` 两阶段剪枝消融，完整证据见 [docs/verification/jevdb-smoke-2026-11-25.md](verification/jevdb-smoke-2026-11-25.md) 与 [evaluation/results/prune-ablation.json](../evaluation/results/prune-ablation.json)。
- **Multi-Agent 交叉核验记录**：已围绕（1）代码、防未来函数与安全审计、（2）交易账务与权限边界、（3）题目一数学推导、课件勘误与参考文献核验开展独立双 Agent 对抗审查，全部发现、采纳理由与闭环修复记录见 [docs/verification/multi-agent-audit-2026-11-27.md](verification/multi-agent-audit-2026-11-27.md)。
