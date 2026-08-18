# PlotAgent Agent Foundation 探索性黑盒交接

> 原始探索性运行时代码：`29bfefdb1fcb7611528c7e354fdfa0131e27c826`。黑盒后修复运行时代码：`a03a04a6bdbba7146ad870da8ed483947076d9a7`；两者的证据不得混用，后续定向/最终执行以当前 clean HEAD 的非文档内容等同于 `a03a04a` 为准。
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
- 开始前保存 `git rev-parse HEAD`、`git status --short` 和 `git diff --exit-code 29bfefdb1fcb7611528c7e354fdfa0131e27c826 -- . ':(exclude)docs/**'`。
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

- Python 714 passed；Node 188 passed；Ruff、mypy 184 模块、contracts codegen、两套 typecheck、ESLint、production build 均通过。
- Agent Foundation regression suite v2：真实模型 18 × 3、运行时 6 × 1，共 60/60 PASS，决策 GO。
- task exact、validator、route、binding、visual action、data operation、inspection、runtime、确认前无副作用均为 1.0；模型错误率 0；median 6.500 秒，p95 16.633 秒，max 92.225 秒。
- Agent 总任务不设产品时长硬截止；Provider/工具仍有传输 timeout，用户取消仍可用。

这些结果只说明候选版本可以进入正式桌面探索性黑盒。

## 6. 收口

本轮输出单独保存，不覆盖旧冻结回归。最终报告应包含环境、用例、证据索引、PASS/FAIL/BLOCKED/UNVERIFIED 计数、产品缺陷、环境问题和未覆盖风险。任何产品 FAIL 修复后必须在新的干净提交上定向复测；若修改 renderer source scope，再按影响范围补视觉/Origin 证据。

## 7. 执行结果（2026-08-19）

探索性黑盒、修复和定向复测已完成。收口代码为 `a03a04a6bdbba7146ad870da8ed483947076d9a7`。

- 本地缺陷定向复测通过：模型余额诊断与任务终态、首次编辑撤销/重做、K03 Origin 轴语义；
- 完整机械门禁通过；
- 新的 SEQ-70 因供应商对 54 个真实推理 trial 全部返回 HTTP 402 而 NO_GO；6 个确定性运行时用例通过；
- 在更换或充值模型服务并重跑 SEQ-70 前，不宣称真实模型发布资格 GO。

详细事实、路径和判定见 `docs/PLOTAGENT-AGENT-FOUNDATION-QUALIFICATION-RESULTS.md`。
