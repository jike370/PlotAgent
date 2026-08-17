# WorkflowRun 与 TaskPlan 运行时

> 本文定义 PlotAgent v3 当前唯一任务运行时。目标架构见 [成本感知 Agent 编排架构](./AGENT-ORCHESTRATION-ARCHITECTURE.md)。

## 1. 权威对象

一次用户目标按以下对象推进：

```text
WorkflowRun
  → WorkflowContext
  → TaskDraft
  → TaskPlan / TaskItem
  → confirmed execution
  → item result / retry
```

- `WorkflowContext` 是从项目当前 revision 构建的有界别名投影。
- `TaskDraft` 只表达来源、封闭数据操作、字段绑定、图类和公共视觉动作。
- `TaskPlan` 由本地编译器解析真实字段、图形版本和幂等键；模型不能直接构造。
- `TaskItem` 是局部成功、局部失败和局部重试的最小单位。

## 2. 状态

WorkflowRun 依次经过 context preparation、Agent/显式 Recipe/结构化 UI、inspection/preview、needs_input、draft_ready、awaiting_confirmation、executing 和终态。TaskPlan 依次经过 awaiting_confirmation、ready、running 与 succeeded/partially_succeeded/failed/rejected/cancelled。

用户确认前不得执行。项目 revision 或目标 plot version 变化时，旧计划必须稳定拒绝，不能在新对象上猜测重放。

## 3. 执行规则

- 同一计划按 TaskItem 顺序执行；显式依赖失败时下游标为 blocked。
- 已 succeeded 的 TaskItem 在 resume 时直接复用，不重复创建或编辑。
- 每个 create/edit 动作继续经过 EngineCatalog 本地能力校验。
- 数据处理只允许 TaskDraft Schema 中的封闭操作；预演与正式执行使用同一实现，原始 SourceDataset 不可变。
- 当前图的数据重绑定生成 PreparedDataView 和新的 PlotDocument 版本，不能作为纯视觉 edit 执行。
- 结构化追问暂停 WorkflowRun；回答只补充上下文，不执行未经确认的部分 Draft。
- 导出目的地由桌面保存对话框选择，不属于 Agent 或 TaskDraft 权限。

## 4. 持久化与恢复

项目 schema v5 保存 WorkflowRun、WorkflowContext、TaskDraft、TaskPlan、TaskItem（含失败原因与可重试性）、事件和 WorkflowRecipe。项目使用单写入器锁；崩溃后只从已提交状态恢复，不续跑未知的 renderer 内部状态。

恢复时重新检查项目 revision、plot version、输入对象与执行条件。合法成功项保留；失败项可由用户明确继续。旧 schema 不原地迁移，不存在双读、双写或兼容回退。

## 5. 门禁

- 未确认计划产生零项目副作用。
- 批量部分失败不回滚成功项，也不在重试时重复成功项。
- 一次 TaskItem 成功只发布一个新 plot version。
- 运行时事件包含真实阶段、item ID、attempt 和稳定错误码。
- 所有正式桌面入口只调用 workflow.* RPC。
- 自然语言 instruction 在 Electron、Core、Agent 之间逐字保持，运行时不创建隐藏改写版本。
