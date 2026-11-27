# 矩阵分析与应用课程大作业（题目一 + 题目二完整版）

本项目按课程大作业要求同时完成**题目一**与**题目二**，并实现“理论精修 ↔ 真实金融数据与语义系统落地”的闭环联动：

- **题目一（《矩阵分析》中文书稿修订）**：精修**第八章《特征值、特征向量与正定矩阵》（对应 `Lec9` / Meyer 第 7 章）**，并联动补强**第五/六章核心专题《矩阵范数、条件数与奇异值分解（SVD）》（对应 `Lec6`、`Lec7` / Meyer 第 5 章）**。完整交付包括修订稿、逐条修改说明与参考文献核验表、以及 SymPy/NumPy 自动验算与出版级配图脚本：
  - [第八章修订稿：特征值、特征向量与正定矩阵](manuscript/chapter8_eigenvalues_and_psd_revised.md)
  - [第五/六章联动补强：矩阵范数、条件数与奇异值分解](manuscript/chapter5_6_norms_svd_supplement.md)
  - [修改说明、课件勘误与参考文献核验表](manuscript/revision_notes.md)
  - [数学定理与习题自动验算脚本](manuscript/verify_manuscript_math.py)
- **题目二（基于 JEVDB 的股票研究与模拟交易软件）**：原生 Qt 四工作台桌面端（`matrixlab/desktop/`：行情工作台 / 公司研究 / 矩阵组合 / Agent 工作流）、Streamlit 调试对照界面（`app.py`）、四层 Agentic 编排器（`matrixlab/agent.py` + `skills/`）与 CLI（`matrixlab/cli.py`）。

## 核心能力与实测结果

1. **JEVDB 全算子集成与 Prune-First 剪枝**：
   - 支持 `jev_holds`（布尔筛选）、`jev_probability`（置信度排序与阈值截断 $\tau$）、`jev_choose`（结构化行业分类）、`jev_score`（分档打分）与 `prune_then_decide`（对应论文《Prune First, Decide Fast》的两阶段“先粗排剪枝、后语义判定”级联，桌面端可调粗排候选数 `K`，默认消融最优 `K=3`）；
   - 离线关键词基线采用全语料库 IDF 的 Okapi BM25（支持 AND/OR 与引号短语）并严格标记，绝不冒充语义结果；
   - 40 条人工标注评估集实测（DeepSeek 兼容端点 + 协议适配层）：全量 JEVDB 宏 F1 `0.865`（关键词 AND `0.792`）；采用 `Prune-First (k=3)` 粗排后剪枝掉 **31.7%** 候选文档（`328/480`），宏精确率反而从 `0.826` 提升至 **`0.854`**、精确匹配率从 `0.600` 升至 **`0.650`**，同时保持宏 F1 **`0.863`**。
2. **矩阵组合风控与数学诊断**：
   - 样本协方差 Gram 矩阵、正定性检验、条件数 $\kappa(\Sigma)$、手工与 **Ledoit-Wolf (2004) 解析最优收缩 $\alpha^*$**、只做多最小方差 QP + 无约束闭式解对照 + **KKT 互补松弛残差数值校验**（`3.96e-9`）、**Spinu 凸风险平价（ERC，支持桌面端一键切换目标权重并按 ERC 调仓下单）**、相关系数矩阵 PCA 谱分析、以及严格次日开盘撮合的**月度滚动调仓样本外回测**；
   - 12 只美股 2025-01-27 至 2026-10-22 月度滚动实测（21 次调仓，单边 15bp）：Ledoit-Wolf 最小方差实现累计收益 `48.18%`、年化波动 `11.25%`、夏普 **`2.26`**（优于固定 $\alpha=0.05$ 的 `2.23` 与等权滚动的 `1.64`），Spinu ERC 将年化换手率减半至 `35.5%`。
3. **四层 Agent 编排与可视化人工审批工作台**（对应课程 `Lec0` Agentic AI 框架）：
   - 将核心模块封装为标准化 Skills（[skills/](skills/)），区分 `LOW_AUTO`（检索/诊断）、`MEDIUM_CONFIRM`（调仓提案预览）与 `HIGH_EXPLICIT_APPROVAL`（SQLite 原子账本落盘，未获显式批准严禁执行）；
   - 原生桌面端内置第 4 页签 **“Agent 工作流”**，支持输入自然语言需求 → 预览 5 步四层执行轨迹、风险等级与调仓提案 → 人工确认后按预览清单原子撮合并导出审计轨迹 JSON。

## 文档导航

- [项目总报告：架构、矩阵方法、JEVDB 实证与双题联动](docs/report.md)
- [工具与开源 Skills 调研、职责、权限与许可审计](docs/tools.md)
- [运行说明与完整演示步骤](docs/runbook.md)
- [5 位成员个人录屏自述提词脚本与分镜手册](docs/presentation-scripts.md)
- [Windows 桌面版使用说明](docs/windows.md) · [桌面排布与参考来源](docs/desktop-design.md)
- [JEVDB 本机验证记录（2026-11-25）](docs/verification/jevdb-smoke-2026-11-25.md)
- [Multi-Agent 交叉核验报告（2026-11-27）](docs/verification/multi-agent-audit-2026-11-27.md)
- [人工标注评估集与 Prune-First 消融说明](evaluation/README.md)
- [成员贡献记录](docs/contributions.md) · [初始方案简报](docs/proposal.md)

## 快速启动与验证

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-desktop.lock
.venv/bin/python -m matrixlab.cli doctor
.venv/bin/python -m matrixlab.cli fetch
.venv/bin/python -m matrixlab.cli archive --asof 2024-12-31
.venv/bin/python -m matrixlab.desktop
```

测试与评估命令：

```bash
QT_QPA_PLATFORM=offscreen PYQTGRAPH_QT_LIB=PySide6 .venv/bin/python -m pytest -q
.venv/bin/python evaluation/evaluate.py --mode keyword --operator all
.venv/bin/python evaluation/evaluate.py --mode prune_ablation
.venv/bin/python -m matrixlab.cli agent "cloud software" --asof 2025-01-27 --operator any --strategy erc
.venv/bin/python manuscript/verify_manuscript_math.py
```

**Windows 便携版**：[v0.3.0 便携包](https://github.com/mmmsssttt404/matrix/releases/download/v0.3.0/MatrixWorkbench-Windows-x64-v0.3.0.zip) · [Releases 版本页](https://github.com/mmmsssttt404/matrix/releases/latest)（完整解压后双击 `MatrixWorkbench.exe`，保留同目录 `_internal` 文件夹，无需安装 Python）。

![原生股票工作台](docs/images/desktop-workbench.png)

参考：[JEVDB 作者仓库](https://github.com/PDAIS/JEVDB)、[题目论文 arXiv:2610.02046v1](https://arxiv.org/abs/2610.02046v1)。
