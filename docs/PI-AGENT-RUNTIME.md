# Pi 通用 Agent 运行时接入契约

> 状态：2026-08-13 起作为 Windows 桌面版自然语言入口的正式运行时。

## 1. 目标

PlotAgent 使用 Pi 承担通用 Agent 运行时职责：模型流式调用、会话轮次、工具调用、取消、steering/follow-up 基础能力和生命周期事件。PlotAgent 自身继续拥有科研绘图领域约束、字段权威、计划确认、版本控制、事务提交和双后端渲染。

这不是把产品变成可执行文件或 Shell 的通用 Agent。Pi 在 PlotAgent 中只获得一个强类型工具：`submit_plotagent_decision`。它没有文件、命令行、数据库、网络抓取、Origin、Matplotlib 或项目写入工具。

## 2. 正式执行链

1. 用户在桌面 UI 选择数据和图形，并提交自然语言目标。
2. 本地 Core 从权威项目状态构造有界 `ContextEnvelope`，同时给出允许的 `AgentDecision` schema。
3. Electron 主进程启动 Pi；Pi 可进行多轮模型推理，但只能调用一次 `submit_plotagent_decision`。
4. 本地 Core 重新核对项目版本、目标、字段别名、图形能力和动作参数，并将候选绑定为待确认计划。
5. 用户确认后，Core 才执行动作并提交新版本；拒绝、超时、取消和陈旧结果均不得产生项目副作用。

## 3. 安全和隐私边界

- 模型服务密钥继续由操作系统凭据存储保护；只在受信任的 Electron 主进程与本地 Core 之间按本轮请求读取，不进入 renderer、日志或项目文件。
- 发送给模型的仍是经过最小化、数量限制和披露记录的 `ContextEnvelope`。
- Pi 的文本回复不具备执行权。只有强类型工具参数经过本地 Pydantic/Engine validator 和对象绑定后才能形成计划。
- 同一时刻只允许一个模型运行；新请求或目标切换会取消旧运行，迟到结果不能覆盖当前计划。

## 4. 用户可见状态

桌面端从真实 Pi 生命周期显示“读取数据结构”“规划绘图动作”“校验字段绑定”“保存待确认计划”等阶段。不得用计时器伪造进度、百分比或剩余时间。

## 5. 验收标准

- 明确请求能生成唯一、可确认的计划；确认前项目版本不变。
- 缺少必要图形类型时直接 `NeedsInput`，且不调用模型。
- 非法字段、错误目标、越权图形或无效动作被本地拒绝。
- 超时、取消、目标切换和陈旧返回均无副作用。
- UI 显示的阶段来自实际 Pi/Core 事件；成功后确认卡包含具体字段和动作。
- 模型服务未配置或不可达时，手动绘图、编辑和导出仍可用。

Pi SDK 文档参考：[Pi SDK](https://pi.dev/docs/latest/sdk)、[Pi extensions and tools](https://pi.dev/docs/latest/extensions)。
