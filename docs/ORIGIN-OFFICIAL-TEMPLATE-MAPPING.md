# PlotAgent v3：38 个候选图—35 图 Origin renderer 映射与重构基线

状态：38 个候选图的官方资料与本机资产已经审计；其中 35 图进入 Origin renderer，核密度图、Kaplan–Meier 生存曲线、森林图明确排除。旧模板优先链的历史证据只作选型追溯，不代表当前 renderer 资格。35 个可用切片已完成代码、机械读回与 fresh-reopen；产品负责人于 2026-08-12 确认 35/35 图视觉验收通过。

核对环境：OriginPro 2024 SR1 `10.10.178`，`originpro 1.1.15`

模板来源：本机 Origin 安装目录 `D:\origin`

历史图形范围：旧证据清单中的 45 图，仅作迁移追溯，不再作为产品库存

重构后 Origin renderer 范围：仅 T1/T2，共 35 图；另保留 3 个明确拒绝的候选记录

## 1. 使用原则

本表既是模板选择基线，也是当前生产绑定目录。代码只接受表内 build-pinned 模板路径与哈希；模板存在、默认态 fresh-reopen 成功仍不等价于视觉 PASS。

映射等级：

- **T1 直接模板**：模板与图形语义基本一致；Python 只负责数据绑定、动态系列和用户编辑。
- **T2 模板＋小补**：使用官方模板，但需补少量轴、图例、参考线、分组或面板逻辑。
- **T3 官方样例派生**：以随附 OPJU 中的合格图页为准，从该图页冻结模板；不从通用几何重画。
- **T4 基础模板＋专用 renderer**：本机未找到精确官方模板；使用官方基础模板和原生 Plot/Object 完成。

证据等级沿用现有视觉审计：

- **A**：Origin 随附 OPJU 中存在同源图页与数据。
- **C**：使用 Origin 官方数据，通过 Origin 官方模板重新生成参考图。
- **D**：固定合成数据，通过独立 Origin 原生路径生成参考图。

验收要求：每次模板迁移必须保留原生 Worksheet/Matrix、原生 Plot、数据链接和可编辑对象，并完成保存后 fresh-reopen；找到同名模板不等于迁移通过。

### 正式范围决定

- **正式纳入 Origin renderer：35 图。**
- **明确排除：核密度图、Kaplan–Meier 生存曲线、森林图。** 不允许以预计算折线、手工图元或错误模板替代。
- **从正式产品删除：T3 2 图（K05、S25）与 T4 5 图（K17、S05、S07、S31、X01）。**
- 删除覆盖图形库、搜索、创建能力、Agent capability、字段映射、编辑入口、Origin 导出、资格清单与发布声明；不得仅在前端隐藏而保留可调用入口。
- 历史数据或项目若引用这 7 个 ID，只允许给出明确的“不再支持”迁移诊断，不静默替换为近似图形。
- 删除工作与绘图引擎全面重构同时实施；重构完成后 Origin 可渲染清单、测试与文档必须统一为 35 图，并保留 3 个 fail-closed 记录。

## 2. 38 个候选图映射（35 可用＋3 排除）

| ID | 图形 | 现有证据 | 首选 Origin 官方资产 | 等级 | Python 需要补充的最小逻辑 | 迁移注意事项 |
|---|---|---|---|---|---|---|
| K01 | 折线图 | C；`Sine Curve.dat` | `LINE.otpu` `76a7ce886e22` | T1 | 绑定 X/Y、系列数、用户线型 | 不再由后端重建默认线样式 |
| K02 | 线点图 | C；`Sine Curve.dat` | `LINESYMB.otpu` `2f1292a939ea` | T1 | 绑定 X/Y；同一系列线与点共享身份 | 图例只生成一个复合样例 |
| K03 | 散点图 | C；`Linear Fit.dat` | `SCATTER.OTP` `efef85d7c3db` | T1 | 绑定 X/Y、分组色与符号 | 不自动添加连接线 |
| K04 | 气泡与颜色映射散点 | A；`bubble.opju` Graph2 | `bubble.otpu` `abc20768493e` | T2 | 绑定 X/Y/Size/Color；按用户意图启用 size key 或 color scale | 当前额外色带问题：默认必须显式 `colorbar=false`，只有请求颜色映射图例时开启 |
| K06 | 点估计与误差棒 | A；`ERRBAR.opju` Graph1 | `ERRBAR.otpu` `c17ebd8f68f8` | T1 | 绑定 X/Y/XErr/YErr、端帽与中心符号 | 必须保持双向误差、端点不成为数据点 |
| K07 | 误差带与置信带 | A；`ERRORBAND.opju` Graph1 | `ERRORBAND.otp` `dfd36bf19bf3` | T1 | 绑定 X/Center/Lower/Upper、系列数 | 使用原生 fill-to-next；禁止上下界进入图例 |
| K08 | 柱状图 | C；`Column.opju` Book2 | `COLUMN.otpu` `ec9e654e8860` | T1 | 绑定 Category/Value；动态标签留白 | 长标签的旋转/换行仍需数据驱动 |
| K09 | 分组柱状图 | A；`Column.opju` Graph2 | `COLUMN.otpu` `ec9e654e8860`，以 `Column.opju` Graph2 分组设置为准 | T2 | 按组数建立 Origin plot group、动态宽度和 gap | 1/2/3/5 组均不得重叠 |
| K10 | 堆积柱状图 | A；用户修正默认 OPJU + 本机菜单 `StackColumn` | `STACKCOLUMN.otp` `3ffd84ea777e` | T1 | 原始 category + 动态 Y 一次选中，调用 `worksheet -p 213 StackColumn`；读回 PID 213、`Stack.Offset=1`、`StackOffset=0` | 系列顺序决定堆积顺序；禁止空 `COLUMN` + AddPlot 重构 |
| K11 | 100% 堆积柱状图 | A；用户修正默认 OPJU + 本机菜单 `StackColP` | `StackColP.otp` `2094be00706b` | T1 | 原始 category + 动态 Y 一次选中，调用 `worksheet -p 213 StackColP`；读回 PID 213、`Stack.Offset=1`、`StackOffset=1` | 禁止 Python 预归一化、空图重构或二次归一化 |
| K12 | 单变量点图与条带图 | A；`ColumnScatter.opju` Graph11 | `ColumnScatter.otp` `e9bfbf3b74bc` | T2 | 长表映射、组内散点偏移、动态组标签 | 大样本下图例应避开观测点 |
| K13 | 箱线图 | A；`Box.opju` Graph1 | `BOX.OTP` `a1f26e68a6a0` | T1 | 绑定原始值与可选分组；冻结 Tukey 规则 | 优先让 Origin 创建原生 box plot，不拼箱体线条 |
| K14 | 小提琴图 | C；`Box.opju` 原始值＋系统 Violin 重建 | `Violin.otpu` `ee71ef5fb2bf` | T1 | 绑定原始值与分组、KDE/内部统计参数 | 高优先级迁移：禁止用普通线和 fill_area 模拟外轮廓，避免边缘竖线复现 |
| K15 | 直方图 | A；`Histogram.opju` Graph2 | `Hist.otpu` `cc1d7edd9f07` | T1 | 原始观测绑定 PID219；共享计算内核只冻结 bin begin/end/size 与 Count 口径 | Origin 使用原生 Histogram 对象，不创建预计算普通柱；fresh reopen 必须读回固定分箱 |
| K16 | 核密度图 | A；`Histogram.opju` Graph7 | `HISTDIST.otpu` `a584e2ee70fa` | 排除 | 不进入 Origin renderer | Origin 2024 fresh reopen 会恢复 histogram bins；不得以预计算 XY 密度线冒充纯 KDE |
| K18 | 面积图 | A；`Area.opju` Graph1 | `AREA.otpu` `c14ad432ffd6` | T1 | 绑定 X 与 1..N 个 Y，官方菜单一次性创建；开放共同的颜色与边界线样式 | 默认保持官方覆盖语义，不擅自改成累计/堆积；精确 From Y 仍需人工视觉确认 |
| K19 | 日期时间折线图 | B；Origin Help `Line Graph` + 本机 Origin 2024 原生实证 | `LINE.otpu` `76a7ce886e22` | T1 | 绑定数值型 Date/Time X 与 `series_1..series_N`，一次调用官方 Line 菜单 | PID 200 与源列逐项读回；同日显示 `Time/HH:mm`，跨日显示 `Date/Short Date`；不使用 Time Series Explorer |
| K20 | 热图 | A；`Heatmap.opju` Graph1 | `Heat_Map.otpu` `9bd8240ca582` | T1 | 写入 Matrixbook 或规则矩阵、设置 palette/range | 行列语义和色标位置显式控制 |
| K21 | 相关矩阵图 | D；独立 Origin 矩阵参考 | `Heat_Map_With_Labels.otpu` `d1a7fcd8af23` | T1 | 写入预计算相关矩阵、对角/上下三角策略 | 模板负责标签与色标，相关计算仍由引擎负责 |
| K22 | 等高线与填色等值图 | A；`Contour.opju` Graph1 | `CONTOUR.otpu` `b4915054edd4` | T1 | 写入规则 Matrix 或 XYZ 网格、levels/palette | 色标不得覆盖数据框或被裁切 |
| K24 | 格状分面图 | D；官方 Trellis 路径的 Agent Native 实证 | `Grouped.otp` `b3a1999cc9e9` + `plot_group` | T2 | 长表绑定 facet/X/Y，并由官方 X-Function 动态生成单层 2–5 面板 | 不复制普通图层；保持 PID 202、源 facet 顺序和原生 Trellis 面板 |
| K25 | 多面板组合图 | D；异构原生子图合并实证 | `Graph > Merge Graph Windows` / `merge_graph` | T2 | 追加 2–4 个精确版本子 OPJU，再调用官方合并流程并重放公共编辑 | MGROUPS 只适用于同构多面板，不是 K25 运行依赖；子图 Worksheet、Plot 与 PID 必须保持，不栅格化 |
| S01 | KM 生存曲线 | D；独立 Origin 生存图参考 | `SurvivalPlot.otp` `0b8759367ce1` | 排除 | 不进入 Origin renderer | 阶梯、置信带、风险表与共同 Agent 编辑布局不能稳定 fresh-reopen；不得改跑统计分析或手工拼图 |
| S21 | 森林图 | D；官方 Forest Plot App | 本机未安装官方 App | 排除 | 不进入 Origin renderer | 不得用 `SCATTERINTERVAL.otp`、普通误差棒或手工线段冒充官方森林图 |
| S34 | Nyquist 图 | D；独立 Origin line-symbol 参考 | `LINESYMB.otpu` `2f1292a939ea` | T2 | 绑定 Z′/−Z″、等比例轴、方向/频率编码 | 本机未找到 Nyquist 命名模板；不可把频率误作坐标轴 |
| S61 | 混淆矩阵 | C；官方 `LogRegData.dat` | `Heat_Map_With_Labels.otpu` `d1a7fcd8af23` | T2 | 写入预聚合 Count 矩阵、轴类目和单元格标签 | 必须支持原始样本计数与预聚合 Count，两者都落为同一原生矩阵语义 |
| X02 | 垂线图 | C；官方 step signal 数据 | `DROPLINE.OTP` `69cbcf934924` | T1 | 绑定 X/Y、symbol 和 drop-line 样式 | 垂线落到当前绘图区底部 X 轴；不与 X03 混淆 |
| X03 | 棒棒糖图 | A；`Lollipop.opju` Graph1 | `Lollipop.otpu` `f76fc89b9438` | T1 | 绑定类别和 2+ 数值系列、动态系列颜色 | 两系列形成哑铃预设；保持当前正式命名 |
| X05 | 蜂群图 | A；`ColumnScatter.opju` Graph10 | `ColumnScatter.otp` `e9bfbf3b74bc` | T1 | 绑定原始值/分组和避让参数 | 使用模板原生 Column Scatter/Beeswarm 结构 |
| X09 | 浮动柱状图 | A；用户修正默认 OPJU + 官方 Floating Column 帮助 | `FloatCol.otp` `f1ea445735f9` | T1 | 一次绑定 category + 原始有序 start/middle/end 边界，直接执行官方 Floating Column 创建；默认样式由模板管理 | 类别沿横轴、数值沿纵轴；不得改用水平 `FloatBar.otp`、普通柱形、预计算 bottom/height、排序边界或复制 end；PID 207 的分段颜色未获官方稳定证据，暂不开放 |
| X13 | 人口金字塔 | C；官方 `African_population.dat` | `PopulationPyramid.otpu` `2c5958a91130` | T1 | 绑定 category/left/right、中心零轴 | 左右符号和显示格式遵循模板 |
| X23 | 双 Y 轴Y-Y图 | A；`Double Y.opju` Graph1 | `DOUBLEY.OTP` `487547eb206e` | T1 | 绑定共享 X 和左右 Y、线点样式与图例 | 保持两个 PID202 Line+Symbol、X straight 1:1 linked layers、左右Y独立 |
| X24 | 帕累托图 | C；官方 `Counts.dat` | `ParetoRaw.otpu` `5f273e70f87c` | T1 | 绑定类别/值，使用预计算或模板累计百分比 | 只能有一个累计百分比权威来源 |
| X35 | 双 Y 轴柱状图 | A；`Double Y.opju` Graph2 | `2Ys_Col.otpu` `cba0737aaa4c` | T1 | 绑定类别和左右值、动态柱宽 | 右轴默认不加粗；两侧柱不重叠 |
| X36 | 双 Y 轴柱线图 | A；`Double Y.opju` Graph3 | `2Ys_ColSymb.otpu` `6e951a3dd1f0` | T1 | 左柱、右线/点、共享类别和图例 | 右轴默认不加粗，模板层关系不拆散 |
| X38 | Y 偏移堆积线图 | C；官方 `waterfall.opju` 数据 | `OffsetStackY.otp` `c6d7548cf738` | T1 | 绑定多系列、计算显示 offset、轴/图例 | offset 只影响显示，不写回原始 Y |
| X39 | 线条序列图 | A；`BoxLser.opju` Graph2 | `BoxLser.otpu` `8396fd58435c` | T1 | 宽表不转置；每行跨 2+ 数值列形成原生线点序列 | 单一 PID206 组；动态列数、行数与源列标签 fresh 保持 |
| X40 | 前后对比图 | A；`BeforeAfter.opju` Graph1 | `BeforeAfter.otpu` `d37a1c294969` | T1 | 两列宽表不转置；Subgroup Size=2 逐行成对连接 | 单一 PID206 组；对象数不随受试者行数增长，动态15行 fresh 保持 |

## 3. 迁移优先级

### 第一批：T1/T2 中直接解决当前可见问题

1. **K14**：改为 `Violin.otpu` 原生小提琴图，停止用普通线/填充模拟边缘。
2. **K04**：使用 `bubble.otpu`，把 size key 和 color scale 变成两个显式开关；默认不自动添加色带。
3. **K09**：交由 Origin 原生 Plot Group 管理柱宽、组间距和颜色递增，验证 1/2/3/5 组。

### 第二批：其余 T1 直接模板

`K01`、`K02`、`K03`、`K06`、`K07`、`K08`、`K10`、`K11`、`K13`、`K15`、`K18`、`K19`、`K20`、`K21`、`K22`、`X02`、`X03`、`X05`、`X09`、`X13`、`X23`、`X24`、`X35`、`X36`、`X38`、`X39`、`X40`。

### 第三批：其余 T2 小补模板

`K12`、`K24`、`K25`、`S34`、`S61`。`K16`、`S01`、`S21` 已在候选审计后明确排除，不进入实现批次。

## 4. 删除清单

正式删除 `K05`、`K17`、`S05`、`S07`、`S25`、`S31`、`X01`。重构提交必须同时清理：

1. 图形注册表、生成 Schema 和前端图形库。
2. Agent create/edit capability、搜索别名和字段映射规则。
3. PlotDocument 创建入口、固定计算入口、Matplotlib/Origin Profile 与导出动作。
4. 通用编辑白名单、专属编辑参数和批量/组合候选入口。
5. 视觉 fixture、逐图 OPJU 清单、资格测试和发布能力声明。
6. 旧项目兼容读取：保留 ID 识别，只返回稳定的 `CHART_TYPE_REMOVED` 诊断；不恢复渲染能力，也不自动替换图形。

删除完成的判据不是“界面搜不到”，而是任何生产 Origin 入口都不能再分派到已排除的图；`ORIGIN_RENDERABLE_RECIPES` 必须严格等于 35。

## 5. 35 图裸模板动态数据测试

全面重构开始前，对候选图逐一执行裸模板测试。正式 renderer 的动态测试只覆盖最终保留的 35 图；测试的目的不是证明当前 renderer，而是测清 Origin 官方模板自身能处理到什么程度。

### 5.1 裸模板允许的操作

测试脚本只允许：

1. 新建或导入 Worksheet/Matrix。
2. 写入测试数据并设置 X/Y/Z、误差、标签等列 designation。
3. 使用映射表指定的官方 `.otp/.otpu` 创建图页。
4. 按模板要求把数据 Plot 加入既有 Layer 或 Plot Group。
5. 保存 OPJU、退出 Origin、在新会话 fresh-reopen 并检查原生对象。

裸模板阶段禁止：

- 手工计算图元坐标、柱宽、图例位置或标签位置。
- 用大量 Line/Text/Shape 对象模拟 Origin 已支持的原生 Plot。
- 按图形 ID 注入视觉补丁。
- 修改模板文件来掩盖测试失败。
- 嵌入 Matplotlib 位图代替 Origin 原生图。

### 5.2 每图动态测试矩阵

| 变化维度 | 最低覆盖 | 通过条件 |
|---|---|---|
| 行数 | 小、标准、大三档 | 数据范围、坐标缩放和对象链接正确 |
| 系列/组数 | 1、2、3、5；不适用时登记 N/A | 系列不丢失、不重叠，样式稳定递增 |
| 类别数 | 3、10、30；不适用时登记 N/A | 刻度完整，模板能处理的布局不被 Python 接管 |
| 标签 | 短英文、长英文、中文 | 文本内容、数据关联和字体正确；裁切、换行、重叠仅记录，不作本轮阻断 |
| 数值范围 | 小数、大数、正负混合、跨零 | 坐标、基线、科学计数和参考线正确 |
| 缺失值 | 中间缺失、整组缺失；不适用时登记 N/A | 连接方式和缺失值显示符合模板语义 |
| 编辑态 | 颜色、符号、线型、标题、轴、图例中适用项 | 编辑仍作用于原生对象并可再次保存 |
| 持久化 | build 与 fresh-reopen | 数据、Plot、Layer、轴、图例和显示状态一致 |

### 5.3 测试结论

每图只能得到以下一种结论：

- **AUTO**：Origin 模板自动适应，生产实现只保留数据绑定和用户编辑。
- **DECLARED_PATCH**：模板主体正确，但确实需要一项已声明的 T2 原生配置；必须有失败证据和最小补丁测试。
- **REMOVE_OR_RECLASSIFY**：裸模板无法达到要求，且需要超出 T2 的专属 renderer；该图不得留在正式 Origin renderer 中，需明确拒绝，不能偷偷扩张实现。

测试产物至少包含输入数据、模板哈希、默认/变化状态 PNG、OPJU、fresh-reopen 检查结果和结论清单。

## 6. 绘图引擎全面重构顺序

1. **冻结候选与正式范围。** 候选资料保留 38 图；Origin renderer、测试和能力声明统一为 35 图可用、3 图拒绝。
2. **运行裸模板测试。** 先测 Origin 自动能力，不修改现有 renderer 来追求通过。
3. **冻结模板目录。** 每图记录官方模板、版本、哈希、数据 designation、AUTO/DECLARED_PATCH 结论和允许编辑项。
4. **建立模板优先执行路径。** 生产链只完成数据导入、列角色、模板应用、必要的声明式原生配置、用户编辑和保存检查。
5. **迁移 T1。** 28 图逐图替换旧 Origin 构建路径；禁止回退到旧几何模拟。
6. **迁移 T2。** 7 图只实现裸模板证据证明必需的最小补丁；每项补丁独立测试。
7. **删除旧绘图路径。** 35 个可用图全部通过后，删除被替代的专属 Origin 几何拼装、旧图形分支和过期视觉证据。
8. **重新资格。** 以 35 图新引擎统一生成默认态、动态状态、代表性编辑态和逐图 OPJU；完成全部机械修改读回后，一次性生成统一审查页交由用户逐图视觉判断，人工实际编辑按 Origin 模板家族选代表图。

截至 2026-08-12：35 个 Origin 可渲染 Profile 已完成新引擎切片；3 个排除项在 recipe 选择阶段 fail closed。旧绘图 compiler、resolver、共享 plan 与旧 Origin renderer 已从生产路径删除。统一视觉入口位于 `build/visual-audit/origin-recipe-renderer-35/index.html`，35/35 图人工视觉状态为 `PASS`。

重构不预先规定“每图一个 renderer”或“所有图共用一个 renderer”。选择标准只有三个：Origin 映射正确、行为稳定、后续 Agent 容易操作。新 `PlotDocument`、`EngineDataView` 与公开 Engine Action 是唯一生产契约；旧 `PlotSpec`、compiler、resolver、`ResolvedPlot` 和 Origin plan 不得进入新执行路径，也不得作为迁移兜底。

## 7. 实施门禁

每张图迁移时逐项检查：

1. 模板文件路径、文件 SHA-256、Origin 版本固定。
2. 输入数据与参考图严格同源。
3. Worksheet/Matrix、Plot、Layer、Axis、Legend 均为 Origin 原生对象。
4. 数据 Plot 与 Worksheet/Matrix 保持链接。
5. 默认态和代表性编辑态都由模板路径生成。
6. 保存 OPJU 后退出 Origin，以新会话重新打开。
7. fresh-reopen 后重新读取数据、Plot 类型、图层、图例、色带和对象属性。
8. 动态组数/系列数不能造成错误的数据几何重叠；标签长度输出只记录文本、字体和原始排版证据，不以裁切/重叠阻断。
9. 35 图逐图机械修改数据值和代表性样式并 fresh-reopen 读回；机械完成后统一交付 Matplotlib、Origin 对照与 OPJU，由用户逐图签名；人工实际编辑按模板家族选代表图，机械成功不能代替视觉通过。

## 8. 官方依据

- Origin 官方说明所有图页都由图形模板创建，模板保存页面、图层、坐标轴、标签、数据 Plot 样式等属性：<https://docs.originlab.com/origin-help/plot-graph-template/>
- 模板保存内容说明：<https://docs.originlab.com/origin-help/graph-template-elements/>
- `originpro` 的 `GLayer.add_plot` 支持 X/Y/Z/XErr/YErr 并创建原生 Plot：<https://docs.originlab.com/originpro/classoriginpro_1_1graph_1_1GLayer.html>
- External Python 通过 Origin Automation Server 创建、修改并保存 Origin 项目：<https://docs.originlab.com/externalpython/>
