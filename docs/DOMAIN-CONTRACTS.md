# PlotAgent 领域契约与 Schema 设计

> 状态：第一轮契约基线已确认  
> 日期：2026-08-05  
> 适用范围：DatasetVersion、TransformSpec、PlotSpec、PlotPatch、BatchSpec、FigureSpec、ActionPlan 及其跨进程 Schema  
> 相关文档：[派生数据、单位与血缘契约](./DATA-TRANSFORMS.md)、[分析计算层与科学边界](./ANALYSIS-ENGINE.md)、[拟合系统契约](./FITTING-SYSTEM.md)、[后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)、[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)

## 1. 契约原则

- Python/Pydantic 模型是领域 Schema 的唯一源头。
- 从 Pydantic 自动生成 JSON Schema Draft 2020-12。
- TypeScript 类型与验证器从发布的 JSON Schema 生成，不维护第二套手写结构。
- 所有跨进程对象携带明确 `schema_version`。
- 所有写操作携带项目、对象版本和幂等信息。
- 所有模型拒绝未知字段，不允许模型通过额外属性绕过白名单。
- 模型输出只表达领域意图，不包含 Python、SQL、LabTalk、JavaScript、命令行或任意文件路径。

Pydantic 官方支持从模型生成 JSON Schema Draft 2020-12，并建议对多模型联合使用带 discriminator 的联合：

- [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/)
- [Pydantic Discriminated Unions](https://docs.pydantic.dev/latest/concepts/unions/)
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)

## 2. 核心对象边界

```text
DatasetVersion
├─ 原始或派生数据的不可变版本
└─ 父级、TransformSpec、模式、UnitSpec、哈希、三层血缘和质量摘要

AnalysisSpec / AnalysisResult
├─ 用户明确指定的分析参数
└─ 拟合、误差、检验、平滑等可复现结果

PlotSpec
├─ 一张独立图的结构化定义
└─ 引用 DatasetVersion 与 AnalysisResult

BatchSpec
├─ 完全同构数据上的共享 PlotSpec 模板
└─ 共享样式、字段映射与各图覆盖

FigureSpec
├─ 多面板组合图
└─ 引用明确的 PlotSpec 版本

ExportSpec
└─ PNG、SVG 或 OPJU 的目标、尺寸、命名和验证要求
```

约束：

- PlotSpec 不保存原始表格数组，只引用数据版本。
- PlotSpec 不在渲染时临时计算统计量，只引用已持久化的分析结果。
- FigureSpec 与 BatchSpec 是独立对象，不通过给 PlotSpec 增加任意布局字段来模拟。
- ExportSpec 不改变 PlotSpec，只描述如何从特定版本生成正式产物。

## 3. 公共基础类型

所有领域对象复用以下严格基础类型：

```text
SchemaVersion        例如 1.0
ObjectId             带类型前缀的稳定 ID
VersionId            不可变对象版本
SemanticTargetId     例如 series:control、axis:y-left
DatasetVersionRef    数据集 ID + 版本 + 内容哈希
ObjectVersionRef     对象 ID + expected version
Quantity             数值 + 明确单位
FieldId              跨 rename/reorder 稳定的字段 ID
RowId                基于源位置或父行组合的稳定行 ID
UnitSpec             原文 + 规范单位 + 维度 + kind + registry version
ColorValue           标准颜色表达，不接受任意 CSS
ResourceRef          主进程授权的资源 ID，不是任意路径
```

建议 ID 前缀：

- `dataset:`、`analysis:`、`plot:`、`batch:`、`figure:`、`export:`
- `series:`、`axis:`、`legend:`、`annotation:`、`panel:`

### 3.1 DatasetVersion 与 TransformSpec

DatasetVersion 保存 parent refs、ImportRecipe 或 TransformSpec、schema/UnitSpec、数据哈希、row lineage ref、field lineage 和 quality summary。一次 `create_derived_dataset` 使用最多 16 步线性 TransformPipeline，只原子发布最终 DatasetVersion；Join/Concat 可声明多个父级。

TransformStep 使用 Pydantic discriminated union 和类型化 AST，禁止 SQL、Python、字符串表达式与 UDF。第一轮白名单、异常策略、UnitSpec 运算、三层 lineage 与预检以 [派生数据、单位与血缘契约](./DATA-TRANSFORMS.md) 为准。

## 4. PlotSpec

### 4.1 公共外壳

```json
{
  "schema_version": "1.0",
  "plot_id": "plot:temperature-a",
  "plot_version": 3,
  "chart_type_id": "K02",
  "family": {
    "kind": "xy",
    "geometry": ["line", "symbol"]
  },
  "datasets": [],
  "field_mapping": {},
  "analysis_refs": [],
  "scales": {},
  "axes": [],
  "series": [],
  "annotations": [],
  "style_sources": [],
  "resolved_style": {},
  "publication_profile": {},
  "provenance": {}
}
```

必需字段：

- `schema_version`：领域 Schema 版本。
- `plot_id`、`plot_version`：稳定对象与不可变版本。
- `chart_type_id`：图形库稳定 ID。
- `family`：带 `kind` discriminator 的图形家族配置。
- `datasets`：一个或多个精确数据版本引用。
- `field_mapping`：角色到字段 ID 的映射，不使用展示名称作为唯一标识。
- `analysis_refs`：已完成分析的版本引用。
- `style_sources`：项目、批次与图表样式来源。
- `resolved_style`：创建当前版本时解析出的完整样式快照。
- `publication_profile`：固定版本与物理尺寸。
- `provenance`：创建计划、用户指令、父版本和引擎版本引用。

### 4.2 图形家族联合

第一轮使用八个家族：

- `xy`：折线、散点、误差、面积、时间序列、连续谱、XRD、Nyquist。
- `categorical`：柱状、分组、堆积、百分比堆积。
- `distribution`：点图、箱线、小提琴、直方、KDE、ECDF。
- `matrix`：热图、相关矩阵、等高线、混淆矩阵。
- `survival`：KM 生存曲线与风险表。
- `dose_response`：剂量反应与 IC50/EC50。
- `forest`：效应量、区间、权重和无效线。
- `facet`：共享基础图形语法的分面图。

`chart_type_id` 在图形注册表中进一步声明：

- 所属家族与允许的 geometry。
- 必需和可选字段角色。
- 允许的分析、坐标、图层、标注和组合能力。
- PNG、SVG、OPJU 能力等级。
- 图形专用校验规则。

因此，同属 `xy` 的 K01 与 S31 可以复用基础 Schema，但 S31 额外允许谱轴方向、峰标签和参考卡配置。

### 4.3 数据与分析分离

- 字段角色引用稳定列 ID，并附带名称、数据类型和单位快照用于审计。
- TransformSpec 表达确定性表变换并生成新的 DatasetVersion，不把转换表达式藏在 renderer 中。
- 拟合、误差、平滑、检验、直方分箱和 KDE 等计算生成 AnalysisResult。
- AnalysisResult 表格端口只有通过独立 `materialize_analysis_output` Action 才成为 DatasetVersion；物化复制持久化结果，不重新计算分析。
- PlotSpec 只描述如何显示 AnalysisResult；重新计算会生成新分析版本和新 PlotSpec 版本。

### 4.4 样式快照

- `style_sources` 保存项目、批次、图表覆盖的来源版本。
- `resolved_style` 保存最终字体、线宽、颜色、标记、间距和画布参数。
- 全局样式或发表规格更新不会改变既有 PlotSpec。
- 用户迁移样式时生成新 PlotSpec 版本。

## 5. BatchSpec 与 FigureSpec

### 5.1 BatchSpec

```text
BatchSpec
├─ batch_id / batch_version
├─ dataset_signature
├─ dataset_version_refs[]
├─ shared_field_mapping
├─ plot_template
├─ shared_style
├─ axis_policy: per_plot | unified
├─ plot_overrides{}
└─ item_states{}
```

- `dataset_signature` 包含列、类型、单位和语义哈希。
- 只有签名完全一致的数据才能进入同一批次。
- 批次展开由 BatchService 完成，Agent 不逐文件复制计划。
- `plot_overrides` 按 plot ID 保存局部覆盖；批次强制统一必须由明确操作触发。

### 5.2 FigureSpec

```text
FigureSpec
├─ figure_id / figure_version
├─ layout: 1x2 | 2x1 | 2x2
├─ panels[]
│  ├─ panel_id
│  ├─ plot_version_ref
│  └─ panel_label
├─ common_legend
├─ physical_size
└─ publication_profile
```

- 面板引用明确 PlotSpec 版本。
- 源图更新只产生可替换提示，不自动修改 FigureSpec。
- 第一轮不包含图片面板、自由网格和嵌套面板。

## 6. PlotPatch

### 6.1 不使用通用 JSON Patch

模型不可见 RFC 6902 风格任意路径修改，也不提供 `set_property(path, value)`。

PlotPatch 使用带 `operation` discriminator 的领域联合：

```json
{
  "operation": "set_axis_range",
  "target_id": "axis:y-left",
  "expected_plot_version": 3,
  "payload": {
    "minimum": 0,
    "maximum": 100,
    "scale": "linear"
  }
}
```

第一轮操作：

- `set_axis_range`
- `set_axis_scale`
- `set_axis_label`
- `set_series_style`
- `set_category_color`
- `move_legend`
- `set_legend_visibility`
- `add_annotation`
- `update_annotation`
- `remove_annotation`
- `apply_publication_profile`
- `set_canvas_size`
- `set_batch_axis_policy`

### 6.2 PatchTransaction

```text
PatchTransaction
├─ transaction_id
├─ project_id
├─ expected_versions{}
├─ patches[1..N]
└─ scope
```

- 所有 Patch 先完成 Schema、目标、单位、科研规则和版本校验。
- 校验通过后原子应用并生成新版本。
- 任何 expected version 不匹配都返回版本冲突，不覆盖新修改。
- 批量事务保留成功项与失败项边界，并支持整条命令撤销。

## 7. ActionPlan

### 7.1 结果联合

模型只能返回以下五类结果之一：

- `ExecutablePlan`：计划完整且允许本地校验。
- `NeedsInput`：缺少必要参数或目标存在歧义。
- `BlockedPlan`：数学、结构、安全或产品硬规则禁止执行。
- `UnsupportedRequest`：第一轮没有对应能力。
- `NoChange`：请求已经满足或不会产生状态变化。

每种结果都使用 `result_type` discriminator，不依赖自然语言判断结果类型。

### 7.2 ExecutablePlan

```json
{
  "schema_version": "1.0",
  "result_type": "executable",
  "plan_id": "plan:001",
  "project_id": "project:001",
  "expected_versions": {},
  "actions": [],
  "warnings": [],
  "confirmation": "not_required"
}
```

约束：

- 一个计划最多 8 个 Action。
- Action 可以通过 `depends_on` 引用同一计划的先前输出。
- 依赖必须构成有向无环图，不允许循环、条件脚本或运行时生成新 Action。
- 批次内部 fan-out 不计入 8 个 Action，由 BatchService 根据 BatchSpec 完成。

### 7.3 Action 联合

- `create_derived_dataset`
- `materialize_analysis_output`
- `run_analysis`
- `create_plot`
- `patch_plot`
- `create_batch`
- `patch_batch`
- `create_figure`
- `patch_figure`
- `export_artifact`

不向 Agent 提供以下 Action：

- 任意删除或永久清空回收站。
- 任意文件读写、移动或覆盖。
- 任意 SQL、Python、命令行、LabTalk 或脚本执行。
- 修改邀请码、凭据、隐私设置或全局安全策略。

## 8. 模型与执行器边界

- Context Builder 在模型调用前解析 `@` 引用、当前目标、字段结构、单位、数据摘要、图形能力和项目规则。
- 模型不直接获得 DatasetService、PlotService、文件系统或 Origin 工具。
- 模型只提交一个结构化计划候选。
- Local Planner Validator 再次执行 Schema、策略、科研、对象版本和权限校验。
- 校验通过后，Local Executor 才把 Action 映射到领域服务。
- 信息不足时返回 NeedsInput，不让模型自行遍历项目、猜测字段或尝试执行。

供应商工具调用能力可以用于约束 `ActionPlan` 输出，但不等于把本地执行工具直接交给模型。

## 9. 确认与风险

确认和科研校验是两个独立维度：

```text
confirmation: not_required | required
validation: info | warning | blocked
```

规则：

- 明确、可逆的样式修改直接执行并创建版本。
- 用户已经明确给出全部参数的数据变换可以生成派生 DatasetVersion，分析可以生成 AnalysisResult；两者执行前都展示参数与警告。
- 字段映射遵循一次映射规则；精确、无歧义指令可以跳过确认。
- 参数缺失、目标歧义、统计方法未指定时返回 NeedsInput。
- 数学不可执行、数据结构不满足或违反产品硬规则时返回 BlockedPlan。
- 永久删除、覆盖外部文件等破坏性操作不进入普通 ActionPlan，必须通过专门 UI 确认。

## 10. Schema 发布与兼容

- 每个发布版本输出 `schemas/` 包，包含 PlotSpec、PatchTransaction、ActionPlan、RPC 和事件 Schema。
- Schema 使用固定 `$id` 和 Draft 2020-12 `$schema`。
- TypeScript 类型由发布 Schema 生成，并在 CI 中检查工作区无未生成差异。
- 读取旧 Schema 时先执行显式迁移，再进入当前 Pydantic 模型。
- 迁移不得静默改变图形类型、数据版本、统计方法、单位或视觉结果。
- 未知新版本返回“需要升级应用”，不能以忽略字段的方式继续写入。

## 11. 第一轮契约测试

- 所有 discriminator 联合的合法与非法变体。
- `extra` 字段拒绝、严格数值和单位校验。
- PlotSpec 到 JSON 再读取的一致性。
- Pydantic Schema 与生成 TypeScript 类型的一致性。
- PatchTransaction 原子性与版本冲突。
- ActionPlan 最大 8 步、无环依赖和禁止 Action。
- TransformPipeline 最大 16 步、只发布最终 DatasetVersion，ActionPlan 的 `materialize_analysis_output` 不重算分析。
- UnitSpec、对象/字段/行 lineage 与 TransformStep discriminated union。
- BatchSpec 完全同构签名。
- FigureSpec 固定版本引用。
- 旧 Schema 迁移与未知新版本拒绝。
