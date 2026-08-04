# PlotAgent 邀请、额度、最小云控制面与软件更新契约

> 状态：第一轮云控制面协议基线已确认
> 日期：2026-08-05
> 适用范围：InviteGrant、DeviceCredential、QuotaLedger、内置 Model Proxy、签名配置与软件更新
> 相关文档：[本地安全、离线模式、诊断、迁移与恢复备份契约](./LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md)、[Agent 上下文、模型供应商与数据出境契约](./AGENT-CONTEXT-AND-PROVIDERS.md)、[后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)、[领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)、[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)

## 1. 核心原则与边界

- 邀请码代表一个 `InviteGrant`，不是账号、用户资料或单次安装许可证。
- 同一邀请码在有效期内可以在不限数量设备重复兑换；所有设备共享该 InviteGrant 的总额度。
- 设备只承担鉴权、设备级并发/短时限流与异常封禁，不获得独立赠送额度。重装和增加设备不能绕过 InviteGrant 总额度。
- 第一轮没有账号、邮箱、密码、个人资料、云端项目归属或找回流程。
- 邀请、令牌、额度或云服务状态永不成为本地项目的访问控制条件。
- 自定义 ModelProvider 由桌面端直连，不通过 PlotAgent proxy，也不消耗 PlotAgent 额度。

## 2. 最小云端范围

云端只提供：

1. 邀请兑换、短期 access token 与 refresh token 刷新。
2. 内置模型 proxy。
3. InviteGrant 共享额度、设备/邀请限流和幂等账本。
4. 签名、版本化 cloud config 与 update manifest。
5. 用户主动提交的诊断包入口；具体内容与保留规则由诊断契约定义。

第一轮明确不提供：

- 项目、会话、图表、模板、设置或 `.plotproj` 云同步。
- 账号资料、联系人、团队、共享空间或云端权限管理。
- 原始文件、派生数据、PlotSpec、OPJU 或完整模型 payload 的持久化。
- 远程科研计算、远程绘图、远程 Origin/OPJU 自动化。
- 远程修改项目、渲染算法、分析默认值或 publication snapshot。

应用启动和本地能力不依赖该控制面可用。

## 3. InviteGrant

### 3.1 领域对象

```text
InviteGrant
├─ invite_id
├─ secret_hash
├─ secret_hash_algorithm_version
├─ status: active | revoked | expired
├─ expires_at
├─ quota_policy_id
├─ allowed_model_profile_ids[]
├─ release_channel
├─ created_at
├─ revoked_at?
└─ policy_version
```

- 邀请 secret 必须由 CSPRNG 生成并具备足够熵；服务端只保存带版本的抗暴力破解 hash，不保存明文或可逆密文。
- 客户端只在兑换请求期间持有邀请码。成功后不进入文件、普通设置、SQLite、日志、诊断或命令行。
- 邀请在撤销或过期前可重复兑换；兑换不消耗“设备名额”。
- 管理端可以撤销整个 InviteGrant，或只封禁单个异常 DeviceCredential；两者必须有不同审计事件和客户端错误。
- `expires_at` 到达后状态按服务端时间判定；客户端时间不能延长有效期。

### 3.2 邀请状态机

```text
active ──expires_at──> expired
   │
   └──admin revoke──> revoked
```

`expired` 与 `revoked` 都停止新的内置 Agent 请求和 token refresh，但不删除设备记录、不锁定项目，也不影响自定义 provider 或本地能力。

## 4. 设备身份与令牌

### 4.1 Installation 与 DeviceCredential

- 首次兑换前由客户端 CSPRNG 生成随机 `installation_id`。
- 不采集或派生硬盘序列号、MAC、TPM ID、Windows 用户名、SID、主机名、设备名或其他硬件指纹。
- 服务端设备记录只能包含随机 installation/device ID、InviteGrant 伪名引用、状态、时间、限流与安全元数据；不得能够反推出硬件或 Windows 身份。
- 凭据丢失或重装后，用户可用原邀请码和新的 installation_id 再次兑换；没有云端找回流程，也不转移旧设备额度，因为额度本来就属于 InviteGrant。

### 4.2 Token 组合

成功兑换返回：

- 短期 access token，默认有效期 15 分钟。
- 长期 refresh token；服务端保存可撤销的 hash/rotation lineage，不保存明文。
- 设备状态、InviteGrant 状态摘要、允许的最小 scopes 和服务端时间。

refresh token 与内置设备凭据只存 Windows Credential Manager；renderer 只能看到不含 secret 的连接状态。Refresh token 建议单次轮换，旧 token 在成功轮换后失效；并发刷新必须通过 rotation family 与幂等规则消除双写。

### 4.3 Scopes 与 401 语义

Scopes 只允许：

- `invitation:status`
- `model:proxy`
- `quota:read`
- `config:read`

令牌不得授予项目、文件、SQLite、诊断内容或 Origin 读取权限。诊断上传使用一次性、用户主动流程授权，不能复用 model proxy scope。

401/403 响应必须以稳定错误区分：

- `TOKEN_EXPIRED`
- `INVITE_REVOKED`
- `INVITE_EXPIRED`
- `DEVICE_BLOCKED`
- `TOKEN_INVALID`

客户端不得把这些状态统一显示成“项目未激活”。

## 5. 兑换与刷新协议

### 5.1 通用 envelope

所有控制面请求/响应采用版本化 envelope：

```text
RequestEnvelope
├─ protocol_version
├─ request_id
├─ client_time
├─ client_version
├─ installation_id
├─ idempotency_key?
└─ payload

ResponseEnvelope
├─ protocol_version
├─ request_id
├─ server_time
├─ status: ok | error
├─ payload?
└─ error { code, retryable, retry_after?, details_schema_version? }?
```

Error details 只能包含修复所需结构化信息，不回显 secret、Authorization header 或模型 payload。

### 5.2 Redeem

`POST /invites/redeem` 输入 invite secret、随机 installation_id、客户端版本和支持的协议版本；成功输出 token 组合、device ID、InviteGrant 状态、release channel 与 QuotaSnapshot。

状态：

```text
idle -> submitting -> redeemed
                  ├-> invite_invalid
                  ├-> invite_expired
                  ├-> invite_revoked
                  ├-> rate_limited
                  └-> transient_failure
```

成功前不清除用户输入；成功后立即从内存/UI 清除邀请码，不持久化。

### 5.3 Refresh

`POST /tokens/refresh` 使用 refresh token 与 installation_id，成功时原子轮换 refresh token 并返回新 access token。客户端仅在调用内置 Agent 或读取云状态时 lazy refresh，不要求应用启动时刷新。

瞬时连接或 5xx 最多自动重试 2 次；同一次刷新复用 request/idempotency lineage。用户取消、认证 4xx、邀请撤销/过期和设备封禁不重试。

## 6. 共享额度与幂等账本

### 6.1 归属与 QuotaSnapshot

额度 ledger 的 owner 是 `invite_id`。Device ID 仅作为限流和审计维度。

```text
QuotaSnapshot
├─ period_start
├─ period_end
├─ granted
├─ reserved
├─ consumed
├─ remaining
├─ reset_at
└─ server_time
```

- `remaining = max(0, granted - reserved - consumed)`，所有值使用同一版本化计量单位。
- 具体 grant 数值、周期、每设备并发和短时速率属于版本化服务策略，不写死在客户端。
- 服务端可限制每设备并发/短时速率，但不得通过设备总数限制改变“不限设备”的产品语义。
- 429 必须返回 `RATE_LIMITED` 与 `retry_after`。
- `QUOTA_EXHAUSTED` 只禁用内置 Agent，UI 提供切换自定义 provider；本地手动能力始终可用。

### 6.2 ModelRun ledger

每次用户 Agent 请求生成全局唯一 `client_run_id`，并将其作为 `Idempotency-Key`。服务端对 `(invite_id, client_run_id)` 建立唯一约束。

```text
requested -> reserved -> upstream_running -> settled
                    │                ├-----> settled_with_validation_failure
                    │                └-----> cancelled_after_usage
                    ├-> released
                    └-> cancelled_before_usage
```

1. **Reserve**：调用上游前按策略预留最大允许量；额度不足时不调用上游。
2. **Settle**：上游完成后按实际 input/output/repair usage 结算，并释放未用 reserve。
3. **Cancel/release**：上游未消费时释放全部；已消费时结算实际 usage 后释放其余。
4. 相同 client_run_id 的重试返回同一 ledger 状态/结果引用，不重复 reserve 或扣减。
5. 上游已消费但本地/代理 schema 或业务校验失败时，仍按实际 usage 记账；错误与账本状态并存。
6. repair usage 计入同一 client_run_id，UI 按一次用户任务汇总，而非显示两次扣费。
7. Idempotency-Key 被不同 payload/context hash 复用时返回 `IDEMPOTENCY_CONFLICT`，绝不猜测覆盖。

Proxy 崩溃恢复时必须从持久化账本继续 settle/reconcile；不能因为超时、客户端重启或响应丢失重复调用上游或重复扣费。

## 7. 内置模型 Proxy 与日志

- Proxy 接收已授权的 ContextEnvelope、固定 model profile/config version、AgentDecision Schema 和 client_run_id。
- 上游平台 key 只在服务端 secret store；不下发客户端、不写日志。
- Proxy 不记录 prompt/request body/response body、字段、样本、原始数据或 reasoning。
- 允许记录的元数据仅为 run ID、InviteGrant/device pseudonymous IDs、model profile/config version、token usage、latency、稳定 error code、timestamps、幂等和额度状态。
- DataDisclosure 与供应商保留说明遵循 [Agent 上下文、模型供应商与数据出境契约](./AGENT-CONTEXT-AND-PROVIDERS.md)；“proxy 不记录 payload”不能被宣传为底层供应商零保留。
- 一次 run 固定 model/profile/config；服务端不能在运行中静默换模型。不可用时返回稳定错误，由用户明确重试或选择其他 provider。

## 8. 故障降级与重试

- 应用启动、打开项目、导入、分析、手动 ActionPlan、绘图、组合、PNG/SVG/OPJU 和自定义 provider 均不依赖控制面。
- 不在启动关键路径刷新 token、查 quota 或等待 cloud config；内置 Agent 调用时才 lazy refresh/status check。
- 兑换、refresh、quota、config 或 proxy 失败不得开启/回滚项目 SQLite 事务。
- 瞬时连接错误或 5xx 最多自动重试 2 次，并复用原 request/client_run/idempotency lineage。
- 用户取消、确定性 4xx、permission/error schema validation 不自动重试。
- 控制面完全不可达时显示“内置 Agent 暂不可用”，不把整个应用标为离线损坏。

## 9. 签名 CloudConfig

Remote config 只能声明：

- 可用的 cloud model profiles 与固定版本。
- quota display/policy identifiers。
- cloud protocol compatibility。
- 服务/区域可用性与维护状态。
- `min_cloud_version` 和签名 update manifest location。

Remote config 不能改变：

- resolver、坐标、ticks、渲染算法或图形准入。
- 分析方法、统计默认值、拟合公式或科学 warning。
- 已有项目、DatasetVersion、AnalysisSpec/Result、PlotSpec/FigureSpec。
- style/publication/package snapshot。

配置必须 HTTPS 获取并由应用内置 public key 验签；运行时固定 config/profile version 并写入 ModelRunAudit。

## 10. 软件更新

### 10.1 与邀请解耦

- 更新资格不要求邀请码、设备 token、账号或内置 provider；使用自定义 provider 或不使用模型的用户同样有资格取得更新。
- `NetworkMode=local_only` 严格激活期间绝不检查、下载或请求更新 manifest。用户只有显式退出 local_only、创建内存态 `OneTimeUpdateGrant`，或人工取得已签名离线安装包，才可更新。
- OneTimeUpdateGrant 生效期间，持久 NetworkMode 仍为 local_only，但 transient `effective_network_policy=update_only`，严格 local_only 暂时不处于激活态。update_only 只允许当前 update manifest check/package download，不能授权 Agent、token/quota、analytics、diagnostics、remote config、release notes 或任意 URL；完成、失败、取消、过期或应用退出后立即回到严格 local_only。
- 允许联网更新的模式下，启动完成后异步检查；之后最多每 24 小时一次。检查失败不阻塞应用。
- Manifest 与 package 仅通过 HTTPS；Authorization 不跨 origin redirect。

### 10.2 UpdateManifest

```text
UpdateManifest
├─ manifest_schema_version
├─ channel
├─ version
├─ published_at
├─ package_url
├─ package_sha256
├─ package_size
├─ release_notes_url
├─ min_cloud_version
├─ supported_cloud_protocol_versions[]
└─ signature
```

- Manifest 使用应用内置 public key 验签。
- Package 下载完成后校验精确 size、SHA-256 与 Windows Authenticode code signature。
- 人工取得的离线安装包必须执行相同的内置 manifest signature、package size/SHA-256 与 Windows code signature 校验，不能因为离线来源而降级。
- Manifest/package 篡改、签名/哈希/证书错误、非法 scheme 或跨 origin credential redirect 全部阻断。
- 下载使用隔离临时文件并支持安全断点/重试；失败不改变当前安装或项目。

### 10.3 更新状态机与 UX

```text
idle -> checking -> available -> downloading -> downloaded -> awaiting_user_restart
           └-----> no_update       └-----------> failed
awaiting_user_restart -> preflight_deferred | installing_on_explicit_restart
```

- 可以后台下载，但运行 ExecutionTask、Origin 导出、项目保存/committing 或迁移期间不得安装。
- 必须由用户点击“重启并更新”；普通更新可延后，不静默重启。
- 安装前再次检查应用任务、项目提交和 Origin 管理实例安全边界。
- `min_cloud_version` 只阻止过旧客户端调用内置云服务，不阻止打开项目、自定义 provider 或本地手动能力。
- 第一轮不允许 remote config 触发静默强制安装。

## 11. API 与领域命令

| 操作 | 输入关键字段 | 输出/状态 | 幂等规则 |
| --- | --- | --- | --- |
| `redeem_invite` | invite secret、installation ID、protocol/client version | credentials、grant/device status、quota | request id；重复安全返回同一 device lineage |
| `refresh_token` | refresh token、installation ID | rotated credentials、status | rotation family + request id |
| `get_quota_snapshot` | access token | 固定 QuotaSnapshot | 只读 |
| `reserve_model_run` | client_run ID、context hash、profile、estimate | reservation ID/snapshot | `(invite_id, client_run_id)` 唯一 |
| `settle_model_run` | reservation、actual usage、upstream status | ledger final/snapshot | output usage record 唯一 |
| `cancel_model_run` | client_run/reservation、observed usage | released 或 settled | 重复取消返回当前 final state |
| `get_signed_config` | client/protocol versions、channel | signed config | 只读、ETag 可缓存 |
| `check_update` | channel、current version/platform | signed UpdateManifest | 只读、无邀请依赖 |

协议只定义领域语义和 envelope，不绑定部署商、数据库产品、云函数平台或上游模型供应商。

## 12. 稳定错误

| Error code | 条件 | 客户端行为 |
| --- | --- | --- |
| `INVITE_INVALID` | secret 不存在/格式非法 | 不持久化，允许重新输入 |
| `INVITE_EXPIRED` | grant 过期 | 内置 Agent 不可用，本地不受影响 |
| `INVITE_REVOKED` | grant 被撤销 | 清除设备凭据；本地不受影响 |
| `DEVICE_BLOCKED` | 单设备封禁 | 可用原邀请码新兑换是否允许由安全策略返回，不假装 grant revoked |
| `TOKEN_EXPIRED` | access token 到期 | 尝试一次 lazy refresh |
| `TOKEN_INVALID` | token 非法/rotation reuse | 清除无效凭据并提示重新兑换 |
| `QUOTA_EXHAUSTED` | InviteGrant remaining 为零 | 提供自定义 provider；本地不受影响 |
| `RATE_LIMITED` | invite/device 速率或并发限制 | 遵守 retry_after |
| `IDEMPOTENCY_CONFLICT` | 同 client_run ID 不同 payload | 阻止，生成新用户任务才用新 ID |
| `PROVIDER_UNAVAILABLE` | 内置上游不可用 | 保持 run/ledger 状态，明确重试 |
| `UPGRADE_REQUIRED` | 低于 min_cloud_version | 仅禁用内置云服务并提供更新 |
| `CLOUD_PROTOCOL_UNSUPPORTED` | 无共同协议版本 | 更新应用；本地不受影响 |
| `MANIFEST_INVALID` | 清单 schema/字段非法 | 阻止更新 |
| `SIGNATURE_INVALID` | config/manifest/包签名失败 | 阻止并记录本地安全错误 |
| `PACKAGE_HASH_INVALID` | size/SHA-256 不匹配 | 删除临时包并阻止 |
| `PACKAGE_CERTIFICATE_INVALID` | Windows code signature 无效 | 阻止安装 |
| `REDIRECT_BLOCKED` | credential 跨 origin 或非法 redirect | 阻止请求 |

## 13. 验收与故障注入矩阵

| 契约 | 验收 | 故障注入 |
| --- | --- | --- |
| 多设备共享额度 | 两个 installation 消耗同一 InviteGrant snapshot | 并发 reserve、第三设备兑换 |
| 重装不可绕过 | 新 installation 仍看到同一 consumed/remaining | 删除本地凭据后重兑 |
| 无硬件指纹 | 服务端记录字段 allowlist 审计 | 注入 hostname/MAC/SID 并确认拒绝 |
| 兑换可重复 | 有效 secret 多次获得独立 device credentials | revoke grant、block 单设备、过期边界 |
| 令牌最小权限 | token scope 无项目/文件权限 | 伪造 scope、expired/revoked/blocked 401 |
| 幂等扣费 | 超时、重试、客户端/代理重启只结算一次 | reserve 后断电、settle response 丢失、ID 冲突 |
| 实际 usage | schema/业务校验失败仍结算已消费量 | 上游成功后返回非法 AgentDecision |
| 自定义 provider | 不经过 quota ledger | 内置额度耗尽时调用自定义 endpoint |
| 额度耗尽降级 | 只禁用内置 Agent | quota=0 后执行手动 ActionPlan/PNG/SVG/OPJU |
| 控制面不可达 | 应用启动并打开项目 | DNS/timeout/5xx/离线启动 |
| 云失败无项目事务 | project DB 无对应写事务 | redeem/refresh/quota 每阶段失败 |
| Proxy 无 payload 日志 | 日志 allowlist 扫描 | prompt/sample/reasoning 注入 |
| 更新资格与网络模式 | 无邀请码可更新；严格 local_only 零请求；update_only 仅 manifest/package；离线包完整验签 | revoked invite、custom provider、local_only/update_only 抓包、取消/失败/重启、篡改离线包 |
| 更新安装闸门 | 活跃任务/Origin/committing 时只 deferred | 每个阶段触发“重启并更新” |
| 更新完整性 | manifest signature、包 hash/code signature 全通过 | 篡改清单/包、错误证书、非法 redirect |
| 更新中断安全 | 当前安装和项目仍可用 | 下载/校验/启动安装前断电 |
| min cloud version | 只阻断内置云服务 | 旧客户端打开项目并导出 |
| Remote config 边界 | 只接受允许字段且 run 固定 version | 尝试更改 renderer/analysis/PlotSpec、run 中换模型 |

第一轮实现只有在上述协议、状态机、幂等恢复和安全负面测试通过后，才开放内置 provider 与自动更新通道。
