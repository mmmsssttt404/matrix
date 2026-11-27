# JEVDB 验证记录（2026-11-25）

状态：**部分完成**。Typesafe 后端因地区限制返回 HTTP 451；改走 `MATRIX_BACKEND=llm`，经本地协议适配层调用 DeepSeek，完成 40 条查询与评估。

## 环境

- Windows 11 + WSL2 Ubuntu 24.04
- Python 3.12（WSL），`jevdb==0.1.0`，`duckdb==1.4.3`
- 上游：DeepSeek Chat Completions，模型 `deepseek-flash`
- 适配层：`scripts/jev_llm_proxy.py`（本机 127.0.0.1:8111）

## 已验证

扩展可以正常连接并注册以下函数：

```text
jev_choose, jev_holds, jev_keys_overlap, jev_probability, jev_score, jevdb_stats
```

默认 `jev` 后端调用返回：

```text
IO Error: JEVDB: request failed or returned no answers (HTTP 451):
{"title":"Typesafe is not available in your region.","status":451}
```

DeepSeek 的 `response_format` 兼容性探测：

```text
{"type":"json_object"}  → HTTP 200
{"type":"json_schema","json_schema":{...,"strict":true}} → HTTP 400
{"type":"json_schema","json_schema":{...}}               → HTTP 400
错误信息：This response_format type is unavailable now
```

JEVDB 扩展固定发送 `json_schema`（二进制内可见
`"response_format":{"type":"json_schema","json_schema":{"name":...,"strict":true,...}}`），
因此直连 DeepSeek 不可行。适配层把 schema 注入提示词、以 `json_object` 调用上游，
再按 schema 校验并在失败时重试；语义判断仍由 DeepSeek 完成。

单条调用（`cloud computing`，12 份文档）：

```text
run.backend = jevdb_llm
matched = 4（AAPL/AMZN/GOOGL/MSFT）
errors = 0，单次请求约 7.4 秒
```

## 40 条评估

命令（WSL，端点指向本机适配层）：

```bash
MATRIX_BACKEND=llm MATRIX_API_ENDPOINT=http://127.0.0.1:8111/v1/ \
MATRIX_API_MODEL=deepseek-flash \
python evaluation/evaluate.py --mode both --operator all \
  --output evaluation/results/both-deepseek.json
```

结果：

```text
JEVDB ：40/40 成功，0 错误，宏 P=0.826 R=0.969 F1=0.865 MRR=0.906，精确匹配 0.600
关键词：40/40 成功，0 错误，宏 P=0.850 R=0.769 F1=0.792 MRR=0.850，精确匹配 0.700（2026-11-27 修复全语料 IDF 后复测口径一致）
代理入口请求 41 次（含 1 次冒烟与 40 条评估），期间 5 次触发 schema 校验内部重试，最终失败 0
prompt 37689 tokens，completion 42792 tokens，合计 80481
累计约 403 秒，单次最长 56.3 秒
```

注：`deepseek-flash` 为本次兼容端点日志记录的模型标识，实际复现请按所使用供应商的有效模型 ID 配置（如 DeepSeek 官方 `deepseek-chat`）。

## 边界

- 这是 DeepSeek 兼容端点上的真实模型判断，**不是 Typesafe 原生服务**，不能外推为 JEVDB 官方后端质量。
- 只有 40 条查询、单次运行；温度设为 0 只能降低、不能消除波动。
- 费用只记录 token 数，未按供应商当期价格折算。
- `tools/standin` 的固定响应仍不能记作语义结果。
- 密钥只保存在本地 `.env`（已被 `.gitignore` 忽略），未写入研究导出或日志。
