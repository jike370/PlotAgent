# Pi 通用 Agent 运行时接入契约

> Pi 是可替换的通用 Agent runtime；PlotAgent Core 始终拥有数据、任务、权限、编译、执行和恢复权威。

## 1. 调用链

1. Electron 向 Core 调用 `workflow.prepare`。
2. Core 先尝试确定性规则和 WorkflowRecipe。
3. 只有仍需语义判断时，Core 返回 `agent_required`、有界 `WorkflowContext`、TaskDraft Schema、轮次/工具预算和系统约束。
4. Pi 可以调用 `inspect_source`、`preview_rows`、`profile_field`、`compare_schemas` 四个只读工具。
5. Pi 必须以 `submit_task_draft` 提交唯一完整 TaskDraft。
6. Core 严格校验并编译为 TaskPlan；确认后才执行。

## 2. Pi 的职责与权限

Pi 负责目标拆解、必要的数据理解、受控数据处理规划和自然语言到结构化绘图参数的翻译。Pi 不拥有文件系统、SQL、Shell、Python、Origin、renderer 或导出路径权限，也不能绕开本地确认和 EngineCatalog。

只读工具接受安全别名，不接受路径或内部 renderer 对象。工具调用和披露标量数受 WorkflowBudget 约束；超预算立即终止当前 run，不执行部分草稿。

## 3. 运行时结果

- `draft_ready`：得到完整 TaskDraft 和本地 TaskPlan。
- `needs_input`：仅提出完成目标所必需的少量问题。
- `unsupported`：目标超出当前产品权限或图类能力。
- Provider/超时错误：保持项目 revision 不变，允许用户明确重试。

Pi 的消息、工具 transcript 和隐藏推理不是项目真相。只有 Core 接受的 TaskDraft、编译后的 TaskPlan 和执行事件进入项目。

## 4. 可替换性门禁

任何其他 Agent runtime 只要能够消费 WorkflowContext、遵守预算、调用同一只读工具并提交 TaskDraft，即可替换 Pi。替换不得改变 TaskDraft Schema、TaskCompiler、TaskPlan、确认、执行、恢复或渲染器合同。
