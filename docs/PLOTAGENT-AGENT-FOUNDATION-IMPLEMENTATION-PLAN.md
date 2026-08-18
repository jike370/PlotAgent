# PlotAgent Agent 基础设施施工计划

> 状态：P0–P9 已完成；P10 代码切换、旧公开链清理、E0–E2 与 E4 已完成。尚待有效模型凭据下的 E3 真实模型评测和正式 Electron smoke；两者通过后才启动探索性黑盒。
> 权威设计：[PLOTAGENT-AGENT-FOUNDATION-DESIGN.md](./PLOTAGENT-AGENT-FOUNDATION-DESIGN.md)
> 编制日期：2026-08-18。

## 1. 目标与非目标

本计划把已确认的任务合同、领域说明、上下文、Pi 运行循环、工具、验证、权限与回滚、工作记忆、可观察性和评测体系落入当前代码，同时保持正式 Electron 主链可运行。

目标：

- 让 Agent 能持续完成“理解目标—检查/整理数据—形成 Intent—确认—执行—验证—修复—交付”；
- 最大化复用 Pi 的模型—工具内循环；
- 让 Core 的耐久任务状态、项目 revision 和真实产物成为权威；
- 保留现有 Agent Native renderer、34 图合同和 Matplotlib/Origin 能力；
- 每个阶段形成可回滚、可测试的独立提交。

非目标：

- 不重写 Pi；
- 不引入多 Agent；
- 不恢复 DataPreparationRecipe 自动匹配、候选索引或跨任务学习；
- 不重新设计 34 个 renderer 或 Origin 模板；
- 不在同一阶段同时替换合同、数据库、Pi、UI 和 renderer；
- 不通过关键词、正则或列名规则恢复程序语义路由。

## 2. 当前资产与迁移判断

| 当前资产 | 处理策略 |
|---|---|
| `WorkflowContext` | 拆分/迁移为 TaskEnvelope 与可重建 ContextSnapshot；迁移期保留 v1 读取 |
| `TaskDraft` | 演进为 Proposed TaskIntent 的模型输出合同，不直接成为执行授权 |
| `TaskPlan` / `CompiledTaskItem` | 保留为确认后确定性执行计划 |
| `TaskPlanExecutor` | 保留并增加 receipt、cancel、VerificationReport 和逐项恢复 |
| `WorkflowRepository` | 先增加 v2 Ledger/activation/event 表，不破坏 v1 表 |
| `PiAgentRuntime` | 收敛为 `PiRuntimeAdapter.run(AgentActivation) -> AgentYield` |
| 现有 inspect/preview 工具 | 迁移到统一 ToolGateway，保留实现与测试 |
| `TaskTracker` / TaskDrawer | 改为 TaskEvent 的用户投影，不再维护另一套任务真相 |
| 34 个 EngineProfile / renderer | 第一至第八阶段保持冻结，只消费其合同与验证结果 |
| workflow recipe replay/save | 不迁入新基础 Agent；新链稳定后清理旧公开入口 |

## 3. 总体迁移策略

采用“加法建设—垂直切片—单点切换—删除旧链”，避免长期双轨：

1. 先增加 v2 Schema、状态仓库和 adapter，不改变用户行为；
2. 以一个单图创建任务打通新链，但只在测试入口启用；
3. 补齐确认、执行、验证和恢复；
4. 正式 UI 一次切换到 v2；
5. 通过冻结回归后删除 v1 workflow/recipe 路由和兼容分支。

迁移期内部 feature gate 名称固定为 `agent_foundation_v2`，只用于隔离未完成链路；不得成为长期产品设置。数据库变化全部 additive，切换前不删除 v1 数据。每个 schema/event 都有版本，旧任务只读展示，不尝试用不完整信息伪造 v2 恢复。

## 4. 阶段总览

| 阶段 | 交付物 | 用户行为变化 | 主要门禁 |
|---|---|---|---|
| P0 | 冻结基线与影响清单 | 无 | 全量现状门禁 |
| P1 | v2 合同与 codegen | 无 | Schema/性质测试 |
| P2 | 耐久 Task Ledger 与状态机 | 无 | 状态/迁移/恢复测试 |
| P3 | 领域知识注册表与 ContextBuilder | 无 | 34 卡一致性/预算/安全 |
| P4 | ToolGateway、权限和 receipt | 无 | 工具/幂等/披露/权限 |
| P5 | PiRuntimeAdapter | 无 | fake provider 多轮/yield/abort |
| P6 | 单任务端到端垂直切片 | 测试 gate 下可用 | 确认—执行—验证主链 |
| P7 | scoped repair、partial 与批量 | gate 下增强 | 恢复/部分成功/无循环 |
| P8 | 取消、重启、lease 与完整权限 | gate 下增强 | chaos/restart/side effects |
| P9 | 对话 UI、任务中心与可观察性 | 正式 UI 切换 | Vitest + Windows 黑盒 |
| P10 | 评测、发布门与旧链清理 | 新链成为唯一入口 | E0–E6 + 删除兼容 |

### 验收时序（2026-08-18 冻结）

- P6 的 11 项正式 Electron 测试只是单任务垂直切片的阶段门禁，不是完整产品黑盒或发布验收；
- P7、P8、P9、P10 按顺序施工，每阶段先完成代码、自动化测试、静态门禁和必要的机械证据；
- P7–P10 期间不提前发起新一轮探索性黑盒，避免用未完成产品反复消耗黑盒窗口并混淆阶段结论；
- P10 完成、旧链清理、全量发布门通过并冻结 clean commit 后，才向探索性测试会话索取独立测试计划；
- 最终探索性黑盒由本窗口在正式 Windows Electron 入口执行，结果与 P6 阶段报告分开归档。

## 5. P0：冻结基线

### 工作

- 记录起始 commit、依赖、Python/Node/Origin 版本和当前工作树；
- 运行 Python、Ruff、mypy、codegen check、typecheck、ESLint、Vitest、production build；
- 固定 34 图库存与当前 renderer source identity；
- 建立本计划的变更影响清单和测试选择表；
- 明确 `.pytest-tmp/`、`outputs/` 等运行产物不进入提交。

### 退出条件

- 基线缺陷与本轮新增缺陷可区分；
- 当前正式 UI 主链可重复启动；
- 没有未归属的源文件改动。

### 建议提交

无源码提交；保存本地基线报告。若需补测试清单，独立 `test(agent): freeze foundation baseline`。

## 6. P1：v2 合同与 codegen

### 新增/演进合同

- `TaskEnvelope`、`TaskIntent`、`TaskIntentVersion`；
- `TaskState`、`TaskItemState` 与合法 transition；
- `AgentActivation`、`AgentActivationReason`；
- `AgentYield` 判别联合；
- `ExecutionGrant` 与 permission scope；
- `ToolReceipt`、`SideEffectReceipt`；
- `VerificationClaim`、`VerificationFinding`、`VerificationReport`；
- `TaskEvent`、`TaskCheckpoint`、双层 `TaskBudget`；
- 统一 `TaskError` 分类与 retry/repair/safety 属性。

### 约束

- Python Pydantic 是合同源，通过现有 codegen 生成 TS；
- 所有 ID、版本、hash、枚举和最大长度严格约束；
- AgentYield、TaskEvent、VerificationFinding 使用 discriminator；
- 不在本阶段接入数据库、Pi 或 UI；
- `TaskPlan` 暂保留 v1 名称，避免无行为收益的大规模 rename。

### 测试

- Schema round-trip 与 Python/TS 编译；
- 所有合法/非法状态转移；
- stale task/activation version；
- receipt 与 side-effect 元数据一致性；
- budget 上限与不可为负；
- `completed_verified` 必需字段性质测试；
- codegen `--check`。

### 退出条件

- 合同能独立表达设计文档所有状态与边界；
- 不修改当前正式运行结果；
- v1/v2 类型命名不会被 UI 混用。

### 建议提交

`feat(agent-contracts): define durable task protocol`

## 7. P2：耐久 Task Ledger 与状态机

实现记录（2026-08-18）：

- 项目 schema 已从 v5 增量迁移至 v6；旧 workflow 表原样保留；
- 已建立 task、intent、activation、event、checkpoint、receipt、verification、lease
  八类严格表；
- `TaskLedgerRepository` 已实现 Core 白名单状态迁移、逐项状态、幂等、迟到 yield
  拒绝、事务检查点、重启恢复和 writer lease；
- 内部 `agent.tasks.*` RPC 已接入，但正式 UI 尚未切换，因此用户行为不变；
- 已通过事务故障、v5 迁移、重启、并发租约、批量子项隔离及完整 Python/Node
  回归门禁。

### 工作

- 在项目数据库增加 v2 task、item、intent、activation、event、checkpoint、receipt、verification 表；
- 实现 append-only TaskEvent 与事务内 snapshot 更新；
- 实现 Core `task.create/get/list/advance/accept_yield/record_user_event/cancel`；
- transition 由 Core 白名单驱动，模型和 Main 不能直接写 state；
- activation/event 使用唯一 ID 去重；
- 增加 writer lease 与 project revision 检查接口，但本阶段不启动外部执行；
- 为旧 workflow task 提供只读 legacy projection，不把旧状态升级成虚假 v2 checkpoint。

### 测试

- 每条合法/非法 transition；
- 重复 event、乱序 event、迟到 yield；
- 事务中断后 event/snapshot 一致；
- 关闭并重开 Core 后恢复；
- 旧数据库 additive migration；
- 两个 writer 竞争和 lease 过期；
- TaskItem 部分状态不污染其他项。

### 退出条件

- 仅凭数据库即可回答任务处于何阶段、等待什么、哪些项成功以及下一动作；
- Main/Pi 全部退出后状态仍可恢复；
- 无需读取聊天历史重建 TaskState。

### 建议提交

`feat(tasks): add durable task ledger`

## 8. P3：领域知识与 ContextBuilder

实现记录（2026-08-18）：

- 已定义并 codegen 发布 `ChartKnowledgeCard`、`CalculationContract`、
  `AgentContextSnapshot`、目录、比较、示例、untrusted source 和 tool contract；
- 已为 34 个正式图类建立一一对应的知识卡；角色、对象、repeatable object 与
  capability 直接嵌入 `EngineProfile` 并以 canonical hash 绑定，没有维护第二份手抄真值；
- 已将 8 个现有冻结计算规格发布为版本化计算合同，算法版本和 Spec Schema hash
  直接绑定现有 calculation union；
- 官方资料与本机审核事实只以官方 URL、审核版本、claim 和证据摘要进入 Agent
  上下文，不暴露模板文件、PID、LabTalk、Origin C、路径或 renderer 私有对象；
- `DomainKnowledgeRegistry` 已提供目录、单卡、比较、计算合同和示例的 fail-closed
  查询；缺失与版本不匹配使用稳定错误码；
- `ContextBuilder` 已严格核对 TaskEnvelope、TaskCheckpoint、AgentActivation、选中来源、
  工具 allowlist、权限阶段和双层 disclosure budget；未选图时只提供 34 图目录，选图后
  只注入对应卡及其关联计算合同；
- 数据名、列名和预览值在合同中永久标为 untrusted，不能更改工具或权限；上下文使用
  canonical hash 防篡改，可从 Ledger 权威状态重建；
- 当前正式 UI/Pi 尚未消费这些新增合同，因此本阶段不改变用户行为。

### 工作

- 定义 `ChartKnowledgeCard` 与 `CalculationContract` Schema；
- 为 34 个正式 EngineProfile 建立卡片库存；
- 从 EngineProfile 生成/校验 roles、objects、capabilities，不手抄第二份真值；
- 绑定 Origin 官方 URL、本机版本/模板证据和 verification claim；
- 实现 `list_chart_catalog/get_chart_knowledge/compare_chart_profiles/get_calculation_contract/get_domain_example`；
- 实现 ContextBuilder：Task Ledger + 选择数据轻预览 + 按需知识 + 当前工具 + budget；
- 所有数据 payload 保持 untrusted 标记与披露审计。

### 测试

- 34 卡完整性、唯一性、版本与引用；
- EngineProfile/知识卡/claim 无漂移；
- selected profile 只注入对应卡；
- 未选图时目录可读但程序不自动选择；
- knowledge unavailable/version mismatch fail closed；
- prompt injection fixture 不改变 system/tool 权限；
- context budget、分页和权限裁剪；
- Origin 网页与本机版本冲突时使用审查过的版本事实。

### 退出条件

- system prompt 只保留短 D0 constitution；
- 模型可按需取得准确图类知识；
- 不存在关键词/正则/列名语义路由。

### 建议提交

`feat(domain): add versioned chart knowledge registry`

## 9. P4：ToolGateway、权限与 receipt

里程碑记录（2026-08-18）：

- 已新增公开 `ToolContract`、`ToolInvocation`、`AgentToolResult` 与五类 typed error，
  并通过现有 codegen 发布 JSON Schema/TypeScript；
- 已建立 Core 所有权的统一 `ToolGateway`：调用前校验 task/activation/checkpoint、
  TaskState、allowlist、权限阶段、参数 hash、输入 Schema、调用/披露/Origin 预算与截止时间；
  调用后校验输出 Schema、公开副作用等级、披露量和结果合同；
- 已把 P3 的五个知识查询注册成第一批 P0 工具。工具只返回 renderer-neutral 公共合同，
  未把后端模板、命令、路径或对象编号暴露给 Agent；
- 已将现有 8 个只读数据检查实现适配进同一 Gateway：保留原始分页、抽样、字段画像、
  值搜索、结构比较、仪器元数据和 `InspectionAudit` 行为，同时为每次结果补充来源版本/hash
  provenance；v1 正式入口暂不伪造 v2 task authority，等 P6 垂直切片再单点切换；
- Gateway 可按 activation allowlist 输出实际 JSON Schema 定义，供下一阶段 Pi adapter 注册工具；
- untrusted payload 无法增加 allowlist、权限或预算，错误统一返回可修复/需用户/瞬态/
  不支持/致命五类结构结果；
- `ToolInvocation` 已固定 P1 幂等键以及 P2/P3 item-scoped `ExecutionGrant` 要求；Gateway
  会核对 grant 的 task/version/revision/phase/expiry/item/operation，拒绝过期、越权和 stale 授权；
- 每次调用可确定性生成 `ToolReceipt`，记录输入/输出 hash、公开副作用、错误、时长、披露量、
  Origin session 与 project revision；Ledger 事务内持久化回执并累计 task-wide budget，重复回执不重复
  计费，超预算时回执、事件和 checkpoint 一并回滚；
- 已新增 task/version/source-scoped 的临时数据工作区。原始来源不修改；每次整理生成不可变
  `DataViewHandle`，记录父句柄、根来源、操作 hash、数据 hash、Parquet artifact hash 和完整 lineage；
  临时索引位于项目 `tmp/agent-data-v2`，可在 Core 重启后恢复，按 TTL 清理，不进入正式项目对象、
  package 或 project revision；
- 已注册 P1 `stage_source_data` / `apply_data_view_operation` 与 P0
  `inspect_data_view` / `preview_data_view`。来源必须精确属于当前 task authority，P0 预览限制为
  24 字段 × 40 行并计入披露预算；P1 只产生 staged receipt，不消耗 ExecutionGrant，也不改变
  project revision；
- 数据操作是封闭的 typed union：字段选择/重命名/显式类型转换、筛选、稳定排序、去重、有限算术派生、
  注册单位换算、wide↔long、同构纵向拼接、带声明 cardinality 的 keyed join 和显式聚合。不存在
  任意 Python/SQL/正则执行；缺失 join key、隐式聚合、多对多关系、单位不兼容、结果为空和字段覆盖均
  fail closed；
- preview 与正式 staged operation 使用同一 `EngineDataView`/Parquet 执行实现；落盘后按 artifact/data
  双 hash 读回，Provider 不能替换授权 source identity 或字段选择；跨 task/version、过期或损坏句柄均拒绝；
- 已新增 task/version/item-scoped 的绘图沙箱与 `SandboxPlotHandle`。P1
  `preview_plot` / `preview_origin_plot` / `apply_plot_edits` /
  `apply_origin_plot_edits` 只写临时子项目，P0 `inspect_plot` 只读取公共结果；它们不增加正式
  project revision，也不写入正式 PlotDocument、项目对象或 package；
- Matplotlib 预演实际复用 34 图正式 renderer 库并产生 PNG/SVG；Origin 预演实际复用受资格约束的
  官方模板绑定器并产生可编辑 OPJU。每次预演/编辑都保存不可变数据根来源、公开 PlotDocument、
  artifact hash、机械 readback 和 action lineage，支持 Core 重启后继续检查；
- Agent 只看到 semantic object ID、对象类型、数据/style hash 与产物句柄；Origin native ref、模板路径、
  LabTalk/Origin C、renderer 私有对象和任意脚本不会进入公开合同。每次工具调用只接受一个 typed
  公共编辑，错误时不会留下半条已提交编辑链；
- staged plot 工具产生 `staged_plot` receipt，Origin 另产生 `origin_session` receipt；Origin 不提供内联
  PNG 时明确返回 warning，不用 Matplotlib 图片冒充 Origin 图；跨 task/version/item、后端不匹配、
  stale plot version、非法对象、过期/损坏 artifact 均 fail closed；
- P4 仍为 additive 基础设施：正式 UI/Pi 尚未消费新工具，P2 正式项目写入将在 P6 垂直切片中接入，
  因而本阶段不改变用户行为，也不修改 34 图 renderer 语义或视觉默认态。

### 工作

- 将现有 inspect/preview 工具迁入统一 ToolGateway；
- 工具按 P0 只读、P1 staged、P2 confirmed write、P3 expanded risk 分类；
- 根据 TaskState、AgentActivation 和 ExecutionGrant 动态暴露工具；
- 接入 Pi `beforeToolCall/afterToolCall`，但最终授权仍由 Core ToolGateway 校验；
- 所有工具返回 result、lineage、validation、side effects、receipt 和 typed error；
- 数据工具使用不可变 DataViewHandle 链；
- 补齐已确认的关系检查、类型转换、join、去重、显式聚合、沙箱渲染、后端读回和局部修正能力；
- 为写入工具加入稳定 idempotency key 与 reconcile API。

### 拆分提交

1. `refactor(agent-tools): route inspection through tool gateway`
2. `feat(data-tools): complete bounded data operations`
3. `feat(render-tools): add sandbox render and native readback`
4. `feat(agent-tools): enforce grants and receipts`

### 测试

- 每个工具 Schema、权限阶段和负例；
- 原始来源不可变与 lineage；
- 数据披露预算；
- preview/execute 同实现一致性；
- 幂等与断连 reconcile；
- 跨项目/对象/版本越权；
- untrusted 数据不能改变工具权限；
- renderer 工具仅返回公共语义，不泄露后端脚本。

### 退出条件

- Pi 只能通过 ToolGateway 接触项目；
- Main 中不再手写另一套工具权限；
- 所有副作用可由 receipt 追踪和恢复。

## 10. P5：PiRuntimeAdapter

里程碑记录（2026-08-18）：

- 已新增 test-gated `PiRuntimeAdapterV2.run(AgentActivation) -> AgentYieldContract`；每次运行先由
  Core host 重建并校验 `AgentContextSnapshot`、动态工具定义、终态 Schema 与 Provider 配置，
  不依赖 Pi 内存中的旧消息恢复任务真相；
- 工具列表完全来自 Core activation allowlist 与 `ToolContract`，adapter 不维护第二份手写业务工具表。
  context tool ref、执行合同、任务状态、权限阶段和 P2/P3 Core-bound item/grant 不一致时，在调用模型前拒绝；
- Pi 继续负责模型—工具内循环、顺序执行、自动继续、turn stop、steering、stream/provider 抽象与 abort；
  Core 继续独占上下文构建、权限、工具执行、项目 revision、回执和终态验证；
- 模型参数中不含 execution grant 或幂等键。adapter 根据 Core-bound authority 生成
  `ToolInvocation`、argument hash、deadline、调用序号和 P1–P3 idempotency key，再交给 ToolGateway host；
- 只允许保留字工具 `submit_agent_yield` 结束 activation；其参数必须经过 Core `validateYield`。
  正常结束但未调用终态工具稳定返回 `AGENT_YIELD_MISSING`，Core 工具/终态身份错配则 fail closed；
- 同时执行 activation 与 task-wide 的 model call/turn、token、tool call、披露 scalar、估算成本和 wall-time
  预算；超限返回 typed `budget_exhausted`，不伪造 TaskState transition；
- abort 已覆盖 ContextBuilder/host prepare 与 Pi 运行阶段；新 activation 会取消旧 generation，迟到的
  tool result/yield 在接受前重新核对 generation，不会覆盖新任务版本；Provider 中断、timeout、supersede
  均转成稳定的 typed yield；
- activation trace 只包含 task/version/activation、阶段、工具名和调用 ID，不包含 API key、prompt、
  原始参数或工具 payload。Provider 凭证只经 Main host 的 `getApiKey` 进入 Pi；
- P5 保持 additive：正式 Electron 仍只有 v1 runtime 是活动入口，v2 仅由 fake-provider 测试直接调用；
  P6 建立 Core TaskPump/host 后再接第一条测试 gate 主链，避免出现两套同时消费用户请求的 Agent loop。

### 工作

- 将 `PiAgentRuntime.run(params)` 收敛为 `run(AgentActivation) -> AgentYield`；
- 每次 activation 从 ContextBuilder 输入开始，`messages=[]` 不再意味着丢失任务状态；
- Pi 内循环保留 prompt、工具循环、sequential execution、turn stop、continue、abort 和 streaming；
- 接入 transformContext、before/after tool hook 和 task/activation trace；
- 只接受 typed yield 工具；正常 agent_end 无 yield 返回 `AGENT_YIELD_MISSING`；
- 同时执行 per-activation 与 task-wide budget；
- 支持 steering 的消息通道，但 task version 由 Core 控制；
- Provider 凭证继续只存在 Main 信任边界。

### 测试

- fake provider：一轮 intent、多轮 inspection、needs_input、unsupported、blocked、repair yield；
- validation reject 后模型可在预算内修正；
- turn/token/tool/time budget；
- abort、timeout、Provider 断连和 superseded activation；
- 迟到工具结果/yield 被拒绝；
- Pi 事件映射为 activation trace，不直接成为 TaskState；
- 不将 API key、原始敏感 payload 写入 event/log。

### 退出条件

- Pi adapter 不调用 task transition，只返回 yield；
- adapter 可替换 stream/provider 测试；
- 当前 v1 Pi runtime 测试全部迁移或明确保留，不存在两套活动 Agent loop。

### 建议提交

`refactor(agent): adapt Pi runtime to durable activations`

## 11. P6：单任务端到端垂直切片

### 首个范围

只打通“一份已导入数据 + 用户已选正式图类 + 创建一张图 + 可选基础视觉动作”，不先做批量、修复或 Origin 故障恢复。

### 工作

- 实现 Main `TaskPump` 与 Core `task.advance` next action；
- 新 UI 请求创建 TaskEnvelope，不直接调用旧 `workflow.prepare`；
- `new_task` activation 由 Pi 检查数据并产生 `intent_ready`；
- Core 编译 TaskIntent 为现有 TaskPlan，生成 staged 数据预览和确认卡；
- 用户确认后签发 ExecutionGrant；
- 复用 TaskPlanExecutor 执行单个 TaskItem；
- 增加最小 VerificationReport：来源、绑定、PlotDocument、项目 revision、渲染产物；
- 通过后进入 completed_verified，UI 展示 plot ID/version 和产物；
- 仅在 `agent_foundation_v2` 测试 gate 下启用。

### 当前实现进度（2026-08-18）

- Main 已有 pull-based `TaskPump`，只执行 Core 返回的 activation，并在 durable wait 立即退出；
- Core 已有 `DurableTaskCoordinator`，可幂等创建 `new_task` activation，且 activation 运行期间不提前
  改写 task version；
- `TaskEnvelope` 与 `AgentContextSnapshot` 已从模糊 source ID 收紧为精确
  `source_dataset_id + source_version + content_hash`，防止任务途中读到另一数据版本；
- Core activation host 已能从真实项目构造无初始单元格泄露的上下文，注册审核过的领域/数据检查工具，
  执行 P0 调用并持久化 ToolReceipt；
- Main host 已将 Core authority、模型服务配置与 Pi runtime 组合，API key 只停留在 Main 内存，不进入
  Core context、task event 或 renderer；
- Core 已校验 terminal yield 的 activation/task identity、context hash 与 TaskIntent content hash；
- Core 已将合法 `TaskIntent` 对照冻结的数据版本、字段别名和图形合同编译为持久 `TaskPlan`；非法绑定在
  确认卡出现前拒绝，且不改变项目 revision；
- 用户确认事件、计划 hash 与最小 P2 `ExecutionGrant` 原子持久化；确认后复用确定性 executor 完成单项
  create、ToolReceipt、PlotDocument 读回、VerificationReport 和 `completed_verified`；
- Main 在 `PLOTAGENT_AGENT_FOUNDATION_V2=1` 下只接管“一份数据 + 一个已选图类 + 新建一图”，其他请求
  保持 v1；正式对话可看到真实读取/检查/规划/校验阶段，并复用字段确认卡完成确认与执行；
- gate 默认关闭；P6 已在正式 Windows Electron 中完成 11 项阶段门禁，结果为 11 PASS / 0 FAIL /
  0 BLOCKED / 0 UNVERIFIED。该结果只证明单任务切片满足 P6 退出条件；P7 才开始扩大到批量、partial
  与 scoped repair。

### 测试

- 明确任务无需无效追问；
- 只读 inspection → intent → confirmation → execute → verify；
- 拒绝确认零副作用；
- 修改确认内容使旧 intent/grant 失效；
- Core 拒绝非法绑定时 Pi 在 activation 内修正；
- 成功后版本/receipt/VerificationReport 完整；
- Electron/Main/Core 中途退出后恢复等待状态；
- 同一 idempotency key 不重复创建图。

### 退出条件

- 一条真实主链不再依赖旧 workflow 状态；
- 用户能从正式对话看到真实阶段与确认卡；
- 仍未切换默认入口，现有黑盒基线不受影响。

### 建议提交

1. `feat(tasks): add local task pump`
2. `feat(tasks): execute confirmed single-item plans`
3. `feat(tasks): complete verified single-plot tasks`

## 12. P7：验证修复、partial 与批量

### 工作

- 将已确认七层验证接入统一 VerificationReport；
- 对失败做 transient/technical/semantic/stale/unsupported/safety 分类；
- 生成 scoped RepairAssignment 和 `verification_failed` activation；
- 只开放失败 claim 与对象范围内的诊断/修复工具；
- 实现 no-progress signature、相同修复拒绝和 repair budget；
- 扩展到 1–64 TaskItem 的批量计划；
- TaskItem 逐项原子提交，成功项冻结，失败项独立 repair/retry；
- 语义变化生成新 TaskIntentVersion 并重新确认；
- 用户可接受 partial、仅重试失败项或取消剩余项。

### 当前实现进度（2026-08-18）

- v2 Main 入口已从 P6 的单数据/单图类限制扩为 1–8 个不可变数据源与有界多图类任务；Core
  接受 1–64 个显式 TaskItem，并继续逐项校验 source/profile authority；
- 确认后的批量执行按 TaskItem 串行原子推进，成功项立即持久化 PlotDocument、receipt 与 passed
  VerificationReport；后续项失败不会回滚或重复执行成功项；
- 执行错误已分类并生成 failed VerificationReport。可修复项进入 `repairable_failed`，任务进入
  `partial`；不可修复项保持独立失败证据；
- `verification_failed` activation 会把真实失败报告注入 AgentContext，只允许在失败 item/report 范围内
  返回 `retry_execution`，不允许借修复改变已确认字段、图类或输出范围；
- 修复只重试失败项；一次同构重试仍失败即以 `REPAIR_NO_PROGRESS` 收口，不形成 Agent 循环。最终成功时
  completion 仅引用每项最新 passed report 与 receipt；
- Main 已能从 partial 重新进入耐久 repair pump；用户稍后也可从任务卡显式触发“仅重试失败项”。
- 用户补充答案或纠正计划时，原文作为耐久 UserTaskEvent 保存；Core 生成
  `user_answered` / `user_corrected` activation。新语义必须沿用同一 intent_id、递增
  intent_version，并进入 `awaiting_reconfirmation`；旧 ExecutionGrant 不会被复用。

### 测试

- renderer 技术错误自动修复且无需重新确认；
- 字段/图类/统计定义变化必须重新确认；
- 相同失败不会循环；
- 3 项中 2 成功 1 失败只修失败项；
- repair 后重跑原 claim 和影响 claim；
- 预算耗尽保留成功项与 staged 证据；
- 真实模型 batch mapping、multiple-data-one-chart 和 mixed task；
- 非法自动聚合、排序、单位假设和对象绑定稳定拒绝。

### 退出条件

- Agent 能从 VerificationReport 继续工作而非结束于第一份 TaskDraft；
- partial 的 UI、Ledger、项目和产物完全一致；
- 不依赖多 Agent 或写入并行。

### 建议提交

1. `feat(verification): add structured task reports`
2. `feat(agent): add scoped verification repair`
3. `feat(tasks): preserve partial batch success`

## 13. P8：权限、取消、重启与外部副作用

### 工作

- 完整实现 P0/P1/P2/P3 permission gate 与最小 ExecutionGrant；
- UI → Main/Pi → Core → ToolGateway → renderer/Origin 贯通 cancel token；
- 原子提交临界区完成到一致边界后停止；
- writer lease、Origin lease、revision conflict 和 stale activation 恢复；
- 外部文件 staged → verify → atomic publish，默认不覆盖；
- 只终止身份可验证的本任务 Origin 实例；
- restart 时根据 checkpoint 恢复 awaiting_input、confirmation、blocked、executing reconcile 或 repair；
- 实现 user_answered、user_corrected、resume_after_restart 和 external_blocker_cleared activation；
- follow-up 创建关联新任务，不改写已完成历史。

### 测试

- 每个权限级别的 allow/deny；
- 扩大数据披露、覆盖文件、改变语义的 P3 确认；
- Pi、Core、renderer、Origin 各阶段取消；
- 写工具返回前断连后的 receipt reconcile；
- Electron/Core 重启恢复；
- 两个 writer、lease 过期、stale revision；
- 用户 Origin 不被自动化终止；
- 外部文件存在、磁盘满、路径不可写和 Origin 不可用。

### 退出条件

- 任意中断后状态可解释、可恢复且不重复副作用；
- 用户无需理解内部事务即可知道保留了什么、下一步是什么。

### 建议提交

1. `feat(tasks): enforce execution grants`
2. `feat(tasks): add end-to-end cancellation`
3. `feat(tasks): resume tasks after restart`

### 完成记录

- P0/P1/P2/P3 继续由 Core 上下文、ToolGateway 和最小 ExecutionGrant 共同执行；公开入口不提供绕过确认的 P3 扩权动作；
- ToolGateway 现有独立 P3 边界回归：`expanded_risk` 工具在 P2 activation/grant 下稳定拒绝，只接受同任务、同 item、同 revision 的显式 P3 grant；
- 桌面取消优先定位 durable task，只中止该任务的 Pi activation，并在原子 item 边界保留已成功结果、取消其余 item；不通过终止全部 Origin 实例实现取消；
- renderer/Origin 已进入的原子 item 不会被提前标成 cancelled；取消请求保持 `cancelling`，待该 item 的 plot、receipt 和 verification 一致落盘后，保留它并取消剩余 item，避免“图已写入但 Ledger 不知情”的竞态；
- execution writer lease、过期 activation、写工具返回前断连后的 receipt/plot reconcile，以及 blocked 后显式恢复均已有持久化路径；
- PNG、SVG、OPJU 先写同卷私有 staging，校验大小和 SHA-256 后无覆盖原子发布；已有目标、无效目录和发布 I/O 失败返回稳定公开错误；
- awaiting input/confirmation 直接从 checkpoint 恢复；过期 activation 使用 `resume_after_restart`，外部阻断解除使用 `external_blocker_cleared`，repairing 使用定向 repair activation；
- follow-up 使用新 TaskEnvelope 的 `parent_task_id + relationship=follow_up` 关联已结束或 partial 的父任务，不改写父任务事件历史。

## 14. P9：正式对话 UI、任务中心与可观察性

### 工作

- 正式 UI 默认切换到 v2 Task API；
- 对话展示用户消息、Agent 说明、数据映射确认卡、具体追问、结果卡；
- 阶段反馈由 TaskEvent 驱动：检查数据、整理数据、字段绑定、调用 renderer、验证、导出；
- 未知工作显示状态与持续时间，不显示伪百分比/ETA；
- TaskDrawer 展示 TaskItem、partial、失败原因、保留结果、retry failed only、取消和恢复；
- 增加 undo/redo 对项目 revision 的可见入口；
- 成功导出给出明确文件/格式/大小/可编辑性反馈；
- diagnostics 仅展示安全摘要与 diagnostic ID；
- 键盘、焦点、屏幕阅读器、CJK、窄窗口和长任务状态完整。

### 测试

- React/Vitest 覆盖所有状态和事件乱序；
- 确认卡的数据预览与字段角色同源；
- 真实阶段不得由 timeout 模拟；
- stale Agent 响应不覆盖当前卡片；
- 取消、重试、撤销、重启和 partial；
- Windows Electron 正式入口黑盒；
- 导出成功/失败/Origin 不可用反馈；
- accessibility smoke。

### 退出条件

- UI 不再直接维护独立任务真相；
- 用户可以仅通过对话与任务中心理解当前状态、做必要确认并恢复失败任务；
- v1 默认入口关闭，但保留一个短期只读诊断开关供回滚。

### 建议提交

1. `feat(desktop): present durable agent tasks`
2. `feat(desktop): add real-time task progress and recovery`
3. `feat(desktop): switch to agent foundation v2`

### 完成记录

- Agent 追问不再被降级为普通错误；回复通过 `workflow_run_id=task:<id>` 续接同一 durable task、同一 checkpoint 与同一任务历史；
- 正式对话中的计划确认卡直接展示来自 Core 计划绑定的原始字段、字段角色和同一数据表样本，不维护第二份映射真相；
- 执行中的提示来自 Agent runtime 与 Core TaskEvent，覆盖上下文、数据检查、合同校验、renderer/验证和结果读取，不使用 timeout 伪造百分比或 ETA；
- TaskDrawer 读取 durable task checkpoint，展示逐项状态、partial 已保留 plot/version、可重试失败、安全诊断 ID、取消和仅重试失败项；P10 已删除 legacy 任务公开投影；
- undo/redo、导出成功/失败、Origin 可用性、聊天气泡、键盘焦点与 aria-live 延续正式 UI 现有能力；新增状态解析与任务中心回归覆盖续接、partial、诊断和恢复入口。

## 15. P10：评测、发布与旧链清理

### 工作

- 实现新 EvalCase、EvalPolicy、trial、grader 和 evidence manifest；
- 将真实缺陷、旧 SEQ-70 和黑盒用例迁移为新 suite 版本；
- 跑 E0–E6：确定性、真实模型多 trial、34 图资格、正式 UI、性能、安全和恢复；
- Agent 改动未触碰 renderer source scope 时不无理由重做全部视觉；仍运行代表 Matplotlib/Origin/OPJU 主链；
- 若 EngineProfile、renderer 或 source identity 变化，按影响规则重建相应视觉与 Origin 证据；
- 通过切换观察期后删除 v1 workflow RPC、旧 Pi runtime、recipe replay/save 公共入口、legacy UI 和 feature gate；
- 数据库旧表保留只读迁移期后再单独制定清理方案，不在发布提交中破坏用户项目。

### 发布门

- E0–E2 100%；
- Agent critical regression 3/3；
- 错误自动绑定、无效追问、成功项重复执行为 0；
- 必测 UI 无 FAIL/BLOCKED/UNVERIFIED；
- 34 图合同资格当前；
- 代表 OPJU live + fresh reopen；
- 性能、成本、cancel、restart、privacy 与 diagnostics 达标；
- 同一冻结 clean commit；
- 旧入口删除后重新跑完整门禁。

### 建议提交

1. `test(agent): add foundation v2 evaluation suites`
2. `refactor(workflows): remove legacy agent workflow`
3. `test(release): qualify durable agent foundation`

### 当前完成记录

- 正式 Electron/Main 只实例化 `AgentFoundationRuntime`；旧 `PiAgentRuntime`、feature gate、v1 workflow/recipe IPC、preload、renderer UI 和 Core RPC 已删除；数据库旧表仅作为不破坏历史项目的内部迁移资产保留；
- v2 支持“选定数据但未选图类”的自然语言规划，以及“只选当前 plot”的编辑任务；图类不明确时由 Agent 追问，不再由 UI 先行拒绝；
- 旧 24 项 SEQ-70 已迁移为版本化 EvalCase：E3 18 项各 3 次，E2 6 项各 1 次，并生成 grader、evidence manifest 和统一发布报告；
- Python 全量 702 项、Node 177 项、production build、Ruff、mypy 184 模块、ESLint、codegen 均通过；Engine/Matplotlib/Origin 机械门禁 325 项通过；
- 本轮未修改 `src/plotagent/engine` renderer source scope，34 图既有视觉签名与 fresh-reopen OPJU 证据可完整索引，因此不重做视觉审查；
- E3 调试已到达真实 Provider，但本机当前保存的 DeepSeek 凭据返回 HTTP 401。该项属于发布阻断，必须用有效凭据从干净 commit 重跑，不得以 mock、旧结果或删用例代替。

## 16. 每阶段统一质量门

每个源代码提交至少满足：

1. 只 stage 责任文件，保留用户/运行产物；
2. `git diff --check`；
3. Ruff 与目标 mypy；
4. contracts codegen `--check`；
5. Python 定向测试；
6. TypeScript typecheck、ESLint、相关 Vitest；
7. 行为阶段运行 production build；
8. milestone 运行完整 Python/Node 门禁；
9. 任何数据库 migration 有旧项目打开/重启测试；
10. 任何 UI cutover 有正式 Electron 黑盒；
11. 任何 renderer source-scope 变化按视觉影响规则处理；
12. 提交信息描述单一可回滚能力。

## 17. 回滚策略

- P1–P5 是 additive，回滚提交不会改变既有用户主链；
- P6–P8 由内部 gate 隔离，失败时关闭 gate 并保留 v2 task 证据；
- P9 切换通过一个独立 commit 完成，可在未产生新格式项目写入前回退；
- v2 已产生项目状态后不得简单切回会误读状态的 v1；此时只允许只读打开或向前修复；
- P10 删除旧链前冻结最后一个可回退 tag/commit；
- 数据库表删除、旧数据压缩和长期迁移不与运行时切换同批进行。

## 18. 禁止跨阶段偷跑

- P1 不实现状态业务；
- P2 不调用模型；
- P3 不根据自然语言自动选择图类；
- P4 不开放任意代码执行；
- P5 不直接执行项目写入；
- P6 不同时加入批量、repair 和复杂 Origin 恢复；
- P7 不引入多 Agent；
- P8 不通过终止全部 Origin 解决取消；
- P9 不用计时器伪造 Agent 阶段；
- P10 不因失败删除用例或临时缩小发布范围。

## 19. 历史第一施工节点（已完成）

下一次代码改动只执行 P0/P1：

1. 冻结当前 `c302ee0` 之后的文档基线与现状测试；
2. 在 `src/plotagent/contracts/` 增加 v2 durable task 合同；
3. 接入现有 codegen，生成 shared TS；
4. 增加纯合同/状态性质测试；
5. 不改 `workflow_service.py`、`pi-runtime.ts`、数据库、UI、renderer 或 Origin；
6. 门禁通过后提交 `feat(agent-contracts): define durable task protocol`。

该节点的完成只证明新架构有稳定语言，不宣称新 Agent 已经上线。
