# PlotAgent 产品需求文档

> 状态：专业能力范围完整，工程成熟度面向小规模邀请制 Beta
> 产品代号：PlotAgent  
> 日期：2026-08-05  
> 相关资料：[规格索引与小规模 Beta 设计基线](./SPEC-INDEX.md)、[实施拆分与里程碑计划](./IMPLEMENTATION-PLAN.md)、[已确认产品决策基线](./PRODUCT-DECISIONS.md)、[后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)、[Agent 上下文、模型供应商与数据出境契约](./AGENT-CONTEXT-AND-PROVIDERS.md)、[邀请、共享额度与最小 Beta 云控制面](./CLOUD-CONTROL-PLANE.md)、[本地安全、诊断与 Beta 兼容](./LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md)、[小规模 Beta 性能测试与发布门禁](./PERFORMANCE-TEST-RELEASE.md)、[领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)、[项目存储、项目包与数据导入](./PROJECT-STORAGE.md)、[受控数据准备、单位与来源追溯契约](./DATA-TRANSFORMS.md)、[任务运行时、取消和崩溃恢复](./TASK-RUNTIME.md)、[固定绘图计算与科学边界](./ANALYSIS-ENGINE.md)、[拟合能力分期边界](./FITTING-SYSTEM.md)、[渲染管线与跨 Renderer 一致性契约](./RENDERING-PIPELINE.md)、[原生 Origin OPJU 导出契约](./ORIGIN-EXPORT.md)、[科研图形库调研](./chart-library-research.md)、[产品战略](../PRODUCT.md)、[设计种子](../DESIGN.md)

## 1. 产品概述

PlotAgent 是面向通用科研用户的 Windows 桌面绘图软件。用户在类似 ChatGPT 的项目对话中导入数据，明确选择图形，设置或确认一次字段映射，由本地绘图引擎生成单图、批量图和组合图。用户可以继续用自然语言修改，并导出 PNG、SVG 和原生可编辑的 Origin `.opju`。

首版不试图取代 Excel、Origin 或完整统计软件。产品聚焦于把“数据到投稿图”的高频工作流变得更快、更清楚、更可追溯。

## 2. 用户与成功标准

### 2.1 核心用户

- 跨学科研究生、实验人员和科研团队。
- 熟悉表格和常见科研图，但不一定会编程。
- 既包含 Origin 熟练用户，也包含只使用 Excel 或图形界面的用户。
- 使用未发表数据，重视本地存储、复现和导出后的继续编辑。

### 2.2 首要成功标准

首版成功不是图形数量最大，而是用户愿意尝试并再次使用。

邀请制内测重点指标：

- 用户能在 5 分钟内生成第一张真实数据图。
- 用户完成一次自然语言改图。
- 用户完成一次多文件批量绘图。
- 用户成功导出并在 Origin 中继续编辑 `.opju`。
- 用户在一周内再次使用。
- 能定位导致用户放弃或转回 Origin、Excel、Python 的步骤。

首批内测 10 至 15 人；第二轮扩展至 30 至 50 人，覆盖至少五个学科。

## 3. 产品原则

1. **对话就是工作流。** 导入、映射、绘图、修改、组合和导出都留在连续任务上下文中。
2. **用户明确选择图形。** Agent 不主动推荐或替换图形类型。
3. **原始数据永远只读。** v1 只通过可追溯的受控 PreparationSpec 生成绘图用 Plot Data，不提供通用派生数据平台。
4. **一段对话可以产出多个批次。** 对话不是一张图的容器。
5. **批量先统一，再允许局部覆盖。** 样式统一，坐标默认按各图自动缩放。
6. **复杂度逐步展开。** 默认保持对话式，需要精确控制时才进入聚焦编辑。
7. **导出承诺必须真实。** `.opju` 必须是数据驱动、可继续编辑的 Origin 项目，不能用嵌入图片冒充。
8. **在线模型只规划，本地引擎执行。** 云端模型不能直接操作文件系统或运行任意代码。
9. **显式状态优于隐式记忆。** 作用对象、范围、字段映射、固定计算/预计算要求、数据版本和持久偏好必须可见。
10. **第一轮只做数值绘图。** 科研图像、地图数据与图片混合面板不进入首轮闭环。

## 4. 核心对象模型

```text
项目
├─ 原始数据与绘图用 PreparedDataset/Plot Data
├─ 发表规格与样式模板
├─ 对话
│  ├─ 绘图批次
│  │  ├─ 图表
│  │  │  └─ 图表版本
│  │  └─ 批次任务与导出记录
│  └─ 结构化操作记录
├─ 组合图
├─ 绘图流程模板
├─ 项目资源库与回收站
└─ 项目设置与显式偏好
```

### 4.1 项目

- 保存数据、对话、样式、发表规格、图表和导出记录。
- 默认把导入数据复制进项目，不依赖原文件路径。
- 记录文件哈希、原始路径、导入时间和解析方式。
- 可导出为单个 `.plotproj`，并选择是否包含原始数据。
- `.plotproj` 是项目快照；打开后导入本机工作副本，原包不被持续修改。
- 同一项目包默认回到已有工作副本，也可以明确“作为新副本导入”。
- 第一轮不提供“仅链接外部文件”模式。
- 相同内容只在同一项目内按哈希去重，不跨项目共享可变对象。
- 所有成功操作以原子事务自动保存；界面不提供传统保存按钮，只提供项目副本导出。

### 4.2 对话

- 一个项目可以有多段对话。
- 项目共享数据、样式、术语、单位和图表资产。
- 对话独立保存当前批次、映射、指令与版本历史。
- 新对话不自动继承其他对话全文，通过 `@数据集`、`@图表`、`@绘图批次` 明确引用。

### 4.3 绘图批次

- 同一图形类型与字段映射作用于一组结构同构的数据。
- “结构同构”要求字段集合、逻辑类型、单位、字段语义和最终映射一致；列顺序可以不同，整数与浮点统一为逻辑 `numeric`，不允许按文件设置映射例外。
- 不同结构的数据拆分为独立候选批次；v1 不用通用变换标准化异构输入。
- 一个批次生成一张或多张图。
- 单个文件失败不终止整个批次。
- 一条批次命令作为一个事务记录；撤销时撤销全部成功修改，失败项保持未修改。

### 4.4 图表版本

- 每次成功修改创建可恢复版本。
- 支持撤销、重做、比较和命名检查点。
- 底层版本结构允许分支，界面只展示简洁时间线。
- 从旧版本继续修改时创建新分支，第一轮不提供分支合并。
- 组合图引用具体图表版本，源图更新时只提示，不自动替换。

### 4.5 SourceDataset 与绘图数据版本

- 源文件重新导入且内容变化时创建新的数据集版本。
- ImportRecipe 记录格式、编码、工作表、表头、缺失值与解析版本；解析配置变化同样创建新的数据集版本。
- 既有图表继续绑定原数据版本，不因重新导入而静默变化。
- 用户明确重新运行后才创建绑定新数据的图表版本。

### 4.6 项目资源与偏好

- 项目资源库包含原始数据、PreparedDataset/Plot Data、批次、图表、组合图、模板和导出记录；Plot Data 明确标示为绘图复现产物。
- 支持搜索、重命名、版本、血缘、引用对话、归档和删除保护。
- 删除进入项目回收站，回收站不自动清空；永久删除由用户手动执行。
- 被其他对象引用的资源禁止直接删除，必须先展示并解除依赖。
- 只有用户明确选择“保存到项目”或“保存为全局设置”时才持久化偏好，不使用隐藏记忆。

## 5. 核心用户流程

### 5.1 首次使用

1. 应用无需账号、邀请码或联网即可进入主窗口，不使用多页向导或强制教学弹窗。
2. 软件检查本地存储空间，只对 Origin 做轻量可用性检测，不阻塞 PNG/SVG 绘图；云状态不在启动关键路径。
3. 用户首次需要内置 Agent 时再输入邀请码兑换设备令牌；也可选择自定义 provider，任何服务选择都不阻止本地工作入口。
4. 启动空状态提供三个入口：主按钮“用示例项目试用”、次按钮“导入自己的数据”、文字入口“打开已有 `.plotproj`”。
5. 打开示例项目时创建本地副本；示例使用合成数值数据，可离线修改，不改变内置模板。
6. 示例项目包含时间序列、分组实验、材料连续谱与 2×2 数值组合图三个对话，示例指令明确指定图形类型。
7. 用户导入真实数据时自动创建项目，名称由文件名生成，可随后修改。
8. 系统展示数据摘要，用户明确选择图形并确认一次字段映射。
9. 首张图成功后，再按上下文介绍批量、模板和 `.opju` 导出。

### 5.2 数据导入与批量绘图

1. 用户导入单文件、多个文件、文件夹或 ZIP。
2. 系统先确定数据位置与结构：Excel 的 sheet/region/header，或 TXT/CSV 的 encoding/delimiter/InstrumentMetadata/DataBlock/postamble/block/sweep/channel。
3. 存在多个合理解释时只问一个最小问题；超出清单时可操作拒绝。系统随后按字段、类型、单位和结构形成候选组。
4. 用户从图形库选择类型，或在指令中明确指定图形。
5. 系统根据列名、类型、单位和结构预填字段映射。
6. 用户只确认或调整一次，映射应用到整个批次。
7. 明确指令且无歧义时可跳过映射确认。
8. 结构确认回答“数据在哪里”，FieldMapping 回答“字段在图中是什么”，因此不是第二轮字段映射；不允许单文件例外。
9. 映射结果进入最终语义签名；只有字段集合、逻辑类型、单位、语义和最终映射全部一致时才组成正式批次。
10. 异构数据拆为其他候选批次；v1 不提供通用转换把它们标准化后重新入批。
11. 系统生成图集，样式统一，坐标按每张图自动缩放；统一坐标范围只能由用户明确开启。

导入在临时区完成授权复制、哈希、结构识别、最多一个必要追问、完整分块解析、Arrow/Parquet 转换、来源坐标和质量摘要；只有全部校验通过后才移动不可变对象并用单个 SQLite 事务注册 SourceDataset。

### 5.3 自然语言改图

- 输入框始终显示当前作用对象和范围。
- 作用范围包括当前图、选中图和整个批次。
- 用户可点击系列、坐标轴、图例、结构化标注和组合图面板，选中对象显示为目标标签。
- 图形子对象使用稳定语义 ID；支持多选，不依赖屏幕坐标解释后续指令。
- 对话中只有一个合理目标时自动绑定；存在歧义时必须追问。
- 可逆样式修改直接执行，并显示摘要和撤销。
- 受控准备、固定绘图计算和字段变化显示规格、参数与影响范围；用户预计算曲线只显示来源和字段，不伪装为本应用拟合。
- 用户可通过 `@` 引用其他对话中的数据、图表和批次。

### 5.4 聚焦编辑

- 点击图表进入全窗口聚焦编辑。
- 中央为大画布，顶部提供撤销、重做、版本比较和导出。
- 精确参数面板按需打开，不常驻主对话。
- 批量任务在底部显示缩略图条，支持多选修改。
- 首版允许直接拖动图例和结构化标注。

### 5.5 组合图

第一轮提供：

- 1×2、2×1、2×2 等固定布局。
- A/B/C/D 面板编号。
- 公共图例。
- 仅组合数值数据生成的图表，不接收图片面板。
- 组合图绑定具体源图版本，源图更新后只提示；只有用户确认才替换引用。

第二轮提供：

- 不等宽、跨行跨列和自由布局。
- 局部放大图与嵌套面板。
- 共享坐标轴和更精确的对齐控制。
- 数值图表与科研图像的混合面板。
- 源图版本更新与布局重新校验。

组合图布局修改不反向修改源图。

## 6. 信息架构与界面

### 6.1 主窗口

- 左侧顶部：新建对话、搜索。
- 左侧主体：项目列表；展开项目后显示对话。
- 左侧底部：任务中心、模型设置、Origin 状态、应用设置。
- 主区顶部：项目名称、发表规格、后台任务状态。
- 主区中间：连续对话流，嵌入数据集、映射、批次、图表、版本和导出结果。
- 主区底部：文件导入、图形库、`@` 引用、目标范围和自然语言输入。
- 不设置常驻右侧参数栏。
- 项目标题与 `@` 菜单可以打开项目资源库覆盖层，不增加常驻资源侧栏。
- `Ctrl+K` 搜索项目、对话和资源元数据，不搜索原始单元格值；归档资源默认隐藏。

### 6.2 图形库

- 用户可以随时从输入框旁打开图形库。
- 支持中英文名、别名、缩写、学科、数据形状、坐标系、固定计算/预计算要求和导出能力搜索。
- 每种图显示真实缩略图、适用数据、必需字段、可选参数、批量能力、组合能力和 Origin 等级。
- 上传数据后，不隐藏不兼容图形，只说明缺少字段、结构或“需要预计算字段”。
- 提供最近使用和收藏，不提供“猜你喜欢”。
- 用户必须主动选择，系统不能自动替换图形类型。
- 正式界面只展示已经通过准入验证的图形，不放置“即将推出”占位项。
- 图形能力通过签名、版本化的官方核心包与官方学科包交付；第一轮不开放第三方插件。

完整分类以 [科研图形库调研](./chart-library-research.md) 的 157 个稳定条目为长期上限框架：研究 taxonomy 为核心高频 25、扩展常用 34、学科专用 70、进阶分析 28；这不改变第一轮正式准入的 24 个核心层 + 7 个跨学科验证层，共 31 个纯数值数据图表。

### 6.3 Agent 回复

- 任务回复展示本地阶段与结构化结果对象，不展示内部推理、供应商传输细节或冗长控制台输出。
- 结果对象优先；正文只说明结果范围、必要警告和可执行下一步，详细参数折叠显示。
- 只在对象不明、导入结构/字段映射同等候选、误差语义或预计算输入缺失、需要扩大数据出境或本地校验缺少必要信息时追问；一次最多一张卡、卡内最多三个问题。
- 不生成论文式解释、图注、方法摘要或科研结论。

### 6.4 批量审阅

- 支持网格、列表和轮播，支持排序、筛选、异常标记和从本次导出排除。
- 可临时统一坐标范围，并临时叠加选中的同构曲线；临时比较不修改源图。
- 只有用户明确“保存为新图”时，临时叠加才创建新图表对象。

### 6.5 上下文帮助

- 帮助在图形库、字段映射、科研警告、导出和 Origin 状态附近按需出现，不建立教程市场。
- 内容包括数据结构要求、风险解释、Origin 能力等级、期刊官方来源、Origin 故障排查、术语、快捷键与合成示例。
- 帮助只解释规则和操作，不自动解释用户的科研结果。

## 7. 数据、单位与复现

### 7.1 原始数据与受控绘图准备

- 不提供任意单元格编辑。
- 原始数据只读。
- SourceDataset 保存 ImportRecipe、schema/UnitSpec、数据 hash、稳定 field/row id、质量摘要以及 sheet/block/line/cell 来源坐标。
- 本地 compiler 把一次 FieldMapping 编译为封闭 PreparationSpec，只允许字段选择、结构投影、完全同构纵向 concat、metadata label、plot order 与 plot mask。
- PreparedDataset/Plot Data 可持久化以复现，但不是可任意继续加工的新数据资源。
- v1 不提供 TransformPipeline、通用 derived-dataset workflow、filter/dedupe/join/unit conversion/arithmetic/log/zscore/baseline/normalize/category recode、单元格编辑、SQL/Python/UDF。
- Excel 多 sheet 默认独立批量；只有用户明确且 schema/类型/单位/语义一致时纵向 concat 并保留 `source_sheet`，绝不自动跨 sheet join。
- TXT/CSV 分离 InstrumentMetadata、DataBlock 与 postamble；多个 block/sweep/channel 默认独立批量，元数据只在用户明确用于标签/分组时投影常量列。
- 不静默删行、补值、去重、过滤异常、换算单位、科学计算或执行公式/宏/脚本；`0/False` 有效，NaN/Inf/missing 保留并报告。
- missing policy 只允许 `fail` 或 `exclude_with_report`，后者生成可审计 mask，SourceDataset 不变。
- 源文件内容改变后重新导入会创建新的数据集版本，不覆盖旧版本。
- 完全相同的数据在同一项目内按内容哈希去重，不跨项目共享对象。
- 同构批次使用完全相同 FieldMapping、PreparationSpec 与可选 PlotCalculationSpec；不允许逐文件例外，单项可部分失败。
- 完整边界见[受控数据准备、单位与来源追溯契约](./DATA-TRANSFORMS.md)。

### 7.2 单位与显示精度

- UnitSpec 保存 source text、canonical unit、dimensionality、physical/dimensionless/opaque kind 和 registry version。
- 从列名、单位行和 Excel 表头识别的单位只是建议，确认后的数据库 UnitSpec 才是权威；Parquet metadata 只镜像。
- 字段映射同时展示名称、数据类型和单位。
- 同一坐标轴出现不兼容单位时阻止执行。
- v1 不执行单位换算；用户需外部生成明确数值并重新导入。系统不得在 PreparationSpec、PlotSpec、renderer 或 Origin 中隐式换算。
- UnitSpec 用于同构、坐标兼容与审计；opaque 仅同名兼容。
- 数据精度与显示精度分离。
- 系统不根据数值大小擅自换算单位。

### 7.3 大数据

- 固定 PlotCalculation、范围和数值摘要使用完整数据。
- thumbnail 与 interactive 允许确定性视觉降采样，并显示完整点数、显示点数、方法和状态。
- formal PNG、SVG 和 `.opju` 第一轮一律使用完整 PreparedDataset、PlotCalculationResult 或用户预计算表；SVG 不静默抽稀或栅格化。
- 并发根据本机内存控制。
- 屏幕降采样必须明确标注完整点数与当前显示点数。
- 本地缓存键包含内容哈希、绘图规格、渲染器和主题版本；支持增量失效和用户清除。

### 7.4 自动保存与恢复

- 所有成功操作作为原子事务自动保存。
- 失败操作不污染当前版本。
- 异常退出后恢复到最后一个完整事务。
- 不提供传统“保存”按钮，只提供导出项目副本。
- 原始数据和命名版本不自动删除。
- `.plotproj` 导入为 `%LOCALAPPDATA%` 下的事务工作副本，不依赖原包路径；导出项目副本时可选择完整项目包或结果项目包。
- 不完整事务、临时导出文件和崩溃中间态不得成为当前版本。
- 第一轮不做每日自动 Backup、最近三份恢复集、恢复分支/UI 或通用 N→N+1 migration framework；可搬运备份由用户主动导出 `.plotproj`。
- Beta schema 不兼容时稳定拒绝并保持原项目不变。确需升级时只为明确 source→target 版本对实现一次性迁移：一致快照、新 temp workspace、完整验证、原子切换，失败/取消继续使用原项目。
- 一次性迁移不能改变图形、mapping、unit、analysis/fit、style 或 visual semantics；科研/渲染新版本必须由用户明确 adopt 并创建新对象。

### 7.5 项目存储与项目包

- 全局 catalog 只保存项目目录、最近打开和应用设置；每个项目使用独立 SQLite、SHA-256 对象存储、缓存、临时区和项目锁。
- 原始文件、Parquet 与导出等大对象按 SHA-256 保存；原始数据不可变，缓存可再生且不进入项目包。
- 完整项目包包含原始、派生和历史，可完整复现；结果项目包省略原始但保留改图与导出所需派生数值。
- 结果项目包不能宣称隐私安全，依赖原始数据的重算不可用。
- 项目包通过 SQLite Online Backup、manifest、checksums 和原子替换生成，禁止复制活动 WAL 数据库。
- SQLite WAL 仅用于本机活动工作区，由 Python Core 单写入器管理；活动数据库和项目包不放在网络文件系统。
- 活动 workspace 只允许本机固定磁盘；`.plotproj` 始终先在随机隔离 temp 中验证 archive path/link/size/hash 后导入本机副本。
- 第一轮不加密项目；`.plotproj`、Parquet、OPJU 和结果包都可能含敏感科研数据，依赖 Windows account ACL，并建议敏感环境启用 BitLocker。
- 详细约束见 [项目存储、项目包与数据导入](./PROJECT-STORAGE.md)。

## 8. 样式、发表规格与标注

### 8.1 样式继承

1. 项目模板：发表规格、默认字体、基础配色和画布尺寸。
2. 批次样式：图形类型、线型、标记、图例和布局规则。
3. 图表覆盖：标题、标注、坐标范围和个别样式。

批次更新默认保留单图覆盖。只有用户明确要求强制统一时才清除相关覆盖。

图表创建时以物理尺寸为真值：

- canvas、margin、gutter 与 subplot 使用 mm；font、line 和 marker 使用 pt。
- PNG 用物理尺寸和 DPI 确定像素并写 DPI metadata；SVG 写物理 width/height 与 viewBox；Origin 使用相同 page 尺寸。
- 第一轮正式渲染只使用 sRGB。
- 聚焦编辑的缩放只影响查看，不改变字体、线宽或导出尺寸。
- 默认画布不添加大标题；批量来源名称显示在画布外的审阅界面。
- 坐标轴标题默认由变量名与单位组成。

### 8.2 发表规格

- 项目可选择通用单栏、双栏、通栏、演示或自定义尺寸。
- 用户明确选择期刊或刊群，Agent 不推断投稿目标。
- 导出检查尺寸、DPI、字体、线宽、色彩、矢量保真和组合图标注。
- 规格带版本与来源日期。
- 第一轮优先 Nature、JACS、IEEE Journals、Physical Review、PLOS Biology、AIP Journals 和 Elsevier Default。
- 规格更新必须签名和版本化，项目固定已使用的规格快照。
- 规格变更创建图表新版本，不静默改写既有版本。
- 项目同时固定渲染器、图形包和主题版本；迁移前提供预览。

### 8.3 结构化标注

- 文本、箭头、直线、矩形、高亮区间。
- 水平或垂直参考线与参考区域。
- 峰值标签、显著性括号和面板编号。
- 标注可绑定数据坐标或画布坐标。
- 图例和结构化标注支持直接拖动。
- ROI、通道和比例尺等图像专用标注不进入第一轮。
- Agent 不主动计算或添加显著性结果。

### 8.4 坐标与配色

- 第一轮 axis 只支持 linear、log10、datetime 和 categorical；不支持 log2、ln、symlog、probability 或 probit。
- autoscale 使用完整可见 Prepared/Plot Data、误差、区间与用户预计算 curve；bar/stack/area 包含零，line/scatter/distribution 不强制零。
- 不静默排除离群值；NaN/Inf 不参与范围但记录计数。图例和标注不扩大范围，reference 只有显式 `affect_range` 才参与。
- 连续轴在变换空间加 5% padding，类别轴首尾各半 slot，zero-span 使用版本化规则；log 可见数据含非正值时阻止。
- lower/upper bound 可分别 auto/fixed，reverse 必须显式。批次 unified scale 先 union 未 padding 候选再只 padding 一次。
- exact tick values/labels/exponent/precision 由版本化 nice-number algorithm 产生；碰撞消减确定性。v1 不执行单位前缀换算，scientific exponent 只改变显示格式。
- 批次坐标默认按图独立缩放，跨图统一范围只在用户明确开启时生效。
- 调色板区分类别、连续、发散、循环和灰度，不默认使用 jet。
- 类别到颜色的映射在项目内保持稳定，类别缺失不导致其余颜色重新分配。
- 提供色盲与灰度预览，重要差异不能只依靠颜色表达。

### 8.5 图表文字

- SafeRichText AST 只支持 plain/newline/sub/sup/bold/italic、Unicode Greek/常用符号和有限 fraction；不接受任意 LaTeX、HTML 或 script。
- 默认 font stack 为 Arial → Microsoft YaHei → DejaVu Sans；resolver 固定并验证实际字体与 file hash。
- SVG 默认 text-to-path；可选 editable text 并显示字体可移植性 warning。OPJU 中的图表文字保持原生可编辑。
- 完整坐标、文本、物理尺寸与跨 renderer 契约见 [渲染管线与跨 Renderer 一致性契约](./RENDERING-PIPELINE.md)。

## 9. Agent 行为与科研护栏

### 9.1 执行模型

- 模型没有数据处理、统计、绘图、导出、文件、数据库、Origin 或 URL 工具，也没有 tool loop；只返回一个结构化 AgentDecision 候选。
- 只有一个对话编排 Agent；一个会话可有多个 FigureTask/BatchTask，但每次运行只返回一个决策，并携带常驻 active target。
- ActionPlan 候选必须通过本地 Schema、对象版本、capability、permission 与科研业务校验，之后才由本地 Executor 映射到领域服务。
- 模型不生成或执行任意 Python、LabTalk、SQL、命令行或脚本。
- 模型只表达业务意图，不输出 pandas/Python/Matplotlib/Origin、文件/SQL、内部表 ID 或处理步骤；PreparationSpec 由本地 compiler 生成。
- 首版不支持自定义 Python 节点。

### 9.2 固定计算与预计算科学结果

- v1 只执行九类封闭 PlotCalculationSpec：HistogramBinning、TukeyBox、ViolinKDE、DensityKDE、ECDF、SummaryError、PercentStack、MatrixProjection、ConfusionCount。
- 固定默认为 FD/Sturges/常量单箱、线性分位数+1.5 IQR、Gaussian/Scott/256 KDE、右连续 ECDF、非负百分比堆积、唯一 XY、三种 confusion normalization 和固定 jitter seed。
- SummaryError 只允许 mean±SD、mean±SEM、mean±95% t CI、median+IQR、median+range 或直接中心/边界/对称误差；语义缺失返回 NeedsInput。
- PlotCalculationSpec 不允许新 kind、任意表达式、自由串联或发布为通用数据集；模型不能选择/编排。参数、算法版本、完整数据输入、mask、计数和 hashes 持久化。
- K05 提供 curve/lower/upper；K21 提供矩阵；K22 提供规则 grid；S01 提供 step/CI/风险人数；S05 提供曲线/参数；S21 提供 effect/lower/upper/weight。
- S25 不做 baseline/平滑/归一化，S31 不做背景/寻峰/拟合，S34 不做等效电路拟合。图形仍显示，但详情页与执行前明确“需要预计算字段”。
- AnalysisSpec/Result、FitSpec/Result、回归/相关/显著性/统计检验/KM/4PL/5PL/平滑/基线/归一化全部后移，不进入 v1 实现和门禁。
- Log axis v1 仅 Log10，非正值阻断；missing policy 只允许 `fail`/`exclude_with_report`，原始数据不变。
- Matplotlib、SVG 与 Origin 消费同一 PlotCalculationResult 或用户预计算 Plot Data，不各自重算。完整契约见[固定绘图计算与科学边界](./ANALYSIS-ENGINE.md)和[拟合能力分期边界](./FITTING-SYSTEM.md)。

### 9.3 三级校验

- 阻止执行：数学上不可计算或数据结构不满足要求。
- 警告后继续：样本量、误差定义、预计算输入来源或固定计算排除情况存在风险。
- 提示信息：图形可能造成误读，例如截断柱状图坐标或任意双 Y 轴。

非阻断情况下用户可以继续，决定写入操作记录与 `.opju` 批次摘要。

### 9.4 模型数据边界

- 本地 ContextBuilder 从权威对象与 ConversationState 构建版本化 ContextEnvelope；在线模型只返回业务意图 AgentDecision，本地引擎负责导入、准备、固定计算、绘图、文件和 Origin 操作。
- 每个 provider 首次处理项目内容前取得一次明确同意。默认只发送指令、相关字段元数据、统计摘要和确定性小样本；小样本硬上限为 20 行、12 个字段和 200 个 scalar。
- 默认不发送原始文件、工作区路径、SQLite、OPJU、完整表、完整项目或完整对话。超过 200 列时先在本地按名称/类型/单位筛选相关字段，不发送全量 schema。
- 需要更多数据时只能返回 NeedsInput；界面展示 SourceDataset/PreparedDataset、字段、规模和用途。授权只允许本次或本对话同类请求，可撤销且不提供永久全局放行。
- 离线时手动选图、字段映射、参数编辑、重绘和导出继续可用，只有自然语言 Agent 不可用。
- 模型不使用供应商托管 Conversation 或 `previous_response_id`；官方 OpenAI adapter 固定 `store:false`。列名、单元格和其中 URL 均按不可信 data 处理，不解释为指令或抓取链接。
- 完整 ContextEnvelope、DataDisclosure、provider 能力级别、凭据、审计和保留说明见 [Agent 上下文、模型供应商与数据出境契约](./AGENT-CONTEXT-AND-PROVIDERS.md)。

## 10. 绘图与导出契约

### 10.1 正式图形准入

- 正式图形必须通过 PNG、SVG 和 `.opju` 三种导出测试。
- `.opju` 重新打开后，数据、图层、轴、图例和标注仍可编辑。
- 软件内预览与 Origin 要求视觉等价，不承诺逐像素一致。
- 跨 renderer 要求 semantic parity；canvas ±0.2 mm、subplot ±1 mm、font/line ±0.1 pt、marker ±0.25 pt、RGB 精确、alpha ±0.01、range/tick 按 `1e-10 × max(1, abs(value))` 校验。
- 无法映射为 Origin 原生对象时，必须提前提示，不能静默嵌入图片。
- 尚未通过完整测试的图形只进入实验性目录，不进入正式内测图形库。

Origin 能力分级：

- O1：full native semantic parity，数据 linked，graph/layer/plot、axis/ticks、legend/annotation/page 原生可编辑。
- O2：数据仍 linked 且对象原生可编辑，但有预先声明的非关键视觉差异。
- O3：visual embedded/unlinked；O0：unavailable。
- 第一轮 31 项正式图形全部必须达到 O1 才显示 OPJU；O2 只为未来高级图形保留并需执行前披露，O3/O0 不生成第一轮正式 OPJU。

### 10.2 `.opju` 内容

- OPJU 是 target-scoped self-contained editable delivery，不是 `.plotproj`，不包含无关对话、数据、secret 或绝对路径。直接图为 Raw Data→Graph；固定计算图为 Raw Data + Plot Data(PlotCalculationResult)→Graph。
- current chart 为一个 graph 与所需数据；selected/batch 为多个 graph 并去重共享数据；Figure 为一个原生可编辑 multi-layer graph。
- Project Explorer 固定 Data/Analysis/Graphs/Metadata；Analysis 目录在 v1 保存固定 Plot Data 或用户预计算表，不表示 Origin/PlotAgent 分析链。
- 只包含实际绘制的 Raw Data、PreparedDataset、PlotCalculationResult/用户预计算字段；不复制未使用列。
- Graph 引用最终 Plot Data；修改 Plot Data 可更新图，修改 Raw Data 不承诺自动重新执行 PlotAgent 固定计算。v1 不生成 Origin Analysis Template、worksheet formula 或 LabTalk。
- Worksheet 保存 Long Name、Units、Comments 和 designations；matrix chart 可用 Matrixbook。
- Manifest 保存 PlotAgent↔Origin object map、全部 version/hash、chart/style/profile、adapter/template/originpro/Origin version、export time、capability 与 O2 known differences。
- 一个 OPJU 是原子产物；任一目标失败不生成最终文件。排除失败目标必须创建新的显式 ExportSpec。
- 不支持反向导入现有 `.opju`。

### 10.3 Origin 自动化隔离

- 每个 Beta build 只声明一个完成完整 O1 qualification 的 Origin exact version/build/bitness；其他版本全部返回 `VERSION_UNSUPPORTED`，不能用“2021+”、版本范围或 O2 降级替代。
- Preflight 检查安装版本精确命中该 build 声明，并检查 license/originpro/font/template/adapter/目录/锁；失败不启动实例。
- 不连接用户当前打开的 Origin，不调用 `op.attach()`；构建和验证各自从空白 dedicated managed instance 开始，不终止用户实例。
- OriginAdapter 只接收 typed OriginExportPlan，并只通过应用内固定的 `originpro`/Python 类型化映射构建对象；第一轮完全不执行 LabTalk，也不接受模型/数据/配置注入的 Python/script/property string。
- 签名 template 复制到任务临时目录，不读取或修改用户全局 template。
- 构建实例做 live structural validation，保存同目录临时文件后退出；新实例打开临时文件并重新枚举/读回数据对象、链接、轴、ticks、图例、page、style 与数值/missing 语义。
- 两阶段通过后才原子移动；成功或失败均清理临时资源和 PlotAgent 管理实例。
- 导出完成后只有用户明确点击才在 Origin 打开；外部编辑不回写 PlotAgent。
- ExportRecord 保存外部 path/hash/size/mtime 与 spec/plan hash；同路径覆盖前检测外部修改并要求确认或 Save As。
- 启动时只做轻量 Origin 检测；首次 OPJU 导出或设置中的自检才执行完整验证，并按该 build 唯一 exact version 缓存结果。
- 稳定错误包括 NOT_INSTALLED、VERSION_UNSUPPORTED、LICENSE_UNAVAILABLE、CAPABILITY_MISSING、TEMPLATE_OR_FONT_MISSING、START_FAILURE、BUILD_FAILURE、SAVE_FAILURE、REOPEN_FAILURE、VALIDATION_FAILURE、TARGET_LOCKED、EXTERNAL_MODIFIED 和 CANCELLED。
- 完整内容、安全、两阶段验证、原子性和恢复动作见 [原生 Origin OPJU 导出契约](./ORIGIN-EXPORT.md)。

### 10.4 文件导出

- 支持当前图、选中图、整个批次和组合图。
- 文件名模板支持来源、图形类型和版本。
- 默认不覆盖已有文件，自动追加版本号。
- PNG 支持尺寸、DPI 和透明背景，第一轮颜色固定为 sRGB；SVG 保留矢量对象，默认文字转路径，可选 editable text。
- PNG 校验 signature/pixel/DPI/content；SVG 校验 parse/viewBox/size、无 script/external refs 和预期 element count；OPJU 在新受控实例中重新打开读回对象。
- 每个正式 ExportSpec 固定 ResolvedRenderPlan hash，临时产物验证通过后才原子移动。
- 批量导出生成清单，记录来源、版本、参数与失败项。
- 正式导出仅提供 PNG、SVG 和 OPJU；不提供 PDF、EPS、EMF。
- 剪贴板 PNG/SVG 是快捷复制，不生成正式导出记录。
- Origin 不可用时只禁用 OPJU，不阻断 PNG、SVG、项目保存或其他本地功能。

## 11. 绘图流程模板

- 样式模板只保存视觉与发表规格。
- 绘图流程模板保存 FieldMapping、PreparationSpec、图形类型、固定计算参数和样式引用；不包含通用处理/分析/拟合步骤。
- 模板不包含原始数据或聊天记录。
- 可保存到项目或本机全局模板库。
- 使用模板前检查列结构并展示执行步骤。
- 第二轮内测开放流程模板。

## 12. 后台任务

- 模型规划使用 InteractionRun；本地导入、Preparation、PlotCalculation、绘图、渲染和导出使用 ExecutionTask。NeedsInput 结束当前 InteractionRun，不创建后台任务。
- ExecutionTask 状态为 `queued`、`preparing`、`running`、`committing`、`succeeded`、`cancelling`、`cancelled`、`failed`、`partially_succeeded` 或 `interrupted`。
- `committing` 短暂且不可取消；第一轮不提供暂停或继续。失败任务可由用户明确重跑，正式任务不自动重试。
- 控制与 SQLite 写入单通道执行；普通计算默认最多 2 个隔离进程，内存压力时降为 1；Origin 严格串行。
- 交互预览优先，同一图的新预览可替代尚未开始的旧预览；预览和缓存可以按固定输入自动重建。
- 取消先发送 cooperative token 并等待安全边界；宽限期后只终止隔离计算进程。Origin 无响应时只重建 PlotAgent 管理的实例，不强杀 Core。
- 每个任务固定输入版本和 expected version；冲突不静默覆盖。活跃任务引用阻止对象删除，输出使用 `(task_id, action_id, output_slot)` 幂等键。
- Electron监督Core心跳；任务预先持久化输入、计划、阶段、尝试和暂存目录，只在阶段边界写记录用于确认原子提交与清理temp。遗留任务标为interrupted，不续跑内部算法状态。
- 批量任务保留已完成结果并形成已取消或部分成功批次；PNG、SVG、OPJU 每个文件临时写入、验证并原子替换。
- 任务卡留在来源对话，项目标题显示全局后台任务数；进度使用实际单位，第一轮不发送 Windows 通知。
- 关闭应用时提供“等待完成”“取消并退出”“返回”；取消并退出仍须等待不可取消的 committing 阶段结束。
- 详细契约见 [任务运行时、取消与崩溃恢复](./TASK-RUNTIME.md)。

## 13. 数据格式

### 13.1 第一轮重点

- `.xlsx/.xls/.xlsm` 多工作表只读数据；多 sheet 默认独立批量，明确且完全同构时才纵向拼接并保留 `source_sheet`。
- 带仪器前导/尾部的 TXT；普通 CSV/TSV/DAT 复用同一文本解析路径。InstrumentMetadata/DataBlock/postamble 分离，多 block/sweep/channel 默认独立批量。
- 文件夹和 ZIP 批量导入。
- 分隔符、编码、表头、小数格式和缺失值识别。
- 存在多个合理 region/encoding/delimiter/header 时只问一个最小问题；超出已列举模式可操作拒绝。
- 所有第一轮输入均为数值或分类表格数据，不接收科研图像。
- Excel 宏、VBA、公式和外链不执行/刷新；公式只使用文件内已有缓存值并记录 provenance，无缓存结果为 missing/NeedsInput。CSV/worksheet text 永远按 data 处理。
- `.plotproj`/ZIP 拒绝 absolute/`..`/重复规范化路径、symlink/junction/reparse point、超 entry/file/expanded size 与 archive bomb；全部验证后才注册。

### 13.2 第二轮

- Parquet、Feather。
- NPY、NPZ、MAT。
- HDF5、NetCDF 与内部数据集选择器。
- TIFF、PNG、JPEG。
- GeoTIFF、GeoJSON。

图像与空间格式即使进入后续格式解析，也必须在科研图像或地图能力完成独立验证后才开放，不由格式支持自动推导产品能力。

首版不支持数据库连接、实时仪器数据流和厂商私有格式。

## 14. 桌面与服务架构

### 14.1 桌面端

- Windows 桌面软件。
- 采用单实例、单主窗口结构；第二次启动聚焦已有窗口，并转发 `.plotproj` 或数据文件参数。
- 不驻留系统托盘；关闭主窗口即退出应用。
- Electron + React + TypeScript 负责界面。
- Electron 主进程监管一个常驻 Python 3.12 Core，后者负责导入、受控准备、固定绘图计算、绘图和 Origin 自动化。
- Electron 与 Python 使用版本化 JSON-RPC over stdio，不开放本地 HTTP 端口；大型数据只传对象引用。
- 固定修复版 SQLite（至少 3.51.3 或官方修复回移版本）保存全局 catalog 与项目元数据；Python Core 是项目数据库唯一写入器。
- Python 引擎随安装包分发，用户无需单独安装 Python。

### 14.2 Agent 与绘图核心

- 第一轮采用单 Agent 有界规划，不使用多 Agent 或开放式自主循环。
- Provider 只返回 `ActionPlan | NeedsInput | Unsupported | NoChange` 四类 AgentDecision；ActionPlan 是本地校验前的候选，手动 UI 直接生成相同 ActionPlan 并复用本地执行链。
- 数学、安全、对象版本和产品硬规则由本地 validator 产生稳定阻断错误，不设置模型自报的 blocked 分支。
- 版本化 PlotSpec 与不可变引用是结构化真值，单一 resolver 生成带 hash 的 ResolvedRenderPlan；Matplotlib、PNG、SVG 和 Origin 不再各自解析坐标或默认样式。
- Matplotlib 是第一轮唯一正式预览、PNG 和 SVG adapter；Origin 由独立串行 Worker 从同一 ResolvedRenderPlan 重建原生对象。
- Python Core 按 Project、Import、Preparation、PlotCalculation、Plot、Batch、Composition、Export、Origin 和 Task 领域服务拆分；v1 无通用 Transform/Analysis/Fit 服务。
- 详细协议、数据结构、任务状态与实现顺序以 [后端与 Agent 架构](./BACKEND-ARCHITECTURE.md) 为准。
- PlotSpec、PlotPatch、BatchSpec、FigureSpec、ActionPlan 和 Schema 兼容规则以 [领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md) 为准。
- ContextEnvelope、ConversationState、AgentDecision、Provider、DataDisclosure 与 ModelRunAudit 以 [Agent 上下文、模型供应商与数据出境契约](./AGENT-CONTEXT-AND-PROVIDERS.md) 为准。

### 14.3 本地优先

- 项目、数据、图表和历史默认只保存在本机。
- 无网络时可导入、查看、手动选图、字段映射、参数编辑、重绘和重新导出。
- 自然语言 Agent 需要在线模型或用户配置的兼容模型服务。
- 用户可以配置 OpenAI-compatible base URL、model ID 与可选 API key；连接测试只发合成内容，凭据只存 Windows Credential Manager。
- 临时文件在隔离目录中创建并在任务结束后清理。
- 主窗口工作入口始终是“用示例项目试用 / 导入自己的数据 / 打开已有 `.plotproj`”。builtin invite、custom provider、local_only 是首次需要 Agent 或模型设置中的服务模式，不是启动入口。
- `NetworkMode=local_only` 禁止 credential/quota/model/config/update/analytics/diagnostics/远程 URL 全部出站；第一轮无 update-only 例外，localhost provider 仍属于 custom provider。模式切换不修改项目。
- local_only/断网时手动 UI 仍生成同一种 ActionPlan，导入、Preparation、PlotCalculation、31 图、批量/组合和 PNG/SVG/OPJU 全部本地可用。

### 14.4 最小云端控制面

- 邀请码对应 InviteGrant，不是账号；不采集邮箱、密码、个人资料或硬件指纹。同一有效邀请码可在不限数量设备重复兑换，额度归 InviteGrant 并由所有设备共享。
- 设备使用随机 installation ID 与长期 DeviceCredential；凭据只进 Windows Credential Manager，邀请码成功后不在本地保存。第一轮不实现短期 access token 或 refresh rotation。
- 模型请求使用唯一 `client_run_id`/Idempotency-Key。服务端对 InviteGrant 原子共享计数并保存幂等结果；超时、重试和服务重启不得重复调用或扣费。第一轮不实现 reserve/settle/reconcile；自定义 provider 不消耗 PlotAgent 额度。
- QuotaSnapshot 只展示 granted、consumed、remaining、period/reset（如适用）和 server time，不含 reserved。额度耗尽只禁用内置 Agent，手动能力和自定义 provider 不受影响。
- 云端仅提供邀请码兑换/设备凭据校验、内置模型 proxy、原子共享计数与 client_run 幂等记录；不提供 CloudConfig、自动更新、analytics、诊断上传、项目/图表/原始数据存储或远程科研计算/Origin。
- 应用启动不依赖控制面；只在内置 Agent 调用时校验 credential/quota。瞬时连接/5xx 最多重试两次并复用同一 client_run_id；4xx 与用户取消不重试，云失败不进入项目事务。
- InviteGrant 撤销或单设备封禁只能停止相应内置 Agent 权限，不能锁定本地项目或禁用本地导入、Preparation/PlotCalculation、绘图与导出。

内置 provider 通过设备令牌访问 PlotAgent proxy，平台供应商 key 只在服务端；用户配置自有兼容模型后桌面端直连。非 loopback endpoint 强制 HTTPS，TLS 校验不可关闭，禁止携带 Authorization 跨 origin redirect。

第一轮不做 CloudConfig、自动/应用内更新、后台下载或 `update_only`。用户人工取得安装包后，必须验证发布方签名、SHA-256 与 Windows code signature，再在退出应用后显式运行；更新资格不依赖邀请码。strict local_only 始终零出站。

完整协议、原子共享计数、幂等、日志、稳定错误与人工安装包验证见 [邀请、共享额度与最小 Beta 云控制面契约](./CLOUD-CONTROL-PLANE.md)。

### 14.5 隐私、安全与诊断

- 第一轮不实现或发送 usage analytics。DiagnosticBundle 只由用户主动生成、逐文件与 exact JSON 预览后保存到本地，用户自行发送。
- 本地 Bundle 不得包含原始数据、任何用户提示、文件名、路径、列名或列值。
- 第一轮不提供应用级项目加密，依赖 Windows 文件权限与用户选择的磁盘加密。
- 后续可评估密码加密 `.plotproj`；无账号体系，因此不提供云端密码找回。
- ModelRunAudit 只记录 provider/model/profile、版本、origin、request/run ID、耗时、usage、稳定错误、DataDisclosure 类别/计数和 context hash，不记录 secret、隐藏推理或完整 request/response body。
- 内置 proxy 只承诺自身不记录 payload，并准确展示底层供应商政策；OpenAI API 不宣传默认零保留，第三方兼容 provider 首次使用前必须确认其保留政策。
- 本地日志按 allowlist 保留 14 天或 100 MB，禁止 prompt、文件/路径、列名/值/摘要、secret 与模型 body；stack scrub 用户路径，第一轮不收集 memory dump。
- DiagnosticBundle 默认禁止项目 DB/数据/preview/OPJU/prompt/文件名/路径/列名/值/secret，只保存结构、统计 bucket 与 hash；用户为本次 bundle 明确同意并逐项预览后，可加入专门脱敏数据文件。第一轮没有上传、diagnostic ID 或云端保留期。
- 完整安全、日志、本地诊断与 Beta schema 兼容契约见 [本地安全、诊断与 Beta 兼容契约](./LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md)。

## 15. 语言、视觉与无障碍

- 产品界面仅提供简体中文。
- Agent 支持中文、英文和混合科研术语。
- 图题、坐标轴、图例和专业术语不自动翻译。
- 浅色界面，图表画布默认纯白。
- 产品界面配色与科研图表配色分离。
- WCAG 2.2 AA、键盘操作、清晰焦点、色盲友好和减少动态效果。
- 视觉规则以 [DESIGN.md](../DESIGN.md) 为准。

## 16. 内测分期

### 16.1 第一轮：核心闭环

- 首轮正式图形共 31 项，全部面向数值数据：K01–K22、K24–K25，加 S01 KM 生存曲线、S05 剂量反应曲线、S21 森林图、S25 连续谱图、S31 XRD 衍射图、S34 Nyquist 图和 S61 混淆矩阵。K23 科学图像面板与 S45 专题地图不进入第一轮。
- 三入口启动空状态与可复制的本地合成数据示例项目。
- 本地项目、多对话与自动保存。
- 项目资源库、归档、删除保护与项目回收站。
- 核心数据格式与数据摘要。
- 确定性结构导入、明确选图与一次字段语义映射。
- 九类固定 PlotCalculation 与需要预计算字段的图形路径；不含通用分析/拟合。
- 单图与多文件批量绘图。
- 批量网格、列表、轮播、异常标记与临时比较。
- 自然语言改图与作用对象。
- 版本、撤销、科研有效性校验。
- PNG、SVG、原生 `.opju`。
- 七个首批发表规格。
- 基础固定布局组合图。
- 用户配置的 OpenAI-compatible 模型端点。

### 16.2 第二轮：扩展能力

- 扩大正式图形库。
- 通用 AnalysisSpec/Result、FitSpec/Result、统计检验、拟合、平滑、基线和归一化需独立决策与验证后再进入后续阶段。
- 完整结构化标注。
- 高级组合图编辑。
- 扩展数据格式与大数据压力测试。
- 绘图流程模板。
- 科研图像与空间数据在完成独立产品验证后再评估开放。

## 17. 明确不做

- Agent 主动推荐或自动替换图形类型。
- 任意编辑表格单元格。
- 隐藏保存跨项目偏好或聊天记忆。
- 反向导入现有 `.opju` 图表。
- 首版账号、云同步和团队协作。
- 首版深色主题和多语言界面。
- 首版自定义 Python 执行。
- 第一轮通用 TransformPipeline/derived-dataset workflow、独立数据处理 Agent、AnalysisSpec/Result 与 FitSpec/Result。
- 首版数据库、实时仪器流和厂商私有格式。
- 第一轮科研图像导入、处理及数值图表与图片的混合组合。
- 第一轮 PDF、EPS、EMF 正式导出。
- 第一轮多主窗口、系统托盘驻留、版本分支合并和外部数据链接模式。
- 第三方图形插件、社区市场和教程市场。
- 图注、方法摘要和论文式科研写作。
- 对科研结果进行自动解释或生成结论。

## 18. 已知风险与阻塞

1. **Origin 环境。** 当前开发机器的 `originpro` Python 包可导入，但 Origin 安装或 COM 注册不完整，真实 `.opju` 生成和重新打开校验尚不可执行。
2. **图形覆盖与原生导出。** 调研目录有 157 个条目，但正式库只能逐个通过三格式导出契约后开放。
3. **期刊规则变化。** 发表规格必须版本化，并记录官方来源与更新时间。
4. **模型隐私。** 桌面端必须清楚展示实际发送的数据摘要，服务端不得记录科研数据正文。
5. **批量异构。** 第一轮只允许列、数据类型、单位、语义、mapping/preparation 完全同构的批次；异构数据必须拆分，不提供通用标准化变换。
6. **版本迁移。** 发表规格、渲染器、主题和图形包更新不得静默改变既有图，迁移预览与快照锁定必须可靠。
7. **任务恢复。** 批量部分失败、应用关闭和 Origin 中断必须保留完整事务边界，避免把半成品标记为成功版本。

## 19. 第一轮验收标准

- 新用户无需创建账号或填写项目表单，可从示例、导入数据或已有项目三个入口开始。
- 示例项目打开为本地副本，可离线完成数值绘图、修改和基础组合。
- 完全同构的多文件只需确认一次映射，异构文件不会混入同一批次。
- 一段对话可以生成多个批次和多个图表。
- 输入框始终显示当前作用对象和范围。
- 用户点击系列、坐标轴、图例、标注或面板后，目标标签和作用范围保持可见。
- 原始数据无法被任意改写；FieldMapping、PreparationSpec、PlotCalculationSpec/Result 与来源坐标可审计。
- Excel 多 sheet 与 TXT 多 block 默认独立，歧义只出现一个明确追问，超出清单可操作拒绝且没有静默解析。
- 需要分析的正式图形显示预计算字段要求；缺少输入时明确阻断，不隐藏图形或偷偷计算。
- 九类固定绘图计算在完整数据上可复现，参数变化创建新 FigureVersion，三种 renderer 消费同一结果。
- 批量任务部分失败时保留成功结果，并可重试失败项。
- 批量结果可用网格、列表和轮播审阅，可标记异常并从本次导出排除。
- 基础组合图可组合数值数据图表，并生成统一面板编号。
- 正式图形可导出 PNG、SVG 和原生 `.opju`。
- 普通数据图的 OPJU 达到 O1；受控 Origin 实例重新打开后核心对象仍可编辑。
- Origin 不可用时只禁用 `.opju`，不阻断其他功能。
- 重新打开 `.plotproj` 后，对话、数据、批次、图表版本和任务状态完整恢复。
- Core异常退出后遗留任务标为interrupted，项目权威状态必须不损坏且temp可清理；正式任务不会静默续跑/自动重试，用户从来源对话明确重试。
- 源数据重新导入、从旧版本继续、发表规格变化和外部 OPJU 修改均不会静默覆盖既有结果。
- 离线时除自然语言 Agent 外，导入、手动绘图、编辑和导出仍可用。
- 第一轮无 usage analytics；DiagnosticBundle 仅用户主动生成、逐项预览并保存到本地，默认只含结构/统计/hash；仅本次明确同意后可加入已预览的脱敏数据，仍不含 DB原件、提示、路径或 secret。
- 多设备共享 InviteGrant 额度，重装、超时、重试和服务重启不会获得新额度或重复扣费；控制面完全不可达时仍可启动、打开项目并使用全部本地手动能力。
- 第一轮无应用内更新或 update_only；strict local_only 抓包为零。人工取得的安装包在应用外验证发布签名、SHA-256 与 Windows code signature，异常即阻断。
- local_only 全进程抓包为零出站；断网仍可完成手动绘图、批量/组合和 PNG/SVG/OPJU。恶意 archive、宏/外链/公式、日志/诊断泄露与 Electron 注入均被阻止。
- 未知 schema 明确拒绝；已知 source→target 一次性迁移失败后原项目仍可打开且科学/视觉语义不变；旧组件缺失不静默换算法。任务崩溃不损坏已有权威状态，用户明确重试。

## 20. 小规模邀请制 Beta Qualification

- 每个 Beta build 只在一个 Windows 11 x64 reference profile 正式 qualification：当前为25H2/6C/16GB/NVMe/1920×1080，DPI 100%与150%；其他OS、minimum machine与DPI矩阵后续再做。
- 唯一正式规模为100k rows×20 columns、常规10 charts、单图≤100k plotted primitives、批量20 files/charts×每图10k、项目≤100 charts。超范围显示“超出Beta已验证范围”后best effort，资源不足稳定拒绝并建议外部准备较小数据或缩小批次，不暴露隐藏筛选/聚合。
- Thumbnail≤5k、interactive≤20k visible primitives；100k preview P95≤3s且range/PlotCalculation full data。声明规模内formal PNG/SVG/OPJU一律full data，不静默抽稀、栅格或换算法。
- 导入只qualification 100MB CSV≤12s、50MB XLSX≤30s；常规峰值内存≤2GB。100k PNG≤5s、SVG≤10s、single OPJU≤60s、20-chart OPJU≤180s。
- 31图每图minimal/representative/edge三fixture，formal PNG/formal SVG/O1 OPJU共279 paths；preview另测。每个build只声明一个Origin exact version，其OPJU 93条完整运行；其他版本`VERSION_UNSUPPORTED`。
- Data corruption、silent wrong science/semantic change、formal抽稀/算法替换、假O1、secret泄漏、声明图形失败、签名绕过、已知blocker/critical或靠retry变绿仍不可豁免。
- 每个Beta build固定manifest/source/test-runner/app/PlotSpec/model/prompt/Unicode/dependency/fixture hashes，提交约30个导入golden、279、单Origin 93、固定计算/预计算、reference performance、local security、quota幂等、签名安装包和known issues检查单；不要求商业级SBOM流程、多角色签署、长soak或全OS/云攻击矩阵。
- 首批10–15人的80%/60%/60%、至少一名batch与一名Origin继续编辑指标仍决定第二批go/no-go，使用经同意观察/访谈而非analytics。
- 完整预算、MatrixKey、检查单与后续工程边界见 [小规模邀请制 Beta 性能测试与发布门禁契约](./PERFORMANCE-TEST-RELEASE.md)。这些是未来Beta gate，当前文档不表示真实实现或测试已通过。
- 实施按W0–W10依赖与M0–M7 evidence里程碑执行，详见 [实施拆分与里程碑计划](./IMPLEMENTATION-PLAN.md)；需求权威、实现入口和future evidence映射见 [规格索引与小规模 Beta 设计基线](./SPEC-INDEX.md)。
