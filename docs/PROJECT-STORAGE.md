# PlotAgent 项目存储、项目包与数据导入

> 状态：第一轮存储与导入基线已确认  
> 日期：2026-08-05  
> 适用范围：本机事务工作区、SQLite、内容寻址对象存储、`.plotproj`、数据导入、完全同构判断与单轮字段映射  
> 相关文档：[本地安全、诊断与 Beta Schema 兼容契约](./LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md)、[后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)、[领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)、[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)

## 1. 核心结论

- 运行态使用 `%LOCALAPPDATA%\PlotAgent` 下的本机事务工作区，不直接在 `.plotproj` 压缩包中运行。
- 全局 catalog 与每个项目的数据库、对象、缓存和临时文件严格分离。
- 项目数据库保存关系、版本和操作状态；大对象按 SHA-256 存入内容寻址对象存储。
- 原始数据不可变；派生数据、PlotSpec、AnalysisSpec 和版本关系可追溯；缓存可以删除并重建。
- `.plotproj` 是可搬运、可校验的项目快照，不是实时数据库，也不是持续自动保存目标。
- 数据导入先在临时区完成识别、解析和验证，最后才移动不可变对象并用单个 SQLite 事务注册。
- 完全同构判断分为自动结构候选和最终语义签名；用户只确认一次字段映射。
- SQLite WAL 只用于本机活动工作区，由 Python Core 单写入器管理。

## 2. 本机运行态布局

```text
%LOCALAPPDATA%\PlotAgent\
├─ catalog.sqlite3
└─ projects\
   └─ <project-uuid>\
      ├─ project.sqlite3
      ├─ objects\
      │  └─ sha256\
      │     └─ <content-addressed objects>
      ├─ cache\
      ├─ tmp\
      └─ project.lock
```

### 2.1 全局 catalog

`catalog.sqlite3` 只保存：

- 项目 UUID 与本机项目目录。
- 最近打开项目和最后访问时间。
- 应用级设置。

catalog 不保存项目对话、PlotSpec、数据集、版本 DAG、原始数据或模型凭据。模型凭据继续保存在 Windows Credential Manager。

### 2.2 项目数据库

每个项目的 `project.sqlite3` 保存：

- 项目设置、对话和结构化操作记录。
- 资源对象、对象关系和引用。
- DatasetVersion、AnalysisSpec/Result、PlotSpec、BatchSpec、FigureSpec 与 ExportSpec 元数据。
- 图表、数据和组合图的不可变版本 DAG。
- 任务、事务、警告、部分失败和导出记录。
- 内容对象的哈希、类型、大小、来源和引用计数。

数据库不内联保存大型原始文件、Parquet 表或导出文件字节。

### 2.3 内容寻址对象存储

`objects/sha256` 保存按完整内容 SHA-256 寻址的大对象，包括：

- 导入的原始文件只读副本。
- 解析后的 Arrow/Parquet 数据和派生数值表。
- 需要持久化的 PlotSpec、AnalysisResult 或其他较大结构化产物。
- 正式导出产物或其项目内不可变副本。

对象先在 `tmp` 完整写入并计算哈希，校验成功后再移动到最终地址。同一项目内内容相同的对象复用同一哈希对象，不跨项目共享可变状态。

### 2.4 缓存、临时区与锁

- `cache` 保存可再生预览、渲染缓存和索引；可以由用户清除，不进入 `.plotproj`。
- `tmp` 保存尚未提交的导入、解析、快照和导出中间产物；失败或恢复检查后清理。
- `project.lock` 防止同一活动工作区被两个写入进程同时打开。
- 原始对象和已注册版本不是缓存，不得因空间回收而自动删除。

## 3. `.plotproj` 的语义

### 3.1 快照包而非实时数据库

`.plotproj` 是某个完整事务点的可搬运项目快照。应用运行时持续自动保存到本机项目工作区，不在每次操作后重写 `.plotproj`。

打开 `.plotproj` 时：

1. 校验包结构、manifest 和 checksums。
2. 将内容导入 `%LOCALAPPDATA%\PlotAgent\projects\<uuid>` 的本机工作副本。
3. 后续修改只写入该工作副本，不修改原始 `.plotproj` 文件。
4. 同一包再次打开时，默认回到 catalog 中已有的工作副本。
5. 用户明确选择“作为新副本导入”时，创建新的项目 UUID 和独立工作区。

内部自动保存与“导出项目副本”是两个不同动作：前者提交本机事务，后者创建新的 `.plotproj` 快照。

### 3.2 包结构

```text
project.plotproj
├─ manifest.json
├─ project.sqlite3
├─ objects\
│  └─ sha256\
│     └─ <included objects>
└─ checksums.sha256
```

- `manifest.json` 记录包格式版本、项目标识、快照事务、包类型、对象清单、能力限制和创建引擎版本。
- `project.sqlite3` 是一致的只读快照，不是活动 WAL 数据库的文件级复制。
- `objects/sha256` 只包含该包模式要求且被快照引用的对象。
- `checksums.sha256` 用于导入前完整性校验。
- `cache`、`tmp`、`project.lock`、WAL 和共享内存文件不进入包。

### 3.3 一致快照与原子生成

创建项目包时：

1. 记录要导出的完整事务版本。
2. 使用 SQLite Online Backup API 创建一致的 `project.sqlite3` 快照。
3. 根据包类型收集被该快照引用的不可变对象。
4. 生成 manifest 与 checksums。
5. 在临时目标中重新校验数据库、对象和哈希。
6. 全部通过后原子替换最终 `.plotproj`。

禁止直接复制正在使用 WAL 的活动数据库文件，也禁止把半成品包注册为成功导出。

## 4. 两类项目包

### 4.1 完整项目包

完整项目包包含：

- 原始文件副本。
- 派生数值数据。
- 对话、对象关系、版本 DAG、任务和操作历史。
- PlotSpec、AnalysisSpec/Result、图表、组合图和导出记录。

完整项目包可以在另一台兼容设备上恢复完整复现与重算能力。

### 4.2 结果项目包

结果项目包省略原始数据，但必须保留：

- 打开既有图表、继续可逆改图和重新导出所需的派生数值数据。
- PlotSpec、AnalysisResult、样式快照、发表规格和版本关系。
- 对话、任务与导出记录中仍属于项目快照的结构化元数据。

结果项目包的边界：

- 不能宣称为隐私安全包；派生数值、标签、统计结果和元数据仍可能包含敏感信息。
- 任何依赖已省略原始数据的重新解析、重新转换或重新分析操作都不可用。
- manifest 必须声明包类型、省略对象和不可用能力，界面打开后持续显示该限制。

## 5. 数据导入流水线

一次导入按以下顺序执行：

1. **文件授权。** Electron 文件选择器返回受控 ResourceRef，renderer 和模型不获得任意路径权限。
2. **临时复制与哈希。** 文件复制到项目 `tmp`，流式计算 SHA-256，不直接在源路径上解析或修改。
3. **结构识别。** 识别格式、编码、分隔符、工作表、表头、小数格式和缺失值表达。
4. **必要问题。** 只有编码、工作表、表头或解析规则存在必要歧义时才询问用户。
5. **完整分块解析。** 解析全部数据；预览样本不能代替正式解析和质量校验。
6. **Arrow/Parquet 转换。** 生成内部列式数据，保留逻辑类型、物理类型、精度与单位元数据。
7. **质量摘要与候选签名。** 计算行列数、缺失、非有限值、重复列名、字段结构和自动同构候选。
8. **不可变对象提交。** 将校验完成的原始副本和 Parquet 对象移动到 `objects/sha256`。
9. **SQLite 事务注册。** 在一个项目事务中注册 DatasetVersion、ImportRecipe、对象引用、摘要和来源。

任何步骤失败都不得把临时文件、半解析表、对象引用或 DatasetVersion 写成正式项目状态。

## 6. ImportRecipe 与 DatasetVersion

`ImportRecipe` 保存使导入可复现的解析配置，包括：

- 格式、编码、分隔符和小数规则。
- 工作表、表头行、数据范围和缺失值表达。
- 列名规范化结果、逻辑/物理类型与单位识别。
- 使用的解析器与 Schema 版本。

相同源内容使用不同 ImportRecipe 时生成新的 DatasetVersion，不覆盖既有版本。重新导入内容变化时同样生成新的 DatasetVersion；既有图表继续引用原数据版本。

## 7. 完全同构与单轮字段映射

### 7.1 自动结构候选

导入完成后，系统先根据字段集合、逻辑类型、单位和结构形成候选组。整数与浮点都按逻辑 `numeric` 参与候选分组，物理类型与精度作为审计信息保留。候选分组只是减少用户操作，不代表已经成为正式批次。

列名只允许：

- 清理首尾空格。
- 执行统一的 Unicode 规范化。

不做模糊匹配、同义词猜测、大小写折叠或按位置强配。规范化后出现重复列名时阻止导入，并要求用户修复来源或明确解析配置。

### 7.2 一次字段映射

系统根据规范化字段名、逻辑类型、单位和用户指令预填映射。用户只确认或调整这一个字段映射对象；不存在绘图前第二轮映射，也不允许为单个文件设置例外。

明确且无歧义的用户指令可以跳过映射确认界面，但仍必须生成同一个可审计映射对象。

### 7.3 最终语义签名

字段映射确认后生成最终语义签名。只有以下内容全部一致的数据才是完全同构：

- 规范化后的字段集合。
- 每个字段的逻辑类型。
- 单位。
- 字段语义与角色。
- 最终字段映射。

列顺序可以不同，不参与同构判定。整数与浮点可统一为逻辑 `numeric`，但必须保留原始物理类型、范围和精度，供精度校验、导出和审计使用。

最终语义签名不同的数据不能进入同一批次。用户必须拆分批次，或先明确创建标准化派生数据，再重新判断同构关系。

## 8. SQLite 运行约束

- SQLite WAL 只用于 `%LOCALAPPDATA%` 下的活动项目数据库。
- Python Core 是 `project.sqlite3` 的唯一写入器；renderer、Electron Main 和 Origin Worker 不直接写项目数据库。
- 使用固定、包含所需修复的 SQLite 构建：至少 SQLite 3.51.3，或带有官方修复回移且经过同等测试的版本。
- 活动数据库、WAL、项目锁与运行中项目工作区不得放在网络文件系统。
- `.plotproj` 不在网络共享中直接打开或持续写入；需要使用时先复制到本地，再导入为本机工作副本。
- 项目包中的 SQLite 快照不包含 WAL 状态；导入完成后由本机工作区按当前受控版本重新启用 WAL。

相关实现必须覆盖：单写入器、进程崩溃、幂等重试、项目包Online Backup、包校验、版本不兼容稳定拒绝和网络路径拒绝测试。

## 9. 安全导入与 Beta Schema 兼容

- 活动 workspace 只允许本机固定磁盘；外部 `.plotproj` 始终先进入当前用户 ACL 的随机 temp workspace。
- 解包前和流式解包中校验 manifest/hash、entry count、单文件/总 expanded size 与压缩比；拒绝 absolute/`..`/重复规范化路径、link/junction/reparse/special entry 和 archive bomb。
- Excel 宏/VBA/外链/公式不执行或刷新；只导入已有缓存公式值并记录 provenance，无缓存结果为 missing/NeedsInput。所有文本只作 data。
- 每任务 temp 独立并在 success/failure/cancel/startup recovery 清理；普通删除为 best effort，不承诺 secure erase。
- 不兼容 schema 默认返回 `SCHEMA_VERSION_UNSUPPORTED` 并保持原项目不变；第一轮不建设通用 N→N+1 migration framework。
- 确需升级时只为明确 source→target 版本对实现一次性迁移：用 SQLite Online Backup 创建一致输入，在新 temp workspace 验证对象/引用/hash/DAG/current pointer 与科学/视觉语义后原子切换。
- 第一轮无每日自动 Online Backup、最近三份保留、恢复分支或恢复 UI。用户主动导出的 `.plotproj` 是可搬运快照，仍按第4节使用 Online Backup 创建一致数据库快照。
- 完整边界、领域对象、稳定错误和故障注入见 [本地安全、诊断与 Beta Schema 兼容契约](./LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md)。
