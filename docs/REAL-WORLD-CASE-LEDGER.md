# 真实论文图案例台账

更新时间：2026-08-31
证据目录：`%USERPROFILE%\Desktop\实机演示`

本台账记录“当前是否适合实机复现和日更”，不等同于 34 个模板的实现状态。`已整理`只表示本地已有目标图和数据，不表示已经通过 fig-agent、Origin 或视频验收。

新增能力的立项证据必须落在本台账的具体文献面板上，并同时记录论文题名、期刊、DOI 或稳定 URL、图号、原始数据与产品失败证据。只有内部样例、合成图或功能设想时只登记为候选，不进入产品实现。

文献证据不会自动扩张产品范围。每条能力记录还必须同时列出 `in_scope`、`out_of_scope` 和裁决理由；未纳入项按明确产品边界管理，不写成没有证据的“未来全部支持”。

本台账中的能力候选必须执行[用真实论文任务决定新增能力边界](./REAL-WORLD-RESEARCH-FIGURE-ROADMAP.md#41-用真实论文任务决定新增能力边界开发强制约束)的开发门禁：每个目标元素只能归入“产品能力缺失、上下游契约错误、作者提供的数据不全、图形表达超出产品边界、操作或数据整理问题”五类之一。候选记录还必须包含目标插图、数据完整性、失败层、跨模板复用性、范围裁决及 Matplotlib/Origin 验收要求；字段不全时不得进入实现。该门禁只约束案例如何归因和能力如何立项，不增加路线目标、案例数量或完成条件。

## 新增能力候选强制记录格式

真实任务暴露的新需求必须先按目标元素填写以下记录；不得用整篇论文或整张复合图的一条笼统结论代替。记录不完整时只能保持“待补证据”，不能进入 Catalog、Agent 工具、编译器或 renderer 实现。

- **论文与目标插图**：论文题名、期刊、DOI 或稳定 URL、图号、目标元素和本地证据路径。
- **数据完整性**：逐项说明绘图数值、分组/系列映射、顺序、单位、误差或配对关系、派生量输入和方法参数是否齐全；缺失项不得用截图测量或合成数据补写成作者证据。
- **失败层与一级归因**：从 Agent、TaskIntent/TaskPlan、Catalog、编译器、数据处理、Matplotlib、Origin、验证器中定位失败层，并且只选择“产品能力缺失、上下游契约错误、作者提供的数据不全、图形表达超出产品边界、操作或数据整理问题”之一；同一面板有多类问题时拆成多条元素记录。
- **跨模板复用性**：列出可复用的稳定科研语义、适用模板和一个视觉相似但科学语义不同的反例；无法抽象时说明为何属于单篇特判。
- **范围裁决**：写明 `in_scope`、`out_of_scope`，并从“纳入、暂缓、明确不支持”中选择一项及理由。上下游契约错误另按 Bug 修复，受控数据整理另按数据能力处理，均不得冒充新增绘图能力。
- **双后端实现与验收**：分别写明 Matplotlib 和 Origin 的对象映射、可见结果、结构 readback、保存后重开要求；Origin 还必须说明是否能由稳定原生对象表达。任何一端未达到要求时不得宣称该能力跨后端可用。

建议采用以下单条记录骨架：

```text
候选编号 / 目标元素：
论文 / 图号 / 证据路径：
数据与方法完整性：
失败层 / 一级归因：
跨模板公共语义 / 反例：
in_scope / out_of_scope：
裁决（纳入 / 暂缓 / 明确不支持）及理由：
Matplotlib 实现与验收：
Origin 实现、readback 与 fresh-reopen 验收：
```

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
| X23 | 发酵过程三 Y 轴曲线 | 目标图、Source Data、整理数据、说明 | 红色、超出产品边界 | 目标图实际为左外侧乙酸线性轴、左内侧生物量对数轴、右侧衣康酸线性轴，共三个独立 Y 轴；当前 X23 只允许 `left + right` 两轴两系列。不得靠删系列或合并左轴冒充完整复刻，本参考图明确不纳入 |
| X35 | 薄膜开裂应变与模量双 Y 柱 | 目标图、Source Data、整理数据、说明、双后端默认/编辑产物与真实 OPJU | 黄色、部分视觉契约已验 | 5 个数字类别、左右柱、产品默认系列色、显式填充/边界样式以及左右轴标题、范围和颜色均已通过 fresh-reopen 与独立截图；零编辑轴色、自动上界和画布布局仍未裁决，不能把部分通过写成模板绿色 |
| X36 | 污水监测双 Y 柱线图 | 目标图、Source Data、整理数据、说明、双后端默认/编辑产物与真实 OPJU | 黄色、部分视觉契约已验 | 日期顺序、柱线几何、显式宽画布、绿色柱、蓝色无点虚线、黑色三侧轴、纵向日期和隐藏图例均通过 fresh-reopen；物理尺寸改变后的标题/轴标题自动避让、零编辑 marker/轴色/范围/布局仍开放。作者未公开可唯一恢复精确柱值的内部分类输出，只允许透明重计算演示；X36 只声明 Fig. 6B，不包含上方热图 |
| X40 | 神经元 SFC 前后配对图 | 目标图、Source Data、整理数据、说明、双后端默认/编辑产物、真实 OPJU 与独立 Origin64.exe 导出 | 黄色、部分视觉契约已验 | 身份标签显隐、数值身份列、两成员标记和逐行连接均通过真实 fresh-reopen；旧通用成员编辑会取消原生 GroupPlot 并删掉连接线，现已改用原生增量列表和真实 ConnectLine 读回。connector/column 目标范围和零编辑语义默认均已关闭；其余 Catalog 参数仍未逐项审计，因此不能升级为模板绿色 |
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
| RW-001 | X35/X36 | Profile 接受数字 `category`；首轮修复只用整数单测，真实 X35 审计中的 `0.0/10.0` 经 Origin 类别列重开后变成 `0/10`，仍被验证器判为不同 | 上游类型范围已对齐，但 numeric category 的稳定文本没有覆盖 Arrow/JSON 将整数提升为 integral float 的情况；这是标签规范化与 fresh readback 的契约错误，不需要 Agent `convert_type` | 已将有限浮点类别规范为稳定最短文本，新增 integral-float 回归；X35 真实 Source Data 的 5 类别、3 列、5 行经保存重开和独立导出通过。X36 真实案例使用日期文本，只能证明自己的 23 个日期类别，不能替代 numeric category 证据；X35 默认/编辑 OPJU SHA-256 分别为 `05CB37B66B0EF7548AE5A5DF4EE482F38768E2820C74CACA3FCEA473190236D4`、`3A5FE2C1FDA056D0E455361FC0E26A5BDFD7DF1FE21649E11D6AAE03575FF653` |
| RW-002 | 多数图类/X36 | 缺少可由自然语言稳定调用、两后端一致的页面宽高/宽高比 | 画布曾被误做成单模板私有参数；现已改为公共 `set_canvas` | 物理尺寸已实现并通过 Origin 实机读回。X36 真实 fresh-reopen 读回 `180.0098 × 80.01 mm`、宽高比 `2.24984`，但标题贴近上边框、X 轴标题侵入纵向日期区域；因此物理尺寸关闭，内容版式重排仍是独立开放契约 |
| RW-003 | 项目 208 / X35/X36 | 双 Y 轴边框/轴线颜色修改在预览或真实 OPJU 中未反映 | Matplotlib 的非归属 twinx spine 曾覆盖语义轴；Origin 又把 `y_right` 的侧相关样式写进第二层隐藏的 `y`，并从同一错误属性读回，真正可见右轴位于 `y2` | **已关闭显式动作链**：Matplotlib 主轴/孪生轴各自拥有左/右 spine；Origin 的右轴颜色、刻度色、字号、旋转和线宽等侧相关视觉属性改写/读回 `y2`。X36 用“蓝色右曲线 + 黑色右轴”的对照请求通过独立 fresh-reopen，排除系列色同色造成的假阳性；零编辑轴色仍单独开放 |
| RW-004 | 项目 208 / X35/X36 | Matplotlib 与 Origin 的系列/轴颜色未真正对应 | 产品蓝/橙系列默认已统一；X35 首次以“右系列绿色 + 右轴绿色”验收，无法区分 set_axis 是否生效，后来 X36 的“右系列蓝色 + 右轴黑色”暴露 Origin `y/y2` 错位和读回假阳性 | 显式合同现由 X36 独立对照关闭：两后端保留绿色柱、蓝色线，同时三侧轴为黑色；Origin 保存后重开可见。零编辑轴色策略仍开放，坚持轴色必须显式设置，不把 Origin 随系列着色的隐式级联包装成公共能力；证据见 `build/visual-audit/renderer-rereview-4/X36/` |
| RW-005 | 项目 210 / X40 | `label` 留空不能隐藏 Mouse/subject 标签 | 身份绑定和标签可见性被错误耦合 | 已新增 `identity_labels_visible`，保留 label 数据与绑定；真实 8 对 Fig. 5M 数据的双后端编辑态均隐藏身份文字，Origin worksheet 与分组结构仍保留，独立 `Origin64.exe` 导出通过 |
| RW-006 | 项目 210 / X40 | OPJU fresh-reopen 报第三列数值不一致 | `wide_series` 为绘制身份文字把数字格式化为字符串，Origin 保存后又按数值列读回；验证器错误地用显示字符串校验权威 worksheet，混淆了表示层与数据层 | 已分离契约：worksheet 写入和 fresh-reopen 期望都使用原始绑定值及类型，图上身份文字继续使用格式化字符串；真实 X40 OPJU 保持一张 worksheet、8 对配对值和独立 fresh-reopen，旧失败缓存继续保留为反例 |
| RW-007 | X40 资产目录 | 目录中混入名为 X35 的旧 OPJU | 案例资产缺少命名和归属校验 | 待清理确认 |
| RW-008 | K01/K02 离散 x 轴 | Profile 允许 `text/categorical` x，`grouped_xy` 却强制数值 | Profile—normalizer—Matplotlib—Origin 对离散 x 的声明不一致 | 已修复；K02 真实数据在 Matplotlib、Origin 原生对象和 fresh-reopen 中通过 |
| RW-009 | K02 / 公共画布 | 页面改为 180×100 mm 后尺寸正确，但 `inside_top_left` 图例实际附着页面，且默认字号导致裁切与遮挡 | Origin 把公共 inside 语义错误实现为 page attachment；物理尺寸与版式仍需分别验收 | 已修复图层附着；使用现有显式字号动作完成 v12 实机/fresh-reopen 验收 |
| RW-010 | K02 / 图形库预检 | 引擎已接受文本离散 X，图形库仍将 `text/text/numeric` 判为不兼容并禁用选择 | 前端维护了独立的硬编码数值列计数，且未把 `text` 纳入类别字段，违反 Profile 单一权威来源 | 已改为读取生成的 `role_field_types` 并做字段—角色可满足性匹配；真实 UI 与定向测试通过 |
| RW-011 | 编辑任务计划摘要 | 视觉编辑计划错误显示“0 个来源 · 字段绑定待补充” | 编辑动作本应继承目标图的数据和绑定，展示层误把空的新增来源解释为缺失 | 已改为“沿用原图数据与字段绑定”；定向 UI 测试通过 |
| RW-012 | X13 资产血缘 | 目录中的 `source_data.xlsx` 被误记为人口金字塔源数据 | 只按论文和附件名归档，未逐表核对目标面板与数据语义 | 已纠正文档并降为红色待资产；找到 Fig. 2b–e 正确人口数据前不进入产品预演 |
| RW-013 | X03 模板语义 | “Lollipop”名称相同，但产品实现和文献突变位点图的数据几何不同 | 选案例时按图名匹配，没有核对坐标语义、视觉元素和字段角色 | 已降为红色能力错配；后续需决定扩展 X03 变体还是新增突变位点模板 |
| RW-014 | X23 / Nature Communications 2022 Fig. 5 的轴基数 | 重新核对目标图可见坐标系后，确认它不是“左轴 2 条、右轴 1 条”，而是左外侧乙酸线性轴、左内侧生物量对数轴、右侧衣康酸线性轴，共三个独立 Y 轴；作者 Source Data 与无损整理数据完整，因此不能归因为数据不全 | 归类为“图形表达超出产品边界”，不是当前 X23 的普通多系列缺口。三轴布局、第三套刻度/标题、轴侧避让和跨轴系列寻址虽然可以抽象，但对现阶段 34 模板的收益不足，且会显著扩张 Agent、Catalog、Matplotlib 与 Origin 对象模型 | **明确不纳入**：保留 X23 的两轴两系列合同，换用真正的双 Y 轴参考图；不得删去乙酸、生物量或衣康酸后称为 Fig. 5 完整复刻。X23 现有合同的双后端审计独立记录在 `docs/visual-contracts/audit-ledger.json`，不因本论文不纳入而标记模板未完成 |
| RW-015 | S61 比例混淆矩阵 | 论文面板给出行归一化比例，当前 S61 只接受非负整数 `count` | 图类把矩阵统计量硬编码为计数，未声明 count / fraction / percent 及显示格式 | 已移出日更主链；后续扩展明确的矩阵值语义后再验收 |
| RW-016 | K04 NASICON Fig. 4b | `sigma` 是带置信标签的结构化字符串；目标还依赖参考线、注释与混合标记 | 已新增封闭的 `extract_mapping_fields` 并生成精确键存在性字段；`set_point_marker_map` 已关闭混合标记，数据坐标注释仍未覆盖 | 484 行真实源表双后端门禁通过，保持黄色升级案例；不删减剩余目标元素进入绿色库存 |
| RW-017 | K08 土壤金属迁移率 | 检索摘要和 `Fig1g` 表格形状像统计柱图，但论文面板实际是雷达图；更接近 K08 的 Fig. 4b/4d 又包含均值参考线和箭头注释 | 候选漏做“原图面板几何—数据字段—模板合同”三方核对；参考线合同已关闭，数据坐标箭头仍未覆盖 | Fig. 1g 保持红色错配，Fig. 4b/4d 保持黄色升级证据 |
| RW-018 | K09 Fig. 1c 候选审计 | 单个 Profile renderer 只消费结构动作，表面看像拒绝视觉编辑；完整调用链实际在 Matplotlib 保存钩子和 Origin worker 中统一应用 T1 视觉动作 | 审计必须沿实际编排链核对职责边界，不能只读一个 renderer 就判定契约矛盾 | 已纠正误判；K09 进入真实双后端预演，结果以可见产物和 fresh-reopen 为准 |
| RW-019 | K09 Origin 分组柱视觉语义 | `plot_gindexed` 生成一个原生 DataPlot 和多个语义子组，通用执行器曾把子组误当成独立 DataPlot；默认双层分类标签和原生线段图例也与论文语义不符 | “可寻址系列”不必等于“原生 DataPlot”；子组能力、分类标签表和图例样本必须有显式 native 映射及 fresh-reopen 读回 | 已修复并限制 K09 子组公开样式为 `fill_color`；fixed4 在独立重开后通过颜色、单层类别、无表格边框、图例色块和尺寸验证 |
| RW-020 | K09 / OriginPro 2024 SR1 刻度字号 | 首次产品 OPJU fresh-reopen 时 X 轴仍为 12 pt；执行器调用了 2024b 才引入的 `layer.axis.labeln.pt`，与明确支持的 2024 SR1 能力不一致 | 产品兼容声明、LabTalk 属性版本和 native readback 没有形成同一版本契约 | 已改用 OriginC Axis Format Tree 的 `Labels.<side>Labels.Font.Size`；真实 SR1 设置、保存、新鲜重开读回 9 pt，项目 213 v11 通过 |
| RW-021 | K09 / 产品对象选择 | 创建后已有 `@图1` 卡片，但旧实现把未带 `@` 的后续请求作为无目标的新建任务；“无 `@` = 新建”没有可见入口，也与用户对连续改图的理解冲突 | 可见对象、Composer 目标、TaskEnvelope `selected_plots` 和 Agent `task_kind` 没有同一状态机 | **已关闭**：已有当前图时 Composer 明示“默认编辑 `@图N · vM`”并发送精确 plot/version；`@图N` 覆盖默认；“新建图”显式打开图形库并发送空 `selected_plots`。Core 拒绝任何在已选 plot 上产生的 `create` intent。`src/renderer/src/App.test.tsx` 完整 103 项通过，Agent 定向合同见 `tests/desktop_core/test_agent_foundation.py::test_current_plot_context_preserves_bindings_for_data_update` |
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
| RW-035 | K15 / Nature Communications 2026 Fig. 1e | 官方 `Source_Data.xlsx > 1e` 提供 231 条 coverage 原始观测；正文给出均值 0.98、中位数 0.99，但未明示 bin start/width/count，作者公开仓库未找到该面板绘图代码 | 必须按元素拆分：精确复刻该面板的分箱属于“作者提供的数据不全（方法参数缺失）”；当用户显式给定固定分箱参数时，当前合同无法表达才属于独立的“产品能力缺失”候选，不能把两者合成一个产品结论 | 已无损提取并验证数值类型；当前自动合同为 35 个 FD bin，图像几何与 0.80–1.00、宽 0.005 的 40-bin 候选吻合但仍属推断。固定等宽分箱暂缓，等待与目标面板一一对应的文献证据；对数/非等宽、多组叠加、累计、KDE 和自动异常值裁剪明确不纳入本案例 |
| RW-036 | K15 / 固定分箱候选复核 | Nature Genetics 2025 相关代码直接调用 R 默认 `hist()`，属于当前已支持的 Sturges；MetaNeighbor 论文关联 vignette 使用 `breaks=20/10`，但未找到论文目标面板的精确绘图代码；sciPlex-ATAC Fig. 1e 也未给出可核对的分箱参数 | “论文或仓库里出现固定 bin”不足以证明目标面板需要同一合同；面板、数据和参数必须一一对应，当前一级归因为“作者提供的数据不全（方法证据缺失）” | 固定等宽分箱继续保持候选，不实现。拒绝把默认 Sturges、非目标 vignette 或截图测量当成立项证据；多分布叠加、KDE、累计和非等宽 bin 也不随候选一起纳入 |
| RW-037 | K13 / Nature Communications 2023 Fig. 3c | 官方 Source Data 提供 8 个基因型×处理组合、每组 7 个原始观测；论文明确箱体中心为中位数、边界为 Q1/Q3、须线为 1.5×IQR。目标还显示全部观测、二级分组和显著性字母 | 箱线统计语义已被现有 K13 覆盖；“同一批原始观测叠加到箱体”经元素级门禁裁决为产品缺口并已关闭。二级分组和显著性字母是两个独立问题，不能捆绑进前者 | `set_observation_overlay` 只消费原箱体 value 行，56/56 点、确定性 jitter、样式和对象读回通过 Matplotlib；Origin 独立进程 fresh-reopen 为 8×PID206 + 8×PID201，类别轴 0.5–8.5、图例与透明度持久化。证据见两个 `build/real-world-k13-observation-overlay*-20260830/run-metadata.json`；第二数据集、beeswarm/violin、配对线、显著性、二级轴分组和预计算箱线统计仍不纳入 |
| RW-038 | K03 / Nature Communications 2021 Fig. 2a | 旧 K03 目录中的 `source_data.xlsx` 实际属于另一篇 m6A 论文；重新冻结官方附件后，`Figure 2 Data` 的 A:B 与 E:F 分别提供无内含子/有内含子各 180 对归一化 X/Y，正文说明按实验均值归一化 | 这是先前候选的证据错配，不是作者数据缺口或 K03 能力失败。新候选只需 wide-to-long 无损整理；附带 `Lineage` Sheet 会触发逐表表头确认，属于已有导入交互而非绘图缺口 | 已独立创建 360 行可追溯工作簿；plain Matplotlib oracle 与 K03 v7 产品预览均重建两组几何、实心/空心圆、0–2.6 双轴和图例。OriginPro 2024 SR1 独立进程重开后读回 2 个原生序列、每列 180 行及全部动作，OPJU SHA-256 `A3F1944DAEA1935EE2049A396CCFA5524B112F6421FBB4A17EBC45444EA47984`。精确 marker 描边宽度未由作者指定且不是面板科学语义，不扩张合同；数据与独立 oracle 门禁已关闭，真实 Agent 和最终可见资格见 RW-039–RW-041。 |
| RW-039 | K03 / 真实 Agent 评分 | Agent 计划实际含两个轴、两组实心/空心黑色样式、图内左上图例和画布；`build/real-world-k03-fig2a-agent-20260830/run-metadata.json` 的旧评分却把这些项判为 false | 评分器把计划别名当作原生 target，并要求 Agent 重复写出 K03 默认 `marker_shape=circle`；它在检查语法形状而不是编译后的有效语义 | 以确认后的 typed actions 和最终任务状态为权威：`build/real-world-k03-fig2a-agent-execution-20260830/run-metadata.json` 为 `completed_verified`、v7、PNG/SVG/OPJU 均生成。旧 FAIL 保留为评估器反例，不再归因 Agent 能力 |
| RW-040 | K03 / Agent OPJU 跨后端标记 | 同一 typed plan 在 Matplotlib 为黑色实心/空心圆，首个 Origin OPJU 却为方形/实心圆且空心内部未形成白色可见语义 | Origin 官方 Scatter 模板会按组递增 symbol；renderer 未把公共 K03 默认物化到原生序列，且空心语义只写 interior 状态，没有把可见填充解析为白色 | 已在 K03 Origin 创建阶段解除组样式递增并统一 5 pt 圆形，空心有效填充解析为白色；r3 独立进程 fresh-reopen 读回 2 个圆形序列、180×4 数据和正确实心/空心状态，OPJU SHA-256 `C8B61A5150CF3F5103B67A767891F437469E034F21C03EBC71DC6E4482E230B2` |
| RW-041 | K03 / Origin 可见文本 | r3 在 `originpro`/COM 会话中重开同一 OPJU 时，轴标题、图例及新建普通文本上方均出现长横线；对象文本、Format Tree 和边框属性中没有对应 accent。退出 COM 后，由独立 `Origin64.exe` 打开同一文件导出的 PNG 无横线 | OriginLab 已确认 OriginPro 2024 SR1（10.1.0.178）对嵌入/OLE 图存在相同悬浮横线缺陷，并说明 2024b 修复。fig-agent 恰好使用外部自动化会话，因此旧 fresh PNG 是验证环境伪影，不是作者数据、产品文本合同或 OPJU 持久化缺陷 | 已关闭。结构读回继续使用 fresh COM 进程；可见 OPJU 验收必须在 COM 退出后使用独立 Origin 可执行程序。失败与成功对照、哈希和官方链接见 `build/real-world-k03-fig2a-agent-origin-fixed-20260830-r3/standalone-visual-readback.json`；通用门禁实现见 `scripts/origin_standalone_export.py` |
| RW-042 | K03 / 首次 OPJU 导出性能 | 真实 Agent v7 首次导出请求携带 `previous_opju=v6`，旧 Runtime 会先递归补齐 v1–v6；但 K03 binder 无论是否收到旧项目都会从不可变源数据和完整有效动作历史重新创建图 | `revision_materialization=previous_project` 与 renderer 实际重建策略矛盾，前六次 Origin 启动和模板构建不贡献最终状态 | K03 recipe 已与 K08 一样改为 `current_state`；Runtime 首次请求 vN 时只 stage 当前版本且 `previous_opju=None`。该结论只授予已审计的 K03/K08，其余 recipe 继续保留增量策略 |
| RW-043 | K09 / Nature Communications 2023 Fig. 1c 官方 Source Data 原表导入 | 官方 38-Sheet 工作簿的目标 `Figure 1c!A1:D8` 首列为空表头；其他面板还包含同名 X/Y 列、两行分组表头和空行分隔的多个表块。项目 217 因旧导入器要求整本工作簿每列单行且唯一，显示笼统 `The Core request failed` | 旧测试只覆盖人为规整工作簿，把“拒绝空/重复表头”误当安全边界；真实文献附件证明这些结构是正常科研数据表达。`in_scope`：Excel 空表头按列补名、重复表头按源列消歧、数字数据前的两行层级表头组合、空行明确分隔的表块分别导入；`out_of_scope`：任意文本行猜表头、跨 Sheet 语义合并、自动把宽表改成长表 | 已按源单元格位置确定性规范化并在 ImportRecipe/Trace 中记录；官方原表 SHA-256 `7FF406D586D34F2F40818C7FD3DA86956B4C305C6E5A262E7BE3F7CE095221AE` 只读验收为 39 个独立数据集，`Figure 1c` 首个数据集 7×4，ProjectStore 提交 39/39、对象校验通过；整理成长表仍是后续显式受控处理，不在导入阶段偷偷执行 |
| RW-044 | K01 / 用户实机折线图的默认颜色、反转轴侧与自动范围 | 同一数值数据在 Matplotlib 为产品蓝、5% 自动留白且 Y 轴保持物理左侧；Origin 旧产物为黑线、8% 留白，反转 X 后内部仍报告主 Y 轴/左标签，但独立 `Origin64.exe` 导出的画面把 Y 刻度和标题放在物理右侧 | 一级归因为“上下游契约错误”，不是新增能力：K01 Origin 创建阶段没有物化产品默认色和范围；验证器只检查 first/opposite 轴的逻辑属性，不检查主轴在横向尺度反转后的物理锚点。Origin 的默认主 Y 轴位置跟随 X 尺度 `From` 端，X 反转会把语义主 Y 轴带到画布右侧 | 已统一 K01 双后端产品蓝 `#1676D2` 和 5% 自动范围；Origin 在最终轴动作后按反转状态把主 Y/X 轴显式锚定到物理左/下对应的数据端点，并在 fresh-reopen 读回 `postype=2` 与位置。零编辑证据见 `build/real-world-k01-visual-contract-after-20260831-r2/`；反转 X 的双后端可见证据见 `build/real-world-k01-reversed-after-20260831-r3/`，Origin OPJU SHA-256 `9052565A1A2DD0A41ACD7B303327F4F0714A3DFB0BC3E1C98BE2288B8BE34BBB` |
| RW-045 | K09 / Nature Communications 2023 Fig. 1c 的柱边框与分组间距 | 论文目标图、官方 Source Data `Figure 1c!A1:D8` 及整理后的 7 类别×3 系列×21 数值均完整；目标图明确使用无黑色柱边框、可见组内间距和更大的组间间距。作者没有给出精确百分比，因此精确像素复刻不是本候选的承诺，用户显式设置值时则有唯一可验收语义 | 按元素拆分为两类：零编辑 Matplotlib/Origin 的边框、间距及已声明 `fill_color` 的默认色不同属于“上下游契约错误”；当前 Catalog 无法表达全图柱边框显隐、组内间距和组间间距，属于有真实任务证据的“产品能力缺失”。失败层为 Catalog、Agent/TaskPlan、Matplotlib 默认几何和 Origin T1 映射；不是 Origin/Python 限制，原生 PID203 已验证 `set -pbc -4`、`set -vg` 与 `layer.plot1.subsetgap` 可保存并 fresh-reopen | **已关闭最小公共语义**：K09 全图 `bar_border_visible`、`within_group_gap_percent`、`between_group_gap_percent` 已进入 Catalog、Agent 提示、双后端和验证器；模糊“柱间距”必须追问组内或组间。零编辑统一产品色、无边框及 20%/20% 间距；显式案例验证有边框及 40%/50%。**不纳入**：独立 `bar_width`、负间距/重叠、按子组设置边框，以及边框颜色/宽度/线型；一个原生 Indexed DataPlot 也不承诺这些子组级属性。Origin fresh-reopen 精确读回 `-pbc`、`-vg`、`subsetgap`，退出 COM 后独立 PNG 与 Matplotlib 均通过可见边框、色彩和间距检查；证据见 `build/real-world-k09-visual-contract-after-20260831-r3/contract-report.json`、`visible-geometry-report.json` 及两组 PNG。零编辑/显式 OPJU SHA-256 分别为 `02B3B76B177EBB50FCBBC68E8D1759171DD090BF99685DF69005BDD75C2C5E9E`、`887A7F649C1B909AC752C84367CEE0D96816AADC815E98F60B1B0177285B144D`；原生能力探针保留于 `build/real-world-k09-native-style-probe-20260831-r2/probe.json` |
| RW-046 | K06 / Catalog 驱动的零编辑与误差样式审计 | 当前源码重新生成时，旧审计夹具因仍使用 `x_lower/x_upper/lower/upper` 而被实时 K06 合同拒绝；修正为 `x_err_minus/x_err_plus/y_err_minus/y_err_plus` 后，零编辑 Matplotlib 为蓝色圆点、蓝色 X/Y 误差棒、隐藏图例，Origin 官方模板则为黑色方点、黑色误差棒、显示图例。一个公共 K06 语义系列在 Origin 内实际对应中心点图和 X±/Y± 四个误差对象 | 全部属于“上下游契约错误”，不是新增能力：审计夹具与 Catalog 漂移；产品默认只在 Matplotlib renderer 中物化；Origin `set_error_style` 只修改了第一个原生误差对象，却把单对象读回当成整组成功 | 已改为实时 Catalog 角色，审计脚本通过正式 Matplotlib backend 应用公共 T1；共享 K06 产品默认统一为 `#1676D2` 圆点、同色 1.25 pt 误差棒、4 pt 端帽、隐藏图例。Origin 对 `primary` 误差语义同时写入并 fresh-reopen 验证四个原生对象；显式 `#B42318`、1.75 pt、6 pt、0.7 在四对象均读回（Origin 宽度原生量化为 1.8）。当前画布比例、绘图区占比和自动留白仍未裁决，因此 K06 维持部分完成；证据及边界见 `docs/visual-contracts/audit-ledger.json` 与 `build/visual-audit/renderer-rereview-4/K06/`。默认/编辑 OPJU SHA-256 分别为 `1806A11099C72636E1D1D30B156FBF8A80E1579339302936D746060ECC41BC84`、`9B38BA5462BE0C818F3D7DFEC538944DE21DB2CA54AAAFDB3B6C6B98E19847E7` |
| RW-047 | K07 / Catalog 驱动的中心线与误差带审计 | 实时 Catalog 为 `primary` 公开中心线 `line_stroke_color/line_width_pt/line_style/line_opacity` 和误差带填充/边界参数。旧 Origin 路线把官方 PID 201 Scatter 的不可见 line 属性当作成功，并把通用 DataPlot 透明度/边框代理误当作 ErrorBar2D 的可见属性；审计案例构造器还曾静默漏掉 `line_opacity`。 | **上下游契约错误，代表项已修复**：Origin 现在显式开启中心连接、隐藏模板符号并应用线色/宽/型/透明度；带填充透明度通过原生 `Pattern.Transparency`，边界通过 ErrorBar2D 连接线颜色/宽度；Matplotlib 将透明度只施加于 face，避免连带稀释边界。双后端共用 X 与上下边界 5% 自动范围。 | 独立 Origin64 重开验证默认/编辑 OPJU 的一个图、一个工作簿、三原生图元、源数据、范围与全部代表视觉动作；默认范围为 X `-0.2..4.2`、Y `0.65..3.95`。编辑态主填充像素约为 Matplotlib `(251,221,169)` / Origin `(252,221,170)`，边界均为 `#B45309`，0.7 中心线主像素约为 `(138,95,144)` / `(140,96,145)`。默认/编辑 OPJU SHA-256 为 `A796C5A7974CECF2D49A732B1DD2EF7E31B3B240766ED48F2D1F3784CDC850F3`、`56C42E28C430B441231580251F477F73105DEF70C0CF34F778CDCDC00D941F78`；证据见 `build/visual-audit/renderer-rereview-4/K07/`。本轮不扩张能力面；原生布局允许差异，其余 Catalog 参数仍保持 partial。 |
| RW-048 | K14 / Nature Communications 2024 Fig. 5C 与 Catalog 驱动的小提琴图审计 | 论文目标、官方 Source Data 和 82,989 条事件的无损长表齐全；完整面板需要 `RNA × U1_C_nM` 双重分组、按 `State` 上下分面、log10 Y 轴、中位数/IQR 和 N 标签。当前 K14 仅声明 `value + 可选 group`，所以完整论文要求属于有真实任务证据的“产品能力缺失”，不是作者数据不全。对当前已声明能力的双组实产曾暴露默认色、中位数、字段标题和可见样式不一致；Origin 通用 `-pfb/-pbc` 实际写入 PID 206 的 `Patterns.Above`，读回成功但可见琴形由 `Patterns.Below` 与根 Line 绘制 | 两类问题分开管理：完整论文面板仍是待裁决的公共分布图能力候选；现有 K14 默认与样式映射属于“上下游契约错误”且已关闭。双后端现共用蓝/橙调色板、0.75 填充不透明度、黑色实线轮廓、隐藏中位数/图例、字段标题和 5% 数据范围；Origin 改写真实可见节点。`line_*` 与 `fill_stroke_*` 明确为同一轮廓的历史别名，组合时后者覆盖 | **现有能力已关闭，论文扩展仍暂缓纳入，保持黄色能力案例**：默认及代表编辑的颜色、透明度、轮廓色/宽/型、标题和图例均通过双后端实产、独立进程 fresh-reopen 与退出 COM 后 Origin64 单独导出；完整 Fig. 5C 的二级分组、分面、中位数/IQR 与 N 标签仍不宣称支持，也不为单篇论文增加专用五联模板。证据见 `build/visual-audit/renderer-rereview-4/K14/origin-default-independent.json`、`origin-edited-independent.json` 及对应 PNG；默认/编辑 OPJU SHA-256 分别为 `8F4694CAE63FC13F3ABDC9E1B5646D2A6C1CE38DBB888D36738E8AFBA748509E`、`ED4DDA6B125CCCE574AF0DB15FA259AD32ABC037C3D379AC1BA1254E8D44A724` |
| RW-049 | X40 / Nature Communications 2024 Fig. 5M/5P 的配对连接与成员样式 | 论文 Source Data 可唯一恢复 Before/After 数值和身份配对；旧代表编辑第一步修改 Before 标记时执行通用 `layer -gu`，把官方 PID 206 的依赖 GroupPlot 拆散，逐行 Connect Data Points 随即消失。普通 plot 线属性仍可读回，旧验证器因此把不可见连接线误报为成功 | 一级归因为“上下游契约错误”，不是新增能力：X40 已声明连接线和两列标记，但 Origin 后端把复合原生对象当作独立普通序列；同时旧 Catalog 只发布模板级 `set_series_style` 参数并集，不能说明 connector 只接受线属性、column_1/2 只接受标记属性 | **已关闭原生对象、可见链与目标级 Catalog**：成员样式改写 GroupPlot 的 Shape/Size/Interior/EdgeColor/FillColor 增量列表，连接线改写真正 `BoxChart.ConnectLine`；fresh-reopen 读回 `group_count=2`、`subgroup_size=2`、`ConnectbySubgroup=1` 和全部请求值。退出 COM 后独立 `Origin64.exe` 导出仍可见 8 条黑色配对线、灰色方形 Before、红色圆形 After且无身份文字。Catalog 现按 connector/column 发布目标级参数子集，错误组合在执行前拒绝。当前编辑态 OPJU SHA-256 `1FB30B73C3CC0482DC5771B5E231BB1AF203F1CE5DD935C7997F8EE787CB3623`；证据见 `build/visual-audit/renderer-rereview-4/X40/origin-edited-standalone.json`。显著性检验/括号/星号与论文多面板拼版不随本修复纳入 |
| RW-050 | X40 / 零编辑默认裁决 | 旧 Matplotlib 默认显示红/蓝圆点、图例、身份标签、`Series/Value` 标题和数据驱动范围；Origin 官方模板显示红/蓝圆点、无图例、身份标签、错误的 `Before SFC` Y 标题、9 pt 标记及 0..30 范围。同一数据因继承两套后端默认而表达不同 | 归类为“上下游契约错误”，不是新增能力；真实 Fig. 5M/5P 证明灰色 Before、红色 After、黑色配对线和隐藏身份标签是可复用的 X40 语义默认。论文单位不能从 `Before/After` 条件列可靠推断，因此默认 Y 标题保持中性 `Value`，不臆造 `ΔF/F (%)` | **零编辑默认已裁决**：双后端统一灰色 6 pt 方形 Before、红色 6 pt 圆形 After、黑色 1 pt 连接线、隐藏身份标签/图例/X 标题、`Value` Y 标题及数据跨度外扩 5% 的范围；默认 OPJU SHA-256 `562B1975931F2AFAC0A38517080B594D6C4C6C60B9BA6B13CD70FFE381E39384`。COM fresh 与独立 `Origin64.exe` 截图均无标签、图例和裁切。4:3 页面下的原生字体栅格化、刻度生成和绘图区占比允许不同；颜色、形状、显隐和数据范围不属于允许差异。证据见 `build/visual-audit/renderer-rereview-4/X40/` |

## 4. 第一轮真实数据导入审计

使用正式 `inspect_source` 读取本地演示 CSV，未对文件做预先改型：

- X35 `Z1_amount_wt_pct` 被识别为 `numeric`；这正是 RW-001 的真实回归输入。
- X36 `Week_start` 被识别为 `text`，两个系列为 `numeric`；23 周子集已完成双后端/fresh-reopen。作者未公开可唯一恢复精确柱值的内部 Crykey 分类输出，因此精确柱值归为作者数据不全，不新增绘图能力；公开原始数据的透明重计算系列仅用于趋势演示。
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
3. X35 已完成数字类别、左右柱、显式轴色/系列色和固定范围；X36 已用自身真实数据完成日期类别、180×80 mm/2.25 画布、柱线样式、黑色 `y2` 右轴和隐藏图例验收。两者零编辑默认和版式重排仍开放；下一步按各自视觉契约继续，不互相外推未审参数。
4. X40 的标签隐藏、数值身份列、原生两成员分组、逐行连接线、connector/column 目标范围和零编辑语义默认已通过真实 OPJU、fresh-reopen、独立 `Origin64.exe` 与执行前拒绝测试；下一步只按 Catalog 继续逐项审计未覆盖参数，不再把原生字体栅格化、刻度生成和绘图区占比差异反复当作未决功能。
5. Excel `EmptyCell`、K08 OPJU 递归物化和跨后端排版基线 v1 已修复；下一次产品导出核对真实耗时、10/9/8/8 pt fresh-reopen 与窄页可读性，密度碰撞仍单独设计。
6. 精确参考线、reference-line-bound callout、K04 结构化标量提取与逐点形状映射合同已关闭；K04 仍须关闭数据坐标注释，K08 Fig. 4 仍须走真实产品 UI 主链。任意 datum/free-coordinate annotation 没有纳入本切片，不能据此提前升级为绿色。
7. K15 固定等宽分箱在三组外部候选复核后仍缺少“目标面板—目标数据—明确参数”的闭环，继续不立项；K13 同源原始点叠加已完成机器合同、拒绝矩阵和双后端验收。下一能力必须重新经过元素级作者数据/方法/oracle 门禁，不从 K13 的相邻需求自动扩张。
8. K03 Fig. 2a 已通过作者证据、独立 oracle、真实 Agent 规划/确认/执行、Origin 原生标记读回和独立 `Origin64.exe` 视觉复验，成为第四个绿色库存。RW-041 的 COM 横线保留为验证器反例；marker 精确描边宽度等非必要像素控制继续不纳入。

## 7. 已形成的第一批证据

- RW-001：在 Profile—normalizer 与假后端测试之外，真实 X35 进一步暴露 integral float 标签的保存重开差异；规范化后 `0.0/10.0` 稳定为 `0/10`，真实 Origin worksheet、两层图、OPJU 和独立截图均通过。X36 只共享该标签修复，不共享视觉结论。
- RW-003/004：X35 的同色轴/系列截图曾无法排除 Origin 隐式级联；X36 随后用绿色柱、蓝色线、黑色三侧轴暴露并关闭 `y_right` 错写隐藏 `y`、验证器又读回同一错误属性的假阳性。右轴侧相关样式现统一写入/读回 `y2`，独立 `Origin64.exe` fresh PNG 可见黑色右轴且蓝线不变；证据见 `build/visual-audit/renderer-rereview-4/X36/`。默认态的 Matplotlib 黑轴与 Origin 随系列着色仍未裁决。
- RW-005：X40 以 `identity_labels_visible=false` 控制 Mouse/subject 身份文字，label 列、角色绑定和 Origin worksheet 身份数据仍保留；真实 Fig. 5M 受控数据的 Matplotlib 与 Origin 独立截图均无身份文字。
- RW-006：项目 210 的第三列失败由“显示标签字符串”错误校验“原始 worksheet 标量”导致。现由同一原始绑定列驱动 Origin 写入和 fresh-reopen 期望；真实 X40 OPJU 已保存一张原生 worksheet 和 8 对配对数据，旧失败缓存保留为反例。
- RW-049/050：X40 不能沿用通用“取消分组后逐 plot 编辑”的策略。代表编辑已改为原生 GroupPlot 增量列表和真实 ConnectLine，结构读回与独立 `Origin64.exe` 可见结果同时证明连接线未丢失；Catalog 现表达 connector/column 的目标级参数子集。零编辑语义默认也已统一，只有明确记录的原生排版差异允许保留。
- RW-026：只读 Excel 的普通空单元格不再读取 `.coordinate`；公式证据坐标由当前 sheet、枚举行列构造，稀疏行宽回归与相关导入套件通过。
- RW-028：项目 216 的缓存目录证明首次 v7 OPJU 在 14:36:57–14:38:16 间依次生成 v1–v7。K08 现声明 `revision_materialization=current_state`，Runtime 不再先补齐旧 native 版本；同一原始 v7 产品请求在当前版本只运行一个 12.77 s worker。该证据只授权 K08；K03 后续以 RW-042 独立审计，其余 recipe 不随之改变。
- RW-042：K03 worker 与 K08 同样只消费源数据和完整有效动作历史，从不打开 `previous_opju`；recipe 现声明 `current_state`，首次导出不再递归生成 v1–v6。其余 32 个未审计 recipe 仍保持 `previous_project`，不把一次审计外推为全局优化。
- RW-043：K09 官方附件来自 *One-stone-for-two-birds strategy to attain beyond 25% perovskite solar cells*（Nature Communications 14, 296；https://www.nature.com/articles/s41467-023-36229-1）。同一原表直接触发项目 217 失败；修复后正式 `inspect_source` 返回 39 个数据块，`Figure 1c!A1:D8` 保留 7 个类别、3 个能量列和两个真实零值，完整 ProjectStore 导入生成 40 个 CAS 对象并通过对象校验。空/重复/层级表头只做确定性命名，不承担 wide-to-long 或科学语义推断。
- RW-044：K01 的旧结构读回曾显示 `y.showLabels=1`、`y2.showlabel=0` 并错误判为左轴通过；独立可见 PNG 证明 X 反转后标签实际位于右侧。修复后 fresh-reopen 额外读回 `x.reverse=1`、主 Y 轴 `postype=2 / position=1500`、主 X 轴 `postype=2 / position=-10000`，并由独立 `Origin64.exe` 导出确认标签位于物理左/下。反转案例的 Origin 自动 X 范围为 `-100..1500`，不再出现旧 8% 留白导致的 `-200/1600` 额外刻度；Matplotlib 与 Origin 均保持降序 `1400..0` 和产品蓝。
- RW-027：产品默认排版不写入用户动作历史；Matplotlib backend 通过统一 rc fallback 解析 10/9/8/8 pt，Origin T1 后处理写入同一物理字号，并在显式 `set_title`/`set_axis`/`set_legend` 后按覆盖值 fresh-read。项目 216 原始 v7 请求已在当前版本真实重建；独立 Origin 进程读回 8 pt 刻度、9 pt 轴标题和完整 13 行，fresh PNG 已视觉检查。证据位于 `build/real-world-k08-fig2f-product-requalify-20260830/`。
- RW-029：`add_reference_line` 已贯通 Agent、Draft、编译器、Engine Action、30 个 Profile 和双后端。Matplotlib 以语义 ID 寻址 Line2D；Origin 使用官方轴 `refline#` 而不是 `addline` 图形对象。`build/release-matrix/reference-line-native-k04-k08-20260830/` 记录 K04/K08 36/36 PASS、0 FAIL，执行轨迹在 fresh-reopen 后分别读回精确值 `2.6` 和 `16.5`。
- RW-030：使用表格审计流程只读检查官方 `Fig4.xlsx`；Fig. 4b/4d 分别是 8×2 的类别—数值表，没有 annotation 坐标。源值均值与图中水平虚线一致，因此第一版 callout 绑定 `reference_line_id`，不从截图反推一个虚构的数据点。源文件 SHA-256、逐行值和计算结果冻结于 `build/real-world-k08-fig4-callout-audit-20260830/source-audit.json`。
- RW-031：Agent 选中图上下文已加入动态 `visual_objects`，只暴露当前动作历史中最新有效的参考线；领域知识与 Agent 上下文回归包含在本轮 181/181 定向套件中。该能力证明后续 turn 可以取得真实语义 ID，不等于已经完成一次真实模型产品对话。
- RW-032：`add_callout` 已在与参考线相同的 30 个 Profile 中公开，每个 Profile 声明 12 个可编辑参数；34 图机器合同现为 2,502 个公开 Profile—操作—参数三元组、2,497 组隔离 A/B，2,502 个焦点参数全部通过 Matplotlib 可见差异门禁。Origin 实机证据位于 `build/release-matrix/reference-line-callout-native-k08-20260830-r6/`：`run-metadata.json` 为 PASS，独立进程 fresh-reopen 读回 `end_style=1`，`fresh.png` 可见实心箭头，OPJU/PNG SHA-256 已冻结。该 K08 证据不冒充 30 图 Origin 全矩阵。
- RW-033：对 `source_data.xlsx > Fig. 4` 的 484 行真实 `sigma` 运行产品同一封闭数据程序，得到数值字段 484/484、置信字段 475/484、9 个显式缺失、86 个置信标签，以及存在性输出 475 个 `true`/9 个 `false`，数值范围 `1e-15..0.008212832236281`；源 SHA-256 为 `8CA7C25990848351723754D7387F4E9D5CD12587401EF0CC7EBD50440185DEDF`，门禁记录位于 `build/real-world-k04-structured-extraction-20260830/run-metadata.json`。最终 `color → sigma_value → 原始 sigma` 的绑定证据链有独立断言。
- RW-034：`set_point_marker_map` 已贯通 Agent、Draft、编译器、执行器、K04 Profile 和双后端。`build/real-world-k04-point-marker-product-gate-20260830/run-metadata.json` 冻结真实 484 行证据：Matplotlib 保持一个 `bubble_series`；Origin 创建与独立进程 fresh-reopen 均为一个 PID 201 DataPlot，shape modifier `103`、size modifier `101`、475 个圆形代码 `2`、9 个向下三角代码 `4`，颜色绑定 `Book2_D` 且自动刻度范围覆盖真实数值。可见 PNG 已人工检查；该证据不等于数据坐标注释或完整 K04 论文复刻通过。
- RW-002：`set_canvas` 已贯通 Engine Action、34 Profile capability、TaskDraft、编译器、执行器、Agent 提示、Matplotlib page 和 Origin GraphPage。K02 读回 `180.0098 × 99.9998 mm`/`1.8001`，X36 读回 `180.0098 × 80.01 mm`/`2.24984`；物理尺寸合同通过。X36 的标题贴顶与 X 标题侵入日期区再次证明尺寸变化不会自动得到合格版式，内容重排继续单独验收。
- RW-008：K01/K02 离散 x 会统一映射为源顺序位置；Matplotlib 在轴尺度后应用文字刻度，Origin 写入原文字并固定 categorical source order。受影响定向套件 62 项通过；K02 真实数据已在 Matplotlib 可见产物、Origin 四条原生 `line_symbol_series`、保存和 fresh-reopen 中复核。
- RW-009：保留 `origin_preflight_k02_canvas.png` 作为失败反例。Origin 官方 attachment 语义为 `0=Layer、1=Page、2=Axes`；原实现却给 `inside_*` 写入 `attach=1`，画布改变后必然漂移。现已改用 `attach=0` 与可 fresh-reopen 的原生 `left/top` 定位；再通过公共 `set_axis`/`set_legend` 将轴文字设为 8–10 pt、图例设为 7 pt。K02 v12 独立重开后的画面已通过人工复核，成功证据为 `origin_preflight_k02_final.*`。
- RW-010/011：项目 211 使用正式 `data_fig6b_k02.csv` 和已配置真实模型。图形库修复后允许 K02；首次计划准确绑定 `TimePoint → X、PercentOfTotalProtein → Y、Curve → 分组`，编辑计划准确生成 8 项显式视觉动作并执行到 v9。产品 UI 导出 `图1-K02-线点图-v9.png/.svg/.opju`，大小分别为 61,350 / 35,571 / 36,179 B，OPJU 经外部 Origin 生成与验证。完整记录见案例目录 `ui-preflight.md` 与 `video.md`。
- RW-019/020：项目 213 使用官方 Fig. 1c 无损长表。首次 OPJU fresh-reopen 暴露 2024b LabTalk 属性误用于 2024 SR1；改用 OriginC Axis Format Tree 后，v11 在真实 SR1 新鲜重开读回 X/Y 刻度 9 pt、标题 10 pt、三组颜色、分类表和 180×100 mm 页面。产品 UI 的 PNG/SVG/OPJU 大小为 26,625 / 36,186 / 47,096 B；完整记录见 K09 `ui-preflight.md`。
