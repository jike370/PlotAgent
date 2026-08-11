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

## 35 图 Origin renderer 范围

| ID | 中文名称 | 官方模板或流程 | 创建类型 | 证据 |
|---|---|---|---|---|
| K01 | 折线图 | `LINE.otpu` | 模板 | 原生结构已证 |
| K02 | 线+符号图 | `LINESYMB.otpu` | 模板 | 原生结构已证 |
| K03 | 二维散点图 | `SCATTER.OTP` | 模板 | 原生结构已证 |
| K04 | 索引大小气泡与颜色映射图 | `bubble.otpu` | 模板 | 原生结构已证 |
| K06 | XY双向误差棒图 | `ERRBAR.otpu` | 模板 | 原生结构已证 |
| K07 | 误差带图 | `ERRORBAND.otp` | 模板 | 原生结构已证 |
| K08 | 柱状图 | `COLUMN.otpu` | 模板 | 原生结构已证 |
| K09 | 分组柱状图（索引数据） | `gColumn.otpu` + `plot_gindexed` | X-Function | 专属属性人工门禁 |
| K10 | 堆积柱状图 | `COLUMN.otpu` + 原生累计堆积 | 模板 | 原生结构已证 |
| K11 | 100%堆积柱状图 | `COLUMN.otpu` + 原生百分比堆积 | 模板 | 原生结构已证 |
| K12 | 列散点图 | `ColumnScatter.otp` | 模板 | 专属属性人工门禁 |
| K13 | 箱线图 | `BOX.OTP` + Tukey 1.5×IQR | 模板 | 专属属性人工门禁 |
| K14 | 小提琴图 | `Violin.otpu` | 模板 | 专属属性人工门禁 |
| K15 | 直方图 | `Hist.otpu` / plot type 219 | 模板 | 原生结构已证 |
| K18 | 面积图 | `AREA.otpu` | 模板 | 专属属性人工门禁 |
| K19 | 日期时间折线图 | `LINE.otpu` + Date/Time X | 模板 | 原生结构已证 |
| K20 | 热图 | `Heat_Map.otpu` + Matrix | 模板 | 专属属性人工门禁 |
| K21 | 带标签热图 | `Heat_Map_With_Labels.otpu` + Matrix | 模板 | 专属属性人工门禁 |
| K22 | 填色等高线 | `CONTOUR.otpu` + Matrix | 模板 | 专属属性人工门禁 |
| K24 | Trellis分面图 | `Grouped.otp` + `plot_group` | X-Function | 专属属性人工门禁 |
| K25 | 多面板组合图 | `mgroups.otpu` / Merge Graph Windows | 组合 | 原生结构已证 |
| S01 | Kaplan-Meier生存曲线 | `kaplanmeier` 官方分析 | 分析 | 专属属性人工门禁 |
| S34 | Nyquist图 | `LINESYMB.otpu` + EIS语义 | 模板 | 原生结构已证 |
| X02 | 垂线图 | `DROPLINE.OTP` | 模板 | 专属属性人工门禁 |
| X03 | 棒棒糖图 | `Lollipop.otpu` | 模板 | 专属属性人工门禁 |
| X05 | 蜂群图 | `Beeswarm.otpu` | 模板 | 专属属性人工门禁 |
| X09 | 浮动柱状图 | `FloatCol.otp` | 模板 | 专属属性人工门禁 |
| X13 | 人口金字塔 | `PopulationPyramid.otpu` | 模板 | 专属属性人工门禁 |
| X23 | 双Y轴Y-Y图 | `DOUBLEY.OTP` | 模板 | 原生结构已证 |
| X24 | 帕累托图（分箱数据） | `ParetoBin.otpu` + `plot_paretobin` | X-Function | 专属属性人工门禁 |
| X35 | 双Y轴柱状图 | `2Ys_Col.otpu` | 模板 | 原生结构已证 |
| X36 | 双Y轴柱线图 | `2Ys_ColSymb.otpu` | 模板 | 原生结构已证 |
| X38 | Y偏移堆叠线图 | `OffsetStackY.otp` | 模板 | 专属属性人工门禁 |
| X39 | 线条序列图 | `BoxLser.otpu` | 模板 | 专属属性人工门禁 |
| X40 | 前后对比图 | `BeforeAfter.otpu` | 模板 | 专属属性人工门禁 |

## 暂不进入 Origin renderer 的 3 图

| ID | 原因 | 禁止的替代实现 |
|---|---|---|
| K16 | Origin 2024 fresh reopen 后 bins 重新显示，当前不构成纯 KDE | 不得用预计算 XY 密度线冒充官方流程 |
| S21 | 官方 Forest Plot App 尚未安装和实证 | 不得用普通误差棒、手工线段或 Python 森林图替代 |
| S61 | clean dynamic rebuild 自动化链尚未闭合 | 不得把已有静态热图证据当作动态 renderer 通过 |

## 与公开 Agent 动作的关系

`OriginRecipe` 不增加 Agent 顶层动作。Agent 仍只使用公开的
`create_plot`、`bind_fields`、`set_title`、`set_axis`、
`set_series_style`、`set_legend`、`set_chart_parameter`、
`add_annotation` 和 `export_plot`。各 Profile 只开放 Matplotlib 与 Origin
都能稳定表达并读回的参数；Origin 专属创建细节完全留在 renderer 内部。

