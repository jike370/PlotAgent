# PlotAgent 科研图形库调研

> 版本：2026-08-05  
> 访问日期：所有网络来源均于 2026-08-05 访问  
> 范围：A）本地独立参考素材 `C:\Users\pc\Desktop\No.1-128\fig`；B）OriginLab 官方 Graph Gallery、文档、模板与文件能力；C）各学科头部期刊、出版社图稿规范、权威报告规范与代表性论文；D）邀请制内测的发表规格/期刊样式模板。  
> 约束：本报告不修改 `PRODUCT.md` 或产品代码；本地素材只读。用户必须明确选择或指定图形，因此本文不设计 Agent 主动推荐图形的路径。
> 当前产品边界：本文是长期 taxonomy 与研究输入，不是 v1 准入清单。v1 以 [产品决策基线](./PRODUCT-DECISIONS.md) 和 [PRD](./PRD.md) 为准：31 项纯数值图表、无图像/地图、无通用 Transform/Analysis/Fit；分析型图只接受规定的预计算字段，固定绘图计算仅限封闭 PlotCalculationSpec。本文出现的图像面板、Analysis Template、拟合或统计建议不得被实现为 v1 承诺。

## 1. 摘要与产品结论

PlotAgent 不应把“科研图形库”收缩成十几种商业 BI 图，也不应把 Origin Graph Gallery 中每一张示例图当成一个独立、内置的 Origin 类型。三条证据线应先独立解释，再在统一的“图形族—数据形状—语义参数”模型下归并。

核心结论如下。

1. **完整库需要四层，而不是小规模 MVP 清单。** 建议覆盖约百个去重后的图形族/专业变体，分为“核心高频、扩展常用、学科专用、进阶分析”。核心层仍需包含多面板组合、误差与原始点、热图/二维场、图像面板等科研高频能力，而不只是折线、柱和饼。
2. **图形名不足以定义能力。** KM 曲线需要删失与风险人数，森林图需要效应量和区间，地图需要 CRS，EIS 需要复阻抗与频率，XRD/NMR 有领域坐标惯例，单细胞 dot plot 同时编码表达比例与平均表达。产品模型必须保存这些语义字段。
3. **组合图是核心能力。** 头部期刊论文经常在一个 figure 中组合示意图、显微/遥感图、统计估计、谱图与模型结果。共享图例、统一面板标签、栏宽、字号、混合矢量—位图导出不应放到很后面的“高级美化”。
4. **PNG、SVG、OPJU 是三种不同承诺。** PNG 是发布栅格；普通 2D 图可输出真矢量 SVG；`.opju` 是保存数据、图层、分析和项目状态的 Origin 原生项目，不是把 PNG/SVG 改后缀即可得到的图片格式。真正可编辑 OPJU 需要可用的 Origin 运行时或自动化接口。
5. **批量绘制的前提是结构同构。** Origin 官方 Batch Plotting 明确要求相似数据结构。统计分析派生图、聚类图、网络/流图和复杂多面板更适合 Cloneable Template 或 Analysis Template，必须标为“条件批量”，不能一律写“支持”。
6. **默认安全比图形数量更重要。** 3D 饼/柱、rainbow/jet、未定义误差棒的均值柱、任意双 Y 轴、无实测点的平滑曲面、只给 ROC 的不平衡分类评估等不应成为默认模板。
7. **图形选择库应支持主动浏览与精确检索。** 用户通过中英文名、别名、数据形状、学科、坐标系、分析语义和导出能力定位图形。系统只做兼容性校验，不替用户选择另一种图。
8. **发表规格是带版本的约束配置，不是纯视觉主题。** 栏宽、成品高度、字体、线宽、色彩空间、有效 DPI、矢量保真和组合图标注需要在最终成品尺寸上校验；期刊规则变化时应更新配置并保留来源快照。用户明确选择目标期刊/刊群后系统才应用该规格，不由 Agent 猜测投稿目标。

## 2. 研究方法、证据边界与术语

### 2.1 三条彼此独立的证据线

| 证据线 | 研究对象 | 能证明什么 | 不能直接证明什么 |
|---|---|---|---|
| A 本地独立参考素材 | `C:\Users\pc\Desktop\No.1-128\fig` 中的实际文件 | 素材实际包含哪些图、视觉变体和学科主题 | 不能因为视觉相似就断言来自 Origin；不能外推为所有学科的频率 |
| B OriginLab 官方 | Graph Gallery、Appendix 2、数据要求、模板、批量、导出和文件类型文档 | Origin 当前或官方展示过的图形能力、输入结构与文件边界 | Gallery 示例不等于全部为内置菜单图；“能做”不等于“无需 App/脚本” |
| C 期刊与规范 | 头部/代表性期刊的官方指南、权威报告规范、代表性论文 | 各学科反复出现的图形任务、图稿要求和误导风险 | 不是逐篇计量学统计，不能声称是严格的全球频率排名 |

“一区”会随 JCR/SJR 年份、数据库和学科分类变化。本文不把某期刊永久标注为一区，而采用各领域公认的头部/代表性期刊、出版社官方作者指南和学术组织规范作为证据。正文中的“常见”表示在抽样的规范与头部期刊论文中反复出现，并由至少一种领域规范或多篇代表性论文交叉支持。

### 2.2 数据形状词汇

| 代码 | 含义 | 例子 |
|---|---|---|
| `Y` | 一列数值，x 可为行号 | 直方图、ECDF |
| `XY` | 自变量与响应 | 散点、折线、回归 |
| `XYY` | 共享 X 的多系列 Y | 多曲线、谱图、瀑布 |
| `XYZ` | 不规则点或三变量 | 等高线、3D 散点、三维表面前的插值 |
| `matrix/grid` | 规则二维网格或矩阵 | 热图、图像、场图 |
| `long` | 观测行 + 值列 + 分组/分面列 | 箱线、小提琴、分面 |
| `wide` | 行为观测、列为变量/条件 | 相关矩阵、配对比较 |
| `interval` | 中心/起止或下限—上限 | 误差棒、森林、甘特 |
| `event` | 时间、事件、删失、组别 | KM、累计发生、可靠性 |
| `edge list` | source、target、weight | 网络、Sankey、Chord |
| `hierarchy` | id、parent、value | Sunburst、树、圆形打包 |
| `geo` | 几何/经纬度 + CRS + 属性 | 地图、轨迹、栅格场 |
| `image/volume` | 像素/体素 + 通道 + 标尺/ROI | 显微、病理、遥感 |

### 2.3 表格代码

- 产品层级：`K` 核心高频；`X` 扩展常用；`S` 学科专用；`A` 进阶分析。
- 优先级：`P0` 第一批完整交付；`P1` 紧随核心；`P2` 按学科包交付；`P3` 低频或依赖复杂分析链。
- 批量/组合：`✓` 结构稳定时直接支持；`△` 依赖同构数据、模板、分析链或人工布局；`—` 不宜承诺通用批量。组合列中的 `层` 表示可叠加图层，`面` 表示多面板，`独` 表示通常独立使用。
- 导出按 `PNG / SVG / OPJU` 记录。`原` 表示 Origin 原生可编辑对象；`组` 表示可用 Origin 多层、模板、App 或脚本组合为可编辑项目；`嵌` 表示只能可靠地嵌入图像/矢量，不能承诺恢复为数据驱动的 Origin plot。`SVG△` 表示含栅格面板或 OpenGL 3D 的栅格嵌入。

## 3. 证据线 A：本地独立参考素材集

> 本节仅针对用户指定的 `C:\Users\pc\Desktop\No.1-128\fig`。未查看或枚举父目录的其他内容；不把该素材标注为 Origin。

### 3.1 素材性质与精确统计

该目录是一个用于微信传播的科研图表模板宣传素材集：31 张统一版式 JPEG，每页 4 个图表卡片，带 `sci_shop` 斜向水印、微信二维码和“科研小卷王 原创出品”署名。可见图表编号连续为 `#1–#124`，没有 `#125–#128`。它不是底层图形工程、原始数据集或干净图稿，无法从 JPEG 判定由 Origin、Prism、R 或其他软件生成。

| 项目 | 结果 |
|---|---|
| 子目录 / 文件 | 0 / 31，全部 `.jpg` |
| 总大小 | 7,815,531 bytes（7.453 MiB） |
| 平均 / 中位 | 252,113.9 / 267,562 bytes |
| 最小 / 最大 | 192,627 / 305,839 bytes |
| 像素 | 24 张 1080×1443；2 张 1080×1444；1 张 1080×1445；4 张 1280×1711 |
| 色彩 / DPI | 全部 24-bit RGB；标称 96×96 dpi |
| 编号完整性 | 文件序号 1–31 连续；图卡编号 #1–#124 连续 |
| 重复与元数据 | SHA-256 无完全重复；无相机、方向、软件或拍摄时间等可用 EXIF |
| 修改时间 | 31 项均为 2026-08-05 02:32:39 |

机械盘点覆盖 31/31 文件；视觉核验按原始像素覆盖 31/31 页面和 124/124 个可见图卡。特别核验了首尾页、序号 27→28 的分辨率变化、高密度 UMAP/热图、WB 图像与定量组合、KM/ROC/RCS/森林/火山/GO 等分析图，以及双 Y 轴、堆积、华夫饼和甜甜圈等高风险形式。

### 3.2 逐文件可见图形清单

下表记录 JPEG 中实际可见的标题，不把营销样式名自动视为独立图形语法。

| 相对路径 | Bytes / 像素 | 可见图形 |
|---|---:|---|
| `微信图片_20260805023113_1_104.jpg` | 268,504 / 1080×1443 | #1 生存曲线；#2 百分比堆积柱状图；#3 散点箱线图；#4 散点折线图 |
| `微信图片_20260805023114_2_104.jpg` | 276,893 / 1080×1443 | #5 分段折线图；#6 相关性热图；#7 趋势折线图；#8 带误差棒堆积柱状图 |
| `微信图片_20260805023115_3_104.jpg` | 256,266 / 1080×1443 | #9 小提琴图；#10 热图；#11 哑铃图；#12 带散点多组柱状图 |
| `微信图片_20260805023115_4_104.jpg` | 277,968 / 1080×1443 | #13 多组带可信区间散点图；#14 双向误差棒散点折线图；#15 彩色森林图；#16 堆叠柱状图 |
| `微信图片_20260805023116_5_104.jpg` | 278,217 / 1080×1443 | #17 火山图；#18 混淆矩阵；#19 富集分析棒棒糖图；#20 剂量效应曲线 |
| `微信图片_20260805023117_6_104.jpg` | 277,828 / 1080×1443 | #21 三角形相关性热图；#22 富集分析气泡图；#23 富集分析柱状图；#24 柱状哑铃图 |
| `微信图片_20260805023118_7_104.jpg` | 273,553 / 1080×1443 | #25 横向百分比堆积柱状图；#26 甜甜圈图；#27 彩色气泡图；#28 多组 ROC 曲线 |
| `微信图片_20260805023119_8_104.jpg` | 282,308 / 1080×1443 | #29 多组干预柱状图；#30 多指标分类散点图；#31 分组棒棒糖图；#32 双误差棒图 |
| `微信图片_20260805023120_9_104.jpg` | 287,773 / 1080×1443 | #33 双因子柱状图；#34 散点小提琴图；#35 限制性立方样条图；#36 多组蜂群图 |
| `微信图片_20260805023120_10_104.jpg` | 286,280 / 1080×1443 | #37 多组散点小提琴图；#38 UMAP 降维聚类图；#39 多因子散点箱线图；#40 双 Y 轴时间序列曲线 |
| `微信图片_20260805023121_11_104.jpg` | 294,660 / 1080×1443 | #41 双拼热图；#42 花花蜂群图；#43 IC50 曲线；#44 多组折线图 |
| `微信图片_20260805023122_12_104.jpg` | 305,839 / 1080×1443 | #45 回归分析森林图；#46 双向条形图；#47 多因子柱状图；#48 肿瘤生长曲线 |
| `微信图片_20260805023123_13_104.jpg` | 267,562 / 1080×1443 | #49 泡泡蜂群图；#50 相关性散点图；#51 云雨图；#52 两组比较柱状图 |
| `微信图片_20260805023124_14_104.jpg` | 295,937 / 1080×1443 | #53 累积频率分布图；#54 分面堆积柱状图；#55 富集气泡条目图；#56 qPCR 热图 |
| `微信图片_20260805023125_15_104.jpg` | 283,515 / 1080×1443 | #57 堆积蝴蝶图；#58 WB 蛋白定量气泡图；#59 棒棒糖条形图；#60 多组区间折线图 |
| `微信图片_20260805023125_16_104.jpg` | 276,325 / 1080×1443 | #61 花花折线图；#62 WB 蛋白定量热图；#63 彩色标签森林图；#64 彩色卡片折线图 |
| `微信图片_20260805023126_17_104.jpg` | 301,196 / 1080×1444 | #65 多因子蜂群图；#66 彩色气泡热图；#67 qPCR 分段柱状图；#68 蝴蝶棒棒图 |
| `微信图片_20260805023127_18_104.jpg` | 258,430 / 1080×1444 | #69 箱线小提琴图；#70 多组花花蜂群图；#71 WB 多条带热图；#72 多因子误差棒图 |
| `微信图片_20260805023128_19_104.jpg` | 215,966 / 1080×1443 | #73 双 Y 轴相关性散点图；#74 蛋白差异火山图；#75 多组平滑曲线图；#76 多指标基因表达热图 |
| `微信图片_20260805023129_20_104.jpg` | 195,756 / 1080×1443 | #77 CCK8 细胞增殖图；#78 EC50 曲线；#79 荧光染色小提琴图；#80 基因排序图 |
| `微信图片_20260805023130_21_104.jpg` | 199,056 / 1080×1443 | #81 超多组散点柱状图；#82 带区间 KM 生存曲线；#83 彩色百分比堆积柱状图；#84 水彩散点箱线图 |
| `微信图片_20260805023130_22_104.jpg` | 201,026 / 1080×1443 | #85 双向棒棒糖图；#86 区间波形图；#87 qPCR 基因表达气泡图；#88 WB 多条带气泡图 |
| `微信图片_20260805023131_23_104.jpg` | 192,627 / 1080×1443 | #89 多因子柱状哑铃图；#90 多因子两组柱状图；#91 临床特征热图；#92 WB 条带折线图 |
| `微信图片_20260805023132_24_104.jpg` | 197,475 / 1080×1443 | #93 CCK8 柱状图；#94 WB 多指标柱状图；#95 带误差棒云雨图；#96 ELISA 多指标箱线图 |
| `微信图片_20260805023133_25_104.jpg` | 197,686 / 1080×1445 | #97 MTT 细胞活性气泡图；#98 渐变火山图；#99 GO 富集气泡图；#100 WB 多指标小提琴图 |
| `微信图片_20260805023134_26_104.jpg` | 206,290 / 1080×1443 | #101 BCA 蛋白定量柱状图；#102 多指标多组箱线图；#103 分类柱状图；#104 多组 IC50 曲线 |
| `微信图片_20260805023134_27_104.jpg` | 198,509 / 1080×1443 | #105 ELISA 小提琴图；#106 WB 单指标柱状图；#107 两组折线图；#108 单组 ROC 曲线 |
| `微信图片_20260805023135_28_104.jpg` | 247,559 / 1280×1711 | #109 双 Y 轴堆积柱状折线图；#110 WB 多条带彩色气泡图；#111 CCK8 柱状图；#112 Seahorse OCR 折线图 |
| `微信图片_20260805023136_29_104.jpg` | 232,123 / 1280×1711 | #113 OCR 蜂群图；#114 免疫荧光成像柱状图；#115 GO 功能富集基因热图；#116 箱线哑铃图 |
| `微信图片_20260805023137_30_104.jpg` | 259,433 / 1280×1711 | #117 多结局指标图（视觉上为森林图）；#118 WB 蛋白衰减折线图；#119 RNA 转录组基因热图；#120 华夫饼图 |
| `微信图片_20260805023138_31_104.jpg` | 222,971 / 1280×1711 | #121 WB 水彩柱状图；#122 多因子小提琴图；#123 泳道图；#124 WB 多组柱状图 |

### 3.3 归并前的图形族与数据推断

以下数据形状是根据可见图形推断，不是对底层数据的验证。

| 图形族 | 代表编号 | 最可能的数据形状 | 学科用途 |
|---|---|---|---|
| 生存/诊断 | 1、28、82、108 | `time,event,censor,group`；或 `label,score/threshold` | 临床预后、诊断模型 |
| 柱/条/堆积 | 2、8、12、16、25、33、47、54、83、109 | 类别×系列；原始重复或汇总+误差；组成图另有分母 | 实验组比较、组成结构 |
| 折线/剂量/时间 | 4、5、7、20、40、43、44、48、60、77、78、104、107、112 | X/时间/浓度×系列，常含重复、区间或拟合参数 | 动力学、药效、增殖、代谢 |
| 分布/原始点 | 3、9、34、36、37、39、42、51、65、69、70、84、95、102、105、113、122 | `long: group,value`；配对另需 subject ID | 个体分布、组间比较 |
| 热图/矩阵 | 6、10、18、21、41、56、62、66、71、76、91、115、119 | 行×列矩阵 + 行列注释 | 相关性、表达谱、临床特征 |
| 富集/组学 | 17、19、22、23、27、38、55、59、74、80、98、99、115 | fold change、P/FDR、gene count、enrichment ratio、embedding | 转录组、蛋白组、通路 |
| 森林/回归 | 15、35、45、63、117 | effect + lower/upper CI + label；RCS 另需连续暴露与预测 | 临床回归、Meta、多结局 |
| 气泡/棒棒糖/哑铃 | 11、24、27、31、49、58、66、68、85、87、89、110、116 | 类别/坐标 + 值；可再映射 size/color | 多变量压缩展示 |
| WB 组合图 | 58、62、71、88、92、94、100、106、110、118、121、124 | 条带栅格图像 + 样本分组 + 归一化密度值 | 蛋白表达与定量 |
| 实验专题 | 56、67、77、87、93、96、97、101、105、111–114 | qPCR、CCK8、MTT、BCA、ELISA、OCR 或成像派生值 | 分子/细胞实验 |
| 组成/流程 | 26、57、120、123 | part-to-whole；或对象的起点、持续时间、状态事件 | 构成、临床疗程 |

### 3.4 A 线对产品的有效信息与限制

素材的有效贡献是证明生命科学/医学用户会把基础图形与实验语义反复组合，例如“WB + 气泡/热图/柱/小提琴”“qPCR + 热图/柱/气泡”“CCK8/MTT + 曲线/柱”。产品应把这些作为**领域预设**映射到同一个底层图形族，而不是为“水彩柱状图”“花花蜂群图”新建图形语法。

限制如下：JPEG 无底层数据、图层、统计方法、误差定义或拟合公式；营销背景、二维码、水印和有损压缩使其不适合作为直接绘图资产；不能确认作者软件；只能确认 #1–#124；#117 标题与视觉类型不完全一致。由此，本地素材只参与“用户语言、视觉变体和生命科学场景”映射，不作为 Origin 能力或统计正确性的证据。

## 4. 证据线 B：OriginLab 官方图形库与文件能力

### 4.1 如何解释 Graph Gallery、内置图和扩展模板

Origin 官方资料称提供 100+ 图形类型；当前帮助的不同页面也会因版本、菜单项和模板计数口径出现更高数字。权威的内置类别入口应以 [Appendix 2 - Graph Types](https://docs.originlab.com/origin-help/graphtypes/) 和 [Data Selection Requirements](https://docs.originlab.com/origin-help/graph-type-data-req/) 为准。Graph Gallery 是官方实例库，但混合了内置图、用户提交示例、扩展模板、App 结果和高度定制的组合图，因此只能证明“Origin 官方展示过这种结果”，不能单独证明它是当前版本的内置菜单类型。

官方内置一级类别包括：2D Line、2D Scatter、2D Line Symbol、2D Column/Bar、Pie、Multi-Axis、Multi-Panel、Waterfall、Statistics、Grouped、Map、Area、Specialized、Financial、3D XYY、3D Surface、3D Symbol/Bar/Vector、Contour、Image/Profile。产品不必逐字复刻 Origin 菜单，而应把这些对象映射到统一图形族。

### 4.2 Origin 能力归纳

| Origin 官方族 | 代表变体 | 主要数据结构 | 批量 | 组合 | 产品映射 |
|---|---|---|---|---|---|
| 线、点、误差、线点 | step、spline、rug、bubble、color map、X/Y error、error band、before-after | `XY/XYY + error/modifier` | ✓ | 同层/多层 | 核心 XY 图族 |
| 柱、条、面积 | grouped、stacked、100%、floating、anomaly、column-line | 类别/`XY/XYY/interval` | ✓ | 同层/多层 | 比较、组成、区间 |
| 统计分布 | histogram、CDF、box、violin、beeswarm、probability、Q-Q、marginal、2D KDE | `Y/long/wide/XY` | △ | 同层/多层 | 分布与诊断 |
| 多轴、多面板 | double-Y、2Y–4Y、zoom、2/4/9 panel、trellis、inset | 多个共享或非共享 `XY` | ✓/△ | 多层 | 组合图核心 |
| 热图、等高线、图像 | heatmap、split、contour、polar/ternary contour、image/profile | `XYZ/matrix/grid/image` | ✓ | 同层/多层 | 矩阵、场与图像 |
| 流、网络与层级 | Sankey、alluvial、chord、network、parallel sets、sunburst | `edge list/matrix/hierarchy` | △ | 通常独立/多面板 | 关系、流与层级 |
| 极坐标与组成 | polar、radar、wind rose、ternary、tetrahedral | 角度—半径、组成列 | ✓/△ | 专用坐标层 | 方向与组成 |
| 地学专用 | Piper、Durov、Stiff、Schoeller、map overlays | 离子组成、`geo` | △ | 多层 | 水化学与地图 |
| 向量与 3D | quiver、streamline、3D scatter/bar/surface/waterfall | 向量场、`XYZ/matrix/XYY` | ✓ | 2D/3D 层 | 场图与 3D |
| 质量与工程统计 | QC、EWMA/CUSUM、DOE effects、Bland–Altman、Weibull | 顺序/分组/配对/失效数据 | △ | 多面板 | 进阶分析 |
| 生命科学分析输出 | ROC、Manhattan、forest App、flow cytometry 等 | 严格领域结构 | △ | 多面板 | 学科专用分析 |

### 4.3 模板、批量和组合

- [Graph Template Basics](https://docs.originlab.com/origin-help/graph-template-basics/) 与 [What is Saved with the Graph Template](https://docs.originlab.com/origin-help/graph-template-elements/) 说明：`.otpu/.otp` 保存页面、图层、轴、绘图样式、标签和标注，但不保存数据；Cloneable Template 额外记住数据结构匹配关系。
- [Batch Plotting](https://docs.originlab.com/origin-help/graphing-batch-plotting/) 明确覆盖 2D、3D 和 Contour，要求新数据与原图具有相似的工作簿、工作表或列结构。
- 统计分析和拟合派生图宜使用 [Analysis Templates](https://docs.originlab.com/origin-help/analysis-templates) 与 [Batch Processing](https://docs.originlab.com/origin-help/batch-processing/)，因此在统一库中标为“条件批量”。
- Origin 图形对象遵循 Page → Layer → Plot。基础 2D 可同层混合；不同坐标系、插图和多轴通过多层、Merge、Inset 等组合。[Creating Multi-Layer Graphs](https://docs.originlab.com/origin-help/multilayer-graph/)

### 4.4 PNG、SVG、OPJU 的真实边界

| 目标 | 可行性 | 关键限制 |
|---|---|---|
| PNG | 所有 Origin 图可导出；支持 DPI、像素尺寸和批量页 | 栅格，不可从 PNG 恢复数据、分析和图层 |
| SVG | 普通 2D/GDI 图可输出真矢量；适合后编辑 | 文字转轮廓后不再是文本；位图面板仍是栅格 |
| SVG + OpenGL 3D | 文件可生成 | 3D 内容是栅格对象嵌入，不能标为“完全可编辑矢量”，缩放可能失真 |
| OPJU | Origin 原生项目保存 | 是数据、图、分析、元数据和窗口状态的容器，不是普通图片导出；需 Origin 环境生成真正可编辑项目 |
| OTPU | 图形模板 | 不含数据；用于复用页面、轴、图层与样式 |
| OGGU | 独立图窗 | 可在 Origin 中继续编辑，但不同于完整项目 |

依据：[Origin File Types](https://docs.originlab.com/user-guide/origin-file-types/)、[Opening/Closing/Saving Origin Project](https://docs.originlab.com/origin-help/opj-open-close-backup/)、[Exporting Graphs](https://docs.originlab.com/origin-help/expgraph-to-image/)、[3D and Contour Graphing](https://docs.originlab.com/origin-help/3d-contour-graphing/)。产品推断是：没有 Origin 运行时或其自动化接口时，不应承诺从 PNG/SVG 直接生成真正数据可编辑的 OPJU。

### 4.5 Origin 官方来源清单

- [Origin Graphing product overview](https://www.originlab.com/index.aspx?go=Products%2FOrigin%2FGraphing)
- [OriginLab Graph Gallery](https://www.originlab.com/www/products/graphgallery.aspx)
- [Appendix 2 - Graph Types](https://docs.originlab.com/origin-help/graphtypes/)
- [Data Selection Requirements](https://docs.originlab.com/origin-help/graph-type-data-req/)
- [Creating 3D Graphs](https://docs.originlab.com/origin-help/create-3d-graph/)
- [Graph Template Basics](https://docs.originlab.com/origin-help/graph-template-basics/)
- [Template Center](https://docs.originlab.com/origin-help/template-center/)
- [Batch Plotting](https://docs.originlab.com/origin-help/graphing-batch-plotting/)
- [Publishing and Export](https://docs.originlab.com/user-guide/publishing-and-export/)
- [Origin Sample Projects](https://www.originlab.com/Index.aspx?go=Products%2FOrigin%2FOriginSamplesProject)

### 4.6 第一轮 31 图证据矩阵（Origin 模板优先）

本节把第一轮冻结注册表中的 31 个 `chart_type_id` 逐项绑定到可复核证据，作为绘图规范、视觉审计和后续实现修正的共同依据。它不是“看到某张图后仿一个相似样式”的清单，也不把单篇论文的个人配色提升为通用规范。

证据按下列顺序使用：

1. **`O-SYS`：Origin 系统模板或内置图。** 优先证明图的几何结构、数据角色、图例/色标对象和可编辑对象关系。
2. **`O-ANA`：Origin 官方分析输出。** 只证明该领域图的输出结构；第一轮若约定接收预计算结果，不能据此偷偷增加分析或拟合。
3. **`O-PRIM`：Origin 系统模板的原生图元组合。** 当 Origin 没有一对一系统模板时，明确记录由哪些已安装模板/连接方式组成，不伪称为独立模板。
4. **`O-EXT`：OriginLab 官方 File Exchange 模板或 App。** 可作为官方展示和领域语义的补充，但它不是系统内置能力，也不自动成为 PlotAgent 运行依赖。
5. **`PUB`：报告规范、学会/出版社指南或代表性同行评议图。** 用于补足统计语义和发表惯例；单篇论文只证明“这样发表过”，不能单独规定颜色、字号或装饰。

证据能支持的规则分为三档：**必须**是数据语义或权威规范直接要求；**默认**是 Origin 官方结构与跨来源共识支持、用户未指定时采用；**可选/产品选择**是外部证据没有唯一答案的部分，必须允许用户或发表规格覆盖。所有表中“验收”均指最小可见结构，不表示 Origin 模板的全部默认外观都要逐像素复刻。

版本口径固定为当前 Beta 的 **Origin 2024 SR1，DisplayVersion 10.10.178 / runtime 10.100178，64-bit，`originpro=1.1.15`**。2026-08-06 在新的隐藏受控 Origin 实例中以 `originpro.new_graph` 做了不保存项目的可创建性探测：`LINE`、`LINESYMB`、`SCATTER`、`Bubble`、`ERRBAR`、`ERRORBAND`、`COLUMN`、`gColumn`、`Beeswarm`、`BOX`、`Violin`、`HIST`、`HISTDIST`、`AREA`、`HeatMap`、`HEAT_MAP_WITH_LABELS`、`CONTOUR`、`grouped`、`MGROUPS` 均能创建图页；`CDF`、`statdot` 与无效名称对照均不能创建。这与官方帮助给出的 `CDF.OTPU` 最低 Origin 2025b、`statdot.optu` 最低 Origin 2025 相符。在线帮助若未给最低版本，仍以该实机探测限定“目标版本可用”，不能外推到其他版本。

以下是从 [Nature figure specifications](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/) 和 Cochrane 的 [2024 graphical recommendations](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/graph-recommendations) 中抽取、且不依赖特定期刊版式的跨图语义底线：已知的量名与单位必须出现在轴标题或等价标签中，不能编造缺失单位；尺度覆盖全部应展示数据并有效利用画布，截断必须披露；不确定性类型必须可追溯；颜色不能是唯一的关键编码；用于直接比较的面板默认采用相同尺度。它们应用到全部 31 图；Nature 的具体字号、字体、栏宽等 house style 仍只在用户选择对应 `publication_profile` 时覆盖。单个未分组系列不强制显示无信息量图例；一旦存在多个系列、组别、尺寸或颜色映射，就必须提供对应图例、气泡标尺或色标。

#### 4.6.1 XY、柱形与时间图

| ID / 图形 | Origin 优先证据与等级 | 证据支持的结构 | 第一轮验收规范与边界 |
|---|---|---|---|
| K01 折线图 | `O-SYS`：[Line Graph](https://docs.originlab.com/origin-help/line-graph/)，`LINE.OTP` | 一个或多个 Y 对关联 X，以线连接 | **必须**有可解释的 X/Y 轴标题，单位存在时带单位；多系列使用一致的系列映射并显示图例。**默认**按 X 顺序连接、缺失段断开、轴覆盖全数据；不擅自平滑。 |
| K02 线点图 | `O-SYS`：[Line+Symbol](https://docs.originlab.com/origin-help/linesym-graph/)，`LINESYMB.OTP` | 同一系列同时有线和符号 | 线与符号必须归属同一系列并保持同色；多系列同时用颜色加线型/符号冗余区分并显示图例。marker 形状、稀疏显示频率属于产品默认或用户样式。 |
| K03 散点图 | `O-SYS`：[2D Scatter](https://docs.originlab.com/origin-help/2dscatter-graph/)，`SCATTER.OTP` | XY 符号，不要求连接线 | 不连接独立观测；有 `group` 时组间可辨且有图例，颜色之外再保留符号等冗余通道；透明度和点大小按遮挡程度自动选取，但不改变数据。 |
| K04 气泡与色映射散点 | `O-SYS`：[Bubble + Color Mapped](https://docs.originlab.com/origin-help/bubble-color-map-graph/)，`Bubble.OTP`；[Bubble Scale](https://docs.originlab.com/origin-help/bubblescale/)；[Color Scale](https://docs.originlab.com/origin-help/colorscale/) | X/Y 位置，独立列控制点大小与颜色；Origin 默认创建气泡标尺，并可加入色标 | `size` 存在时**必须**显示气泡标尺，`color` 存在时**必须**显示带数值范围/单位的色标，`group` 存在时另有组图例；三者不可相互冒充。无映射时退化为普通散点，不显示空标尺。调色板类别由数据语义决定。 |
| K05 含给定回归曲线 | `O-PRIM`：`SCATTER.OTP` + `LINE.OTP` + 可选 `ERRORBAND.OTP`；Origin 的 [Logistic function](https://docs.originlab.com/origin-help/logistic-fitfunc/) 仅是分析语义补充 | 原始点、已给定曲线和可选上下界叠加 | 第一轮**只绘制 supplied curve**，不拟合、不改参数；点在带和线之上，带不遮蔽点；多模型/组别显示图例。公式、拟合优度和区间含义只在输入提供时展示。 |
| K06 点估计与误差线 | `O-SYS`：[Y Error Bar](https://docs.originlab.com/origin-help/y-errbar-graph/)，`ERRBAR.OTP` | 中心值加对称或非对称误差，可画为 bar/line/area | 中心值与上下界必须同时可见；误差是 SD、SE、CI 或其他量必须在元数据/图注可追溯，不能由形状猜测；组间重叠时错位但不改变类别顺序。 |
| K07 误差带 | `O-SYS`：[Error Band](https://docs.originlab.com/origin-help/error-band-graph/)，`ERRORBAND.OTP` | 中心线加 YEr+/YEr−；官方模板自 2020 起带颜色跟随线并用 50% 透明填充 | 中心线始终可见，带位于线后且与系列颜色关联；上下界不得交叉而不报错；多系列显示图例。50% 是 Origin 证据支持的起始默认，不是不可修改的期刊硬规则。 |
| K08 柱/条形图 | `O-SYS`：[Column Graph](https://docs.originlab.com/origin-help/column-graph/)，`COLUMN.OTP` | 每个 Y 值由固定宽度柱表示，并以关联 X 类别居中 | 类别之间必须有可见间隔；线性值轴默认包含零基线，负值向零线另一侧延伸；水平/垂直方向由用户选择。单系列可省略图例，多系列不得省。 |
| K09 分组柱形图 | `O-SYS`：[Grouped Columns](https://docs.originlab.com/origin-help/grouped-column-index-data/)，`gColumn.otpu` | 同一主类别内子组并排；官方默认对子组索引颜色，Spacing 控制组内/组间空隙 | 每个主类别内的各组柱必须**并排且彼此分开**，不得叠在同一中心；同一组跨类别颜色/图案一致并显示组图例；默认让组间间隔大于组内间隔。具体 gap 关系和百分比是 PlotAgent 产品默认，可由样式覆盖，不冒充 Origin/期刊硬值。 |
| K10 堆积柱形图 | `O-SYS`：[Stacked Column](https://docs.originlab.com/origin-help/stack-column-graph/)，`COLUMN.OTP` | 后一成分从前一成分终点开始，整栈以 X 居中 | 成分顺序和颜色跨类别保持一致，必须有成分图例；总量由栈顶表达。正负混合数据需分别从零累计或拒绝含糊方案，不能把分组柱误作堆积柱。 |
| K11 百分比堆积柱形图 | `O-SYS`：[100% Stacked Column](https://docs.originlab.com/origin-help/100-stack-column-graph/)，`COLUMN.OTP` | 每栈归一为百分比，可显示百分比标签 | 每个非空类别严格合计 100%，值轴固定 0–100% 并标明百分比，保留成分图例；零总和类别给明确错误/缺失，不制造比例。标签仅在不拥挤时显示。 |
| K18 面积图 | `O-SYS`：[Area Graph](https://docs.originlab.com/origin-help/area-graph/)，`AREA.OTP` | 数据曲线与指定 `From Y` 基线之间填充 | 基线必须明确，默认线性轴填到 0；边界线保持可见；多面积重叠时使用透明度或显式堆积，不能靠遮盖隐藏后画系列。 |
| K19 日期时间折线 | `O-SYS`：`LINE.OTP`；时间列作为关联 X，基础结构见 [Line Graph](https://docs.originlab.com/origin-help/line-graph/) | 按日期时间轴绘制一个或多个连续序列 | 保留输入行序与数值型 Date/Time X；同日显示时间、跨日显示日期；缺失值不插值；1–N 系列由官方 Line 菜单一次创建。独立的 Time Series Explorer 不是本图依赖。 |

#### 4.6.2 分布图

分布类同时参考 [Beyond Bar and Line Graphs](https://journals.plos.org/plosbiology/article?id=10.1371%2Fjournal.pbio.1002128) 对“只给均值/误差会隐藏原始分布”的证据。它支持保留点和分布，但并不意味着每张分布图都必须叠加所有几何。

| ID / 图形 | Origin 优先证据与等级 | 证据支持的结构 | 第一轮验收规范与边界 |
|---|---|---|---|
| K12 点/条带图 | `O-SYS`：[Beeswarm Plot](https://docs.originlab.com/origin-help/beeswarm-plot/)，`Beeswarm.OTPU`；当前 [Dot Plot](https://docs.originlab.com/origin-help/dot-plot/) 的 `statdot.optu` 最低为 Origin 2025，目标版本不可用 | 每列/组形成独立点群，swarm 用位移减少重叠 | 每个观测只出现一次，组之间位置和颜色可辨；抖动只作用于显示位置，不改变数值轴值；不自动叠加均值或显著性。目标 2024 采用 beeswarm/散点图元，不声称使用 `statdot.optu`。 |
| K13 箱线图 | `O-SYS`：[Box Chart](https://docs.originlab.com/origin-help/boxchart-graph/)，`BOX.OTP` 及 overlap/half 变体 | 箱体、中心统计量、须和离群点；Origin 页面给出的默认须为 5th/95th percentile | PlotAgent 冻结计算是 **Tukey box**，因此 Q1/Q3、中位数、1.5×IQR 须与离群点必须通过数值测试；不能照搬 Origin 5th/95th 默认。Origin 只作为几何/可编辑对象证据；叠加原始点为可选样式。 |
| K14 小提琴图 | `O-SYS`：[Violin Plot](https://docs.originlab.com/origin-help/violin-plot/)，`Violin.otpu` 及 box/point/quartile/split/half 变体；[Distribution tab](https://docs.originlab.com/origin-help/pd-dialog-distribution-tab/) | 每组独立核密度轮廓，可对称并可叠加箱/点/四分位 | 密度轮廓与冻结 `violin_kde` 结果一致、左右对称且不越过计算网格；组色和图例一致。带宽是计算契约，不由 Origin 默认替换；内部箱/点属于可选样式。 |
| K15 直方图 | `O-SYS`：[Histogram/Distribution](https://docs.originlab.com/origin-help/histogram-graph/)，`HIST.OTP`；带分布曲线为 `HISTDIST.OTP` | 原始值按 bin 聚合为柱，Distribution 是另一个叠加变体 | bin 边界、闭区间规则和 count/density 口径必须与冻结计算一致，横轴覆盖全部 bin；纵轴明确写 count、frequency 或 density。第一轮 K15 不自动叠加分布拟合曲线。 |
| K16 KDE 密度 | `O-PRIM`：冻结 KDE 网格用 `LINE.OTP`；`O-SYS` 补充为 `HISTDIST.OTP` 的 Kernel Smooth 选项及 [Distribution tab](https://docs.originlab.com/origin-help/pd-dialog-distribution-tab/) | 连续密度曲线；Origin 提供 kernel smooth 与带宽控制，但没有目标语义下独立的 1D KDE 系统模板 | 曲线来自 `density_kde` 固定计算，不调用 Origin 重新估计；密度非负，若定义为概率密度则数值积分约为 1；多组颜色/线型可辨并有图例。是否填充曲线下方是产品样式。 |
| K17 ECDF/CCDF | `O-PRIM`：[Horizontal Step](https://docs.originlab.com/origin-help/horizontalstep-graph/) 使用 `LINE.OTP`；当前 [CDF Plot](https://docs.originlab.com/origin-help/cdf-plot/) 使用 `CDF.OTPU`，最低 Origin 2025b，目标版本不可用 | 单调阶梯累计函数；当前 Origin CDF 支持 empirical/theoretical 与 0–1/0–100 | 第一轮只绘制固定 `ecdf` 结果：ECDF 单调不减，CCDF 单调不增，概率轴固定 0–1 或明确 0–100%；不平滑、不输出理论分布。目标 2024 不声称使用 `CDF.OTPU`。 |

#### 4.6.3 矩阵、等值和组合图

| ID / 图形 | Origin 优先证据与等级 | 证据支持的结构 | 第一轮验收规范与边界 |
|---|---|---|---|
| K20 热图 | `O-SYS`：[Heatmap](https://docs.originlab.com/origin-help/heat_map/)，`HeatMap.otp`；[Color Scale](https://docs.originlab.com/origin-help/colorscale/) | 矩阵/虚拟矩阵单元格着色，刻度居中于色块，缺失值可用独立颜色 | 所有矩阵单元必须无内部留白地铺满数据框，行列标签与矩阵顺序一致；连续值映射必须有色标，缺失值与数值 0 明确区分。默认不使用 rainbow；色板可从安全的顺序/发散集合选择。 |
| K21 给定相关矩阵 | `O-SYS`：[Heatmap with Labels](https://docs.originlab.com/origin-help/heatmap-labels/)，`HEAT_MAP_WITH_LABELS.OTPU` | 每格颜色加矩阵 Z 值标签 | 只绘制 supplied matrix，不从原始表重新算相关；行列变量顺序一致，值标签精度统一；相关系数语义时色域固定 −1..1、发散色板以 0 为中点并显示色标。若输入声明的不是相关系数，则不得强套 −1..1。三角遮罩/层次聚类不在第一轮。 |
| K22 给定规则网格等值图 | `O-SYS`：[Color Fill Contour](https://docs.originlab.com/origin-help/colorfill-contour-graph/)，矩阵 `CONTOUR.OTP`；[Color Scale](https://docs.originlab.com/origin-help/colorscale/) | 规则 XY 网格上以填色和等值线表示 Z 范围；矩阵图默认按 X:Y 数值跨度联动图层比例 | 填色必须覆盖从 `x_min..x_max`、`y_min..y_max` 的完整网格范围，图层内部不留无数据边；必须显示色标，Z 变量名/单位存在时写入色标。规则网格默认遵循数据坐标比例；若为版式填满而改变 aspect，必须是显式样式选择。提供多套感知均匀顺序/发散色板，按 Z 语义选择；等值级数量属于自动默认且可改，不固定为单一调色板。 |
| K24 分面图 | `O-SYS`：[Trellis](https://docs.originlab.com/origin-help/trellis/)，`grouped.otp` | 分组列决定横/纵面板，并可用另一变量映射颜色 | 每个 facet 只包含对应子集，面板标签完整且顺序稳定；直接比较时默认共享相同尺度，公共轴标题不重复堆叠；系列颜色跨面板同构。自由尺度只能由用户明确指定。 |
| K25 多面板组合图 | `O-SYS`：[Multiple Panels](https://docs.originlab.com/origin-help/multipanel-graph/)，`MGROUPS.OTPU`，证明多层、面板排列与间距；`O-PRIM`：各子图仍按自己的 31 图证据构建 | 多层页面、可配置行列/间距，并能统一编辑层/轴属性 | 面板按阅读顺序排列，统一字体、线宽和对齐；按 [Nature panel guide](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/) 使用 `a,b,c…` 标签并减少无效白边。只有映射含义完全相同时才共享图例/色标；`MGROUPS` 是布局证据，不伪称能直接生成任意异构子图。 |
| S61 混淆矩阵 | `O-SYS`：`HEAT_MAP_WITH_LABELS.OTPU`，见 [Heatmap with Labels](https://docs.originlab.com/origin-help/heatmap-labels/) | 分类矩阵每格用颜色和数值标签显示 | X/Y 轴明确标为 predicted/actual，类别顺序与计算结果一致，每格显示 count；必须有色标且文字与底色保持对比。第一轮只执行 `confusion_count`；若以后支持行/列归一化，必须在标题或色标注明口径，不能与计数混用。 |

#### 4.6.4 学科专用图

| ID / 图形 | Origin 优先证据与等级 | 领域/发表证据 | 第一轮验收规范与边界 |
|---|---|---|---|
| S01 给定 KM 生存曲线 | `O-ANA`：[Kaplan–Meier Estimator](https://docs.originlab.com/origin-help/kaplanmeier-estimator/) 与 [Survival Plots](https://docs.originlab.com/origin-help/kaplanmeier-dialog/) 证明 step survival、上下置信限、多组同图；`O-PRIM`：`LINE.OTP` step + `ERRORBAND.OTP` + 风险表图层 | Origin 说明 KM 是阶梯函数并可输出置信区间；但未证明风险表是内置输出硬要求 | 第一轮只接收 supplied steps，不从个体数据估计 KM；生存轴固定 0–1，曲线单调不增；CI、删失标记、risk table 仅在对应输入存在时绘制，多组必须有图例。不得凭空补风险人数或检验结果。 |
| S05 给定剂量反应曲线 | `O-ANA`：[Origin Logistic](https://docs.originlab.com/origin-help/logistic-fitfunc/) 证明常见四参数 logistic 语义；`O-PRIM`：`SCATTER.OTP` + `LINE.OTP` + 可选 `ERRORBAND.OTP` | Origin 把 logistic 标为药理/化学 dose response，但不同实验也可能使用其他模型 | 原始点、supplied curve、可选区间清楚分层；第一轮不拟合、不选择模型。剂量对数轴只在用户/PlotSpec 明确选择且全部绘制值合法时启用；零剂量不能静默丢弃。参数只展示输入提供内容。 |
| S21 给定效应量森林图 | `O-EXT`：[OriginLab Forest Plot App](https://www.originlab.com/fileExchange/details.aspx?fid=362)（最低 Origin 2017，非系统模板）支持 effect、上下 CI、可选 weight 和线性/对数轴；`O-PRIM`：[2 Point Segment](https://docs.originlab.com/origin-help/2point-seg-graph/) 的 `LINESYMB.OTP` + symbol | Cochrane [2024 forest recommendations](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/graph-recommendations)：效应量横轴、无效线、点估计方块、水平 CI、面积对应权重、Study ID、比值效应使用对数轴且刻度显示原值 | 每行 label、effect、CI 对齐；无效线位置由效应类型决定；有 weight 时符号面积而非半径与权重关联。单组可用中性色；存在有意义的系列/亚组时，用无障碍颜色加符号区分并显示图例，**不得给每行随机换色**。第一轮不计算汇总菱形或异质性。 |
| S25 连续谱图 | `O-PRIM`：`LINE.OTP`；`O-EXT`：[Color Spectrum Plot](https://www.originlab.com/fileExchange/details.aspx?fid=666) 只证明 OriginLab 展示过波长谱扩展样式，不是系统模板或通用谱规范 | 化学/材料期刊中的 NMR、Raman、UV–Vis、XPS 等都采用连续轴—强度线图，但横轴方向和单位随谱种类变化 | 光谱轴和 intensity 标题/单位存在即显示，多系列颜色/线型和图例一致；完整给定范围进入自动缩放。第一轮不平滑、基线扣除、峰拟合或归一化；反向轴、填色、offset 仅由明确的领域类型或用户指令启用。 |
| S31 XRD 衍射图 | `O-PRIM`：基础图为 `LINE.OTP`；`O-EXT`：[XRD with PDF](https://www.originlab.com/fileexchange/details.aspx?fid=929&v=0) 是 OriginLab Technical Support 发布的 graph template，最低 Origin 2023，输入 XRD XY 与标准卡 XY；[Graph Gallery](https://www.originlab.com/www/products/GraphGallery.aspx?GID=1617) 展示曲线与标准卡 | [Nature Communications 材料实例](https://www.nature.com/articles/s41467-025-65815-8) 证明 XRD 常与显微/晶体结构组合发表；单篇图不规定统一颜色 | X 轴为 angle/2θ（以输入标签为准），Y 轴为 intensity；曲线覆盖完整给定角度范围，峰标签只在输入提供时绘制并避免重叠。第一轮不做背景扣除、归一化、寻峰或 PDF 卡匹配；扩展模板是证据，不是安装依赖。 |
| S34 Nyquist 图 | `O-PRIM`：`LINESYMB.OTP`；Origin 2025b 的同名控制系统 App 版本和语义均不匹配本 Beta，不能作为 2024 EIS 模板证据 | ACS [Electrochemical impedance tutorial](https://pubs.acs.org/doi/abs/10.1021/acsmeasuresciau.2c00070) 支持 EIS Nyquist 的复阻抗、频率与时间常数语义 | X 为 `Z′`，Y 为输入约定后的 `−Z″`/imaginary，并把符号约定写入轴标题；数据坐标默认等比例，点按频率顺序连接，提供 frequency 时可标方向或代表点。多系列用颜色加符号区分并显示图例；不拟合等效电路。 |

#### 4.6.5 证据参考图索引

下表把 31 项证据与对应参考图放在同一处。点击缩略图回到原始证据页；图片本身只用于本项目视觉审计，不作为可再分发的产品素材。**一对一**表示目标几何直接对应；**结构参考**表示只支持几何、布局或领域结构，颜色、统计计算和装饰仍以本节文字规范为准。远程图片地址和原始证据页访问日期均为 2026-08-06。

| ID | 对应参考图 | 匹配范围 |
|---|---|---|
| K01 | <a href="https://docs.originlab.com/origin-help/line-graph/"><img src="https://docs.originlab.com/origin-help/line-graph/images/Image006.webp?v=WftSMi2vYoo" width="200" alt="Origin Line Graph"></a> | `O-SYS` `LINE.OTP`，一对一 |
| K02 | <a href="https://docs.originlab.com/origin-help/linesym-graph/"><img src="https://docs.originlab.com/origin-help/linesym-graph/images/Image010.webp?v=5jFvqaHm75M" width="200" alt="Origin Line and Symbol"></a> | `O-SYS` `LINESYMB.OTP`，一对一 |
| K03 | <a href="https://docs.originlab.com/origin-help/2dscatter-graph/"><img src="https://docs.originlab.com/origin-help/2dscatter-graph/images/Image002.webp?v=2p8aRmbRQ78" width="200" alt="Origin Scatter"></a> | `O-SYS` `SCATTER.OTP`，一对一 |
| K04 | <a href="https://docs.originlab.com/origin-help/bubble-color-map-graph/"><img src="https://docs.originlab.com/origin-help/bubble-color-map-graph/images/Bubble_Graph_with_Color_Map.webp?v=YsOi1LY1vlM" width="200" alt="Origin Bubble Color Map"></a> | `O-SYS` `Bubble.OTP`，一对一；大小/颜色图例另见正文 |
| K05 | <a href="https://docs.originlab.com/origin-help/logistic-fitfunc/"><img src="https://docs.originlab.com/origin-help/logistic-fitfunc/images/CFF_Image308.webp?v=8B8cC48aZsM" width="200" alt="Origin Logistic Curve"></a> | `O-ANA/O-PRIM`，曲线结构参考；不是通用回归模型 |
| K06 | <a href="https://docs.originlab.com/origin-help/y-errbar-graph/"><img src="https://docs.originlab.com/origin-help/y-errbar-graph/images/Image064.webp?v=LvKL2fZoE90" width="200" alt="Origin Error Bar"></a> | `O-SYS` `ERRBAR.OTP`，一对一 |
| K07 | <a href="https://docs.originlab.com/origin-help/error-band-graph/"><img src="https://docs.originlab.com/origin-help/error-band-graph/images/Error_Band.webp?v=4bGx6bZuuG8" width="200" alt="Origin Error Band"></a> | `O-SYS` `ERRORBAND.OTP`，一对一 |
| K08 | <a href="https://docs.originlab.com/origin-help/column-graph/"><img src="https://docs.originlab.com/origin-help/column-graph/images/Image046.webp?v=oPOMtUx05No" width="200" alt="Origin Column Graph"></a> | `O-SYS` `COLUMN.OTP`，一对一 |
| K09 | <a href="https://docs.originlab.com/origin-help/grouped-column-index-data/"><img src="https://docs.originlab.com/origin-help/grouped-column-index-data/images/Grouped_Column_Indexed_Data.webp?v=wwLjaqaI41I" width="200" alt="Origin Grouped Columns"></a> | `O-SYS` `gColumn.otpu`，一对一；柱必须并排分开 |
| K10 | <a href="https://docs.originlab.com/origin-help/stack-column-graph/"><img src="https://docs.originlab.com/origin-help/stack-column-graph/images/Image061.webp?v=uyq3W7jJOdo" width="200" alt="Origin Stacked Column"></a> | `O-SYS` `COLUMN.OTP`，一对一 |
| K11 | <a href="https://docs.originlab.com/origin-help/100-stack-column-graph/"><img src="https://docs.originlab.com/origin-help/100-stack-column-graph/images/100_Stack_Column.webp?v=jYp7iMwcqAY" width="200" alt="Origin 100 Percent Stacked Column"></a> | `O-SYS` `COLUMN.OTP`，一对一 |
| K12 | <a href="https://docs.originlab.com/origin-help/beeswarm-plot/"><img src="https://docs.originlab.com/origin-help/beeswarm-plot/images/Appendix2_Beeswarm_example.webp?v=yp7M5GX10dA" width="200" alt="Origin Beeswarm"></a> | `O-SYS` `Beeswarm.OTPU`，目标 2024 一对一替代证据 |
| K13 | <a href="https://docs.originlab.com/origin-help/boxchart-graph/"><img src="https://docs.originlab.com/origin-help/boxchart-graph/images/Box_chart2.webp?v=3PdyLcmyAUM" width="200" alt="Origin Box Chart"></a> | `O-SYS` 几何一对一；须统计与 PlotAgent Tukey 契约不同 |
| K14 | <a href="https://docs.originlab.com/origin-help/violin-plot/"><img src="https://docs.originlab.com/origin-help/violin-plot/images/Violin_Plot.webp?v=2r6zALU9EO8" width="200" alt="Origin Violin Plot"></a> | `O-SYS` `Violin.otpu`，一对一 |
| K15 | <a href="https://docs.originlab.com/origin-help/histogram-graph/"><img src="https://docs.originlab.com/origin-help/histogram-graph/images/Histogram_Graph1.webp?v=4SGPUV3gk7k" width="200" alt="Origin Histogram"></a> | `O-SYS` `HIST.OTP`，一对一 |
| K16 | <a href="https://docs.originlab.com/origin-help/histogram-graph/"><img src="https://docs.originlab.com/origin-help/histogram-graph/images/Histogram_Graph3.webp?v=ozqhyo2nqbk" width="200" alt="Origin Distribution Curve"></a> | `O-SYS/O-PRIM`，KDE 曲线结构参考；第一轮独立线图 |
| K17 | <a href="https://docs.originlab.com/origin-help/horizontalstep-graph/"><img src="https://docs.originlab.com/origin-help/horizontalstep-graph/images/Image030.webp?v=JAAi7c19oK4" width="200" alt="Origin Horizontal Step"></a> | `O-PRIM` `LINE.OTP` step，一对一几何；非 2025b `CDF.OTPU` |
| K18 | <a href="https://docs.originlab.com/origin-help/area-graph/"><img src="https://docs.originlab.com/origin-help/area-graph/images/Image_area_graph_type.webp?v=MFQNpQl1fdc" width="200" alt="Origin Area Graph"></a> | `O-SYS` `AREA.OTP`，一对一 |
| K19 | <a href="https://docs.originlab.com/origin-help/line-graph/"><img src="https://docs.originlab.com/origin-help/line-graph/images/Image006.webp?v=WftSMi2vYoo" width="200" alt="Origin Line Graph for Time Series"></a> | `O-SYS` `LINE.OTP`，线结构参考；日期刻度由时间语义决定 |
| K20 | <a href="https://docs.originlab.com/origin-help/heat_map/"><img src="https://docs.originlab.com/origin-help/heat_map/images/Heat_Map-01.webp?v=3LXYIoVm_I4" width="200" alt="Origin Heatmap"></a> | `O-SYS` `HeatMap.otp`，一对一 |
| K21 | <a href="https://docs.originlab.com/origin-help/heatmap-labels/"><img src="https://docs.originlab.com/origin-help/heatmap-labels/images/Heatmap_with_Labels-01.webp?v=Y4zBxX2GA94" width="200" alt="Origin Heatmap with Labels"></a> | `O-SYS` 矩阵色块/标签一对一；相关色域来自语义 |
| K22 | <a href="https://docs.originlab.com/origin-help/colorfill-contour-graph/"><img src="https://docs.originlab.com/origin-help/colorfill-contour-graph/images/Color_Fill_Contour_Graphs_01.webp?v=x9iDjo6w3r8" width="200" alt="Origin Color Fill Contour"></a> | `O-SYS` `CONTOUR.OTP`，一对一 |
| K24 | <a href="https://docs.originlab.com/origin-help/trellis/"><img src="https://docs.originlab.com/origin-help/trellis/images/Trellis_graph_01.webp?v=Ti6O3JNxuxU" width="200" alt="Origin Trellis"></a> | `O-SYS` `grouped.otp`，一对一 |
| K25 | <a href="https://docs.originlab.com/origin-help/multipanel-graph/"><img src="https://docs.originlab.com/origin-help/multipanel-graph/images/Multiple_panels_by_label_01.webp?v=dvDkUfDUCfU" width="200" alt="Origin Multiple Panels"></a> | `O-SYS/O-PRIM`，布局一对一；异构子图另按各自证据 |
| S01 | <a href="https://docs.originlab.com/origin-help/kaplanmeier-estimator/"><img src="https://docs.originlab.com/origin-help/kaplanmeier-estimator/images/Kaplan-Meier_Estimator_Image372.webp?v=DgekENBcIPk" width="200" alt="Origin Kaplan Meier"></a> | `O-ANA/O-PRIM`，领域结构参考；第一轮不运行 KM |
| S05 | <a href="https://docs.originlab.com/origin-help/logistic-fitfunc/"><img src="https://docs.originlab.com/origin-help/logistic-fitfunc/images/CFF_Image308.webp?v=8B8cC48aZsM" width="200" alt="Origin Dose Response Logistic"></a> | `O-ANA/O-PRIM`，领域结构参考；第一轮不拟合 |
| S21 | <a href="https://www.originlab.com/fileExchange/details.aspx?fid=362"><img src="https://www.originlab.com/fileexchange/images/362/ForestPlotScreenShot.png?t=260617172150" width="200" alt="OriginLab Forest Plot App"></a> | `O-EXT/O-PRIM`，一对一领域图；非系统模板 |
| S25 | <a href="https://www.originlab.com/fileExchange/details.aspx?fid=666"><img src="https://www.originlab.com/fileexchange/images/666/Color_Spectrum_Plot_scs.png?t=220511093941" width="200" alt="OriginLab Color Spectrum Plot"></a> | `O-EXT/O-PRIM`，连续谱结构参考；彩色填充不通用 |
| S31 | <a href="https://www.originlab.com/fileexchange/details.aspx?fid=929&amp;v=0"><img src="https://www.originlab.com/fileexchange/images/929/xrdpdf_otp.png?t=241115042752" width="200" alt="OriginLab XRD with PDF"></a> | `O-EXT/O-PRIM`，一对一领域图；非系统模板 |
| S34 | <a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC10288619/#fig17"><img src="https://cdn.ncbi.nlm.nih.gov/pmc/blobs/db1e/10288619/0e5f1ae01566/tg2c00070_0017.jpg" width="200" alt="ACS EIS Tutorial Figure 17 Nyquist"></a> | `PUB/O-PRIM`，ACS Measurement Science Au Figure 17；Origin 2024 无匹配 EIS 系统模板 |
| S61 | <a href="https://docs.originlab.com/origin-help/heatmap-labels/"><img src="https://docs.originlab.com/origin-help/heatmap-labels/images/Heatmap_with_Labels-01.webp?v=Y4zBxX2GA94" width="200" alt="Origin Heatmap with Labels for Confusion Matrix"></a> | `O-SYS/O-PRIM`，矩阵结构参考；actual/predicted 和 count 由固定计算决定 |

为了快速视觉审计，另生成本地筛选页：`build/visual-audit/31-chart-evidence-matrix.html`。该页面只是上述已固化索引的浏览视图，不是新的产品规格文档。

#### 4.6.6 由矩阵直接导出的视觉审计规则

这组规则直接用于当前 31 图审计，避免再次依靠肉眼临时判断：

- **轴标题：** K01 等普通 XY 图只要字段映射能提供变量名，就必须生成 X/Y 标题；单位仅在来源元数据存在时追加。无标题不是“极简风格”，而是语义缺失。
- **图例与标尺：** K04 的 size/color/group 分别对应气泡标尺、色标、组图例；K09 的 subgroup 必须有图例；S21 只有存在有意义的系列/亚组时才使用颜色/符号和图例。单系列无映射图可以不放图例。
- **分组几何：** K09 同一类别下的组必须有不同中心位置和可见组内间距；如果柱中心重合，即使颜色不同也判失败。
- **网格填充与色标：** K20、K21、K22、S61 的数据几何必须覆盖自己的完整数据框，连续颜色映射必须有色标；K22 不能在坐标框内留下无语义白边。色板从多套感知均匀的 sequential/diverging 方案中按数据语义选择，参考 [Crameri et al.](https://www.nature.com/articles/s41467-020-19160-7)，不把单一 Viridis 或 Origin Thermometer 固化为所有场图的唯一规范。
- **系列同构：** 同一系列在图、图例、分面和组合图中保持同一颜色/线型/符号；颜色是增强通道，不是唯一识别通道。S21 不按研究行随机上色，只有系列/亚组才改变编码。
- **自动缩放：** 线/点图覆盖全部有限数据并保留小而不误导的边距；线性柱图包含零；概率图使用 0–1 或明确百分比范围；直接比较的分面默认共享尺度；K22 的 x/y 范围严格来自规则网格边界。对数轴遇到非正值必须报可定位错误，不能静默删除。

该矩阵是**规范证据层**，不是导出实现对 Origin 官方模板文件的直接依赖。PlotAgent 仍可从签名基础模板用类型化 Origin 原生对象构建等价结构；验收看对象语义、数据绑定和可见结果是否满足本矩阵，而不是要求模板文件名逐项出现在 OPJU 中。

## 5. 证据线 C：各学科头部期刊与学术规范

### 5.1 跨学科图稿要求

| 规范来源 | 直接证据 | 对 PlotAgent 的要求 |
|---|---|---|
| [Nature figure specifications](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/) | 轴、刻度、轴名和单位完整；无障碍色板；线、箭头、比例尺和文字尽可能为可编辑矢量 | 默认完整轴语义；SVG 保留文字；图像面板保留比例尺 |
| [Nature building/exporting panels](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/) | 期刊栏宽、5–7 pt 字体、多面板按字母顺序、减少白边 | 核心支持栏宽预设、面板字母、统一字体与共享图例 |
| [Nature image integrity](https://www.nature.com/npjclimataction/for-authors-and-referees/about/editorial-policies/image-integrity) | 图像只做最低限度处理；拼接边界显式标出；保存原图、元数据和处理记录 | 显微、凝胶、遥感图带处理历史、拼接标记和原图引用 |
| [Nature formatting guide](https://www.nature.com/nature/for-authors/formatting-guide) | 误差线和统计定义写入图注，图尽可能简单 | 所有误差模板强制记录 SD/SE/CI、n 和重复类型 |
| [AGU Text & Graphics](https://www.agu.org/publications/authors/journals/text-graphics-requirements) | 反对 rainbow 和红绿依赖；推荐感知均匀、色觉缺陷友好的色图，并用线型/符号冗余编码 | 连续、发散、分类色板分开；默认禁用 jet/rainbow |
| [IEEE Create Graphics](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/) | 线图同时使用颜色、线型和点符号，灰度打印仍可辨 | 工程/计算图默认提供颜色 + 线型 + marker |
| [ACS graphics guidance](https://researcher-resources.acs.org/publish/author_guidelines) | 线稿、灰度、彩色图有不同分辨率要求；强调尺寸、线宽、字体、色彩和结构图 | 化学结构、谱图、线稿与照片分别导出；提供 ACS 版式预设 |
| [APS Physical Review Materials author guide](https://journals.aps.org/prmaterials/authors/information-for-contributors) | 图缩栏后仍可读，轴含物理量与单位，多面板统一标号 | 物理量/单位是字段而非自由文本；按最终尺寸校验 |
| [ACM accessible figures](https://dis.acm.org/2023/creating-accessible-figures-and-tables/) | 颜色不能是唯一编码；图注、轴、图例和趋势 alt text 应完整 | 图形元数据支持 alt text/长描述；表格保持结构化 |

### 5.2 生命科学与医学

高频任务是：原始点/配对点与分布、KM/累计发生、森林与亚组效应、ROC/PR/校准/决策曲线、临床和综述流程图、组学热图/volcano/MA、UMAP/t-SNE/PCA、富集图、单细胞 dot plot、显微/病理/凝胶图、基因组轨道与 Circos。

| 权威或代表性来源 | 支持的图形证据 |
|---|---|
| [PRISMA 2020 flow diagram](https://www.prisma-statement.org/prisma-2020-flow-diagram) | 系统综述的记录识别、纳入、排除数量与原因 |
| [CONSORT 2025 statement](https://www.bmj.com/content/389/bmj-2024-081123) | 随机试验参与者流转图 |
| [Cochrane meta-analysis chapter](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-10) | 森林图展示研究效应、CI、权重和汇总；异质性和汇总语义 |
| [Cochrane missing-evidence chapter](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-13) | 漏斗图不对称有多种原因，不能自动等同发表偏倚 |
| [TRIPOD explanation](https://methods.cochrane.org/sites/methods.cochrane.org.prognosis/files/uploads/Moons%20%28Ann%20Intern%20Med%202015%29.pdf) | 预测模型校准图、判别、决策曲线语义 |
| [PLOS Biology graph policy](https://journals.plos.org/plosbiology/s/submission-guidelines) | 小样本连续数据不鼓励只有均值柱/线；推荐散点、箱线、直方图显示分布 |
| [Nature: integrated spatial genomics](https://www.nature.com/articles/s41586-020-03126-2) | 代表性组合使用直方图、箱线、UMAP、热图、拟时序、网络和相关矩阵 |
| [Bioimage publishing checklists](https://www.nature.com/articles/s41592-023-01987-9) | 比例尺、强度/校准图例、色盲可读和完整图像分析流程 |

领域风险：KM 需删失标记、风险人数、置信带和随访范围；不平衡分类不能只看 ROC；volcano 需多重比较校正；UMAP/t-SNE 不可把全局距离和簇面积解释为定量生物距离；显微图不可用不同亮度/阈值或未披露的拼接来比较组别。

### 5.3 化学

高频任务是：化学结构/反应/催化循环，NMR、IR、Raman、UV–Vis、荧光、MS/ECD 谱，HPLC/GC 色谱，校准/滴定/动力学曲线，能量剖面，晶体/ORTEP，二元/三元相图与线性自由能关系。

| 来源 | 支持的图形证据 |
|---|---|
| [ACS Guide to Scholarly Communication](https://pubs.acs.org/styleguide) | 图形、结构式、化学方程、分析结果和晶体学的正式规范入口 |
| [ACS Preparing Manuscript Graphics](https://pubs.acs.org/page/4Authors/submission/graphics_prep.html) | 图稿与 ChemDraw/结构式规范 |
| [Nature chemical structures guide](https://www.nature.com/documents/nr-chemical-structures-guide.pdf) | 键长、键角、线宽和立体化学一致性 |
| [IUPAC stereochemical representation](https://publications.iupac.org/publications/pac/2006/7810/7810x1897.html) | 楔键方向与避免歧义的原始建议 |
| [IUCr checkCIF](https://checkcif.iucr.org/index.html) | CIF、几何、空间群、位移参数和结构因子检查 |
| [JACS molecular diffusivity study](https://pubs.acs.org/doi/10.1021/jacs.1c11754) | 反应方案、催化循环、1D NMR、时间谱和动力学曲线的组合实例 |
| [JACS sequential switch](https://pubs.acs.org/doi/abs/10.1021/jacs.1c11183) | HPLC/NMR 动力学和实验/计算自由能剖面的组合实例 |

领域风险：NMR 横轴惯例通常高 ppm 在左；谱图局部截取、分别归一化、强平滑或基线扣除必须披露；色谱不能只给目标峰附近；能量图必须统一零点、单位、温度、溶剂和计算层级；球棍图不能代替 CIF 与 CheckCIF。

### 5.4 材料科学

高频任务是：XRD/SAXS/WAXS/SAED，SEM/TEM/STEM/AFM 与元素 mapping，EBSD/pole figure，应力–应变/载荷–位移，DSC/TGA，CV/GCD/cycling/rate/Nyquist/Ragone，组成相图，能带/DOS/电荷密度和 Ashby 图。

| 来源 | 支持的图形证据 |
|---|---|
| [Nature Materials reporting standards](https://www.nature.com/nmat/editorial-policies/reporting-standards) | 最小可验证数据集、CIF/结构因子/CheckCIF 与概率椭球结构图 |
| [Unified battery metrics](https://www.nature.com/articles/s41467-018-07599-8) | 容量、电压窗、载量、循环、库仑效率、电解液、质量/体积性能的完整口径 |
| [Redox-flow battery metrics](https://www.nature.com/articles/s41560-020-00772-8) | 电池测试与比较框架 |
| [JACS electrocatalyst example](https://pubs.acs.org/doi/abs/10.1021/jacs.2c07226) | CV、Nyquist、Tafel、稳态与寿命曲线组成的代表性电化学 figure |
| [Nature Communications Zn–iodine batteries](https://www.nature.com/articles/s41467-025-60488-9) | 示意、CV、GCD、倍率、循环、文献对比、原位 Raman 和表面图组合 |
| [Materials microstructure and sensing](https://www.nature.com/articles/s41467-025-65815-8) | 制备流程、SEM/TEM/STEM、SAED、晶体结构和 XRD 组合 |

领域风险：XRD 的背景扣除、峰宽处理和独立归一化影响判断；显微图必须有尺度、视野数和可比较强度；工程应力与真实应力须区分；EIS 等效电路不是唯一机理证明；相图/等值图由稀疏点插值时必须叠加实测点。

### 5.5 物理

高频任务是：色散、能带与 DOS，相图，log–log/semilog 标度，二维强度/谱函数/FFT 图，磁滞与 I–V/输运，时空图、waterfall/spectrogram，实验装置与理论示意，误差棒数据和理论曲线叠加。

| 来源 | 支持的图形证据 |
|---|---|
| [Physical Review Style and Notation Guide](https://journals.aps.org/files/styleguide-pr.pdf) | 自解释图、物理量/单位、多面板标号与缩栏可读性 |
| [APS accessibility guidance](https://journals.aps.org/prl/authors) | 无障碍色板；以文字/符号而非只靠颜色表达 |
| [Nature Communications topological phase example](https://www.nature.com/articles/ncomms13918) | 相图与能带结构同图的代表实例 |
| [Nature Communications band-structure example](https://www.nature.com/articles/s41467-021-27042-9) | 能带与 Berry curvature 的多参数面板 |
| [PRL band unfolding](https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.104.216401) | 能带与谱权重可视化 |

领域风险：log–log 的视觉直线不能替代拟合区间与不确定度；相边界不能用过度平滑暗示精确；谱图色限裁剪会制造/消除弱特征；能带必须记录 k 路径、费米能零点、展宽和谱权重；实验、模拟与解析曲线使用不同编码。

### 5.6 地球与环境科学

高频任务是：点/线/面与栅格地图、等值线/矢量/流线、异常和趋势时间序列、地质/海洋/大气剖面、hydrograph/hyetograph、Taylor/target、ensemble plume/fan、风玫瑰、三元/Piper/Stiff、物质流/碳预算。

| 来源 | 支持的图形证据 |
|---|---|
| [AGU Text & Graphics](https://www.agu.org/publications/authors/journals/text-graphics-requirements) | 图形无障碍、地图经纬度、数据/软件可追溯和组合文件要求 |
| [IPCC AR6 WGI Visual Style Guide](https://www.ipcc.ch/site/assets/uploads/2022/09/IPCC_AR6_WGI_VisualStyleGuide_2022.pdf) | 地图、误差棒、带状区间、纹理与多种不确定性表达 |
| [Crameri et al., Nature Communications](https://www.nature.com/articles/s41467-020-19160-7) | rainbow/红绿配色的感知失真与科学色图原则 |
| [Geospatial modelling challenges](https://www.nature.com/articles/s41467-024-55240-8) | 空间预测与不确定性地图；bivariate choropleth 等 |
| [Hovmöller application](https://www.nature.com/articles/s41598-024-52541-2) | 时间—经度/空间热图的代表实例 |
| [WRR flood-reactivity study](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1002/2017wr021650) | hydrograph、函数与聚类展示洪水过程 |
| [GRL Taylor diagram application](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2018GL079272) | Taylor diagram 与区域偏差的模型比较 |

领域风险：地图必须记录 CRS/投影、比例尺、方向和覆盖范围；稀疏站点插值要叠加站点/遮罩；异常需写基准期；多模型只画均值会隐藏离散度，spaghetti 过多又不可读；Taylor 图不宜作为唯一模型评估。

### 5.7 工程

高频任务是：系统/流程/控制框图，Bode/Nyquist/root locus，CFD/FEA contour 与矢量场，应力–应变/S–N/Paris，控制图，DOE 主效应/交互/响应面，Weibull 可靠性，Pareto 和校准/残差。

| 来源 | 支持的图形证据 |
|---|---|
| [IEEE graphics guide](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/) | 图形格式、无障碍和线图冗余编码 |
| [NIST graphical techniques gallery](https://www.itl.nist.gov/div898/handbook/graphgal.htm) | EDA、时间序列、回归、多变量、可靠性、控制图和 DOE 的权威图形族 |
| [NIST control charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc31.htm) | 过程监控与控制限语义 |
| [NIST Weibull plot](https://www.itl.nist.gov/div898/handbook/eda/section3/edav.htm) | 失效时间、形状/尺度、删失和分布假设 |
| [NIST DOE contour](https://www.itl.nist.gov/div898/handbook/pri/section5/pri59a.htm) | 响应面、固定其他因子与下一轮实验设计 |
| [Electrochemical impedance tutorial](https://pubs.acs.org/doi/abs/10.1021/acsmeasuresciau.2c00070) | Nyquist 是 EIS 的典型表示及其频率/时间常数语义 |

领域风险：FEA/CFD 必须标网格、边界条件、色限和单位；响应面不可无警告外推；控制限不是规格限；Weibull 需处理删失与分布假设；Bode/Nyquist 标频率方向和相位约定；S–N 需区分 run-out。

### 5.8 计算机与数据科学

高频任务是：训练/验证学习曲线，ROC/PR/校准/阈值，confusion matrix，多数据集 benchmark，critical difference，消融与超参敏感性，速度—精度 Pareto，embedding，SHAP/归因热图，架构/计算图，可扩展性曲线与事件 trace。

| 来源 | 支持的图形证据 |
|---|---|
| [NeurIPS paper checklist](https://blog.neurips.cc/2021/03/26/introducing-the-neurips-2021-paper-checklist/) | 复现、限制、实验误差线与统计说明 |
| [ACM accessible figures](https://dis.acm.org/2023/creating-accessible-figures-and-tables/) | 图注、轴、图例、趋势 alt text 和非颜色单通道 |
| [Calibration of modern neural networks](https://proceedings.mlr.press/v70/guo17a.html) | confidence histogram 与 reliability diagram |
| [Precision/Recall on imbalanced test data](https://proceedings.mlr.press/v206/shang23a.html) | 不平衡数据下 PR 与区间 |
| [JMLR classifier comparisons](https://www.jmlr.org/beta/papers/v7/demsar06a.html) | 多数据集统计比较与 critical difference diagram |
| [JMLR t-SNE](https://www.jmlr.org/papers/v9/vandermaaten08a.html) 与 [DR methods comparison](https://jmlr.org/beta/papers/v22/20-1061.html) | 降维点图及局部/全局结构保持的权衡 |
| [Representative ML evaluation figure](https://www.nature.com/articles/s43247-025-02816-x) | ROC、confusion matrix、SHAP summary/dependence 的组合实例 |

领域风险：不能只画最佳 run；平均线需多 seed 区间；benchmark 压缩 y 轴会夸大差异；confusion matrix 必须说明计数/行归一/列归一；校准需记录分箱；UMAP/t-SNE 参数和 seed 可追溯；SHAP/attention 不可默认解释为因果；逐项消融不能替代完整因子实验。

### 5.9 心理与社会科学

高频任务是：原始点 + 箱线/小提琴/raincloud，配对点与个体轨迹，interaction/marginal effects，coefficient/forest，event-study/DiD，SEM/path/mediation，Likert 发散堆积，mosaic，社会网络、choropleth、Sankey 与系统综述图。

| 来源 | 支持的图形证据 |
|---|---|
| [Psychological Science submission guidance](https://www.psychologicalscience.org/publications/psychological_science/ps-submissions) | 要求效应量、CI 和关键变量分布；优先展示个体点和分布，置信区间优于模糊误差棒 |
| [APA JARS-Quant entry](https://www.equator-network.org/reporting-guidelines/journal-article-reporting-standards-for-quantitative-research-in-psychology-the-apa-publications-and-communications-board-task-force-report/) | 实验、观察、纵向、临床、SEM、Bayesian 和 Meta 的报告标准 |
| [CONSORT-SPI](https://www.equator-network.org/reporting-guidelines/consort-spi/) | 社会与心理干预试验的流程和报告语义 |
| [Beyond Bar and Line Graphs](https://journals.plos.org/plosbiology/article?id=10.1371%2Fjournal.pbio.1002128) | 703 篇论文的审查；相同均值/SE 可隐藏完全不同分布，建议完整散点与配对结构 |
| [AEA visualizing data guide](https://www.aeaweb.org/articles?id=10.1257%2Fjep.28.1.209) | 经济学领域图形设计的同行评议指南 |
| [QJE event-study example](https://academic.oup.com/qje/article/137/3/1495/6517334) | 事件时间系数、95% CI、基期与样本定义 |
| [Nature Human Behaviour network example](https://www.nature.com/articles/s41562-023-01686-7) | 社会网络实验示意、网络结构与模型架构组合 |

领域风险：Likert 是有序分类，不应只给均值；交互应画模型预测与区间，不能用“一个显著、另一个不显著”证明差异；路径箭头不自动代表因果；event-study 必须记录省略基期与聚类区间；网络布局视觉中心不等于统计中心；choropleth 警惕生态谬误；调查图记录权重、有效样本和缺失处理。

## 6. 发表规格与期刊样式模板（邀请制内测）

### 6.1 定位、口径与数据模型

发表规格应实现为用户明确选择的 `publication_profile`，与用户已经选定的 `chart_type` 正交。它负责约束画布、排版、导出和交付检查，不应改换图形类型，也不应建立“Agent 根据数据主动推荐期刊或图形”的路径。

本节只采用期刊、出版社或学会官方页面/PDF。模板名称分为两类：

- **期刊级模板**：规则能由该刊官方指南直接支持，例如 Nature、JACS、PLOS Biology。
- **刊群/出版社级模板**：作为没有更具体规则时的兜底，例如 IEEE Journals、Elsevier Default、Wiley Default；目标期刊的 Author Guidelines 永远优先。

每个配置至少保存 `profile_id`、`scope`（期刊/学会/出版社）、`workflow_stage`（初稿/修订/终稿/Extended Data）、适用期刊/刊群、来源 URL、来源发布日期/修订日期、抓取/访问日期、`requirement_level`（required/preferred/tip）、`applies_to`（矢量/照片/线稿/组合图）、成品宽高、色彩模式、字体与字号、线宽、位图分类及 DPI、矢量与字体嵌入要求、组合图标签、规则严重级别和覆盖关系。所有尺寸和 DPI 都按**最终发表尺寸**计算，不能把“文件元数据写着 300 dpi”当成有效分辨率合格；应计算 `有效 DPI = 像素数 ÷ 成品英寸数`。

### 6.2 通用发表规格

以下是跨出版社反复出现、适合先做成公共规则的要求。`自动` 表示对 PlotAgent 的结构化画布或可解析导出文件可确定校验；`半自动` 表示可以检测并给出风险，但不能替代作者判断；`提示` 表示涉及科学语义、投稿情境或人工审稿。

| 规则 | 规范化字段/检查 | 能力等级 | 建议处理 |
|---|---|---|---|
| 成品尺寸 | 单栏、1.5 栏、双栏/通栏宽度；最大高度；是否含 caption | 自动 | 明确数值超限可阻断；官方未给值时不得用产品经验值冒充规则 |
| 文件格式 | 扩展名、MIME、单页/多页、每图一文件 | 自动 | 不在官方接受列表则阻断或警告；同时保留 PlotAgent 源项目 |
| 位图有效分辨率 | 照片/半色调、组合图、线稿分别计算有效 DPI | 自动 | 低于硬门槛阻断；单纯上采样不能消除警告 |
| 矢量保真 | 线、箭头、文字是否为矢量；PDF/EPS/SVG 中是否嵌入低分辨率栅格 | 自动 | 报告每个栅格子图的有效 DPI；不能只看容器后缀 |
| 字体 | 字体族、成品字号、嵌入状态、是否转轮廓 | 自动/半自动 | 原生对象可精确检查；扁平位图只能 OCR/估计并提示 |
| 线宽与点大小 | 成品 pt、极细线、缩放后的 marker | 自动/半自动 | 矢量对象可精确检查；位图只能检查潜在断线和可读性 |
| 颜色空间 | RGB/灰度/CMYK、alpha、ICC、对比度 | 自动 | 模式和对比度可测；是否科学准确仍需作者确认 |
| 灰度与色觉可读性 | 灰度模拟、常见色觉缺陷模拟、颜色之外的线型/符号冗余 | 半自动 | 产生对比度和混淆报告，不宣称“自动证明可访问” |
| 组合图结构 | 单个 figure 文件、面板标签、标签顺序/重复、对齐与间距 | 自动/半自动 | 结构化面板可精确检查；阅读顺序和内容对应关系只能提示 |
| 图像比例尺与拼接 | scale bar 对象、物理单位映射、拼接分隔线、处理记录 | 半自动/提示 | 可检查对象是否存在；标尺真实性、图像完整性和处理合理性不能自动批准 |
| 图注科学语义 | `n`、误差定义、统计检验、缩写、颜色/符号、面板逐项说明 | 提示 | 用清单提醒并允许缺失字段标记；不能根据图形外观臆造 |
| 版权与投稿政策 | 复用许可、AI 使用披露、彩图费用、补充材料政策 | 提示 | 只提供官方链接和检查清单；由作者确认目标刊当前政策 |

通用默认值只应在没有目标期刊配置时称为“PlotAgent 安全预设”，不能称为“期刊要求”。例如：优先可编辑 PDF/SVG 源、同时导出 TIFF/PNG 预览；使用色觉友好色板；非颜色编码冗余；在 100% 成品尺寸预览；多面板使用唯一、连续标签；保留原始数据、字体和图像处理记录。

### 6.3 代表性官方模板

表中 `—` 表示该官方来源未给出统一数值，不用二手博客或经验值补齐。“双栏/通栏”统一指跨两栏的全宽成品；某些单栏排版期刊只给文本栏或页面宽度，因此按官方原词记录。

| 模板 | 单栏 / 中间宽度 / 双栏或通栏 | 最大高度 | 格式与矢量 | 彩色/灰度 | 字体与字号 | 线宽 | 位图 DPI（成品尺寸） | 组合图要求 | 官方来源与日期 |
|---|---|---|---|---|---|---|---|---|---|
| `nature-article`（Nature 主刊） | 89 mm / — / 183 mm | 170 mm，给图注留空间 | 主图优先 PDF/EPS；文字、线、箭头、标尺保持可编辑矢量；嵌入字体且不要转轮廓 | RGB；印刷时转换 CMYK；无障碍色板，避免彩色文字 | Arial/Helvetica；正文 5–7 pt；面板标签 8 pt、粗体、正体、小写 `a,b,c` | 主图页未给统一值；Extended Data 给 0.25–1 pt，不能混作所有主图硬门槛 | 照片至少 300；导出页要求/建议图像 450 以上。内测设 `<300` 阻断、`300–449` 提示 | 面板尽量按字母顺序、紧凑对齐、减少白边；标尺与文字保持独立可编辑层 | [Building and exporting panels](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/)、[Preparing figures](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/)、[Extended Data](https://research-figure-guide.nature.com/figures/extended-data-formatting-guidelines/)；页面未标发布日期，访问 2026-08-05 |
| `jacs`（Journal of the American Chemical Society） | ≤240 pt/3.33 in（84.7 mm） / 双栏可为 300–504 pt（105.8–177.8 mm） / 504 pt/7 in（177.8 mm） | 660 pt/9.167 in（232.8 mm），**含图注**，每行图注预留 12 pt | 稿件图可提交 TIFF/PDF/EPS；PDF/EPS 可保留矢量；字体需按文件要求嵌入或正确处理 | 可用彩色且不额外收费；若计划黑白/灰度发表，不应提交彩色；不得仅依赖颜色编码；文字/非文字对比度参考 4.5:1/3:1 | Helvetica/Arial；成品文字不小于 4.5 pt | 不小于 0.5 pt | 黑白线稿 1200；灰度 600；RGB 彩色 300 | 一个 figure 的各部分应完成标注和装配；图注置于图下并能独立理解，符号优先在图内给 key | [JACS Author Guidelines](https://researcher-resources.acs.org/publish/author_guidelines?coden=jacsat)，更新 2026-07-03；[ACS accepted software](https://pubs.acs.org/page/4authors/submission/software.html)，访问 2026-08-05 |
| `ieee-journals`（IEEE 期刊刊群） | 3.5 in/88.9 mm / — / 7.16 in/182 mm | 8.8 in/220 mm | PS/EPS/PDF 为矢量；也接受 PNG/TIFF；PDF/EPS/PS 嵌入字体或转轮廓 | 彩色和灰度位图均可；必须用灰度打印测试，并以线型/符号补充颜色 | Helvetica、Times New Roman、Arial、Cambria、Symbol；成品约 9–10 pt | IEEE 通用网页未给统一数值，只要求粗线和可读；不硬编码 | 彩色/灰度 >300；黑白线稿 >600 | 通用规则要求多部件合并；代表性 IEEE 模板使用居中于子图下方的 8 pt Times New Roman `(a) (b) (c)`，具体期刊可覆盖 | [Resolution and size](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/resolution-and-size/)、[File formatting](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/file-formatting/)、[Accessible line graphs](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/)；页面未标发布日期，访问 2026-08-05 |
| `plos-biology`（PLOS Biology） | 最小 2.63 in/66.8 mm；文本栏建议 ≤5.2 in/132 mm / — / 最大 7.5 in/190.5 mm | 8.75 in/222.3 mm，不含图注 | TIFF 或 EPS；EPS 嵌入字体或转轮廓；TIFF 扁平、LZW、无 alpha | 仅 RGB 8 bit/channel 或灰度 | Arial、Times 或 Symbol，8–12 pt | 通用规则未给硬值；SigmaPlot 专项示例为 0.2 mm，不提升为全局门槛 | 300–600；小字/多图组合建议 600 | 多面板必须合成一个页面、一个文件；图注用 `(A)` 或 `(a)` 逐面板说明，全部符号和缩写须定义 | [PLOS Biology Figures](https://journals.plos.org/plosbiology/s/figures)；页面未标发布日期，访问 2026-08-05 |
| `physical-review`（APS Physical Review 刊群） | 85 mm / 允许 1.5 栏但未给统一数值 / 允许 2 栏但未给统一数值 | —，须查目标刊 | 偏好 PS/EPS/JPG/PNG；照片用高分辨率 JPG/PNG；color-online-only 的生产文件需 PS/EPS | 使用无障碍配色；线上彩色/印刷灰度必须同时可辨，并以线型等辅助编码 | 成品最小大写字母/数字高 ≥2 mm | ≥0.18 mm/0.5 pt；数据点直径 ≥1 mm | 只对扫描图建议 600 以上，不是所有原生图的 DPI 硬门槛 | 面板用 `(a),(b)`；一个图注说明各面板；多面板尽可能合为一个文件；轴给物理量和括号内单位 | [APS Style Basics](https://journals.aps.org/authors/style-basics)；页面未标发布日期，访问 2026-08-05 |
| `aip-journals`（AIP Publishing，JMP 除外） | 3.37 in/85 mm / — / 6.69 in/170 mm | 8.25 in/211 mm | SVG/EPS/PS/TIFF/PDF/JPEG/PNG；生产阶段优先 PS/EPS/TIFF，PDF 仅在首选格式不可得时使用；嵌入字体 | 在线彩色免费、印刷通常灰度；只交一个版本并保证灰度可读；彩色用 RGB | 图例/标签 ≥8 pt | ≥0.5 pt | 黑白线稿 600；灰度半色调 264；组合 600；在线彩色 300；PDF 内照片 600、线稿 1200 | 面板用 `(a),(b)`；全部视觉内容必须提供 alt text；JMP 是单栏例外，最大宽仍为 170 mm | [AIP Author Instructions](https://publishing.aip.org/resources/researchers/author-instructions/)；页面未标发布日期，访问 2026-08-05 |
| `elsevier-default`（Elsevier 出版社兜底） | 90 mm / 140 mm / 190 mm | —，须查目标刊 | EPS/PDF 优先矢量；TIFF 用于位图；JPEG 可用于照片；嵌入字体 | RGB 优先；黑白印刷须验证灰度可辨；印刷彩图和费用因刊而异 | Arial/Helvetica、Courier、Symbol、Times/Times New Roman；通常 7 pt，角标不小于 6 pt | 推荐 0.25 pt，绝对最小 0.1 pt；主要数据线约 1 pt | 半色调 300；组合 500；线稿 1000 | 通用页不统一规定面板字母；要求每个 figure 为完整文件、图注与图稿分离，具体标签按目标刊覆盖 | [Artwork sizing](https://www.elsevier.com/en-au/about/policies-and-standards/author/artwork-and-media-instructions/artwork-sizing)、[Artwork overview](https://www.elsevier.com/en-gb/about/policies-and-standards/author/artwork-and-media-instructions/artwork-overview)、[Artwork FAQ](https://www.elsevier.com/about/policies-and-standards/author/artwork-and-media-instructions/artwork-faq)；页面未标发布日期，访问 2026-08-05 |
| `wiley-default`（Wiley 出版社兜底） | 小图 80 mm / — / 大图 180 mm；官方用 small/large，不等同所有刊的固定栏宽 | —，须查目标刊 | 线稿优先 EPS/PDF；图像优先 TIFF/PNG/EPS；每个 figure 单独文件 | 该 PDF 未给统一 RGB/灰度规则，目标刊覆盖 | 该 PDF 未给统一字体族/字号 | 未统一规定 | 同行评审：线稿 600、图像 300；录用后：线稿 600–1000、图像 300 | 图注按阿拉伯数字顺序、解释缩写/符号；该 PDF 未统一规定面板字母样式 | [Wiley Guidelines for the Preparation of Figures](https://authorservices.wiley.com/asset/photos/electronic_artwork_guidelines.pdf)，更新 2016-09-01，访问 2026-08-05 |

Nature 的初稿页面约用 90/180 mm，而上述 `nature-article` 是最终制作的 89/183 mm。产品必须以 `workflow_stage` 拆分，不能把初稿、终稿、Extended Data 的尺寸和格式规则合并为一个互相冲突的模板。PLOS Biology 的 66.8/190.5 mm 是总允许宽度范围，不应擅自改名为“单栏/双栏”。纯矢量图不执行无意义的 DPI 失败，只检查其中嵌入位图的有效 DPI。

### 6.4 内测首批模板优先名单

| 优先 | 模板 | 原因与上线边界 |
|---|---|---|
| P0-1 | Nature 主刊 | 规格公开且严格，覆盖生命、医学、材料、物理、地球环境等多领域；可自动校验字段完整，适合验证端到端能力 |
| P0-2 | JACS | 化学代表性强；线稿/灰度/彩色 DPI 分层明确，栏宽与最大深度明确；化学结构样式仍需单独提示，不由普通图表主题替代 |
| P0-3 | IEEE Journals | 覆盖工程、电子、计算机；栏宽、格式、DPI、字体和灰度可读性明确；具体 Transactions 的面板与稿件模板可覆盖通用配置 |
| P0-4 | Physical Review | 物理学代表；当前 Style Basics 对 85 mm、字高、数据点、线宽、格式和灰度可读性给出可编码规则；1.5/2 栏精确宽度仍留空 |
| P0-5 | PLOS Biology | 生命科学开放获取代表；文件、像素尺寸、颜色、字体、组合图和图像诚信说明细，适合测试栅格工作流 |
| P0-6 | AIP Journals | 补充应用物理、化学物理、流体和仪器；尺寸、格式、分内容 DPI、alt text 与印刷灰度规则完整，JMP 作为显式例外 |
| P0-7 | Elsevier Default | 学科覆盖广，90/140/190 mm、三档 DPI 和线宽便于自动化；必须显示“出版社兜底，目标刊指南优先”，不能伪装成某一本期刊模板 |
| P1-1 | Wiley Default | 可覆盖 Advanced Materials 等 Wiley 刊群的初始布局，但官方公共 PDF 较旧且缺字体、线宽、色彩和最大高度，先作为带黄色提示的兜底配置 |

P0 的目标不是声称“已获期刊认证”，而是提供**来源可追溯的成品尺寸预设 + 规则检查报告**。每次输出报告应显示模板版本、官方链接、访问日期、通过项、警告项、未能自动验证项；规则页超过设定复核周期或目标期刊另有更新时，模板应进入“需复核”状态。

### 6.5 自动校验与仅提示的产品边界

可在内测首批稳定实现为自动校验的规则：画布宽高、单位换算、文件扩展名/MIME、页数、色彩空间、透明通道、图像像素与有效 DPI、字体对象的字体族/字号/嵌入状态、矢量对象的线宽、栅格嵌入、面板标签的存在/唯一/连续、文件大小和命名模式。若图形由 PlotAgent 原生对象生成，还可精确检查轴标题/单位字段、图例、标尺对象和面板阅读顺序。

只能提示或至多半自动检查的规则：配色是否科学准确、灰度/色觉模拟是否仍能表达全部语义、面板内容是否按逻辑顺序、标尺是否与原始采集标定一致、拼接是否合规、亮度/对比度处理是否误导、图注是否完整说明 `n`/误差/统计检验、第三方版权、AI 使用披露、彩图费用和投稿栏目例外。系统不得用一个绿色“全部通过”掩盖这些人工责任。

模板检查结果建议分三档：`阻断` 仅用于官方明确且机器可确定的硬错误；`警告` 用于出版风险、来源冲突和兜底模板；`提示` 用于科学语义和人工确认。原生 SVG/PDF 能检查的对象，在用户上传扁平 PNG/TIFF 后往往只能降级为启发式提示，这一能力差异必须在结果中可见。

## 7. 去重后的完整图形分类体系

以下条目把视觉相近但语义不同的图分开（例如普通瀑布桥图、光谱瀑布和肿瘤 waterfall），把只改变颜色或装饰的样式变体合并。参数列只列决定科学含义的核心项；字体、颜色、线宽、栏宽等通用样式由统一主题系统管理。

### 7.1 核心高频 `K`

| ID | 中英文名 | 类别 | 数据形状 | 核心参数 | 典型学科 | 批量/组合 | PNG/SVG/OPJU | 优先级 |
|---|---|---|---|---|---|---|---|---|
| K01 | 折线图 / Line plot | 时间/关系 | `XY/XYY` | 排序、连接、缺失值、轴尺度 | 全学科 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K02 | 线点图 / Line + symbol | 时间/关系 | `XY/XYY` | marker、连接规则、重复/系列 | 全学科 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K03 | 散点图 / Scatter plot | 关系 | `XY + group` | marker、透明度、抖动、分组 | 全学科 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K04 | 气泡/颜色映射散点 / Bubble & colormap scatter | 多变量关系 | `XY + size/color` | 面积尺度、色板、范围、图例 | 材料、环境、生信、数据科学 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K05 | 回归散点与置信带 / Regression plot | 模型关系 | `XY + group` | 模型、变换、CI、稳健/加权、原始点 | 全学科 | △ / 层·面 | ✓/✓/原 | P0 |
| K06 | 点估计与误差棒 / Point estimate + error bar | 估计比较 | `category + estimate + lower/upper` | SD/SE/CI、置信水平、n、方向 | 全学科 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K07 | 误差带/置信带 / Error ribbon | 不确定性 | `X + center + lower/upper` | 区间定义、透明度、边界、样本数 | 全学科 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K08 | 柱/条图 / Column & bar | 比较 | `category + value` | 基线、方向、排序、标签、误差语义 | 全学科 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K09 | 分组柱/条图 / Grouped bar | 比较 | `category × group + value` | 组序、间距、误差、原始点叠加 | 全学科 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K10 | 堆积柱/条图 / Stacked bar | 组成 | `category × component + value` | 堆积顺序、正负值、总量、标签 | 全学科 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K11 | 百分比堆积图 / 100% stacked bar | 组成 | `category × component + value` | 分母、缺失、归一化、组件顺序 | 医学、生态、调查、组学 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K12 | 单变量点图/条带图 / Dot & strip plot | 分布比较 | `long: value + group` | jitter、透明度、配对 ID、点重叠 | 生医、心理、材料 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K13 | 箱线图 / Box plot | 分布比较 | `Y/long` | 分位数、须、异常点、notch、原始点 | 全学科 | △ / 层·面 | ✓/✓/原 | P0 |
| K14 | 小提琴图 / Violin plot | 分布比较 | `Y/long` | KDE 带宽、裁剪、宽度缩放、内嵌统计 | 生医、心理、数据科学 | △ / 层·面 | ✓/✓/原 | P0 |
| K15 | 直方图 / Histogram | 分布 | `Y + optional group` | bin 宽/边界、频数/密度、堆叠、范围 | 全学科 | △ / 层·面 | ✓/✓/原 | P0 |
| K16 | 核密度图 / KDE density | 分布 | `Y + group` | kernel、带宽、边界、归一化 | 统计、生医、社会、数据科学 | △ / 层·面 | ✓/✓/原 | P0 |
| K17 | 经验累积分布 / ECDF/CCDF | 分布 | `Y + group` | 累积方向、删失/权重、置信带 | 物理、工程、生医、社会 | △ / 层·面 | ✓/✓/原 | P0 |
| K18 | 面积图 / Area plot | 时间/组成 | `XY/XYY` | 基线、透明度、正负填充、堆积方式 | 环境、经济、信号 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K19 | 日期时间折线图 / Date-time line plot | 时间 | `time + series_1..series_N` | 时区、毫秒精度、缺失；不做排序/聚合/重采样 | 全学科 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K20 | 热图 / Heatmap | 矩阵 | `matrix/XYZ/long` | 聚合、色域、缺失、标准化、标签 | 全学科 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K21 | 相关矩阵图 / Correlation matrix | 矩阵/关系 | `wide` 或相关矩阵 | Pearson/Spearman、显著性、多重校正、上/下三角 | 全学科 | △ / 面 | ✓/✓/原 | P0 |
| K22 | 等高线/填色等值图 / Contour | 二维场 | `XYZ/grid` | gridding、插值、level、边界、色板、实测点 | 地学、物理、材料、工程 | ✓ / 层·面 | ✓/✓/原 | P0 |
| K23 | 科学图像面板 / Scientific image panel | 图像 | `image/volume + scale/ROI/channel` | 比例尺、通道、强度范围、ROI、处理历史 | 生医、材料、地学、工程 | △ / 面 | ✓/SVG△/嵌 | P0 |
| K24 | 分面/Trellis / Faceted plot | 布局 | `long + facet variable` | 行列、共享轴、排序、自由尺度、共享图例 | 全学科 | ✓ / 面 | ✓/✓/原 | P0 |
| K25 | 多面板复合图 / Multi-panel figure | 布局 | 多个图/图像/示意对象 | 栏宽、网格、面板字母、对齐、共享图例、混合导出 | 全学科 | △ / 面 | ✓/SVG△/组 | P0 |

### 7.2 扩展常用 `X`

| ID | 中英文名 | 类别 | 数据形状 | 核心参数 | 典型学科 | 批量/组合 | PNG/SVG/OPJU | 优先级 |
|---|---|---|---|---|---|---|---|---|
| X01 | 阶梯图 / Step plot | 时间/事件 | `XY` | before/after/mid、缺失、事件点 | 生存、信号、经济 | ✓ / 层·面 | ✓/✓/原 | P1 |
| X02 | 垂线图 / Drop Line | 连续关系 | `XY` | 垂线落到坐标框底部 X 轴、点/线尺度 | 信号、材料、工程 | ✓ / 层·面 | ✓/✓/原 | P1 |
| X03 | Origin 棒棒糖图 / Origin Lollipop | 多系列比较 | `category + 2..n numeric series` | 系列顺序、逐行连接、点/线尺度；两系列形成哑铃效果 | 临床、社会、benchmark | ✓ / 层·面 | ✓/✓/原 | P1 |
| X04 | 斜率图 / Slope graph | 配对/少时点 | `entity × 2..n time` | 时点顺序、连接、标签避让、差值 | 社会、经济、医学 | ✓ / 面 | ✓/✓/组 | P1 |
| X05 | 蜂群图 / Beeswarm | 分布比较 | `long` | 点布局、间距、大小、分组 | 生医、心理、材料 | △ / 层·面 | ✓/✓/原 | P1 |
| X06 | 云雨图 / Raincloud | 分布比较 | `long` | half-violin、box/interval、jitter、配对 | 生医、心理 | △ / 面 | ✓/✓/组 | P1 |
| X07 | 山脊图 / Ridgeline | 多分布 | `value + group/order` | KDE 带宽、重叠、归一化、组序 | 组学、环境、社会 | △ / 面 | ✓/✓/原 | P1 |
| X08 | 箱须增强图 / Boxen/letter-value | 多分布 | `long` | 分位层数、尾部、异常点、原始点 | 大样本数据科学 | △ / 面 | ✓/✓/组 | P1 |
| X09 | 浮动条形图 / Floating Bar | 区间 | `category + start + end` | 有序边界、方向、区间标签 | 工程、临床、计划 | ✓ / 层·面 | ✓/✓/原 | P1 |
| X10 | 甘特/泳道时间线 / Gantt & timeline | 时间区间 | `entity + start + end + status` | 时间尺度、重叠、里程碑、泳道顺序 | 临床、工程、计算机 | △ / 面 | ✓/✓/组 | P1 |
| X11 | 桥图/瀑布图 / Bridge waterfall | 累计变化 | `category + delta/total` | 起点、累计、subtotal、正负色 | 经济、工程、质量 | ✓ / 面 | ✓/✓/原 | P1 |
| X12 | 子弹图 / Bullet chart | 目标比较 | `item + actual + target + ranges` | 目标线、定性区间、统一尺度 | 工程、项目监控 | ✓ / 面 | ✓/✓/原 | P1 |
| X13 | 人口金字塔/蝴蝶图 / Population pyramid | 镜像比较 | `category × side + value` | 共享零点、比例/计数、年龄序 | 流行病、人口、社会 | ✓ / 面 | ✓/✓/原 | P1 |
| X14 | Mosaic/列联图 / Mosaic plot | 分类关联 | 交叉频数表 | 面积/残差着色、类别顺序、权重 | 社会、生态、医学 | △ / 独·面 | ✓/✓/原 | P1 |
| X15 | 散点矩阵/Pair plot | 多变量 | `wide` | 上/下三角、对角分布、相关/拟合、抽样 | 数据科学、统计、生信 | △ / 面 | ✓/✓/原 | P1 |
| X16 | Hexbin/二维密度点图 / Hexbin & 2D density | 高密散点 | `XY` | bin/带宽、计数/密度、色域、边界 | 物理、数据科学、组学 | △ / 层·面 | ✓/✓/原 | P1 |
| X17 | 边际分布图 / Marginal scatter | 关系+分布 | `XY + group` | 边际 histogram/KDE/box、共享范围 | 统计、生医、社会 | △ / 面 | ✓/✓/原 | P1 |
| X18 | Q–Q/概率图 / Q–Q & probability plot | 分布诊断 | `Y` 或两样本 | 分布族、参数估计、参考线、CI | 统计、工程、物理 | △ / 面 | ✓/✓/原 | P1 |
| X19 | Bland–Altman 图 / Agreement plot | 方法一致性 | 两个配对测量列 | mean difference、LoA、CI、重复测量 | 医学、计量、心理 | △ / 面 | ✓/✓/原 | P1 |
| X20 | ROC 曲线 / ROC curve | 分类评估 | `label + score` | positive class、AUC/CI、阈值、验证集 | 医学、计算机 | △ / 面 | ✓/✓/原 | P1 |
| X21 | PR 曲线 / Precision–Recall curve | 分类评估 | `label + score` | 阳性基线、AP/CI、阈值、验证集 | 医学、计算机 | △ / 面 | ✓/✓/组 | P1 |
| X22 | 校准/可靠性图 / Calibration plot | 概率评估 | `label + probability` | bin/smoother、CI、样本量、Brier/ECE | 医学、计算机 | △ / 面 | ✓/✓/组 | P1 |
| X23 | 双 Y 轴图 / Dual-axis plot | 多量纲时间 | 共享 X 的两组 Y | 轴归属、单位、范围、零点、线型冗余 | 工程、化学、环境 | ✓ / 多层 | ✓/✓/原 | P1，强警告 |
| X24 | Pareto 图 / Pareto chart | 排名/质量 | `category + count/cost` | 降序、累计百分比、阈值 | 工程、质量、管理 | ✓ / 多层 | ✓/✓/原 | P1 |
| X25 | 平行坐标图 / Parallel coordinates | 多变量 | `wide` | 归一化、轴序、线透明、聚类/高亮 | 数据科学、社会、材料 | △ / 独·面 | ✓/✓/原 | P1 |
| X26 | Sankey/Alluvial / 桑基与冲积图 | 流/转移 | `edge list` 或多阶段类别+权重 | 节点序、流宽、方向、颜色、守恒 | 能源、生态、社会、组学 | △ / 独·面 | ✓/✓/原 | P1 |
| X27 | 弦图 / Chord diagram | 关系矩阵 | 矩阵或 `edge list` | 节点序、方向、阈值、弦透明 | 组学、生态、贸易 | △ / 独·面 | ✓/✓/原 | P1 |
| X28 | 网络图 / Network graph | 图结构 | 节点表 + 边表 | 布局、权重、方向、阈值、seed、标签 | 社会、组学、计算机 | △ / 独·面 | ✓/✓/原 | P1 |
| X29 | UpSet 图 / UpSet plot | 集合交集 | 二元 membership 矩阵 | 集合顺序、交集阈值、计数/比例 | 组学、文献、数据科学 | △ / 面 | ✓/✓/组 | P1 |
| X30 | Venn/Euler 图 / Venn & Euler | 少集合交集 | 2–4 集合或区域计数 | 集合数、面积拟合、标签 | 生物、综述 | △ / 独 | ✓/✓/组 | P1，限少集合 |
| X31 | 层级矩形/圆形图 / Treemap, sunburst, circle packing | 层级 | `hierarchy` | 面积、层级深度、排序、标签 | 生态、分类、软件结构 | △ / 独·面 | ✓/✓/原 | P1 |
| X32 | 雷达图 / Radar/spider | 多指标比较 | 对象 × 指标矩阵 | 指标归一化、轴序、量程、填充 | 工程性能、少对象比较 | △ / 独 | ✓/✓/原 | P1，非默认 |
| X33 | 极坐标图 / Polar plot | 周期/方向 | `theta + r (+group)` | 角度零点/方向、周期、径向尺度 | 物理、天文、行为、气象 | ✓ / 专用层 | ✓/✓/原 | P1 |
| X34 | 三元图 / Ternary plot | 组成 | 三个非负组成列 | 归一化、三轴顺序、边界、点编码 | 化学、材料、地学 | ✓ / 专用层 | ✓/✓/原 | P1 |
| X39 | 线条序列图 / Line Series | 多列比较 | `2..n numeric series` | 列顺序、逐行线点连接、动态系列数 | 全学科 | ✓ / 层·面 | ✓/✓/原 | P1 |
| X40 | 前后对比图 / Before-After | 成对比较 | `paired numeric series` | 每相邻两列成对连接；奇数末列仅显示散点 | 临床、社会、工程 | ✓ / 层·面 | ✓/✓/原 | P1 |

### 7.3 学科专用 `S`

| ID | 中英文名 | 类别 | 数据形状 | 核心参数 | 典型学科 | 批量/组合 | PNG/SVG/OPJU | 优先级 |
|---|---|---|---|---|---|---|---|---|
| S01 | Kaplan–Meier 生存曲线 / KM curve | 生存分析 | `time,event/censor,group` | 删失、风险人数、CI、检验、随访范围 | 医学、生物、可靠性 | △ / 面 | ✓/✓/原 | P1 |
| S02 | 累计发生/竞争风险 / Cumulative incidence | 生存分析 | `time,event type,group` | 竞争事件、删失、CI、Gray 检验 | 医学 | △ / 面 | ✓/✓/组 | P2 |
| S03 | 泳道/Swimmer plot | 患者时间线 | `subject,start,end,status,event` | 排序、持续时间、事件 marker、删失 | 肿瘤、临床 | △ / 面 | ✓/✓/组 | P2 |
| S04 | 肿瘤 waterfall/spider / Tumour response plots | 个体疗效 | `subject,time,response` | 最佳变化、基线、RECIST 阈值、个体轨迹 | 肿瘤学 | △ / 面 | ✓/✓/组 | P2 |
| S05 | 剂量–反应/IC50/EC50 / Dose–response | 非线性拟合 | `dose + response + replicate/group` | 4/5PL、上下平台、Hill slope、CI、log dose | 药理、毒理、生物 | △ / 层·面 | ✓/✓/原 | P1 |
| S06 | 生长/细胞活性曲线 / Growth & viability | 重复时间 | `time/dose + replicate + group` | 重复层级、归一化、区间、基线 | 细胞、生物、微生物 | △ / 面 | ✓/✓/原 | P1 |
| S07 | 火山图 / Volcano plot | 组学差异 | `feature,log2FC,p/q` | FDR、FC 阈值、标签、对称 x、零值处理 | 转录组、蛋白组 | △ / 面 | ✓/✓/原 | P1 |
| S08 | MA 图 / MA plot | 组学差异 | `feature,mean abundance,logFC` | normalization、trend、FDR、低丰度 | 转录组、蛋白组 | △ / 面 | ✓/✓/原 | P2 |
| S09 | 富集 dot/bar/lollipop / Enrichment plots | 通路富集 | `term,ratio/count,p/q,group` | q 值、gene ratio、size/color、条目排序/去冗余 | 生信 | △ / 面 | ✓/✓/原 | P1 |
| S10 | GSEA 运行富集图 / GSEA running score | 排序统计 | 基因排序 + score + hits | ES/NES、命中线、leading edge、FDR | 生信 | △ / 面 | ✓/✓/组 | P2 |
| S11 | 聚类表达热图 / Clustered expression heatmap | 组学矩阵 | feature × sample + annotations | 标准化、距离、linkage、树切割、色域 | 组学、临床 | △ / 面 | ✓/✓/原 | P1 |
| S12 | 单细胞 dot plot / Single-cell dot plot | 双编码矩阵 | cell type × gene 的 mean + fraction | 点面积、表达色、尺度、基因/群序 | 单细胞、生信 | △ / 面 | ✓/✓/组 | P2 |
| S13 | UMAP/t-SNE embedding | 降维 | `sample + dim1 + dim2 + label` | 方法参数、随机种子、预处理、点密度 | 单细胞、数据科学 | △ / 面 | ✓/✓/原 | P1 |
| S14 | Manhattan 图 / Manhattan plot | 基因组关联 | `chr,pos,p (+effect)` | -log10P、基因组/提示阈值、交替色、标签 | 遗传学 | △ / 面 | ✓/✓/原 | P2 |
| S15 | Circos/基因组轨道 / Circos & genome tracks | 基因组区间 | 区间、连接、signal tracks、染色体 | 坐标版本、轨道序、缩放、连接阈值 | 基因组学 | △ / 独·面 | ✓/✓/组 | P2 |
| S16 | 序列 Logo / Sequence logo | 序列位点矩阵 | aligned sequences / PWM | 信息量/概率、字母表、背景、位点编号 | 分子生物、蛋白 | △ / 独 | ✓/✓/嵌 | P2 |
| S17 | 系统发育树 / Phylogenetic tree | 树 | Newick/tree + tip metadata | rooted、branch length、layout、clade annotation | 进化、微生物 | △ / 独·面 | ✓/✓/组 | P2 |
| S18 | 流式细胞术密度/门控 / Flow cytometry | 事件点云 | event × marker + gate hierarchy | 变换、补偿、密度、门、百分比 | 免疫、生物 | △ / 面 | ✓/✓/组 | P2 |
| S19 | CONSORT/STARD 流程图 / Trial/diagnostic flow | 报告流程 | 有向阶段节点 + count/reason | 规范版本、阶段、排除原因、计数守恒 | 临床、诊断 | △ / 独 | ✓/✓/嵌 | P1 |
| S20 | PRISMA 流程图 / Systematic-review flow | 报告流程 | 来源/阶段节点 + count/reason | 新/更新综述、来源类型、排除原因 | 系统综述 | △ / 独 | ✓/✓/嵌 | P1 |
| S21 | 森林/系数图 / Forest & coefficient plot | 效应估计 | `label,effect,lower,upper,weight/group` | 效应尺度、对数轴、无效线、权重、汇总 | 医学、Meta、社会、经济 | △ / 面 | ✓/✓/原 | P1 |
| S22 | 漏斗图 / Funnel plot | Meta 诊断 | `effect,SE/precision` | y 轴定义、轮廓显著区、检验、研究数 | Meta 分析 | △ / 面 | ✓/✓/原 | P2，强警告 |
| S23 | Nomogram/列线图 | 临床预测 | 模型系数、变量刻度、总分映射 | 模型版本、变量范围、校准、结局时间 | 医学 | △ / 独 | ✓/✓/组 | P2 |
| S24 | 显微/病理/凝胶组合图 / Bioimage composite | 图像+定量 | image/channel/ROI + summary/raw values | 同尺度强度、比例尺、拼接、原图、定量链接 | 生医 | △ / 面 | ✓/SVG△/嵌 | P1 |
| S25 | 连续谱图 / NMR, IR, Raman, UV–Vis spectra | 光谱 | `x + intensity + sample` | x 方向/单位、基线、归一化、offset、峰标注 | 化学、材料、物理 | ✓ / 层·面 | ✓/✓/原 | P1 |
| S26 | 质谱/棒谱 / Mass spectrum | 峰谱 | `m/z + intensity + annotation` | centroid/profile、相对强度、同位素/碎片标签 | 化学、生物 | ✓ / 层·面 | ✓/✓/原 | P2 |
| S27 | 色谱图 / Chromatogram | 分离信号 | `retention time + signal + channel` | 检测器、基线、积分、峰、对齐、全范围 | 化学、药学 | ✓ / 层·面 | ✓/✓/原 | P1 |
| S28 | 校准/滴定曲线 / Calibration & titration | 定量拟合 | `concentration/equivalent + response` | 模型、权重、LOD/LOQ、残差、CI | 分析化学、生物 | △ / 面 | ✓/✓/原 | P1 |
| S29 | 反应坐标/能量剖面 / Reaction-energy profile | 机理/能量 | state/coordinate + relative energy | 零点、单位、温度、溶剂、计算层级、TS | 计算/物理化学 | △ / 独·面 | ✓/✓/组 | P2 |
| S30 | 化学结构/反应/催化循环 / Chemical scheme | 结构示意 | atom/bond graph + conditions/yield | 立体化学、键规范、条件、产率、原始结构文件 | 化学 | △ / 面 | ✓/✓/嵌 | P1 |
| S31 | XRD/SAXS/WAXS/SAED 图 / Diffraction plot | 衍射 | `angle/q + intensity` 或 2D image | 背景、归一化、峰宽、参考卡、offset、波长 | 材料、化学、地学 | ✓ / 层·面 | ✓/SVG△/原 | P1 |
| S32 | 循环伏安/极化曲线 / CV & polarization | 电化学 | `potential + current (+cycle/group)` | 扫速、方向、iR 校正、面积/质量归一化 | 电化学、材料 | ✓ / 层·面 | ✓/✓/原 | P1 |
| S33 | 充放电/倍率/循环图 / GCD, rate & cycling | 储能性能 | time/cycle/rate + voltage/capacity/efficiency | 载量、倍率、面积/质量口径、循环、效率 | 电池、材料 | ✓ / 面 | ✓/✓/原 | P1 |
| S34 | Nyquist 图 / Nyquist plot | 复阻抗 | `frequency,Z',-Z''` | 频率方向、等比例轴、拟合、等效电路、残差 | 电化学、控制、材料 | △ / 面 | ✓/✓/原 | P1 |
| S35 | Bode 图 / Bode plot | 频域 | `frequency,magnitude,phase` | log f、幅值单位、相位约定、双面板 | 控制、电化学、信号 | ✓ / 面 | ✓/✓/原 | P1 |
| S36 | Tafel/Arrhenius 图 / Tafel & Arrhenius | 线性化动力学 | log current–overpotential；1/T–ln k | 拟合区间、校正、单位、权重、CI | 电化学、化学、材料 | △ / 面 | ✓/✓/原 | P1 |
| S37 | 应力–应变/载荷–位移 / Stress–strain | 力学曲线 | strain/displacement + stress/load | engineering/true、试样几何、速率、循环、区间 | 材料、工程 | ✓ / 面 | ✓/✓/原 | P1 |
| S38 | S–N/Paris 疲劳图 / Fatigue & crack-growth | 可靠性曲线 | cycles/stress；ΔK/da/dN + censor/run-out | log 轴、run-out、拟合区间、环境、CI | 材料、机械 | △ / 面 | ✓/✓/原 | P2 |
| S39 | DSC/TGA/DTA 热分析 / Thermal analysis | 温度过程 | temperature/time + heat flow/mass | 升温速率、气氛、基线、峰/失重、归一化 | 材料、化学 | ✓ / 面 | ✓/✓/原 | P2 |
| S40 | 相图/稳定区图 / Phase diagram | 参数空间 | 2–3 参数 + phase/order parameter | 边界来源、实测点、插值、温压/组成、相标签 | 物理、化学、材料 | △ / 面 | ✓/✓/原 | P1 |
| S41 | 能带与 DOS / Band structure & density of states | 电子结构 | k-path + energy + weight；energy + DOS | k 路径、费米零点、展宽、投影、晶胞 | 物理、材料 | △ / 面 | ✓/✓/组 | P2 |
| S42 | 晶体/ORTEP/晶胞图 / Crystal structure | 3D 结构 | atom coordinates + bonds + symmetry | space group、概率椭球、视角、晶胞、CIF | 化学、材料 | △ / 面 | ✓/SVG△/嵌 | P2 |
| S43 | EBSD/IPF/Pole figure | 取向/图像 | spatial orientation map / orientation samples | 晶体对称、色键、相、置信度、投影 | 材料、地学 | △ / 面 | ✓/SVG△/组 | P2 |
| S44 | Ashby/Ragone 性能图 / Performance trade-off | 多指标关系 | item + metric x + metric y + class | log 轴、边界、口径一致、类别、文献来源 | 材料、储能 | △ / 面 | ✓/✓/原 | P2 |
| S45 | 点/线/面专题地图 / Thematic map | 地理 | `geo geometry + attributes + CRS` | CRS/投影、比例尺、方向、分类、底图、来源 | 地学、环境、社会 | △ / 面 | ✓/SVG△/组 | P1 |
| S46 | 栅格/不确定性地图 / Raster & uncertainty map | 地理场 | georeferenced grid + uncertainty/mask | CRS、色域、分辨率、插值、遮罩、不确定性 | 地学、遥感、环境 | △ / 面 | ✓/SVG△/组 | P1 |
| S47 | 轨迹/路径地图 / Trajectory map | 时空路径 | `id,time,lon,lat (+value)` | 投影、方向、速度/时间编码、断点、简化 | 海洋、气象、生态、交通 | △ / 层·面 | ✓/SVG△/组 | P2 |
| S48 | 剖面/Transect / Cross-section | 距离/纬度 × 深度/高度场 | `distance,z,value` 或 grid | 竖向方向、地形/海底、插值、采样点 | 地质、海洋、大气 | △ / 面 | ✓/✓/原 | P1 |
| S49 | Hovmöller/时空图 / Hovmöller | 时间—空间场 | time × longitude/latitude/distance matrix | 聚合、异常基准、色域、方向、缺失 | 气候、海洋、信号 | ✓ / 面 | ✓/✓/原 | P2 |
| S50 | 水文过程图 / Hydrograph & hyetograph | 事件时间 | time + discharge/stage/rainfall | 双面板/倒置降雨、基流、事件窗、单位 | 水文、环境 | ✓ / 面 | ✓/✓/原 | P2 |
| S51 | 风玫瑰图 / Wind rose | 方向频率 | direction + speed 或 binned counts | 扇区、speed bin、归一化、北向/角度 | 气象、环境、建筑 | △ / 独·面 | ✓/✓/原 | P2 |
| S52 | Taylor/Target diagram | 模型评估 | model + correlation + SD + RMSE/bias | reference、归一化、符号、指标定义 | 气候、环境、模拟 | △ / 独·面 | ✓/✓/组 | P2 |
| S53 | 集合 plume/spaghetti/fan / Ensemble forecast | 不确定性时间 | time × member/scenario/quantile | 成员透明、分位带、基准、情景、成员数 | 气候、经济、预测 | ✓ / 面 | ✓/✓/原 | P1 |
| S54 | Piper/Durov/Stiff/Schoeller 水化学图 | 组成/专用坐标 | 离子浓度 + sample ID (+location) | 当量归一化、离子次序、TDS、投影 | 水文地球化学 | △ / 独·面 | ✓/✓/原 | P2 |
| S55 | 根轨迹图 / Root locus | 控制分析 | transfer function poles/zeros + gain path | 增益、稳定区、渐近线、阻尼/频率网格 | 控制工程 | △ / 独·面 | ✓/✓/组 | P2 |
| S56 | Smith 图 / Smith chart | 射频复量 | complex reflection/impedance + frequency | impedance/admittance、归一化、频率方向 | 射频、微波 | △ / 独·面 | ✓/✓/原 | P2 |
| S57 | 系统/控制/P&ID/流程示意 / Engineering schematic | 结构流程 | component nodes + typed connections | 标准符号、信号/物料方向、层级、版本 | 工程、计算机 | △ / 独·面 | ✓/✓/嵌 | P1 |
| S58 | DOE 主效应/交互图 / Main effects & interactions | 实验设计 | factor levels + response + replicate | 设计类型、均值/CI、因子顺序、交互 | 工程、农业、材料 | △ / 面 | ✓/✓/原 | P2 |
| S59 | Weibull/可靠度概率图 / Weibull reliability | 可靠性 | failure time + censor + group | 分布族、shape/scale、删失、CI、拟合检验 | 工程、材料 | △ / 面 | ✓/✓/原 | P2 |
| S60 | 学习曲线 / Learning curve | 模型训练 | epoch/sample size + train/valid metric + seed | 多 seed、区间、early stop、split、metric | 计算机、数据科学 | △ / 面 | ✓/✓/原 | P1 |
| S61 | 混淆矩阵 / Confusion matrix | 分类评估 | true class × predicted class counts | count/row/column normalization、class order、threshold | 计算机、医学 | ✓ / 面 | ✓/✓/原 | P1 |
| S62 | Critical difference diagram | 多数据集比较 | method ranks across datasets | test、alpha、post-hoc、平均秩、连接组 | 机器学习、统计 | △ / 独·面 | ✓/✓/组 | P2 |
| S63 | SHAP summary/bar / Global attribution | 模型解释 | sample × feature SHAP + feature value | background、output scale、排序、采样、色域 | 数据科学、医学 | △ / 面 | ✓/✓/组 | P2 |
| S64 | SHAP dependence/PDP/ICE | 模型解释 | feature + prediction/attribution + sample | 条件/边际、交互、数据覆盖、平滑、CI | 数据科学 | △ / 面 | ✓/✓/组 | P2 |
| S65 | 模型架构/计算图 / Architecture graph | 结构流程 | operation nodes + tensor/data edges | shape、模块、方向、重复块、版本 | 计算机、方法论文 | △ / 独·面 | ✓/✓/嵌 | P1 |
| S66 | Likert 发散堆积图 / Likert plot | 有序调查 | question × ordered response counts/weights | 固定顺序、中立项、权重、有效 n、缺失 | 心理、社会、调查 | ✓ / 面 | ✓/✓/原 | P1 |
| S67 | 边际效应/系数图 / Marginal effects & coefficients | 回归估计 | predictor/level + estimate + CI | 参照组、尺度、控制值、区间、聚类 SE | 社会、心理、经济、医学 | △ / 面 | ✓/✓/原 | P1 |
| S68 | 交互作用图 / Interaction plot | 模型预测 | x + moderator + prediction + CI | 调节值、预测尺度、控制变量、CI | 心理、社会、DOE | △ / 面 | ✓/✓/原 | P1 |
| S69 | Event-study/DiD 系数图 | 准实验 | relative time + estimate + CI | 省略基期、聚类 SE、处理时点、pre-trend | 经济、政策、社会 | △ / 面 | ✓/✓/组 | P2 |
| S70 | SEM/路径/中介图 / Path diagram | 结构模型 | observed/latent nodes + coefficients | 标准化、误差项、拟合指标、方向、因果措辞 | 心理、社会 | △ / 独·面 | ✓/✓/嵌 | P2 |

### 7.4 进阶分析 `A`

| ID | 中英文名 | 类别 | 数据形状 | 核心参数 | 典型学科 | 批量/组合 | PNG/SVG/OPJU | 优先级 |
|---|---|---|---|---|---|---|---|---|
| A01 | 聚类树/树状图 / Dendrogram | 聚类分析 | distance matrix / feature matrix | 距离、linkage、标准化、树切割、叶序 | 组学、数据科学、生态 | △ / 面 | ✓/✓/原 | P2 |
| A02 | PCA scores/loadings/biplot/scree | 降维分析 | sample × feature matrix | scaling、缺失、组件数、解释方差、载荷尺度 | 化学计量、组学、社会、材料 | △ / 面 | ✓/✓/原 | P1 |
| A03 | PLS/CCA/判别 scores 与载荷图 | 多变量分析 | X/Y matrices + labels | component、validation、scaling、ellipse、loading | 化学计量、组学 | △ / 面 | ✓/✓/原 | P2 |
| A04 | 回归诊断四图 / Regression diagnostic panel | 模型诊断 | observed/fitted/residual/leverage | residual type、QQ、scale-location、Cook/leverage | 全学科统计 | △ / 面 | ✓/✓/组 | P1 |
| A05 | 限制性立方样条 / Restricted cubic spline | 非线性效应 | continuous exposure + outcome/covariates | knots、reference、模型族、CI、边缘分布 | 医学、流行病、社会 | △ / 面 | ✓/✓/组 | P2 |
| A06 | 决策曲线 / Decision curve analysis | 临床效用 | threshold + net benefit by model | threshold range、treat-all/none、validation、CI | 医学预测 | △ / 面 | ✓/✓/组 | P2 |
| A07 | Hazard/累计风险/对数生存图 | 生存诊断 | `event` data / survival estimates | estimator、smoothing、time transform、CI | 医学、可靠性 | △ / 面 | ✓/✓/原 | P2 |
| A08 | Bayesian posterior/trace/rank plot | 贝叶斯诊断 | draws × parameter × chain | warmup、chain、interval、R-hat/ESS、reference | 统计、心理、计算 | △ / 面 | ✓/✓/组 | P2 |
| A09 | 3D 散点/轨迹 / 3D scatter & trajectory | 三维关系 | `XYZ (+group/size/color)` | 视角、投影、等比例、透明、连接 | 物理、材料、计算 | ✓ / 3D 层 | ✓/SVG△/原 | P2 |
| A10 | 3D 表面/网格 / 3D surface & wireframe | 三维场 | `XYZ/grid` | gridding、mesh、光照、z scale、边界、实测点 | 物理、材料、工程、地学 | ✓ / 3D 层 | ✓/SVG△/原 | P2 |
| A11 | 光谱 waterfall / Spectral waterfall | 堆叠谱 | `XYY` 或 x–condition–intensity grid | offset、series order、色映射、统一归一化 | XRD、Raman、NMR、信号 | ✓ / 面·3D | ✓/SVG△/原 | P2 |
| A12 | 3D 柱/带/墙 / 3D bar, ribbon & wall | 三维展示 | `XYZ/XYY` | 视角、遮挡、尺度、排序、投影 | 工程、光谱展示 | ✓ / 3D 层 | ✓/SVG△/原 | P3，非默认 |
| A13 | 矢量/箭袋图 / Quiver/vector field | 向量场 | `x,y,u,v` 或 angle/magnitude | 箭头尺度、key、采样、颜色、坐标比例 | 流体、气象、电磁 | ✓ / 层·面 | ✓/✓/原 | P2 |
| A14 | 流线图 / Streamline | 向量场 | gridded `u,v(,w)` | 种子、密度、步长、方向、颜色 | 流体、气象、电磁 | ✓ / 层·面 | ✓/✓/原 | P2 |
| A15 | 频谱/功率谱 / Spectrum & periodogram | 信号分析 | ordered time/signal | sampling rate、window、detrend、scaling、CI | 物理、工程、神经 | △ / 面 | ✓/✓/原 | P2 |
| A16 | 频谱图 / Spectrogram | 时频分析 | ordered signal + sampling metadata | window、overlap、FFT、log power、色域 | 信号、物理、神经 | △ / 面 | ✓/✓/原 | P2 |
| A17 | 小波时频图 / Wavelet scalogram | 时频分析 | ordered signal + sampling metadata | wavelet、scale/frequency、COI、significance | 地学、信号、生医 | △ / 面 | ✓/✓/组 | P2 |
| A18 | ACF/PACF/lag plot | 时间诊断 | ordered series | lag、CI、缺失、detrend/seasonal adjustment | 统计、经济、工程 | △ / 面 | ✓/✓/原 | P2 |
| A19 | 季节分解图 / Seasonal decomposition | 时间分析 | regular time series | period、method、robust、transform、remainder | 环境、经济、监控 | △ / 面 | ✓/✓/组 | P2 |
| A20 | Shewhart/run 控制图 / Control chart | 过程控制 | time/subgroup + measurement/count | chart type、center/UCL/LCL、phase、rules | 制造、工程、实验室 QC | △ / 面 | ✓/✓/原 | P2 |
| A21 | EWMA/CUSUM/Hotelling T² | 高级过程控制 | ordered univariate/multivariate process | lambda/k/h、baseline phase、covariance、limits | 制造、质量 | △ / 面 | ✓/✓/原 | P3 |
| A22 | DOE 响应面/等值图 / Response surface | 实验设计 | factor design + response | 模型、固定因子、设计域、实测点、残差、CI | 工程、材料、农业 | △ / 面·3D | ✓/SVG△/原 | P2 |
| A23 | Voronoi/Delaunay 图 | 空间结构 | `XY (+value)` | 距离度量、边界、重复点、插值/三角剖分 | 地学、材料、计算几何 | △ / 层·面 | ✓/✓/原 | P3 |
| A24 | 图像/等高线剖面 / Image & contour profile | 图像分析 | image/grid + profile path | 路径、宽度、像素→物理坐标、插值、ROI | 显微、遥感、材料 | △ / 面 | ✓/SVG△/原 | P2 |
| A25 | 2D/3D 函数与参数曲线 / Function plot | 理论函数 | formula + domain/parameter domain | 采样、定义域、奇点、坐标系、参数 | 数学、物理、工程 | △ / 层·面 | ✓/SVG△/原 | P2 |
| A26 | 极坐标/三元等高线 / Polar & ternary contour | 专用场 | theta–r–z；3-component + z | gridding、level、角度/组成约定、边界、实测点 | 气象、材料、化学、地学 | △ / 专用层 | ✓/✓/原 | P2 |
| A27 | 平行集合/层级边捆绑 / Parallel sets & edge bundling | 高维关系 | categorical stages / hierarchical graph | 节点序、聚合、阈值、bundling strength | 社会、组学、软件 | △ / 独 | ✓/✓/原 | P3 |
| A28 | 金融 OHLC/蜡烛图 / Financial OHLC | 金融时间 | date + open/high/low/close/volume | 交易日、复权、涨跌色、成交量副轴 | 金融、经济 | ✓ / 多层 | ✓/✓/原 | P3 |

### 7.5 覆盖检查

统一体系共列出 **157 个可检索条目**（K 25、X 34、S 70、A 28）。其中不少条目共享同一底层绘图原语，但保留为独立选择项是因为数据语义、必填参数或学科规范不同。例如 S21 森林图不能降格成“横向误差棒样式”，S34 Nyquist 不能只当普通散点，S66 Likert 也不能只当百分比堆积柱。

本地 A 线的 124 个营销图卡均可映射到上述体系：纯视觉变体（“彩色”“渐变”“花花”“水彩”“卡片”“泡泡”）落到主题/样式标签；WB、qPCR、CCK8、MTT、BCA、ELISA、OCR 等落到实验语义预设；基础图形仍复用 K/X/S 的底层对象。Origin B 线的内置图、扩展模板和 App 也可分别映射并保留来源标签，而不是继续膨胀图形 ID。

## 8. 产品分层与交付边界

### 8.1 核心高频

核心层不是“先做几个图标”，而是完整科研绘图闭环：K01–K25、X20–X22（分类评估）、S21（森林）等高频条目；长/宽表映射；原始点、区间和误差语义；log/日期/分类轴；分面与多面板；期刊栏宽/字号；无障碍色板；PNG/SVG；Origin 可用时生成 OPJU。

核心验收要求：

- 数据映射可追溯，单位与变量角色明确；
- SD、SE、CI、n 和生物/技术重复不混淆；
- 多面板可混合矢量图与图像，并统一字母标签/图例；
- 任何支持 OPJU 的核心图都能在 Origin 中继续编辑数据系列、轴和图层；
- 批量绘制只在数据结构验证通过时启用。

### 8.2 扩展常用

覆盖 X01–X34：配对/排名/区间、raincloud/ridgeline、二维密度、协议一致性、PR/校准、Pareto、parallel、Sankey/chord/network、UpSet、层级、极坐标和三元图。扩展层仍是跨学科通用能力，不应被误解为可有可无的装饰模板。

### 8.3 学科专用

按可独立发布的领域包交付，而不是一次性塞入主菜单：

| 领域包 | 主要条目 | 必须同时交付的语义校验 |
|---|---|---|
| 临床与流行病 | S01–S06、S19–S24、A05–A07 | 删失、风险人数、效应尺度、验证集、报告规范版本 |
| 组学与单细胞 | S07–S18 | FDR、normalization、feature/sample 注释、DR 参数和 seed |
| 化学与光谱 | S25–S30、A11 | 轴方向、单位、基线/归一化、积分、结构文件、计算条件 |
| 材料与电化学 | S31–S44 | 载量/面积口径、扫速、频率方向、等效电路、试样几何、实测点 |
| 地球与环境 | S45–S54、A13–A17、A24、A26 | CRS、投影、基准期、插值、遮罩、色图、不确定性 |
| 工程与质量 | S55–S59、A20–A23 | 控制限/规格限、删失、设计域、边界条件、稳定性约定 |
| 计算机与数据科学 | S60–S65、X20–X22、A08 | 多 seed、split、归一化、阳性基线、分箱、解释非因果 |
| 心理、社会与经济 | S66–S70、X03–X04、X13–X14 | 权重、有效 n、参照组、基期、聚类 SE、因果措辞 |

### 8.4 进阶分析

A01–A28 依赖拟合、聚类、信号处理、DOE、控制/可靠性、3D 或领域分析链。进阶层必须保存分析参数和软件版本，不能只保存最终像素。Analysis Template/批处理、诊断面板和可重算结果比增加更多视觉主题优先。

## 9. 不应默认提供或容易误导的图形

“不默认”不等于绝对禁止；意味着用户必须明确选择，界面显示风险和必填参数，导出前做一致性检查。

| 图形/做法 | 默认策略 | 主要风险与安全条件 |
|---|---|---|
| 3D 饼、3D 柱、3D 堆积、装饰性 3D 面积 | 不出现在默认浏览首屏；P3 | 透视、遮挡和面积/体积造成数量错觉；只有第三维有真实空间语义时使用 |
| 饼/甜甜圈/不同半径饼 | 可搜索，非默认 | 只用于少量、非负、总和有明确分母的 part-to-whole；多类别改用排序条图 |
| Radar/spider、radial bar、spiral | 可搜索，强提示 | 轴顺序、归一化和面积改变结论；必须固定尺度并提供数值表/平行坐标备查 |
| 双 Y 轴和 3Y/4Y | 用户明确指定后可用 | 任意缩放可制造相关；必须显示轴归属、单位、零点和完整范围，优先多面板 |
| 连续变量的均值柱 + SE | 默认阻止无说明导出 | 隐藏分布、离群点、配对与小样本；叠加原始点并明示 SD/SE/CI、n |
| Spline/平滑线 | 默认只作视觉连接且标注 | 暗示未观测中间趋势；统计拟合需显示模型、参数、区间和原始点 |
| 截断柱轴、未标 log/断轴 | 导出检查报错/强警告 | 改变视觉比例；柱图通常从有意义基线开始，任何变换/断轴显式标注 |
| rainbow/jet、同亮度红绿 | 默认禁用 | 感知不均匀、制造虚假边界且色觉缺陷不可读；改用科学顺序/发散/分类色板 |
| 无实测点的 contour/surface/相图 | 默认叠加观测点或遮罩 | 稀疏数据插值产生虚假精度；记录 gridding、边界、level 和外推范围 |
| OpenGL 3D 导出 SVG | 不能标“真矢量” | Origin 官方说明 3D 内容为栅格嵌入；交付元数据应写 `vector_fidelity=raster-embedded` |
| KM 无风险人数/删失/CI | 阻止“发表预设”导出 | 远端小样本视觉稳定；至少要求删失、风险表、随访范围和区间 |
| 仅 ROC 的不平衡分类 | 提示同时提供 PR/基线 | ROC 可能过于乐观；记录阳性率、阈值和独立验证 |
| 无多重校正的 volcano | 阻止显著性着色 | 大规模检验伪阳性；必须记录 FDR 方法、阈值和零 P 处理 |
| UMAP/t-SNE 的簇间距离结论 | 图注模板强提醒 | 全局距离、簇面积和簇数受参数/seed 影响；保存预处理和参数 |
| Funnel = 发表偏倚 | 禁止自动结论文案 | 不对称有异质性、小样本效应等多种来源；研究数不足时不宜使用 |
| Venn > 3–4 集合 | 自动兼容校验失败 | 区域不可读且难保证面积；用 UpSet |
| 过多系列 spaghetti/chord/network hairball | 提示过滤/分面 | 遮挡和视觉中心错觉；保留阈值、抽样和布局 seed |
| Choropleth 原始计数 | 要求确认分母 | 面积和人口共同影响；通常用率/标准化指标并标不确定性 |
| 热图各行独立缩放却不说明 | 强制图例说明 | 颜色不再代表可比较绝对值；记录 z-score/normalization 维度 |
| SHAP/attention/path 箭头的因果措辞 | 默认文案禁用 | 归因或模型路径不是因果识别；需要研究设计另行支持 |
| 显微/凝胶不同组分别增强 | 发布预设阻止 | 强度不可比、隐藏拼接和选择偏倚；共享处理、原图、比例尺和多视野 |
| Word cloud、gauge/speedometer | 不进入科研默认库 | 定量比较弱、数据密度低；仅作为非分析性附属视觉 |

## 10. 图形选择库的信息架构

### 10.1 用户路径：明确选择，不主动推荐

建议唯一的主路径为：

1. 用户打开“图形库”；
2. 通过类别树、搜索框或筛选器定位图形；
3. 用户点击具体图形卡片，系统写入稳定 `chart_type_id`；
4. 页面展示该图的数据要求、必填语义参数、风险和导出能力；
5. 用户如需投稿规格，再明确选择 `publication_profile`（或选择“不应用期刊模板”）；系统不得根据学科或图形自动猜测；
6. 用户映射列并处理数据兼容性与发表规格校验；
7. 绘制、组合、修改和导出。

系统可以做**兼容性校验**，但不应在校验失败时自动改选另一图形。错误应写成“所选 KM 曲线缺少事件/删失列”“所选三元图的三列存在负值或总和规则未确认”，并让用户修复数据、调整映射或返回图形库自己选择。

不设置“为你推荐”“根据数据自动选择”“最适合这个文件”等入口；也不把某图卡预选为默认答案。可以保留“最近使用、收藏、自建模板”，因为它们仍由用户明确选择。

### 10.2 页面结构

| 区域 | 内容 |
|---|---|
| 一级导航 | 全部、核心高频、扩展常用、学科专用、进阶分析、我的模板 |
| 二级类别树 | 比较、分布、关系、时间、矩阵/场、组成、流/网络/层级、地图、图像、统计分析、领域专图、布局 |
| 搜索 | 中英文名、缩写、俗称、实验名、轴/数据术语、Origin 名称 |
| 筛选器 | 数据形状、坐标系、编码、学科、分析依赖、批量、组合、导出、风险等级、来源 |
| 图形卡 | 双语名、缩略示意、1 句用途、数据形状、K/X/S/A、批量/组合徽章、PNG/SVG/OPJU 徽章、风险标记 |
| 详情抽屉 | 所需列、示例 schema、核心参数、适用/不适用、学科惯例、来源证据、Origin 支持级别 |
| 发表规格 | 用户显式选择“无 / 期刊级 / 刊群兜底”；显示来源日期、适用范围、自动校验项和人工提示项 |
| 选择后的数据映射 | 变量角色槽位、单位、层级/配对/删失/CRS 等语义字段、即时校验 |

缩略示意应使用合成数据和无版权依赖的自有图稿。A 线 JPEG 仅用于研究用户语言与变体，不应裁切成产品缩略图；其中含品牌、水印和二维码。

### 10.3 标签体系

建议为每个 `chart_type_id` 保存以下可筛选字段。

| 标签组 | 建议枚举/例子 |
|---|---|
| `family` | line、scatter、bar、distribution、matrix、field、flow、network、map、image、diagram |
| `intent` | compare、distribution、relationship、trend、composition、uncertainty、diagnose、classify、flow、spatial |
| `data_shape` | Y、XY、XYY、XYZ、matrix、grid、long、wide、interval、event、edge-list、hierarchy、geo、image |
| `variable_type` | continuous、categorical、ordinal、datetime、circular、compositional、geospatial、image、graph |
| `design` | independent、paired、repeated、nested、survival、competing-risk、weighted、multi-seed、meta-analysis |
| `coordinate` | cartesian、log、polar、ternary、geographic、3d、specialized |
| `encoding` | position、line、point、length、area、color、size、density、flow、surface、vector、image |
| `uncertainty` | none、SD、SE、CI、credible-interval、quantile、ensemble、censoring |
| `analysis_dependency` | none、aggregate、fit、test、clustering、embedding、signal-processing、domain-analysis |
| `composition` | same-layer、multi-layer、facet、inset、multi-panel、standalone、mixed-raster-vector |
| `batch_mode` | direct、cloneable-template、analysis-template、conditional、manual-layout |
| `domain` | life-science、clinical、chemistry、materials、physics、earth、environment、engineering、CS、psychology、social |
| `artifact` | PNG、SVG、OPJU、OTPU、OGGU |
| `vector_fidelity` | native-vector、text-outline、raster-embedded、raster-only |
| `origin_source` | built-in、extended-template、app、composed-example、unsupported |
| `evidence_source` | local-A、origin-B、journal-C；可多值 |
| `risk` | safe-default、needs-parameters、strong-warning、not-default |
| `locale_alias` | 生存曲线/KM、森林/forest、火山/volcano、泳道/swimmer、云雨/raincloud 等 |

`publication_profile` 不应塞进每个 `chart_type_id`，而应作为独立、可版本化的选择对象。建议检索字段为：`profile_id`、`journal_title`、`publisher`、`journal_family`、`discipline`、`width_modes`、`accepted_formats`、`vector_policy`、`color_mode`、`dpi_classes`、`source_updated_at`、`source_accessed_at`、`review_status`。用户可搜索 `Nature`、`JACS`、`IEEE`、`PLOS Biology`、`Elsevier 90 mm` 等，但搜索结果只供用户点击选择，不自动应用。

### 10.4 搜索同义词示例

| 用户输入 | 命中条目 |
|---|---|
| `KM`、`生存`、`survival`、`risk table` | S01 KM 曲线 |
| `IC50`、`EC50`、`剂量效应`、`4PL` | S05 剂量–反应 |
| `WB`、`western blot`、`条带定量` | S24 图像组合 + K/X 分布/比较预设 |
| `GO`、`KEGG`、`富集气泡`、`gene ratio` | S09 富集图 |
| `相关热图`、`corrplot`、`三角热图` | K21 相关矩阵 |
| `EIS`、`阻抗`、`Nyquist` | S34 Nyquist；同详情页关联 S35 Bode，但不自动改选 |
| `李克特`、`Likert`、`发散堆积` | S66 Likert |
| `桑基`、`Sankey`、`alluvial`、`流向` | X26 Sankey/Alluvial |
| `小提琴+散点`、`云雨`、`raincloud` | X06 Raincloud |
| `响应面`、`DOE contour`、`RSM` | A22 响应面 |

## 11. 实现与导出建议

### 11.1 一个条目、三类对象

每个图形条目建议拆成：

- `schema`：变量角色、类型、单位、层级与约束；
- `semantics`：统计/领域参数、风险规则、图注元数据；
- `renderers`：PNG/SVG 渲染器与 Origin 项目构建器。

样式主题独立于图形语法。A 线中的“彩色、渐变、水彩、花花、卡片”应成为 theme；“WB、qPCR、CCK8、ELISA、Seahorse OCR”应成为 domain preset；两者都不复制底层 renderer。

### 11.2 OPJU 能力等级

| 等级 | 定义 | 产品文案 |
|---|---|---|
| O1 原生 | Origin 内置/分析对象，数据、轴、plot 可编辑 | “可在 Origin 中继续编辑” |
| O2 组合 | 用多层、模板、App/脚本构建，主要对象可编辑 | “可编辑；部分布局依赖模板/App” |
| O3 嵌入 | 将 SVG/PNG/结构图嵌入 OPJU，不能恢复为数据驱动 plot | “可在项目中查看/排版；非原生数据图” |
| O0 不可用 | 无 Origin 运行时/许可或该类型未实现 | 不展示 OPJU 导出按钮 |

后端应在运行时探测 Origin 与 `originpro` 自动化是否可用，并把实际等级返回前端；不能因 Python 包存在就假设用户机器一定有可授权 Origin。

### 11.3 批量与可复现

- 直接批量：输入 schema 同构，绘图无分析依赖；
- Cloneable Template：同构工作簿/工作表/列，复用图层与样式；
- Analysis Template：需要拟合、统计、聚类或信号处理，保存完整参数与重算链；
- 人工布局：复杂示意、图像拼接、网络标注等不承诺通用批量。

每次导出应保存：数据 hash、列映射、过滤/变换、随机种子、模型/统计参数、主题版本、图形类型版本、软件和渲染器版本、Origin 模板/App 依赖、导出尺寸/色彩/字体设置。

## 12. 最终建议

1. 以本报告 157 个条目作为完整选择库的上限框架，不要求一次全部实现，但产品目录从一开始保留四层和稳定 ID，避免后续重构。
2. 第一阶段优先交付 K 层、分类评估、森林/KM、光谱/材料曲线、地图基础和多面板，而不是大量营销样式。
3. A 线的 124 张图卡建立“用户俗称 → 统一条目 → 领域预设/主题”映射，不直接复用图片资产，也不把它标成 Origin 证据。
4. 邀请制内测首批上线 Nature、JACS、IEEE Journals、Physical Review、PLOS Biology、AIP Journals 和 Elsevier Default 七个发表规格；Wiley Default 先以“需复核/目标刊覆盖”状态进入 P1。
5. B 线保留 `origin_source` 和 OPJU 能力等级；Gallery、扩展模板、App、内置图必须分开。
6. C 线的规范字段进入 schema 和导出检查，而不是只停留在帮助文档。
7. 图形库只负责用户主动浏览、搜索、筛选与明确选择；系统负责展示要求和校验，不新增 Agent 主动推荐路径。
