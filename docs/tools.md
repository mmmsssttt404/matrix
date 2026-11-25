# 工具、依赖、许可与权限

| 工具及入口 | 输入→输出 | 依赖与权限 | 已知限制 |
|---|---|---|---|
| `matrixlab.acquire.fetch_dataset` | 股票、日期→行情CSV与manifest | Yahoo公开数据端点、yfinance；外网读取、本地data写入 | 限流、历史修订；当前简介以获取时刻计可用时间 |
| `matrixlab.acquire.archive_documents` | 公司、历史截止日期→特定版本正文 | Wikipedia版本API、BeautifulSoup；外网读取、本地data写入 | 资料是百科叙述；保留版本链接与署名来源，不视为财报事实已独立核验 |
| `matrixlab.research.screen` | 条件、可用日期、文档→带来源与相关度的研究记录 | JEVDB/DuckDB/Arrow；读取环境凭证、发送指定文档、写研究JSON | 语义模式须有模型API；关键词模式使用AND/OR+BM25并明确标记，不能等同语义质量 |
| `evaluation.evaluate` | 文档CSV、人工标注CSV→逐条与汇总指标JSON | pandas；只读文档与标注、写`evaluation/results` | 40条标注是课程诊断样本，不构成统计显著性结论 |
| `scripts.jev_llm_proxy` | OpenAI兼容的`json_schema`请求→`json_object`上游调用→按schema校验与重试 | 上游兼容端点、本机回环端口；读取本地密钥 | 仅为协议适配层；语义判断由上游模型完成，不等价于JEVDB原生提供商 |
| `matrixlab.analytics.analyze` | 收益率、回看长度、α→协方差、特征值、权重 | pandas/NumPy/SciPy；内存计算 | 不填补缺失；至少60个共同收益率观测，历史风险不预测未来收益 |
| `matrixlab.trading.Broker` | 订单、信号日期、行情→成交与权益 | SQLite/Decimal；本地账本读写 | 单账户、简化复权份额；无真实券商权限 |

应用不接受任意Shell命令或可执行SQL，也不自动安装外部Skills。用户资料作为待分析数据处理，不用其中的文字改变程序权限。模型输出只能影响资料筛选；金额、订单有效性与账本更新由确定性代码检查。

实际集成依赖来自官方发布包，完整版本保存在`requirements.lock`。JEVDB0.1.0的DuckDB绑定为1.4.3；pandas3字符串类型通过Arrow表桥接，避免DuckDB旧版pandas扫描器不兼容。

| 直接依赖 | 上游与许可 |
|---|---|
| JEVDB | [PDAIS/JEVDB](https://github.com/PDAIS/JEVDB)，MIT |
| DuckDB | [duckdb/duckdb](https://github.com/duckdb/duckdb)，MIT |
| NumPy、pandas、SciPy | [NumPy](https://github.com/numpy/numpy)、[pandas](https://github.com/pandas-dev/pandas)、[SciPy](https://github.com/scipy/scipy)，BSD系列；二进制分发另含第三方通知 |
| Streamlit、PyArrow、yfinance | [Streamlit](https://github.com/streamlit/streamlit)、[Arrow](https://github.com/apache/arrow)、[yfinance](https://github.com/ranaroussi/yfinance)，Apache-2.0 |
| Plotly、python-dotenv | [Plotly](https://github.com/plotly/plotly.py)、[python-dotenv](https://github.com/theskumar/python-dotenv)，MIT与BSD-3-Clause |
| PySide6 / Qt | [PySide6](https://doc.qt.io/qtforpython-6/licenses.html)，LGPL-3.0（本仓库动态链接，未修改 Qt 源码）；安装包内附 LGPL/GPL 文本 |
| pyqtgraph | [pyqtgraph](https://github.com/pyqtgraph/pyqtgraph)，MIT |
| PyInstaller（构建） | [PyInstaller](https://github.com/pyinstaller/pyinstaller)，GPL-2.0-with-exception；仅用于构建，不修改其源码 |
| pytest、pytest-qt、Playwright（开发） | [pytest](https://github.com/pytest-dev/pytest)，MIT；[pytest-qt](https://github.com/pytest-dev/pytest-qt)，MIT；[Playwright](https://github.com/microsoft/playwright-python)，Apache-2.0 |

软件许可与数据使用条件分开记录。Yahoo数据仅在本地用于研究演示，使用者需查看其条款；Wikipedia文本保留原始历史版本链接，使用与分发应遵守页面对应的许可及署名要求。公开仓库不包含下载的第三方数据全集。

开发核查使用Context7及作者仓库文档，题目论文按arXiv记录核实；本机JEVDB测试服务参考作者仓库MIT许可的`tools/standin/jev_standin.py`协议，未将测试服务包装为真实语义模型。2026-11-25 的 WSL 验证：扩展可加载并注册函数；Typesafe 后端返回 HTTP 451；DeepSeek 兼容端点只支持`json_object`，因此经`scripts/jev_llm_proxy.py`做`json_schema`→`json_object`适配后完成40条查询（0错误）。该结果是兼容端点上的真实模型判断，不是 Typesafe 原生调用，详见 `docs/verification/jevdb-smoke-2026-11-25.md`。
