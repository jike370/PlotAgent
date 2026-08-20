# Durable Agent Task 与 TaskPlan 运行时

> 本文定义 PlotAgent 当前正式桌面任务运行时。编排边界见 [程序—Agent 编排架构](./AGENT-ORCHESTRATION-ARCHITECTURE.md)，状态转换见 [Agent 任务状态合同](./PLOTAGENT-AGENT-TASK-STATE-CONTRACT.md)。

## 1. 权威对象

```text
TaskEnvelope
  → durable Agent task / checkpoint
  → AgentActivation ↔ ToolGateway
  → AgentYield / TaskIntent
  → Core TaskPlan
  → confirmation / ExecutionGrant
  → execution / VerificationReport
  → delivery or recoverable state
```

- `TaskEnvelope` 保存用户原文和提交时的结构化数据、图类与 `@图N` 选择。
- `AgentActivation` 是 Core 根据当前 checkpoint 生成的有界上下文、工具和预算。
- `TaskIntent` 只表达来源、封闭数据操作、字段绑定、图类和公共视觉动作；模型不能构造真实对象 ID 或授权。
- `TaskPlan` 由 Core 解析真实字段、图版本、依赖和幂等键后冻结，是用户确认的对象。
- `ExecutionGrant` 绑定精确 plan/intent/version；没有 grant 不得写项目。
- `VerificationReport` 决定成功、修复、部分结果或终态，Agent 自述不构成完成。

## 2. 状态

durable task 覆盖 `created`、`investigating`、`awaiting_input`、`intent_staged`、`awaiting_confirmation`、`executing`、`verifying`、`repairing`、`awaiting_reconfirmation`、`delivering`、`partial`、`blocked`、`cancelled`、`failed` 和 `completed_verified` 等受限状态。

用户确认前不得执行。项目 revision、来源版本或目标 plot version 变化时，旧计划稳定拒绝，不能在新对象上猜测重放。状态转换的完整合法边以任务状态合同和确定性矩阵为准，UI 不自行推导第二套状态。

## 3. 执行规则

- 同一计划按 item 和显式依赖执行；依赖失败时下游标为 blocked。
- 已成功 item 在安全重试或恢复时复用，不重复创建或编辑。
- 每个 create/edit 动作经过 Engine Profile capability、本地版本和参数校验。
- 数据处理只允许 TaskIntent item 中的封闭操作；Core 使用同一确定性实现校验和执行，原始 SourceDataset 不可变。
- 当前图的数据重绑定生成 PreparedDataView 和新的 PlotDocument 版本，不能作为纯视觉 edit。
- 结构化追问暂停同一 task；续轮上下文作为事件进入 ledger，不只存在于聊天或 React 状态。
- 导出目的地由桌面保存对话框授权，不属于 Agent 权限。

## 4. 持久化与恢复

项目 schema v7 保存 task、intent、activation、plan、grant、事件、checkpoint、tool receipt、VerificationReport 和 lease。项目使用单写入器锁；崩溃后只从已提交 checkpoint 恢复，不续跑未知 renderer 内部状态。

恢复时重新检查项目 revision、plot version、输入对象和执行条件。合法成功项保留；仅 `partial` 等合同允许的状态可走安全重试。本机 v5/v6 工作区只执行代码覆盖的事务性增量迁移；其他版本不改写并稳定拒绝。

旧 WorkflowRun/TaskDraft repository 是非公开实现遗留/技术储备；正式桌面不公开旧 workflow RPC、Recipe save/replay，也不把其状态作为当前任务权威。

## 5. 门禁

- 未确认计划产生零项目副作用。
- 批量部分失败不回滚成功项，也不在重试时重复成功项。
- 一次 item 成功只发布一个预期的新 plot version。
- 事件包含真实阶段、item、attempt、稳定错误和可恢复性。
- 自然语言 instruction 从 Electron 到 Core/Pi 保持原文；程序不创建隐藏语义版本。
- 重启后 checkpoint、上下文更新、确认授权和成功项身份保持一致。
