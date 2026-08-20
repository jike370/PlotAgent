# PlotAgent 固定绘图计算与科学边界

> 状态：当前 Beta 固定绘图计算合同
> 适用范围：PlotCalculationSpec/Result、需要预计算字段的图形、缺失策略、完整数据与后续科学分析边界
> 相关文档：[受控数据准备、单位与来源追溯](./DATA-TRANSFORMS.md)、[领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)、[渲染管线](./RENDERING-PIPELINE.md)、[产品决策](./PRODUCT-DECISIONS.md)、[PRD](./PRD.md)

## 1. 当前计算边界

当前产品不是通用科研分析或拟合平台。`AnalysisSpec/AnalysisResult`、`FitSpec/FitResult`、统计检验、显著性、相关、回归、平滑、基线、归一化、KM 估计和 4PL/5PL 拟合均不属于公开 Action、任务或发布门禁。

当前产品只保留与图形几何不可分割、由 Engine Profile 固定的 `PlotCalculationSpec/PlotCalculationResult`。它们：

- 是封闭 discriminated union，不允许运行时增加 kind。
- 不支持任意表达式、自由串联、用户代码或把结果发布为通用数据集。
- 由本地图形 compiler 根据用户选图、明确参数和 FieldMapping 生成；模型不能选择、编排或执行计算。
- 在完整 PreparedDataset 上运行，持久化全部参数、算法版本、输入/输出哈希和纳入/排除计数。
- 被 Matplotlib、SVG 与 Origin 共同消费；renderer/Origin 不得各用自己的默认算法重算。

## 2. 封闭 PlotCalculationSpec 联合

当前只允许以下八个 kind：

1. `HistogramBinningSpec`
2. `TukeyBoxSpec`
3. `ViolinKDESpec`
4. `ECDFSpec`
5. `SummaryErrorSpec`
6. `PercentStackSpec`
7. `MatrixProjectionSpec`
8. `ConfusionCountSpec`

没有 fallback kind。图形注册表未声明的计算必须返回 `PLOTSPEC_CALCULATION_UNSUPPORTED`；不能降级为 pandas/Origin/Matplotlib 默认计算。

## 3. 固定算法与默认值

### 3.1 Histogram

- 默认 Freedman–Diaconis bin width。
- IQR 为 0 时回退 Sturges。
- 全部有效值相同时使用一个 bin。
- bins/edges/counts 进入 PlotCalculationResult；renderer 不重新分箱。

### 3.2 Tukey box

- 固定版本的线性分位数。
- whisker 为 1.5 IQR 规则。
- 离群点只标记，不从输入删除。
- quartiles、whiskers、outlier row refs 与 n 持久化。

### 3.3 Violin 与 density KDE

- Gaussian kernel、Scott bandwidth、256 point grid。
- violin grid 裁剪到观测范围。
- density grid 在两端延伸 3 bandwidth。
- bandwidth、grid、density 与输入 mask 持久化，不由 renderer 重算。

### 3.4 ECDF / CCDF

- ECDF 为右连续 `count(x_i <= x) / n` 阶梯。
- CCDF 使用对应反向累计定义并记录 mode。
- 排序规则、重复值处理和有效 n 由算法版本固定。

### 3.5 Summary/error

用户只能明确选择以下一种：

- `mean ± SD`
- `mean ± SEM`
- `mean ± 95% two-sided t CI`
- `median + IQR`
- `median + range`
- 直接提供 center + lower/upper
- 直接提供 center + symmetric error

SD 固定 `ddof=1`；SEM=`SD/sqrt(n)`；95% CI 使用双侧 t 区间；计算型 summary 每组至少 2 个有效值。误差语义不明时返回 NeedsInput，不创建任务。

### 3.6 Percent stack

- 仅接受非负组件。
- 每个类别的组件总和必须大于 0。
- 按类别分别归一化，输出原值、比例与总和；不修改 PreparedDataset。

### 3.7 Matrix projection 与 heatmap

- 只把已经确认的规则矩阵或唯一 XY 坐标投影为矩阵表。
- XY 坐标必须唯一；重复坐标阻断，不聚合、不取平均。
- K22 等高线只接受规则 grid，不执行 scattered-data gridding 或 interpolation。

### 3.8 Confusion count

- 支持原始 count、按真实类归一化、按预测类归一化。
- 类别顺序必须显式或由固定输入顺序产生。
- 不训练模型、不计算分类器结论或自动比较模型。

### 3.9 公共规则

- jitter 使用固定 seed 并写入 PlotCalculationResult。
- 公共 log axis 仅 Log10；参与绘图的非正值阻断，不静默跳过。
- missing policy 只允许 `fail` 或 `exclude_with_report`；后者保存排除行引用与原因。
- 参数变化创建新的 FigureVersion，并生成新的 PlotCalculationSpec/Result；不覆盖旧结果。

## 4. 需要预计算字段的正式图形

正式图形库固定为34张单图；依赖用户预计算字段的图在详情页和执行前确认区明确显示“需要预计算字段”。缺少输入时返回稳定的预计算输入错误。研究清单、内部 adapter 和已删除 ID 不会因具备预计算输入而开放：

| 图形 | 当前接受的预计算输入 | 当前不执行 |
| --- | --- | --- |
| K21 相关矩阵 | 已计算矩阵及标签 | Pearson/Spearman/显著性 |
| K22 等高线 | 规则 X×Y grid 与 Z | gridding/interpolation |
| S34 Nyquist | 已准备的 Z′/Z″ 与可选曲线 | 等效电路拟合 |

预计算输入仍须通过字段类型、单位、长度、范围与结构校验。PlotAgent 不把用户提供的分析结果宣传为本应用计算所得。

## 5. PlotCalculationResult

结果至少保存：

- `calculation_id`、kind、schema version、algorithm id/version。
- SourceDataset/PreparedDataset 精确版本和 input hash。
- 规范化参数、missing policy、fixed seed（如适用）。
- 总行数、纳入/排除数、分组 n、排除原因与非有限值计数。
- 图形消费所需的持久化 Plot Data 表及 output hash。
- warning/error、创建时间和 producer build hash。

它只服务于引用它的图表/批次/导出；当前没有把结果转为通用数据集的 Action。

## 6. 执行、版本与批量

- 单图计算作为任务中的原子阶段；只有 PlotCalculationResult 与引用它的 PlotDocument 均验证通过才更新当前版本。
- 完全同构批次使用规范化后相同的 FieldMapping、PreparationSpec 与 PlotCalculationSpec；没有逐文件算法或参数例外。
- 单项可失败并形成部分成功批次；失败不改变其他项，也不自动更换算法。
- preview 与 formal 使用同一 PlotCalculationResult。样式 patch 不重算；计算参数 patch 创建新 FigureVersion。
- 数据版本变化不会自动重算或替换旧结果；用户明确基于新输入重绘时创建新结果。

## 7. 后续科学分析阶段

AnalysisSpec/Result、FitSpec/Result、统计检验、科学拟合、平滑、基线、归一化与可物化分析输出均不在当前范围。未来启用时必须新增产品决策、Schema、错误、fixtures、provider context、storage 和 release gate；不得复用 PlotCalculationSpec 作为开放分析后门。

正式 34 图的准入只验证各图适用的直接数据、固定计算或预计算字段路径，不验证上述非产品算法的科学正确性；图形目录变化不会自动扩大 AnalysisSpec/FitSpec 范围。

## 8. 稳定错误与契约测试

至少覆盖：

- 八类kind的schema拒绝未知字段、禁止自由串联和禁止模型选择。
- 固定算法 golden：FD/Sturges/常量 histogram、Tukey outlier、KDE grid、ECDF ties、summary/error、percent stack、matrix duplicate、confusion normalization。
- `0/False` 有效、NaN/Inf/missing、`fail` 与 `exclude_with_report`。
- Log10 非正值阻断、固定 jitter seed、完整数据输入、result hash 可复现。
- 九个预计算图形的字段缺失、结构错误与有效输入。
- Matplotlib/SVG/Origin 消费同一 PlotCalculationResult，不发生 renderer-side 重算。

稳定错误归入 `PREPARE_*`、`PLOTSPEC_*` 或 `RENDER_*`，不复用通用 `ANALYSIS_*`/`FIT_*` 作为当前执行路径。
