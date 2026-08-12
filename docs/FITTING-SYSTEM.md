# PlotAgent 拟合能力分期边界

> 状态：v1 implementation-ready design baseline；拟合引擎为后续阶段
> 适用范围：v1 预计算拟合输入、禁止边界、未来 FitSpec/Result 启用条件与导出语义
> 相关文档：[固定绘图计算与科学边界](./ANALYSIS-ENGINE.md)、[受控数据准备、单位与来源追溯](./DATA-TRANSFORMS.md)、[领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)、[原生 Origin OPJU 导出契约](./ORIGIN-EXPORT.md)、[产品决策基线](./PRODUCT-DECISIONS.md)

## 1. v1 不实现拟合引擎

v1 不定义、执行或验收 FitSpec/FitResult。以下能力全部后移：

- linear OLS/WLS、Huber、polynomial、exponential、power law、4PL、5PL。
- 自动或手动初值、边界、multistart、求解诊断、权重转换。
- parameter CI、confidence band、prediction interval、Bootstrap。
- residual、R²、外推判断、IC50/EC50/ED50 估计。
- 回归/相关/显著性、KM 估计、平滑、基线、归一化或等效电路拟合。

不得把这些运算藏在 PreparationSpec、PlotDocument、renderer、Matplotlib、Origin worksheet formula、Origin Analysis Template 或 LabTalk 中。模型不能输出拟合代码、公式、参数求解步骤或工具调用。

## 2. v1 预计算输入

用户可以导入外部软件已经计算好的数值结果，并明确选择相应的正式图形：

- K21：提供已经计算的相关矩阵。
- K22：提供规则网格与Z值，不执行插值或gridding。
- S34：提供Z′/Z″与可选曲线，不执行等效电路拟合。

字段映射只确认这些列的图形角色。系统进行类型、单位、形状、单调性（适用时）、上下界次序和有限性等结构校验，但不重新计算科学结果，也不替用户判断模型是否适当。

图形库详情页必须显示“需要预计算字段”和具体字段清单。缺少结果时图形仍可见，执行被 `PLOTSPEC_PRECOMPUTED_INPUT_REQUIRED` 阻断并提供可操作说明。

## 3. PlotDocument 与渲染

- PlotDocument 精确引用 PreparedDataset 或用户提供的预计算数值表。
- 预计算 curve/band/step/matrix 是普通已确认 Plot Data，不标记为 PlotAgent FitResult/AnalysisResult。
- Profile renderer 只消费明确字段绑定与完整数值引用；renderer 不拟合、不插值、不估计区间。
- 数据更新不会自动刷新外部分析结果；用户重新导入并重绘会创建新的 FigureVersion。
- 正式 PNG、SVG、OPJU 使用同一组持久化预计算数值。

## 4. Origin 边界

OPJU 中预计算曲线作为 Plot Data 工作表列进入原生、可编辑 Graph：

- 编辑 Plot Data 可以按 Origin 原生数据链接更新图形。
- 编辑 Raw Data 不承诺重新拟合或重新生成 Plot Data。
- v1 不创建 Origin Analysis Template、Fit Function、worksheet formula 或重算链。
- 不依赖 LabTalk，也不嵌入 PNG/SVG 冒充 O1。

导出说明和 Manifest 必须标记数据来源为 `user_provided_precomputed`，并说明 PlotAgent 未执行拟合/分析。

## 5. 后续阶段的启用门槛

未来若启用 FitSpec/FitResult，必须另行完成并冻结：

- 模型白名单与版本化公式、输入层级、权重语义、初始化/边界和失败规则。
- 区间种类、随机种子、完整数值诊断、持久化曲线和科学 reference fixtures。
- PlotDocument/EngineDataView/Origin 如何引用单一持久化结果的契约。
- 新 Decision ID、Action 联合、稳定错误、迁移/兼容、权限与 release gate。

这些长期方向不是当前 v1 承诺，也不进入 W0–W10 当前完成定义。实现者不得因为本文件保留未来边界而预置可被 v1 UI 或 Agent 触达的隐藏拟合入口。

## 6. v1 契约测试

- 全局 Schema 与 Action 联合不存在可执行 FitSpec/FitResult/AnalysisSpec/AnalysisResult。
- K21/K22/S34 的预计算字段有效、缺失和结构错误 fixtures。
- 同一预计算表在 preview、formal PNG/SVG 和 O1 OPJU 中保持数值与版本一致。
- Origin Manifest 正确区分 direct、fixed PlotCalculationResult 与 user-provided precomputed。
- 禁止 renderer fitting、Origin Analysis Template、worksheet formula、LabTalk 和模型拟合步骤。
