# OriginRecipe 基线

`OriginRecipe` 是 PlotAgent v3 Origin 后端的唯一创建事实源。它不向 Agent
暴露 LabTalk、模板路径或 Origin 对象 ID；它只在引擎内部把公开 Profile
映射到已经核实的官方入口、本机 Origin 2024 模板、数据组织、重建策略和
原生读回门禁。

权威实现位于：
`src/plotagent/engine/backends/origin/recipe.py`。

## 规则

1. 默认图从官方模板、官方 X-Function、官方分析或官方组合流程创建。
2. Agent 只提交公开 Engine Action；不能选择模板、注入脚本或修改 recipe。
3. 数据重绑、系列数变化和结构参数变化均从 recipe 重新创建；标题、坐标轴、
   系列样式、图例等公开编辑可在同一版本的原生对象上增量应用。
4. OPJU 必须保存源工作表或矩阵、原生图层和原生 Plot；fresh reopen 后按
   recipe 的 `readback_contract` 再验证。
5. `manual_native_property` 表示 Origin 2024 自动化接口不能稳定读回某一专属
   属性，不表示可以跳过检查；该属性必须在最终视觉审计时人工确认。
6. 模板文件名以本机 Origin 2024 Build 178 的实际资产为准，并固定 SHA-256。
7. `local_dispatch` 固定本机 `Plot.ogs`/`Plot3D.ogs` 菜单段、X-Function、
   分析或组合入口。模板文件正确但 dispatcher 不同，仍视为错误实现。

## 35 图 Origin renderer 范围

| ID | 中文名称 | 官方模板或流程 | 创建类型 | 证据 |
|---|---|---|---|---|
| K01 | 折线图 | `LINE.otpu` | 模板 | 原生结构已证 |
| K02 | 线+符号图 | `LINESYMB.otpu` | 模板 | 原生结构已证 |
| K03 | 二维散点图 | `SCATTER.OTP` | 模板 | 原生结构已证 |
| K04 | 索引大小气泡与颜色映射图 | `worksheet -p 248 Bubble` / `bubble.otpu` | 菜单＋模板 | 原生 size/color modifier 已证；默认只显示 Bubble Scale |
| K06 | XY双向误差棒图 | 菜单 33336 / `worksheet -p 201 ERRBAR` | 菜单＋模板 | 列顺序固定为 X/Y/YErr/XErr；renderer live 待收口 |
| K07 | 误差带图 | `Plot.ogs [ScatterErrorBand]` / `ERRORBAND.otp` | 菜单＋模板 | 上下界转 YEr-/YEr+；renderer live 待收口 |
| K08 | 柱状图 | `COLUMN.otpu` | 模板 | 原生结构已证 |
| K09 | 分组柱状图（索引数据） | `gColumn.otpu` + `plot_gindexed` | X-Function | 专属属性人工门禁 |
| K10 | 堆积柱状图 | `STACKCOLUMN.otp` / `Plot.ogs [StackCol]` | 菜单＋模板 | 原生累计堆积与完整图例已证 |
| K11 | 100%堆积柱状图 | `StackColP.otp` / `Plot.ogs [StackColPercentage]` | 菜单＋模板 | Origin 原生百分比归一化与完整图例已证 |
| K12 | 列散点图 | `Plot.ogs [ColumnScatter]` / `ColumnScatter.otp` | 菜单＋模板 | PID206、原始Y列、源绑定和官方 Data/Jitter 外观已完成 live/fresh 门禁；图例使用 `legendbox id:=L` 的原生数据符号 |
| K13 | Tukey箱线图 | `Plot.ogs [BoxChart]` / `BOX.OTP` + Tukey 1.5×IQR | 菜单＋模板 | 原生 Layer Format 已固定 Box 25/75、Whisker Outlier、Coef=1.5、离群点开启，并在 fresh reopen 读回 |
| K14 | 小提琴图 | `Plot.ogs [ViolinPlot]` / `Violin.otpu` | 菜单＋模板 | Kernel Smooth、共同绝对带宽、Extend=0、Width缩放和100%曲线尺度均由原生 Layer Format 写入并 fresh 读回 |
| K15 | 直方图 | `Plot.ogs [Histogram]` / `Hist.otpu` / plot type 219 | 菜单＋模板 | 原始观测Y保留；FD/Sturges begin/end/bin size 与 Count 高度写入 PID219 并 fresh 读回，不生成预计算柱 |
| K18 | 面积图 | `AREA.otpu` | `worksheet -p 204 Area` | X+1..N Y、PID204、源绑定、颜色/边界线样式机械读回；From Y 专属枚举人工门禁 |
| K19 | 日期时间折线图 | `LINE.otpu` + Date/Time X | 模板 | 原生结构已证 |
| K20 | 热图 | `Heat_Map.otpu` + Matrix | 模板 | 专属属性人工门禁 |
| K21 | 带标签热图 | `Heat_Map_With_Labels.otpu` + Matrix | 模板 | PID105、MatrixBook 源绑定、Z 值标签、±1 色域和 full/lower/upper 原生 `FillDispl`/`LabelDispl` 均已经独立进程 fresh-reopen 读回 |
| K22 | 填色等高线 | `CONTOUR.otpu` + Matrix | 模板 | 完整等距规则网格、PID226、MatrixBook 源绑定、坐标映射、色阶边界和色标均已经独立进程 fresh-reopen 读回 |
| K24 | Trellis分面图 | `Grouped.otp` + `plot_group` | X-Function | 专属属性人工门禁 |
| K25 | 多面板组合图 | `Graph > Merge Graph Windows` / `merge_graph` | 组合 | 2–4 个异构原生子图与独立进程 fresh-reopen 已证；无 MGROUPS 运行依赖 |
| S34 | Nyquist图 | `LINESYMB.otpu` + EIS语义 | 模板 | 原生结构已证 |
| X02 | 垂线图 | `DROPLINE.OTP` | 模板 | 专属属性人工门禁 |
| X03 | 棒棒糖图 | `Lollipop.otpu` | 模板 | 专属属性人工门禁 |
| X05 | 蜂群图 | `Beeswarm.otpu` | 模板 | 专属属性人工门禁 |
| X09 | 浮动柱状图 | `FloatCol.otp` | 模板 | 原始有序边界一次创建；PID 207、纵向方向、两/三边界、下降/交叉边界与 Agent 公共编辑均经独立 fresh-reopen 机械读回 |
| X13 | 人口金字塔 | `Plot.ogs [PopulationPyramid]` / `PopulationPyramid.otpu` | 菜单＋模板 | X＋恰好2个Y；两层 PID203、ExchangeXY、链接签名 `(1,1,2)`、A/B与A/C源绑定及跨层图例均已 live/fresh 读回 |
| X23 | 双Y轴Y-Y图 | `Plot.ogs [2Ys_Y-Y]` / `DOUBLEY.OTP` | 菜单＋模板 | 两层 PID202 Line+Symbol；第二层 X 1:1 链接、Y独立，线点样本图例及 Agent 标题在 fresh reopen 保持 |
| X24 | 帕累托图（分箱数据） | `ParetoBin.otpu` + `plot_paretobin` | X-Function | 专属属性人工门禁 |
| X35 | 双Y轴柱状图 | `2Ys_Col.otpu` | 模板 | 原生结构已证 |
| X36 | 双Y轴柱线图 | `2Ys_ColSymb.otpu` | 模板 | 原生结构已证 |
| X38 | Y偏移堆叠线图 | `OffsetStackY.otp` | 模板 | 专属属性人工门禁 |
| X39 | 线条序列图 | `Plot.ogs [LineSeries]` / `BoxLser.otpu` | 菜单＋模板 | 宽表原位、单一 PID206 组跨列按行连接；3→5列、5→12行及 Agent 组/成员编辑均已独立 fresh 读回 |
| X40 | 前后对比图 | `Plot.ogs [BeforeAfter]` / `BeforeAfter.otpu` | 菜单＋模板 | 两列宽表原位、单一 PID206 组、Subgroup Size=2；6→15行及 Agent 组/成员编辑均已独立 fresh 读回 |
| S61 | 带标签热图（混淆矩阵语义） | `plotvm` / `Heat_Map_With_Labels.otpu` | X-Function＋模板 | clean dynamic rebuild 与 fresh-reopen 已闭合 |

## 已删除 ID 的兼容边界

`K16`、`S01`、`S21` 不属于 `OriginRecipe`、图形目录或任何 renderer/export
能力。旧项目引用这些 ID 时，引擎只返回 `CHART_TYPE_REMOVED`，不得创建
worksheet、graph、OPJU 或近似替代图。兼容墓碑不是隐藏 recipe，也不参与35图资格计数。

## 本机 dispatcher 门禁

- 基础菜单图必须执行 Recipe 中对应的 `Plot.ogs`/`Plot3D.ogs` section 或
  `worksheet -p` 路线，不得改成“空模板＋逐个 AddPlot”。
- 分组柱、Trellis、帕累托分别固定为 `plot_gindexed`、`plot_group`、
  `plot_paretobin`；多面板组合固定为 `merge_graph`。
- 热图与带标签热图固定为本机 `GenericHeatMap ... 105 1 1`/`plotvm`
  路线；数据源必须是 MatrixBook 或明确的 Virtual Matrix，不能以图片代替。
- 线条序列、前后对比固定走 `BoxChartImp BoxLser` 与
  `general,206 BeforeAfter`。row-wise/subgroup 结构已经由官方样例、默认态、
  编辑态、动态数据和独立 fresh reopen 实证；旧的“转置成多条普通 XY 线”路径已移除。

## 与公开 Agent 动作的关系

`OriginRecipe` 不增加 Agent 顶层动作。Agent 仍只使用公开的
`create_plot`、`bind_fields`、`set_title`、`set_axis`、
`set_series_style`、`set_legend`、`set_chart_parameter`、
`add_annotation` 和 `export_plot`。各 Profile 只开放 Matplotlib 与 Origin
都能稳定表达并读回的参数；Origin 专属创建细节完全留在 renderer 内部。
