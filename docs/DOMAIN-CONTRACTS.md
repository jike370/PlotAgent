# PlotAgent 领域契约与 Schema 设计

> 状态：现有45图契约属于重构前基线；正式目标已缩减为 T1/T2 共38图，七个 T3/T4 图将在 R0 从 availability、Schema、Agent 与导出能力删除；38图裸模板测试结论冻结后再重写渲染契约
> 日期：2026-08-07
> 适用范围：SourceDataset、FieldMapping/PreparationSpec、PlotCalculationSpec/Result、StructureUnit/ChartRecipe、PlotSpec、PlotPatch/ChartEditCapabilityProfile、BatchSpec、FigureSpec、ActionPlan 及跨进程 Schema
> 相关文档：[Agent 上下文、模型供应商与数据出境契约](./AGENT-CONTEXT-AND-PROVIDERS.md)、[邀请、共享额度与最小 Beta 云控制面契约](./CLOUD-CONTROL-PLANE.md)、[本地安全、诊断与 Beta Schema 兼容契约](./LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md)、[受控数据准备、单位与来源追溯契约](./DATA-TRANSFORMS.md)、[固定绘图计算与科学边界](./ANALYSIS-ENGINE.md)、[拟合能力分期边界](./FITTING-SYSTEM.md)、[渲染管线与跨 Renderer 一致性契约](./RENDERING-PIPELINE.md)、[原生 Origin OPJU 导出契约](./ORIGIN-EXPORT.md)、[后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)、[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)

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
SourceDataset
├─ 确定性导入的不可变版本
└─ ImportRecipe、schema/UnitSpec、source coordinates、hash 与质量摘要

FieldMapping / PreparationSpec / PreparedDataset
├─ 当前图字段角色与本地编译的封闭准备规格
└─ 为绘图复现持久化的 Plot Data，不是通用派生数据

PlotCalculationSpec / PlotCalculationResult
├─ 九类图形不可分割固定计算
└─ 固定算法、参数、完整数据输入、mask、输出表与 hashes

StructureUnitDefinition / ChartRecipe
├─ 可复用视觉构件、语义端口与封闭结构关系
└─ 版本化图义骨架，不绑定源列、当前数据或 renderer 代码

PlotSpec
├─ 一张独立图的结构化定义
└─ 引用 ChartRecipe 版本、PreparedDataset、用户预计算字段与 PlotCalculationResult

ResolvedRenderPlan
├─ 已解析坐标、刻度、物理布局、样式、文本与数据完整性
└─ Matplotlib 与 Origin adapter 的共同只读输入

BatchSpec
├─ 完全同构数据上的共享 PlotSpec 模板
└─ 共享样式、字段映射与各图覆盖

FigureSpec
├─ 多面板组合图
└─ 引用明确的 PlotSpec 版本

ExportSpec
└─ PNG、SVG 或 OPJU 的目标、命名、ResolvedRenderPlan hash 和验证要求

OriginExportPlan
├─ target-scoped 数据布局、原生对象和 typed property map
└─ OriginAdapter、template、capability 与两阶段验证计划
```

约束：

- PlotSpec 不保存原始表格数组，只引用数据版本。
- ChartRecipe 不保存 SourceDataset、FieldId、数据值、自动坐标范围或 PlotCalculationResult；它只保存结构、语义槽位、关系、坐标策略、默认样式与显式模板常量。
- PlotSpec 不在渲染时临时分箱、KDE、汇总、拟合或分析，只引用持久化 Plot Data/PlotCalculationResult。
- Matplotlib 与 Origin 不直接解释 PlotSpec 的未解析默认值，只消费同一 ResolvedRenderPlan。
- FigureSpec 与 BatchSpec 是独立对象，不通过给 PlotSpec 增加任意布局字段来模拟。
- ExportSpec 不改变 PlotSpec，只描述如何从特定版本和固定 RenderPlan 生成正式产物。

## 3. 公共基础类型

所有领域对象复用以下严格基础类型：

```text
SchemaVersion        例如 1.0
ObjectId             带类型前缀的稳定 ID
VersionId            不可变对象版本
SemanticTargetId     例如 series:control、axis:y-left
SourceDatasetRef     原始数据集 ID + 版本 + 内容哈希
PreparedDatasetRef   绘图数据 ID + 版本 + 内容哈希
ObjectVersionRef     对象 ID + expected version
Quantity             数值 + 明确单位
PhysicalLength       数值 + mm 或 pt 等受限物理单位
RenderPlanHash       规范化 ResolvedRenderPlan 的 SHA-256
OriginCapability     O1 | O2 | O3 | O0
FieldId              跨 rename/reorder 稳定的字段 ID
RowId                基于源位置或父行组合的稳定行 ID
UnitSpec             原文 + 规范单位 + 维度 + kind + registry version
ColorValue           标准颜色表达，不接受任意 CSS
PaletteRef           冻结 palette ID + version/hash + resolved 8-bit sRGB colors/stops
MarkerSymbol         12 种稳定语义枚举，不保存 Origin 数字编号
MarkerInterior       solid | open | hollow
ResourceRef          主进程授权的资源 ID，不是任意路径
```

建议 ID 前缀：

- `source:`、`prepared:`、`plotcalc:`、`plot:`、`batch:`、`figure:`、`export:`
- `series:`、`axis:`、`legend:`、`annotation:`、`panel:`

### 3.1 SourceDataset、Preparation 与 PlotCalculation

`SourceDataset` 保存 ImportRecipe、schema/UnitSpec、数据哈希、稳定 field/row id、sheet/block/line/cell 来源坐标与 quality summary。原始文件和 SourceDataset 不可变。

`FieldMapping` 是当前图形角色到稳定 FieldId 的唯一语义映射。`PreparationSpec` 是本地 compiler 生成的封闭联合，只允许字段选择、结构投影、完全同构纵向 concat、metadata label、plot order 与 plot mask；不得由模型输出，不支持通用 TransformPipeline。`PreparedDataset` 保存输入、mapping/spec/compiler version、provenance、纳入/排除计数与 input/output hash，且不能继续任意加工。

`PlotCalculationSpec/Result` 是九类封闭联合：HistogramBinning、TukeyBox、ViolinKDE、DensityKDE、ECDF、SummaryError、PercentStack、MatrixProjection、ConfusionCount。它不允许任意表达式、自由串联或发布为通用数据集；完整算法与缺失规则以[固定绘图计算与科学边界](./ANALYSIS-ENGINE.md)为准。

### 3.2 StructureUnitDefinition 与 ChartRecipe

`StructureUnitDefinition` 是系统版本化的结构单元登记项。它只描述图中可复用的视觉构件或关系能力，不承担源文件解析、表型转换、固定计算或后端代码：

```text
StructureUnitDefinition
├─ unit_id / version / display metadata
├─ semantic_ports[]          # x、y、category、value、error、color、size…
├─ accepted_data_kinds[]     # prepared | precomputed | plot_calculation
├─ parameters[]              # 强类型、有限范围、无任意属性路径
├─ relation_capabilities[]   # 可参与哪些封闭关系
└─ renderer_capabilities     # Matplotlib / Origin typed support
```

`ChartRecipe` 是可复用、不可变版本的完整组件图：

```text
ChartRecipe
├─ recipe_id / recipe_version / schema_version
├─ origin: official | user
├─ parent_recipe_ref?
├─ components[1..N]: ComponentInstance
├─ relations[]: overlay | group | stack | attach | connect
├─ semantic_slots[]
├─ coordinate_policy / default_style_ref
├─ explicit_template_constants[]
└─ structure_fingerprint / provenance
```

约束：

- `ComponentInstance` 引用一个已登记 unit/version，并为其端口分配稳定 component-local slot；不允许嵌入 Python、LabTalk、任意 JSON path 或 renderer 参数字符串。
- `Relation` 是带 discriminator 的封闭联合，目标使用稳定 component ID。误差/区间/标签必须显式 `attach` 到目标构件；堆积、分组和轴归属不得从字段名或 series 顺序推断。
- 两个单元分别可用不代表其任意多单元组合合法；Local Recipe Validator 必须校验完整有向组件图、端口基数、关系冲突、单位/坐标、固定计算来源和 renderer capability。
- 已迁移官方图形与未来用户图形使用同一 ChartRecipe Schema。官方身份只表示完成更严格的证据门禁；未迁移 29 图在过渡期继续使用既有运行时，不伪装为 recipe。
- ChartRecipe 只保存语义槽位。当前数据经一次 FieldMapping 绑定到槽位，本地 compiler 再生成具体 PlotSpec；已有有效绑定可增量复用，新增或冲突槽位才需要用户确认。
- 固定计算只能作为登记的输入来源供构件消费，不能在组件图中自由串联，也不能成为通用派生数据工作流。
- M6 只实现 Schema、validator、compiler 与首批 14 个官方配方迁移。v1 关系只覆盖 overlay/group/stack/attach/connect，baseline 通过强类型 attach 表达；offset/facet/axis assignment、FigureRecipe、用户搭建器、用户配方包和自然语言结构 Action 后移。

## 4. PlotSpec

### 4.1 公共外壳

```json
{
  "schema_version": "1.0",
  "plot_id": "plot:temperature-a",
  "plot_version": 3,
  "chart_type_id": "K02",
  "chart_recipe_ref": {
    "recipe_id": "official:K02",
    "recipe_version": 1,
    "structure_fingerprint": "sha256:<canonical-recipe-hash>"
  },
  "family": {
    "kind": "xy",
    "geometry": ["line", "symbol"]
  },
  "prepared_data_refs": [],
  "precomputed_data_refs": [],
  "plot_calculation_refs": [],
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
- `chart_recipe_ref`：生成当前实例的精确图形配方版本与结构指纹；过渡期内官方 registry ID 与 recipe ref 同时存在并由本地 validator 校验一致。
- `family`：带 `kind` discriminator 的图形家族配置。
- `prepared_data_refs`：一个或多个精确 PreparedDataset 版本引用。
- `precomputed_data_refs`：用户提供的 curve/band/matrix/step 等预计算字段引用。
- `plot_calculation_refs`：已完成固定绘图计算的精确结果引用。
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
- 允许的固定计算、所需预计算字段、坐标、图层、标注和组合能力。
- PNG、SVG、OPJU 能力等级。
- 图形专用校验规则。
- `availability: official | internal_hidden`；只有 `official` 可进入 create/edit/export capability。
- 版本化 `ChartEditCapabilityProfileRef`，它是 UI、Agent Context、PlotPatch validator 和 export capability 的单一能力来源。

因此，同属 `xy` 的 K01 与 S31 可以复用基础 Schema，但 S31 额外允许谱轴方向、峰标签和参考卡配置。

M6 补充迁移后，首批 K01/K02/K03/K05/K08/K09/K10/K18/S05/S25/X01/X02/X03/X09 的注册表条目指向精确 `ChartRecipeRef`，并保留产品名称、字段/预计算门槛、证据状态和导出等级。ChartRecipe compiler 负责从组件图生成 PlotSpec；这 14 图不得新增按 chart ID 的第二套布局真值。其余 29 个正式图保留既有注册表和 Resolver 路径，后续迁移须单独通过同样门禁。

### 4.3 数据准备、固定计算与渲染分离

- FieldMapping 引用稳定 FieldId，并附带名称、类型、单位和来源快照用于审计。
- PreparationSpec 只执行受限图形准备，不把任意转换藏在 renderer 中。
- 直方分箱、Tukey box、KDE、ECDF、固定 summary/error、百分比堆积、矩阵投影和混淆计数生成 PlotCalculationResult。
- 回归、相关、KM、剂量反应等 v1 只引用用户提供的预计算字段；不生成 AnalysisResult/FitResult。
- PlotSpec 只描述如何显示这些持久化数值；参数变化创建新 PlotCalculationResult 与 PlotSpec/FigureVersion。

### 4.4 样式快照

- `style_sources` 保存项目、批次、图表覆盖的来源版本。
- `resolved_style` 保存最终字体、线宽、颜色、标记、间距和画布参数。
- 全局样式或发表规格更新不会改变既有 PlotSpec。
- 用户迁移样式时生成新 PlotSpec 版本。

#### 4.4.1 Origin 对齐的符号与色板

```text
MarkerStyle
├─ symbol: square | circle | triangle_up | triangle_down | diamond | plus | cross
│          | triangle_left | triangle_right | hexagon | star | pentagon
├─ interior: solid | open | hollow
├─ size_pt / stroke_width_pt
├─ stroke_color: ColorValue
└─ fill_color: ColorValue?

PaletteRef
├─ palette_id / palette_version
├─ origin_source_name
├─ origin_asset_kind: color_list | palette
├─ kind: qualitative | sequential | diverging | special | grayscale
├─ colors[] | stops[]        # 8-bit sRGB 是运行时真值
├─ reversed
└─ source_version / source_hash
```

符号语义固定如下，adapter 本地维护 Origin 原生值和 Matplotlib marker 的类型化映射，不把 Origin 数字编号写进 PlotSpec：

| enum | Origin 显示名 | Matplotlib |
| --- | --- | --- |
| `square` | Square | `s` |
| `circle` | Circle | `o` |
| `triangle_up` | Up Triangle | `^` |
| `triangle_down` | Down Triangle | `v` |
| `diamond` | Diamond | `D` |
| `plus` | Plus Sign | `+` |
| `cross` | Cross | `x` |
| `triangle_left` | Left Triangle | `<` |
| `triangle_right` | Right Triangle | `>` |
| `hexagon` | Hexagon | `h` |
| `star` | Star | `*` |
| `pentagon` | Pentagon | `p` |

对闭合符号，`solid` 使用显式 fill；`open` 使用已经解析的画布/axes 背景色 fill，从而遮住下层线；`hollow` 使用透明 fill，下层线可以穿过。`plus/cross` 无内部，只接受规范化 `solid`；`open/hollow` 必须在 capability 校验阶段返回不支持。该差异必须进入 RenderPlan，不能由 adapter 猜测。

内置 palette ID 固定为：`ColorBlindSafe8`、`ColorBlindSafe15`、`BlueOrange`、`OrangeNavy`、`RedPurple`、`Viridis`、`Plasma`、`Inferno`、`Magma`、`GreyBlue`、`YellowBlue`、`YellowGreen`、`YellowPurple`、`GrayScale`、`Fire`、`Rainbow_Modified`。`GrayScale` 的 source hash 锚定 Origin 2024 SR1 `Palettes/GrayScale.PAL`。`PaletteRef` 是产品统一名称，但 `origin_asset_kind` 必须保留来源是 Origin Color List 还是 Palette；每条记录携带冻结 RGB/stops 与 hash。Matplotlib 和产品目录只依赖冻结值；原生 Origin 导出仅可使用已限定 Origin 版本安装目录中的对应资产，并须先精确核验 source hash。缺失或不一致时稳定失败，不接受用户文件或同名替代品。`ColorValue` 额外允许严格 `#RRGGBB` 单色，不接受颜色表达式。

当前源资产选择固定如下；同名 `.oth/.PAL` 同时存在时不允许运行时任选：

| palette_id | Origin source asset | kind |
| --- | --- | --- |
| `ColorBlindSafe8` | `Themes/Color/ColorBlindSafe8.oth` | qualitative |
| `ColorBlindSafe15` | `Themes/Color/ColorBlindSafe15.oth` | qualitative |
| `BlueOrange` | `Palettes/BlueOrange.PAL` | diverging |
| `OrangeNavy` | `Palettes/OrangeNavy.PAL` | diverging |
| `RedPurple` | `Palettes/RedPurple.PAL` | diverging |
| `Viridis` | `Palettes/Viridis.PAL` | sequential |
| `Plasma` | `Palettes/Plasma.PAL` | sequential |
| `Inferno` | `Palettes/Inferno.PAL` | sequential |
| `Magma` | `Palettes/Magma.PAL` | sequential |
| `GreyBlue` | `Palettes/GreyBlue.PAL` | sequential |
| `YellowBlue` | `Palettes/YellowBlue.PAL` | sequential |
| `YellowGreen` | `Palettes/YellowGreen.PAL` | sequential |
| `YellowPurple` | `Palettes/YellowPurple.PAL` | diverging |
| `GrayScale` | `Palettes/GrayScale.PAL` | grayscale |
| `Fire` | `Palettes/Fire.pal` | sequential |
| `Rainbow_Modified` | `Palettes/Rainbow_Modified.PAL` | special |

类别超过 15 时 resolver 不循环颜色；它按冻结联合编码策略分配上述 symbol，仍不足时产生版本化 warning 或稳定阻止。X23/X24/X35/X36 的双 Y axis style 默认是中性 8-bit sRGB、正常字重和非加粗细线，显式 patch 才可分别修改轴颜色。

#### 4.4.2 逐图编辑能力

```text
ChartEditCapabilityProfile
├─ profile_id / version / hash
├─ chart_type_id
├─ availability: product | internal_hidden | removed
├─ capabilities[]
│  ├─ operation discriminator
│  ├─ allowed_target_kinds[]
│  ├─ allowed_payload_fields[]
│  ├─ constraints
│  └─ renderer_support: matplotlib + origin
└─ evidence_refs[]
```

正式 profile 只属于 38 图：K01–K04、K06–K16、K18–K22、K24–K25、S01、S21、S34、S61、X02、X03、X05、X09、X13、X23、X24、X35、X36、X38、X39、X40。`K05`、`K17`、`S05`、`S07`、`S25`、`S31`、`X01` 固定为 `removed`：只保留旧项目 ID 识别并返回 `CHART_TYPE_REMOVED`，不能创建、编辑、渲染、导出或作为批量/组合候选。X07、X11、X12、X15、X16、X17、X18、X19、X37 固定为 `internal_hidden`，不能出现在图形库、ContextEnvelope create capability 或正式 export target 中。完整新引擎边界以 [绘图引擎重构与验收基线](./PLOTTING-ENGINE-REFACTOR-ACCEPTANCE.md) 为权威。

能力联合覆盖 `general`、`line`、`marker`、`bar_fill`、`error_interval`、`palette_color_scale`、`dual_y`、`facet`、`y_offset`、`chart_parameters` 十组语义；每个 capability 仍解析为下面列出的领域 Patch，而不是任意 property path。直方分箱、KDE 带宽、ECDF/CCDF 等改变数值结果的参数不属于 Style/PlotPatch，必须生成新的封闭 PlotCalculationSpec/Result。

下列 `PlotSpec.specialist` 是重构前兼容结构；生产 38 图迁移后由平坦 ChartProfile 只声明双后端交集能力。旧字段可为历史项目解码，但不得使 removed 图重新获得生产能力：

```text
SpecialistEditSpec
├─ bar_area: fill_color / edge_color / edge_width / width_ratio / alpha
├─ uncertainty: color / line_width / cap_size / band_alpha
├─ colorbar: visible / title / minimum+maximum / levels
├─ dual_y: left_color / right_color / axis_width
├─ facet: order / labels / gap / shared_x / shared_y / common_legend
├─ y_offset: distance / order
└─ chart_parameters
   └─ pareto_reference_percent           # X24，0 < percent < 100
```

对应 Patch/Agent intent discriminator 固定为 `set_bar_area_style`、`set_uncertainty_style`、`set_colorbar_style`、`set_dual_y_style`、`set_facet_style`、`set_y_offset_style`、`set_chart_parameters`。UI 只在当前图声明相应 capability 时显示控件；Agent、本地 validator、Resolver、Matplotlib 与 Origin adapter 消费同一状态。X02 是连续型 Drop Line，X 轴保持在坐标框底部，垂线始终终止于解析后的底部轴，不再具有可编辑 baseline。

### 4.5 ResolvedRenderPlan（旧引擎兼容）

旧引擎的 Render Resolver 把 PlotSpec/FigureSpec 解析为共享 ResolvedRenderPlan。该结构在迁移期只为尚未替换的历史路径与旧项目读取保留；新生产链不再要求 Matplotlib 与 Origin 共享最终几何或像素布局。

新引擎以语义 PlotSpec 与 ChartProfile 为共同真值：每图 Matplotlib renderer 与 Origin 官方模板绑定器可各自使用目标原生布局，但不得重算科研数据、改变系列身份或丢弃用户状态。迁移完成后删除只服务旧共享几何路径的代码与测试。

### 4.6 OriginExportPlan

OPJU ExportSpec、ResolvedRenderPlan 与版本化 OriginAdapter 在本地解析为 typed OriginExportPlan。它固定 target scope、Data/Analysis/Graphs/Metadata 布局、ASCII internal names、Long Names、数据对象、原生 graph/layer/plot、typed properties、template/capability 和 live/reopen validation。

Origin Worker 不接受任意 property/path/script 字符串。正式 38 图只在对应官方模板绑定器达到 O1 时开放 OPJU；九个 `internal_hidden` 与七个 `removed` 图均不承诺生产导出；整份 OPJU 原子成功或失败。完整迁移契约见 [38图 Origin 官方模板映射](./ORIGIN-OFFICIAL-TEMPLATE-MAPPING.md)。

内部注册表/Schema 保留 54 个稳定 chart ID 以识别历史项目；生产 capability 明确分为 38 个 `product`、九个 `internal_hidden` 与七个 `removed`。只有 38 个 product ID 可进入 create/edit/render/export。X02/X03 语义已按 Origin 官方模板纠正，X39/X40 分别固定为 Line Series 与 Before-After；X03 的两系列形态只作为“哑铃图”搜索别名，不另占 ID。

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
- 一个批次只有一个用户明确指定的 `chart_type_id`；第一阶段批量资格 allowlist 为首迁 14 图。
- 批次展开由 BatchService 完成，Agent 不逐文件复制计划。
- `plot_overrides` 按 plot ID 保存局部覆盖；批次强制统一必须由明确操作触发。
- `shared_field_mapping` 每批只确认一次，只有字段签名精确兼容时复用；不兼容项进入 `NeedsInput`，不执行模糊映射。

### 5.2 第一阶段批量交互对象

```text
SelectionScope = current_plot | selected_plots[] | batch

AgentChangeSet
├─ source_versions
├─ target_scope
├─ accepted_patches[]
├─ unsupported_or_skipped_targets[]
├─ failed_targets[]
├─ resulting_versions[]
└─ reversible_transaction_ref

BatchReviewItem
├─ plot_version_ref / preview_ref
├─ execution_state / validation_warnings
├─ selection_state
└─ retry_eligibility
```

- `AgentChangeSet` 是本地校验和执行后的权威结果，不是模型说明文字；每个 ChangeSet 只要求一次整体撤销，不新增 ChangeSet 专属历史/分支或任意重放脚本，既有 PlotSpec 版本 DAG 保持不变。
- 批量统一修改只分发目标共同声明的 `ChartEditCapabilityProfile` 字段，不适用目标必须进入 skipped/unsupported，不能静默忽略。
- 第一阶段不定义 `figure` selection scope、持久化 `StylePreset` 或 `DataReplacementPlan`；可把当前图现有强类型样式直接复制到选中图或批次。

### 5.3 FigureSpec

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

- `set_plot_title`
- `set_axis_range`
- `set_axis_scale`
- `set_axis_label`
- `set_axis_ticks`
- `set_series_style`
- `set_category_color`
- `set_error_style`
- `set_palette`
- `set_color_scale`
- `set_dual_axis_style`
- `set_facet_style`
- `set_y_offset`
- `move_legend`
- `set_legend_visibility`
- `add_annotation`
- `update_annotation`
- `remove_annotation`
- `apply_publication_profile`
- `set_canvas_size`
- `set_batch_axis_policy`

`set_series_style` 的 payload 是强类型 line/marker/fill 子对象；marker 只能使用 §4.4.1 的枚举，palette 只能引用冻结 `PaletteRef` 或显式 RGB。每个 Patch 先查询目标图的 `ChartEditCapabilityProfile`，operation、target kind 或 payload field 未被声明时，Agent 返回 `Unsupported(reason=chart_edit_capability_not_supported)`；本地 validator 返回 `PATCH_CAPABILITY_NOT_SUPPORTED`，不得丢弃未知字段、近似为其他操作或调用 Origin fallback。双 Y 轴默认中性细线由 resolved style 提供，不是 adapter 隐式默认。

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

模型只能返回以下四类 `AgentDecision` 之一：

- `ActionPlan`：完整的白名单计划候选，仍须本地校验。
- `NeedsInput`：缺少必要参数或目标存在歧义。
- `Unsupported`：第一轮或当前 provider 没有合法能力路径。
- `NoChange`：请求已经满足或不会产生状态变化。

每种结果都使用 `decision_type` discriminator，不依赖自然语言、Markdown 或 tool transcript 判断结果类型。数学、结构、安全、版本或产品硬规则由本地 validator 拒绝并产生稳定错误，不由模型返回“已阻止”结果。

### 7.2 ActionPlan

```json
{
  "schema_version": "1.0",
  "decision_type": "action_plan",
  "plan_id": "plan:001",
  "target_alias": "active_target",
  "actions": [],
  "warnings": [],
  "confirmation": "not_required"
}
```

约束：

- 一个计划最多 8 个 Action。
- Provider 返回的 ActionPlan 只含业务意图和 ContextEnvelope 中的语义 target alias，不含 project path、内部 table ID、PreparationStep、PlotCalculation kind 选择或 resolved object IDs。Local Planner Compiler 解析 active target 并附加 expected versions，产出只在本地存在的 resolved execution plan。
- Action 可以通过 `depends_on` 引用同一计划的先前输出。
- 依赖必须构成有向无环图，不允许循环、条件脚本或运行时生成新 Action。
- 批次内部 fan-out 不计入 8 个 Action，由 BatchService 根据 BatchSpec 完成。

### 7.3 Action 联合

- `create_plot`
- `patch_plot`
- `create_batch`
- `patch_batch`
- `create_figure`
- `patch_figure`
- `export_artifact`

文件选择/导入、结构确认、FieldMapping UI、PreparationSpec 编译和 PlotCalculation 执行是本地工作流阶段，不是模型 Action。`create_plot/create_batch` 只表达已经选定的 chart type、字段语义和用户参数；本地 compiler 根据图形注册表决定是否生成封闭 PlotCalculationSpec。

M6 不扩展上述 Action 联合。M6 后的自然语言搭建器只能增加带 discriminator 的 `add_component`、`remove_component`、`set_relation`、`set_axis_assignment`、`bind_recipe_slot` 和 `save_custom_chart_type` 等领域 Action；模型仍不得输出自由图层 JSON、任意属性路径或 renderer 代码。

不向 Agent 提供以下 Action：

- 任意删除或永久清空回收站。
- 任意文件读写、移动或覆盖。
- 任意 SQL、Python、命令行、LabTalk 或脚本执行。
- 修改邀请码、凭据、隐私设置或全局安全策略。

## 8. 模型与执行器边界

- Context Builder 在模型调用前解析 `@` 引用、当前目标、字段结构、单位、数据摘要、图形能力、预计算要求和项目规则。
- 模型不直接获得 ImportService、PreparationService、PlotCalculationService、PlotService、文件系统或 Origin 工具。
- 每次 InteractionRun 只有一个编排 Agent 和一个结构化 AgentDecision 候选；无多 Agent、工具循环或 partial plan 执行。
- 模型只表达业务意图，不输出 pandas/Python/Matplotlib/Origin/文件/SQL/table id 或数据处理步骤。
- Local Planner Validator 再次执行 Schema、策略、科研、对象版本和权限校验。
- 校验通过后，Local Executor 才把 Action 映射到领域服务。
- 信息不足时返回 NeedsInput，不让模型自行遍历项目、猜测字段或尝试执行。

供应商的 JSON Schema、response format 或 function-calling 只能约束单个 `AgentDecision` 的传输格式；第一轮不提供工具循环，也不把任何本地工具交给模型。结构错误最多一次格式修复；同类错误再次出现立即停止。ContextEnvelope、AgentDecision、provider 能力级别和数据出境以 [Agent 上下文、模型供应商与数据出境契约](./AGENT-CONTEXT-AND-PROVIDERS.md) 为准。

## 9. 确认与风险

确认和科研校验是两个独立维度：

```text
confirmation: not_required | required
validation: info | warning | blocked
```

规则：

- 明确、可逆的样式修改直接执行并创建版本。
- 用户确认导入结构与图形字段角色后，本地 compiler 才能生成封闭 PreparationSpec；不存在通用数据变换确认。
- 字段映射遵循选图后一次语义映射规则；精确、无歧义指令可以跳过映射 UI，但仍生成审计对象。
- 必需角色、误差语义或预计算字段缺失时返回 NeedsInput；v1 不询问或执行统计/拟合方法。
- 数学不可执行、数据结构不满足或违反产品硬规则时由本地 validator 阻止并返回稳定错误，不要求模型自我判断。
- 永久删除、覆盖外部文件等破坏性操作不进入普通 ActionPlan，必须通过专门 UI 确认。

## 10. 云控制面协议对象

- `InviteGrant` 拥有 status、expiry、quota policy、granted/consumed 与 allowed profiles；设备只通过随机 ID 和长期 DeviceCredential 引用 grant。
- `QuotaSnapshot` 固定为 granted、consumed、remaining、可选 period/reset 与 server time，不含 reserved。
- `ModelRunRecord` 以 `(invite_id, client_run_id)` 唯一，状态仅覆盖 accepted、invoking、completed、failed、cancelled；同一 ID 的重试返回同一记录，不能再次调用或扣费。
- Beta 在一个服务端事务中插入幂等记录并原子扣减 InviteGrant 共享计数；不定义 reserve/settle/reconcile/release-unused 状态。
- 第一轮无 `CloudConfig`、`UpdateManifest`、refresh rotation、analytics 或诊断上传 Schema。Redeem、credential-authenticated invoke、quota status 使用严格 Request/ResponseEnvelope 与稳定错误。
- 完整字段、简单状态与测试矩阵见 [邀请、共享额度与最小 Beta 云控制面契约](./CLOUD-CONTROL-PLANE.md)。

## 11. 本地安全与生命周期对象

- `NetworkMode` 是 `builtin_proxy | custom_provider | local_only` 的严格持久联合；它是本机服务模式而非项目字段或启动工作入口。第一轮没有 `OneTimeUpdateGrant` 或 `update_only`。
- `LocalDiagnosticBundleManifest` 逐文件保存 logical name、purpose、size/hash 与禁止字段扫描结果；Bundle 只保存到本地，未知/禁止字段阻止生成。
- `KnownVersionMigrationRecord` 只描述一个明确 source→target 版本对、专用实现版本、source snapshot、validation/semantic hash 与状态；它不是通用 MigrationPlan。
- 第一轮不定义 `BackupRecord`、`RecoveryRecord`、`BackupState`、`RecoveryState` 或 analytics event；`TempCleanupState` 保持封闭且不能发布临时对象。
- 完整字段、稳定错误和安全测试见 [本地安全、诊断与 Beta Schema 兼容契约](./LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md)。

## 12. Schema 发布与兼容

- 每个发布版本输出 `schemas/` 包，包含 StructureUnitDefinition、ChartRecipe/ChartRecipeRef、PlotSpec、PatchTransaction、ActionPlan、RPC 和事件 Schema。
- Schema 使用固定 `$id` 和 Draft 2020-12 `$schema`。
- TypeScript 类型由发布 Schema 生成，并在 CI 中检查工作区无未生成差异。
- 不兼容 Schema 默认返回 `SCHEMA_VERSION_UNSUPPORTED`，不能以忽略字段方式继续写入；v1 Schema 不含可执行 AnalysisSpec/FitSpec。
- 只有当前 build 明确实现的 source→target 版本对可在一致快照和新 temp workspace 中执行一次性迁移；迁移不得静默改变图形类型、SourceDataset/PreparedDataset、FieldMapping/PreparationSpec、PlotCalculation、预计算字段、单位或视觉结果。
- 未知新版本和没有专用迁移的旧版本都保持原项目不变，并提示使用兼容 build。

## 13. 第一轮契约测试

- 所有 discriminator 联合的合法与非法变体。
- `extra` 字段拒绝、严格数值和单位校验。
- PlotSpec 到 JSON 再读取的一致性。
- Pydantic Schema 与生成 TypeScript 类型的一致性。
- PatchTransaction 原子性与版本冲突。
- ActionPlan 最大 8 步、无环依赖和禁止 Action。
- Excel/TXT/CSV ImportRecipe、结构候选、一次 FieldMapping、PreparationSpec 封闭联合与来源坐标。
- PlotCalculationSpec 九类联合、固定算法 golden、禁止自由串联与 input/output hash。
- StructureUnitDefinition/ComponentInstance/Relation/ChartRecipe/ChartRecipeRef v1 的合法与非法组件图、稳定指纹、版本引用、未知单元和完整图冲突拒绝；v1 只接受 overlay/group/stack/attach/connect。
- ChartRecipe 只含语义槽位与显式模板常量，不含 SourceDataset/FieldId/数据值/自动范围/PlotCalculationResult/路径/代码；官方与用户 recipe 使用同一 Schema。
- 首迁 14 图的 ChartRecipe→FieldMapping→PlotSpec 编译确定性，同一输入/版本产生相同规范化 PlotSpec；其余 29 图既有回归无退化。
- ResolvedRenderPlan 规范化 hash、正式 ExportSpec 绑定与 Matplotlib/Origin adapter 禁止重新解析。
- 冻结数据生成器的基础结构不变量：并列不重叠、正负堆积分离、误差显式附着、范围覆盖、series/颜色/图例身份和 finite geometry。
- 坐标、ticks、SafeRichText、物理尺寸、quality tier 与跨 renderer 容差。
- OriginExportPlan、O1 准入、最小自包含数据、两阶段读回、整文件原子性和稳定错误。
- BatchSpec 的 FieldMapping/PreparationSpec/PlotCalculationSpec 完全同构签名。
- SelectionScope 只接受 current/selected/batch；AgentChangeSet 的成功/跳过/失败、版本、整体撤销与 BatchReviewItem 局部重试状态可回放验证。
- FigureSpec 固定版本引用。
- 已知 source→target 一次性迁移原子性/语义不变与其他 Schema 稳定拒绝。
- InviteGrant/DeviceCredential、QuotaSnapshot、ModelRun原子共享计数/client_run幂等与稳定错误。
- NetworkMode/strict local_only、LocalDiagnosticBundle、KnownVersionMigrationRecord、temp cleanup 与禁止字段。
