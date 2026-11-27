# 研究筛选评估

这是一个**人工标注的小型诊断集**，用于比较离线关键词基线（AND/OR + BM25）与 JEVDB 语义筛选，不作为投资建议，也不代表真实市场全貌。

- `documents.csv`：12 家公司的简短介绍，由小组成员根据公开常识自行撰写，不是维基原文；`source_url` 仅指向对应百科条目。
- `labels.csv`：40 条“查询 → 相关公司代码”的人工标注，相关性按公司业务判断，可能与关键词是否出现无关。标注是本评估的主观真值，修改标注会改变指标。
- `evaluate.py`：逐条调用 `matrixlab.research.screen`，计算 precision、recall、F1、MRR、exact match，并输出 JSON。

## 运行

```bash
python evaluation/evaluate.py --mode keyword --operator all
python evaluation/evaluate.py --mode keyword --operator any
python evaluation/evaluate.py --mode jevdb
python evaluation/evaluate.py --mode both
python evaluation/evaluate.py --mode prune_ablation
```

默认使用 `evaluation/documents.csv` 和 `evaluation/labels.csv`。要评估真实数据：

```bash
python evaluation/evaluate.py --documents data/documents.csv --labels evaluation/labels.csv --mode both
```

前提是 `data/documents.csv` 中至少包含这 12 个代码；相关性标签按代码匹配，不依赖文档原文。

## 结果（2026-11-25 / 2026-11-27 更新）

| 模式 | 评估文档数 | 剪枝比例 | 宏 P | 宏 R | 宏 F1 | MRR | 精确匹配 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 关键词 AND + BM25（全语料 IDF） | 480 | — | 0.850 | 0.769 | 0.792 | 0.850 | 0.700 |
| 关键词 OR + BM25（全语料 IDF） | 480 | — | 0.729 | 0.844 | 0.730 | 0.925 | 0.500 |
| JEVDB 全量（DeepSeek 兼容端点） | 480/480 | 0.0% | 0.826 | 0.969 | 0.865 | 0.906 | 0.600 |
| Prune-First + JEVDB (`prune_k=3`) | 328/480 | 31.7% | 0.854 | 0.923 | 0.863 | — | 0.650 |
| Prune-First + JEVDB (`prune_k=4`) | 334/480 | 30.4% | 0.848 | 0.923 | 0.859 | — | 0.625 |
| Prune-First + JEVDB (`prune_k=6`) | 341/480 | 29.0% | 0.844 | 0.923 | 0.856 | — | 0.625 |

JEVDB 结果来自 DeepSeek 兼容端点加本机协议适配层（`scripts/jev_llm_proxy.py`），不是 Typesafe 原生服务；`prune_ablation` 为基于 `both-deepseek.json` 的精确重放消融（详见 `results/prune-ablation.json` 与 `docs/verification/jevdb-smoke-2026-11-25.md`）。

## 注意

- 这 40 条标注用于课程演示和错误分析，样本量不足以支撑统计显著性结论。
- JEVDB 模式需要真实模型密钥或 Linux 语义服务；未配置时会明确报错，不会生成替代语义结果。若供应商只支持 `json_object`，需先启动兼容层，见 `docs/runbook.md`。
- 关键词模式的结果只能说明词面匹配能力，不能当作语义质量的上限或下限。
