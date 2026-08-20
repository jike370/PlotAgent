# PlotAgent Agent 任务状态与确定性测试矩阵

> 状态：2026-08-20 冻结基线。本文是《Agent 任务状态合同》的可执行测试索引。
>
> 适用顺序：先通过本文全部确定性测试且不调用真实模型，再冻结源码进行 Windows UI 黑盒，最后运行一次 SEQ-70。UI 黑盒与 SEQ-70 不能替代本矩阵。

## 1. 判定口径

- Core 的 durable task checkpoint、TaskItem、ExecutionGrant、receipt、verification report 和 project revision 是权威事实。
- “追问”“确认”“重新确认”“跳过”“取消”和“恢复”必须是类型化事件，不能从聊天文案猜状态。
- 确定性测试使用受控 Agent yield 或假 Core；不得发起真实 Provider 请求。
- 每个写入场景同时核对项目副作用。确认前、追问中、拒绝后、执行前取消和 stale 响应均不得修改项目。
- 技术重试只重放相同授权；语义变化必须形成新意图、新计划并重新确认。
- 所有成功项均不可重复执行；取消只停止后续工作，不等于撤销已提交结果。

## 2. 用户阶段与内部状态投影

| 用户阶段 | Core 状态 | 用户可见含义 |
|---|---|---|
| 规划 | `created`、`investigating`、`intent_staged` | Agent 正在检查上下文并形成结构化任务 |
| 追问 | `awaiting_input` | 缺少会改变结果的信息，等待用户回答 |
| 确认 | `awaiting_confirmation` | 首版计划已冻结，确认前无正式副作用 |
| 执行 | `executing`、`verifying`、`delivering` | 按已确认授权执行、验证并整理结果 |
| 部分失败 | `partial` | 成功项已保留，失败项等待处理 |
| 修复 | `repairing` | Agent 仅处理语义失败项或验证失败项 |
| 重新确认 | `awaiting_reconfirmation` | 修订会产生新副作用，旧授权失效 |
| 跳过 | `completed_verified` + `completed_with_skips` | 用户接受成功子集，其余明确跳过 |
| 取消 | `cancelling` → `cancelled` | 停止启动新项；原子边界内已提交结果保留 |
| 恢复 | `blocked` 或可恢复的非终态 → 合法后继状态 | 外部条件满足或进程恢复后从准确检查点继续 |
| 重启 | 状态本身不变，或仅对中断激活/原子项做确定性对账 | 不从头执行、不复用过期授权、不伪造终态 |

### 2.1 Core 任务状态闭集

表中列出每个状态唯一允许的直接后继；同状态幂等读取不记作转换。没有列出的边必须由契约拒绝。

| 起点 | 允许的直接后继 |
|---|---|
| `created` | `investigating`、`cancelling`、`failed` |
| `investigating` | `awaiting_input`、`intent_staged`、`blocked`、`unsupported`、`cancelling`、`failed`、`completed_verified` |
| `awaiting_input` | `investigating`、`cancelling`、`failed` |
| `intent_staged` | `awaiting_confirmation`、`awaiting_reconfirmation`、`investigating`、`cancelling`、`failed` |
| `awaiting_confirmation` | `executing`、`rejected`、`investigating`、`cancelling`、`failed` |
| `executing` | `verifying`、`partial`、`blocked`、`cancelling`、`failed` |
| `verifying` | `delivering`、`repairing`、`awaiting_reconfirmation`、`partial`、`blocked`、`cancelling`、`failed` |
| `repairing` | `executing`、`awaiting_input`、`intent_staged`、`blocked`、`unsupported`、`cancelling`、`failed` |
| `awaiting_reconfirmation` | `executing`、`rejected`、`investigating`、`cancelling`、`failed` |
| `delivering` | `completed_verified`、`repairing`、`blocked`、`partial`、`cancelling`、`failed` |
| `partial` | `investigating`、`executing`、`repairing`、`cancelling`、`completed_verified` |
| `blocked` | `investigating`、`repairing`、`cancelling`、`failed` |
| `cancelling` | `cancelled` |
| `unsupported`、`cancelled`、`rejected`、`failed`、`completed_verified` | 无；均为终态 |

### 2.2 Core 任务项状态闭集

| 起点 | 允许的直接后继 |
|---|---|
| `pending` | `staged`、`running`、`blocked`、`failed`、`cancelled` |
| `staged` | `running`、`blocked`、`failed`、`cancelled` |
| `running` | `succeeded`、`repairable_failed`、`failed`、`blocked`、`cancelled` |
| `repairable_failed` | `running`、`failed`、`blocked`、`cancelled` |
| `blocked` | `pending`、`running`、`failed`、`cancelled` |
| `succeeded`、`failed`、`cancelled` | 无；任务项终态不可重跑 |

## 3. 完整行为矩阵

“模型调用”列均为 `0`；这里的 Agent yield 来自测试夹具，不连接真实模型。

| ID | 场景 | 起点 → 事件 → 终点 | 项目/执行不变量 | 确定性证据 |
|---|---|---|---|---|
| SM-01 | 开始规划 | `created` → 调度 → `investigating` | 同一检查点只创建一个 activation | `tests/desktop_core/test_agent_foundation.py::test_next_action_creates_one_idempotent_activation` |
| SM-02 | 图类冲突追问 | `investigating` → UI 图类与文字图类冲突 → `awaiting_input` | 不静默选择任一图类 | `tests/desktop_core/test_agent_foundation.py::test_chart_selection_conflict_requires_one_answer_before_intent` |
| SM-03 | 用户回答追问 | `awaiting_input` → `answered` → `investigating` | 沿用同一 task，回答成为当前依据 | `tests/tasking/test_task_ledger.py::test_activation_needs_input_and_user_answer_are_ordered` |
| SM-04 | 首版计划待确认 | `investigating` → `intent_ready` → `intent_staged` → `awaiting_confirmation` | TaskItem 已冻结，attempt=0，项目未写入 | `tests/desktop_core/test_agent_foundation.py::test_context_authority_stays_current_until_yield_then_waits_for_confirmation` |
| SM-05 | stale 确认卡 | `awaiting_confirmation` → 错误 plan hash/version → 保持原状态 | 无 grant、无 plot、revision 不变 | `tests/desktop_core/test_application.py::test_agent_v2_rejects_a_stale_confirmation_without_project_side_effects` |
| SM-06 | 首次确认 | `awaiting_confirmation` → `confirmed` → `executing` | grant 精确绑定 task/intent/plan/version/scope | `tests/desktop_core/test_application.py::test_agent_v2_confirmed_plan_executes_and_verifies_one_plot` |
| SM-07 | 用户拒绝 | `awaiting_confirmation` → `rejected` → `rejected` | 终态；之后不能确认或执行 | `tests/desktop_core/test_agent_foundation.py::test_rejected_intent_is_terminal_and_cannot_be_confirmed` |
| SM-08 | 单项成功 | `executing` → `verifying` → `delivering` → `completed_verified` | receipt、verification、plot ID/version 与 revision 一致 | `tests/desktop_core/test_application.py::test_agent_v2_confirmed_plan_executes_and_verifies_one_plot` |
| SM-09 | 批量全部成功 | `executing` → 全部 item 成功 → `completed_verified` | 每项仅执行一次，完成证据齐全 | `tests/desktop_core/test_application.py::test_agent_v2_executes_confirmed_batch_and_verifies_every_item` |
| SM-10 | 批量部分失败 | `executing` → 成功+失败 → `partial` | 成功 plot/receipt/report 保留，失败项独立计次 | `tests/desktop_core/test_application.py::test_agent_v2_preserves_successful_items_when_one_batch_item_fails` |
| SM-11 | 临时外部故障 | `partial` → 同参数自动重试一次 → `executing` | 不调用 Agent，不改变授权，不重跑成功项 | `tests/desktop_core/test_application.py::test_agent_v2_retries_one_transient_failure_without_model_activation` |
| SM-12 | 安全手动重试 | `partial` → `retry_requested` → `executing` | 仅允许 deterministic、retryable、known-none 的失败项 | `tests/desktop_core/test_application.py::test_agent_v2_user_safe_retry_replays_failed_item_without_agent_activation` |
| SM-13 | 相同失败无进展 | `partial` → 同一修复再次失败 → `partial` | 停止自动循环；attempt 增加但成功项不重复 | `tests/desktop_core/test_application.py::test_agent_v2_stops_after_a_scoped_retry_makes_no_progress` |
| SM-14 | 语义失败 | `partial` → Agent 修复 activation → `awaiting_input` | 不能走安全确定性重试；保留成功项 | `tests/desktop_core/test_application.py::test_agent_v2_scoped_repair_can_request_missing_semantic_input` |
| SM-15 | 语义修订 | `awaiting_input` → 回答 → `investigating` → `intent_staged` → `awaiting_reconfirmation` | 新计划版本；旧 grant 不可复用 | 同上 |
| SM-16 | 修订后执行 | `awaiting_reconfirmation` → `confirmed` → `executing` | 只执行新增/失败项，成功项 attempt 不变 | 同上 |
| SM-17 | 自然语言缩减 | `partial` → Agent 输出成功项的结构化真子集 → `completed_verified/completed_with_skips` | 不重新确认、不执行、不增 revision | `tests/desktop_core/test_application.py::test_agent_v2_accepts_verified_subset_without_reconfirmation_or_rerun` |
| SM-18 | 显式跳过 | `partial` → `partial_accepted` → `completed_verified/completed_with_skips` | 跳过 ID 完整，成功项和 attempt 原样保留 | `tests/desktop_core/test_application.py::test_agent_v2_explicit_skip_closes_partial_without_model_or_rerun` |
| SM-19 | 用户修改待确认计划 | `awaiting_confirmation` → `corrected` → `investigating` → `awaiting_reconfirmation` | 新 intent version；必须再次确认 | `tests/desktop_core/test_agent_foundation.py::test_user_correction_creates_next_intent_version_and_requires_reconfirmation` |
| SM-20 | 规划中取消 | active activation → 产品停止控制 → `cancelled` | activation aborted；项目无变化 | `tests/tasking/test_task_ledger.py::test_cancel_aborts_owned_activation_and_finalizes_without_side_effects` |
| SM-21 | 执行原子边界取消 | `executing/running` → 停止 → `cancelling` → `cancelled` | 当前原子项一致提交后保留，其余取消 | `tests/desktop_core/test_application.py::test_agent_v2_cancel_waits_for_the_running_item_and_preserves_its_receipt` |
| SM-22 | 取消中重启 | `cancelling` + running item → 重启对账 → `cancelled` | 未提交则取消；已提交则补齐 ledger/receipt/report 后保留 | `tests/desktop_core/test_application.py::test_agent_v2_restart_reconciles_cancelling_atomic_item` |
| SM-23 | 取消后新任务 | `cancelled` → 新 task → `created` | 不继承旧 busy、错误、activation 或 grant | `tests/desktop_core/test_application.py::test_agent_follow_up_links_new_task_without_reopening_parent` |
| SM-24 | 外部阻断恢复 | `blocked` → `resumed` → `investigating` | 仅显式恢复；创建新 activation | `tests/desktop_core/test_agent_foundation.py::test_blocked_task_resumes_only_after_explicit_external_clear` |
| SM-25 | activation 中断重启 | active activation → 进程恢复 → 新 `resume_after_restart` activation | 旧 activation 标 aborted，不能晚到覆盖 | `tests/desktop_core/test_agent_foundation.py::test_inflight_activation_is_aborted_and_resumed_after_restart` |
| SM-26 | 追问中重启 | `awaiting_input` → 重启 → `awaiting_input` | 不新增 activation，不丢问题 | `tests/tasking/test_task_ledger.py::test_waiting_input_checkpoint_survives_restart_without_new_activation` |
| SM-27 | 首次确认前重启 | `awaiting_confirmation` → 重启 → 原状态 | 无执行、attempt=0、无项目副作用 | `tests/tasking/test_task_ledger.py::test_waiting_confirmation_checkpoint_survives_restart_without_execution` |
| SM-28 | 重新确认前重启 | `awaiting_reconfirmation` → 重启 → 原状态 | 保留新 intent，旧 grant 不存在 | `tests/tasking/test_task_ledger.py::test_waiting_reconfirmation_checkpoint_survives_restart_without_old_grant` |
| SM-29 | 部分失败重启 | `partial` → 重启 → `partial` | item 状态、attempt、output identity 原样恢复 | `tests/desktop_core/test_application.py::test_agent_v2_partial_and_completed_with_skips_survive_restart` |
| SM-30 | 跳过终态重启 | `completed_with_skips` → 重启 → 同一终态 | skipped IDs 和成功结果不变，pump 只返回 terminal | 同上 |
| SM-31 | stale Agent yield | activation 被替代 → 旧 yield 晚到 → 拒绝 | 不覆盖当前 task/version/intent | `tests/tasking/test_task_ledger.py::test_late_yield_is_rejected_after_activation_is_superseded` |
| SM-32 | 事件幂等与 stale version | 同 event ID/内容重放或旧 version 写入 | 同内容幂等；不同内容/旧版本冲突 | `tests/tasking/test_task_ledger.py::test_core_rejects_illegal_and_stale_state_transitions`、`test_activation_needs_input_and_user_answer_are_ordered` |
| SM-33 | 状态表闭集 | 任意 task/item 状态 → 任意后继 | 只允许冻结表中的边；终态闭合；`cancelling` 不能回到 `partial` | `tests/contracts/test_agent_tasks.py::test_complete_task_transition_matrix_is_frozen`、`test_complete_task_item_transition_matrix_is_frozen` |
| SM-34 | 任务中心部分失败 | durable `partial` → 用户选择重试/跳过 | 展示保留结果、阶段、类别、副作用、下一步、诊断 ID | `src/renderer/src/components/TaskDrawer.test.tsx` |
| SM-35 | UI 取消结果 | running → 点击停止 → 刷新 durable `cancelled` | 先读取原子边界后的 checkpoint，再报告保留数量 | `src/renderer/src/App.test.tsx` 中 `projects the refreshed cancelled checkpoint...` |
| SM-36 | 桌面重启恢复计划权限 | 重启 → `list/get` 已有 task/plan | 恢复 task→plan authority，不新建隐藏任务 | `src/main/agent/agent-foundation-runtime.test.ts` 中 `recovers durable plan authority...` |
| SM-37 | 桌面显式跳过 | recovered `partial` → `acceptPartial` | 只发送 typed `partial_accepted`，不启动 Pi runtime | `src/main/agent/agent-foundation-runtime.test.ts` 中 `accepts a recovered partial result...` |
| SM-38 | 桌面安全重试 | recovered `partial` → `resume` | 只发送 typed `retry_requested` 后执行；不启动 Pi runtime | `src/main/agent/agent-foundation-runtime.test.ts` 中 `offers and performs a side-effect-free retry...` |
| SM-39 | 部分失败自然语言修订 | recovered `partial` → `corrected` → `investigating` | 继续同一 task，不创建替代任务 | `src/main/agent/agent-foundation-runtime.test.ts` 中 `continues a partial task as a correction...`、`src/renderer/src/App.test.tsx` 中 `sends a natural-language partial repair...` |
| SM-40 | 规划中断桌面恢复 | `created/investigating/intent_staged` → 任务中心“继续任务” | 不新建 task；从原 checkpoint 继续 | `src/main/agent/agent-foundation-runtime.test.ts` 中 `resumes an interrupted planning checkpoint...`、`src/renderer/src/App.test.tsx` 中 `continues an interrupted planning task...` |
| SM-41 | 修复期间外部阻断 | `repairing` → `blocked` → `resumed` → `repairing` | 恢复时仍携带失败项和验证证据，不降级为普通规划 | `tests/desktop_core/test_agent_foundation.py::test_blocked_repair_resumes_in_repair_scope_with_failure_evidence` |
| SM-42 | 修复无需追问 | `repairing` → `intent_staged` → `awaiting_reconfirmation` | 修订计划必须重新确认，不能被非法边拒绝 | `tests/desktop_core/test_agent_foundation.py::test_repair_can_stage_a_revised_intent_without_an_extra_question` |
| SM-43 | 确认执行后重启 | `executing` + running item → 对账 → `partial` 或继续完成 | 未提交项不伪造；已提交项补齐 receipt/report；不重复执行 | `tests/desktop_core/test_application.py::test_agent_v2_restart_resumes_confirmed_execution_at_the_atomic_boundary` |
| SM-44 | 验证/交付中重启 | `verifying/delivering` → 重启 → `completed_verified` | attempt 保持 1，已有 plot 不重建 | `tests/desktop_core/test_application.py::test_agent_v2_restart_finishes_verified_delivery_without_rerunning_items` |
| SM-45 | 预算耗尽 | activation → `budget_exhausted` → `failed` | 没有伪“恢复”按钮；重试必须是具有新预算的新任务 | `tests/tasking/test_task_ledger.py::test_budget_exhaustion_is_terminal_without_a_fake_resume_path` |
| SM-46 | 不可恢复 blocker | activation → non-retryable `blocked` yield → `failed` | 不展示永远无法成功的“重新检查条件” | `tests/desktop_core/test_agent_foundation.py::test_nonretryable_blocker_is_terminal_instead_of_offering_fake_recovery` |
| SM-47 | 拒绝修订计划 | `awaiting_reconfirmation` → `rejected` | 不执行修订；如已有成功项，项目结果保留并如实提示 | `src/renderer/src/App.test.tsx` 中 `rejects a revised plan without claiming...` |
| SM-48 | 全状态交叉积 | 每个 task/item 状态 × 每个候选后继 | 声明边全部接受，未声明边（含同状态伪转换）全部拒绝；仅初始 `TASK_CREATED` 事件保留 `created → created` | `tests/contracts/test_agent_tasks.py::test_every_task_state_pair_is_accepted_or_rejected_by_the_frozen_matrix`、`test_every_task_item_state_pair_is_accepted_or_rejected_by_the_frozen_matrix` |
| SM-49 | 桌面批量控制边界 | `executing` → 每次只执行一个原子 item → 返回控制通道 → 继续/取消/部分失败 | 已提交 item 保留；主进程在点击停止时立即立取消栅栏，下一项不会抢先排队；先前失败项不被隐式重试 | `tests/desktop_core/test_application.py::test_agent_v2_step_execution_yields_between_atomic_items_for_cancellation`、`test_agent_v2_step_execution_does_not_implicitly_retry_an_earlier_failure`；`src/main/agent/agent-foundation-runtime.test.ts` 中 `returns to the Core control channel between atomic batch items`、`does not enqueue the next atomic item after the user requests cancellation` |
| SM-50 | 意图已冻结但确认卡尚未投影时取消 | `intent_staged` → `cancel_requested` → `cancelling` → `cancelled` | 窄窗口仍可停止；冻结意图不被误当终态 | `tests/tasking/test_task_ledger.py::test_intent_staged_can_be_cancelled_before_the_confirmation_card_is_projected` |
| SM-51 | 再次修改修订计划 | `awaiting_reconfirmation` → `corrected` → `investigating` | 不执行旧修订计划；沿用同一任务生成下一版 intent | `tests/tasking/test_task_ledger.py::test_reconfirmation_plan_can_be_corrected_again_before_execution` |
| SM-52 | 执行终态失败投影 | `executing` → 不可恢复失败 → `failed` | Main/UI 显示任务已停止并要求新任务；不得冒充“结果已验证”或可恢复 partial | `src/main/agent/agent-foundation-runtime.test.ts` 中 `reports a terminal execution failure as failed instead of verified completion`；`src/renderer/src/App.test.tsx` 中 `presents a terminal execution failure as stopped...` |
| SM-53 | 修复流程终态投影 | `partial` → repair pump → `failed/cancelled` | 修复链任一终态均按最终 durable state 投影；不得落入通用“结果已验证”分支 | `src/main/agent/agent-foundation-runtime.test.ts` 中 `projects failed/cancelled when a partial-repair pump stops terminally` |
| SM-54 | 活跃规划防重复恢复 | `investigating/repairing` + active activation → 点击“继续任务” | UI 不展示重复继续入口；Main 仍以 active activation 拒绝重复 pump，仅保留停止控制 | `src/main/agent/agent-foundation-runtime.test.ts` 中 `rejects duplicate continuation while the durable activation is still running`；`src/renderer/src/components/TaskDrawer.test.tsx` 中 `does not offer duplicate continuation...` |
| SM-55 | 终态失败不伪装可重试 | `failed` + 历史错误 `retryable=true` → UI 投影 | `failed` 仍不可恢复；不显示“继续未完成步骤”，提示修改要求后新建任务 | `src/renderer/src/data/productState.test.ts` 中 `never projects a terminal failed task as resumable...` |
| SM-56 | 语义失败不可伪装技术重试 | `repairing` + semantic failure → `technical_repair_ready` | Core 拒绝；任务仍在 `repairing`，只能追问、阻断或经用户回答形成重新确认计划 | `tests/desktop_core/test_application.py::test_agent_v2_scoped_repair_can_request_missing_semantic_input` |
| SM-57 | 未投影/过期计划的重启恢复 | `intent_staged/investigating/awaiting_input/repairing/blocked` + prior intent → 桌面重启 | 只恢复 durable checkpoint/问题，不读取不存在或过期的确认 plan；`intent_staged` 可继续完成投影 | `src/main/agent/agent-foundation-runtime.test.ts` 中 `restores a ... checkpoint without reading a missing or stale confirmation plan` |
| SM-58 | 预算终态不伪装原地重试 | `budget_exhausted` → `failed` → 公共错误投影 | `retryable=false`；提示修改要求后创建新任务，不提供无效的同任务重试 | `src/main/agent/agent-foundation-runtime.test.ts` 中 `does not present an exhausted task budget as retryable in place` |
| SM-59 | 非成功终态不使用成功视觉 | `cancelled/rejected/unsupported` → 任务中心 | 保留真实终态标签并使用中性视觉；只有 `completed_verified` 使用成功图标和成功色 | `src/renderer/src/components/TaskDrawer.test.tsx` 中 `does not style cancelled, rejected, or unsupported terminal tasks as success` |
| SM-60 | 用户动作状态闭集 | 8 种 `UserTaskAction` × 全部 TaskState | 每个动作仅在冻结的允许状态生效；取消、跳过、重试、恢复、回答、确认、拒绝、纠正没有隐式入口 | `tests/tasking/test_task_ledger.py::test_complete_user_action_state_matrix_is_frozen` 及对应行为测试 |
| SM-61 | 多来源计划确认前门禁 | `investigating` + 多来源 item 未声明完整合并 → validator reject | 不生成“0 项数据处理”的错误确认卡；遗漏来源的部分合并同样拒绝 | `tests/workflows/test_workflow_contracts.py::test_compiler_rejects_uncombined_multi_source_item_before_confirmation`、`test_compiler_rejects_combine_operation_that_omits_a_declared_source` |
| SM-62 | 计划结构失败自动返修 | `partial` + plan-revision error → `repairing` → 下一版 `intent_staged` → `awaiting_reconfirmation` | 不按原计划盲重试；Agent 只修订未完成项，保留成功项，修订必须由用户重新确认 | `tests/desktop_core/test_application.py::test_multi_source_plan_structure_failure_requires_agent_revision`、`tests/desktop_core/test_agent_foundation.py::test_repair_host_requires_the_next_intent_version_and_preserves_item_scope`、`src/main/agent/agent-foundation-runtime.test.ts` 中 `returns an Agent-revised plan for reconfirmation...` |

## 4. 一次性缺口审计结论

本轮一次性审计并关闭了以下同源缺口：

1. 所有显式停止统一经过 `cancelling → cancelled`；删除直达 `cancelled` 和回到 `partial` 的歧义边。
2. 取消中、执行中、验证中和交付中重启均按原子项目事实对账，不重跑成功项。
3. Core 的部分结果接受能力补齐真实 UI 入口，并以 `completed_with_skips` 区分终态。
4. 确定性安全重试与 Agent 语义修订分流；只有 `known_none` 的技术失败可零模型重放。
5. 修复路径补上 `repairing → intent_staged`，允许 Agent 直接给出修订计划；修订仍须重新确认。
6. 部分失败后的自然语言修改沿用同一 durable task，不创建隐蔽替代任务。
7. 规划、追问、确认、重新确认、部分失败、阻断、执行、验证、交付和取消均有明确重启行为。
8. 追问内容随 checkpoint 恢复；桌面重启后仍能回答同一 task。
9. 外部 blocker 仅在 `retryable=true` 时可恢复；修复期 blocker 恢复到 `repairing`，不丢失败证据。
10. 没有原地扩容机制的预算耗尽改为明确终态；删除未实现的 `budget_extended` 用户动作。
11. UI 取消先刷新 Core checkpoint，再报告原子边界后实际保留的成功项。
12. 执行返回后重新读取最新 checkpoint，避免用执行前陈旧状态误判后续动作。
13. 拒绝修订计划的文案与真实语义对齐：不执行新方案，但不会声称此前成功结果消失。
14. task/task-item 全状态交叉积测试冻结所有合法与非法边；后续不能悄悄扩大状态图。
15. 桌面批量执行改为逐原子项 RPC，并在用户点击停止时立即建立主进程取消栅栏：每个 item 后主动归还串行 Core 控制通道，下一 item 不会与取消请求竞态抢跑。
16. 补齐两个 UI 可达但状态表遗漏的窄窗口：`intent_staged` 可取消，`awaiting_reconfirmation` 可再次修订；二者均保持同一 durable task。
17. 修正执行终态失败的 Main/UI 投影：`failed` 不再发出“任务结果已验证”，也不再提示用户继续一个不可恢复的旧任务。
18. 删除任意状态的同状态“伪转换”；幂等读取不写事件。唯一例外是任务创建时的 `TASK_CREATED(created → created)` 初始事实事件。
19. 统一初次执行、部分失败修复和修复后重试的所有执行出口：最终状态只能由 durable checkpoint 决定，`failed/cancelled/partial/blocked` 不再被通用完成文案误报为验证成功。
20. 区分“当前 activation 正在运行”和“重启后需要恢复”的相同 planning 状态；前者只允许停止，不允许启动第二个 Agent pump。
21. 删除终态 `failed` 的伪恢复投影；历史错误的 `retryable` 属性不能越过 TaskState 终态约束，只有 `partial` 可走确定性安全重试。
22. 将 `technical_repair_ready` 绑定到确定性技术错误、可重试、不需用户且 `known_none` 的失败项；语义冲突不能借该 yield 绕过追问与重新确认。
23. 计划恢复按 TaskState 过滤：规划、追问、修复和阻断阶段只恢复检查点，不把缺失 plan 当协议失败，也不把上一版 plan 误呈现为当前确认卡。
24. 多来源任务项必须在确认前编译为单一 prepared view；没有 `concatenate_sources` / `align_sources_on_x` 或只合并部分来源时，Core 将草稿退回 Agent，不向用户展示非法确认卡。
25. 执行期若仍发现结构性计划错误，将其分类为需要修订的语义冲突，自动再激活 Agent 生成下一版 intent；旧计划不得直接重放，修订计划必须重新确认。

## 5. 冻结门禁

进入 UI 黑盒前必须同时满足：

- 本文全部确定性用例通过；
- contracts codegen check、Ruff、mypy、TypeScript typecheck、ESLint、Vitest、production build 通过；
- 完整 Python 非 live-Origin 测试通过；
- 工作树干净并冻结单一 commit；
- 运行日志确认没有真实 Provider 调用。

随后只进行一轮冻结 Windows Electron UI 黑盒；修复任何产品缺口后冻结 commit 即失效，必须重新执行门禁和黑盒。UI 黑盒完成后，才运行一次 SEQ-70。
