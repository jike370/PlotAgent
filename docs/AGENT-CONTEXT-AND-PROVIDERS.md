# PlotAgent Agent 上下文、模型供应商与数据出境契约

> 状态：第一轮 Agent/Provider 基线已确认
> 日期：2026-08-05
> 适用范围：ContextBuilder、ConversationState、ContextEnvelope、DataDisclosure、ModelProvider、AgentDecision、澄清、审计、隐私和稳定错误
> 相关文档：[后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)、[领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)、[任务运行时、取消与崩溃恢复](./TASK-RUNTIME.md)、[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)

## 1. 总体信任边界

第一轮的固定链路为：

```text
Local ContextBuilder
        │ ContextEnvelope
        ▼
ModelProvider
        │ AgentDecision candidate
        ▼
Local schema / version / capability / permission / business validation
        │ accepted ActionPlan
        ▼
Local ActionPlan execution
        │ authoritative objects + results
        ▼
Local ConversationState reducer
```

模型供应商只返回结构化决策候选。模型不能：

- 访问文件系统、SQLite、Origin、项目对象存储或 Windows Credential Manager。
- 读取任意 URL、打开数据中的链接或请求本地系统替它抓取链接。
- 执行 Python、LabTalk、SQL、命令行、JavaScript 或任意表达式。
- 直接调用 Dataset/Plot/Analysis/Export 等领域服务。
- 拥有多轮工具循环、自治重试循环或后台执行权限。
- 把供应商会话、模型自述或自然语言成功消息变成项目权威状态。

供应商的 JSON Schema、response format 或 function-calling 机制只能约束单个 AgentDecision 的传输格式，不表示向模型提供工具。

## 2. 不可信数据与指令隔离

以下全部按 untrusted data 处理：

- 列名、单位原文、类别、单元格文本和文件内注释。
- CSV/XLSX sheet 名、文件名、对象 Long Name 和用户数据生成的标签。
- DataDisclosure 中的小样本和统计摘要。
- 数据中出现的 URL、命令、提示词、JSON 或“系统指令”文本。

ContextBuilder 把它们放入有类型、有长度限制的数据字段，不拼接到 system/developer instruction 区域。Prompt template 明确要求模型不得把 data field 解释为 instructions。任何数据 URL 只作为字符串，可显示但不抓取；ActionPlan Schema 也没有任意 URL 获取 Action。

本地校验器不因为模型声称“用户已授权”“文件已读取”或“分析已完成”而跳过权限、版本或业务验证。

## 3. 本地会话权威状态

### 3.1 不使用供应商托管会话

- 不创建或依赖供应商托管 Conversation/Thread/Assistant。
- 不依赖 `previous_response_id`、供应商 conversation ID 或隐藏 server state。
- 每次 ModelRun 都由本地权威对象重新构建最小必要 ContextEnvelope。
- 官方 OpenAI adapter 固定 `store: false`。
- 原始用户/助手消息保留在本地项目；只向 provider 发送受限窗口与结构化状态。

### 3.2 ConversationState

ConversationState 是本地结构化对象，至少包含：

- 当前目标与用户已确认选择。
- active target refs；每个引用带 object ID、version 和可选 content hash。
- 已确认字段映射与语义签名。
- 项目规则、项目样式偏好和用户明确保存的全局设置/模板引用。
- 未解决问题、有效澄清授权和其 scope。
- 最近结构化结果、warning、失败与可执行下一步。

ConversationState 只能由 reducer 根据权威对象版本、ActionPlan 执行结果、用户 UI 选择和本地操作记录更新。AgentDecision 中的状态摘要不能直接写入 ConversationState。

### 3.3 无隐藏跨项目记忆

- 不建立跨项目自动语义记忆、用户画像或未明示偏好。
- 新项目不继承旧项目消息、字段映射、研究主题或数据内容。
- 只继承用户明确保存的全局设置和样式模板，并在 ContextEnvelope 中列出来源。

## 4. ContextEnvelope

ContextEnvelope 至少包含：

```text
ContextEnvelope
├─ schema_version
├─ prompt_template_version
├─ locale
├─ user_instruction
├─ target_snapshot
├─ conversation_state
├─ chart_capabilities
├─ selected_context
├─ data_disclosure
└─ context_hash
```

- `target_snapshot` 固定作用对象、object ID、version、类型、状态和必要摘要。
- `conversation_state` 是本次最小化投影，不发送本地完整状态表。
- `chart_capabilities` 只包含与明确图形/操作相关的版本化白名单能力。
- `selected_context` 包含允许出境的字段元数据、摘要、消息窗口和小样本。
- `data_disclosure` 描述实际发送类别、对象/字段范围、计数、授权和 provider。
- `context_hash` 覆盖规范化 Envelope、目标版本、prompt/schema 版本和 disclosure hash。

输入框常驻作用对象必须与 target_snapshot 一致。所有 `@` 引用在本地解析为带 version 的对象引用；模型不通过显示名称自行遍历项目。

## 5. 默认数据出境

### 5.1 Provider 首次同意

每个 provider 配置第一次处理项目内容前，显示一次明确同意：默认可能发送用户指令、字段元数据、统计摘要和小样本。确认按 provider config ID、endpoint origin、retention disclosure version 记录；provider origin 或保留说明变化时重新确认。

默认永不发送：

- 原始文件或完整 DatasetVersion 表。
- 工作区路径、源路径、SQLite、OPJU 或 `.plotproj`。
- 完整项目、完整对话或未选择对象。
- API key、设备令牌、凭据和诊断包。

### 5.2 小样本硬上限

每次 ModelRun 的默认小样本同时满足：

- 最多 20 行。
- 最多 12 个相关字段。
- 最多 200 个 scalar cell values。

实际行上限为 `min(20, floor(200 / selected_field_count))`。没有字段时不发送样本。

确定性选择规则：

1. 字段优先级依次为显式 target/mapping 引用、用户指令精确名称命中、图形/分析所需角色、类型与单位候选，最后按稳定 field ID；最多 12 个。
2. 行按 DatasetVersion hash、稳定 row ID 和 sampling rule version 计算确定性 hash order，选择前 N 个；相同输入与版本得到相同样本。
3. missing/NaN/Inf 作为类型化状态计数并按 disclosure 规则表示，不借机追加更多行。

### 5.3 超宽表

DatasetVersion 超过 200 列时，本地字段索引按规范化名称 token、逻辑类型、UnitSpec、字段语义和当前 chart/analysis role 评分：

- 只发送相关候选字段元数据，不发送全量宽表 schema。
- 候选仍受 12 个 sample field 与 ContextEnvelope 大小限制。
- 同分候选保持稳定 field ID 顺序；真正同等且影响映射时返回 NeedsInput。
- 字段索引和筛选在本地运行，不把“先看全部列再决定”交给模型。

## 6. 扩大出境授权

模型发现当前 Envelope 不足时只能返回 NeedsInput，并在 `data_request` 中声明：

- DatasetVersion 与字段 IDs/versions。
- 请求的数据类别和估算 scalar/row/field 数量。
- 用途、为什么默认摘要不足、是否可以用更小范围满足。
- 所需授权 scope。

UI 只允许：

- `this_run`：仅下一次固定 context hash 的重试。
- `this_conversation_similar`：同一 provider、对话、数据集、字段类别和用途的同类请求。

授权可以随时撤销；不提供永久项目级或全局“始终发送完整数据”。目标版本、provider、用途或字段范围改变时授权不自动扩张。

本地 DataDisclosure 记录保存：

- provider/config、目标对象/版本、授权 scope 和时间。
- 发送类别、字段/行/scalar 数量与规范化 disclosure hash。
- context hash、授权来源和撤销状态。

不保存为了审计而复制的完整网络 request body，也不保存 UI 未展示的数据副本。

## 7. ModelProvider 统一适配层

### 7.1 Capability-based interface

内部接口按能力而非供应商品牌分支：

```text
ModelProvider
├─ probe(synthetic_request)
├─ decide(ContextEnvelope, AgentDecisionSchema, fixed_profile)
├─ cancel(model_run_id)
└─ report_usage(model_run_id)
```

Probe 记录 endpoint、protocol、output level、streaming、usage 与错误能力，不发送项目内容。

### 7.2 内置邀请制 Provider

- 桌面端使用 Windows Credential Manager 中的长期 DeviceCredential 访问 PlotAgent proxy。
- 上游平台 provider key 只存在服务端，不下发桌面端。
- 第一轮没有 remote CloudConfig；客户端 build 固定允许的 model profile/protocol，服务端部署只能在该 allowlist 内响应。
- 每次 ModelRun 固定 profile/model 与服务端 deployment identifier 并写入审计；运行中不能静默换模型。

### 7.3 自定义 OpenAI-compatible Provider

用户配置：

- base URL。
- model ID。
- 可选 API key。

能力探测优先 `/v1/responses`，不支持时回退 `/v1/chat/completions`。连接测试只发送合成 schema、合成指令和合成数据，不发送项目名称、字段、样本或消息。

自定义 provider 配置属于本机全局设置，不随 `.plotproj` 导出。

## 8. 凭据与 endpoint 安全

- 自定义 API key 与内置设备令牌只存 Windows Credential Manager。
- 凭据不得进入 React renderer、项目、`.plotproj`、project/catalog SQLite 普通字段、日志、诊断包、环境变量或命令行。
- Renderer 只看到不含 secret 的 provider config ID、显示名称、origin、model ID 和状态。

Endpoint 规则：

- 非 loopback 地址强制 HTTPS。
- 只有 `localhost`、`127.0.0.1` 和 `::1` 可以使用 HTTP。
- TLS certificate/hostname 验证不可关闭，也不提供“忽略证书错误”。
- 只允许 HTTP(S)，拒绝 `file://`、`ftp://`、自定义 scheme 和模型提供的 URL。
- 带 Authorization 的请求遇到 cross-origin redirect 时拒绝，不转发 credential；同 origin redirect 仍受协议、次数和 TLS 校验。
- Endpoint origin 规范化为 scheme + host + port，配置和审计不保存 secret/query。

## 9. 输出能力等级

- **P1 — strict schema**：provider 可稳定按 AgentDecision JSON Schema 返回严格结构。
- **P2 — JSON only**：provider 只有 JSON mode 或普通 JSON；本地严格 schema 校验，第一次失败后最多发送一次 repair request。
- **P0 — unsupported**：无法稳定产生合法 AgentDecision；连接测试判定不支持，不能处理项目请求。

Repair request：

- 固定同一 model/profile、target versions、context hash 和 disclosure scope。
- 只说明 schema errors 并携带待修复候选；不增加新项目数据。
- repair usage 计入同一 ModelRunAudit。
- 第二次仍失败返回 REPAIR_EXHAUSTED，不从自然语言猜 Action。

P1/P2 都必须通过相同本地 schema、对象版本、capability、permission 和业务规则校验。输出能力等级从不授予直接执行权限。

## 10. AgentDecision

所有 provider 只返回一个带 discriminator 的联合：

```text
AgentDecision
├─ ActionPlan
├─ NeedsInput
├─ Unsupported
└─ NoChange
```

- `ActionPlan` 是最多 8 个白名单 Action 的完整候选。
- `NeedsInput` 只用于必要澄清或扩大出境请求。
- `Unsupported` 表示产品/Provider 能力没有合法实现路径。
- `NoChange` 表示权威状态已满足请求或没有状态变化。

AgentDecision 不设置模型自报的 blocked 分支。ActionPlan 违反数学、安全、版本或产品硬规则时由本地 validator 拒绝并产生稳定错误；不能让模型自我声明“已通过校验”。

本地系统不从 Markdown、自然语言、tool transcript 或部分 JSON 猜命令。完整 AgentDecision 未接收并校验前，不展示或执行 partial plan。

## 11. 澄清契约

只有以下情况询问：

- 作用对象不明确。
- 字段映射存在同等候选且无法由已确认映射消解。
- 分析方法、误差语义或设计选择会实质影响科研结果。
- 需要扩大数据出境。
- 本地 validator 缺少使计划成立的必要信息。

一次 ModelRun 最多产生一张 clarification card，卡内最多 3 个相互独立问题。样式琐事、普通默认值或可逆且已有确定规则的设置不询问。

续接请求必须携带：

- 原 target refs 与 versions。
- 原 context hash。
- clarification decision ID 与用户回答。

任一目标版本变化时旧 draft 和 clarification 失效，返回 TARGET_STALE，并基于新权威状态重新规划；不能把旧回答套到新对象。

## 12. ModelRunAudit

每次调用保存：

- provider type、provider config ID、endpoint origin；不含 secret/path/query。
- model ID、model profile、client build 与服务端 deployment identifier。
- prompt template version、ContextEnvelope schema 与 AgentDecision schema version。
- provider request ID、client model run ID、开始/结束时间、latency。
- input/output/repair token usage 与 usage 来源。
- 状态、稳定 error code、P1/P2 level 和 repair count。
- DataDisclosure 类别/field/row/scalar 数量与 disclosure hash。
- target refs/versions 与 context hash。

审计不保存 API key、DeviceCredential、隐藏 reasoning、chain-of-thought、完整 request/response body 或未展示数据。AgentDecision 作为项目操作候选按对象契约保存；provider 原始传输响应不作为权威记录。

如果 provider 返回 reasoning 字段或专有推理项，adapter 不展示、不持久化，也不把它送入下一次 ConversationState。

## 13. 数据保留说明

### 13.1 内置 PlotAgent proxy

PlotAgent 可以作出并验证的应用级承诺是：proxy 不记录 prompt/request body/response body 或原始数据，只记录运行、额度、延迟和稳定错误等必要元数据。设置页仍必须准确展示底层模型供应商的数据政策，不能把 proxy 的日志策略宣传为供应商零保留。

### 13.2 OpenAI API

官方 OpenAI adapter 的产品说明必须使用准确口径：

- OpenAI API 输入/输出默认不用于训练模型，除非客户明确选择共享。
- 默认 abuse monitoring logs 可能包含 prompt/response 等 customer content，并保留最多 30 天；法律要求可能例外。
- `store: false` 避免使用 Responses API 托管 application state，但不等于默认 Zero Data Retention。
- Zero Data Retention 是需符合资格并获批准的单独控制，PlotAgent 第一轮不能宣传自己默认具备。

官方依据：[OpenAI API Data Controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint)、[OpenAI Business Data Privacy](https://openai.com/business-data/)。

### 13.3 第三方兼容 Provider

第三方保留、训练、地域和安全政策由用户与 provider 负责。首次使用和 endpoint origin/retention disclosure 变化时，设置页要求确认；未确认返回 PROVIDER_RETENTION_UNACKNOWLEDGED。

## 14. 运行、Streaming 与取消

- 可以使用 HTTP streaming 降低等待，但 streaming fragment 只进入 adapter buffer。
- UI 只显示“准备上下文、等待模型、校验决策、等待输入”等本地阶段，不展示 chain-of-thought 或 provider tool trace。
- AgentDecision 完整并通过本地校验前，不显示/执行 partial plan。
- 用户停止生成时中止 HTTP 请求并结束 InteractionRun；已存在 ExecutionTask 不受影响。
- 内置 profile 只能随新客户端 build 或明确服务端部署在两次 run 之间变化；每次 run 固定 model/profile/deployment，运行中不能 fallback 或静默切模型。
- 网络错误后的明确重试创建新的 transport attempt，但保持同一本地 run lineage、目标版本与已授权 disclosure；不扩大上下文。

## 15. 稳定错误

| Error code | 条件 | UI/恢复 |
| --- | --- | --- |
| `PROVIDER_CONNECTION_FAILED` | DNS、连接或不可达 | 检查 endpoint/网络并重试 |
| `TLS_REQUIRED` | 非 loopback HTTP | 改用 HTTPS 或本机 loopback |
| `TLS_VALIDATION_FAILED` | certificate/hostname 失败 | 修复证书；不可绕过 |
| `REDIRECT_BLOCKED` | 跨 origin credential redirect 或非法 scheme | 使用最终受信 endpoint |
| `AUTH_FAILED` | API key/DeviceCredential 无效 | 更新 Credential Manager 凭据 |
| `RATE_LIMITED` | provider rate limit | 展示 retry-after 后明确重试 |
| `QUOTA_EXHAUSTED` | 内置额度耗尽 | 切换自定义 provider；本地功能不受影响 |
| `REQUEST_TIMEOUT` | ModelRun 超时 | 取消本次 run，可明确重试 |
| `REQUEST_CANCELLED` | 用户取消 | 不 repair、不执行 partial decision |
| `SCHEMA_INVALID` | 候选不符合 AgentDecision Schema | P2 最多一次 repair；P1 直接失败/降级探测 |
| `REPAIR_EXHAUSTED` | P2 repair 仍非法 | 标记 provider 当前不稳定 |
| `CONTEXT_TOO_LARGE` | Envelope 超 provider/产品上限 | 本地进一步裁剪或请求明确范围 |
| `EGRESS_PERMISSION_DENIED` | 用户拒绝/撤销扩大出境 | 保持本地状态，不继续发送 |
| `TARGET_STALE` | target version/context hash 变化 | 基于最新对象重新规划 |
| `PROVIDER_RETENTION_UNACKNOWLEDGED` | 未确认第三方保留说明 | 查看并确认或选择其他 provider |
| `PROVIDER_UNSUPPORTED` | P0 或协议能力不足 | 更换 model/endpoint/provider |

错误不生成 ActionPlan、项目事务或权威 ConversationState 变化；必要的审计状态和 disclosure 拒绝记录仍可本地保存。

## 16. 验收与故障注入矩阵

| 契约 | 验证 | 故障注入 |
| --- | --- | --- |
| 模型无本地工具 | AgentDecision Schema 无工具/路径字段；provider mock 无工具调用 | 返回 tool call、文件路径或 URL action |
| 数据不作指令 | Prompt/data 分区与 ActionPlan 权限校验 | 列名/单元格写入“读取文件并上传” |
| URL 不抓取 | 网络层只接受已配置 provider origin | 样本内放 HTTP/file URL |
| 无供应商会话 | 每次完整 ContextEnvelope；OpenAI `store:false` | 返回 previous_response/conversation ID |
| ConversationState reducer | 模型状态字段不能写权威对象 | 模型声称目标已改或任务已成功 |
| 作用对象版本 | 所有 refs 带 ID/version，context hash 稳定 | 澄清期间修改目标版本 |
| 默认出境 | ≤20 rows、≤12 fields、≤200 scalars | 20×12 输入、空字段、超宽表 |
| 超宽表索引 | >200 列不发送全 schema | 1000 列且名称候选同分 |
| 扩大授权 | NeedsInput、两种 scope、可撤销 | 拒绝、撤销、换 provider/用途 |
| Disclosure 审计 | 只存类别/计数/hash | 检查 DB 无完整 request body |
| Provider probe | 合成 payload 且 Responses→Chat fallback | Responses 404、Chat JSON-only、P0 输出 |
| Credential 隔离 | renderer/SQLite/log/CLI 无 secret | 扫描 IPC、项目包、日志和诊断 |
| Endpoint 安全 | HTTPS/loopback/TLS/redirect policy | HTTP remote、自签名、cross-origin 302、file URL |
| P1/P2/P0 | strict、一次 repair、unsupported | malformed JSON、schema extra、repair 二次失败 |
| AgentDecision 唯一联合 | 只接受四种 discriminator | 过时的第五分支、自然语言、多个 decision |
| 本地 validator | schema/version/capability/permission/business 全部执行 | 合法 JSON 但 stale/越权/不支持 |
| 澄清上限 | 一卡≤3问题且仅白名单原因 | 4 个问题、样式琐事追问 |
| Streaming/partial | fragment 不进入 UI/执行器 | 中途断流、完整前取消 |
| Audit 最小化 | 元数据齐全且无 reasoning/payload | provider 返回 reasoning 和 secret query |
| Retention 文案 | 内置/OpenAI/第三方分别展示 | 模拟未确认第三方与政策版本变化 |
| 固定 profile | run 审计 model/profile/deployment 一致 | 运行中服务要求换模型 |
| 错误稳定性 | 每个错误映射可恢复动作 | DNS/TLS/401/429/timeout/quota/schema/stale |
