# PlotAgent 拟合系统契约

> 状态：第一轮拟合系统基线已确认  
> 日期：2026-08-05  
> 适用范围：FitSpec、线性与非线性白名单模型、输入层级、权重、初始化、区间、外推、FitResult 与正式导出  
> 相关文档：[分析计算层与科学边界](./ANALYSIS-ENGINE.md)、[领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)、[后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)、[任务运行时、取消与崩溃恢复](./TASK-RUNTIME.md)、[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)

## 1. 契约位置

FitSpec 是 AnalysisSpec 的带 discriminator 专用变体，FitResult 是 AnalysisResult 的拟合结果变体。它们继承固定 DatasetVersion、方法实现版本、float64、固定种子、缺失策略、expected version 和命名输出端口等通用约束。

拟合不是 renderer 的样式功能：

- 字段映射、输入层级、模型、参数边界、权重和区间设置在执行前可见。
- 用户明确执行后创建 FitSpec，并由独立 ExecutionTask 产生 FitResult。
- PlotSpec 只引用 FitResult 的持久化端口和曲线表。
- Matplotlib、Origin、PNG/SVG/OPJU 导出器都不能重新拟合。

## 2. 第一轮模型白名单

FitSpec 的 `model.id` 只能是：

| 模型 ID | 第一轮语义 | 必须显式的设置 |
| --- | --- | --- |
| `linear_ols` | 普通最小二乘直线 | `include_intercept: true/false` |
| `linear_wls` | 加权最小二乘直线 | 截距设置与 weight semantics |
| `huber_robust` | 显式 Huber robust 直线拟合 | 截距设置与 Huber 参数 |
| `polynomial_2` | degree 2 polynomial | 截距设置 |
| `polynomial_3` | degree 3 polynomial | 截距设置 |
| `exponential` | 版本化的指数模型 | 参数边界与初始化策略 |
| `power_law` | 版本化的幂律模型 | 参数边界、初始化策略与正值定义域 |
| `logistic_4pl` | 固定公式的 4PL log-dose 模型 | 参数边界、初始化策略与剂量语义 |
| `logistic_5pl` | 固定公式的 5PL log-dose 模型 | 参数边界、初始化策略、剂量语义与 asymmetry |

第一轮不支持：

- 任意公式、用户 Python、模型生成代码或自定义目标函数。
- 自动选择多项式阶数。
- 自动模型比较、逐步回归或按指标挑选“最佳模型”。
- 拟合失败后自动切换模型。

模型公式、参数顺序、边界语义和实现版本属于注册表的一部分。相同 `model.id` 的公式变更必须提升实现版本，旧 FitResult 仍使用旧版本复现。

## 3. 拟合输入层级

FitSpec 必须通过 `input_level` 明确记录以下四类之一：

### 3.1 `raw_observations`

- 使用全部符合纳入规则的原始观测行。
- 相同 X 的重复观测保持为独立点，不自动折叠或平均。
- 缺失与排除 mask 按原始行记录。

### 3.2 `x_center_summary`

- 先按 X 形成显式中心汇总，再对汇总结果拟合。
- 汇总方法、分组键、每个 X 的样本数和生成的结果表引用必须记录。
- 该汇总是明确的上游绘图计算，不得由拟合器临时隐藏执行。

### 3.3 `provided_summary_error`

- 输入是用户已经提供的中心值和误差列。
- FitSpec 记录中心、误差、样本数等字段角色以及误差语义。
- 不把误差列名猜成 SD、SE、variance 或 weight；语义不明确时返回 NeedsInput。

### 3.4 `fit_by_replicate_or_group`

- 按用户明确指定的 replicate 或 group 字段分别拟合。
- 每个组生成独立 FitResult 子结果和独立诊断。
- 不自动平均不同 replicate 的参数，也不把参数均值伪装成整体拟合。
- 如果用户需要参数汇总，必须另建显式 AnalysisSpec。

输入层级是科学语义而非性能选项。切换层级会创建新的 FitSpec，不能作为同一结果的显示切换。

## 4. 权重契约

`weighting.semantic` 只能是：

- `direct_weight`：输入值直接作为非负拟合权重。
- `variance`：转换为 `weight = 1 / variance`。
- `sd`：转换为 `weight = 1 / sd²`。
- `se`：转换为 `weight = 1 / se²`。

FitSpec 与 FitResult 必须保存：

- 权重来源字段的稳定 ID、名称、单位和 DatasetVersion。
- 用户选择的语义、转换公式、实现版本和转换后权重表引用。
- 非有限、零或负值的校验结果与逐行 mask 原因。
- 求解器实际接收的权重及任何仅为数值稳定性进行的等比例缩放。

系统不根据 `error`、`sd`、`sem` 等列名猜权重语义，也不自动把现有误差棒当作 WLS 权重。没有有效权重时，WLS 返回 NeedsInput 或验证失败，不能静默退化为 OLS。

## 5. 轴尺度、模型变换与派生数据

坐标轴显示与模型数学定义彼此独立：

- 把 X 或 Y 轴设为 logarithmic 不会把线性模型变成 log-linear，也不会改变 FitSpec。
- 模型使用 log 域时必须由注册表公式明确规定，并在执行前校验定义域。
- `power_law` 等需要正值的模型遇到非正输入时阻止执行，不能静默删除或加常数。
- 对数轴遇到非正显示值仍按绘图校验处理，与拟合纳入 mask 分开记录。

归一化必须先生成可追溯的派生 DatasetVersion，拟合器不能在内部临时归一化。剂量为零时：

- 用户可以把零剂量显式标记为 `control`。
- control 点可以在图中显示，但不进入 4PL/5PL 的 log-dose 拟合。
- FitResult mask 记录 `control_zero_dose`，并分别报告显示点数与拟合点数。
- 未标记为 control 的零或负剂量触发定义域失败。

## 6. 4PL 与 5PL 固定公式

### 6.1 公共定义

对正剂量 `dose`，令：

```text
x = log10(dose / x_unit)
```

其中 `x_unit` 是 DatasetVersion 中固定的 X 物理单位。参数使用：

- `lower`：响应下渐近值。
- `upper`：响应上渐近值。
- `log_midpoint`：log-dose 中点参数。
- `slope`：带符号斜率参数。
- `asymmetry`：仅 5PL 使用，且必须大于零。

注册表约束 `lower < upper` 且 `slope` 为有限非零值，因此 slope 的正负可以唯一表示上升或下降方向。

### 6.2 4PL v1

```text
y = lower + (upper - lower) /
    (1 + 10 ^ (-slope * (x - log_midpoint)))
```

4PL 中 `x_unit × 10 ^ log_midpoint` 是 50% response dose。`slope > 0` 表示响应随剂量上升，`slope < 0` 表示响应随剂量下降；系统不强制把斜率改成正值，也不交换数据来伪造方向。

### 6.3 5PL v1

```text
y = lower + (upper - lower) /
    (1 + 10 ^ (-slope * (x - log_midpoint))) ^ asymmetry
```

5PL 中 `log_midpoint` 是模型中点参数，不等同于实际 50% response dose。实际 50% response 的 log-dose 为：

```text
log_dose_50 = log_midpoint
              - log10(2 ^ (1 / asymmetry) - 1) / slope
```

当 `asymmetry = 1` 时，5PL 退化为 4PL，两个中点才一致。FitResult 必须分别输出 `model_midpoint_parameter` 和 `response_50_dose`，不能把前者标成 IC50/EC50。

### 6.4 标签与单位

- IC50、EC50、ED50 或通用“50% response dose”标签由用户明确选择；Agent 不根据列名、曲线方向或学科自动决定。
- 未明确标签时只显示“50% response dose”或“模型中点参数”等中性名称。
- dose 中点、IC50、EC50 和 ED50 从 log 域还原后继承 X 的物理单位。
- 中点或 50% response dose 落在 observed X range 之外时标为 `extrapolated`。

## 7. 初始化、边界与多起点

### 7.1 确定性初始化

每个非线性模型在注册表中绑定版本化的 deterministic initializer。FitSpec 保存：

- `initializer.strategy_id` 与 `implementation_version`。
- 由固定输入数据和参数边界生成初值的规则。
- 用户在高级设置中显式覆盖的参数初值。

同一输入、同一规格和同一实现版本必须生成相同初值。

### 7.2 有界确定性 multistart

- 非线性求解使用边界内的 deterministic multistart，不依赖未记录随机状态。
- 候选起点数量、生成算法、参数边界和选解规则版本化。
- FitResult 保存每个起点、终止状态、目标函数值、迭代信息，以及最终选中解的索引和确定性选中理由。
- 高级用户可以覆盖初值或边界；覆盖值成为 FitSpec 的正式字段并通过同样校验。

拟合失败时绝不自动切换模型、删除数据点、放宽边界、改变权重或改变输入层级。完全同构批次使用完全相同的 initializer 算法与版本；算法可以按每份数据确定性地产生不同数值初值，但不允许逐文件手工例外。

## 8. 不确定性与区间

界面、FitSpec 和 FitResult 必须区分：

1. **Parameter CI**：模型参数本身的置信区间。
2. **Mean confidence band**：给定 X 处平均响应的置信带。
3. **New-observation prediction interval**：给定 X 处新观测值的预测区间。

三者使用不同设置和输出端口，不能共用“置信区间”一个模糊开关。不存在统计支持时，端口明确为不可用，不用其他区间替代。

非线性模型第一轮允许两类明确选择的不确定性方法：

- `jacobian_covariance`：保存 Jacobian、协方差估计、自由度、假设与失败诊断。
- `bootstrap`：保存重采样方法、次数、固定 seed、成功/失败次数和区间算法。

Bootstrap 的 `resampling_unit` 必须明确为 `row`、`replicate` 或 `subject`。当数据设计需要 replicate/subject 而字段未映射时返回 NeedsInput；系统不能默认按行重采样。

## 9. 曲线范围与外推

- 默认曲线表只覆盖 observed X range。
- X 网格、点数和端点由 FitSpec 固定并保存到 FitResult。
- 用户可以显式启用外推并给出范围；外推区段在持久化曲线表中带 `is_extrapolated` 标记。
- 图中外推部分必须以可辨认样式区分，图例或提示说明外推范围。
- 参数中点、IC50、EC50、ED50 或实际 50% response dose 超出 observed X range 时，即使落在用户扩展曲线范围内，也标记 `extrapolated`。
- 正式导出不得扩大曲线范围或补算更密网格。

## 10. 失败与警告

### 10.1 阻止或失败

以下情况不生成成功曲线：

- 模型、输入层级、截距设置、权重语义或必要参数未明确。
- 有效观测数或不同 X 数不足以识别模型参数。
- 数据违反模型 log 域、单位、缺失策略或权重定义域。
- 初值或用户边界非法、互相矛盾或没有可行区域。
- 所有 multistart 都未收敛到边界内有限解。
- 输出参数、目标函数、协方差或生成曲线包含未解释的非有限值。
- FitResult 校验、输出表持久化或原子提交失败。

失败时保留 raw points 和逐行 mask，显示失败代码与可执行修正项；不绘制最后一次迭代曲线、伪造收敛曲线或用其他模型代替。

### 10.2 可继续但必须警告

以下结果可以保存，但必须带结构化 warning：

- 参数触及或非常接近边界。
- Jacobian、协方差或设计矩阵病态，参数相关性过高。
- 区间极宽、不可估计或 Bootstrap 成功比例不足预设阈值。
- 重复 X、X 覆盖或样本量对目标模型非常有限。
- 目标量、模型中点或 50% response dose 位于 observed range 外。
- 高影响观测、残差结构或异方差诊断提示模型风险。

warning 不触发自动删点、自动换模型或自动放宽边界。用户决定继续时，选择与 warning 一起进入操作记录。

## 11. FitResult

FitResult 除通用 AnalysisResult 字段外，必须提供命名输出：

- `parameters`：参数估计、单位、边界状态与可选 parameter CI。
- `intervals`：区间方法、水平和结构化结果。
- `curve`：observed range 内的持久化曲线表。
- `bands`：mean confidence band 表。
- `prediction`：new-observation prediction interval 表。
- `residuals`：逐观测残差表。
- `fitted`：逐观测 fitted value 表。
- `metrics`：与模型和目标函数匹配的指标。
- `solver_diagnostics`：初始化、全部起点、终止、目标值、Jacobian/协方差与选解信息。
- `mask`：纳入、排除、control、缺失和定义域原因。
- `warnings`：结构化风险、外推和区间诊断。

R² 仅在数学定义和模型语境适用时作为一个指标输出，不是所有模型的通用成功标准，也不能单独决定收敛、模型有效或结果可接受。成功状态由模型定义域、求解器终止、参数有限性、输出验证和提交契约共同决定。

## 12. 渲染与正式导出

- `curve`、`bands` 和 `prediction` 都是 FitResult 中持久化、带哈希的数值表。
- PlotSpec 引用精确 FitResult 版本与输出端口；样式修改不触发重新拟合。
- Matplotlib 预览、PNG/SVG 和 Origin OPJU 从同一持久化表构建曲线与带区间。
- Origin 只接收原始/派生数值、持久化拟合表、参数和诊断，不调用 Origin 自己的拟合器重新估计。
- 任何更密网格、新区间、新外推范围或新参数都必须创建新的 FitSpec/FitResult。
- 正式导出记录 FitResult 哈希、曲线表哈希、模型实现版本和源 DatasetVersion。

## 13. 第一轮契约测试

- 九个模型 ID、显式截距、degree 2/3 和非白名单拒绝。
- 四种输入层级、重复 X 不折叠、replicate/group 独立结果与无参数自动平均。
- direct weight/variance/SD/SE 转换、无效值和不猜列名。
- 轴尺度与模型变换分离、log 域、zero-dose control 和归一化派生数据。
- 4PL/5PL 公式版本、斜率方向、中点区别、标签确认、X 单位和 extrapolated 标记。
- deterministic initializer、bounded multistart、逐起点诊断、用户覆盖和批次算法一致性。
- parameter CI、mean confidence band、prediction interval 与 Bootstrap unit。
- observed range 默认、显式外推与持久化曲线表。
- 失败不画伪曲线、warning 不改模型，以及 R² 不作为通用成功标准。
- Matplotlib、Origin 与正式导出均只消费 FitResult，不重新拟合。
