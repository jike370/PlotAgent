# PlotAgent Agent 基础设施施工计划

> 状态：P0–P3 已完成；P4 待施工。
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

## 19. 第一施工节点

下一次代码改动只执行 P0/P1：

1. 冻结当前 `c302ee0` 之后的文档基线与现状测试；
2. 在 `src/plotagent/contracts/` 增加 v2 durable task 合同；
3. 接入现有 codegen，生成 shared TS；
4. 增加纯合同/状态性质测试；
5. 不改 `workflow_service.py`、`pi-runtime.ts`、数据库、UI、renderer 或 Origin；
6. 门禁通过后提交 `feat(agent-contracts): define durable task protocol`。

该节点的完成只证明新架构有稳定语言，不宣称新 Agent 已经上线。
