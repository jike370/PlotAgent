# PlotAgent v3 Origin Recipes

> 当前范围：34 张单图。每个 recipe 绑定 Origin 官方模板、菜单 section 或 X-Function；组合图和 K25 不存在于生产 recipe registry。

## Recipe 约束

每个 recipe 至少声明：

- 图类 ID 与中文名称；
- 官方帮助入口；
- 本机 Origin 版本、模板/脚本资产及 SHA-256；
- worksheet 或 matrix 的列 designation；
- 官方创建命令；
- 默认、编辑、动态数据和 fresh-reopen 的原生读回合同；
- Agent 可编辑对象与不支持动作；
- 失败时的稳定错误，不允许近似回退。

## 正式清单

| 图类 | Origin 官方模板或流程 |
|---|---|
| 折线图 | `LINE.otpu` |
| 线点图 | `LINESYMB.otpu` |
| 散点图 | `SCATTER.OTP` |
| 气泡与颜色映射散点图 | `Bubble` 菜单 / `bubble.otpu` |
| 双向误差棒图 | X Y Error 菜单 / `ERRBAR.otpu` |
| 误差带图 | `ScatterErrorBand` / `ERRORBAND.otp` |
| 柱状图 | `COLUMN.otpu` |
| 分组柱状图 | `gColumn.otpu` + `plot_gindexed` |
| 堆积柱状图 | `STACKCOLUMN.otp` / `StackCol` |
| 100% 堆积柱状图 | `StackColP.otp` / `StackColPercentage` |
| 列散点图 | `ColumnScatter.otp` |
| Tukey 箱线图 | `BOX.OTP` + 1.5×IQR 参数 |
| 小提琴图 | `Violin.otpu` |
| 直方图 | `Hist.otpu` / PID 219 |
| 面积图 | `AREA.otpu` |
| 日期时间折线图 | `LINE.otpu` + Date/Time X |
| 热图 | `Heat_Map.otpu` + Matrix |
| 相关矩阵图 | `Heat_Map_With_Labels.otpu` + Matrix |
| 填色等高线图 | `CONTOUR.otpu` + Matrix |
| Trellis 分面图 | `Grouped.otp` + `plot_group` |
| Nyquist 图 | `LINESYMB.otpu` + EIS 语义 |
| 混淆矩阵 | `Heat_Map_With_Labels.otpu` |
| 垂线图 | `DROPLINE.OTP` |
| 棒棒糖图 | `Lollipop.otpu` |
| 蜂群图 | `Beeswarm.otpu` |
| 浮动柱状图 | `FloatCol.otp` |
| 人口金字塔 | `PopulationPyramid.otpu` |
| 双 Y 轴 Y-Y 图 | `DOUBLEY.OTP` |
| 帕累托图 | `ParetoBin.otpu` + `plot_paretobin` |
| 双 Y 轴柱状图 | `2Ys_Col.otpu` |
| 双 Y 轴柱线图 | `2Ys_ColSymb.otpu` |
| Y 偏移堆叠线图 | `OffsetStackY.otp` |
| 线条序列图 | `BoxLser.otpu` / `LineSeries` |
| 前后对比图 | `BeforeAfter.otpu` / `BeforeAfter` |

精确 ID、模板哈希、数据合同和逐图注意事项见 [Origin 官方模板映射](./ORIGIN-OFFICIAL-TEMPLATE-MAPPING.md)。

## 删除规则

`K16`、`K25`、`S01`、`S21` 及此前已删除图类不得出现在 recipe registry、Agent capability、图形库、导出候选或资格计数中。只允许旧项目读取时返回 `CHART_TYPE_REMOVED`。
