# PlotAgent 本地安全、离线模式、诊断、迁移与恢复备份契约

> 状态：第一轮本地安全与生命周期基线已确认
> 日期：2026-08-05
> 适用范围：NetworkMode、本地权限、不可信导入、日志/分析/诊断、Schema migration、兼容与恢复备份
> 相关文档：[项目存储、项目包与数据导入](./PROJECT-STORAGE.md)、[任务运行时、取消与崩溃恢复](./TASK-RUNTIME.md)、[Agent 上下文、模型供应商与数据出境契约](./AGENT-CONTEXT-AND-PROVIDERS.md)、[邀请、额度、最小云控制面与软件更新契约](./CLOUD-CONTROL-PLANE.md)、[领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)、[后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)、[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)

## 1. 两组三入口必须分离

### 1.1 主窗口工作入口

首次启动/启动空状态始终只有既有三个工作入口：

1. 主按钮“用示例项目试用”。
2. 次按钮“导入自己的数据”。
3. 文字入口“打开已有 `.plotproj`”。

应用无需账号、邀请码、模型配置或联网即可使用这些入口。示例打开为可修改的本地副本；不使用多页向导或同权重卡片网格。

### 1.2 模型服务模式

首次真正需要 Agent 时，以轻量服务选择或模型设置提供三种模式；它们不是启动工作入口：

```text
NetworkMode
├─ builtin_proxy   # 邀请码兑换的内置服务
├─ custom_provider # 用户配置的 OpenAI-compatible endpoint
└─ local_only      # 明确零远程出站
```

- `builtin_proxy` 遵循 InviteGrant、设备令牌、共享额度和 DataDisclosure 契约。
- `custom_provider` 由桌面端直连已配置 endpoint；localhost/127.0.0.1/::1 仍属于 custom provider，不属于 local_only。
- `local_only` 是明确安全模式，不是“网络暂时不可用”的推断状态。
- 切换 NetworkMode 只修改本机全局设置/凭据选择，不迁移、不改写项目，也不改变 ActionPlan、PlotSpec 或历史。

## 2. local_only 零出站契约

`NetworkMode=local_only` 激活期间应用不得：

- 兑换邀请码、刷新/校验 token 或查询 quota。
- 调用内置或自定义 ModelProvider，包括 localhost provider。
- 检查、下载更新或读取远程 config/manifest。
- 发送 usage analytics、DiagnosticBundle、崩溃报告或任何 telemetry。
- 抓取 URL、加载远程帮助、远程字体、外部图像或远程 release notes。

local_only 下仍完整可用：

- 示例、本地项目、数据导入、字段映射与项目资源库。
- 手动选择 31 项图形、参数编辑、绘图、重绘和版本管理。
- TransformSpec、AnalysisSpec/FitSpec、批量绘图/审阅与数值 Figure。
- 正式 PNG、SVG 和本机 Origin 可用时的 O1 OPJU 导出。
- 日志、迁移、恢复备份和用户手动生成的本地 DiagnosticBundle 预览；不能发送。

手动 UI 构造与 Agent 相同的 ActionPlan 并进入相同本地 validator/executor/transaction 链。断网或 local_only 不是降低科研校验、正式数据完整性或 OPJU O1 要求的理由。

设置中持久切换离开 local_only 必须是用户显式操作。另一条受限路径是创建内存态 `OneTimeUpdateGrant`：

```text
OneTimeUpdateGrant
├─ grant_id
├─ created_at / expires_at
├─ allowed_operation: update_check_and_download
├─ allowed_manifest_origin
├─ allowed_package_origin
└─ state: active | completed | failed | cancelled | expired
```

- OneTimeUpdateGrant 不写入持久 NetworkMode、项目、catalog 或 Credential Manager。
- Grant active 时，持久设置仍为 `NetworkMode=local_only`，但 `effective_network_policy` 明确变为 transient `update_only`；严格 local_only 暂时不处于激活态。
- `update_only` 只允许当前签名更新流程的 manifest check 和 package download。它不允许 Agent、token/quota、analytics、diagnostics、remote cloud config、release notes 页面、任意 URL 或后台 update scheduler。
- Grant 完成、失败、取消、过期或应用退出后立即销毁，`effective_network_policy` 恢复为严格 local_only；未完成下载不会因重启自动联网续传。
- UI 必须在发出请求前显示临时 update_only 状态与取消入口；抓包验收将严格 local_only 与 update_only 分开测试。

## 3. 本地保密边界

### 3.1 不提供项目加密

- 第一轮不实现应用级项目数据库、CAS 或 `.plotproj` 加密。
- 本地机密性依赖当前 Windows account ACL；产品建议敏感数据用户自行启用 BitLocker 或组织批准的全盘加密。
- `.plotproj`、Parquet、OPJU、完整项目包和结果项目包都可能包含敏感科研数据，不得标为匿名、脱敏、隐私安全或适合公开共享。
- 结果项目包省略原始文件也不能推导为隐私安全；派生值、图形、分析与元数据仍可能泄露研究内容。
- 自定义 API key、内置 refresh/device credential 只进入 Windows Credential Manager。

### 3.2 活动工作区与固定磁盘

- 活动项目 workspace 只允许位于本机固定磁盘。
- 网络共享、同步盘的在线占位目录、可移动远程挂载或其他不满足本地 WAL/锁语义的路径不得直接运行 `project.sqlite3`。
- `.plotproj` 可以从外部位置选择，但必须先导入本机新工作副本；原包不作为活动数据库。
- 拒绝路径时返回稳定错误并提供选择本机目录，不静默复制到未知位置。

## 4. 临时文件与清理

- 每个任务使用 CSPRNG 随机名称的独立 temp root，不在任务间共享 staging 文件。
- 创建后立即设置当前 Windows 用户专属 ACL；继承范围与 effective ACL 必须验证。
- 成功、失败、取消以及启动时的 interrupted recovery 都执行清理状态机。
- 普通删除是 best effort；SSD、文件系统日志、备份和底层存储使 secure erase 无法保证，产品不得宣传安全擦除。
- 清理失败记录不含路径的稳定错误与重试状态；下次启动只扫描应用已知 temp root，不递归清理任意目录。

```text
TempCleanupState = active | cleanup_pending | cleaned | cleanup_failed
```

任务提交前的临时对象不进入正式 project refs；CAS 对象只有在内容校验和 SQLite 事务提交后成为权威对象。

## 5. 不可信 `.plotproj` 与 Archive

### 5.1 解包前预检

在创建/注册工作副本前先校验：

- manifest schema/version、signature policy（若有）、checksums 文件与每个声明对象 hash。
- entry count、每文件 uncompressed size、总 expanded size、压缩比和产品资源预算。
- 路径规范化后唯一；拒绝绝对路径、drive/UNC prefix、`..`、空/控制字符和重复 normalized/case-folded path。
- 拒绝 symlink、hardlink、junction、mount point、NTFS reparse point 和 archive 中的特殊设备类型。
- 拒绝嵌套 archive 自动递归展开与 archive bomb。

### 5.2 隔离验证与注册

1. 始终解包到新建随机 temp workspace，且不跟随链接/reparse point。
2. 流式写入时同时实施单文件、总量和压缩比限制，不能只信 header。
3. 校验 manifest、每个 hash、SQLite 快照完整性、对象引用和包类型约束。
4. 全部通过后才移动为本机项目工作副本并在 catalog 注册。
5. 任一失败清理 temp；catalog/project DB 不出现半注册记录。

## 6. Excel、CSV 与表格内容安全

- XLS/XLSX 中宏、VBA、Office Script、DDE、外部链接、数据连接、pivot refresh、公式和 volatile function 绝不执行或刷新。
- 公式单元格只有文件内存在缓存结果时导入缓存值，并保存 `cached_formula_value` provenance、公式存在标记和 parser version；公式文本不执行。
- 缺少缓存结果时该值为 missing；若必需字段因此无法成立则返回 `FORMULA_VALUE_UNCACHED`/NeedsInput，不启动 Excel 求值。
- 外部 workbook link 即使带缓存也标记来源，不联网刷新。
- CSV/worksheet text 只作为 data，不解释为公式、命令、HTML、Markdown script、Prompt instruction 或 Origin expression。
- 项目、template、publication profile、chart package 和 SafeRichText 不自动执行代码；未知 executable member 使包校验失败。

## 7. Electron 本地权限边界

- Renderer 启用 Chromium sandbox 与 `contextIsolation`，关闭 Node integration。
- Preload 只暴露强类型、逐项、参数受限 API；不暴露通用 `ipcRenderer.send`、shell、fs、process 或任意 channel。
- Electron Main 校验 renderer 消息，并通过系统 file picker 把用户授权路径转换为 scoped resource ID。
- 对话、列名、单元格、SafeRichText 和模型文本用安全组件渲染；不执行 HTML/JavaScript，不自动打开 `data:` URL 或数据中的链接。
- 外部网页只允许用户显式点击应用拥有的 allowlist 链接，并经过 scheme/origin 展示；数据 URL 始终不可点击抓取。
- ModelProvider 没有任意 path/URL/file API，ContextEnvelope 只含带版本对象引用与已授权数据。

## 8. 本地结构化日志

### 8.1 保留与轮换

- 本地日志始终可用，不属于 analytics。
- 保留最多 14 天或总计 100 MB，先到即按最旧文件轮换。
- 日志文件位于应用本地日志目录并使用当前用户 ACL，不进入项目或 `.plotproj`。
- 第一轮不创建、收集或上传 process memory dump/core dump。

### 8.2 Allowlist

只允许：

- app/protocol/schema/renderer/adapter/dependency version。
- task/run 状态、阶段和结构化对象类型。
- chart type ID、feature flag ID 与 stable error code。
- timing、memory bucket、row/column count bucket 和 retry/attempt count。
- 不含用户内容的 stack frame module/function；落盘前 scrub 用户路径。

禁止：

- 用户提示、聊天正文、文件名、sheet 名、绝对或相对用户路径。
- 列名、类别、单元格值、数据摘要、样本、图表文字或注释。
- API key、token、invite secret、Authorization、connection string。
- 模型 request/response body、AgentDecision 原始 transport、reasoning。

Logger 使用字段 allowlist 而不是 denylist；未知字段拒绝写入并产生本地 `LOG_SCHEMA_VIOLATION` 计数。

## 9. 匿名 Usage Analytics

- 默认关闭；只有用户在设置中 opt-in 后发送。
- 启用页展示完整事件 schema、保留时间和当前 endpoint，不使用笼统“帮助改进”。
- 事件只允许预定义 `event_name`、`event_version`、chart ID、feature flags、timing bucket、success 与 stable error code。
- 不允许 free text、对象名、project/device persistent ID、路径、字段、数值、样本或 prompt。
- 原始事件服务端最多保留 30 天；之后只能保留不可关联到设备/邀请的 aggregate。
- local_only 强制停止发送，不排队等待未来自动补传；切出 local_only 后只发送新事件。
- Opt-out 立即停止新事件并清除未发送队列，不删除本地项目。

## 10. DiagnosticBundle

### 10.1 用户主动流程

每次诊断必须由用户主动执行：

1. 本地收集候选项。
2. 展示逐文件清单、size/hash 和每个 JSON 的 exact 展开预览。
3. 用户可取消或移除可选项。
4. 明确点击发送；local_only 下发送动作被阻止，允许只保存本地包。
5. 上传成功返回不含个人信息的 diagnostic ID。

### 10.2 允许内容

- app、Windows、Python、Origin、originpro、关键 dependency 和 schema versions。
- Origin install/capability/adapter/template/font 检测状态，不含安装路径。
- stable errors、ExecutionTask state transitions 与 performance buckets。
- 已 scrub 的 stack、已知 config/feature flags、NetworkMode 名称和本地日志受控摘录。
- Diagnostic manifest、每个成员 hash/size/schema version 与用户确认时间。

### 10.3 禁止内容与保留

禁止 project/catalog DB、数据文件、preview、PNG/SVG/OPJU、`.plotproj`、prompt、聊天、文件名、路径、列名、类别、数值、样本、secret、token 与 memory dump。

Bundle builder 对每个成员先做 strict schema validation；任何未知字段或禁止内容命中都阻止生成/上传。服务端原始包最多保留 30 天后删除；diagnostic ID 可继续关联不含内容的处理状态。

```text
DiagnosticBundleManifest
├─ schema_version
├─ created_at
├─ app/session versions
├─ files[] { logical_name, schema_id, size, sha256 }
├─ forbidden_content_scan_version
└─ user_confirmation_at
```

## 11. Schema Migration

### 11.1 MigrationPlan

迁移开始前：

1. 以只读方式读取 `.plotproj`/workspace manifest、schema versions 与完整性信息。
2. 对未来新 schema 立即拒绝编辑，不猜测降级。
3. 构建确定性 `MigrationPlan`，展示源/目标版本、逐步 `N→N+1` steps、预计对象/空间/时间与可恢复边界。
4. 用户确认后使用 SQLite Online Backup 创建一致快照；禁止复制活跃 WAL 文件。
5. 在新的临时 workspace 逐步执行，不改原 workspace。

```text
MigrationPlan
├─ plan_id
├─ source_schema_version
├─ target_schema_version
├─ source_manifest/hash
├─ steps[]: MigrationStep
├─ required_free_space
├─ validation_profile_version
└─ expected_semantic_hashes

MigrationStep
├─ from_version
├─ to_version
├─ implementation_version
├─ representation_changes[]
└─ validation_rules[]
```

### 11.2 验证与原子切换

临时 workspace 必须验证：

- SQLite integrity/foreign keys、object counts/types/refs。
- CAS hashes、Dataset rows/columns/schema/UnitSpec/lineage。
- version DAG、current pointers、task/export/history references。
- PlotSpec/AnalysisSpec/FitSpec/FigureSpec 与 resolved semantic hashes。

全部通过后原子切换 catalog 的 active workspace pointer；原 workspace 与旧对象在迁移成功记录持久化前保留。失败或取消继续使用原项目，绝无 partially migrated state。

`MigrationRecord` 保存 plan/step/version、source/target hash、backup ref、验证报告、状态、时间与稳定错误。

### 11.3 科研/视觉语义不可伪装迁移

Migration 只能改变存储表示，不能改变：

- chart type、field mapping、UnitSpec 或 DatasetVersion 内容。
- statistical method、missing policy、fit formula/initializer/bounds。
- style、axis/ticks、visual result、renderer/theme/publication/package snapshot。

科学或渲染语义新版本必须由用户显式执行“adopt new version”，创建新的 AnalysisResult、PlotSpec 或 FigureSpec 并保留旧版本；不能把行为改变隐藏在 migration。

## 12. Compatibility 与旧组件

- 项目固定旧 renderer、theme、publication profile、chart/analysis package 与 adapter snapshot。
- 旧组件缺失时可展示项目中已有 preview/result；需要重绘时返回 `LEGACY_COMPONENT_MISSING`，不得换用当前算法、模板或近似图形。
- 遇到应用不认识的未来 schema，拒绝编辑、迁移和写回，并提示升级；允许只展示经安全验证的外部静态信息必须由独立 viewer 契约定义，第一轮不猜测。
- 第一轮不支持 save-as-old、downgrade migration 或兼容 writer。
- 已有结果能查看不表示可复现重绘；UI 必须分别显示“可查看”和“可重算/重绘”。

## 13. Recovery Backup

### 13.1 正常保存与每日备份

- 日常修改依赖 project SQLite transaction、WAL 与 immutable CAS，不在每次操作复制整个项目。
- 每个活动项目每日最多创建一次 SQLite Online Backup，按项目保留最近 3 份成功备份。
- Backup 在一致读取点生成并验证 integrity/refs；CAS 对象不可变且不就地修改，因此备份记录引用对象 hash，而不是重复复制全部 CAS。
- 迁移成功并过验证/切换前保留旧 workspace 和旧对象。
- 用户主动导出的完整 `.plotproj` 才是可搬运项目快照；每日本地 DB backup 不是 cloud backup，产品不得这样宣传。

### 13.2 恢复

- 恢复必须由用户查看 backup time/schema/object summary 后明确确认。
- 从备份创建新的 recovery candidate/workspace，完整验证后作为新的 project recovery record；不在原 workspace 上静默 rollback 或覆盖当前状态。
- 用户可以保留当前副本并将恢复结果作为新恢复分支/工作副本打开。
- `BackupRecord`/`RecoveryRecord` 保存 source project/schema、backup/hash、CAS set hash、验证、状态、时间和原因。

```text
BackupState = scheduled | creating | validating | succeeded | failed | expired
RecoveryState = proposed | restoring | validating | ready | adopted | failed | cancelled
```

## 14. 稳定错误

| Error code | 条件 | 恢复动作 |
| --- | --- | --- |
| `NETWORK_BLOCKED_LOCAL_ONLY` | 严格 local_only 触发任何远程请求 | 保持本地；显式切换或创建 OneTimeUpdateGrant |
| `ONE_TIME_UPDATE_GRANT_REQUIRED` | local_only 无有效 grant 请求更新 | 取得明确同意或使用离线包 |
| `ONE_TIME_UPDATE_GRANT_EXPIRED` | update_only grant 终止/过期 | 立即回到 local_only；重新确认才可联网 |
| `WORKSPACE_NOT_LOCAL_FIXED_DISK` | 活动 workspace 位于网络/不受支持卷 | 选择本机固定磁盘导入副本 |
| `TEMP_ACL_INVALID` | 临时目录 ACL 不满足 | 阻止任务并修复目录权限 |
| `ARCHIVE_UNSAFE_PATH` | absolute/`..`/重复规范化路径 | 拒绝导入 |
| `ARCHIVE_LINK_FORBIDDEN` | link/junction/reparse/special entry | 拒绝导入 |
| `ARCHIVE_RESOURCE_LIMIT` | entry/size/ratio 超预算或 bomb | 拒绝并显示限制 |
| `ARCHIVE_HASH_INVALID` | manifest/checksum/object hash 失败 | 拒绝注册 |
| `FORMULA_VALUE_UNCACHED` | 必需公式无缓存值 | 作为 missing 并 NeedsInput/换文件 |
| `LOG_SCHEMA_VIOLATION` | 日志出现非 allowlist 字段 | 丢弃事件并本地计数 |
| `DIAGNOSTIC_SCHEMA_VIOLATION` | bundle 未知/禁止字段 | 阻止生成/上传 |
| `MIGRATION_UNSUPPORTED` | 无完整 N→N+1 路径 | 保持原项目并升级应用 |
| `MIGRATION_FAILED` | step 失败/崩溃 | 删除候选，继续使用原项目 |
| `MIGRATION_VALIDATION_FAILED` | refs/hash/count/semantic 验证失败 | 不切换，保留诊断 |
| `NEWER_SCHEMA_UNSUPPORTED` | 项目 schema 高于应用 | 拒绝编辑并提示升级 |
| `LEGACY_COMPONENT_MISSING` | 重绘所需旧组件缺失 | 只看现有结果或安装兼容组件 |
| `BACKUP_FAILED` | 在线备份/验证失败 | 项目继续工作并显式重试 |
| `RESTORE_FAILED` | 恢复候选失败 | 当前项目不变，保留失败记录 |

## 15. 验收与故障注入矩阵

| 契约 | 验收 | 故障注入 |
| --- | --- | --- |
| 两组三入口 | 启动空状态仍为示例/导入/打开；服务模式只在 Agent/设置 | 首次启动无网、无 invite、无 provider |
| local_only 零出站 | 严格 local_only 全进程抓包/DNS/HTTP mock 为零 | 启动、24h update tick、analytics、诊断发送、数据 URL |
| 一次性 update_only | 仅 manifest/package origin 可达，终止即回 local_only | Agent/quota/config/analytics/diagnostic/任意 URL、取消/失败/重启 |
| 断网本地闭环 | 导入、手动 ActionPlan、分析、batch/Figure、PNG/SVG/OPJU | 控制面和 provider 全不可达 |
| localhost 边界 | localhost 只在 custom_provider 模式调用 | local_only 配置仍保留 localhost endpoint |
| 项目非加密文案 | UI/导出无匿名/隐私安全承诺 | 完整/结果包、Parquet、OPJU 检索文案 |
| 固定磁盘工作区 | 网络共享不能运行 SQLite/WAL | UNC、mapped drive、sync placeholder |
| Temp ACL/清理 | 每任务隔离且 success/fail/cancel/recovery 清理 | ACL inheritance 失败、进程崩溃、文件锁 |
| Archive 安全 | traversal/link/bomb/hash 全阻止 | absolute、`..`、case duplicate、symlink、reparse、zip bomb |
| 表格不执行 | 宏/公式/外链不运行，缓存 provenance 正确 | VBA、DDE、external refresh、uncached formula |
| Renderer 隔离 | sandbox/contextIsolation/no Node/narrow preload | HTML/script/data URL/任意 IPC 注入 |
| 日志 allowlist | 14d/100MB 轮换且无禁止字段 | prompt/path/filename/column/value/secret/stack path 注入 |
| Analytics opt-in | 默认零事件、schema 可见、local_only 强停 | free text/unknown event/opt-out/30d retention |
| DiagnosticBundle | 逐文件与 exact JSON 预览，主动发送，30d 删除 | project DB/preview/prompt/path/secret 注入 |
| Migration crash safety | 每阶段 crash 后原项目仍可打开且无半迁移 | backup/step/validation/switch 各点中断 |
| Migration semantic parity | 科研与视觉 semantic hashes 不变 | 尝试换算法/单位/fit/style/renderer |
| 新/旧兼容 | future schema 明确拒绝；旧组件不替换 | unknown extra/version、remove old renderer |
| Backup/restore | 每日≤1、保留3、恢复不覆盖当前且有 record | backup disk full、restore hash/ref failure |

本文件定义未来实现与 release gate；当前文档提交不表示日志、迁移、备份或安全测试代码已经实现。
