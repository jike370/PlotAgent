# PlotAgent 邀请、共享额度与最小 Beta 云控制面契约

> 状态：小规模邀请制 Beta 已确认边界
> 日期：2026-08-05
> 适用范围：InviteGrant、长期设备凭据、built-in model proxy、原子共享计数、请求幂等、云故障降级与人工安装包
> 相关文档：[产品决策基线](./PRODUCT-DECISIONS.md)、[Agent 上下文、模型供应商与数据出境](./AGENT-CONTEXT-AND-PROVIDERS.md)、[本地安全、诊断与 Beta 兼容](./LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md)、[后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)、[领域契约](./DOMAIN-CONTRACTS.md)

## 1. Beta 原则

- 同一邀请码可在不限数量设备重复兑换，额度归 `InviteGrant` 并由所有设备共享；增加设备或重装不能获得新额度。
- 设备只承担鉴权与设备级速率保护，不建立账号、邮箱、密码、个人资料、找回流程或硬件身份。
- 云端仅服务 built-in Agent；项目、数据、Preparation/PlotCalculation、图表、PNG/SVG/OPJU 与 custom provider 始终在本地或由用户配置的 provider 完成。
- 应用启动和打开项目不依赖云。邀请撤销、额度耗尽或云故障不能锁定项目或禁用任何本地能力。
- 第一轮以可审计的简单状态和原子操作为准，不实现生产级 token rotation、reserve/settle/reconcile ledger、CloudConfig、应用内更新、analytics 或诊断上传。

## 2. 明确不在 Beta 云端的能力

- 账号、登录、团队、联系人、云端项目/会话/图表同步。
- 原始文件、项目包、PlotSpec/PlotCalculationResult 或完整对话的云存储。
- 远程科研计算、远程渲染、远程 Origin/OPJU。
- 短期 access token 与 refresh-token rotation、复杂 scope delegation。
- usage-token reserve/settle、unused release、reconciliation job 或多阶段计费恢复。
- remote CloudConfig、更新 manifest、应用内检查/下载/安装。
- usage analytics、DiagnosticBundle 上传或后台 telemetry。

## 3. InviteGrant

```text
InviteGrant
├─ invite_id
├─ invite_secret_hash       # 高熵 secret 的版本化服务端 hash
├─ status                   # active | expired | revoked
├─ expires_at?
├─ quota_policy_id
├─ quota_granted
├─ quota_consumed
├─ period_start?
├─ period_end/reset_at?
├─ allowed_model_profile_ids
├─ created_at
└─ revoked_at?
```

- 邀请 secret 不明文存储；日志和管理界面不得显示完整 secret。
- 撤销整个 grant 立即阻止该 grant 的新 built-in model run；已有本地项目不受影响。
- Beta 可以封禁单个异常 DeviceCredential，但不能通过设备数限制邀请兑换。
- 额度是服务端权威共享计数；客户端缓存仅用于显示，不作为扣费真相。

## 4. 设备兑换与凭据

客户端首次兑换生成随机 `installation_id`。不得读取硬盘序列号、MAC、Windows 用户名、主机名、TPM ID 或其他硬件指纹。

```text
RedeemInviteRequest
├─ invite_secret
├─ installation_id
├─ app_build
└─ protocol_version

RedeemInviteResponse
├─ invite_id
├─ device_id                # 随机服务端伪名
├─ device_credential        # 长期凭据，只返回一次
├─ allowed_model_profile_ids
├─ quota_snapshot
└─ protocol_version
```

- `device_credential` 与 built-in 设备凭据只存 Windows Credential Manager，不进入 renderer、项目、`.plotproj`、SQLite普通字段、日志、诊断包或命令行。
- 邀请码成功兑换后不在本地持久化；凭据丢失时使用原邀请码重新兑换，不提供云端找回。
- 第一轮不签发 15 分钟 access token，也不实现 refresh rotation；撤销/封禁由每次 built-in 请求的服务端凭据校验生效。
- DeviceCredential 仅授权 invitation status、built-in proxy 和共享 quota status/invoke，不含项目或文件读取 scope。

## 5. 简化共享额度与幂等

### 5.1 固定语义

```text
QuotaSnapshot
├─ invite_id
├─ granted
├─ consumed
├─ remaining
├─ period_start?
├─ reset_at?
└─ server_time
```

Beta 不暴露 `reserved`，也不按 provider token 做多阶段结算。`quota_policy_id` 明确一个 built-in model invocation 如何换算为 quota unit，UI 在兑换/设置页展示该规则。

### 5.2 原子接受与扣减

每次 built-in model run 由客户端生成唯一 `client_run_id`：

```text
ModelInvokeRequest
├─ client_run_id            # Idempotency-Key
├─ model_profile_id
├─ context_hash
├─ request_payload          # 不写控制面日志
└─ protocol_version

ModelRunRecord
├─ invite_id
├─ client_run_id            # 唯一约束
├─ device_id
├─ model_profile_id
├─ state                    # accepted | invoking | completed | failed | cancelled
├─ quota_unit
├─ response_or_error_ref?   # 短期幂等响应，不进入通用日志
├─ created_at
└─ finished_at?
```

服务端在一个原子事务中：

1. 检查 `(invite_id, client_run_id)` 是否已存在；存在则返回同一记录/结果，不再次调用 provider、不再次扣费。
2. 检查 grant/device/model profile 与 remaining。
3. 插入 `ModelRunRecord` 并按当前 policy 扣减一次 quota unit。
4. 事务成功后最多发起一次上游 provider 调用。

第一轮不建立 reserve、settle、release-unused 或 reconcile 状态机。超时后客户端以同一 `client_run_id` 查询/重试；服务端不得创建第二条记录或第二次上游调用。若服务端无法证明上游结果，返回稳定 `RUN_OUTCOME_UNKNOWN` 并保留一次记录，不能通过新 ID 静默重放。

自定义 provider 完全绕过本账本，不消耗 PlotAgent 额度。

## 6. Built-in proxy 边界

- Proxy 接收已由本地 ContextBuilder 形成的请求；模型没有项目、文件、SQLite、Origin、URL 或本地工具访问权。
- 平台 provider secret 仅在服务端；客户端 DeviceCredential 不能换取或查看平台 key。
- Proxy 不保存 provider-hosted conversation 作为真相，不增加工具循环，只转发一个结构化 AgentDecision 请求。
- 取消会中止仍可中止的 HTTP 请求并把当前记录标 `cancelled`；是否消耗一次 quota unit按第5节已显示的简单Beta政策，不触发结算状态机。
- 每次 run 固定 `model_profile_id`；运行中不得静默切换。第一轮无 remote config，允许 profile 由客户端 build 的 allowlist 与服务端部署共同校验。

## 7. 日志与隐私

Proxy 日志不得记录 prompt、request body、response body、字段名、样本、原始数据或完整 ContextEnvelope。允许字段：

- `client_run_id`、invite/device 伪名。
- app/protocol/model profile version。
- quota unit、幂等命中、remaining bucket。
- latency、stable error、timestamps。

幂等响应的短期保存是请求处理状态，不得进入普通日志或长期分析仓库；保留时间和清理策略必须在服务实现时固定并对 Beta 管理员可见。第一轮无 analytics 或 DiagnosticBundle 上传端点。

## 8. 故障降级与重试

- 启动、打开项目、导入、手动 ActionPlan、自定义 provider、Preparation/PlotCalculation、绘图、PNG/SVG/OPJU 不访问本控制面。
- built-in 调用时才校验 DeviceCredential、InviteGrant 和 quota。
- 瞬时连接或 5xx 最多自动重试 2 次，必须复用同一 `client_run_id`。
- 用户取消、invite/device/quota 等确定性 4xx 不自动重试。
- 云失败不写项目事务；只有本地已校验 AgentDecision 与后续 ExecutionTask 才进入项目状态。
- `QUOTA_EXHAUSTED` 只禁用 built-in Agent，并提示 custom provider；本地能力保持可用。

## 9. strict local_only

`NetworkMode=local_only` 激活时，应用不得兑换邀请码、校验 DeviceCredential、查询额度或调用 built-in proxy。第一轮不存在 `update_only`、后台更新、analytics 或诊断上传例外，因此抓包验收必须为零远程出站。localhost 模型属于 custom provider mode，不属于 local_only。

## 10. 人工安装包分发

- 第一轮没有 CloudConfig、UpdateManifest、自动检查、应用内更新、后台下载或“重启并更新”。
- 用户通过应用外渠道人工取得 Beta 安装包；更新资格不要求邀请码或账号。
- 安装前由发行说明/校验工具或安装流程验证发布方签名、SHA-256 与 Windows code signature；任一不匹配返回稳定错误并阻断。
- strict local_only 应用本身不为更新发出网络请求。用户退出应用后显式运行已验证安装包。
- 自动更新、签名远程 manifest、差分下载和安装协调属于后续工程成熟度，不是当前 v1 强制要求。

## 11. 稳定错误

| Error | 条件 | 恢复 |
| --- | --- | --- |
| `INVITE_INVALID` | secret 无效 | 检查邀请 |
| `INVITE_EXPIRED` | grant 过期 | 联系邀请方 |
| `INVITE_REVOKED` | grant 撤销 | 切换 custom/local |
| `DEVICE_CREDENTIAL_INVALID` | 凭据无效 | 用原邀请码重新兑换 |
| `DEVICE_BLOCKED` | 单设备封禁 | 联系邀请方；本地能力继续 |
| `MODEL_PROFILE_UNAVAILABLE` | build/profile 不匹配 | 选择允许 profile 或升级人工安装包 |
| `QUOTA_EXHAUSTED` | shared remaining 为零 | custom provider 或本地手动 |
| `RATE_LIMITED` | 设备短时限制 | 按 `retry_after` 重试 |
| `IDEMPOTENCY_CONFLICT` | 同 run id 不同 context/profile | 创建新的明确用户请求 |
| `RUN_OUTCOME_UNKNOWN` | 无法证明上游最终状态 | 显示一次记录，不自动新ID重放 |
| `PROVIDER_UNAVAILABLE` | 上游/控制面不可用 | 同 run id有限重试或 custom provider |
| `INSTALLER_PUBLISHER_SIGNATURE_INVALID` | 发布签名异常 | 拒绝安装 |
| `INSTALLER_HASH_INVALID` | SHA-256 异常 | 拒绝安装 |
| `INSTALLER_WINDOWS_CODE_SIGNATURE_INVALID` | Windows签名异常 | 拒绝安装 |

## 12. Beta 验收矩阵

| 规则 | 验收 | 故障注入 |
| --- | --- | --- |
| 多设备共享 | 两设备消费同一 remaining | 并发请求/重装重兑 |
| 重试不重复 | 同 client_run_id 最多一次扣减与上游调用 | timeout/5xx/进程重启 |
| 幂等冲突 | 同 ID 不同 context 被阻止 | profile/context hash替换 |
| 撤销边界 | 只影响 built-in Agent | 本地项目/PNG/SVG/OPJU仍可用 |
| 云完全不可达 | 应用启动和本地流程不受影响 | DNS/TLS/5xx/connection reset |
| custom provider | 不访问额度、不扣计数 | built-in quota=0 |
| strict local_only | 全进程零出站 | redeem/quota/model/update/diagnostic尝试 |
| 日志 | 无 payload/字段/数据/secret | 恶意字段与错误堆栈 |
| 人工安装包 | 签名/hash/code signature均正确 | 三类篡改分别阻断 |
| 无硬件身份 | 服务端记录不能反推硬件 | installation重建/多Windows账户 |

通过本矩阵只证明小规模 Beta 控制面契约；生产级计费、token lifecycle、自动更新、远程配置和长期运维属于后续。
