# 运行说明

**主交付是 Qt 桌面版。** Windows 用户解压发行包后直接运行 `MatrixWorkbench.exe`；源码启动：

```bash
python -m matrixlab.desktop
```

下面的 Streamlit 流程保留为调试/对照界面，不是当前主界面。

## 安装和启动（Streamlit 调试界面）

在仓库根目录使用Linux x86-64与Python3.12+，推荐实测版本Python3.13。JEVDB预编译扩展绑定DuckDB1.4.3，不能单独升级DuckDB。

```bash
python3 -m venv .venv
mkdir -p .cache/tmp .cache/pip
TMPDIR="$PWD/.cache/tmp" PIP_CACHE_DIR="$PWD/.cache/pip" .venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m matrixlab.cli doctor
.venv/bin/python -m matrixlab.cli fetch
.venv/bin/python -m matrixlab.cli archive --asof 2024-12-31
.venv/bin/streamlit run app.py
```

浏览器打开终端显示的本机地址，默认http://127.0.0.1:8501。服务绑定本机；GitHub保存协作代码，不自动托管运行实例。`doctor`检查扩展和凭证存在性，不发送模型请求。

`fetch`获取12只美股的真实日线和当前公司简介，排除纽约当天可能尚未完成的日线。`archive`获取2024年末之前的Wikipedia公司介绍版本，用于有依据的历史筛选。每条记录保留来源链接、历史版本ID或获取时间；某个下载失败会记入manifest，全部失败明确报错。首次下载后，数值计算与模拟交易无需联网。原始数据不进入公开仓库。

如需另一份数据或独立账户，在本地.env设置绝对路径`MATRIX_DATA_DIR`，然后重启。已有模拟账户的工作区不能直接覆盖行情，避免改变账本的价格基准。多个小组成员应分别使用自己的数据目录；当前原型没有多用户登录功能。

## 一条完整演示

1. 在“公司研究”中选2025-01-27作为资料可用日期，选择“离线关键词基线”，输入`cloud software`并检索。默认要求全部词命中（AND）并按BM25排序；可切换OR，或用引号指定短语。历史Wikipedia版本能参与筛选，2026年下载的当前公司简介会被排除。结果标明基线类型、相关度、原文、来源和时间。
2. 点击“将这些公司用于组合研究”，进入“矩阵与组合”，计算协方差、最小方差权重和条件数。默认回看252条共同有效收益率，收缩系数0.05；展开“矩阵推导与数值诊断”可查看PCA解释方差与载荷、风险贡献分解、无约束闭式解对照、收缩路径，以及样本外等权比较。
3. 在“模拟交易”中以2025-01-27为起始日创建100000美元账户。研究日期与账户时钟一致时可生成整批调仓单；份额按当日收盘估算，预留5%现金。
4. 确认订单后，程序使用下一交易日的复权开盘价并计入滑点和手续费。资金不足或任何一单无效时整批回滚。也可手动提交一只股票的订单。
5. 推进模拟日期，查看权益和逐笔成交，导出研究JSON、权重CSV及成交CSV。界面变化后须重新计算权重；账户时钟不能回退。

一键数值演示与四层 Agent 工作流演示（不自动执行高风险写库，需 `--approve` 显式授权）：

```bash
.venv/bin/python -m matrixlab.cli demo --asof 2025-01-27
.venv/bin/python -m matrixlab.cli research 'cloud software' --asof 2025-01-27 --mode keyword --operator all
.venv/bin/python -m matrixlab.cli research 'cloud computing' --asof 2025-01-27 --mode jevdb --jev-op prune_then_decide --prune-k 6
.venv/bin/python -m matrixlab.cli agent 'cloud software' --asof 2025-01-27 --mode keyword --operator any
.venv/bin/python -m matrixlab.cli agent 'cloud software' --asof 2025-01-27 --mode keyword --operator any --approve
.venv/bin/python evaluation/evaluate.py --mode keyword --operator all
.venv/bin/python evaluation/evaluate.py --mode prune_ablation
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
