# 运行说明与完整演示手册

**主交付是 Qt 原生桌面版（四大工作台：行情工作台 / 公司研究 / 矩阵组合 / Agent 工作流，配备实时流程引导条与离线 HTML 报告导出）。** Windows 用户解压发行包 `MatrixWorkbench-Windows-x64-v0.4.0.zip` 后，保留同目录 `_internal/` 文件夹，直接双击 `MatrixWorkbench.exe`（或 `start-windows.cmd`）运行，无需安装 Python；Windows 源码用户可在仓库根目录执行 `.\scripts\start-windows.ps1` 一键建环并启动；Linux/macOS 源码启动：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-desktop.lock
.venv/bin/python -m matrixlab.cli fetch
.venv/bin/python -m matrixlab.cli archive --asof 2024-12-31
.venv/bin/python -m matrixlab.desktop
```

## 原生桌面端完整端到端演示（4 步闭环）

1. **准备真实数据与研究日期（行情工作台，`Ctrl+1`）**：首次启动空工作区可点击界面中央“下载课程研究数据”（或在菜单栏点击 `文件 → 获取历史百科存档(2024-12-31)`）；将顶部研究日期设为 `2025-01-27`，可在左侧自选股列表切换标的并缩放 K 线 / MA20。
2. **语义/关键词防穿越筛选（公司研究，`Ctrl+2`）**：选择“离线关键词”（全语料库 BM25，支持 AND/OR）或“JEVDB语义”（支持 `jev_holds`、`jev_probability` 阈值 $\tau$、`jev_choose`、`jev_score` 与 `Prune-First` 粗排剪枝，默认最优 `K=3`）。输入 `cloud software` 检索，系统严格只评估 `available_at <= 2025-01-27` 的历史资料；双击任意命中行查看原文与署名链接，点击“加入组合研究”自动带入股票池与截止日期。
3. **矩阵诊断、收缩优化与策略下单（矩阵组合，`Ctrl+3`）**：勾选 `Ledoit-Wolf最优α*`（或手工调 $\alpha$）并点击“计算组合”，在 3 个子标签页依次检视：
   - **权重与协方差**：对比只做多 QP、无约束闭式解与 Spinu 凸风险平价（ERC），查看欧拉风险分解、年化协方差热力图与 KKT 互补松弛残差（`~3.96e-9`）；可随时切换顶部“调仓目标”为 `最小方差(QP)` 或 `风险平价(ERC)`，并导出多列完整权重诊断 CSV；
   - **PCA 与收缩路径**：查看相关系数矩阵 PCA 解释方差/前 3 主成分载荷，以及 $\alpha \in [0, 1]$ 上条件数与收缩后最小特征值 $\lambda_{\min}(\Sigma_\alpha)$ 的单调演化；
   - **样本外与滚动回测**：点击“运行月度滚动对比(含ERC与LW)”，对比 21 次月度调仓的累计收益、夏普比率与年化换手率。
4. **四层 Agent 编排、离线 HTML 报告与人工审批撮合（Agent 工作流，`Ctrl+4`）**：输入自然语言研究需求，选择目标策略（`最小方差(QP)` 或 `风险平价(ERC)`）并点击“运行四层工作流（预览）”。界面按 `Preamble → Plan → Retrieve → Risk → Proposal` 逐行展示 5 步轨迹、Skill 名称、耗时与风险等级（`LOW_AUTO` / `MEDIUM_CONFIRM` / `HIGH_EXPLICIT_APPROVAL`），此时严格只读、不改写 `paper.sqlite3`。可点击 **“生成可复查 HTML 报告”** 导出完全离线的自包含演示报告（`report.html` + `trace.json`）；核对调仓提案无误后，点击“人工批准并执行撮合”并在二次确认弹窗点选确认，系统立即按所见即所得清单在 SQLite `BEGIN IMMEDIATE` 原子事务中以次日复权开盘价撮合，自动推进模拟日期、刷新右侧账户权益与底部成交表。修改任意筛选条件或风控参数后，旧结果会自动失效，防止误用过期权重。

## Streamlit 调试对照界面（Linux / 开发环境）

在仓库根目录使用 Linux x86-64 与 Python 3.12+（实测 Python 3.13）。JEVDB 预编译扩展绑定 `duckdb==1.4.3`，不能单独升级 DuckDB。

```bash
python3 -m venv .venv
mkdir -p .cache/tmp .cache/pip
TMPDIR="$PWD/.cache/tmp" PIP_CACHE_DIR="$PWD/.cache/pip" .venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m matrixlab.cli doctor
.venv/bin/python -m matrixlab.cli fetch
.venv/bin/python -m matrixlab.cli archive --asof 2024-12-31
.venv/bin/streamlit run app.py
```

浏览器打开终端显示的本机地址，默认 `http://127.0.0.1:8501`。`doctor` 检查扩展和凭证存在性，不发送模型请求。

如需独立工作区，在本地 `.env` 设置绝对路径 `MATRIX_DATA_DIR` 后重启。已有模拟账户的工作区禁止直接覆盖行情，避免破坏账本价格基准。

## CLI 快捷复现与评测命令

一键数值演示与四层 Agent 工作流演示（不自动执行高风险写库，需 `--approve` 显式授权）：

```bash
.venv/bin/python -m matrixlab.cli demo --asof 2025-01-27
.venv/bin/python -m matrixlab.cli research 'cloud software' --asof 2025-01-27 --mode keyword --operator all
.venv/bin/python -m matrixlab.cli research 'cloud computing' --asof 2025-01-27 --mode jevdb --jev-op prune_then_decide --prune-k 3
.venv/bin/python -m matrixlab.cli agent 'cloud software' --asof 2025-01-27 --mode keyword --operator any --strategy erc --include-holdout --html-dir demo-report
.venv/bin/python -m matrixlab.cli agent 'cloud software' --asof 2025-01-27 --mode keyword --operator any --strategy erc --approve
.venv/bin/python evaluation/evaluate.py --mode keyword --operator all
.venv/bin/python evaluation/evaluate.py --mode prune_ablation
.venv/bin/python manuscript/verify_manuscript_math.py --plot
```

`evaluation/evaluate.py` 默认使用 `evaluation/documents.csv` 的12家公司人工标注集（40条查询），输出 precision/recall/F1/MRR；换用真实数据时加 `--documents data/documents.csv`。评估结果在 `evaluation/results/`。

`demo`每次在`data/demo/独立编号/`建立新账本，不改写主账户；输出协方差、权重、样本外曲线和运行摘要。

## 配置真实JEVDB语义查询

将`.env.example`复制为本地`.env`。Jev服务配置：

```dotenv
MATRIX_BACKEND=jev
JEV_API_KEY=在本地填写
```

兼容模型服务配置（必须支持Chat Completions及严格JSON Schema结构化输出）：

```dotenv
MATRIX_BACKEND=llm
OPENAI_API_KEY=在本地填写
MATRIX_API_ENDPOINT=https://供应商接口/v1/
MATRIX_API_MODEL=实际模型名称
```

重启后选择“JEVDB语义查询”，或运行：

```bash
.venv/bin/python -m matrixlab.cli research 'The company offers cloud computing services' --asof 2025-01-27 --mode jevdb
```

若供应商只支持`response_format={"type":"json_object"}`（例如DeepSeek），可用本仓库的兼容层把JEVDB的`json_schema`请求转换后再发往上游：

```bash
python scripts/jev_llm_proxy.py --port 8111
```

```dotenv
MATRIX_BACKEND=llm
OPENAI_API_KEY=供应商密钥
MATRIX_API_ENDPOINT=http://127.0.0.1:8111/v1/
MATRIX_API_MODEL=供应商模型名
```

代理会把schema写入提示词、校验返回值并按需重试；语义判断仍由上游模型完成。它是协议适配层，不等价于JEVDB原生支持的提供商。

条件只作为SQL字符串常量；程序不执行用户提供的任意SQL。最多处理200条资料，并限制并发、超时和重试。资料正文会发送给配置的模型服务；凭证读取自环境，研究导出记录不保存凭证。API不可用时明确报错，不自动伪装成语义结果。

当前本机验证状态（2026-11-25）：WSL2 中 `jevdb==0.1.0` 可加载并注册 `jev_holds` 等函数；默认 Typesafe 后端返回 HTTP 451（地区限制），改走 `MATRIX_BACKEND=llm` 与 DeepSeek 兼容端点后，经上述兼容层完成 40 条查询，0 错误，宏 F1 0.865（关键词 AND 为 0.792），证据见 [verification/jevdb-smoke-2026-11-25.md](verification/jevdb-smoke-2026-11-25.md)。复现：

```bash
.venv/bin/python evaluation/evaluate.py --mode both
```

## CSV字段与价格规则

行情必需字段：`date,symbol,open,high,low,close,volume,price_basis,source_url,retrieved_at`。`date`为交易所日期，`price_basis`必须是`total_return_adjusted`。价格须为有限正数，不能重复同一股票同一天；不接受不同复权基准混合。侧栏可下载空白字段模板并导入CSV。

公司资料必需字段：`doc_id,symbol,title,text,available_at,source_url,retrieved_at`。时间用带时区的ISO格式；可用时间不得晚于获取时间，单条正文最多12000字符。研究日期按纽约当日日末解释。

模拟使用统一总回报复权价、整数模拟份额、无杠杆且只做多。价格已经包含供应商的拆股及股息调整，因此账本不再次发放股息或调整份额。它不是按真实历史未复权股价重建的股数账本。滑点在买入时上调、卖出时下调价格，执行价保留4位小数，手续费按美分四舍五入；现金以百万分之一美元的整数保存。

## 验证

```bash
mkdir -p .cache/tmp
TMPDIR="$PWD/.cache/tmp" .venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

测试中的合成数据只用于数学和交易边界验证；应用图表读取下载或导入的实际数据。JEVDB传输测试使用本机固定响应服务，只验证真实扩展、SQL和请求链路，不代表真实模型质量或API连通性。

真实浏览器检查需要额外安装浏览器，截图写入`docs/images/`；检查使用独立临时账本，不改写主账户：

```bash
PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/browsers" TMPDIR="$PWD/.cache/tmp" .venv/bin/python -m playwright install chromium --only-shell
TMPDIR="$PWD/.cache/tmp" .venv/bin/python scripts/smoke_ui.py
```
