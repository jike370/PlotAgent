# 真实论文图案例台账

更新时间：2026-08-31
证据目录：`C:\Users\pc\Desktop\实机演示`

本台账记录“当前是否适合实机复现和日更”，不等同于 34 个模板的实现状态。`已整理`只表示本地已有目标图和数据，不表示已经通过 fig-agent、Origin 或视频验收。

新增能力的立项证据必须落在本台账的具体文献面板上，并同时记录论文题名、期刊、DOI 或稳定 URL、图号、原始数据与产品失败证据。只有内部样例、合成图或功能设想时只登记为候选，不进入产品实现。

文献证据不会自动扩张产品范围。每条能力记录还必须同时列出 `in_scope`、`out_of_scope` 和裁决理由；未纳入项按明确产品边界管理，不写成没有证据的“未来全部支持”。

## 1. 当前资产概览

- 已建立 34 个模板目录。
- 本地已有实际文件的模板：K01、K02、K04、K08、K09、K13、K14、K15、K20、S61、X03、X13、X23、X35、X36、X39、X40。
- 其中候选清单明确标记“已整理”的模板：K14、K20、X03、X23、X35、X36、X40。
- 其余模板目前仍处于候选锁定、下载不完整或空目录状态。

## 2. 第一批分级

| 模板 | 论文场景 | 本地资产 | 当前级别 | 进入下一阶段前的检查 |
|---|---|---|---|---|
| K14 | U1 snRNP 结合状态停留时间小提琴图 | 目标图、源数据压缩包、整理数据、说明 | 黄色能力缺口 | 目标需要双重分组、上下分面及中位数/四分位区间；当前 K14 仅有 `value + 可选 group` |
| K20 | 测序质控指标热图 | 目标图、Source Data、整理数据、说明 | 黄色数据/能力缺口 | 宽矩阵需受控转为 `row/column/value`，并补齐行 z-score、双向聚类和缺失值策略 |
| X03 | 蛋白突变位点棒棒糖图 | 目标图、补充表、聚合数据、说明 | 红色能力错配 | 当前 X03 是类别间多数值连接图；文献图需要连续蛋白位置轴、突变棒高和位点文字标签，不能因同名而宣称可复刻 |
| X23 | 发酵过程双 Y 轴曲线 | 目标图、Source Data、整理数据、说明 | 红色合同缺口 | 论文为左轴 2 系列 + 右轴 1 系列，当前合同只允许 `left + right` 各一条；不能靠删系列冒充完整复刻 |
| X35 | 薄膜开裂应变与模量双 Y 柱 | 目标图、Source Data、整理数据、说明 | 黄色双后端待验 | 数字类别与 Matplotlib 左右边框归属已修复；仍需真实 OPJU 复核轴色/系列色一致性 |
| X36 | 污水监测双 Y 柱线图 | 目标图、Source Data、整理数据、说明 | 黄色双后端待验 | 数字类别、公共画布和 Matplotlib 左右边框归属已修复；仍需真实 OPJU 尺寸与轴色验收 |
| X40 | 神经元 SFC 前后配对图 | 目标图、Source Data、整理数据、说明 | 黄色 OPJU 待验 | 标签可见性已与身份绑定解耦；数值身份列的写入/显示/回读契约已分层并通过确定性验证，仍需项目 210 重新导出 OPJU 并实机 fresh-reopen 验收 |
| K01 | 磷酸化信号连续趋势线图 | 论文、目标图、Source Data、整理数据、说明 | 红色模板错配 / 内容重复 | Fig. 6b 主面板是带点标记的 4 系列图，右侧另有 2 个小面板；K01 会降级为单层纯折线，主面板已由 K02 严格覆盖，不重复制造退化案例 |
| K02 | 亚细胞组分磷酸化信号趋势 | 论文、目标图、Source Data、受控整理数据、提示词和三种导出均齐全 | 绿色日更库存 | 项目 211 已走通真实 UI 与真实模型：导入、K02 预检、Agent 规划/确认、自然语言改图、PNG/SVG/OPJU；宣发复用 `prompt.md` 和验收产物，不要求另写视频脚本 |
| K03 / Fig. 2a | 单细胞等位基因表达双组散点 | Nature Communications 2021 Fig. 2、官方 Source Data、360 行无损长表、独立 oracle、真实 Agent 计划/执行、Matplotlib 产品门禁、Origin 原生读回和独立可执行程序视觉复验 | 绿色日更库存 | Agent 已正确绑定并确认执行到 v7；首个评分 FAIL 是评估器假阴性，不是计划失败。原生标记递增和空心填充差异已修复；同一 OPJU 经结构读回为 1 个图页、1 个工作簿、2 个圆形散点序列和 `180×4` 列值。COM fresh PNG 的文本横线已确认为 OriginPro 2024 SR1 OLE/COM 渲染缺陷；退出 COM 后由独立 `Origin64.exe` 打开同一文件导出的 PNG 无横线。证据见 `build/real-world-k03-fig2a-agent-execution-20260830/` 与 `build/real-world-k03-fig2a-agent-origin-fixed-20260830-r3/standalone-visual-readback.json` |
| K04 | NASICON 成分—电导率颜色映射散点 | 目标图、官方 Source Data、审计说明、结构化提取及逐点形状双后端门禁 | 黄色能力缺口 | `sigma` 受控提取、参考线和 475 圆形/9 向下三角形混合标记已关闭；仍需数据坐标注释与最终论文版式，不省略这些元素冒充完整复刻 |
| K08 | 土壤金属迁移率图 | Fig. 1/4 目标图、官方 Source Data、审计说明 | 红色图类错配 / 黄色产品主链待验 | Fig. 1g 实为雷达图而非柱图；Fig. 4b/4d 所需的精确参考线及“指向参考线”的语义 callout 已完成双后端切片，但尚未走真实产品 UI 主链，任意数据点/自由坐标注释也仍明确不支持 |
| K08 / Fig. 2F | m6A 位点数—转录本比例单系列柱图 | Nature Communications Fig. 2、官方 Source Data、公式引用的受控整理工作簿、提示词、产品 v7 三种导出、当前双后端与 fresh-reopen 证据 | 绿色日更库存 | 项目 216 已走通真实 UI；其原始 v7 请求在当前代码下重新资格：Matplotlib 保留 13/13 类别，Origin 单次构建 12.77 s，独立进程读回 13 行、0–0.4/0.1、75×100 mm、8/9 pt 字号和请求颜色；宣发复用 `prompt.md` 和已通过产物 |
| K09 | 钙钛矿阳离子三类能量分组柱图 | Fig. 1 目标图、官方 Source Data、无损长表、提示词、双后端/fresh-reopen、产品 UI 三种导出与读回 | 绿色日更库存 | 项目 213 已走通真实 UI、Agent 规划/确认、显式 `@图1` 自然语言改图和 v11 PNG/SVG/OPJU；录制时保留纯文本化学式边界 |
| K13 | CEP/cytokinin 根长箱线图 | Nature Communications 2023 Fig. 3c、官方 Source Data、目标图、56 行无损整理工作簿和正式导入门禁 | 黄色、原始点切片双后端已关闭 | 中位数/Q1/Q3/1.5×IQR 与同源原始点叠加均已通过 Matplotlib 和 Origin fresh-reopen；基因型×处理二级分组及显著性字母仍分别裁决，不因原始点通过而宣称完整复刻 |
| K15 | 231 个 scATAC-seq 数据集的 cPeak coverage 直方图 | Nature Communications 2026 Fig. 1e、官方 Source Data、231 行无损整理工作簿和来源审计 | 黄色方法歧义 / 能力待裁决 | 原始观测足够且均值/中位数复核正文；目标等宽柱距与 0.005 候选高度吻合，但 Source Data 和作者公开仓库未给出绘图分箱代码。当前 K15 只支持自动 Freedman–Diaconis/Sturges。先补明确分箱文献或作者方法证据，再裁决是否纳入固定等宽分箱；不以截图反推参数直接立项 |
| S61 | 病毒感染性分类混淆矩阵 | 目标图、官方 Source Data、由高清图转录的 36 格矩阵、审计说明 | 红色运营/语义缺口 | 当前 `count` 合同不能准确表达行归一化比例；病原体上下文还会触发生物安全实时分类器，移出日更主演示候选 |
| X13 | 中国年龄—性别人口结构 | 目标图、非目标工作簿、说明 | 红色待资产 | 只读核对确认现有工作簿是家庭碳足迹数据，不含 Fig. 2b–e 年龄—性别人口结构；补齐正确源数据前不得用于复刻 |
| X39 | 癌症亚型多序列性能曲线 | 论文、目标图、说明；无完整数据 | 红色待资产 | 补齐 Source Data 和预期字段 |

当前有 4 个完成 Agent 产品主链、可直接录制的绿色库存案例 K02、K03 Fig. 2a、K08 Fig. 2F、K09。K14、K20 已经用真实数据暴露出合同和受控处理缺口，不为了日更硬凑成功演示。首周库存还需继续预检普通散点、简化箱线图和方法明确的直方图，不以 X35/X36/X40 作为保底。

## 3. 已知问题基线

| 编号 | 案例/项目 | 观察结果 | 契约缺口 | 状态 |
|---|---|---|---|---|
| RW-001 | X35/X36 | Profile 接受数字 `category`，normalizer 却要求 categorical/text | 上游接受范围与下游消费不一致；错误修复建议未形成自动动作 | 已修复；定向验证通过 |
| RW-002 | 多数图类/X36 | 缺少可由自然语言稳定调用、两后端一致的页面宽高/宽高比 | 画布曾被误做成单模板私有参数；现已改为公共 `set_canvas` | 物理尺寸已实现并通过 Origin 实机读回；画布变化后的版式重排仍是独立缺口 |
| RW-003 | 项目 208 / X35 | 双 Y 轴边框/轴线颜色修改未反映在实际预览 | `twinx()` 的两个 Axes 同时保留左右 spine，未使用的黑色副本覆盖语义轴线 | 已修复 Matplotlib 轴归属；X35/X36 artist 回归通过，待产品可见复核 |
| RW-004 | 项目 208 / X35 | Matplotlib 与 Origin 的系列/轴颜色未真正对应 | 双后端缺少统一显式颜色来源与读回断言 | Matplotlib 颜色/线宽/标题/刻度已固化；Origin 左右语义分别落到官方第一/末层的测试通过，真实 OPJU 视觉对应仍待验收 |
| RW-005 | 项目 210 / X40 | `label` 留空不能隐藏 Mouse/subject 标签 | 身份绑定和标签可见性被错误耦合 | 已新增 `identity_labels_visible`，保留 label 数据与绑定；领域知识、编排和双后端 70 项定向测试通过，待真实 OPJU 验收 |
| RW-006 | 项目 210 / X40 | OPJU fresh-reopen 报第三列数值不一致 | `wide_series` 为绘制身份文字把数字格式化为字符串，Origin 保存后又按数值列读回；验证器错误地用显示字符串校验权威 worksheet，混淆了表示层与数据层 | 已分离契约：worksheet 写入和 fresh-reopen 期望都使用原始绑定值及类型，图上身份文字继续使用格式化字符串；23 项 X03/X39/X40 定向测试通过，待项目 210 真实 OPJU 复验 |
| RW-007 | X40 资产目录 | 目录中混入名为 X35 的旧 OPJU | 案例资产缺少命名和归属校验 | 待清理确认 |
| RW-008 | K01/K02 离散 x 轴 | Profile 允许 `text/categorical` x，`grouped_xy` 却强制数值 | Profile—normalizer—Matplotlib—Origin 对离散 x 的声明不一致 | 已修复；K02 真实数据在 Matplotlib、Origin 原生对象和 fresh-reopen 中通过 |
| RW-009 | K02 / 公共画布 | 页面改为 180×100 mm 后尺寸正确，但 `inside_top_left` 图例实际附着页面，且默认字号导致裁切与遮挡 | Origin 把公共 inside 语义错误实现为 page attachment；物理尺寸与版式仍需分别验收 | 已修复图层附着；使用现有显式字号动作完成 v12 实机/fresh-reopen 验收 |
| RW-010 | K02 / 图形库预检 | 引擎已接受文本离散 X，图形库仍将 `text/text/numeric` 判为不兼容并禁用选择 | 前端维护了独立的硬编码数值列计数，且未把 `text` 纳入类别字段，违反 Profile 单一权威来源 | 已改为读取生成的 `role_field_types` 并做字段—角色可满足性匹配；真实 UI 与定向测试通过 |
| RW-011 | 编辑任务计划摘要 | 视觉编辑计划错误显示“0 个来源 · 字段绑定待补充” | 编辑动作本应继承目标图的数据和绑定，展示层误把空的新增来源解释为缺失 | 已改为“沿用原图数据与字段绑定”；定向 UI 测试通过 |
| RW-012 | X13 资产血缘 | 目录中的 `source_data.xlsx` 被误记为人口金字塔源数据 | 只按论文和附件名归档，未逐表核对目标面板与数据语义 | 已纠正文档并降为红色待资产；找到 Fig. 2b–e 正确人口数据前不进入产品预演 |
| RW-013 | X03 模板语义 | “Lollipop”名称相同，但产品实现和文献突变位点图的数据几何不同 | 选案例时按图名匹配，没有核对坐标语义、视觉元素和字段角色 | 已降为红色能力错配；后续需决定扩展 X03 变体还是新增突变位点模板 |
| RW-014 | X23 双轴系列基数 | 文献图需要左轴 2 条、右轴 1 条，产品 Profile 只声明单个 `left` 与 `right` | 双轴图按“两条曲线”样例设计，没有把每侧 1..N 系列作为合同维度 | 已阻止降级复刻；后续统一设计左右轴可重复角色、对象寻址和两后端读回 |
| RW-015 | S61 比例混淆矩阵 | 论文面板给出行归一化比例，当前 S61 只接受非负整数 `count` | 图类把矩阵统计量硬编码为计数，未声明 count / fraction / percent 及显示格式 | 已移出日更主链；后续扩展明确的矩阵值语义后再验收 |
| RW-016 | K04 NASICON Fig. 4b | `sigma` 是带置信标签的结构化字符串；目标还依赖参考线、注释与混合标记 | 已新增封闭的 `extract_mapping_fields` 并生成精确键存在性字段；`set_point_marker_map` 已关闭混合标记，数据坐标注释仍未覆盖 | 484 行真实源表双后端门禁通过，保持黄色升级案例；不删减剩余目标元素进入绿色库存 |
| RW-017 | K08 土壤金属迁移率 | 检索摘要和 `Fig1g` 表格形状像统计柱图，但论文面板实际是雷达图；更接近 K08 的 Fig. 4b/4d 又包含均值参考线和箭头注释 | 候选漏做“原图面板几何—数据字段—模板合同”三方核对；参考线合同已关闭，数据坐标箭头仍未覆盖 | Fig. 1g 保持红色错配，Fig. 4b/4d 保持黄色升级证据 |
| RW-018 | K09 Fig. 1c 候选审计 | 单个 Profile renderer 只消费结构动作，表面看像拒绝视觉编辑；完整调用链实际在 Matplotlib 保存钩子和 Origin worker 中统一应用 T1 视觉动作 | 审计必须沿实际编排链核对职责边界，不能只读一个 renderer 就判定契约矛盾 | 已纠正误判；K09 进入真实双后端预演，结果以可见产物和 fresh-reopen 为准 |
| RW-019 | K09 Origin 分组柱视觉语义 | `plot_gindexed` 生成一个原生 DataPlot 和多个语义子组，通用执行器曾把子组误当成独立 DataPlot；默认双层分类标签和原生线段图例也与论文语义不符 | “可寻址系列”不必等于“原生 DataPlot”；子组能力、分类标签表和图例样本必须有显式 native 映射及 fresh-reopen 读回 | 已修复并限制 K09 子组公开样式为 `fill_color`；fixed4 在独立重开后通过颜色、单层类别、无表格边框、图例色块和尺寸验证 |
| RW-020 | K09 / OriginPro 2024 SR1 刻度字号 | 首次产品 OPJU fresh-reopen 时 X 轴仍为 12 pt；执行器调用了 2024b 才引入的 `layer.axis.labeln.pt`，与明确支持的 2024 SR1 能力不一致 | 产品兼容声明、LabTalk 属性版本和 native readback 没有形成同一版本契约 | 已改用 OriginC Axis Format Tree 的 `Labels.<side>Labels.Font.Size`；真实 SR1 设置、保存、新鲜重开读回 9 pt，项目 213 v11 通过 |
| RW-021 | K09 / 产品对象选择 | 创建后已有 `@图1` 卡片，但 `selected_plot` 为空；不显式引用对象的编辑请求失败，进入“编辑图形”再返回后才建立选择 | 可见对象、编辑器选择状态和 Agent 默认目标三者没有同一状态机 | 已记录；当前日更脚本显式使用 `@图1`，后续修复创建后自动选择及持久恢复 |
| RW-022 | K09 / OPJU 重试计时 | 首次 OPJU 失败后重试显示沿用旧尝试的十余分钟耗时，实际成功 worker 约 8.7 秒 | 任务重试沿用了旧 attempt 的计时展示状态 | 已记录为 UX 缺口；不影响产物，后续给每次尝试独立开始时间和终态 |
| RW-023 | K01 / Fig. 6b 候选 | 同一目标图被候选表同时分配给 K01 与 K02；K01 会丢点标记且无法表达右侧小面板 | 内容库存按模板名称配图，没有先做目标面板几何和既有案例去重 | K01 候选降为红色；保留已通过的 K02 主面板，不为覆盖数字制造退化复刻 |
| RW-024 | K03 / Fig. 2B 候选 | 论文称 scatterplot，但可见几何为二维六边形密度图并带边缘直方图 | 候选检索按图注名词匹配，没有检查实际 mark、统计变换和多视图结构 | K03 候选降为红色；同一 Fig. 2F 精确数据改映射 K08，进入绿色候选 |
| RW-025 | K08 / 多表 Excel 表头复核 | `Raw Source` 的表头确认曾被错误复用到 `Data` 和 `Lineage`，可能把每张表的真实表头当成数据 | 表头歧义选项只携带行号，导入器把一次人工确认解释成整个工作簿的全局决定 | 已把选择值编码为 `sheet + line` 并逐表应用；项目 216 的 `Data` 表在正式 UI 中读到正确的 13×2 与字段名，定向导入测试通过 |
| RW-026 | K08 / Excel 尾部空单元格 | 第一行尾部存在 openpyxl `EmptyCell` 时，表头诊断访问不存在的 `coordinate` 并中断导入 | 诊断代码假设所有只读单元格都是带坐标的普通 Cell，未覆盖工作簿行宽不齐的真实输入 | 已修复：仅公式证据生成坐标，并由枚举行列安全构造；稀疏只读工作簿回归通过 |
| RW-027 | K08 / 75×100 mm Origin OPJU | 产品预览字号正常；旧 v7 OPJU 冷启动重开后轴标题和 90° 类别刻度异常巨大、拥挤并越出窄页 | 公共画布只规范了页面尺寸；当 Agent 未显式生成字号动作时，Matplotlib 默认值与 Origin 官方模板默认值没有统一的产品级排版基线 | 已关闭：项目 216 原始 v7 请求在当前代码下重建，独立 Origin 进程读回 8 pt 刻度、9 pt 轴标题和 75.0062×99.9998 mm 页面；1600 px fresh PNG 视觉检查无裁切或重叠。证据见 `build/real-world-k08-fig2f-product-requalify-20260830/run-metadata.json` |
| RW-028 | K08 / OPJU 产品导出 | 首次导出 v7 长时间停留在“正在生成并验证 OPJU”，容易被判断为卡死 | Origin 懒物化默认递归补齐 v1–v7；缓存时间戳显示七次独立 Origin 启动耗时约 79 秒，而 K08 renderer 每次都从源数据与完整动作历史重建，前六次不贡献最终状态 | 已关闭引擎主因：同一项目 v7 请求在当前 `current_state` recipe 下只启动一次 worker，12.77 s 生成 OPJU；另一独立进程 17.08 s 完成重开、读回和 PNG 导出。UI 计时展示仍按通用任务 UX 独立管理，不再阻塞本案例 |
| RW-029 | K04/K08 / Origin 参考线 | 首版 `add_reference_line` 在预览正确，但 OPJU fresh-reopen 后 `2.6 → 2.599435…`、`16.5 → 16.485562…` | Origin `addline` 创建的是经页面像素持久化的 Straight Line 图形对象；它不满足科研阈值必须保持精确轴值的语义合同 | 已改用官方 `layer.axis.refline#` 轴对象；30 个 Profile 公开，K04/K08 36 个自动 Origin 连续版本全部通过并精确读回 |
| RW-030 | K08 Fig. 4b/4d / 箭头说明 | 目标图有指向均值线的箭头和文字，但官方工作簿只含 8 个国家类别与柱值，没有箭头坐标或被指向的数据点 | 若仅按画面外观设计通用 `(x,y)` 箭头，会把“解释参考线”的语义错误包装成 datum annotation，并再次产生类别坐标、双 Y 目标和后端坐标系矛盾 | 已将首个公共切片收窄并实现为 reference-line-bound callout；Fig. 4b/4d 均值经源表复核为 16.26640875 / 0.70573625，通用 datum/free-coordinate 变体继续保持未支持 |
| RW-031 | Agent 连续编辑 / 语义对象寻址 | 创建参考线后，后续自然语言编辑若只看到 Profile 静态对象，无法取得运行时 `reference_line_id`，即使引擎已有 callout 也不能可靠规划目标 | Profile capability 只能声明“可以做什么”，不能替代当前图中“已经存在什么”；静态对象目录与动态视觉对象曾被混为一层 | `selected_plot_contexts.visual_objects` 现暴露最新有效参考线的语义 ID、轴目标、数值、标签和样式，重复 ID 按最新动作折叠；Agent 可在后续 turn 绑定真实目标而不是猜 ID |
| RW-032 | K08 / Origin reference-line callout | Matplotlib 标注可用 axes fraction；Origin 图形对象保存后会把文本/箭头端点经页面像素重新序列化，且 LabTalk `arrowEndShape` 不能证明实际端点样式 | 不能用 Matplotlib 坐标假设或 LabTalk 表面属性冒充 OPJU 原生合同；必须分别验证精确参考线语义、图形对象 attachment、端点格式和 fresh-reopen 可见产物 | 已使用 OriginC `ATTACH_TO_SCALE` 原生线对象、Data.X/Y 向量和 Format Tree 端点样式；K08 独立进程 fresh-reopen 读回实心箭头并导出一致 PNG。参考线值仍精确为 16.5；图形端点只承诺归一化轴空间 5e-4 内的 Origin 亚像素序列化误差 |
| RW-033 | K04 / 结构化 `sigma` | 475 行包含 `value + confidence_level`，另 9 行只含 `value`；这 9 行又与目标图的三角形点一一对应 | 旧流程只能把整列当 text，若用正则或 `eval` 临时拆值会丢可选置信信息、类型约束和字段血缘 | 已实现 `extract_mapping_fields`：全部键必须显式声明，未知键、重复键、嵌套值、非有限数值和隐式字符串转数值均稳定失败；真实 484 行得到 484 个数值、475 个置信标签、9 个显式缺失，以及 475/9 的键存在性布尔输出 |
| RW-034 | K04 / 按点混合标记 | 统一 `marker_shape` 只能覆盖整个系列；若按置信状态拆成伪系列，会破坏原生气泡尺寸、连续颜色和单一系列身份 | 过去没有“字段值 → 点形状”的跨 Agent/编译器/双后端合同，也没有检查映射穷尽性、动作顺序和 rebind 失效 | 已实现只向 K04 公开的 `set_point_marker_map`；真实 484 行在 Matplotlib 单一 `PathCollection` 与 Origin 单一 PID 201 DataPlot 上得到 475 圆形/9 向下三角形，保留 size `101`、shape `103`、worksheet D 颜色绑定并通过独立进程 fresh-reopen |
| RW-035 | K15 / Nature Communications 2026 Fig. 1e | 官方 `Source_Data.xlsx > 1e` 提供 231 条 coverage 原始观测；正文给出均值 0.98、中位数 0.99，但未明示 bin start/width/count，作者公开仓库未找到该面板绘图代码 | 主体数据充分；精确分箱属于作者方法缺口。产品同时只有自动 FD/Sturges、不能在用户明确给参时设置固定等宽分箱，因此是混合问题，不能只归因产品 | 已无损提取并验证数值类型；当前自动合同为 35 个 FD bin，图像几何与 0.80–1.00、宽 0.005 的 40-bin 候选吻合但仍属推断。固定等宽分箱暂列候选；对数/非等宽、多组叠加、累计、KDE 和自动异常值裁剪明确不纳入本案例 |
| RW-036 | K15 / 固定分箱候选复核 | Nature Genetics 2025 相关代码直接调用 R 默认 `hist()`，属于当前已支持的 Sturges；MetaNeighbor 论文关联 vignette 使用 `breaks=20/10`，但未找到论文目标面板的精确绘图代码；sciPlex-ATAC Fig. 1e 也未给出可核对的分箱参数 | “论文或仓库里出现固定 bin”不足以证明目标面板需要同一合同；面板、数据和参数必须一一对应，否则仍是作者方法缺口 | 固定等宽分箱继续保持候选，不实现。拒绝把默认 Sturges、非目标 vignette 或截图测量当成立项证据；多分布叠加、KDE、累计和非等宽 bin 也不随候选一起纳入 |
| RW-037 | K13 / Nature Communications 2023 Fig. 3c | 官方 Source Data 提供 8 个基因型×处理组合、每组 7 个原始观测；论文明确箱体中心为中位数、边界为 Q1/Q3、须线为 1.5×IQR。目标还显示全部观测、二级分组和显著性字母 | 箱线统计语义已被现有 K13 覆盖；“同一批原始观测叠加到箱体”经元素级门禁裁决为产品缺口并已关闭。二级分组和显著性字母是两个独立问题，不能捆绑进前者 | `set_observation_overlay` 只消费原箱体 value 行，56/56 点、确定性 jitter、样式和对象读回通过 Matplotlib；Origin 独立进程 fresh-reopen 为 8×PID206 + 8×PID201，类别轴 0.5–8.5、图例与透明度持久化。证据见两个 `build/real-world-k13-observation-overlay*-20260830/run-metadata.json`；第二数据集、beeswarm/violin、配对线、显著性、二级轴分组和预计算箱线统计仍不纳入 |
| RW-038 | K03 / Nature Communications 2021 Fig. 2a | 旧 K03 目录中的 `source_data.xlsx` 实际属于另一篇 m6A 论文；重新冻结官方附件后，`Figure 2 Data` 的 A:B 与 E:F 分别提供无内含子/有内含子各 180 对归一化 X/Y，正文说明按实验均值归一化 | 这是先前候选的证据错配，不是作者数据缺口或 K03 能力失败。新候选只需 wide-to-long 无损整理；附带 `Lineage` Sheet 会触发逐表表头确认，属于已有导入交互而非绘图缺口 | 已独立创建 360 行可追溯工作簿；plain Matplotlib oracle 与 K03 v7 产品预览均重建两组几何、实心/空心圆、0–2.6 双轴和图例。OriginPro 2024 SR1 独立进程重开后读回 2 个原生序列、每列 180 行及全部动作，OPJU SHA-256 `A3F1944DAEA1935EE2049A396CCFA5524B112F6421FBB4A17EBC45444EA47984`。精确 marker 描边宽度未由作者指定且不是面板科学语义，不扩张合同；数据与独立 oracle 门禁已关闭，真实 Agent 和最终可见资格见 RW-039–RW-041。 |
| RW-039 | K03 / 真实 Agent 评分 | Agent 计划实际含两个轴、两组实心/空心黑色样式、图内左上图例和画布；`build/real-world-k03-fig2a-agent-20260830/run-metadata.json` 的旧评分却把这些项判为 false | 评分器把计划别名当作原生 target，并要求 Agent 重复写出 K03 默认 `marker_shape=circle`；它在检查语法形状而不是编译后的有效语义 | 以确认后的 typed actions 和最终任务状态为权威：`build/real-world-k03-fig2a-agent-execution-20260830/run-metadata.json` 为 `completed_verified`、v7、PNG/SVG/OPJU 均生成。旧 FAIL 保留为评估器反例，不再归因 Agent 能力 |
| RW-040 | K03 / Agent OPJU 跨后端标记 | 同一 typed plan 在 Matplotlib 为黑色实心/空心圆，首个 Origin OPJU 却为方形/实心圆且空心内部未形成白色可见语义 | Origin 官方 Scatter 模板会按组递增 symbol；renderer 未把公共 K03 默认物化到原生序列，且空心语义只写 interior 状态，没有把可见填充解析为白色 | 已在 K03 Origin 创建阶段解除组样式递增并统一 5 pt 圆形，空心有效填充解析为白色；r3 独立进程 fresh-reopen 读回 2 个圆形序列、180×4 数据和正确实心/空心状态，OPJU SHA-256 `C8B61A5150CF3F5103B67A767891F437469E034F21C03EBC71DC6E4482E230B2` |
| RW-041 | K03 / Origin 可见文本 | r3 在 `originpro`/COM 会话中重开同一 OPJU 时，轴标题、图例及新建普通文本上方均出现长横线；对象文本、Format Tree 和边框属性中没有对应 accent。退出 COM 后，由独立 `Origin64.exe` 打开同一文件导出的 PNG 无横线 | OriginLab 已确认 OriginPro 2024 SR1（10.1.0.178）对嵌入/OLE 图存在相同悬浮横线缺陷，并说明 2024b 修复。fig-agent 恰好使用外部自动化会话，因此旧 fresh PNG 是验证环境伪影，不是作者数据、产品文本合同或 OPJU 持久化缺陷 | 已关闭。结构读回继续使用 fresh COM 进程；可见 OPJU 验收必须在 COM 退出后使用独立 Origin 可执行程序。失败与成功对照、哈希和官方链接见 `build/real-world-k03-fig2a-agent-origin-fixed-20260830-r3/standalone-visual-readback.json`；通用门禁实现见 `scripts/origin_standalone_export.py` |
| RW-042 | K03 / 首次 OPJU 导出性能 | 真实 Agent v7 首次导出请求携带 `previous_opju=v6`，旧 Runtime 会先递归补齐 v1–v6；但 K03 binder 无论是否收到旧项目都会从不可变源数据和完整有效动作历史重新创建图 | `revision_materialization=previous_project` 与 renderer 实际重建策略矛盾，前六次 Origin 启动和模板构建不贡献最终状态 | K03 recipe 已与 K08 一样改为 `current_state`；Runtime 首次请求 vN 时只 stage 当前版本且 `previous_opju=None`。该结论只授予已审计的 K03/K08，其余 recipe 继续保留增量策略 |
| RW-043 | K09 / Nature Communications 2023 Fig. 1c 官方 Source Data 原表导入 | 官方 38-Sheet 工作簿的目标 `Figure 1c!A1:D8` 首列为空表头；其他面板还包含同名 X/Y 列、两行分组表头和空行分隔的多个表块。项目 217 因旧导入器要求整本工作簿每列单行且唯一，显示笼统 `The Core request failed` | 旧测试只覆盖人为规整工作簿，把“拒绝空/重复表头”误当安全边界；真实文献附件证明这些结构是正常科研数据表达。`in_scope`：Excel 空表头按列补名、重复表头按源列消歧、数字数据前的两行层级表头组合、空行明确分隔的表块分别导入；`out_of_scope`：任意文本行猜表头、跨 Sheet 语义合并、自动把宽表改成长表 | 已按源单元格位置确定性规范化并在 ImportRecipe/Trace 中记录；官方原表 SHA-256 `7FF406D586D34F2F40818C7FD3DA86956B4C305C6E5A262E7BE3F7CE095221AE` 只读验收为 39 个独立数据集，`Figure 1c` 首个数据集 7×4，ProjectStore 提交 39/39、对象校验通过；整理成长表仍是后续显式受控处理，不在导入阶段偷偷执行 |

## 4. 第一轮真实数据导入审计

使用正式 `inspect_source` 读取本地演示 CSV，未对文件做预先改型：

- X35 `Z1_amount_wt_pct` 被识别为 `numeric`；这正是 RW-001 的真实回归输入。
- X36 `Week_start` 当前被识别为 `text`，两个数值系列被识别为 `numeric`；其当前阻塞点不是导入类型，而是数据周序列完整性、公共画布和双后端呈现。
- K14 被识别为 82,989 行、4 列：`RNA/text`、`State/text`、`U1_C_nM/numeric`、`Dwell_time_s/numeric`。导入正常，但复刻需要同时消费两个分组维度和分面语义，超出现有 K14 合同。
- K20 被识别为 32 行、10 列：`Metrics/text + A1–A9/numeric`，缺失值保留。导入正常，但现有 K20 要求长表 `row/column/value`，且未声明行 z-score、双向聚类和缺失值处理。
- K02 新候选从同一论文 Fig. 6b 真实数据中保留 FR2/FR6 与 40S/60S，组合为四个 `Curve`；正式导入器识别为 `TimePoint/text`、`Curve/text`、`PercentOfTotalProtein/numeric`，20 行、无缺失。
- K13 Fig. 3c 从官方工作簿的 8 个相对根长数据行无损展开为 56 行：`genotype/text`、`treatment/text`、`group_label/text`、`root_length_relative_pct/numeric` 及血缘列。正式导入器保留 56/56 行、0 缺失，未把绝对长度误当相对百分比。
- K03 Fig. 2a 的官方 `Figure 2 Data` 中，A:B 与 E:F 各有 180 对完整数值。受控整理只做 wide-to-long，得到 `Allele 1 Signal/numeric`、`Allele 2 Signal/numeric`、`Condition/text` 共 360 行；原 K03 目录同名附件与目标论文不一致，已保留原件并把新候选隔离到独立子目录。

X35 的修复口径是“`category` 角色将数字值作为离散显示标签”，不是把源列转换成 categorical，也不是要求 Agent 执行 `convert_type`。

## 5. 每个案例的验收状态

后续每个案例按下列状态顺序推进：

`候选 → 资产齐全 → 数据已整理 → Matplotlib 通过 → Origin 通过 → fresh-reopen 通过 → Agent 自然语言通过 → 宣发实机预演 → 已发布`

任何状态只能由相应证据推进，不从“代码存在”或“模板已实现”推断。失败案例保留实际输出和原因，不覆盖为成功结果。

## 6. 下一批动作

1. 将 K14、K20 保留为真实任务驱动的产品升级案例，不进入当前日更库存。
2. K02、K03 Fig. 2a、K08 Fig. 2F、K09 已进入绿色日更库存；K08 的绿色只授予 Fig. 2F，不外推到仍为红色错配的 Fig. 1g 或仍待产品主链的 Fig. 4b/4d。K13 原始点叠加已关闭，但二级分组与显著性字母仍未关闭，所以仍不进入完整复刻的绿色库存。继续预检普通线图、散点、箱线图和直方图，优先补足 7 个可直接录制案例。
3. X35/X36 数字类别与 Matplotlib 双轴边框 artist 回归已通过；下一步仅以真实项目 208 OPJU fresh-reopen 关闭 Origin 轴色/系列色对应边界。
4. X40 标签隐藏及数值身份列的表示/数据分层合同已建立；下一步用项目 210 重新导出并验收产品可见标签隐藏与真实 OPJU fresh-reopen。
5. Excel `EmptyCell`、K08 OPJU 递归物化和跨后端排版基线 v1 已修复；下一次产品导出核对真实耗时、10/9/8/8 pt fresh-reopen 与窄页可读性，密度碰撞仍单独设计。
6. 精确参考线、reference-line-bound callout、K04 结构化标量提取与逐点形状映射合同已关闭；K04 仍须关闭数据坐标注释，K08 Fig. 4 仍须走真实产品 UI 主链。任意 datum/free-coordinate annotation 没有纳入本切片，不能据此提前升级为绿色。
7. K15 固定等宽分箱在三组外部候选复核后仍缺少“目标面板—目标数据—明确参数”的闭环，继续不立项；K13 同源原始点叠加已完成机器合同、拒绝矩阵和双后端验收。下一能力必须重新经过元素级作者数据/方法/oracle 门禁，不从 K13 的相邻需求自动扩张。
8. K03 Fig. 2a 已通过作者证据、独立 oracle、真实 Agent 规划/确认/执行、Origin 原生标记读回和独立 `Origin64.exe` 视觉复验，成为第四个绿色库存。RW-041 的 COM 横线保留为验证器反例；marker 精确描边宽度等非必要像素控制继续不纳入。

## 7. 已形成的第一批证据

- RW-001：Profile—normalizer 一致性、Matplotlib renderer 和 Origin 假后端均覆盖数字类别；受影响定向套件通过。
- RW-003/004：X35/X36 在 Matplotlib 中明确由主轴拥有左 spine、孪生轴拥有右 spine，并隐藏两个非语义副本；左右轴线颜色、线宽、标题及刻度 artist 均有断言。Origin 定向测试证明 `y_left` 与 `y_right` 分别写入官方第一层和末层；未把该单元证据冒充真实 OPJU 视觉通过。
- RW-005：X40 以 `identity_labels_visible=false` 控制 Mouse/subject 身份文字，label 列、角色绑定和 Origin worksheet 身份数据仍保留；领域知识、TaskDraft 编译、Matplotlib 与 Origin 定向套件合计 70 项通过。
- RW-006：项目 210 的第三列失败由“显示标签字符串”错误校验“原始 worksheet 标量”导致。现由同一原始绑定列驱动 Origin 写入和 fresh-reopen 期望，数字 `1/2/3/4` 在 worksheet 中保持数值，图上仍显示文字；X03/X39/X40 定向套件 23 项通过。旧失败缓存保留为反例，未将确定性测试冒充真实 OPJU 通过。
- RW-026：只读 Excel 的普通空单元格不再读取 `.coordinate`；公式证据坐标由当前 sheet、枚举行列构造，稀疏行宽回归与相关导入套件通过。
- RW-028：项目 216 的缓存目录证明首次 v7 OPJU 在 14:36:57–14:38:16 间依次生成 v1–v7。K08 现声明 `revision_materialization=current_state`，Runtime 不再先补齐旧 native 版本；同一原始 v7 产品请求在当前版本只运行一个 12.77 s worker。该证据只授权 K08；K03 后续以 RW-042 独立审计，其余 recipe 不随之改变。
- RW-042：K03 worker 与 K08 同样只消费源数据和完整有效动作历史，从不打开 `previous_opju`；recipe 现声明 `current_state`，首次导出不再递归生成 v1–v6。其余 32 个未审计 recipe 仍保持 `previous_project`，不把一次审计外推为全局优化。
- RW-043：K09 官方附件来自 *One-stone-for-two-birds strategy to attain beyond 25% perovskite solar cells*（Nature Communications 14, 296；https://www.nature.com/articles/s41467-023-36229-1）。同一原表直接触发项目 217 失败；修复后正式 `inspect_source` 返回 39 个数据块，`Figure 1c!A1:D8` 保留 7 个类别、3 个能量列和两个真实零值，完整 ProjectStore 导入生成 40 个 CAS 对象并通过对象校验。空/重复/层级表头只做确定性命名，不承担 wide-to-long 或科学语义推断。
- RW-027：产品默认排版不写入用户动作历史；Matplotlib backend 通过统一 rc fallback 解析 10/9/8/8 pt，Origin T1 后处理写入同一物理字号，并在显式 `set_title`/`set_axis`/`set_legend` 后按覆盖值 fresh-read。项目 216 原始 v7 请求已在当前版本真实重建；独立 Origin 进程读回 8 pt 刻度、9 pt 轴标题和完整 13 行，fresh PNG 已视觉检查。证据位于 `build/real-world-k08-fig2f-product-requalify-20260830/`。
- RW-029：`add_reference_line` 已贯通 Agent、Draft、编译器、Engine Action、30 个 Profile 和双后端。Matplotlib 以语义 ID 寻址 Line2D；Origin 使用官方轴 `refline#` 而不是 `addline` 图形对象。`build/release-matrix/reference-line-native-k04-k08-20260830/` 记录 K04/K08 36/36 PASS、0 FAIL，执行轨迹在 fresh-reopen 后分别读回精确值 `2.6` 和 `16.5`。
- RW-030：使用表格审计流程只读检查官方 `Fig4.xlsx`；Fig. 4b/4d 分别是 8×2 的类别—数值表，没有 annotation 坐标。源值均值与图中水平虚线一致，因此第一版 callout 绑定 `reference_line_id`，不从截图反推一个虚构的数据点。源文件 SHA-256、逐行值和计算结果冻结于 `build/real-world-k08-fig4-callout-audit-20260830/source-audit.json`。
- RW-031：Agent 选中图上下文已加入动态 `visual_objects`，只暴露当前动作历史中最新有效的参考线；领域知识与 Agent 上下文回归包含在本轮 181/181 定向套件中。该能力证明后续 turn 可以取得真实语义 ID，不等于已经完成一次真实模型产品对话。
- RW-032：`add_callout` 已在与参考线相同的 30 个 Profile 中公开，每个 Profile 声明 12 个可编辑参数；34 图机器合同现为 2,502 个公开 Profile—操作—参数三元组、2,497 组隔离 A/B，2,502 个焦点参数全部通过 Matplotlib 可见差异门禁。Origin 实机证据位于 `build/release-matrix/reference-line-callout-native-k08-20260830-r6/`：`run-metadata.json` 为 PASS，独立进程 fresh-reopen 读回 `end_style=1`，`fresh.png` 可见实心箭头，OPJU/PNG SHA-256 已冻结。该 K08 证据不冒充 30 图 Origin 全矩阵。
- RW-033：对 `source_data.xlsx > Fig. 4` 的 484 行真实 `sigma` 运行产品同一封闭数据程序，得到数值字段 484/484、置信字段 475/484、9 个显式缺失、86 个置信标签，以及存在性输出 475 个 `true`/9 个 `false`，数值范围 `1e-15..0.008212832236281`；源 SHA-256 为 `8CA7C25990848351723754D7387F4E9D5CD12587401EF0CC7EBD50440185DEDF`，门禁记录位于 `build/real-world-k04-structured-extraction-20260830/run-metadata.json`。最终 `color → sigma_value → 原始 sigma` 的绑定证据链有独立断言。
- RW-034：`set_point_marker_map` 已贯通 Agent、Draft、编译器、执行器、K04 Profile 和双后端。`build/real-world-k04-point-marker-product-gate-20260830/run-metadata.json` 冻结真实 484 行证据：Matplotlib 保持一个 `bubble_series`；Origin 创建与独立进程 fresh-reopen 均为一个 PID 201 DataPlot，shape modifier `103`、size modifier `101`、475 个圆形代码 `2`、9 个向下三角代码 `4`，颜色绑定 `Book2_D` 且自动刻度范围覆盖真实数值。可见 PNG 已人工检查；该证据不等于数据坐标注释或完整 K04 论文复刻通过。
- RW-002：`set_canvas` 已贯通 Engine Action、34 Profile capability、TaskDraft、编译器、执行器、Agent 提示、Matplotlib page 和 Origin GraphPage。K02 v9 在独立 Origin 进程 fresh-reopen 后读回 `180.0098 × 99.9998 mm`，宽高比 `1.8001`；物理尺寸合同通过。该输出同时证明尺寸变化不会自动得到合格版式，因此不把 RW-009 记为通过。
- RW-008：K01/K02 离散 x 会统一映射为源顺序位置；Matplotlib 在轴尺度后应用文字刻度，Origin 写入原文字并固定 categorical source order。受影响定向套件 62 项通过；K02 真实数据已在 Matplotlib 可见产物、Origin 四条原生 `line_symbol_series`、保存和 fresh-reopen 中复核。
- RW-009：保留 `origin_preflight_k02_canvas.png` 作为失败反例。Origin 官方 attachment 语义为 `0=Layer、1=Page、2=Axes`；原实现却给 `inside_*` 写入 `attach=1`，画布改变后必然漂移。现已改用 `attach=0` 与可 fresh-reopen 的原生 `left/top` 定位；再通过公共 `set_axis`/`set_legend` 将轴文字设为 8–10 pt、图例设为 7 pt。K02 v12 独立重开后的画面已通过人工复核，成功证据为 `origin_preflight_k02_final.*`。
- RW-010/011：项目 211 使用正式 `data_fig6b_k02.csv` 和已配置真实模型。图形库修复后允许 K02；首次计划准确绑定 `TimePoint → X、PercentOfTotalProtein → Y、Curve → 分组`，编辑计划准确生成 8 项显式视觉动作并执行到 v9。产品 UI 导出 `图1-K02-线点图-v9.png/.svg/.opju`，大小分别为 61,350 / 35,571 / 36,179 B，OPJU 经外部 Origin 生成与验证。完整记录见案例目录 `ui-preflight.md` 与 `video.md`。
- RW-019/020：项目 213 使用官方 Fig. 1c 无损长表。首次 OPJU fresh-reopen 暴露 2024b LabTalk 属性误用于 2024 SR1；改用 OriginC Axis Format Tree 后，v11 在真实 SR1 新鲜重开读回 X/Y 刻度 9 pt、标题 10 pt、三组颜色、分类表和 180×100 mm 页面。产品 UI 的 PNG/SVG/OPJU 大小为 26,625 / 36,186 / 47,096 B；完整记录见 K09 `ui-preflight.md`。
