# PlotAgent Agent Foundation 探索性黑盒交接

> 原始探索性运行时代码：`29bfefdb1fcb7611528c7e354fdfa0131e27c826`。最终运行时冻结：`43cae4ce09bedfee8fcebeb17377c24f479fcc72`；两者的证据不得混用。若交接文档另有后续 docs-only commit，最终执行必须确认非文档内容与 `43cae4c` 相同。
>
> 测试角色：探索性会话只根据功能简报设计测试；本主任务窗口负责正式 Windows Electron 执行、证据保存和判定。

## 1. 本轮目的

本轮不重新机械遍历 34 张图，也不继承旧 Agent 黑盒结论。它要在正式桌面入口证明新的目标驱动 Agent 主链可用：

- 用户能提交单项或批量绘图目标；
- Agent 能在必要时检查数据并选择受控数据操作；
- Agent 能给出可理解、可修改、可确认的任务；
- 确认前无项目副作用；
- 确认后执行、验证、部分成功、取消与恢复状态一致；
- renderer 产物和版本身份可由 UI 观察，抽样导出仍可用。

## 2. 独立测试设计输入

探索性测试会话只读取：

- `docs/PLOTAGENT-V3-EXPLORATORY-BLACK-BOX-BRIEF.md`
- `docs/PLOTAGENT-V3-BLACK-BOX-CAPABILITY.md`

不得向其提供源码、SEQ-70 用例、历史失败清单、内部别名、正确字段答案或 renderer 实现。它输出测试目标、风险、操作思路、预期和证据要求，不操作桌面、不作 PASS/FAIL 判定。

## 3. 执行环境

- 仓库：`D:\plotv3`
- 唯一正式入口：`pnpm dev`
- 禁止：`pnpm dev:web`、静态审计页、浏览器 mock、Core 内部接口、单测替代 UI。
- 开始前保存 `git rev-parse HEAD`、`git status --short` 和 `git diff --exit-code 43cae4c -- . ':(exclude)docs/**'`；允许后续交接文档自身变化，非文档差异必须为 0。
- 工作树必须干净；非文档差异必须为 0。
- 使用全新项目与全新输出目录，不复用旧图、截图或导出。
- 不读取、截图或记录模型 API key。

## 4. 主窗口执行规则

主窗口收到独立计划后先去重、编号和排序，再逐项执行。每项至少保存：

- 用户原始目标与所选数据/图形；
- Agent 可见答复、追问或确认卡；
- 确认前后项目 revision、Task/Item 状态、plot ID/version；
- 执行中的真实阶段、取消/失败/恢复反馈；
- 结果图完整窗口截图；
- 请求导出时的文件、大小、hash 与适用的 Origin 重开证据；
- 应用关闭后的进程清理和需要时的重启恢复身份。

判定只允许：

- `PASS`：正式 UI 实际观察符合声明且证据充分；
- `FAIL`：实际观察违反产品声明；
- `BLOCKED`：外部环境阻止执行且有证据；
- `UNVERIFIED`：已尝试但证据不足，不能推定结果。

“单测通过”“SEQ-70 GO”“源码如此”“以前测过”均不能作为本轮 PASS 证据。

## 5. 研发前置证据（不可替代黑盒）

- Python 718 passed；Node/Vitest 27 files / 193 tests passed；Ruff、mypy 184 模块、contracts codegen、TypeScript typecheck、ESLint、production build、Windows release tools 均通过。
- Agent Foundation regression suite v2：真实模型 18 × 3、运行时 6 × 1，共 60/60 PASS，决策 GO；证据 `build/seq70-workflow-eval/20260819140106-43cae4c/`。
- task exact、validator、route、binding、visual action、data operation、inspection、runtime、确认前无副作用均为 1.0；模型错误率 0；median 8.536 秒，p95 25.458 秒，max 38.315 秒。
- Agent 总任务不设产品时长硬截止；Provider/工具仍有传输 timeout，用户取消仍可用。

这些结果只说明候选版本可以进入正式桌面探索性黑盒。

## 6. 收口

本轮输出单独保存，不覆盖旧冻结回归。最终报告应包含环境、用例、证据索引、PASS/FAIL/BLOCKED/UNVERIFIED 计数、产品缺陷、环境问题和未覆盖风险。任何产品 FAIL 修复后必须在新的干净提交上定向复测；若修改 renderer source scope，再按影响范围补视觉/Origin 证据。

## 7. 执行结果（2026-08-19）

上一轮探索性黑盒、修复和定向复测已完成；当前最终运行时收口代码已更新为 `43cae4ce09bedfee8fcebeb17377c24f479fcc72`。

- 本地缺陷定向复测通过：模型余额诊断与任务终态、首次编辑撤销/重做、K03 Origin 轴语义；
- 完整机械门禁通过；
- 当前新的 SEQ-70 已在账户恢复后从零执行，54 个真实推理 trial 与 6 个确定性运行时用例全部通过；
- 历史 HTTP 402 和 59/60 NO_GO 证据仍保留在旧评测目录，不与当前 GO 混用。

详细事实、路径和判定见 `docs/PLOTAGENT-AGENT-FOUNDATION-QUALIFICATION-RESULTS.md`。

## 8. 最终探索性测试重点

独立测试设计应在总量有界的前提下优先覆盖：

1. 未预选图形，从三个已选择数据源发起一次异构批量；确认卡必须逐项显示正确的数据源、图类和字段绑定，确认前无新增 plot；
2. 批量中的一项信息不足或验证失败时，成功项被保留，失败项可单独修复/重试，不重复成功项；
3. 规划阶段与执行阶段分别尝试取消，观察任务中心、项目版本和已提交 TaskItem 的一致性；执行过快无法点击时必须记为 UNVERIFIED，不用单测补成 UI PASS；
4. 完全关闭后重启，项目、最近 plot、任务状态可恢复，且 PID 复用形成的陈旧 writer lock 不误报“已有写入器”；
5. `needs_input` 保持为同一对话中的可继续追问，不出现笼统“Core rejected/missing plan”；
6. 抽样导出一个图，检查用户可见成功反馈、文件身份和适用的 OPJU 重开；
7. 不重新遍历全部 34 张图。只有发现 renderer 相关症状时，才按影响范围补相应视觉/Origin 证据。

探索性会话只负责据此和公开功能简报设计独立计划，不读取源码、不运行产品；正式 Windows Electron 操作与证据判定由本主窗口完成。
