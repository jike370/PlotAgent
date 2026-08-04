# PlotAgent 分析计算层与科学边界

> 状态：第一轮分析计算基线已确认  
> 日期：2026-08-05  
> 适用范围：数值数据的绘图计算、科学分析、显著性检验、AnalysisSpec、AnalysisResult 与批量一致性  
> 相关文档：[派生数据、单位与血缘契约](./DATA-TRANSFORMS.md)、[拟合系统契约](./FITTING-SYSTEM.md)、[后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)、[领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)、[任务运行时、取消与崩溃恢复](./TASK-RUNTIME.md)、[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)

## 1. 三层计算模型

第一轮把从数据到图形的工作分成三层，不把所有绘图都伪装成统计分析，也不允许 renderer 隐藏计算。

### 1.1 直接绘图

直接绘图只把已存在的 DatasetVersion 字段映射为位置、颜色、形状或标签：

- 折线、散点、已提供汇总值的柱状图等不需要生成新的统计量。
- 森林图直接使用用户提供的 effect、CI 和可选 weight。
- Nyquist 图直接使用频率、实部和虚部等数值字段。
- renderer 可以做坐标变换和像素布局，但不能计算误差、拟合、平滑、检验或新的数据值。

直接绘图仍记录精确 DatasetVersion、字段映射和 PlotSpec 版本，但不强制创建 AnalysisSpec。

### 1.2 绘图计算

绘图计算为构造图形几何而产生可复现数值，包括：

- 描述汇总和区间。
- 直方分箱、Tukey 箱线统计与 KDE。
- moving average、Savitzky-Golay 和 LOWESS 平滑。
- 混淆矩阵计数与归一化。

这些计算必须创建 AnalysisSpec 和 AnalysisResult。PlotSpec 只引用结果端口，不能在每次预览或导出时重新分箱、平滑或归一化。

### 1.3 科学分析

科学分析回答用户明确提出的估计或检验任务，包括相关、回归、剂量反应、生存分析和显著性检验。它必须：

- 由用户明确指定方法、设计和必要参数。
- 在本地白名单实现中运行，不执行任意 Python 或任意公式代码。
- 保存纳入与排除、估计量、区间、诊断、收敛和实现版本。
- 只生成结构化结果，不代替用户解释科研含义或形成结论。

## 2. 确认与 NeedsInput

### 2.1 一张确认卡

一次绘图所需的字段映射和计算设置在同一张确认卡完成：

- 先基于导入阶段形成的结构候选显示字段角色，再显示该图所需的分析方法与参数。
- 用户确认这张卡后，不再出现第二轮字段映射。
- 完全同构批次共享同一映射和同一 AnalysisSpec，不允许为单个文件设置例外。
- 计算参数的变化创建新的 AnalysisSpec，不回写或覆盖已完成结果。

### 2.2 模板与显式确认

绘图流程模板可以预填方法和透明参数。界面必须在执行前展示方法、关键参数、输入字段、缺失值策略、区间或校正设置；用户点击“执行”即视为对这些可见设置的确认。模板不能隐藏参数，也不能因为来源是官方模板就绕过校验。

Agent 可以解析用户已经明确表达的方法与参数，但不能替用户选择统计方法、拟合模型、平滑算法或显著性检验。以下情况返回 NeedsInput，不创建 ExecutionTask：

- 用户要求误差棒但未说明 SD、SE、CI 或其他误差语义。
- CI 缺少置信水平或来源定义。
- 显著性分析缺少检验、研究设计、比较集合或校正选择。
- 拟合、平滑或生存分析缺少注册表要求的必要参数。
- 指令与模板参数冲突，且无法通过确定性规则消解。

## 3. 第一轮分析注册表

注册表条目带稳定 kind、method ID、实现版本、输入角色、参数 Schema、输出端口和校验规则。第一轮只发布下表能力。

| 类别 | 第一轮方法 | 典型输出端口 |
| --- | --- | --- |
| 描述汇总 | count、missing、mean、median、SD、SE、min、max、quantile 等显式选择的汇总 | `summary_table`、`estimate` |
| 区间估计 | t interval、Bootstrap interval | `estimate`、`lower`、`upper`、`diagnostics` |
| 分布几何 | histogram、Tukey box、KDE | `bins`、`box_stats`、`density` |
| 相关 | Pearson、Spearman | `coefficient`、`p_value`、`n`、`matrix` |
| 拟合 | linear OLS/WLS、Huber robust、degree 2/3 polynomial、exponential、power law、4PL、5PL | `parameters`、`curve`、`bands`、`prediction`、`residuals`、`metrics`、`solver_diagnostics` |
| 平滑 | moving average、Savitzky-Golay、LOWESS | `smoothed_series`、`diagnostics` |
| 生存分析 | 右删失 KM、风险人数、Greenwood CI、用户显式选择的 Log-rank | `survival_curve`、`risk_table`、`confidence_band`、`test_result` |
| 混淆矩阵 | count、按真实类别归一化、按预测类别归一化、全局归一化 | `matrix`、`class_totals`、`normalization_metadata` |

“第一轮注册表”是能力上限，不是默认执行清单。图形模板只能预填其中的方法；未在注册表中的方法返回 UnsupportedRequest，不能由 Agent 换成“相近方法”。

## 4. 显著性检验白名单

第一轮显著性检验只允许：

- 两组均值：Student t、Welch t、paired t。
- 两组秩检验：Mann-Whitney U、Wilcoxon signed-rank。
- 多组总体检验：one-way ANOVA、Welch ANOVA、Kruskal-Wallis。
- 分类变量：chi-square、Fisher exact。
- 相关：Pearson、Spearman。
- 生存曲线：Log-rank。

多重比较校正只允许 Bonferroni、Holm 和 Benjamini-Hochberg（BH）。执行规则：

- 用户必须明确指定独立/配对设计、单双尾和比较集合；方法不得由样本表现自动切换。
- 多组数据必须列出要比较的组对或明确选择允许的总体检验，不能自动生成所有两两比较。
- 存在多个比较时必须选择白名单校正，或明确选择“不校正”。
- 明确不校正可以执行，但确认卡和结果中必须显示强警告，并记录用户选择。
- 输出默认保存并展示精确 p 值；星号仅是可选显示层，并保存阈值。

## 5. 第一轮硬边界

### 5.1 森林图与 Nyquist

- 森林图只绘制输入数据已提供的 effect、CI 和可选 weight，不计算 Meta 合并效应、异质性、亚组汇总或发表偏倚。
- Nyquist 图只绘制数值阻抗数据，不进行等效电路拟合或自动选择电路模型。

### 5.2 生存分析

- KM 仅支持右删失数据。
- 风险人数和 Greenwood CI 由同一固定输入与分组设计计算。
- Log-rank 只在用户明确指定时执行。
- 第一轮不支持竞争风险、区间删失、左删失、Cox 回归或其他生存模型。

### 5.3 回归、剂量反应与混淆矩阵

- 拟合只允许 linear OLS/WLS、显式 Huber robust、degree 2/3 polynomial、exponential、power law、4PL 和 5PL；不接受任意公式或 Python 代码，不自动选择阶数、模型、初值、边界或权重策略。
- FitSpec 必须显式记录原始观测、按 X 汇总中心、用户提供汇总+误差或按 replicate/group 分别拟合之一，不自动折叠重复或平均 replicate 参数。
- 权重语义、4PL/5PL 公式、确定性多起点、区间、外推、失败与持久化曲线表以 [拟合系统契约](./FITTING-SYSTEM.md) 为准。
- 混淆矩阵可以从真实标签与预测标签计算计数及三种归一化，也可以显示已提供矩阵；不训练模型、不比较模型优劣、不生成科研结论。

## 6. AnalysisSpec

AnalysisSpec 是一次分析意图的不可变、可版本化定义，至少包含：

- `spec_id`、`spec_version` 和 `schema_version`。
- `kind` 与 `method.id`、`method.implementation_version`。
- 精确的输入 DatasetVersion 引用及内容哈希。
- `field_roles`、`grouping` 和 `design`，使用稳定字段 ID。
- `missing_policy`，只能使用本文件定义的策略。
- `parameters`，包括窗口、带宽、阶数、初值等方法参数。
- `bounds`、`weights` 和相关字段引用。
- `uncertainty` 与 CI 方法、置信水平和来源语义。
- `comparisons`、单双尾设置与 `correction`。
- `seed`；任何随机过程都必须固定并保存种子。
- 命名且带类型的 `output_ports`。

方法不使用某字段时显式为空或不适用，不能把未声明参数塞入自由字典。AnalysisSpec 的规范化内容参与哈希，方法实现版本变化即使参数相同也视为不同规格。

## 7. AnalysisResult

AnalysisResult 是 AnalysisSpec 在固定输入上的不可变执行结果，至少保存：

- AnalysisSpec 引用、规范化规格哈希、输入 DatasetVersion 与输入内容哈希。
- 实际纳入和排除的样本、行数、分组计数及每类排除原因。
- 统计量、参数估计、精确 p 值、区间和结构化结果表引用。
- 残差、假设检查、稳定性提示、拟合诊断和收敛状态；不适用项明确标记。
- 每个命名输出端口的类型、单位、行列结构和内容对象引用。
- Python、NumPy、SciPy 及实际算法实现所依赖库的版本。
- 运行种子、完成状态、警告、失败代码和任务来源。

Result 哈希覆盖规格哈希、输入哈希、实现版本和输出对象哈希。显示文本不是科学真值；界面回复和导出摘要必须由结构化结果生成。

AnalysisResult 不自动成为普通 DatasetVersion。只有用户显式执行 `materialize_analysis_output`，才能把一个持久化表格 output port 复制为派生 DatasetVersion；该动作不重算分析，并按 [派生数据、单位与血缘契约](./DATA-TRANSFORMS.md) 保存 UnitSpec 与三层 lineage。

## 8. PlotSpec 引用规则

PlotSpec 通过精确的 AnalysisResult 版本和命名 output port 引用分析数据：

```text
PlotSpec.analysis_refs[]
├─ analysis_result_id
├─ analysis_result_version
├─ output_port
└─ expected_output_type
```

renderer 只读取端口，不重新执行分析，也不能基于当前数据偷偷刷新结果。重新计算会创建新的 AnalysisSpec/AnalysisResult；只有用户明确采用新结果时才创建引用新端口的 PlotSpec 版本。

## 9. 数据、数值与缺失规则

- 第一轮不做缺失值插补。
- 不自动识别或排除离群值；用户显式筛选时必须先生成新的 DatasetVersion。
- 单次分析的缺失策略只能是 `complete_case` 或 `fail_on_missing`。
- 相关矩阵可由用户明确选择 `pairwise_complete`；界面与结果必须显示每个系数实际使用的样本数。该策略不扩展到其他分析。
- 统计、拟合、分箱、平滑和检验使用完整输入数据；屏幕视觉降采样不能成为分析输入。
- 数值计算统一使用 float64。源数据的物理类型和精度仍保留在 DatasetVersion 元数据中。
- Bootstrap 等随机过程必须使用 AnalysisSpec 中的固定种子；未提供种子时不能临时使用系统随机状态。
- 非有限值、单位不兼容和算法定义域问题按阻止、警告或结果诊断明确记录，不静默清理。

## 10. 版本、过期与批量

### 10.1 数据更新

DatasetVersion 更新不会自动重算旧结果：

- AnalysisResult 保持不可变，并因上游存在更新版本而标为 `stale`。
- 引用旧结果的 PlotSpec 继续可复现显示，但必须展示过期状态。
- 用户明确重算后创建新的 AnalysisSpec 或新执行版本和新的 AnalysisResult。
- 系统不自动把新结果替换进既有 PlotSpec。

### 10.2 完全同构批次

- 批次中每个 DatasetVersion 必须满足同一最终语义签名。
- 所有项使用规范化后完全相同的 AnalysisSpec，包括方法实现版本、字段角色、参数、缺失策略、比较集合、校正和种子规则。
- 不允许逐文件修改字段映射、方法、参数、缺失策略或警告处理。
- 单项失败不改变其他项的方法；已完成项可以提交，批次形成 partially_succeeded 并保存逐项诊断。
- 失败项只能在相同规格下明确重跑；如果用户改变规格，则创建新的批次和新结果链。

## 11. 执行与验证

每个正式分析作为 ExecutionTask 运行，并遵循 [任务运行时、取消与崩溃恢复](./TASK-RUNTIME.md)：

1. 在入队前规范化并持久化 AnalysisSpec、输入版本和 expected version。
2. Scientific Validator 校验注册表、字段、单位、设计、参数、缺失策略和警告确认。
3. 隔离计算进程用固定库版本、float64 和固定种子执行。
4. Verifier 检查输出端口、样本计数、数值有限性、诊断与哈希。
5. 控制通道原子提交 AnalysisResult 和对象引用。

第一轮至少覆盖以下契约测试：

- 三层边界与 renderer 不重算。
- 同卡字段映射和计算确认、模板透明参数与 NeedsInput。
- 每个注册方法的合法输入、非法输入和输出端口。
- 显著性白名单、比较集合、校正与不校正强警告。
- 森林图、Nyquist、KM、拟合与混淆矩阵硬边界。
- complete-case、fail、相关矩阵 pairwise、无插补和无自动离群排除。
- float64、固定种子、完整数据计算和依赖版本记录。
- stale 标记、显式重算、PlotSpec 引用切换和完全同构批次部分失败。
