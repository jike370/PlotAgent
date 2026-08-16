# PlotAgent 本地安全与诊断契约

> 状态：小规模邀请制 Beta 已确认边界
> 日期：2026-08-05
> 适用范围：启动入口与 NetworkMode、strict local_only、本地文件/进程安全、日志、本地 DiagnosticBundle、Schema 硬拒绝与崩溃后重试
> 相关文档：[产品决策基线](./PRODUCT-DECISIONS.md)、[项目存储与导入](./PROJECT-STORAGE.md)、[任务运行时](./TASK-RUNTIME.md)、[最小 Beta 云控制面](./CLOUD-CONTROL-PLANE.md)、[领域契约](./DOMAIN-CONTRACTS.md)

## 1. 工作入口与模型服务模式是两组概念

主窗口启动空状态始终保留三个工作入口：

1. 主按钮“用示例项目试用”。
2. 次按钮“导入自己的数据”。
3. 文字入口“打开已有 `.plotproj`”。

应用无需账号、邀请码、模型配置或联网即可使用这些入口；示例打开为可修改的本地副本，不使用多页向导。

首次真正需要 Agent 时，才在轻量服务选择或模型设置中出现：

```text
NetworkMode
├─ builtin_proxy
├─ custom_provider
└─ local_only
```

- 三种 NetworkMode 不是启动工作入口，切换模式不修改项目。
- localhost/127.0.0.1/::1 模型仍属于 `custom_provider`，不属于 `local_only`。
- `local_only` 是用户显式选择的严格模式，不是“暂时断网”的推断状态。

## 2. strict local_only 零出站

`NetworkMode=local_only` 激活期间应用不得：

- 兑换邀请码、校验 DeviceCredential、查询 quota 或调用 built-in proxy。
- 请求 custom provider，包括 localhost。
- 检查/下载更新或获取 remote config。
- 发送 analytics、DiagnosticBundle、telemetry、crash dump 或任意后台请求。
- 访问数据、聊天或模型输出中的 URL，执行 DNS prefetch 或打开 data URL。

第一轮没有 `OneTimeUpdateGrant`、`update_only` 或任何 strict local_only 联网例外。人工安装包由用户在应用外取得，退出应用后显式运行；PlotAgent 本身仍保持零出站。

local_only 下仍完整可用：确定性导入、字段映射、受控 Preparation、九类固定 PlotCalculation、手动选图和参数编辑、正式 43 图、同构批次、固定布局组合、项目资源、PNG/SVG，以及本机 exact Origin version 可用时的 O1 OPJU。九个内部隐藏图不会因离线模式而开放；手动 UI 构造与 Agent 相同的 ActionPlan 并进入相同 validator/executor/transaction 链。

## 3. 本地数据保护边界

- 第一轮不实现项目加密，依赖 Windows account ACL；建议敏感环境启用 BitLocker。
- `.plotproj`、Parquet、OPJU、结果项目包和导出都可能包含敏感科研数据，不得称为匿名、脱敏或隐私安全。
- built-in DeviceCredential、自定义 API key 只存 Windows Credential Manager，不进入 renderer、项目、SQLite普通字段、日志、Bundle 或命令行。
- 普通删除是 best effort，不承诺 secure erase；SSD、文件系统和备份可能保留旧块。

## 4. Workspace 与临时文件

- 活动项目 workspace 只允许本机固定磁盘；拒绝在 SMB、NAS、映射盘、UNC、云占位目录或其他不可靠网络文件系统直接运行 SQLite/WAL。
- 每个任务使用随机隔离 temp 目录，创建时设置当前用户专属 ACL；路径不得由模型、数据或用户表格内容决定。
- 成功、失败、取消和应用下次启动时清理应用已知 temp root 中的遗留目录；不递归扫描任意用户目录。
- 清理失败只记录不含路径的稳定错误，不能把临时对象注册为正式项目对象。
- 任务失败/崩溃后不要求自动续跑；必须确保已提交项目状态不损坏、未提交 temp 可清理，并给出明确“重试”动作。

## 5. 不可信 `.plotproj` 与 archive

打开外部 `.plotproj` 时先复制到新的随机 temp workspace，再逐项验证：

- manifest/schema/version、checksums、entry count、单文件大小、总 expanded size 与 compression ratio。
- 拒绝绝对路径、盘符/UNC、`..`、空/保留名、重复规范化路径、Unicode/case 冲突。
- 拒绝 symlink、hardlink、junction、mount point、reparse point、device/special file。
- 所有解包目标在写入前 `resolve` 并确认仍位于 temp root。
- 只有全部对象、SQLite快照和引用验证通过后才注册本机工作副本；失败不污染 catalog 或正式项目。

稳定错误包括 `ARCHIVE_UNSAFE_PATH`、`ARCHIVE_LINK_REJECTED`、`ARCHIVE_DUPLICATE_PATH`、`ARCHIVE_LIMIT_EXCEEDED`、`ARCHIVE_BOMB_SUSPECTED`、`PROJECT_PACKAGE_HASH_INVALID`。

## 6. Excel 与表格内容安全

- XLS/XLSX 中宏、VBA、Office Script、DDE、外部链接、数据连接、pivot refresh、公式和 volatile function 绝不执行或刷新。
- 公式只有文件内已有缓存值时可导入，并标记 `cached_formula_value` provenance；无缓存结果为 missing/NeedsInput。
- CSV/worksheet text、列名、单元格值和 URL 永远只是 data，不解释为公式、HTML、命令、脚本、Origin expression 或 Agent instruction。
- 模板、publication profile、chart package 和 `.plotproj` 不自动执行代码。

稳定错误包括 `FORMULA_UNCACHED`、`EXTERNAL_LINK_NOT_REFRESHED` 和 `MACRO_CONTENT_IGNORED`。

## 7. Electron 与模型边界

- renderer 开启 sandbox 与 `contextIsolation`，关闭 Node integration。
- preload 只暴露版本化、强类型、窄 allowlist API；参数由 Main/Core再次校验。
- 聊天、表格和模型内容按安全文本/受限 AST 渲染，不执行 HTML/JS，不自动打开链接。
- 任意外部链接只能由用户明确点击、经过 scheme/origin 检查并在系统浏览器打开；data 中的 URL 默认不可点击。
- 模型不能访问任意 path/URL/file/SQLite/Origin，不能执行 Python、LabTalk、SQL 或命令。

## 8. 本地日志

本地日志始终可用，按 14 天或 100 MB（先到者）轮换。允许字段：

- app/protocol/schema/renderer/adapter/dependency version。
- task state/stage、对象类型、chart ID、duration/performance bucket。
- row/column/primitive count bucket、stable error code、boolean feature flags。

禁止字段：用户提示、聊天、文件名、绝对/相对用户路径、列名、单元格值、样本/摘要、API key/credential/invite、模型 request/response body。Stack trace 落盘前 scrub 用户路径。第一轮不生成 process memory dump。

## 9. 第一轮无 analytics

- 第一轮不实现或发送 usage analytics，不提供 opt-in 事件上报，也不在本地积压事件等待未来发送。
- built-in proxy 自身允许的无 payload 运维日志由云契约约束，不属于桌面 usage analytics。
- 功能使用和用户成功指标通过经同意的 Beta 观察、访谈或问卷收集，不从隐藏 telemetry 推断。

## 10. LocalDiagnosticBundle

DiagnosticBundle 只在用户主动操作时生成：

1. 先构建候选文件清单。
2. UI 逐文件显示名称、用途、大小和 allowlisted 字段。
3. 对 JSON 显示 exact JSON 预览，对文本显示完整或明确分段预览。
4. 用户选择保存位置后写入本地包；应用不上传，用户自行发送。

默认允许：app/OS/Python/Origin/dependency/schema versions、Origin capability、stable errors、task state transitions、performance buckets、scrubbed stacks、非敏感 config flags、本地日志节选，以及不含列名/值的结构、计数、统计 bucket 与 content hash。

始终禁止：project/catalog DB 原件、preview/PNG/SVG/OPJU、`.plotproj`、prompt/聊天、文件名/路径、secret/credential/invite、模型 body、memory dump。列名/类别/单元格值/样本默认禁止；只有用户为本次 bundle 单独明确同意、先看到脱敏规则与 exact 文件预览时，才可加入专门的脱敏数据文件。同意不持久化，不能扩展到其他项目或下次 bundle，且应用仍只保存本地、不上传。

```text
LocalDiagnosticBundleManifest
├─ schema_version
├─ generated_at
├─ app_build
├─ files[]: logical_name, purpose, size, sha256
├─ allowed_field_counts
├─ sanitized_data_consent: absent | this_bundle
├─ sanitized_data_rules_hash?
├─ forbidden_scan_result
└─ user_selected_output_path # 仅当前操作，不写入包内容/日志
```

任何未知字段或 forbidden scan 命中返回 `DIAGNOSTIC_SCHEMA_VIOLATION` 并拒绝生成。第一轮没有 upload endpoint、diagnostic ID 或云端保留期。

## 11. Schema 硬拒绝

- 打开项目先只读读取 manifest/schema/version 并验证完整性。
- 当前 build 只接受项目 schema v5；其他版本返回 `SCHEMA_VERSION_UNSUPPORTED`，不编辑、不降级、不创建工作副本。
- 产品不存在旧 Schema 读取器、版本迁移器、旧对象别名、双写或兼容模式。
- 被拒绝项目保持字节不变；用户需使用创建该项目的旧版本自行导出数据，再在当前版本建立新项目。

## 12. 保存、备份与崩溃恢复边界

- 正常修改依赖 SQLite transaction、single writer、immutable CAS 和原子文件提交；失败不会发布半对象。
- 第一轮不创建每日 Online Backup、不保留最近三份、不提供恢复分支、RecoveryRecord 或恢复 UI。
- 用户主动导出的完整 `.plotproj` 是可搬运快照；产品不宣传自动备份或 cloud backup。
- 任务崩溃后 Electron/Core 可把遗留任务标 interrupted、清理 temp 并展示重试；不要求自动续跑或静默重放正式任务。
- `.plotproj` snapshot 仍使用 SQLite Online Backup 生成一致数据库快照，这是主动项目导出机制，不是每日恢复备份框架。

## 13. 稳定错误

| Error | 条件 | 恢复 |
| --- | --- | --- |
| `NETWORK_BLOCKED_LOCAL_ONLY` | strict local_only 触发远程请求 | 保持本地或显式切换 NetworkMode |
| `WORKSPACE_FILESYSTEM_UNSUPPORTED` | 活动 workspace 非本机固定磁盘 | 导入本机副本 |
| `TEMP_ACL_FAILED` | 无法建立用户专属 ACL | 不启动任务 |
| `TEMP_CLEANUP_FAILED` | 遗留 temp 清理失败 | 显示重试；不发布对象 |
| `ARCHIVE_*` | archive path/link/size/hash 不安全 | 拒绝包 |
| `FORMULA_UNCACHED` | 公式无缓存值 | missing/NeedsInput |
| `DIAGNOSTIC_SCHEMA_VIOLATION` | Bundle含未知/禁止字段 | 拒绝生成并显示命中类别 |
| `SCHEMA_VERSION_UNSUPPORTED` | 项目不是当前 schema v5 | 原项目保持不变；使用旧版本导出数据后建立新项目 |

## 14. Beta 验收矩阵

| 规则 | 验收 | 故障注入 |
| --- | --- | --- |
| strict local_only | 全进程抓包/DNS/HTTP mock零请求 | startup/provider/quota/update/diagnostic/URL |
| 断网本地闭环 | 导入、手动 TaskDraft、Preparation/PlotCalculation、正式34图、批量任务、三种导出 | 控制面/provider不可达 |
| 恶意 archive | traversal/link/bomb/hash全部阻断 | Unicode/case/size/ratio边界 |
| 表格不执行 | 宏/公式/外链不运行，cache provenance正确 | VBA/DDE/external refresh |
| Electron边界 | renderer无Node/secret/任意IPC | HTML/JS/data URL/path注入 |
| 日志/Bundle | 默认仅结构/统计/hash且禁止字段为零；单次脱敏数据同意/预览可撤回；Bundle只本地保存 | prompt/path/column/value/secret注入、无同意加样本 |
| 未知 schema | 稳定拒绝且原项目字节/对象不变 | future version/invalid manifest |
| 崩溃重试 | 已有项目不损坏、temp可清理、用户明确重试 | worker/Core/app终止 |
| 无自动备份 | 无后台backup/recovery状态或磁盘写入 | idle 24h/项目修改 |

本矩阵证明的是 Beta 本地安全、Schema 硬拒绝和诊断底线，不是商业级备份或灾难恢复承诺。
