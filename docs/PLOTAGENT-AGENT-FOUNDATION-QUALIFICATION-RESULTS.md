# PlotAgent Agent Foundation 资格结果

> 收口代码：`c6ecbab582d209360ca008c522652c10feff2be6`
>
> 日期：2026-08-19

## 1. 结论

本轮完成了探索性 Windows Electron 黑盒、缺陷修复、定向桌面复测、完整机械门禁、真实 Origin 重开证明和 SEQ-70 重跑。

- 本地产品缺陷的定向复测已通过；
- Python、Node、静态检查、生产构建和 Windows 发布脚本断言均通过；
- K03 散点图的 Origin 原生轴标题已在两个独立 Origin 进程中完成生成与重开读回；
- 历史运行 `20260818224414-a03a04a` 曾收到供应商 HTTP 402；账户恢复后，当前冻结 commit 的真实最小请求返回 HTTP 200，Pi/Core W01、W09 均通过。
- 当前冻结 commit 的完整 SEQ-70 已从零执行并取得 GO；此前 402/59-of-60 NO_GO 仍作为历史证据保留。

所以当前候选版本的准确状态是：**本地机械门禁、真实模型评测和 P7–P10 主链均合格；可以进入最终探索性 Windows 黑盒。**

## 2. 首轮探索性黑盒

正式入口：`pnpm dev`，正式 Windows Electron UI。

报告：`D:\v3-test\outputs\plotv3-agent-foundation-exploratory-29bfefd-20260819-053957\PLOTAGENT-AGENT-FOUNDATION-EXPLORATORY-REPORT.md`

原始计数：

- PASS：5
- FAIL：6
- BLOCKED：10
- UNVERIFIED：1
- TOTAL：22

这轮发现的本地真实问题包括：

1. Provider 错误被包装成泛化的“模型不可用”，没有明确告知余额不足；
2. 失败任务在 UI 中可能残留为运行中，停止操作又被 Core 拒绝；
3. 首次聚焦编辑没有逆操作快照，撤销/重做不可用；
4. K03 Origin OPJU 的轴标题可能沿用错误语义，而不是实际 X/Y 字段名。

模型驱动批量用例的失败后来由真实请求进一步定位为供应商 HTTP 402，而不是本地网络、模型列表或 Core 连接问题。

## 3. 修复节点

### `69caed8 fix(product): close exploratory black-box state gaps`

- 识别并显示模型余额、鉴权和限流诊断；
- 终态任务取消改为幂等；
- 终态事件和异常路径主动刷新 durable task；
- 首次聚焦编辑建立默认样式逆快照；
- K03 Origin 创建和重开时校验真实字段轴标题。

### `a03a04a fix(agent): expose retryable provider diagnostics`

- Provider 余额、鉴权、限流和 timeout 诊断通过公开 IPC 保留 `retryable=true`，供 UI 提供可恢复反馈。

## 4. 定向 Windows Electron 复测

代码：`a03a04a`。使用新建的“温度响应示例”项目；未读取或记录 API key。

### 4.1 模型失败提示与任务终态：PASS

操作：选择 K03 散点图，提交“请把时间作为横轴，荧光强度作为纵轴，按条件分组画散点图”。

实际观察：

- UI 明确显示“模型服务余额不足，未生成计划，也未修改项目。请充值或更换可用模型服务后重试。”；
- 项目保持 v1；
- 任务中心计数为 0；
- 没有遗留运行中任务或无效“停止任务”入口。

### 4.2 首次编辑撤销/重做：PASS

操作与读回：

1. 手动确认字段映射并创建 K03，plot ID 为 `plot:ui.0038be6d-d379-4aaf-b9f3-fd9fed458631`，图版本 v1；
2. 聚焦编辑将符号大小由默认 4.5 pt 改为 8 pt，生成 v2，撤销按钮启用；
3. 点击撤销，生成 v3，参数读回恢复为 4.5 pt，重做按钮启用；
4. 点击重做，生成 v4，参数读回恢复为 8 pt。

证明首次编辑已经有可逆基线，且撤销/重做通过新版本表达，不修改原始数据。

### 4.3 K03 Origin 轴语义：PASS（真实 Origin 机械证明）

- 独立隐藏 Origin 进程生成 OPJU，读回 X=`Dose_uM`、Y=`Response_mV`；
- 完全退出后，以第二个独立 Origin 进程重开同一 OPJU，读回仍为 X=`Dose_uM`、Y=`Response_mV`；
- OPJU 大小 23,995 bytes。

产物：`D:\plotv3\build\k03-axis-live-probe\K03-axis-fields.opju`

该证明针对本次修改的轴标题持久化；它不替代完整 34 图视觉审查。

## 5. 机械门禁

- Python：714 passed；
- Node/Vitest：27 files、191 tests passed；
- Ruff：PASS；
- mypy：184 source files PASS；
- contracts codegen `--check`：PASS；
- production build：PASS；
- Windows PowerShell 5.1 发布工具断言：PASS。

`pnpm test:release` 在当前父 shell 中仅因其子 PowerShell 无法解析 `Get-FileHash` 而失败；同一脚本用系统 Windows PowerShell 5.1 直接运行后全部断言通过。这是测试宿主调用差异，不是产品断言失败。

## 6. SEQ-70 真实模型重跑

证据目录：`D:\plotv3\build\seq70-workflow-eval\20260818224414-a03a04a`

结果：

- 6 个确定性运行时用例全部 PASS；
- 54 个真实模型 trial 均在约 0.5 秒内收到供应商 HTTP 402；
- 本地 validator、binding、visual action、data operation、inspection、runtime 与确认前无副作用指标均为 1.0；
- 模型输出为 0 token，模型错误率为 1.0；
- 总体结论：NO_GO。

报告中的失败信息已准确呈现“余额不足”。`/models` 可访问只证明模型列表接口可读，不能替代 `/chat/completions` 的真实推理成功。

## 7. 历史发布动作（已由第 8 节完成）

1. 配置一个能够成功完成真实推理的模型服务；（已完成）
2. 在新的 clean commit 上从零重跑完整 SEQ-70，不复用 checkpoint；（已完成）
3. 要求所有正确性发布门继续通过，模型错误率恢复为 0；（已完成）
4. 若仅更换模型账户且运行时代码不变，无需重做 34 图视觉；若 renderer source scope 再变化，则按影响范围补视觉/Origin 证据。（仍适用）

## 8. 当前冻结 commit 的真实模型复评

证据目录：`D:\plotv3\build\seq70-workflow-eval\20260819110057-c6ecbab`

- 冻结 commit：`c6ecbab582d209360ca008c522652c10feff2be6`；
- 24 个 case、60 个 trial：54 个真实模型 trial + 6 个运行时 trial，全部 PASS；
- task exact、validator、route、binding、visual action、data operation、inspection、runtime、确认前无副作用：全部 1.0；
- model error rate：0；
- latency median：8.244 秒；p95：29.735 秒；max：104.723 秒；估算成本：¥0.503156。时长和成本进入报告，不作为终止条件；
- `c6ecbab` 同时增加 provider 请求边界的一次有界瞬时错误重试，未扩大工具权限，也未重复任何 Core 副作用。
