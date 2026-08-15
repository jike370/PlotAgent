# PlotAgent 已确认产品决策基线

> 状态：公开产品范围固定为34张单图；不支持组合图，K25与核密度图、Kaplan–Meier生存曲线、森林图已从目录、Agent、双后端和导出能力中删除，仅为旧项目保留 `CHART_TYPE_REMOVED` 墓碑；Pi 已接管通用 Agent 循环，PlotAgent Core 继续拥有领域校验与执行；当前提交尚待视觉和正式黑盒复测。

> 阅读规则：`PD-AF01`—`PD-AF08` 是当前最终决定，并明确取代此前关于35图、K25/组合图和自研通用 Agent runtime 的决定；其余章节保留为决策历史。冲突时以 AF 为准。
> 产品代号：PlotAgent  
> 基线日期：2026-08-07
> 适用关系：本文件记录全部已确认细节；[PRD](./PRD.md) 将其组织为可实施需求；[DESIGN](../DESIGN.md) 约束视觉与交互表达。三者发生冲突时，应先记录新的用户确认，再同时更新相关文件，不得由实现自行改变产品边界。

## A. 产品定位与范围

- **PD-A01 通用科研用户。** 面向跨学科研究生、实验人员和科研团队，不限定单一学科，也不要求用户会编程。
- **PD-A02 核心价值。** 用户上传一份或多份数据，明确选择图形，用自然语言描述绘图与修改需求，由 Agent 组织本地绘图任务。
- **PD-A03 首要成功标准。** 第一轮不以图形数量最大为目标，首要标准是用户愿意尝试并愿意再次使用。
- **PD-A04 桌面产品。** 产品为 Windows 桌面软件，不采用 Web 产品形态。
- **PD-A05 第一轮只做数值数据。** 第一轮聚焦数值数据绘图，不接收科研图像，不提供图像裁剪、通道、ROI、比例尺或其他图像处理能力。
- **PD-A06 正式导出。** 正式导出仅包括 PNG、SVG 和 Origin `.opju`。
- **PD-A07 产品代号。** 继续沿用 PlotAgent，不在当前阶段启动命名或品牌更换。
- **PD-A08 不生成科研写作。** 不提供图注、方法摘要、论文描述或科研结论生成能力。

## B. 产品结构与首次使用

- **PD-B01 对话驱动。** 整体结构接近 ChatGPT：左侧管理项目与对话，中央对话流驱动导入、映射、绘图、修改、组合和导出。
- **PD-B02 无常驻右栏。** 主对话不放置长期占用空间的参数栏；精确控制进入全窗口聚焦编辑，检查器按需出现。
- **PD-B03 一段对话可产生多个结果。** 对话不等于一张图，可以包含多个数据集、多个绘图批次和多个单图。
- **PD-B04 首次启动不用向导。** 应用无需账号、邀请码或联网即可进入主窗口启动空状态，不使用多页引导、账号表单或强制教学弹窗；内置模型服务在首次需要时单独兑换。
- **PD-B05 三个首次启动入口。** 启动空状态提供：主按钮“示例”、次按钮“导入”、文字入口“打开已有 `.plotproj`”。
- **PD-B06 示例项目。** 示例项目完全本地、使用合成数值数据、可离线运行；打开时创建可自由修改的本地副本，不改变内置模板。
- **PD-B07 示例内容。** 示例覆盖三个对话：时间序列、分组实验和材料连续谱；指令明确指定图形，不构成 Agent 推荐。
- **PD-B08 渐进教学。** 用户完成首张图后，再在上下文中介绍批量、模板和 `.opju`，不在首次启动时一次讲完。
- **PD-B09 上下文帮助。** 不建立教程或社区市场；帮助内容围绕图形所需数据结构、科研风险、Origin 能力、期刊官方来源、Origin 故障排查、术语、快捷键和合成示例，并在相关操作附近按需出现。
- **PD-B10 SEQ-10 视觉基线。** 首版采用参考 PLOT 前端的灰白黑产品配色、组件视觉语法和对话区尺寸：`920px` 内容轴、普通消息/提案默认 `780px`、用户消息 `640px` 或 `82%`、单图预览 `720px`、Composer `840px`，左侧项目/对话栏基准 `258px`。复杂 Dataset/Mapping/Batch/ChangeSet/ExportRecord 可在确有横向信息时扩展到完整内容轴。只吸收视觉与尺寸，不继承常驻模型配置、Debug、单图任务模型、浏览器下载或常驻右栏。
- **PD-B11 成熟产品原则。** 其余前端设计借鉴成熟生产力工具的通用理念而不拼贴外观：Windows 的标准控件/键盘/焦点，Notion 的同一对象多视图与显式引用，Linear 的筛选/多选/动作一致性，Figma 的专业模式上下文属性，Raycast 的搜索/命令/快捷键。最终选择以承载真实能力、降低认知负担、简洁清楚和 WCAG 2.2 AA 为准；未实现能力不以占位按钮出现。
- **PD-B12 左栏项目导航。** 左栏项目列表仅常驻显示项目名称，不展开对话；置顶、重命名、删除集中在悬停或聚焦后出现的三点菜单，项目摘要按需浮现。“新建项目”和 `Ctrl+N` 必须真实创建并激活本机项目，不能只清空当前界面。

## C. 项目、对话与资源

- **PD-C01 对象层级。** 项目包含数据、对话、批次、图表、图表版本、样式、发表规格、模板、任务和导出记录。
- **PD-C02 项目共享、对话隔离。** 同一项目的对话共享数据、样式、术语、单位和图表资产，但新对话不自动继承其他对话全文。
- **PD-C03 明确引用。** 当前通过可见项目、数据、图形和范围控件明确引用权威对象，不依赖隐式聊天记忆；`@数据集`、`@图表`、`@绘图批次` 后移。
- **PD-C04 项目包。** 项目保存为 `.plotproj`，导入数据默认复制进项目，不提供第一轮“仅链接外部文件”模式；导出项目副本时可选择是否包含原始数据。
- **PD-C05 来源记录。** 保存原始路径、内容哈希、导入时间、解析方式和数据版本来源。
- **PD-C06 项目内去重。** 完全相同内容通过哈希在同一项目内去重；不同项目彼此独立，不共享可变数据对象。
- **PD-C07 项目资源库。** 后续通过项目标题打开覆盖层/抽屉，不设置常驻资源侧栏；实现前不显示假入口。
- **PD-C08 资源分类。** 资源库包含原始数据、为绘图持久化的 PreparedDataset/Plot Data、绘图批次、图表、模板和导出记录；Plot Data 只用于复现，不作为通用派生数据工作区。
- **PD-C09 资源操作。** 支持搜索、重命名、查看版本与血缘、查看引用对话、归档和删除；归档资源默认隐藏。
- **PD-C10 全局搜索。** `Ctrl+K` 搜索项目、对话和资源元数据，不搜索原始单元格值；归档内容默认不进入结果。
- **PD-C11 删除保护。** 被 PreparedDataset、PlotCalculationResult、图表或批次引用的原始资源不得直接删除，必须先展示依赖并解除引用。
- **PD-C12 项目回收站。** 删除进入项目回收站，不自动清空；永久删除只能由用户手动触发并再次确认影响。
- **PD-C13 显式偏好。** 只有用户明确执行“保存到项目”或“保存为全局设置”时才持久化偏好，不存在隐藏的跨项目记忆。

## D. 数据、字段映射与批量

- **PD-D01 原始数据只读。** 不支持任意改单元格；原始数据永远不可被绘图操作改写。
- **PD-D02 受控准备。** v1 由本地程序把一次字段映射编译为封闭 PreparationSpec，并可持久化 PreparedDataset/Plot Data 以复现；不提供通用派生数据、TransformPipeline 或数据处理 Agent。
- **PD-D03 数据集版本。** 源文件重新导入且内容改变时创建新的数据集版本；已有图表继续绑定旧版本，重新运行时才生成新的图表版本。
- **PD-D04 两阶段单次语义映射。** 导入阶段只确认数据位置/结构；用户选图后字段映射才回答字段在图中的角色，并只确认或调整一次。
- **PD-D05 阶段职责。** 导入器回答“数据在哪里”，FieldMapping 回答“字段在图中是什么”，PlotSpec 回答“怎么画”；结构确认不是第二轮语义映射。
- **PD-D06 完全同构批量。** 同一批次必须具有相同字段集合、逻辑类型、单位、字段语义和最终映射；列顺序可以不同，整数与浮点统一为逻辑 `numeric`，第一轮不允许按文件设置映射例外。
- **PD-D07 异构拆分。** 不同结构的数据拆成独立候选批次；v1 不用通用变换标准化异构输入，也不允许逐文件准备例外。
- **PD-D08 批次产出。** 一个批次可以生成多张同类图；单项失败不取消成功项。
- **PD-D09 样式统一。** 批次默认统一发表规格、字体、颜色映射、线型、标记和布局语法。
- **PD-D10 坐标自动缩放。** 每张图默认依据自身数据范围缩放；只有用户明确选择“统一坐标范围”时才跨图统一。
- **PD-D11 样式继承。** 项目样式低于批次样式，批次样式低于图表覆盖；批次更新默认保留图表覆盖，强制统一必须由用户明确触发。
- **PD-D12 批次事务。** 一条批次命令是一个可审计事务；撤销时撤销全部成功修改，失败项保持未改状态。
- **PD-D13 第一轮格式。** 重点支持 `.xlsx/.xls/.xlsm` 多工作表只读数据与带仪器前导/尾部的 TXT；普通 CSV/TSV/DAT 复用确定性文本路径，并支持文件夹/ZIP 批量导入。
- **PD-D14 后续格式。** Parquet、Feather、NPY、NPZ、MAT、HDF5、NetCDF、TIFF、PNG、JPEG、GeoTIFF 和 GeoJSON 进入后续评估；格式解析完成不代表相关图像或地图产品能力自动开放。

## E. 图形库与批量

- **PD-E01 用户明确选图。** Agent 不主动推荐图形，不自动把用户选择替换成“更合适”的图形；只进行兼容性校验并询问缺失信息。
- **PD-E02 图形库入口。** 支持浏览、分类、筛选、搜索、收藏和最近使用，不提供“猜你喜欢”。
- **PD-E03 图形信息。** 每项显示真实缩略图、中英文名与别名、适用数据、字段要求、参数、学科、批量能力和 Origin 能力等级。
- **PD-E04 不隐藏不兼容项。** 导入数据后仍显示正式图形，只说明缺少的字段、结构或参数。
- **PD-E05 完整候选体系。** 图形调研目录的 157 个稳定条目是长期上限框架，不等于第一轮全部开放。
- **PD-E06 正式库准入。** 只有通过 PNG、SVG、OPJU 生成和重新打开验证的图形才进入正式库；未完成验证的能力不以“即将推出”占据正式界面。
- **PD-E07 官方图形包。** 采用官方核心包与官方学科包，包必须签名和版本化；第一轮不开放第三方插件或社区市场。
- **PD-E08 原始核心31项（历史）。** 早期曾以K01–K22、K24–K25及若干S图构成31项基础集合，并由PD-E25扩至43图；该范围已被PD-AF01的正式34图完整取代，不得用于当前目录、能力或发布计数。
- **PD-E09 Origin P1 候选代码面。** 在不引入双 Y 轴网格图的前提下曾增加 X01、X02、X03、X05、X07、X09、X11、X12、X13、X15、X16、X17、X18、X19、X23、X24、X35、X36、X37、X38、S07，形成 52 图内部代码面。代码存在不等于正式产品准入；视觉测试优先锚定 Origin 示例图与同一来源数据，A 级直接使用随附 OPJU，C 级只允许用 Origin 官方样例数据在 Origin 中重新生成参考图。
- **PD-E24 第一轮排除项。** K23 科学图像面板与 S45 专题地图不进入第一轮；专题地图需要空间几何、CRS 与 GeoJSON，待扩展数据范围后再评估。
- **PD-E10—E12 组合图（已撤销）。** 基础、高级和版本绑定设计均由 PD-AF02 撤销；当前没有隐藏能力或后续承诺。
- **PD-E13 结构单元。** 结构单元是可复用的视觉构件或图形关系，覆盖基础标记、分布、场/矩阵、坐标、布局、附着、视觉编码和受控科研标注；它不是图类型、数据导入/转换、固定计算或 renderer 代码，也不局限于折线、柱和误差棒示例。
- **PD-E14 图形配方。** 图形配方由版本化结构单元实例、语义端口与封闭关系组成；长期可扩展到偏移、分面和坐标归属，但第一阶段只接受 overlay/group/stack/attach/connect，baseline 通过强类型 attach 表达。每份完整组件图必须通过端口、关系、科学语义和 renderer 能力校验，两两兼容不等于任意多单元组合必然合法。
- **PD-E15 官方与用户类型同构。** 已迁移官方图类型是经过官方证据门禁的预装图形配方；未来用户自定义图类型使用同一 Schema、compiler、PlotSpec、ResolvedRenderPlan、Matplotlib 与 Origin 路径，不建立第二套用户 renderer 或脚本机制。第一阶段未迁移的29图明确保留既有路径，不伪装为配方。
- **PD-E16 单图与多面板边界。** 共享一个绘图区的折线+柱+误差、堆积+误差和双 Y 轴等属于一个 PlotSpec/图形配方；1×2、2×2 等多面板仍属于 FigureSpec，结构单元不能跨面板附着，单图配方可作为 Figure 面板来源。
- **PD-E17 自定义身份。** 样式、字段和坐标范围修改不改变图类型；增删构件、改变堆积/分组/轴拓扑或误差归属产生结构版本。官方图发生结构变化后显示为“基于官方图的自定义图”，即使与另一官方结构相同也只提示、不自动替换用户选择。
- **PD-E18 保存作用域。** 一次性结构只随当前 PlotSpec 版本保存；用户明确保存后才进入项目图形库或本机个人图形库。未来声明式图形配方包可导入/导出，但只含 Schema 允许的结构、语义槽位、默认样式、说明和合成缩略图，不含代码、真实数据、文件路径、对话或凭据。
- **PD-E19 配方内容边界。** 图形配方保存结构、语义槽位、关系、坐标策略、默认样式与版本，不保存 SourceDataset、FieldId、工作表、当前数据值、PlotCalculationResult 或数据驱动的自动坐标范围；用户明确固定的参考值/范围可作为模板常量，但保存时必须提示其跨数据影响。
- **PD-E20 配方版本与删除。** 图表固定引用创建时的配方版本；配方升级不静默改变已有图，显式升级先预览并创建新 PlotSpec 版本。缺少新版必需槽位时只补充冲突映射；删除配方默认仅从图形库隐藏，被历史图引用的版本继续保留，彻底删除前展示依赖。
- **PD-E21 后期搭建器。** M6 只完成内部可组合底座和基础泛化门禁，不开放用户搭建器。M6 后再提供全窗口搭建器，以“基于当前图”作为默认入口、空白搭建作为进阶入口，包含结构单元目录、实时预览、结构树、字段槽位以及项目/个人图形库；主对话仍无常驻右栏，也不提供自由矢量绘制。
- **PD-E22 自然语言结构编辑。** 后期 Agent 只使用添加/删除组件、设置封闭关系、设置轴归属、绑定字段和显式保存等领域 Action；模型不输出自由图层 JSON、renderer 代码或任意属性路径。目标明确时创建新图版本，误差归属、堆积范围或轴归属有歧义时只提出一张合并问题卡。
- **PD-E23 先基础后组合。** 组合底座编码前先通过现有基础图形的参数化泛化测试并修复确定性布局/坐标/误差问题；测试与组合架构不得同时变化。正式基础门禁通过后，第一阶段只迁移 PD-AB22 指定的14图并验证有限 compiler；其余29图迁移和用户搭建入口后移。
- **PD-E25 正式 43 图范围。** 第一轮正式图形库为原 31 图，加 X01、X02、X03、X05、X09、X13、X23、X24、X35、X36、X38、S07，共 43 图；这些图才可以由图形库或 Agent 创建并进入 PNG/SVG/OPJU 产品承诺。
- **PD-E26 九图移出覆盖。** X07、X11、X12、X15、X16、X17、X18、X19、X37 从正式图形库、Agent create capability 和导出承诺中隐藏；底层 adapter、fixture 与回归测试可保留，但不得以内部可调用或测试通过暗示产品支持，重新准入需补齐视觉规范、逐图编辑能力和发布证据。
- **PD-E27 合成视觉证据标识。** X24 与 S07 第一阶段允许以冻结合成数据完成 Matplotlib/Origin 并排视觉校准和 O1 结构验证，因此进入正式 43 图；其证据必须显式标记为“合成视觉验证”，不能写成 Origin 官方模板/同源样例证据。获得官方同源图—数据对后再升级证据等级，不静默替换既有基线。

## F. 改图、目标与版本

- **PD-F01 目标常驻。** 自然语言输入框常驻显示当前作用对象和范围，不能只依赖模型从指令中猜测。
- **PD-F02 可选对象。** 用户可点击系列、坐标轴、图例和标注；选中对象显示为输入框附近的目标标签。
- **PD-F03 多选与范围。** 支持多选，并明确区分当前图、选中图和整个批次。
- **PD-F04 稳定语义 ID。** 图形子对象使用稳定语义标识，不依赖屏幕坐标或图层顺序来解释后续指令。
- **PD-F05 歧义处理。** 只有一个合理目标时可自动绑定；存在多个合理目标时必须追问，不能静默选择。
- **PD-F06 版本结构。** 底层使用有向无环图保存版本与分支，界面只展示简洁时间线。
- **PD-F07 从旧版本继续。** 用户从旧版本继续修改时创建新分支；第一轮不提供分支合并。
- **PD-F08 自动保存。** 每次成功操作以原子事务自动保存，不提供传统“保存”按钮，只提供项目副本导出。
- **PD-F09 崩溃恢复。** 异常退出后恢复到最后一个完整事务；失败操作不得污染当前版本。

## G. 批量审阅与后台任务

- **PD-G01 批量审阅。** 第一阶段只提供真实缩略图网格、多选、状态筛选、异常标记和失败项局部重试；列表、轮播、自由排序和图像叠加比较后移。
- **PD-G02 临时统一。** 审阅时可以临时使用共同坐标范围，并把当前图已有强类型样式应用到选中图或批次；只作用于共同 capability，临时操作不改变未提交源图。
- **PD-G03 比较图后移。** 临时叠加比较及“保存为新图”不进入第一阶段，后续实现时必须显式创建新图表对象，不能修改源图。
- **PD-G04 导出排除。** 异常项可以标记并从本次导出中排除，排除状态必须可见且可撤销。
- **PD-G05 任务中心。** 导入、Preparation/PlotCalculation、绘图、重绘和导出作为本地 ExecutionTask，展示准备、运行、提交与结果阶段；模型 NeedsInput 不进入任务中心。
- **PD-G06 并发规则。** 普通绘图任务可并发；Origin 导出串行执行。
- **PD-G07 控制与失败。** 第一轮不提供任意阶段暂停或算法内部续跑；支持取消，并在 ProjectContext/expected versions 重新校验后由用户明确“继续未完成项”。批量部分失败保留成功结果，恢复不得重做成功项或静默从头执行整个计划。
- **PD-G08 中断恢复。** 应用关闭或任务中断时，已完成项保留，未完成项明确标记；恢复必须由用户手动触发，不静默自动继续。
- **PD-G09 关闭提示。** 关闭应用时如果仍有后台任务，提供“等待完成”“取消并退出”“返回”；取消后按安全边界与中断恢复规则保存状态。
- **PD-G10 日志。** 项目保存结构化任务日志，不把冗长控制台输出塞入对话。

## H. 科研绘图与固定计算规则

- **PD-H01 v1 科学边界。** v1 不执行通用统计检验、相关、拟合、平滑、基线、归一化、KM 或显著性计算；需要这些结果的图形接受用户提供的预计算字段。
- **PD-H02 三级校验。** 阻止用于不可计算或结构不满足；警告用于假设、样本量、误差语义或稳定性风险；提示用于可能误读但仍可执行的表达。
- **PD-H03 坐标缩放。** 柱状图和面积图默认包含零；折线、散点等按数据范围；不得静默排除离群值。
- **PD-H04 非有限值。** NaN、无穷和缺失值必须统计并呈现处理结果；对数轴遇到非正值时阻止执行。
- **PD-H05 坐标中断。** 断轴必须由用户明确选择并在图中清楚标识。
- **PD-H06 误差棒。** v1 只接受直接提供的中心/上下界/对称误差，或用户明确选择的五类固定 SummaryErrorSpec；误差语义缺失时返回 NeedsInput。
- **PD-H07 预计算拟合曲线。** 回归、剂量反应、生存等图只绘制用户提供的曲线、区间、参数或风险人数；PlotAgent 不拟合、不估计并明确标示输入来源。
- **PD-H08 禁止隐式处理。** 不静默删行、补值、去重、过滤异常、单位换算、平滑、基线、归一化、科学计算或执行公式/宏/脚本。
- **PD-H09 固定绘图计算。** 仅图形不可分割的封闭 PlotCalculationSpec 可执行；参数、算法版本、输入/输出 hash 与纳入/排除计数必须持久化，参数变化创建新 FigureVersion。
- **PD-H10 单位。** 从表头或单位行解析单位建议，不隐式换算；不兼容单位禁止共享坐标轴或进入同构批次，数据精度与显示精度分离。
- **PD-H11 大数据。** 范围、质量摘要和固定 PlotCalculation 使用完整数据；thumbnail/interactive 可做明确标识的确定性视觉降采样；第一轮 formal PNG/SVG/OPJU 始终使用完整数据。

## I. 样式、尺寸、标注与发表规格

- **PD-I01 物理尺寸为真值。** 图表创建时即确定物理尺寸与 DPI；用户可输入 mm 或 inch，Resolver 规范化为 mm，聚焦编辑缩放只影响查看。
- **PD-I02 无默认大标题。** 默认画布不添加图题；批量来源名称显示在画布外的审阅界面；坐标轴标题由变量名和单位组成。
- **PD-I03 配色语义。** 调色板区分类别、连续、发散、循环和灰度；不默认使用 jet；类别到颜色的映射在项目内稳定，类别缺失不触发重新分配。
- **PD-I04 可访问性预览。** 提供色盲和灰度预览，重要差异不能只依靠颜色表达。
- **PD-I05 富文本范围。** 图表文字只保存 SafeRichText AST：plain/newline/sub/sup/bold/italic、Unicode Greek/常用符号和有限 fraction；不接受任意 LaTeX、HTML 或 script。
- **PD-I06 SVG 文字。** SVG 默认 text-to-path；可选 editable text 并显示字体可移植性 warning；OPJU 文字保持原生可编辑。
- **PD-I07 结构化标注。** 第一轮包括文本、箭头、线、矩形、参考线、参考区间、峰标签、显著性括号和面板编号；图例和标注支持直接拖动。
- **PD-I08 图像标注排除。** ROI、通道、比例尺等图像专用标注不进入第一轮。
- **PD-I09 首批发表规格。** Nature、JACS、IEEE Journals、Physical Review、PLOS Biology、AIP Journals 和 Elsevier Default。
- **PD-I10 规格版本。** 发表规格带官方来源、日期、版本和签名；项目固定所用快照，不因在线更新静默改变既有图。
- **PD-I11 创建时应用规格。** 发表规格在图表创建时应用；更改规格创建新版本，不直接改写既有版本。
- **PD-I12 渲染可复现。** 项目固定渲染器、图形包和主题版本；迁移前提供预览，不静默重新渲染。
- **PD-I13 逐图编辑白名单。** 正式 43 图各自声明可编辑对象、操作和参数；图题、轴、图例、画布、线、符号、填充、误差、色板、双 Y、分面和偏移等能力只在 Matplotlib 与 Origin 均有稳定映射时开放。没有声明的请求返回 `Unsupported`，不暴露任意 Origin 属性、LabTalk、通用 JSON path 或自由 renderer 参数。
- **PD-I14 Origin 对齐符号。** 首批符号枚举固定为 `square`、`circle`、`triangle_up`、`triangle_down`、`diamond`、`plus`、`cross`、`triangle_left`、`triangle_right`、`hexagon`、`star`、`pentagon`；界面显示对应 Origin 英文名称，resolver 保存语义枚举，adapter 分别映射到 Origin 原生符号与 Matplotlib marker，不把 Origin 数字编号作为项目真值。
- **PD-I15 符号内部。** 闭合符号内部只允许 `solid`、`open`、`hollow`：`solid` 使用指定填充色，`open` 以解析后的背景色遮住穿过符号的线，`hollow` 无填充且允许下层线可见；`plus/cross` 是无内部的线符号，只接受规范化 `solid`，请求 `open/hollow` 返回不支持。字符、数字、球体、箭头、特殊 data marker、半填充和用户位图不进入第一轮。
- **PD-I16 Origin 命名色板。** 第一轮内置 16 个 Origin 对照配色资源（保留其 `Color List | Palette` 原生类型）：`ColorBlindSafe8`、`ColorBlindSafe15`、`BlueOrange`、`OrangeNavy`、`RedPurple`、`Viridis`、`Plasma`、`Inferno`、`Magma`、`GreyBlue`、`YellowBlue`、`YellowGreen`、`YellowPurple`、`GrayScale`、`Fire`、`Rainbow_Modified`。`GrayScale` 锚定 Origin 2024 SR1 随安装 `Palettes/GrayScale.PAL`，不是自造的 `OriginGrayScale` 名称。每个版本固定实际 8-bit sRGB colors/stops、来源名、资产/配色类型、顺序、source version/hash；Matplotlib 与产品目录以冻结 RGB 为真值。原生 Origin 导出只使用已限定安装目录中 source hash 完全一致的官方资产；缺失或修改时稳定失败，不读取用户文件或同名替代品。
- **PD-I17 类别编码上限。** 类别不超过 15 时使用冻结映射；超过 15 时不得循环复用颜色，而按证据支持的颜色+符号联合编码。联合编码仍不足或物理空间不可读时给出明确 warning/阻止，不静默产生无法区分的系列；普通 Rainbow/Jet 不作为默认，`Rainbow_Modified` 只能由用户明确选择。
- **PD-I18 双 Y 默认。** X23、X24、X35、X36 的左右轴默认均为中性、非加粗细线，不自动随系列着色；用户明确修改且当前图的编辑能力允许时，左右轴颜色才可分别映射到系列。轴颜色变化不得改变轴归属、range 或数据语义。

## J. Agent、模型与隐私

- **PD-J01 在线规划、本地执行。** 在线模型只返回一个结构化 AgentDecision 候选；导入、Preparation/PlotCalculation、绘图、文件与 Origin 操作由本地 Executor 在完整校验后调用领域服务，模型没有任何本地工具或 tool loop。
- **PD-J02 禁止任意代码与处理步骤。** 第一轮不允许模型运行或输出任意 Python/SQL/LabTalk，不提供自定义代码节点；模型也不输出表 ID、PreparationStep 或 PlotCalculation 编排，本地只接受冻结 Schema 的业务意图。
- **PD-J03 回复契约。** 对话显示本地任务阶段，但不展示内部推理或供应商传输细节；结果对象优先，正文只写结果范围、必要警告和后续动作，详细参数折叠显示。
- **PD-J04 追问原则。** 只在对象不明、字段映射同等候选、科研语义会实质改变结论、需要扩大出境或本地校验缺少必要信息时追问；一次最多一张卡、卡内最多三个问题。
- **PD-J05 不做解释写作。** Agent 不生成论文式解释、图注、方法摘要或结论。
- **PD-J06 默认模型负载。** 默认只发送指令、相关字段元数据、统计摘要和确定性小样本，硬上限为 20 行、12 个字段和 200 个 scalar；不发送原始文件、路径、SQLite、OPJU、完整表或完整对话。扩大范围必须通过 NeedsInput 展示用途与数量并取得作用域授权。
- **PD-J07 原始数据本地。** 云端控制面不保存原始数据、项目、图表或完整对话历史。
- **PD-J08 local_only。** `NetworkMode=local_only` 零远程出站；导入、手动 ActionPlan、字段映射、Preparation/PlotCalculation、绘图/批量和 PNG/SVG/OPJU 均本地可用。localhost 模型属于 custom provider，不属于 local_only。
- **PD-J09 自定义模型。** 用户可以配置 OpenAI-compatible base URL、model ID 与可选 API key；非 loopback 强制 HTTPS，连接测试只用合成内容，凭据只存 Windows Credential Manager。
- **PD-J10 本地诊断。** 第一轮不实现usage analytics；DiagnosticBundle每次由用户主动生成、逐文件与exact JSON预览后只保存本地。默认仅结构/统计/hash；本次单独同意才可含已预览脱敏数据，始终禁止DB原件、prompt、路径与secret，local_only零出站。

## K. Origin 与文件导出

- **PD-K01 正式格式。** 正式导出只提供 PNG、SVG 和 OPJU；不提供 PDF、EPS、EMF 等正式导出入口。
- **PD-K02 快速复制。** 剪贴板 PNG/SVG 可作为快捷操作，但不生成正式导出记录。
- **PD-K03 OPJU 技术路径。** Windows 本地通过 `originpro` 与 Origin COM 自动化生成 `.opju`；每个 Beta build 只声明一个完成完整 qualification 的 Origin exact version/build/bitness，其他版本全部 unsupported。
- **PD-K04 能力等级。** O1 为 full native semantic parity；O2 为原生 linked/editable 但有已声明非关键差异；O3 为 embedded/unlinked；O0 为 unavailable。第一轮正式 43 图必须 O1，O2 只为未来能力保留；已有 31 图实机矩阵是历史基础证据，不等于 43 图发布门禁已完成。
- **PD-K05 三格式验证。** 正式图形必须完成 PNG、SVG、OPJU 验证；OPJU 在构建实例 live validation 后由新的空白受控实例重新打开并读回数据、链接、图层、轴/ticks、图例、page/style 和 missing 语义。
- **PD-K06 独立 Origin 实例。** 不连接用户当前打开的 Origin，不使用 `op.attach()`；从空白项目启动专用受控实例。
- **PD-K07 原子导出。** 先写临时文件，验证成功后原子移动到目标路径；无论成功或失败都清理临时资源并退出受控实例。
- **PD-K08 安全边界。** 第一轮不执行任何 LabTalk、Python 或其他脚本字符串；OriginAdapter 只用 `originpro`/Python 类型化固定映射，不把 raster/SVG 嵌入伪装成原生图。
- **PD-K09 单图内容。** OPJU 只包含目标图直接使用的 Raw Data、PlotCalculationResult/用户预计算 Plot Data、原生图层/轴/ticks/图例/标注和 manifest，不复制无关列、对话、secret 或路径。
- **PD-K10 批次内容。** Selected/batch 在一个 OPJU 中包含多个 graph 并去重共享 Data/Analysis；固定 Data/Analysis/Graphs/Metadata folders，一个目标失败使整文件失败。
- **PD-K11 打开与外部修改。** 导出完成后只有用户明确点击才在 Origin 打开；外部编辑不回写；同路径覆盖前比较 hash/size/mtime，变化时要求确认或 Save As。
- **PD-K12 环境检测。** 启动只做轻量检测；正式 preflight 检查 Origin 精确命中当前 Beta build 声明，以及 license、bitness、originpro、字体、签名 template、adapter、目录和文件锁；其他版本返回 VERSION_UNSUPPORTED。
- **PD-K13 降级。** Origin 不可用时只禁用 OPJU，PNG、SVG、项目和其他本地能力继续可用。
- **PD-K14 不导入 OPJU。** 第一轮只导出，不反向导入或同步现有 `.opju`。

## L. 桌面运行、账户与安全

- **PD-L01 单实例。** 应用采用单实例；第二次启动时聚焦已有窗口，并转发 `.plotproj` 或数据文件参数。
- **PD-L02 单主窗口。** 不提供多主窗口，不驻留系统托盘；关闭主窗口即退出应用。
- **PD-L03 邀请制无账号。** 邀请码只授权内置模型服务，不是使用本地应用的前置激活；不要求注册账号、邮箱、密码、个人资料或云端找回。
- **PD-L04 不限设备。** 同一 InviteGrant 可在不限数量设备兑换；额度归 InviteGrant 并由所有设备共享，设备只承担鉴权及设备级并发/短时限流，重装或增加设备不能获得新额度。
- **PD-L05 撤销邀请码不破坏本地能力。** 邀请码被撤销后可停止云端模型额度，但不能锁定本地项目或禁用本地绘图与导出。
- **PD-L06 最小云端。** Beta云端只负责邀请兑换/长期设备凭据校验、内置模型proxy、InviteGrant原子共享计数和client_run幂等；不提供CloudConfig、更新、analytics或诊断上传，不保存项目或执行远程科研计算。
- **PD-L07 本地权限。** 第一轮不做应用级项目加密，依赖 Windows account ACL 并建议敏感用户启用 BitLocker；凭据只进 Credential Manager。每任务临时目录使用当前用户 ACL 并清理，但不承诺 secure erase。
- **PD-L08 后续加密。** 后续可评估密码加密 `.plotproj`；无账号体系意味着不提供云端找回密码。
- **PD-L09 本地缓存。** 缓存键包含内容哈希、绘图规格、渲染器和主题版本；支持增量失效并可由用户清除。

## M. 明确不做与分期

- **PD-M01 不做自动选图。** 不提供 Agent 推荐路径、自动替换图形或“猜你喜欢”。
- **PD-M02 不做任意改单元格。** PlotAgent 不是电子表格编辑器。
- **PD-M03 不做图像处理。** 第一轮不导入 TIFF、PNG、JPEG 作为科研图像，不做 ROI、比例尺、通道和混合图像面板。
- **PD-M04 不做任意 Python。** 第一轮不运行用户或模型生成的任意 Python。
- **PD-M05 不做账号与协作。** 第一轮无账号、云同步、团队协作和项目云存储。
- **PD-M06 不做多语言界面。** 界面仅简体中文；Agent 支持中文、英文和混合科研术语；图中文字不自动翻译。
- **PD-M07 不做深色主题。** 第一轮保持浅色、纯白图表画布和克制的产品配色。
- **PD-M08 不做 OPJU 导入。** 第一轮不反向读取或同步用户现有 Origin 项目。
- **PD-M09 不做数据库与实时流。** 第一轮不接数据库、实时仪器流和厂商私有格式。
- **PD-M10 不做版本合并。** 第一轮允许从旧版本分支，不提供分支合并。
- **PD-M11 不做社区市场。** 第一轮不开放第三方图形插件、教程市场或社区模板市场，只提供上下文帮助与官方资料。
- **PD-M12 不做科研解释。** 不自动解释数据意义、生成结论、图注或方法文本。
- **PD-M13 分期原则。** 第一轮完成数值绘图闭环；通用数据处理、AnalysisSpec/FitSpec、统计/拟合、高级组合、科研图像、扩展格式、流程模板和更大图形库在分别新增决策与验证后进入后续阶段。

## N. 内测与验收

- **PD-N01 内测规模。** 第一批邀请 10 至 15 人；第二批 30 至 50 人，覆盖至少五个学科。
- **PD-N02 首图激活。** 新用户无需账号，可从示例、真实数据或已有项目进入，并在 5 分钟内获得第一张图。
- **PD-N03 关键行为。** 验证自然语言改图、多文件批量、基础组合、项目恢复和 OPJU 后续编辑。
- **PD-N04 失败可理解。** 导入结构/字段不兼容、固定计算或预计算要求、任务部分失败和 Origin 不可用都必须给出具体原因与可执行下一步。
- **PD-N05 数据可复现。** 原始数据、来源坐标、FieldMapping、PreparationSpec、PlotCalculationResult、图形规格、版本、渲染版本和导出记录可追溯。
- **PD-N06 无隐式改变。** 图形类型、导入结构、FieldMapping、Preparation/PlotCalculation、预计算字段、单位、数据版本、坐标统一、源图替换和云端数据范围均不得静默改变。

## O. 后端与 Agent 架构

- **PD-O01 单 Agent。** 第一轮使用一个规划 Agent，不采用多 Agent 协作或子 Agent 系统。
- **PD-O02 有界规划。** Agent 使用固定上限的“本地上下文、单个结构化决策、本地校验、执行、验证、事务提交、状态归约与结果回复”流程，不运行开放式自主循环或工具循环。
- **PD-O03 结构化决策。** 模型只输出符合 JSON Schema 的 AgentDecision 候选，不生成或执行任意 Python、Matplotlib、Origin、SQL、命令行、URL 或文件系统操作。
- **PD-O04 同一执行链。** 手动 UI 与自然语言操作生成同一种 ActionPlan，离线模式绕过模型但复用完整本地执行链。
- **PD-O05 常驻 Python Core。** Electron 主进程启动并监管一个常驻 Python 3.12 Core，避免按任务重复启动导入、固定计算与渲染环境。
- **PD-O06 本地协议。** Electron 与 Python 使用版本化 JSON-RPC over stdio，不开放本地 HTTP 端口；大型数据只通过对象 ID 或受控资源引用传递。
- **PD-O07 Electron 权限边界。** React renderer 保持 sandbox、context isolation 和关闭 Node integration；preload 只暴露逐项、参数受限的强类型 IPC 方法。
- **PD-O08 主进程职责。** Electron Main 管理窗口、文件授权、单实例、系统凭据、Python 生命周期和任务事件转发。
- **PD-O09 PlotSpec 与 RenderPlan。** 版本化 PlotSpec 是图表结构化真值；Matplotlib、PNG、SVG 与 Origin 使用由 PreparedDataset、PlotCalculationResult/用户预计算字段、样式和发表规格解析出的同一 ResolvedRenderPlan。
- **PD-O10 PlotPatch。** 改图使用面向稳定语义 ID 的白名单 PlotPatch，并通过 expected version 防止覆盖并发或旧版本修改。
- **PD-O11 单一正式渲染器。** Matplotlib 是第一轮正式预览、PNG 和 SVG 渲染器；不同时维护 Plotly 与 Matplotlib 两套正式视觉结果。
- **PD-O12 模型适配层。** 内部只依赖 capability-based ModelProvider；OpenAI-compatible 服务以合成内容依次探测 Responses 与 Chat Completions 的结构化输出能力。response format/function-calling 仅是单个 AgentDecision 的传输约束，不提供工具授权。
- **PD-O13 输出能力等级。** P1 可稳定返回严格 JSON Schema；P2 仅 JSON 并在本地校验失败后最多 repair 一次；P0 不准入。任何等级都必须通过本地 schema、版本、能力、权限和业务校验。
- **PD-O14 领域服务。** Python Core 按 Project、Import、Preparation、PlotCalculation、Plot、Batch、Composition、Export、Origin 和 Task 服务划分，不把业务逻辑集中在模型提示中；v1 无通用 Transform/Analysis/Fit 服务。
- **PD-O15 持久化。** SQLite 保存元数据、引用、版本 DAG、任务和日志；内容寻址存储保存原始副本、PreparedDataset/Plot Data、PlotCalculationResult、PlotSpec、预览与缓存；Arrow/Parquet 为内部表格交换格式。
- **PD-O16 Pandas 边界。** Pandas 用于 Excel、SciPy、Matplotlib 与 Origin 兼容，不作为唯一存储真值。
- **PD-O17 项目包。** 活跃项目使用事务化工作目录；`.plotproj` 是经过 manifest 与哈希校验后原子生成的导入导出包，不在每次操作后重写整个包。
- **PD-O18 任务模型。** 普通数据与渲染任务可以并发，Origin 队列串行；每个写操作使用 request ID、幂等键、项目 ID 与 expected version。
- **PD-O19 Origin Worker。** Origin 在独立串行 Worker 中从 ResolvedRenderPlan 重建原生对象，临时保存、全新实例重新打开验证、原子移动并确保 `op.exit()` 清理。
- **PD-O20 运行时依赖方向。** 第一轮核心不需要本地 FastAPI/Uvicorn HTTP 服务，也不需要 Plotly/Kaleido 正式渲染链；具体依赖移除由实现阶段测试确认。

完整技术结构见 [后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)。

## P. PlotSpec、PlotPatch 与 ActionPlan 契约

- **PD-P01 对象拆分。** SourceDataset、FieldMapping/PreparationSpec、PreparedDataset、PlotCalculationSpec/Result、PlotSpec、BatchSpec、FigureSpec 和 ExportSpec 是独立领域对象，不用一个超大 PlotSpec 表达全部状态。
- **PD-P02 Schema 单一源头。** Python/Pydantic 模型是领域 Schema 唯一源头，自动生成 JSON Schema Draft 2020-12 与 TypeScript 类型。
- **PD-P03 严格输入。** 所有跨进程模型拒绝未知字段，使用严格基础类型，不接受额外属性、任意代码或任意路径。
- **PD-P04 PlotSpec 公共外壳。** PlotSpec 使用公共元数据、PreparedDataset/预计算字段/PlotCalculationResult 引用、坐标、系列、标注、样式快照、发表规格与来源结构。
- **PD-P05 图形家族联合。** 第一轮采用 `xy`、`categorical`、`distribution`、`matrix`、`survival`、`dose_response`、`forest`、`facet` 八个带 discriminator 的家族。
- **PD-P06 图形注册表约束。** `chart_type_id` 在图形注册表中约束家族、字段、geometry、固定计算/预计算要求、坐标、标注、组合和导出能力。
- **PD-P07 数据计算分离。** PlotSpec 只引用确定的 PreparedDataset、用户预计算字段与 PlotCalculationResult；renderer 不隐藏准备、分箱、KDE、汇总、拟合或检验计算。
- **PD-P08 样式快照。** PlotSpec 同时记录样式来源和解析后的完整样式快照，项目或期刊规格更新不会改变既有版本。
- **PD-P09 BatchSpec 独立。** BatchSpec 保存完全同构签名、共享映射、PlotSpec 模板、样式、坐标策略和单图覆盖；批次展开由 BatchService 完成。
- **PD-P10 FigureSpec 独立。** FigureSpec 保存固定布局并引用明确 PlotSpec 版本；源图更新只提示，不自动替换。
- **PD-P11 领域 PlotPatch。** 改图只使用带 `operation` discriminator 的白名单领域 Patch，不向模型暴露通用 JSON Patch 或 `set_property(path, value)`。
- **PD-P12 Patch 事务。** 多项修改进入 PatchTransaction，先完整校验再原子应用，并使用 expected version 防止覆盖新修改。
- **PD-P13 四类 AgentDecision。** 模型只能返回 ActionPlan、NeedsInput、Unsupported 或 NoChange 之一；不从自然语言或传输 transcript 猜命令。
- **PD-P14 v1 Action 边界。** 模型 Action 只表达创建/修改图、批次和导出的业务意图；文件导入、结构确认、FieldMapping UI、Preparation/PlotCalculation 是本地阶段，不由模型输出。没有通用派生数据、分析或拟合 Action。
- **PD-P15 计划上限。** 一个 ActionPlan 最多 8 个 Action，可以有无环依赖，不允许循环、条件脚本或运行时创建额外 Action。
- **PD-P16 批次内部展开。** 多文件 fan-out 由 BatchService 根据 BatchSpec 完成，不让模型逐文件生成 Action。
- **PD-P17 模型无执行工具。** 模型没有领域服务、文件系统、数据库、Origin 或 URL 工具，也没有 tool loop；只提交一个结构化 AgentDecision 候选，由本地校验器决定是否交给执行器。
- **PD-P18 Context Builder。** 模型调用前由本地系统准备当前目标、引用对象、字段、单位、摘要、图形能力与项目规则；不足时模型返回 NeedsInput。
- **PD-P19 确认与校验分离。** 可逆明确修改直接执行；必要信息缺失或歧义返回 NeedsInput；数学、安全、版本与产品硬规则由本地 validator 产生稳定阻断错误；科研 warning 不等同于确认弹窗。
- **PD-P20 破坏性操作隔离。** 永久删除、清空回收站、覆盖外部文件、凭据与隐私设置不进入普通 Agent ActionPlan，只能通过专门 UI 确认。
- **PD-P21 结构契约对象。** 领域 Schema 增加版本化 StructureUnitDefinition、语义 Port、ComponentInstance、封闭 Relation 联合、ChartRecipe 与 ChartRecipeRef；Python/Pydantic 仍是唯一 Schema 源头，所有对象拒绝未知字段和任意代码/路径。
- **PD-P22 结构到实例。** ChartRecipe 表达可复用图义骨架；FieldMapping 把当前 PreparedDataset 字段绑定到配方语义槽位；本地 compiler 确定性生成 PlotSpec，PlotSpec 仍是一张具体图及其精确数据、样式和版本真值。
- **PD-P23 映射增量。** 搭建或选择结构后只进行一次字段映射；增加组件时复用可证明仍有效的绑定，只询问新增/冲突槽位。共享观测的线和点可共用 X/Y，独立测量不得因类型相同自动共用 Y，误差字段必须同时声明所属组件。
- **PD-P24 关系强类型。** 分组、堆积、附着、连接、偏移、分面与轴归属使用带 discriminator 的封闭 Relation；误差、区间和标签通过目标 component ID 附着，renderer 不从字段名、series 顺序或坐标位置反推关系。
- **PD-P25 固定计算端口。** renderer只能消费 PreparedDataset、用户预计算字段或登记的 PlotCalculationResult；直方、箱线等封闭固定计算不能自由串联、发布为通用派生数据或借任何图形能力开放拟合、公式或任意聚合。
- **PD-P26 复用无需再认证。** 图形配方保存和复用只执行 Schema、端口、关系、字段和当前 renderer capability 的确定性校验；不生成测试数据、不重新跑泛化矩阵或 Origin qualification。普通 OPJU 仍执行本次产物的 build/fresh-reopen 验证。
- **PD-P27 结构与样式版本分离。** 纯样式、文字或坐标范围变化只创建 PlotSpec 版本；组件图或关系变化创建配方/结构版本。配方升级与 PlotSpec 升级分别固定父引用，不能用样式变更制造无意义配方版本。
- **PD-P28 编辑能力契约。** 图形注册表为每个正式 chart type 保存版本化 `ChartEditCapabilityProfile`，按 operation、target kind、allowed payload fields、renderer support 和科研约束校验 PlotPatch；客户端控件、Agent Context 与本地 validator 必须消费同一 profile，不能各自维护能力列表。
- **PD-P29 不支持语义。** Agent 收到超出当前图白名单的改图请求时返回 `Unsupported(reason=chart_edit_capability_not_supported)`；绕过 Agent 的本地请求由 validator 返回稳定 `PATCH_CAPABILITY_NOT_SUPPORTED`，不自动近似、不换图、不丢弃字段，事务保持原版本不变。
- **PD-P30 样式真值。** `ColorValue` 使用 8-bit sRGB 或严格 `#RRGGBB`；`PaletteRef` 固定 palette version/hash 与 resolved colors/stops；`MarkerStyle` 固定 symbol/interior/size/stroke/fill。Matplotlib 和 Origin 只消费解析后的值，Origin 名称和原生编号是 adapter 映射元数据而非存储真值。
- **PD-P31 固定计算参数不是样式。** 直方分箱、KDE 带宽、ECDF/CCDF 模式等会改变 PlotCalculationResult 的参数仍走各自封闭计算契约并创建新结果；逐图编辑能力白名单不得把它们伪装成 renderer-only style patch。
- **PD-P32 正式与隐藏能力。** `availability=official` 的 43 图可出现在 create/edit/export capability 中；九个保留图必须是 `availability=internal_hidden`，对用户 create/export 一律不可用。历史对象若存在，只允许在兼容 build 中只读展示或返回稳定不支持结果，不据此扩大正式范围。

完整 Schema 结构见 [领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)。

## Q. 项目存储、项目包与数据导入

- **PD-Q01 本机事务工作区。** 运行态使用 `%LOCALAPPDATA%\PlotAgent`；全局为 `catalog.sqlite3`，项目位于 `projects/<uuid>` 并包含 `project.sqlite3`、`objects/sha256`、`cache`、`tmp` 和 `project.lock`。
- **PD-Q02 catalog 边界。** 全局 catalog 只保存项目目录、最近打开和应用设置，不保存项目数据、对话、图表或凭据。
- **PD-Q03 项目数据库边界。** `project.sqlite3` 保存对话、对象关系、版本 DAG、任务、操作记录以及 SourceDataset、PreparationSpec、PlotCalculationSpec/Result 和 PlotSpec 等领域对象元数据。
- **PD-Q04 内容寻址对象。** 原始文件、Arrow/Parquet、持久化规格和导出等大对象按完整内容 SHA-256 保存，数据库只记录哈希、类型、来源和引用。
- **PD-Q05 不可变与缓存。** 原始数据对象不可变；缓存可再生、可清除且不进入项目包；临时产物未提交前不得成为正式对象。
- **PD-Q06 项目包是快照。** `.plotproj` 是可搬运、可校验的事务快照包，不是持续写入的实时数据库；内部自动保存始终写本机工作区。
- **PD-Q07 打开为工作副本。** 打开 `.plotproj` 时导入本机工作副本，后续不修改原包，也不依赖原包路径。
- **PD-Q08 已有副本与新副本。** 同一包再次打开默认回到已有工作副本；用户明确选择“作为新副本导入”时创建新的项目 UUID。
- **PD-Q09 包结构。** 项目包包含 `manifest.json`、一致的 `project.sqlite3` 快照、`objects/sha256` 和 `checksums.sha256`，不包含缓存、临时目录、项目锁、WAL 或共享内存文件。
- **PD-Q10 一致快照。** 使用 SQLite Online Backup 创建项目数据库快照，临时包完成结构和哈希校验后原子替换目标，禁止直接复制活动 WAL 数据库。
- **PD-Q11 完整项目包。** 完整项目包包含原始数据、PreparedDataset、PlotCalculationResult、对象关系和历史，可以恢复 v1 导入、准备、绘图与固定计算链。
- **PD-Q12 结果项目包。** 结果项目包省略原始数据，但保留打开、改图和导出所需的 Plot Data、固定计算结果、规格和版本关系。
- **PD-Q13 结果包限制。** 结果项目包不能宣称隐私安全；依赖已省略原始数据的重新解析或重新准备不可用，限制必须写入 manifest 并在界面显示。
- **PD-Q14 原子导入流水线。** 导入依次经过文件授权、临时复制与哈希、格式识别、必要追问、完整分块解析、Arrow/Parquet 转换、质量摘要、对象移动和 SQLite 事务注册；失败不污染正式项目。
- **PD-Q15 ImportRecipe。** 编码、分隔符、工作表/DataBlock、表头、preamble/postamble、缺失值和解析版本保存为 ImportRecipe；源内容或 ImportRecipe 变化都创建新的 SourceDataset 版本。
- **PD-Q16 结构后单次语义映射。** 系统先确认 sheet/DataBlock/region 等结构候选，选图后再只进行一次字段角色映射；两阶段职责不同且不允许逐文件例外。
- **PD-Q17 最终语义签名。** 完全同构要求字段集合、逻辑类型、单位、字段语义和最终映射一致；列顺序可以不同，最终映射进入语义签名。
- **PD-Q18 列名规则。** 列名只清理首尾空格并执行统一 Unicode 规范化，不做模糊匹配；规范化后重复列名阻止导入。
- **PD-Q19 数值类型。** 整数与浮点可统一为逻辑 `numeric`，同时保留物理类型、范围和精度用于校验、导出和审计。
- **PD-Q20 SQLite 运行约束。** WAL 仅用于本机活动工作区，由 Python Core 单写入器管理；使用至少 SQLite 3.51.3 或官方修复回移版本，项目包、活动数据库和 WAL 不在网络文件系统中直接打开或持续写入。

完整目录、快照、项目包、导入和同构契约见 [项目存储、项目包与数据导入](./PROJECT-STORAGE.md)。

## R. 任务运行时、取消与崩溃恢复

- **PD-R01 两类运行对象。** InteractionRun 负责模型规划与停止生成，ExecutionTask 负责本地执行与取消；两者使用不同 ID、状态和控制。
- **PD-R02 NeedsInput 不建任务。** NeedsInput 结束当前 InteractionRun，只在来源对话询问必要信息，不进入任务中心或后台任务计数。
- **PD-R03 任务状态机。** ExecutionTask 主链为 `queued → preparing → running → committing → succeeded`，并支持 `cancelling`、`cancelled`、`failed`、`partially_succeeded` 和 `interrupted`。
- **PD-R04 提交不可取消。** `committing` 必须短暂且不可取消，防止 SQLite 或文件停在半提交状态。
- **PD-R05 第一轮无暂停/续跑。** 第一轮不提供任务暂停、继续或正式任务自动续跑；失败或中断后完成状态检查/temp清理，由用户明确重跑。
- **PD-R06 三通道。** Python Core 使用控制/SQLite 单写入通道、隔离计算通道和严格串行的 Origin 通道。
- **PD-R07 计算并发。** 计算通道默认最多 2 个隔离工作进程，检测到内存压力时新的并发下降为 1。
- **PD-R08 预览调度。** 交互预览高优先级；同一图的新预览可以 supersede 尚未开始的旧预览，不静默终止已开始任务。
- **PD-R09 原子领域任务。** 单图、改图、受控准备和一次固定绘图计算分别按一个领域事务原子提交；多文件导入会话整体原子。
- **PD-R10 批量部分提交。** 批量绘图保留已完成结果，取消或失败时创建明确的已取消或部分成功批次，不能标记为完全成功。
- **PD-R11 文件原子导出。** PNG、SVG、OPJU 每个目标文件先临时写入并校验，再原子替换；失败不破坏既有正式文件。
- **PD-R12 Cooperative cancellation。** 取消先设置 cooperative token，并只在解析分块、算法迭代、渲染阶段和批次项之间的安全边界响应。
- **PD-R13 隔离终止。** 宽限期后仍无响应时只终止承载任务的隔离工作进程，不为取消单个任务强杀 Python Core。
- **PD-R14 Origin 取消。** Origin 无响应时终止并重建 PlotAgent 管理的 Worker 与受控实例，不影响 Core 或用户自己打开的 Origin。
- **PD-R15 固定输入与冲突。** 每个任务固定输入版本并携带 expected version；冲突不静默覆盖，由用户选择旧版本分支或基于最新版本重跑。
- **PD-R16 引用与幂等。** 活跃任务引用的数据和对象禁止删除；每个输出使用 `(task_id, action_id, output_slot)` 幂等键。
- **PD-R17 预写与阶段记录。** 任务入队前持久化输入、计划、阶段、尝试和暂存目录，只在阶段边界写记录，用于确认原子提交、清理temp和解释失败，不承诺续跑内部算法状态。
- **PD-R18 Core 崩溃处理。** Electron监督Core心跳；遗留任务标为interrupted，检查项目权威状态未损坏并清理temp，正式任务不自动续跑/重试，由用户明确重试；无副作用preview/cache可重建，崩溃循环时停止自动重启。
- **PD-R19 进度与入口。** 进度使用真实文件、行、图或字节单位；任务卡留在来源对话，项目标题显示全局后台任务数，第一轮无 Windows 通知。
- **PD-R20 关闭应用。** 有活动任务时关闭应用只提供“等待完成”“取消并退出”“返回”；取消并退出必须等待不可取消提交阶段结束。

完整状态、调度、提交、取消、崩溃完整性与明确重试契约见 [任务运行时、取消与崩溃恢复](./TASK-RUNTIME.md)。

## S. 固定绘图计算与科学边界

- **PD-S01 v1 封闭计算。** 第一轮只执行与图形几何不可分割的 PlotCalculationSpec/Result；通用 AnalysisSpec/Result、统计、拟合、平滑、基线和归一化后移。
- **PD-S02 八类联合。** 仅允许 HistogramBinning、TukeyBox、ViolinKDE、ECDF、SummaryError、PercentStack、MatrixProjection 和 ConfusionCount 八类规格。
- **PD-S03 无开放链。** PlotCalculationSpec 不允许新 kind、任意表达式、自由串联或发布为通用数据集；由本地 compiler 生成，模型不能选择或编排。
- **PD-S04 完整持久化。** 参数、算法版本、input/output hash、纳入/排除行数、missing policy 与固定 seed 必须持久化；参数变化创建新 FigureVersion。
- **PD-S05 Histogram。** 默认 Freedman–Diaconis；IQR=0 回退 Sturges；常量数据单箱。
- **PD-S06 Box。** 使用版本化线性分位数与 1.5 IQR whisker；离群点只标记不删除。
- **PD-S07 KDE。** Violin 和 density 都使用 Gaussian/Scott/256 grid；violin 裁剪观测范围，density 两端延伸 3 bandwidth。
- **PD-S08 ECDF。** ECDF 为 `count(<=x)/n` 的右连续阶梯，CCDF 使用对应反向累计定义。
- **PD-S09 Summary/error。** 仅允许 mean±SD、mean±SEM、mean±95% t CI、median+IQR、median+range 或直接中心/边界/对称误差；SD ddof=1，计算型每组至少两个有效值。
- **PD-S10 Percent stack。** 仅接受非负组件且每类别总和大于零，按类别归一化并保留原值与总和。
- **PD-S11 Matrix。** Heatmap XY 坐标必须唯一，重复坐标阻断不聚合；K22 只接受规则 grid，不做 gridding/interpolation。
- **PD-S12 Confusion。** 支持 count、按真实类和按预测类归一化；不训练或评价模型。
- **PD-S13 公共数值规则。** jitter 固定 seed；log axis 第一轮仅 Log10，非正值阻断且不静默跳过。
- **PD-S14 缺失策略。** 只允许 `fail` 或 `exclude_with_report`；后者保存排除行与原因，SourceDataset 不变。
- **PD-S15 预计算图形。** 当前正式图中 K21/K22/S34 只接受规定的预计算字段，不执行对应相关、插值或Nyquist分析；其余历史条目已退出正式产品能力。
- **PD-S16 不隐藏图形。** 需要分析结果的图仍显示，详情页和执行前明确“需要预计算字段”；缺失时稳定阻断并说明字段。
- **PD-S17 同一结果消费。** Matplotlib、SVG 与 Origin 消费同一持久化 PlotCalculationResult 或用户预计算 Plot Data，不各自重算。
- **PD-S18 完整数据。** 固定绘图计算在声明支持规模内使用完整数据；preview 简化不改变范围、计算或输入。
- **PD-S19 不自动重算。** SourceDataset 或参数变化不覆盖旧结果；用户明确重绘时创建新 PlotCalculationResult 和 FigureVersion。
- **PD-S20 批量一致性。** 同构批次使用完全相同的 FieldMapping、PreparationSpec 与 PlotCalculationSpec，不允许逐文件例外；单项可部分失败。

完整固定算法、预计算字段、对象和执行边界见 [固定绘图计算与科学边界](./ANALYSIS-ENGINE.md)。

## T. v1 预计算科学结果与拟合分期

- **PD-T01 后续能力。** FitSpec/FitResult、回归、4PL/5PL、KM、相关、统计检验、显著性、平滑、基线和归一化均不进入 v1 Schema、Action、fixture 或发布门禁。
- **PD-T02 禁止隐藏拟合。** PreparationSpec、PlotSpec、renderer、Origin formula/Analysis Template 和 Agent 均不得执行或伪装拟合。
- **PD-T03 K05 输入。** 回归散点/置信带由用户提供 curve X/Y 和可选 lower/upper；PlotAgent 不回归或估计区间。
- **PD-T04 K21 输入。** 相关矩阵由用户提供已计算矩阵和标签；不执行 Pearson/Spearman、p 值或多重校正。
- **PD-T05 K22 输入。** 等高线只接受规则 X×Y grid/Z；不执行 scattered gridding 或 interpolation。
- **PD-T07 S05 输入。** 剂量反应由用户提供拟合曲线与可选参数标签；不执行 4PL/5PL、IC50/EC50/ED50 估计。
- **PD-T09 S25 输入。** 连续谱图只绘制提供的数值谱线；不做 baseline、平滑或归一化。
- **PD-T10 S31 输入。** XRD 只绘制 angle/intensity 和可选用户峰标；不做背景、寻峰或拟合。
- **PD-T11 S34 输入。** Nyquist 只绘制 Z′/Z″ 和可选用户曲线；不做等效电路拟合。
- **PD-T12 输入透明。** 图形详情页和执行前展示“需要预计算字段”、字段清单和 PlotAgent 未执行分析的说明。
- **PD-T13 结构校验。** 预计算数值仍校验类型、单位、形状、上下界次序、长度和有限性，但不重算科学结果。
- **PD-T14 来源标识。** 用户提供结果记录 `user_provided_precomputed` provenance，不命名为 AnalysisResult/FitResult。
- **PD-T15 不自动刷新。** Raw Data 更新不会自动刷新预计算结果；重新导入与重绘创建新 FigureVersion。
- **PD-T16 统一渲染。** preview、formal PNG/SVG 和 OPJU 使用同一持久化预计算数值，renderer 与 Origin 不重算。
- **PD-T17 OPJU Plot Data。** 预计算结果进入 Plot Data worksheet 并链接原生 Graph；编辑 Plot Data 可更新，编辑 Raw Data 不触发重新分析。
- **PD-T18 无 Origin 分析链。** v1 不创建 Origin Analysis Template、worksheet formula、Fit Function 或 LabTalk 重算链。
- **PD-T19 后续启用条件。** 未来拟合需新增/更新 Decision、Schema、算法版本、reference fixture、错误、兼容与 release gate，不得借 v1 固定计算扩展。
- **PD-T20 不构成当前承诺。** 拟合专项文档只冻结分期与输入边界，不表示任何拟合算法在 v1 可用。

完整 v1 预计算拟合输入与未来分期边界见 [拟合能力分期边界](./FITTING-SYSTEM.md)。

## U. 受控准备、单位与来源追溯

- **PD-U01 SourceDataset 内容。** 保存 source hash、ImportRecipe、schema/UnitSpec、质量摘要、稳定 field id、source row id 和 sheet/block/line/cell 来源坐标。
- **PD-U02 原始只读。** 原始文件与 SourceDataset 永不修改；ImportRecipe 或源内容变化创建新版本，已有图保持绑定旧版本。
- **PD-U03 封闭准备。** 本地 compiler 只生成 select fields、structure projection、isomorphic concat、metadata label、plot order 和 plot mask 等封闭 PreparationSpec。
- **PD-U04 非开放产品。** PreparationSpec 不是模型输出或可编程步骤列表，PreparedDataset/Plot Data 只用于复现，不是可任意继续加工的数据资源。
- **PD-U05 禁止通用变换。** v1 不提供 filter/dedupe/join/unit conversion/arithmetic/log/zscore/baseline/normalize/category recode、单元格编辑、SQL/Python/UDF。
- **PD-U06 Excel sheet。** 多 sheet 默认独立 SourceDataset/批次；仅用户明确要求且 schema/类型/单位/语义一致时纵向 concat，并保留 `source_sheet`。
- **PD-U07 禁止跨 sheet join。** 不依据同名列或位置自动 join、merge、pivot 或 aggregate 工作表。
- **PD-U08 TXT 结构。** TXT/CSV 分离 InstrumentMetadata、DataBlock 与 postamble；多个 block/sweep/channel 展示候选并默认独立批量。
- **PD-U09 Metadata 投影。** InstrumentMetadata 默认不进入列；仅用户明确用于标签/分组时投影常量来源列。
- **PD-U10 最小追问。** region、encoding、delimiter、header 有多个合理解释时只问一个最小问题；超出清单稳定拒绝。
- **PD-U11 不静默处理。** 不删行、补值、去重、过滤异常、换算单位、执行科学计算或公式/宏/脚本；`0/False` 始终有效。
- **PD-U12 UnitSpec。** 保存 source_text、confirmed canonical unit（如有）、dimensionality、kind 与 registry version；v1 只确认和校验，不执行单位换算。
- **PD-U13 PreparedDataset。** 保存 SourceDataset、FieldMapping、PreparationSpec/compiler version、schema/单位、provenance、纳入/排除计数和 input/output hash。
- **PD-U14 来源坐标。** Excel 保留 workbook/sheet/cell/source row，文本保留 byte/line/block/channel/source row；来源关系可从图追溯到原文件坐标。
- **PD-U15 缺失策略。** 只允许 `fail` 或 `exclude_with_report`，后者生成绘图 mask 并记录原因；SourceDataset 不变。
- **PD-U16 非有限值。** NaN/Inf/missing 原样保留并报告未绘制数，不通过 truthiness 或 renderer 默认静默删除。
- **PD-U17 同构签名。** 批量要求字段集合、逻辑类型、单位、语义、FieldMapping 和 PreparationSpec 一致；列顺序可不同。
- **PD-U18 不标准化异构。** 异构输入拆成独立候选；v1 没有先通用变换再纳入批次的路径。
- **PD-U19 持久化边界。** PreparedDataset 与 PlotCalculationResult 可进入 `.plotproj` 和 OPJU Plot Data，但 UI 明确其用途与不可自由加工边界。
- **PD-U20 错误归属。** 导入、映射、准备分别使用 `IMPORT_*`、`MAPPING_*`、`PREPARE_*`，首次偏差通过分层快照定位，不由下游兜底。

完整受控准备、单位与来源追溯契约见 [受控数据准备、单位与来源追溯契约](./DATA-TRANSFORMS.md)。

## V. 渲染管线、坐标与一致性

- **PD-V01 单一 Resolver。** PlotSpec/FigureSpec、PreparedDataset、PlotCalculationResult/用户预计算引用、resolved style 和 publication profile 只经一套版本化 resolver 生成 ResolvedRenderPlan。
- **PD-V02 Adapter 无默认决策。** Matplotlib 与 Origin 只消费 RenderPlan，不自行 autoscale、选择 ticks、重算固定/科学计算、换单位、fallback 字体或重新布局。
- **PD-V03 RenderPlan 内容与哈希。** Plan 固定物理画布/subplot、图层顺序、数据表引用、样式/font、axis range/ticks/labels、legend/annotation/panel、数据完整性和全部 hash/version；正式 ExportSpec 记录 plan hash。
- **PD-V04 三质量层。** 第一轮 quality tier 为 thumbnail、interactive 和 formal，三者使用同一语义 resolver。
- **PD-V05 降采样边界。** thumbnail/interactive 可记录并显示确定性视觉降采样；formal PNG/SVG/OPJU 使用完整数据，SVG 不静默抽稀或栅格化。
- **PD-V06 坐标白名单。** 第一轮只支持 linear、log10、datetime 和 categorical；不包含 log2、ln、symlog、probability 或 probit。
- **PD-V07 范围输入。** Autoscale 使用完整可见 Prepared/Plot Data、error、interval 和用户预计算 curve；离群值包含，NaN/Inf 排除并计数，legend/annotation 不影响范围，reference 由 `affect_range` 决定。
- **PD-V08 家族与 Log 规则。** bar/stack/area 包含零，line/scatter/distribution 不强制零；log 可见数据含非正值时阻止渲染。
- **PD-V09 Padding 与边界。** 连续轴在变换空间加 5% padding，类别轴首尾半 slot，zero-span 规则版本化；上下界分别 auto/fixed，reverse 必须显式。
- **PD-V10 批次统一范围。** Unified scale 先 union 各图未 padding raw candidate，再只执行一次 padding 与 zero-span 规则。
- **PD-V11 Tick 真值。** Resolver 用版本化 nice-number 算法生成 exact values/labels/exponent/precision 并确定性消减碰撞；v1 不执行单位前缀换算，scientific exponent 只改变显示格式。
- **PD-V12 物理尺寸与色彩。** Canvas/margin/subplot 用 mm，font/line/marker 用 pt；PNG 固定像素与 DPI，SVG 固定物理 size/viewBox，Origin 同 page 尺寸；第一轮仅 sRGB。
- **PD-V13 安全文本与字体。** SafeRichText AST 禁止任意 LaTeX/HTML/script；默认 font stack 为 Arial→Microsoft YaHei→DejaVu Sans，resolver 固定并验证实际 font file。
- **PD-V14 SVG 模式。** SVG 默认 text-to-path；editable text 为显式选项并带可移植性 warning，两者禁止 script 与 external refs。
- **PD-V15 语义而非像素一致。** Matplotlib 与 Origin 必须保持数据、坐标、ticks、布局、样式、图例和标注 semantic parity，不要求 pixel identity；font hinting、AA 与极短 dash cap 差异不是缺陷。
- **PD-V16 Parity 容差。** Canvas ±0.2 mm、subplot ±1 mm、font/line ±0.1 pt、marker ±0.25 pt、8-bit RGB 精确、alpha ±0.01、range/tick 容差为 `1e-10 × max(1, abs(value))`。
- **PD-V17 O1 原生语义。** O1 必须使用 Origin 原生 linked worksheet/matrix、plot、axis、legend、annotation 与 page，不嵌入 Matplotlib raster 作为原生 fallback。
- **PD-V18 关键语义阻止。** Origin 无法表达或重新打开读回关键语义时阻止 OPJU；adapter 不能运行时临时降级能力。
- **PD-V19 格式验证。** PNG 校验 signature/pixel/DPI/content；SVG 校验 parse/viewBox/size、无 script/external refs 与 element count；OPJU 在新空白受控实例中重新打开读回核心对象。
- **PD-V20 原子正式导出。** 每个正式产物先写同文件系统临时路径，按 RenderPlan 验证后原子替换；记录 ExportSpec、plan、输出与验证报告 hash。
- **PD-V21 动态布局真值。** 组数、类别数、数据范围、正负值、误差、标签、画布与发表规格共同决定柱宽/偏移/累计基线、坐标范围、绘制顺序、颜色、图例和标签布局；这些结果由单一 resolver 解析进 RenderPlan，Matplotlib 与 Origin 不得各自重算。
- **PD-V22 布局不变量。** 并列 geometry 不重叠；正负堆积分开累计；误差/区间使用显式目标端点；坐标范围覆盖全部可见 geometry；series、颜色与图例身份一致；解析坐标不得含未报告 NaN/Inf 或越界对象。
- **PD-V23 不写死语义。** 图形专用科学规则和固定计算可以登记，但不得以固定两组、固定类别数、固定值域或按 chart ID 常量替代数据驱动布局。基础布局算法按结构关系工作，现有 52 图中的按 ID 分支需审计并逐步迁移。
- **PD-V24 物理极限。** 动态布局先在有依据的最小可读尺寸内调整；固定画布无法容纳时显示具体拥挤/裁切冲突并提供增大画布、旋转标签、移动图例或分面选项，不自动换图、不删系列/刻度/数据、不缩写科研标签或缩成不可读字号。
- **PD-V25 证据阈值。** 最小柱宽、间距、字号、标记和可区分编码数量必须来自 Origin 模板、期刊规范或冻结可用性证据；没有依据的数值不得作为产品规范。超过可区分颜色数量时可组合颜色/线型/标记，仍不足则明确告警。
- **PD-V26 编辑解析唯一性。** PlotPatch 先经 `ChartEditCapabilityProfile` 校验，再由 resolver 把 Origin 对齐的 symbol/interior/palette、轴、线、填充和图例属性解析进单一 RenderPlan；adapter 不读取本机 Origin 色板默认值，仅在 source hash 完全匹配时使用限定安装目录中的官方资产，也不为不支持的编辑做 renderer-specific fallback。

完整 resolver、autoscale、ticks、文本、物理尺寸、容差与验证契约见 [渲染管线与跨 Renderer 一致性契约](./RENDERING-PIPELINE.md)。

## W. 原生 Origin OPJU 导出

- **PD-W01 交付边界。** OPJU 是 target-scoped self-contained editable delivery，不是 `.plotproj`；不包含无关数据、对话、secret、绝对路径或外部依赖。
- **PD-W02 Target scope。** Current chart 为一个 graph+所需数据；selected/batch 为多个 graph+共享数据去重；Figure 为一个原生 editable multi-layer graph。
- **PD-W03 文件夹与命名。** Project Explorer 固定 Data/Analysis/Graphs/Metadata；内部名稳定 ASCII，Long Name 保留可读名称。
- **PD-W04 最小数据。** 只包含直接图 Raw Data、固定计算图所需 Raw Data + PlotCalculationResult Plot Data、用户预计算 Plot Data 和 visibly plotted observations，不包含 unused columns。
- **PD-W05 Origin 元数据。** Worksheet 保留 Long Name、Units、Comments 和 designations；matrix chart 可用保持坐标/单位/链接的 Matrixbook。
- **PD-W06 Manifest。** Manifest 保存 PlotAgent↔Origin object map、所有 version/hash、chart/style/profile、adapter/template/originpro/Origin version、data-chain kind、Raw 不自动重算声明、export time、capability 与 O2 known differences。
- **PD-W07 能力定义。** O1 为 full native semantic parity；O2 为 native linked/editable with declared noncritical differences；O3 为 visual embedded/unlinked；O0 为 unavailable。
- **PD-W08 第一轮 O1。** 第一轮正式 43 图全部要求 O1 才开放 OPJU；未来高级图形可经产品准入使用 O2 并预先披露，不允许运行时降级。九个内部隐藏图不承诺 OPJU，即使 adapter 当前能够生成也不得暴露。
- **PD-W09 OriginAdapter。** 版本化adapter固定chart type、当前Beta build唯一Origin exact version/build/bitness、template hash、capability、data layout、typed property map、validation与differences；架构可在后续build增加新exact version记录。
- **PD-W10 Typed Plan。** Adapter 只接收本地生成的 typed OriginExportPlan，并只用 `originpro`/Python 类型化固定映射；模型、数据和应用均不得注入或执行 LabTalk/Python/property/path string，也不生成 Origin Analysis Template、worksheet formula 或科学重算链。
- **PD-W11 Template 安全。** 官方 template 签名并版本化，任务只复制所需文件到隔离临时目录，不读取或修改用户全局 templates。
- **PD-W12 Preflight。** 正式导出检查Origin精确命中当前Beta build唯一qualification声明，并检查license、bitness、originpro、font、template、adapter、target directory和file lock；其他版本全部`VERSION_UNSUPPORTED`。
- **PD-W13 实例隔离。** 构建与 reopen 各用新的 dedicated blank managed instance，永不 `op.attach()`，也不触碰或终止用户 Origin。
- **PD-W14 Live 验证。** 构建实例验证 folders/books/sheets/matrix/rows/columns/designations/Units/pages/layers/plots/data links/axes/ticks/legend/page/style 与数值/missing 语义。
- **PD-W15 Fresh reopen。** 临时 OPJU 保存后退出构建实例，由新实例打开并重新枚举读回全部关键对象、链接、值与无 external links。
- **PD-W16 整文件原子性。** 一个 OPJU 全部目标成功才原子移动；任一目标失败不发布，排除失败目标必须创建新 ExportSpec，绝不静默跳过。
- **PD-W17 ExportRecord。** 记录外部 path/hash/size/mtime、ExportSpec/RenderPlan/OriginExportPlan/validation hash、adapter/template/Origin version 与 targets。
- **PD-W18 外部修改与无回写。** Origin 编辑不回写；同路径覆盖前检测 EXTERNAL_MODIFIED 并要求确认或 Save As；第一轮无 OPJU import/round-trip。
- **PD-W19 稳定错误。** 错误码覆盖 NOT_INSTALLED、VERSION_UNSUPPORTED、LICENSE_UNAVAILABLE、CAPABILITY_MISSING、TEMPLATE_OR_FONT_MISSING、START_FAILURE、BUILD_FAILURE、SAVE_FAILURE、REOPEN_FAILURE、VALIDATION_FAILURE、TARGET_LOCKED、EXTERNAL_MODIFIED、CANCELLED。
- **PD-W20 恢复不改规格。** 错误提供安装/授权/版本/字体模板/目录锁/Save As 等明确动作；恢复不自动换 adapter、template、删目标或降级 capability。

完整 target 内容、adapter、安全、两阶段验证、原子性、外部修改与错误契约见 [原生 Origin OPJU 导出契约](./ORIGIN-EXPORT.md)。

## X. Agent 上下文、模型供应商与数据出境

- **PD-X01 本地权威链。** 固定链路为本地 ContextBuilder → ModelProvider → 本地 AgentDecision 校验 → 本地 ActionPlan 执行 → 权威对象与 ConversationState reducer；模型不拥有工具循环或执行权。
- **PD-X02 不可信数据。** 列名、单元格、元数据和其中 URL 均是不可信 data，不进入指令区、不解释为 instructions、不抓取链接。
- **PD-X03 无供应商会话。** 每次从本地权威状态重建最小 ContextEnvelope，不使用供应商 Conversation、`previous_response_id` 或隐藏会话状态；官方 OpenAI adapter 固定 `store:false`。
- **PD-X04 ConversationState。** 本地结构化状态保存目标、确认选择、带版本引用、映射、偏好、未决问题和最近结果，只由权威对象与执行结果 reducer 更新；不建立隐藏跨项目记忆。
- **PD-X05 ContextEnvelope。** Envelope 至少包含 schema/prompt 版本、locale、指令、target snapshot、conversation state、图形能力、selected context、DataDisclosure 和 context hash；所有引用带 object ID 与 version。
- **PD-X06 首次出境同意。** 每个 provider 首次处理项目内容前明确说明默认发送类别；默认不发送原始文件、工作区路径、SQLite、OPJU、完整表、完整项目或完整对话。
- **PD-X07 小样本与宽表。** 每次默认小样本最多 20 行、12 个相关字段和 200 个 scalar，使用版本化确定性选择；超过 200 列先由本地字段索引筛选候选，不发送全量 schema。
- **PD-X08 扩大出境。** 扩大数据范围只能由 NeedsInput 请求并显示对象、字段、规模和用途；授权仅为本次或本对话同类请求，可撤销且没有永久全局放行。
- **PD-X09 DataDisclosure。** 本地只保存 provider、对象版本、授权作用域、类别/数量、disclosure/context hash 与撤销状态，不为审计保存未展示的完整网络请求副本。
- **PD-X10 Provider 类型。** 内置 provider 通过邀请设备令牌访问 PlotAgent proxy，平台 key 仅服务端持有；自定义 OpenAI-compatible 先探测 Responses、再回退 Chat Completions，连接测试只发合成内容。
- **PD-X11 凭据与网络。** API key/设备令牌只存 Windows Credential Manager；非 loopback 强制 HTTPS、TLS 不可关闭，拒绝非 HTTP(S) 与带 Authorization 的跨 origin redirect；provider 配置不随项目包导出。
- **PD-X12 输出能力。** P1 为严格 JSON Schema；P2 为 JSON 且最多一次 repair；P0 不支持。所有等级都经过相同本地校验。
- **PD-X13 唯一决策联合。** Provider 只返回 ActionPlan、NeedsInput、Unsupported 或 NoChange；硬规则由本地 validator 阻断，不设置模型自报的 blocked 分支。
- **PD-X14 澄清上限。** 仅在对象、同等映射候选、影响科研结论的语义、扩大出境或本地校验无法成立时询问；一次一张卡且最多三个独立问题。
- **PD-X15 续接失效。** 澄清续接固定 target versions 与 context hash；目标变化使旧 draft 失效并基于最新权威状态重规划。
- **PD-X16 ModelRunAudit。** 审计保存 provider 类型/origin、model/profile/config、prompt/schema、request/run ID、耗时、usage、状态、DataDisclosure 计数与 context hash，不保存 secret、隐藏推理或完整 payload。
- **PD-X17 保留说明。** 内置 proxy 只承诺自身不记录 payload，并准确展示底层供应商政策；OpenAI API 不宣传零保留，第三方 provider 的保留政策必须由用户确认。
- **PD-X18 完整决策后执行。** Streaming 只降低网络等待，UI 只显示本地阶段；完整 plan 校验前不展示/执行 partial plan，取消立即中止 HTTP 请求且不暴露 chain-of-thought。
- **PD-X19 固定模型配置。** 每次 ModelRun 固定 model/profile/config version 并写入审计，运行中不得静默切换或 fallback 模型。
- **PD-X20 错误与验收。** Provider 连接/TLS/auth/rate/quota/timeout/cancel、schema/repair、context、出境、stale target 和 retention acknowledgment 使用稳定错误，并提供契约测试与故障注入矩阵。

完整上下文、供应商、出境、审计、保留与故障注入契约见 [Agent 上下文、模型供应商与数据出境契约](./AGENT-CONTEXT-AND-PROVIDERS.md)。

## Y. 邀请、共享额度与最小 Beta 云控制面

- **PD-Y01 InviteGrant 归属。** 邀请码对应可撤销、可过期的 InviteGrant；服务端只存高熵 secret 的版本化 hash，grant 固定 quota policy、允许 model profiles 与时间戳，不承担应用更新分发。
- **PD-Y02 不限设备共享额度。** 同一有效邀请码可重复兑换且不限制设备数；所有设备共享 InviteGrant 总额度，设备不获得安装级赠送额度。
- **PD-Y03 无硬件指纹。** 客户端生成随机 installation ID，不采集硬盘序列号、MAC、Windows 用户名、主机名或其他硬件身份；服务端设备记录不得反推出硬件身份。
- **PD-Y04 设备凭据。** 邀请码兑换返回长期 DeviceCredential；凭据只进 Windows Credential Manager，邀请码成功后不在本地持久化。第一轮不实现短期 access token、refresh rotation 或找回流程，凭据丢失用原邀请码重新兑换。
- **PD-Y05 最小 scope。** DeviceCredential 只授权 invitation status、built-in model proxy 与共享 quota counter；不得读取项目/文件。401 区分 credential invalid、invite revoked/expired 与 device blocked。
- **PD-Y06 撤销边界。** 管理端可撤销整个 InviteGrant 或封禁单个 device；两者只影响内置 Agent，不锁定项目、自定义 provider 或本地导入/Preparation/PlotCalculation/绘图/导出。
- **PD-Y07 额度幂等键。** 每次用户模型请求使用唯一 `client_run_id`/Idempotency-Key；`(invite_id, client_run_id)` 唯一，服务端原子记录请求结果与扣减，重试、超时和重启不得重复调用或重复扣费。
- **PD-Y08 原子共享计数。** 第一轮用 InviteGrant 级服务端原子共享计数完成检查与扣减，不实现 reserve/settle/reconcile、unused release 或复杂恢复状态机；供应商已实际处理的首次请求按该次 Beta quota unit 计一次，schema/业务校验失败不触发第二次扣减。
- **PD-Y09 QuotaSnapshot。** Beta 固定展示 granted、consumed、remaining、period/reset（如适用）与 server_time；不含 reserved。具体额度、周期和设备级速率属于服务策略。
- **PD-Y10 限流与耗尽。** 每设备可有并发/短时速率限制且 429 返回 retry_after；额度耗尽只禁用内置 Agent并提供自定义 provider，本地能力不受影响。
- **PD-Y11 最小云边界。** Beta 云端只有邀请码兑换/设备凭据校验、built-in model proxy、InviteGrant 原子共享计数与 `client_run_id` 幂等记录；不提供账号、同步、原始文件存储、远程科研计算、远程 Origin、CloudConfig、更新服务、analytics 或诊断上传。
- **PD-Y12 Proxy 日志。** Proxy 不记录 prompt、request/response body 或原始数据；只记录 run、invite/device 伪名、固定 model profile、quota unit、latency、稳定错误、时间和幂等状态。
- **PD-Y13 Lazy 云连接。** 应用启动不依赖控制面，不查额度或刷新凭据；只在内置 Agent 调用时校验 DeviceCredential 与共享计数。云端不可达不影响项目、手动 ActionPlan、自定义 provider 或导出。
- **PD-Y14 云重试。** 瞬时连接/5xx 自动重试最多两次并复用 request/client_run/idempotency lineage；用户取消与确定性 4xx 不重试，云失败不进入项目事务。
- **PD-Y15 人工分发更新。** 第一轮不做自动检查、应用内更新、后台下载或 `update_only`。Beta build 通过用户人工取得的安装包分发；更新资格不依赖邀请码，strict local_only 始终零出站。
- **PD-Y16 安装包完整性。** 人工取得的安装包必须在安装前校验发布方签名、SHA-256 与 Windows code signature；校验失败稳定阻断，不从应用内抓取任意 URL 或 manifest。
- **PD-Y17 无更新状态机。** 第一轮没有 UpdateManifest、download/install/restart 状态机、更新提醒或任务期间安装协调；用户退出应用后显式运行已验证安装包。
- **PD-Y18 无 CloudConfig。** 第一轮不下发 CloudConfig 或 remote config；客户端内置协议/profile allowlist，服务端不能改变导入/Preparation/PlotCalculation、渲染算法、项目或 publication snapshot。
- **PD-Y19 固定模型运行。** 每次 ModelRun 固定 model/profile identifier 并审计，运行中不得静默换模型；profile 变化只能随新客户端 build 或明确服务端部署版本进入后续请求。
- **PD-Y20 协议与验收。** Beta 只定义 redeem、credential-authenticated model invoke、quota status/atomic debit 与 `client_run_id` 幂等 envelope；验收覆盖多设备共享、重装、重试不重复扣费、撤销、云断连和本地降级。

完整 InviteGrant、DeviceCredential、原子共享计数、幂等与人工安装包契约见 [邀请、共享额度与最小 Beta 云控制面契约](./CLOUD-CONTROL-PLANE.md)。

## Z. 离线模式、本地安全、诊断与 Beta 兼容

- **PD-Z01 两组三入口。** 启动空状态保持“用示例项目试用 / 导入自己的数据 / 打开已有 `.plotproj`”；builtin invite、custom provider、local_only 只是首次需要 Agent 或模型设置中的服务模式，不替代工作入口。
- **PD-Z02 NetworkMode。** `builtin_proxy | custom_provider | local_only` 可显式切换且不修改项目；localhost endpoint 属于 custom provider，不能借此绕过 local_only 语义。
- **PD-Z03 local_only 零出站。** 严格 local_only 不兑换/校验设备凭据、不查 quota、不请求模型/更新/config、不发 analytics/diagnostics、不访问远程 URL；第一轮没有 `update_only` 例外。手动本地功能与三种正式导出完整可用。
- **PD-Z04 无项目加密。** 第一轮依赖 Windows account ACL 并建议 BitLocker；`.plotproj`、Parquet、OPJU 和结果包可能含敏感科研数据，均不得宣传匿名或隐私安全。
- **PD-Z05 Temp 安全。** 每任务随机隔离 temp、当前用户专属 ACL，成功/失败/取消/启动恢复清理；删除为 best effort，不承诺 secure erase。
- **PD-Z06 固定磁盘工作区。** 活动 workspace 只允许本机固定磁盘，拒绝在网络共享或不可靠同步占位目录直接运行 SQLite/WAL；外部 `.plotproj` 先导入本机副本。
- **PD-Z07 Archive 防护。** `.plotproj` 解包前/流式中校验 manifest/hash、entry/file/expanded size 与 ratio；拒绝绝对/`..`/重复规范化路径、link/junction/reparse/special entry 与 archive bomb。
- **PD-Z08 表格不执行。** Excel 宏/VBA/外链/公式不执行或刷新；公式仅导入已有缓存值并记录 provenance，无缓存为 missing/NeedsInput。CSV/worksheet text 永远只是 data。
- **PD-Z09 Electron 边界。** Renderer sandbox+contextIsolation、Node integration off、preload 强类型窄 API；聊天/数据不执行 HTML/JS，不自动打开 data URL 或数据链接，模型无任意 path/URL/file access。
- **PD-Z10 本地日志。** 日志 allowlist 保留 14 天或 100 MB；只含版本、状态、对象/chart ID、timing/buckets、稳定错误，禁止 prompt、文件/路径、列名/值/摘要、secret 和模型 body；stack 落盘前 scrub，第一轮无 memory dump。
- **PD-Z11 无 analytics。** 第一轮不实现或发送 usage analytics，不提供 opt-in 上报；本地功能使用情况不形成云端事件流。
- **PD-Z12 本地 DiagnosticBundle。** 每次由用户主动生成、逐文件与 exact JSON 预览后只保存到本地；默认仅含版本/capability/error/task/performance、结构/统计 bucket/hash、scrubbed stack/config/log。只有本次单独明确同意后才可加入已逐项预览的脱敏数据；仍禁止 DB原件、路径、prompt、secret 与 memory dump。
- **PD-Z13 Schema 拒绝优先。** Beta schema 不兼容时稳定返回 `SCHEMA_VERSION_UNSUPPORTED` 并保持原项目不变；第一轮不建设通用 MigrationPlan、N→N+1 registry 或 downgrade writer。
- **PD-Z14 已知版本对迁移。** 确有升级需要时，只为一个明确 source→target 版本对实现确定性一次性迁移：先创建一致快照，在新 temp workspace 执行、验证后原子切换；失败或取消继续使用原项目。
- **PD-Z15 迁移不改语义。** 一次性迁移只能改变存储表示，不得改变 chart/FieldMapping/Preparation/PlotCalculation/预计算字段/unit/style/visual；新科学/渲染版本须用户明确 adopt 并创建新对象。
- **PD-Z16 兼容规则。** 旧组件缺失可显示已有结果但重绘返回 `LEGACY_COMPONENT_MISSING`，不得换算法；未知未来 schema 拒绝编辑并提示使用兼容 build。
- **PD-Z17 无自动备份。** 日常可靠性依赖 SQLite transaction、immutable CAS 与原子项目/导出提交；第一轮不做每日 Online Backup、最近三份保留、恢复分支或恢复 UI。可搬运备份只有用户主动导出的 `.plotproj`。
- **PD-Z18 崩溃后明确重试。** 任务失败或崩溃必须保持已有项目权威状态不损坏、临时文件可清理并显示稳定错误；不要求全面自动续跑或静默 rollback，用户明确重试。
- **PD-Z19 领域与错误。** 固定 NetworkMode、LocalDiagnosticBundle、known-version MigrationRecord 与 cleanup states；不定义 update grant、通用 MigrationPlan、BackupRecord/RecoveryRecord。archive/formula/network/log/diagnostic/schema/migration 使用稳定错误。
- **PD-Z20 安全验收。** 验收覆盖 strict local_only 零出站、断网本地闭环、恶意 archive/Excel、日志/本地 Bundle 禁止字段、崩溃不损坏、未知 schema 拒绝和已知版本对迁移的语义不变/原子失败。

完整 NetworkMode、本地权限、不可信导入、日志/本地诊断、schema兼容与崩溃重试契约见 [本地安全、诊断与 Beta Schema 兼容契约](./LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md)。

## AA. 小规模邀请制 Beta 性能与发布门禁

- **PD-AA01 单一 Windows profile。** 每个 Beta build 只在一个发布时仍受支持的 Windows 11 x64 reference profile 正式 qualification；当前为 Windows 11 25H2/6C/16GB/NVMe/1920×1080，DPI 只测 100% 与 150%。
- **PD-AA02 后续平台。** Windows 10、LTSC、ARM64、minimum machine、125%/200% DPI 与多 OS 矩阵不属于当前 Beta 声明；其他环境可尝试但必须标“未完成 Beta qualification”。
- **PD-AA03 单一 Origin version。** 每个 Beta build 只声明一个完成 qualification 的 Origin exact version/build/bitness；其他版本全部 `VERSION_UNSUPPORTED`。该版本独立完成正式 43 图各一份代表性 O1 live+fresh-reopen；minimal/edge/error 由离线契约、验证器和稳定错误 evidence 覆盖。已有 31 图实跑继续作为基础证据，新增 12 图必须在发布前补齐。
- **PD-AA04 唯一规模基线。** 正式 qualification 为 100k rows×20 columns、常规 10 charts、单图≤100k plotted primitives、批量20 files/charts×每图10k、项目≤100 charts；不再设 large/boundary 门禁。
- **PD-AA05 超范围 best effort。** 超出已验证范围先显示“超出 Beta 已验证范围”与 resource preflight；成功不扩大声明。资源不足稳定拒绝并建议用户在外部显式准备较小数据或缩小批次，formal 不静默抽稀、换算法或借机执行隐藏筛选/聚合。
- **PD-AA06 Preview 与 formal。** Thumbnail≤5k、interactive≤20k visible primitives；100k preview P95≤3s，range/PlotCalculation 使用 full data并显示简化。声明规模内 formal PNG/SVG/OPJU 全部 full data。
- **PD-AA07 导入预算。** Reference P95只保留100MB CSV≤12s与50MB XLSX≤30s，包含安全复制/hash、完整解析、内部格式、摘要与事务提交；1GB CSV不在当前 qualification。
- **PD-AA08 绘图导出预算。** Reference P95：style patch≤2s、20×10k batch≤30s、100k PNG≤5s、SVG≤10s、single OPJU≤60s、20-chart OPJU≤180s；第一轮无1M preview门禁。
- **PD-AA09 Agent 与反馈预算。** ContextEnvelope build P95≤1s；内置 structured decision P50≤8s/P95≤20s并单列 provider latency；输入/点击/任务卡反馈≤100ms，>2s 展示真实阶段。
- **PD-AA10 Memory。** Idle Electron+Core≤700MB，正式 qualification workload peak≤2GB；资源预检不足时以 `RESOURCE_LIMIT` 拒绝，可把新任务并发降为1但不改算法或提交半对象。
- **PD-AA11 Disk 与 SVG preflight。** 导入前 free disk≥estimated landed bytes×2.5；formal按实际100k声明范围估计primitive/file/memory/disk并告警或拒绝，不使用2M primitives/200MB商业级固定门槛，不自动栅格或抽稀。
- **PD-AA12 43图 Fixtures。** 正式 43 图每图保留 minimal valid、representative research、edge/error 三类 fixture；formal PNG/SVG 运行离线矩阵，preview/interactive 另测。OPJU 在当前 build 唯一 Origin exact version 对每图运行一份 representative live+fresh-reopen；minimal 与 edge/error 复用同一 typed plan 的离线 contract/validator 与预期稳定错误，不重复进行昂贵 COM 实跑。九个隐藏图的内部回归不计入正式 MatrixKey 覆盖率。
- **PD-AA13 机器可统计证据。** MatrixKey 固定 build/chart/fixture/artifact/adapter-or-renderer/唯一Origin/Windows profile/locale/case，记录 input/spec/plan/artifact/validator/dependency/fixture hashes、资源和稳定错误。
- **PD-AA14 Beta 测试层。** Gate 覆盖schema/domain、约30个import golden、mapping/preparation/unit/provenance、九类PlotCalculation与预计算字段、render/parity、单Origin O1、Electron↔Python E2E、cancel/crash/idempotency、安全/零出站、reference性能和签名安装包；程序/固定模型契约/真实模型质量三层分离。
- **PD-AA15 可复现性能协议。** 固定cold/warm、dataset hash、reference profile、sample count、nearest-rank P50/P95和cache policy；普通路径≥10次、昂贵OPJU≥5次，P95退化>15%或越绝对预算即调查并阻断。
- **PD-AA16 Beta 缺陷处理。** 每个 blocker/critical/known issue 有唯一 owner、affected MatrixKeys、影响和恢复动作；不影响正确性/安全/可追溯/完成路径的问题可进入 Beta known issues，不建设商业级 waiver 审批链。
- **PD-AA17 不可豁免阻断。** 数据损坏、静默导入区域/mapping/unit/preparation/PlotCalculation/预计算字段变化、formal降采样、假O1、secret泄漏、43图正式声明失败、签名绕过、已知blocker/critical与靠retry变绿均阻止分发。
- **PD-AA18 Beta Evidence。** 每个 build 固定 manifest/source/test-runner/app/PlotSpec/model/prompt/Unicode/dependency/fixture hashes，提交导入 golden、43 图 PNG/SVG 离线矩阵、额外 preview、单 Origin 43 图 representative 实跑、逐图编辑/符号/色板报告、固定计算/预计算、local security、简化 quota 幂等、安装包 hash 和 known issues 检查单。
- **PD-AA19 首批成功门禁。** 第二批 go/no-go：sample 首图独立≥80%，真实数据首图无staff takeover≥60%，愿再用真实数据≥60%，至少1人batch、至少1名Origin用户继续编辑OPJU；第一轮无analytics，使用经同意观察/访谈。
- **PD-AA20 门禁语义。** 本节只定义小规模邀请制 Beta qualification，不表示当前实现已通过；单一 Beta release owner 汇总checklist并由科学/Origin负责人复核专业证据，不要求商业级多角色签署。
- **PD-AA21 两类绘图证据。** 同源参考图视觉审计回答“默认样式是否符合依据”；冻结生成器的参数化泛化测试回答“数据范围、组数和边界变化时结构是否仍正确”。合成数据不能替代同源视觉金标，同源图片也不能替代结构不变量测试。
- **PD-AA22 泛化维度。** 基础门禁至少覆盖系列/组数 1/2/3/5、类别/点数变化、缩放/平移、跨零/全负、零/对称/非对称误差、长中英文标签和可选字段缺失；必要的更高数量按结构风险补充，不要求无意义的全笛卡尔积。
- **PD-AA23 泛化 oracle。** 生成器版本、seed、manifest 与预期不变量随仓库冻结；不得在运行时从被测实现生成答案。可机械验证的重叠、累计、附着、范围、身份和有限值问题必须自动阻断，文字审美等不可完全机械判断的项目保留代表性视觉审计。
- **PD-AA24 Renderer 覆盖。** Matplotlib 运行完整正式基础泛化矩阵；Origin 按不同基础结构签名选择最小、常规和复杂代表数据 live+fresh-reopen。除明确使用冻结合成视觉验证且不得冒充官方证据的 X24/S07 外，每个正式图至少保留一组同源 Origin 证据；九个隐藏图的内部测试不计正式覆盖。昂贵 Origin 泛化不转嫁到每次用户复用。
- **PD-AA25 发布顺序。** 当前先完成并冻结基础图形泛化门禁、修复发现的确定性 bug，再实现结构单元/配方 compiler；组合实现不得修改基础测试 oracle 来适配自身输出，M7 必须等待该重新打开的 M6 范围完成。
- **PD-AA26 编辑与 Origin 样式门禁。** 正式 43 图逐图验证 allowed patch 成功、undeclared patch 稳定不支持、版本/事务原子性和 Matplotlib/Origin semantic parity；覆盖全部 12 种符号、闭合符号的 3 种 interior 与 `plus/cross` 非适用拒绝，以及 16 色板按结构签名的映射/readback；RGB 每通道精确，隐藏九图不得出现在产品 capability snapshot。
- **PD-AA27 专属编辑封闭联合。** 通用编辑之外只增加 `bar_area`、`uncertainty`、`colorbar`、`dual_y`、`facet`、`y_offset`、`chart_parameters` 七个强类型状态组及一一对应的 Patch/Agent intent；UI、Agent、validator 和两套 renderer 共用 capability profile，未声明图形或字段稳定不支持，不开放任意 Origin property、JSON path 或脚本。
- **PD-AA28 X02 基线语义。** 棒棒糖图默认 baseline 为数据坐标 `Y=0`，调整显示范围不改变横轴位置；显式 baseline 同时控制棒线起点与横轴数据交点。
- **PD-AA29 色带标题安全映射。** 色带本体固定为 Origin 原生 `Spectrum1`，色域/levels 写入原生 plot `zlevels`。当前锁定 `originpro` 不能安全稳定写入 `Spectrum1.title`，因此标题使用色带旁同层原生可编辑文本对象并完成 fresh-reopen 读回；不得为内部对象名一致而新增任意 LabTalk/属性路径，未来迁回须建立新的版本化证据。

完整单一平台/规模/Origin、预算、43图MatrixKey、不可豁免blocker、Beta checklist与测量协议见 [小规模邀请制 Beta 性能测试与发布门禁契约](./PERFORMANCE-TEST-RELEASE.md)。

## AB. 实施拆分与设计冻结

- **PD-AB01 Workstream 边界。** v1实施固定拆为W0 Contracts、W1 Desktop、W2 Data Import/Preparation、W3 Plot Calculation、W4 Rendering、W5 Workflow、W6 Origin、W7 Agent、W8 Cloud、W9 Local lifecycle、W10 Release，不设模糊“实现后端”总任务。
- **PD-AB02 W0 先行。** Pydantic/JSON Schema/generated TS types、RPC/event、stable error registry、golden fixtures和evidence harness是所有跨模块实现前置。
- **PD-AB03 W1 Desktop。** Electron Main/preload/PythonSupervisor/single-instance/task events与Credential facade由Desktop Platform负责，不承载领域计算。
- **PD-AB04 W2 Data。** Storage、确定性 Excel/TXT/CSV import、SourceDataset、FieldMapping、PreparationSpec/PreparedDataset、单位与来源追溯由 Data Platform 负责。
- **PD-AB05 W3 Plot Calculations。** 九类封闭 PlotCalculationSpec/Result、固定默认、预计算字段校验和 golden fixtures 由 Plot Calculation 负责；通用分析/拟合不在 v1。
- **PD-AB06 W4 Rendering。** 43 图正式 registry、九图隐藏内部代码面、StructureUnit/ChartRecipe compiler、PlotSpec/Patch、逐图编辑能力、Origin 对齐符号/色板、动态布局、Resolver、Matplotlib与formal PNG/SVG由Rendering负责，不隐藏analysis或Origin逻辑；M6补充按“基础泛化→编辑/样式契约→首批14图配方迁移”顺序执行，其余29图保留既有路径。
- **PD-AB07 W5 Workflow。** 完全同构Batch/review与numeric-only Figure由Workflow负责，临时比较与正式版本严格分离。
- **PD-AB08 W6 Origin。** OriginAdapter/O1 OPJU/两阶段验证独立成高风险workstream；K01 O1 spike前置，不等全部正式图完成才验证技术路径；既有 31 图矩阵与新增 12 图补充证据分别记录。
- **PD-AB09 W7 Agent。** ContextBuilder/Provider/four-way AgentDecision/local validator由Agent Runtime负责；自然语言支持中英混合，但禁止本地任意命令/正则解析器绕过结构化链。
- **PD-AB10 W8 Cloud。** Invite/长期设备凭据/shared atomic quota proxy/client_run idempotency由Cloud负责；第一轮不含refresh rotation、reserve/settle、CloudConfig或应用内更新。
- **PD-AB11 W9 Local lifecycle。** local_only/安全导入/log/本地DiagnosticBundle/known-version migration由Local Security+Lifecycle负责；第一轮不做analytics、云端诊断、通用迁移或自动备份，严格零出站与原项目不受损是完成条件。
- **PD-AB12 W10 Release。** E2E/reference performance/security/manual signed installer/Beta checklist由QA/Release聚合，但领域错误仍回到唯一owner，不在gate层掩盖或修补。
- **PD-AB13 依赖DAG。** W0→W1/W2；W2→W3/W4/W7/W9；W3→W4/W6；W4→W5/W6；W1→W7/W9；W7→W8；W5/W6/W8/W9→W10。
- **PD-AB14 并行边界。** W1/W2在W0后并行，W5/W6在stable K01 Plan后并行；W10 harness从W0开始，但final qualification等待W5/W6/W8/W9。
- **PD-AB15 四个Risk Spikes。** 全面编码前验证K01 import→O1 fresh reopen、100k preview+formal SVG resource preflight、Core crash/SQLite commit boundary integrity、custom provider P1/P2 exactly-one-repair/no-tool-loop。
- **PD-AB16 垂直优先里程碑。** M0 contracts/spikes→M1 manual K01→M2 deterministic import/preparation/fixed calculations+31 PNG/SVG→M3 batch/Figure→M4 Agent→M5单一Origin exact version全部O1→M6轻量工程收口+基础泛化+首批14图可组合底座+批量辨识度闭环+完整生产前端重做→M7 Beta qualification。
- **PD-AB17 Evidence 完成。** Workstream和milestone只有scope/out-of-scope、inputs、deliverables、dependencies、parallel boundary、acceptance evidence、error owner与done definition全部满足才完成，不按“代码写完”。
- **PD-AB18 规格索引。** SPEC-INDEX记录每份文档权威范围、冲突优先级、Requirement→Workstream→entry→future evidence映射与readiness checklist。
- **PD-AB19 冻结含义。** Implementation-ready只表示产品行为和跨模块契约可直接实施，不表示真实后端/云/OPJU/测试已实现，也不伪造每图/每算法完整参数表。
- **PD-AB20 变更控制。** 后续产品/跨模块变化必须新增或更新Decision ID，同步PRD/专门契约/SPEC-INDEX与fixtures/evidence影响；实现层不得以便利为由静默偏离。
- **PD-AB21 M6 重新打开。** 原 M6 cloud/local security/人工安装包工程切片保持已实现，但新增确认的基础泛化门禁与内部可组合绘图底座属于 M6 补充退出条件；完成前顶层状态不得继续写“M0–M6 全部完成”，M7 不启动。
- **PD-AB22 M6 首批配方范围。** M6 先冻结现有基础图形泛化测试与修复，再加入正式/隐藏 availability、逐图编辑能力、Origin 对齐符号/色板、结构单元/ChartRecipe Schema与确定性 compiler。配方迁移只覆盖 K01/K02/K03/K05/K08/K09/K10/K18/S05/S25/X01/X02/X03/X09；其余29个正式图与九个隐藏 adapter 保留既有 PlotSpec/Resolver/renderer 回归，不阻塞 compiler v1。第一阶段不实现 `FigureRecipe`、双Y/分面/跨轴联动、X24/S07新增固定计算或用户自由搭建器。
- **PD-AB23 M6 后范围。** 持久化命名样式预设、数据替换/重放、精确对象树、完整图形模板、全窗口搭建器、项目/个人图形库、用户配方导入导出、其余29图迁移和自然语言结构编辑属于第一阶段后的候选增量，必须复用同一底座，不得另建自由脚本/renderer 或数据处理平台。
- **PD-AB24 最小辨识度对象。** 第一阶段只新增 `SelectionScope(current_plot|selected_plots|batch)`、可整体撤销的 `AgentChangeSet` 与 `BatchReviewItem`；不定义 figure scope、持久化 `StylePreset`、`DataReplacementPlan`、ChangeSet 专属历史/分支系统或任意重放脚本，既有 PlotSpec 版本 DAG 保持不变。
- **PD-AB25 首阶段批量边界。** 一个批次只有一种用户明确指定的图形，批量资格限首迁14图；一批只确认一次字段映射且只对精确兼容字段签名复用，不兼容稳定进入 `NeedsInput`。审阅只做真实缩略图、多选、状态筛选、失败项局部重试和批量导出；统一编辑只作用于共同 capability 并明确列出跳过项。
- **PD-AB26 首阶段样式复用。** 可把当前图已有强类型样式复制到选中图或整个批次，但不建设命名、持久化、版本化样式预设库。
- **PD-AB27 完整生产前端重做。** 第一阶段重做所有现有生产页面与新增批量页面，统一应用壳、项目/对话、首次启动、设置、导入/映射、审阅、ChangeSet、聚焦编辑和导出；前端蓝图先行，生产接入等待最小领域契约和真实批量链路稳定。未实现的第二阶段能力不得显示假按钮或模拟结果。
- **PD-AB28 Agent 辨识度重新排序。** 当前图形语义、Origin 图例和同源视觉证据收口后，第一优先级由 ChartRecipe/组合底座改为“项目级上下文 → 可恢复任务计划与编排 → 跨轮次作用对象解析 → 真实模型纵向链路 → Agent 资格测试”。ChartRecipe compiler、用户搭建器和完整图形模板后移到第二阶段，不再作为首轮 Agent 纵向链路或作品集演示的前置条件。
- **PD-AB29 项目上下文归属。** `ProjectContext` 是由本地权威对象、稳定资源 ID、版本和显式当前作用域构建的结构化投影，不是聊天全文摘要或供应商隐藏 memory。它至少覆盖数据源/工作表、字段映射、图与版本、批次成员、统一样式策略、当前/选中/全部范围、未解决问题和最近可恢复任务；跨对话共享项目对象，但不隐式共享其他对话全文。
- **PD-AB30 可恢复任务编排归属。** PlotAgent 自有 `TaskPlan`、依赖、确认点、逐项状态、幂等键、阶段 journal、部分成功、失败项局部重试和从已提交边界恢复。恢复必须由用户明确触发，只复用仍然有效的冻结输入与成功输出；不续跑进程内部状态、不静默自动重试、不重做成功项，也不把半成品登记为图版本。
- **PD-AB31 Agent Runtime 复用边界。** 不从零重写通用 LLM provider/transport/tool-loop runtime，也不把 Pi、Hermes 或其他通用 Agent 框架变成不可替换的产品核心。保留当前 Python Core 与 `ModelProvider`，新增薄且可替换的 `AgentRuntime` 接口；外部底座只可承担模型调用、结构化传输和通用会话循环，`ProjectContext`、`TaskPlan`、作用对象解析、权限、确认、执行、恢复、事务和科研校验始终由 PlotAgent 本地领域层拥有。Pi 可做限时适配 spike；Hermes 仅作能力参考，首阶段不直接套壳。
- **PD-AB32 有界自主执行。** 模型先基于最小 `ProjectContext` 生成可核对候选计划或提出一个必要追问；本地 resolver 绑定精确对象/版本，本地 validator 决定可执行项，确定性 `TaskOrchestrator` 才调用白名单领域服务。第一阶段不开放任意文件、数据库、Origin、URL、Shell、Python 或工具自治循环；手动 UI 与自然语言继续消费同一计划/执行链。
- **PD-AB33 Agent 作品集证据。** 首轮 Agent 完成定义不以模型回答“像人”或图形数量衡量，而以三条可复现实例证明：多文件/多工作表批量计划与一次确认、跨轮次范围/指代正确解析、部分失败后只修复并恢复失败项。机器指标至少覆盖计划合法率、作用对象解析准确率、字段映射首轮接受率、必要追问数、恢复成功率、陈旧计划拒绝和人工 Origin 流程节省时间；另保留 5–10 名目标科研用户的同意观察与访谈证据。

## AC. Origin 模板优先的绘图引擎重构（历史35图阶段）

- **PD-AC01 历史35图。** 本条记录上一阶段35图范围，现已由 PD-AF01 的34张单图取代。
- **PD-AC02 删除不是隐藏。** 已删除ID必须退出全部可发现、可调用和可导出路径。旧项目只返回 `CHART_TYPE_REMOVED`，不得静默替换近似图；墓碑不是候选、隐藏能力或renderer。
- **PD-AC03 裸模板测试先于实现。** 每个正式图逐图核查官方文档、本机模板和菜单命令，再执行行数、系列/组数、类别数、长中英文标签、数值范围、缺失值、编辑和 fresh-reopen 动态矩阵。测试阶段禁止按图形 ID 修布局或用几何模拟 Origin 原生 Plot。
- **PD-AC04 Origin承担动态显示。** 数据范围、轴缩放、分组间距、原生图例/色带、标签和模板已支持的布局优先由 Origin 自动处理。Python只绑定数据角色、应用模板、执行证据证明必需的 T2 原生配置和用户编辑。
- **PD-AC05 不预设 renderer 形态。** 不再以 StructureUnit、统一 renderer、逐图 renderer 或 compiler 完整性作为目标；只以 Origin 映射正确、动态数据稳定、Agent 易操作和原生可编辑为选择标准。
- **PD-AC06 禁止旧路径回退。** 迁移后的正式图不得回退到手工几何拼装、任意 Origin property/script 或 Matplotlib 位图嵌入。已删除图不得保留可达的 Profile、计算、Matplotlib/Origin binder或近似图元；只允许迁移墓碑。
- **PD-AC07 资格重新建立。** 每图必须记录官方模板版本与哈希、裸模板结论、最小补丁、动态矩阵、默认/编辑态 OPJU、fresh-reopen 原生对象检查和人工视觉签名；历史45图通过记录不自动继承到新引擎。
- **PD-AC08 产品行为边界。** 导入、受控数据准备、明确选图/映射、自然语言与手动共同编辑、批量、项目上下文、任务恢复、PNG/SVG 与原生可编辑 OPJU 的产品目标保持；组合图由 PD-AF02 明确删除。
- **PD-AC09 Agent-native 动作层。** Agent 只生成少量强类型业务动作，由本地 resolver、validator、事务和任务编排执行；模型不得输出 renderer 参数、Origin 对象路径、脚本或自由 PlotSpec JSON。
- **PD-AC10 PlotSpec 保留语义真值。** PlotSpec 继续承担数据/字段/系列/轴/样式/标注/版本与来源的产品真值，但不保存 Matplotlib artist、Origin object ID、最终像素或页面几何，也不强迫两个后端共享最终布局。
- **PD-AC11 平坦 ChartProfile。** 每张正式图使用平坦 ChartProfile 登记字段角色、共同编辑能力、Matplotlib renderer、Origin 模板/绑定器和验证器；ChartProfile 不是 StructureUnit、ChartRecipe 或通用组件图。
- **PD-AC12 Matplotlib 每图独立。** Matplotlib 允许每图独立 renderer，并共享字体、色板、轴、图例、边界、导出等基础工具；不再要求所有图消费统一几何 RenderPlan 才能通过。
- **PD-AC13 公共能力取交集。** 正式 UI 和 Agent 只开放 Matplotlib 与 Origin 都能稳定表达、保存和读回的共同能力；任一后端不支持时返回 Unsupported，不静默忽略、近似替换或产生 target-only PlotSpec 状态。
- **PD-AC14 数据准备不转嫁用户。** 常规选择、类型、筛选、排序、reshape、聚合和登记派生列由强类型 `prepare_data` 生成可追溯 PreparedDataset；原始数据只读，科研计算独立显式，任意脚本与无法确定语义的加工仍需用户确认或外部处理。
- **PD-AC15 验收状态严格区分。** 测试执行、退出码为零、OPJU 可打开或 fresh-reopen 一致均不自动等于 PASS；只有预设判据和原始证据全部满足才 PASS，FAIL、BLOCKED、UNVERIFIED 分开记录，未实测不得由源码或单测推断。
- **PD-AC16 分层资格。** 新引擎依次通过契约冻结、正式图官方路线核查、双后端/动态/编辑、Agent与工作流、正式桌面与发布门禁；任一关键门禁有 FAIL/BLOCKED/UNVERIFIED 均不得宣称完整资格。
- **PD-AC17 Origin 编辑抽检口径。** 准入图全部自动修改数据值与代表性允许样式并在 fresh-reopen 后机械读回；人工实际编辑按官方模板哈希、原生结构和 T2 补丁签名划分的 Origin 模板家族选代表图，每家族至少一图。
- **PD-AC18 标签排版不作阻断。** 长标签、中文和多标签仍保存原始证据并校验文本内容、数据关联和字体，但标签裁切、换行、重叠等自动排版体验不作为本轮绘图引擎资格阻断；数据几何、轴语义、系列身份和原生对象错误仍是阻断项。
- **PD-AC19 视觉审查后置且一次性交付。** 先完成双后端、动态数据、共同编辑、OPJU/fresh-reopen和逐图机械修改读回，再统一生成审查页交由用户逐图判断。机械完成不自动产生视觉 PASS；历史视觉结论不得覆盖当前 renderer 变更。

当前34图映射与准入矩阵见 [Origin 官方模板映射](./ORIGIN-OFFICIAL-TEMPLATE-MAPPING.md)；完整多后端架构、Agent 动作与验收门禁见 [绘图引擎重构与验收基线](./PLOTTING-ENGINE-REFACTOR-ACCEPTANCE.md)。

## AD. Agent Native 引擎最终边界

- **PD-AD01 引擎是独立产品能力。** PlotAgent 的核心是可被任意 Agent 调用的本地绘图引擎；内置 Agent 只是一个可能适配更好的客户端，不是引擎组成部分。
- **PD-AD02 公共调用面。** 任意客户端通过能力目录、九类强类型 Engine Action、版本化目标和稳定错误接入；不得要求使用内置提示词、Provider 或别名绑定器。
- **PD-AD03 PlotDocument 取代 PlotSpec。** 绘图真值为不可变数据引用、字段绑定、Profile、线性 PlotDocument 版本与动作日志；旧 PlotSpec、resolver、共享最终 plan 和旧 Origin renderer 退出生产与存储。
- **PD-AD04 每图 backend。** 正式34图各自拥有 Matplotlib renderer 和 Origin 官方模板绑定器；可以共享基础工具，但不建立统一中间绘图语言或强制共享几何。已删除ID不得以旧 binder 或近似图元补位。
- **PD-AD05 模板优先。** Origin 默认态直接使用固定官方模板；Python只写数据、designation、必要动态绑定与用户明确动作，不全量重建模板对象。
- **PD-AD06 数据与编排保留。** 导入、SourceDataset、CAS、受控准备、ProjectContext、确认、部分失败与恢复执行保留，并改接 EngineDataView 和公共动作。
- **PD-AD07 旧存储不兼容回退。** 项目 schema v3 保留科研数据、项目和 Agent 运行时，移除旧绘图编译状态；不得以迁移兼容为由重新执行旧 renderer。
- **PD-AD08 完成定义。** 工程测试、机械读回、人工视觉和正式桌面黑盒分开记账；当前提交改变了若干 renderer/字段合同，必须重新取证，不能继承旧视觉结论。已删除ID只验证目录不可见和墓碑错误，不计入图形通过数。

## AE. 任务型对话、实时反馈与可撤销交互

- **PD-AE01 任务型聊天。** 主交互是连续任务对话，不是开放式陪聊或表单向导；聊天负责理解、追问、确认、执行与结果，结构化卡片负责精确选择和确认。
- **PD-AE02 缺少前置条件仍可对话。** 缺少数据、用户选择的图形类型或字段角色只阻止可执行计划，不阻止提交自然语言；Agent 在对话中提供上传、选图或字段选择入口。用户仍明确选图，Agent 不推荐、猜测或替换图形。同一模型请求运行期间串行化输入，切换上下文会废弃迟到响应。
- **PD-AE03 消息持久化。** 用户原文、Agent 理解、NeedsInput、Unsupported、失败、进度和完成均进入同一时间线；不得清空输入后丢失用户消息，也不得只用页面顶部通知表达任务结果。
- **PD-AE04 上下文可见。** Composer 常驻显示项目、数据文件/工作表、图形类型、PlotDocument/版本和作用对象/范围；当前使用可见控件切换上下文，`@` 项目对象引用后移，不依赖隐藏跨项目记忆。
- **PD-AE05 具体确认。** 有副作用的 Agent 计划必须在执行前展示目标对象/版本、角色→字段、全部变更、renderer 目标、警告、跳过与不支持项；泛化动作标题不能替代具体确认内容。
- **PD-AE06 真实阶段。** 进度文案只由 Agent/Core/TaskPlan/renderer 的真实事件驱动；不使用定时器伪造阶段、百分比或剩余时间。当前阶段可知后显示为单条状态；后续短阶段抑制不得隐藏长等待的真实阶段。
- **PD-AE07 克制动效。** 运行状态使用单个呼吸圆点和当前阶段文本，同一任务只更新一条状态消息；`prefers-reduced-motion` 下取消呼吸与位移但保留完整状态。
- **PD-AE08 停止与恢复。** 运行中提供停止；失败说明阶段、稳定原因、已完成结果和恢复动作；部分成功保留，局部重试不重做成功项，迟到旧响应不得覆盖新上下文。
- **PD-AE09 结果闭环。** 完成消息必须记录创建/修改对象、PlotDocument版本、renderer结果、警告，并提供打开、继续修改、导出、查看变更和撤销本轮。
- **PD-AE10 撤销与重做。** 能够从当前 PlotDocument 精确构造逆动作的 Agent 或手动编辑形成新版本；`Ctrl+Z`/`Ctrl+Shift+Z`与可见按钮提供会话内撤销/重做。撤销创建新的恢复版本，不删除历史；聚焦编辑只比较当前与直接父版本。
- **PD-AE11 撤销边界。** 当前通用撤销覆盖可逆的标题、坐标轴、系列样式、图例和图形参数；创建、字段重绑、标注、批量、数据导入、外部文件和PNG/SVG/OPJU不纳入通用撤销。任意历史、命名检查点、分支和持久化redo后移。
- **PD-AE12 后台任务。** 长任务离开当前对话后继续运行并在任务中心可见；重启恢复已提交结果，中断任务由用户明确决定是否继续。从任务项跳回原始消息和独立完成通知后移。
- **PD-AE13 本轮优先级。** P0覆盖上下文、具体确认、可恢复错误、停止/局部重试、结果闭环、缺少前置条件时仍可对话和真实阶段；P1覆盖最新版本恢复、相邻比较、可逆编辑撤销/重做、作用对象、多视图一致和后台任务。
- **PD-AE14 P2后移。** `Ctrl+K`上下文命令扩展、大规模快捷键、高级Composer、个性化提示和复杂工作区布局不进入本轮交互升级；未实现能力不得显示假入口。
- **PD-AE15 实施顺序。** 先修复“确认映射并绘图→Core拒绝”并完成重点图正式桌面冒烟，再实施P0/P1，随后重跑34图、编辑、撤销、导出、Origin重开和重启恢复黑盒；交互不得掩盖Core阻断。
- **PD-AE16 当前交付边界。** 已实现JSON集合契约兼容、可操作错误、项目/数据/图形上下文持久化、用户与Agent结果消息、具体确认、真实任务状态、多数据选择、可逆编辑撤销/重做和相邻版本比较。`@`引用、任意历史、命名检查点、持久化redo、任务跳回原消息和独立完成通知后移；正式Electron黑盒未观察到的能力不得记为PASS。

完整交互状态、文案、撤销边界与验收矩阵见 [任务型对话与交互验收契约](./CONVERSATIONAL-INTERACTION.md)。

## AF. Pi 运行时、34张单图与组合图删除（当前最终决定）

- **PD-AF01 正式34图。** 公开目录、Agent capability、字段映射、计算、Matplotlib、Origin/OPJU、批量、资格与发布声明统一为34张单图。精确清单以 `ORIGIN-OFFICIAL-TEMPLATE-MAPPING.md` 为准。
- **PD-AF02 删除组合图。** K25、Figure、组合候选篮、组合目标、组合 renderer、组合导出和组合验收均退出生产路径。旧项目只返回 `CHART_TYPE_REMOVED`；不得以隐藏按钮、旧 RPC 或近似图继续支持。
- **PD-AF03 Pi 接管通用循环。** Windows 主进程使用 Pi 处理 provider、对话循环和工具调用；Pi 是可替换适配层，不拥有项目、对象、权限、确认、版本、事务、执行和科研校验。
- **PD-AF04 Core 保持权威。** Pi 或其他外部 Agent 只能提交强类型 decision；PlotAgent Core 对 capability、字段、目标、版本、确认和副作用做最终校验。
- **PD-AF05 数据合同纠偏。** K06 使用绝对 X/Y 上下界，K07 使用中心/下界/上界，K18/K19/X38 支持重复系列，K21/X05按正式输入形状兼容，X40保留 Subject 与可选 Group 身份。
- **PD-AF06 证据重置。** 当前实现变化影响 K06、X13、X38、X40，旧35图视觉结论不能自动继承；这些图必须在当前提交重新视觉取证，相关黑盒失败图必须从正式 UI 重试。
- **PD-AF07 发布计数。** 34图 minimal/representative/edge × PNG/SVG/OPJU 为306个逻辑 MatrixKey；Origin representative live+fresh-reopen 为34份。K25只测试不可发现和墓碑，不计PASS分母。
- **PD-AF08 冲突处理。** PD-B03/B07、PD-C01/C08/C11、PD-E03/E08/E10—E12/E23/E25、PD-F02、PD-J08、PD-P14/P25、PD-AC01/08/16—19、PD-AD04/08、PD-AE11/15 中与35图、组合图或自研通用Agent runtime冲突的内容均由本节取代。

## AG. 多数据与显式异构批量（当前最终决定）

- **PD-AG01 图类必须显式。** 用户可以在图形库选择图类，也可以在自然语言中逐项点名图类；没有预选图时，明确的“数据→图类”指令可直接形成待确认计划。Agent 不推荐、猜测或替换图类。本条取代 PD-E01、PD-AB25 与 PD-AE02 中“必须先在图形库选图”或“一次任务只能一种图类”的冲突表述。
- **PD-AG02 异构批量。** 一个 Agent 任务可包含多个数据到不同图类的子任务；每项分别绑定数据、字段和图类，分别校验并保留部分成功。未明确图类或对象的子任务进入 `NeedsInput`，不得复用邻项答案。
- **PD-AG03 同类批量。** 多个完全同构数据使用同一图类时，仍共享一次字段映射和批次样式；字段集合、逻辑类型、单位、语义和映射必须一致，单项失败不回滚成功项。
- **PD-AG04 多数据同图。** 只对具有来源分组语义的散点、列散点、箱线、小提琴、面积、日期时间折线和蜂群图开放。用户显式选择 2–8 个数据表；系统验证同构后纵向拼接只读 Plot Data，并把可读数据来源登记为 `group`。不提供任意 join、字段对齐猜测、单位换算或组合图。
- **PD-AG05 Excel 与文本。** Excel 多工作表分别登记为可选数据表；TXT/CSV 的 InstrumentMetadata、DataBlock 与 postamble 分离，多个 block 分别登记。界面显示“文件名 > 工作表/数据块”和只读仪器元数据；元数据不会静默参与绘图。
- **PD-AG06 黑盒边界。** 资格至少覆盖：自然语言异构两项计划、同类两数据批量、受支持图类的两数据同图、非同构稳定拒绝、多 Sheet 可区分、仪器 TXT 元数据与多 block 可区分、部分失败不重做成功项。未经正式 Windows UI 实测的能力只记 `UNVERIFIED`。

完整W0–W10范围、依赖、spikes与M0–M7见 [实施拆分与里程碑计划](./IMPLEMENTATION-PLAN.md)；权威范围、Requirement/Evidence Matrix与冲突审计见 [规格索引与小规模 Beta 设计基线](./SPEC-INDEX.md)。
