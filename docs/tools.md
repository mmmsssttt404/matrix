# 工具、开源 Skills 调研、职责、权限与许可审计

本文档对应大作业要求第 4 节 3(b)：“调研并选用合适的开源 Skills 或工具，说明各组件的职责、输入输出、依赖与权限，检查其来源、许可和潜在风险”。

## 1. 开源 Skills 库与外部生态调研选型

在系统设计阶段，我们调研了语义数据库、金融行情/财报数据、开发核查 Skills 与桌面交易界面四类开源组件，并按**来源可信度、开源许可兼容性、最小权限原则与防未来函数能力**进行筛选：

| 候选开源项目 / Skill | 类别 | 来源仓库 / 主页 | 开源许可 | 调研结论 | 选用或弃用理由与风险评估 |
|---|---|---|---|---|---|
| **PDAIS/JEVDB (0.1.0)** | 语义数据库扩展 | [github.com/PDAIS/JEVDB](https://github.com/PDAIS/JEVDB) | MIT | **核心选用** | 题目论文官方发布包；提供 `jev_holds`/`jev_probability`/`jev_choose`/`jev_score`/`jev_keys_overlap` 五大语义 SQL 算子。风险：仅提供 Linux x86-64 预编译轮子，默认 Typesafe 后端受地区限制（HTTP 451），故需配合 Linux 网关与本地协议适配层。 |
| **Palimpzest** | 语义数据处理框架 | [github.com/mitdbg/palimpzest](https://github.com/mitdbg/palimpzest) | MIT | **调研后未集成（仅对照）** | 题面描述 JEVDB 基于 Palimpzest，但独立核验论文 `arXiv:2610.02046v1` 与作者仓库后发现，JEVDB 实际基于 DuckDB 实现，Palimpzest 是论文中的对照基线系统；直接安装整套 Palimpzest 会引入沉重冗余依赖。 |
| **Context7 (MCP / Skill)** | 开发期文档核查 Skill | [github.com/upstash/context7](https://github.com/upstash/context7) | MIT | **开发期选用** | 仅用于开发阶段核查 DuckDB/PySide6/SciPy/Streamlit 版本接口，不进入运行时依赖，无生产数据外泄风险。 |
| **yfinance / Yahoo Chart API** | 美股历史行情与简介 | [github.com/ranaroussi/yfinance](https://github.com/ranaroussi/yfinance) | Apache-2.0（代码） | **审慎选用（仅本地拉取）** | 免费获取总回报复权日线。风险：代码许可**不授予行情数据再分发权**，且 Yahoo 历史数据可能事后修订、公司简介无历史时间戳；因此仓库不提交原始行情全集，且强制将当前简介 `available_at` 设为拉取时刻，禁止回溯使用。 |
| **Wikipedia MediaWiki Revision API** | 历史文本归档 | [en.wikipedia.org/w/api.php](https://en.wikipedia.org/w/api.php) | CC BY-SA 4.0（文本） | **选用（加限速重试）** | 支持按 `rvstart` 精确抓取 `2024-12-31` 之前的历史版本 ID（`oldid`），可有效避免历史选股引入未来文本。风险：并发抓取易触发 HTTP 429/403，已在 `acquire.py` 改为带规范 User-Agent 的串行限速与指数退避重试；保留 `source_url` 署名链接。 |
| **OpenBB / AKShare / 第三方金融 Skills** | 综合金融数据工具包 | [github.com/OpenBB-finance/OpenBB](https://github.com/OpenBB-finance/OpenBB) / [akfamily/akshare](https://github.com/akfamily/akshare) | AGPL-3.0 / MIT | **调研后弃用** | OpenBB 核心采用强传染性 AGPL-3.0 许可且依赖树庞大；第三方社区交易 Skills 常隐含无审批下单或外部未审计脚本执行风险，不符合课程原型“最小依赖 + 确定性风控”要求。 |
| **vn.py / pyqtgraph（UI 参考）** | 桌面交易布局与绘图 | [vnpy/vnpy](https://github.com/vnpy/vnpy) / [pyqtgraph](https://github.com/pyqtgraph/pyqtgraph) | MIT / MIT | **借鉴布局 + 选用绘图库** | 仅借鉴 vn.py 多面板联动排布思想（不引入其交易引擎），基于 pyqtgraph 改写 `QPicture` 缓存 K 线图，全部署名保留在 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。 |

## 2. 本项目标准化 Agent Skills 与工具契约

参照课程 `Lec0` 讲授的 **AI Agent 四层概念架构**（Preamble/Rules、Reasoning/Planning、Retrieval/Context、Action/Execution）与**人工风控分级原则**（Low risk → automate，Medium risk → confirmation，High risk → explicit approval），本项目将核心能力封装为三个自包含、可审计的标准化 Skills（位于 [skills/](../skills/)），并由 [matrixlab/agent.py](../matrixlab/agent.py) 统一编排并输出 JSON 执行轨迹：

| Skill / 工具入口 | 所属层级 | 风险等级 | 输入 → 输出 | 依赖与权限边界 | 潜在风险与缓解措施 |
|---|---|---|---|---|---|
| `skills/matrix-stock-research` (`matrixlab.research.screen`) | Retrieval / Context | `LOW_AUTO` | `(documents, query, asof, mode, jev_op, threshold, prune_k)` → `ResearchRun` JSON | 依赖 JEVDB/DuckDB/Arrow；只读本地 `documents.csv` 与环境变量凭证，仅写 `research_runs/` | **SQL 注入**：全部条件经 `_literal()` 转义为字面量；**Prompt Injection**：资料文本作为不可信数据，不能改变权限；**语义造假**：无密钥明确报 `ResearchUnavailable`。 |
| `skills/matrix-portfolio-risk` (`matrixlab.analytics.analyze`, `rolling_holdout_curve`) | Action / Analytical | `LOW_AUTO` | `(prices, symbols, asof, lookback, alpha / use_ledoit_wolf)` → `RiskResult`（权重、PCA、KKT、ERC、回测） | 依赖 NumPy/SciPy/pandas；纯内存只读计算，无网络与写库权限 | **未来函数**：严格过滤 `date <= asof`，样本外从次日开盘入场；**缺失值伪造**：不向前填充，共同有效观测不足 60 行直接报错。 |
| `skills/matrix-paper-broker` (`matrixlab.trading.rebalance_orders`, `Broker.execute`) | Action / Execution | `MEDIUM_CONFIRM`（提案）/ `HIGH_EXPLICIT_APPROVAL`（成交） | `(orders, signal_date, prices, request_id)` → SQLite 成交记录与权益快照 | 仅依赖 Python 标准库 `sqlite3`/`decimal`；仅读写本地 `paper.sqlite3`，无真实券商权限 | **误下单/重复成交**：Agent 模式下未传 `approve_execution=True` 严禁写库；单批次使用 `BEGIN IMMEDIATE` 事务，先卖后买，任意异常整批回滚；`request_id` 幂等防重放。 |
| `matrixlab.acquire` (`fetch_dataset`, `archive_documents`) | Data Ingestion | `LOW_AUTO` | `(symbols, start, end / asof)` → `prices.csv`、`documents.csv`、`manifest.json` | 依赖 Yahoo/Wikipedia API、BeautifulSoup；外网只读 + 原子写入本地 `data/` | 已有 `paper.sqlite3` 账本时禁止覆盖行情基准；拉取失败显式记入 manifest，绝不生成替代数据。 |
| `matrixlab.service` | Remote Gateway | `LOW_AUTO` | HTTP JSON → JEVDB 远程筛选 | 标准库 `http.server`；HMAC Bearer Token 鉴权，仅开放 `/health` 与 `/research` | 远程非回环地址强制要求 HTTPS；网关**不暴露任何交易接口**，请求体限制 $\le 4\text{MB}$、文档 $\le 200$ 条。 |
| `scripts/jev_llm_proxy.py` | Protocol Adapter | `LOW_AUTO` | OpenAI `json_schema` → 上游 `json_object` 校验重试 | 仅绑定 `127.0.0.1` 回环口；Bearer Token 鉴权（`PROXY_TOKEN` 或本地密钥），仅开放 `/health` 与 `/v1/chat/completions` | 仅做格式转换与 schema 校验，请求体限制 $\le 4\text{MB}$，日志写入用户私有缓存目录（`0600` 权限），异常响应脱敏。 |

## 3. 直接软件依赖与开源许可清单

完整精确版本锁定在 [requirements.lock](../requirements.lock)、[requirements-desktop.lock](../requirements-desktop.lock) 与 [requirements-windows.lock](../requirements-windows.lock)。JEVDB `0.1.0` 强绑定 `duckdb==1.4.3`，并通过 PyArrow 桥接避免 pandas 3 字符串类型兼容问题。

| 直接依赖 | 上游项目 | 开源许可 |
|---|---|---|
| JEVDB | [PDAIS/JEVDB](https://github.com/PDAIS/JEVDB) | MIT |
| DuckDB | [duckdb/duckdb](https://github.com/duckdb/duckdb) | MIT |
| NumPy、pandas、SciPy | [NumPy](https://github.com/numpy/numpy)、[pandas](https://github.com/pandas-dev/pandas)、[SciPy](https://github.com/scipy/scipy) | BSD-3-Clause |
| Streamlit、PyArrow、yfinance | [Streamlit](https://github.com/streamlit/streamlit)、[Arrow](https://github.com/apache/arrow)、[yfinance](https://github.com/ranaroussi/yfinance) | Apache-2.0 |
| Plotly、pyqtgraph、python-dotenv、beautifulsoup4 | [Plotly](https://github.com/plotly/plotly.py)、[pyqtgraph](https://github.com/pyqtgraph/pyqtgraph)、[python-dotenv](https://github.com/theskumar/python-dotenv)、[BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) | MIT / MIT / BSD-3-Clause / MIT |
| PySide6 / Qt | [PySide6](https://doc.qt.io/qtforpython-6/licenses.html) | LGPL-3.0（动态链接，未修改 Qt 源码，安装包内附许可证文本） |
| PyInstaller（仅打包构建） | [PyInstaller](https://github.com/pyinstaller/pyinstaller) | GPL-2.0-with-exception（仅用于构建） |
| pytest、pytest-qt、Playwright（开发测试） | [pytest](https://github.com/pytest-dev/pytest)、[pytest-qt](https://github.com/pytest-dev/pytest-qt)、[Playwright](https://github.com/microsoft/playwright-python) | MIT / MIT / Apache-2.0 |
