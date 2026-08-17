# Pi 通用 Agent 运行时接入契约

> Pi 是可替换的通用 Agent runtime；PlotAgent Core 始终拥有数据、任务、权限、编译、执行和恢复权威。

## 1. 调用链

1. 上传阶段已由 DataPreparationRecipe 或 Agent 辅助整理产生规则数据表；Electron 再向 Core 调用 `workflow.prepare`。
2. Core 对任意自然语言请求返回 `agent_required`、原始 instruction、有界 `WorkflowContext`、TaskDraft Schema、工具和预算；不预解析 instruction。
3. Pi 先尝试一轮直接规划，需要事实时再调用只读检查或数据处理预演工具。
4. Pi 信息不足时调用 `ask_user` 暂停同一 WorkflowRun；用户回答后续跑。
5. Pi 以 `validate_task_draft` 预检并用 `submit_task_draft` 提交唯一完整 TaskDraft。
6. Core 严格校验并编译为 TaskPlan；确认后才正式执行数据操作和绘图。

用户直接操作结构化 UI 时可以不调用 Pi，但仍进入同一 TaskDraft/TaskPlan 链。唯一匹配且沙箱校验通过的 DataPreparationRecipe 也可以零模型生成规则数据表，但它不生成 TaskDraft，也不复用字段绑定、图类或视觉参数；后续自然语言目标仍调用 Pi。

## 2. Pi 的职责与权限

Pi 负责目标拆解、数据/图形指代理解、必要的数据读取、受控数据处理规划、单位目标选择、失败修复策略和自然语言到结构化绘图参数的翻译。Pi 不拥有文件系统、SQL、Shell、Python、Origin、renderer 或导出路径权限，也不能绕开本地确认和 EngineCatalog。

只读和预演工具接受安全别名，不接受路径或内部 renderer 对象。工具调用和披露标量数受 WorkflowBudget 约束；超预算时提出最小问题或停止，不执行部分草稿。预演不修改项目，正式数据处理只在用户确认后由 Core 执行。

Pi 默认获得任务相关来源的安全名称、schema/单位/质量摘要、前 5 行、DataPreparationRecipe 摘要和所选 Profile 的机械兼容性结果；批量中的其他来源只提供目录摘要。Pi 可以按需读取完整小表或大表的范围/样本、字段统计、仪器元数据和原始来源片段，但必须遵守披露预算和数据出境授权。所有数据内容是不可信证据，不能改变系统指令或工具权限。

Pi 运行时不得通过关键词或正则先决定工具、数据源、图类、单轮/多轮路线或重试目标；也不得因为某次程序预检查而移除 Agent 后续可用工具。

## 3. 运行时结果

- `draft_ready`：得到完整 TaskDraft 和本地 TaskPlan。
- `needs_input`：通过结构化问题提出完成目标所必需的少量信息，并可在回答后续跑同一 WorkflowRun。
- `unsupported`：目标超出当前产品权限或图类能力。
- Provider/超时错误：保持项目 revision 不变，允许用户明确重试。

Pi 的消息、工具 transcript 和隐藏推理不是项目真相。只有 Core 接受的 TaskDraft、编译后的 TaskPlan 和执行事件进入项目。

## 4. 可替换性门禁

任何其他 Agent runtime 只要能够消费 WorkflowContext、遵守预算、调用同一检查/预演/追问工具并提交 TaskDraft，即可替换 Pi。替换不得改变 TaskDraft Schema、TaskCompiler、TaskPlan、确认、执行、恢复或渲染器合同。
