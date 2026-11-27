# Multi-Agent 交叉核验报告（2026-11-27）

本报告对应大作业共同要求第 4 条：“利用 multi-agent 技术及相关大模型、工具或开源 Skills，对生成的数学结论、参考文献、数据和代码进行核验；对重要修改或关键决策给出简要说明”。

## 1. 核验架构与分工设计

参照课程 `Lec0` 讲授的多 Agent 专业分工原则（Coordinator → Specialized Auditors），我们在初版修改与书稿修订完成后，启动了**两组相互独立的只读对抗式审计子 Agent**，结合真实 Linux 运行时测试（`pytest`、`jevdb==0.1.0`、`PySide6`）与原版教材/课件 PDF 逐页对照，对题目一与题目二开展全量交叉核验：

| 独立核验角色 | 审查范围 | 使用的工具与核验方法 |
|---|---|---|
| **Agent A：代码、防未来函数与安全审计器** (`Code and Security Auditor`) | `matrixlab/` 全部核心模块、`scripts/jev_llm_proxy.py`、`evaluation/evaluate.py`、`docs/report.md`、`docs/tools.md`、`README.md` 与评估结果 JSON | 静态代码追踪、时间截断反例分析、SQL 注入与权限边界审查、表格数值与原始 JSON 逐条交叉核对 |
| **Agent B：数学推导、习题与参考文献核验器** (`Math and Citation Auditor`) | `manuscript/chapter8_eigenvalues_and_psd_revised.md`、`chapter5_6_norms_svd_supplement.md`、`revision_notes.md`、`verify_manuscript_math.py` | 逐行证明漏洞排查、Python 精确有理/复数算术复算全部 10 道习题、直接查阅 `lec9.pdf`/`lec6.pdf`/`lec7.pdf` 与 Carl D. Meyer (2000) 原版 PDF 核对页码与定理编号 |

---

## 2. 题目二代码、数据与安全交叉核验发现与修复闭环（Agent A）

### 2.1 首轮代码审查（改造前基线查出的 5 个原始缺陷）

| 编号 | 原始位置 | 发现的问题 | 修复措施与回归验证 |
|---|---|---|---|
| **B1** | `matrixlab/analytics.py:135` | `shrinkage_path()` 记录的 `min_eigenvalue` 误取未收缩矩阵 $\Sigma$ 特征值，导致整条收缩路径 $\lambda_{\min}$ 恒定不变 | 新增 `regularized_eigenvalues` 字段，改为输出 $\lambda_{\min}(\Sigma_\alpha)$，并增加 `test_shrinkage_path_endpoints` 断言严格单调递增至 $\mathrm{tr}(\Sigma)/N$ |
| **B2** | `matrixlab/research.py:117` | `_keyword_screen()` 仅在过滤后的 `matched` 子集上算 BM25 IDF，导致 AND 模式下所有词 IDF 完全退化相等 | 改为在完整 `eligible` 语料上统计 $N$ 与 $n_t$，新增 `test_bm25_uses_full_corpus_idf_under_and_operator` 回归测试 |
| **B3** | `app.py:242` | `performance(curve).style.format("{:.2%}")` 将无量纲“夏普比率”误格式化为百分比（如 `185.00%`） | 改为按列格式化，夏普比率统一用 `{:.2f}` |
| **B4** | `matrixlab/desktop/pages.py` & `window.py` | 主交付 Qt 桌面端缺少报告所述的 PCA 载荷表、收缩路径、双波动率、滚动回测及历史百科存档菜单 | 升级为三页签 `PortfolioPage`、新增 `archive_history` 菜单、重截高清实测界面图 |
| **B5** | `evaluation/results/both.json` & `acquire.py` | 仓库残留早期全报错结果 `both.json`；并发抓取维基百科触发 HTTP 429/403 | 清理失效 `both.json`；`acquire.py` 改为带规范 User-Agent 的串行限速与指数退避重试 |

### 2.2 独立 Agent A 二轮对抗审计发现与采纳决策

| 严重度 | 发现位置 | Agent A 查出的具体缺陷 | 采纳决策与修复结果 |
|---|---|---|---|
| **高** | `matrixlab/desktop/pages.py:398` | `run_rolling()` 遗漏了 `selection_asof` 防未来函数守卫（用户回拨研究日期时可用未来筛选的股票跑滚动回测），且未校验回调时日期是否已切换 | **采纳并修复**：补充 `day < self.workspace.selection_asof` 阻断守卫，回调校验 `day == self.workspace.asof` |
| **高** | `scripts/jev_llm_proxy.py:98-167` | 本地协议适配代理缺少 Bearer 鉴权、未限制 URL 路径与请求体上限、日志默认写公共 `/tmp/jev_proxy.jsonl` 且 502 透传上游异常文本 | **采纳并修复**：新增 `hmac.compare_digest` Bearer 鉴权、路径白名单 `/v1/chat/completions`、4MB 体积上限、用户私有 `0600` 日志路径与异常脱敏，并更新 `docs/tools.md` 分列说明 |
| **中** | `matrixlab/agent.py:108, 146, 158-167` | (1) `available_symbols` 扫描全量行情未按 `date <= asof` 过滤；(2) `approve_execution=False` 预览时提前实例化 `Broker` 在磁盘生成空 SQLite 库；(3) 未校验已有账本时钟与 `asof` 一致性；(4) 预览轨迹默认附带未来 `holdout_performance` | **采纳并修复**：(1) 严格按 `prices.date <= asof_ts` 过滤股票池；(2) 预览模式改为只读不建库，仅在 `approve_execution=True` 时落盘；(3) 已有账本时钟不匹配直接抛 `DataError`（新增 `test_agent_workflow_rejects_mismatched_broker_clock`）；(4) `include_holdout` 默认 `False` |
| **中** | `matrixlab/analytics.py:64-66, 158-168` | Ledoit-Wolf 中 `delta_sq <= 1e-18` 为绝对阈值，在极小波动率尺度下破坏尺度不变性；极端奇异阵下 `sqrt(var)` 与 `inverse.sum()` 缺少防护 | **采纳并修复**：改用直接差矩阵 Frobenius 平方和与相对阈值 `1e-18 * max(frob_sq/n, 1e-30)`，补全 `var_raw <= 0` 与 `denom` 数值防护 |
| **中** | `matrixlab/research.py:153, 217, 283` | `prune_k` 未做严格 `int` 校验（传字符串会触发未捕获 `TypeError`）；`choices` 缺少条数与长度上限；`_literal` 未拦截 `\x00`；排序缺稳定平局规则 | **采纳并修复**：严格校验 `prune_k` 为整数、`choices` 限 `2–50` 条且每条 $\le 100$ 字符、拦截 `\x00`、排序改为 `mergesort` + `["symbol", "doc_id"]` 平局决胜，补齐回归测试 |
| **中** | `evaluation/evaluate.py:101-130` | `prune_ablation()` 未应用 `--asof` 时间截断且排序未对齐生产 SQL `ORDER BY symbol`；结果 JSON 记录了本机绝对路径 | **采纳并修复**：补齐 `cutoff_utc(asof)` 截断、按 `symbol` 排序、改为相对路径并重跑生成全部最新 JSON |
| **中** | `docs/report.md:155, 180-181` & `docs/runbook.md:96` | (1) `both-deepseek.json` 中实际有冗余命中的是 **14 条**（另 2 条为纯漏选，共 16 条非精确匹配），报告原误写为“16 条冗余”；(2) 需透明披露 `Prune-First` 中 `24/40` 条查询触发回退；(3) Ledoit-Wolf 最大回撤为持平 `-11.06%`；(4) `runbook.md` 残留四舍五入口径 `0.793`（应为 `0.792`） | **全部采纳并精确更正**；同时在 `docs/tools.md` 补齐直接依赖 `beautifulsoup4`（MIT）并同步 `pyproject.toml` 版本至 `0.2.0` |

---

## 3. 题目一数学推导、习题与参考文献核验发现与修复闭环（Agent B）

Agent B 独立复算了全部 10 道课后题、Wilkinson 多项式、Gerschgorin 缩放与真实协方差谱数值，**确认全部计算零算术误差**，同时精准查出以下高价值理论与文献细节并全部完成修正：

| 严重度 | 发现位置 | Agent B 查出的具体缺陷 | 采纳决策与修复结果 |
|---|---|---|---|
| **高（数学严谨性）** | `chapter8` §8.4.1 & `revision_notes.md` M6 | 初稿在修正 `Lec9` p.28 时写了“若某顺序主子式为零，则一般不保证存在无行交换的 $LU$ 分解”——这对一般/不定矩阵成立，但对**精确算术下的半正定矩阵为假**（半正定阵遇零主元时由 $|s_{kj}|^2\le s_{kk}s_{jj}=0$ 必令剩余行列全为零，故仍存在非唯一的非负对角 $A=LDL^T$/$R^TR$，只是浮点计算需完全主元选择防崩溃） | **完全采纳并重修**：精确区分精确算术存在性（Horn & Johnson Cor. 7.2.9）、唯一性/严格正对角失效、以及浮点秩揭示主元分解 $PAP^T=LDL^T$（Golub & Van Loan §4.2.8–4.2.9） |
| **高（文献定位）** | `chapter8` §8.1 & `revision_notes.md` | Gilbert Strang (2019) Part I 节号错位 1 节（特征值实际在 **§I.6**、正定阵在 **§I.7**、SVD 在 **§I.8**、PCA/Eckart–Young 在 **§I.9**） | **全部修正**，所有 Strang (2019) 引文精准对齐原书目录 |
| **中（证明完备性）** | `chapter8` 定理 8.6、8.7、8.8、8.9 & `chapter5_6` | (1) 定理 8.6 需注明次可乘矩阵范数并补全 $\|E\|_2\le\|E\|$ 衔接句；(2) Gerschgorin 缩放例题需明示“实阵复根共轭成对”才可推出孤立圆盘内必为实根；(3) 定理 8.8(3)/8.9 需限定实矩阵 $B, C\in\mathbb{R}^{n\times n}$；(4) `chapter5_6` Eckart–Young Frobenius 证明应直接由 2-范数定理 2 行自洽推出，避免引用未证的 Weyl 奇异值不等式；(5) 条件数界需加 $b\neq 0$、PSD 主子式总数写明 $2^n-1$ | **全部逐条采纳并完善**，使全部 11 项定理证明均无隐藏前提与逻辑跳步 |
| **中（页码与验证覆盖）** | `revision_notes.md` & `verify_manuscript_math.py` | 精确对齐 Meyer (2000) 页码（`p.492–493`、`p.551–553`、`p.417–418`）、补充 Horn & Johnson `Thm. 5.6.12` 与正文 Goodfellow (2016) 引文；`verify_manuscript_math.py` 补齐 5 道证明题（Ex 2/3/4/5/9）的随机数值性质检验并修复 Matplotlib 路径的 `fig1` 坐标轴裁切与 `figures_generated` 列表回报 | **全部采纳并重跑通过** |

---

## 4. 最终验证状态

完成上述全部多 Agent 审查修复后，重新同步并执行全量自动化验证：
- **题目二全量测试（Linux + 真实 `jevdb==0.1.0` + PySide6）**：`44 passed`（0 失败，0 跳过）；
- **题目一数学验算与配图脚本**：`manuscript/verify_manuscript_math.py --prices data/prices.csv --plot` 零报错通过，全部 10 道习题（5 道计算 + 5 道证明性质）与 6 项核心定理验证全部通过，3 张出版级高清配图（`fig1`–`fig3`）已生成并人工目视复核无文字裁切。
