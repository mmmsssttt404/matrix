---
name: matrix-paper-broker
description: Atomic, idempotent SQLite paper-trading ledger enforcing next-open execution, directional slippage, integer micro-dollar cash accounting, monotonic simulation clock, and human-in-the-loop approval gates.
---

# Matrix Paper Broker Skill

## 1. 职责与风险等级
- **所属层级**：Action / Execution（状态变更与账本写入层）
- **风险等级**：
  - `rebalance_orders`（调仓订单提案）：`MEDIUM_CONFIRM`（只读计算，需用户预览确认）
  - `Broker.execute`（订单撮合与账本落盘）：`HIGH_EXPLICIT_APPROVAL`（必须获得显式批准才可执行）

## 2. 工具契约（输入 → 输出）
- **入口**：`matrixlab.trading.rebalance_orders`、`matrixlab.trading.Broker`
- **输入**：`orders` 列表、`signal_date`、`prices`、`request_id`（幂等请求号）
- **输出**：成交记录列表、更新后的现金/持仓/每日权益快照（全部封装在单个 SQLite `BEGIN IMMEDIATE` 写事务中）

## 3. 交易规则、权限与安全边界
- **依赖**：Python 标准库 `sqlite3`、`decimal`（PSF 许可，零第三方外部券商依赖）
- **权限**：仅读写当前工作区 `paper.sqlite3`，无真实券商交易接口权限
- **核心风控规则**：
  - 信号日必须等于账户当前时钟 `clock`，禁止回溯或跳步；
  - 统一在下一交易日复权开盘价撮合，买入上调滑点、卖出下调滑点，手续费单列；
  - 先卖后买；任意单笔订单资金/持仓不足或缺失次日开盘价时，整批原子回滚；
  - 现金以整数微美元（`1e-6 USD`）存储，同一 `request_id` 幂等不重复成交，篡改负载直接拒绝。
