# Pi Agent 运行适配契约

> 状态：已实现。Pi 提供可替换的模型—工具运行循环；PlotAgent Core 始终拥有任务、数据、权限、计划、执行、验证与恢复权威。

## 1. 当前调用链

1. Electron Main 根据用户原始 instruction、所选数据、所选图形和可选图类创建 `TaskEnvelope v2`。
2. Core 持久化 durable task，并按当前 task state 生成有界 `AgentActivation`。
3. `PiRuntimeAdapterV2` 消费 activation，读取 Core 提供的 ContextSnapshot、工具定义、预算和 typed `AgentYield` Schema。
4. Pi 自主决定是否调用只读检查、确定性数据工具或领域查询；程序不通过关键词、正则或列名规则替模型理解自然语言。
5. Pi 只提交一个 typed `AgentYield`。Core 校验身份、状态、预算、权限和内容后，形成 `TaskIntent` 或结构化追问。
6. Core 将 intent 编译为可确认计划。只有用户确认后，执行器才可写入项目、调用 renderer 或导出。
7. 执行结果、逐项状态、receipt、验证报告和最终 plot/version 持久化到 durable checkpoint；失败恢复只处理失败项，已成功项不重复执行。

正式入口不再公开 `workflow.prepare`、v1 workflow plan RPC 或 workflow recipe save/replay；`AgentFoundationRuntime` 是唯一桌面 Agent 协调器。

## 2. Pi 的职责与权限

Pi 负责：

- 解释用户目标和对象指代；
- 选择需要检查的数据事实；
- 规划受控的数据整理或转换；
- 将自然语言翻译为图类、字段绑定和 renderer-neutral 绘图参数；
- 信息不足时提出最小必要问题；
- 根据结构化失败证据修订未成功项。

Pi 不拥有任意文件系统、SQL、Shell、Python、Origin、模板、renderer 私有对象或导出路径权限。它只能调用 Core 在本次 activation 中明示、强类型、限时、限量且状态允许的工具。任何写入还需要 Core 生成的 execution grant；模型输出本身不是授权。

## 3. 任务结果

- `propose_intent`：Core 接受 intent，生成等待用户确认的计划；
- `needs_input`：同一 durable task 暂停，用户回答后从 checkpoint 续接；
- `unsupported`：请求超出当前产品或图类合同；
- `blocked`：存在明确外部恢复条件；
- `runtime_failed` / `budget_exhausted`：不产生项目副作用，保留安全诊断并允许重试；
- `cancelled`：停止本任务，保留已原子完成的项目结果，不终止无关任务或用户 Origin。

聊天消息和模型隐藏推理不是项目真相。项目真相仅包括 Core 接受的 intent/plan、TaskEvent、receipt、VerificationReport、durable checkpoint 和正式产物。

## 4. 可替换性

其他通用 Agent runtime 只要能消费 `AgentActivation`、遵守工具与预算、并返回同一个 typed `AgentYield`，就可以替换 Pi。替换不得改变：

- TaskEnvelope、TaskIntent、TaskPlan 与 durable task 状态机；
- ToolGateway、权限阶段、execution grant、receipt 与幂等规则；
- 用户确认、部分成功、取消、重启恢复和验证语义；
- 34 图 EngineProfile、renderer 与 Origin 输出合同。

Pi 因而是运行循环适配层，不是 PlotAgent 的产品权威或绘图引擎。
