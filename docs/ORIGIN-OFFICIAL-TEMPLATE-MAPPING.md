# PlotAgent v3：34 图 Origin 官方模板映射

> 当前基线：34 张单图；不支持组合图。K25 已从生产链删除。每张图先以 Origin 官方帮助、本机模板和菜单命令为依据，再由独立 renderer 绑定动态数据和 Agent 公共编辑。

## 1. 设计规则

- T1：官方模板/菜单可直接承载结构；Python 负责数据 designation、明确参数和编辑。
- T2：官方模板或 X-Function承载主体；Python 只补必要的矩阵、标签、轴或科研语义。
- 默认态不得由普通线、柱、散点或 fill 几何近似重构官方专属图。
- Matplotlib 与 Origin 共享字段/对象语义，不要求共享几何代码。
- Origin 资格必须包含全新会话 fresh-reopen 和原生结构读回。
- 标准单层笛卡尔图在官方模板完成后统一补齐四侧轴线；矩阵/色图、原生 Trellis、中央轴和重叠双轴模板保留官方轴框拓扑。上、右补齐边只作为干净外框，主/次刻度线和刻度值必须关闭；真正的双轴模板按官方拓扑保留右轴语义。显式轴线编辑仍优先。

## 2. 正式映射

| ID | 中文图类 | Origin 官方模板或流程 | 等级 | 关键合同 |
|---|---|---|---|---|
| K01 | 折线图 | `LINE.otpu` | T1 | X + 1..N Y；PID 200 |
| K02 | 线点图 | `LINESYMB.otpu` | T1 | 每系列线与点同一身份 |
| K03 | 散点图 | `SCATTER.OTP` | T1 | X/Y；不自动连线 |
| K04 | 气泡与颜色映射散点图 | Bubble 菜单 / `bubble.otpu` | T2 | X/Y/Size/Color；默认不显示额外 color scale |
| K06 | 双向误差棒图 | X Y Error 菜单 / `ERRBAR.otpu` | T1 | X、中心、X下/上界、Y下/上界；落为原生正负误差列 |
| K07 | 误差带图 | `ScatterErrorBand` / `ERRORBAND.otp` | T1 | X/Center/Lower/Upper；上下界不进图例 |
| K08 | 柱状图 | `COLUMN.otpu` | T1 | Category/Value |
| K09 | 分组柱状图 | `gColumn.otpu` + `plot_gindexed` | T2 | 索引分组，不手工拆柱 |
| K10 | 堆积柱状图 | `STACKCOLUMN.otp` / `StackCol` | T1 | 原始值；Origin 原生累计堆积 |
| K11 | 100% 堆积柱状图 | `StackColP.otp` / `StackColPercentage` | T1 | 原始值；Origin 原生百分比归一化 |
| K12 | 列散点图 | `ColumnScatter.otp` | T2 | 每组一列原始观测；Data/Jitter |
| K13 | Tukey 箱线图 | `BOX.OTP` | T1 | 25/75 箱体、Outlier whisker、系数 1.5 |
| K14 | 小提琴图 | `Violin.otpu` | T1 | Kernel Smooth、冻结带宽、Extend=0 |
| K15 | 直方图 | `Hist.otpu` / PID 219 | T1 | 原始观测；冻结 begin/end/bin size；Count |
| K18 | 面积图 | `AREA.otpu` | T1 | X + `series_1..series_N` |
| K19 | 日期时间折线图 | `LINE.otpu` + Date/Time X | T1 | Date X + `series_1..series_N`；PID 200 |
| K20 | 热图 | `Heat_Map.otpu` + Matrix | T1 | 行列语义、palette、range |
| K21 | 相关矩阵图 | `Heat_Map_With_Labels.otpu` + Matrix | T1 | long/wide 输入适配为预计算相关矩阵 |
| K22 | 填色等高线图 | `CONTOUR.otpu` + Matrix | T1 | 规则 Matrix、levels、palette |
| K24 | Trellis 分面图 | `Grouped.otp` + `plot_group` | T2 | 单层原生 Trellis；facet 顺序保持 |
| S34 | Nyquist 图 | `LINESYMB.otpu` + EIS 语义 | T2 | Z′/−Z″；等比例轴；频率不是坐标 |
| S61 | 混淆矩阵 | `Heat_Map_With_Labels.otpu` | T2 | 原始样本或预聚合 Count → 同一原生矩阵 |
| X02 | 垂线图 | `DROPLINE.OTP` | T1 | drop line 落至绘图区底部轴 |
| X03 | 棒棒糖图 | `Lollipop.otpu` | T1 | 类别 + 2..N 数值系列；不画零基线 stems |
| X05 | 蜂群图 | `Beeswarm.otpu` | T1 | 原始 Value + Group；原生 Swarm |
| X09 | 浮动柱状图 | `FloatCol.otp` | T1 | Category + 原始有序边界；禁止排序/复制边界 |
| X13 | 人口金字塔 | `PopulationPyramid.otpu` | T1 | Category + Left + Right；类别位于中央零轴 |
| X23 | 双 Y 轴 Y-Y 图 | `DOUBLEY.OTP` | T1 | 共享 X；两层 PID 202；X 1:1 linked、Y 独立 |
| X24 | 帕累托图 | `ParetoBin.otpu` + `plot_paretobin` | T1 | Category/Count；累计百分比只有一个权威来源 |
| X35 | 双 Y 轴柱状图 | `2Ys_Col.otpu` | T1 | 两侧普通柱；不得出现浮动柱语义 |
| X36 | 双 Y 轴柱线图 | `2Ys_ColSymb.otpu` | T1 | 左柱、右线点；层关系保持 |
| X38 | Y 偏移堆叠线图 | `OffsetStackY.otp` | T1 | X + 1..N Y；offset 只影响显示 |
| X39 | 线条序列图 | `BoxLser.otpu` / `LineSeries` | T1 | 宽表不转置；每行跨列连接 |
| X40 | 前后对比图 | `BeforeAfter.otpu` / `BeforeAfter` | T1 | Subject/Before/After/可选 Group；成对连接保留身份 |

## 3. 删除项

`K16`、`K25`、`S01`、`S21` 以及此前删除的图类均不属于当前映射。删除完成的判据是：图形库不可见、Agent capability 不含该 ID、字段契约与双后端不可分派、导出与资格清单不计数、旧项目只返回 `CHART_TYPE_REMOVED`。

## 4. 动态与编辑门禁

每图至少测试：

- 行数变化；
- 合法的系列/组/类别数量变化；
- 跨零、全负、缺失值及不同数量级；
- 图类允许的标题、轴、系列、图例与参数编辑；
- 保存后全新 Origin 会话重开；
- worksheet/matrix、plot/layer、源绑定和编辑值读回；
- OPJU 中对象仍可人工编辑。

## 5. 当前证据状态

视觉、OPJU 与原生读回证据只对其冻结提交有效。模板、renderer、共享 T1 适配器或图类合同变化后，必须基于当前候选重新生成受影响图类的证据，不能继承历史 PASS。
