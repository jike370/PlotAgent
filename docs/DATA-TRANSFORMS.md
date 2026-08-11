# PlotAgent 受控数据准备、单位与来源追溯契约

> 状态：v1 implementation-ready design baseline
> 适用范围：SourceDataset、FieldMapping、PreparationSpec、PreparedDataset、单位元数据、来源坐标与同构批量
> 相关文档：[项目存储、项目包与数据导入](./PROJECT-STORAGE.md)、[固定绘图计算与科学边界](./ANALYSIS-ENGINE.md)、[领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)、[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)

## 1. v1 产品边界

v1 不是通用数据处理 Agent，也不提供可编程 TransformPipeline 或可自由继续加工的派生数据平台。权威数据链只有：

```text
SourceDataset
  → FieldMapping + PreparationSpec
  → PreparedDataset
  → optional PlotCalculationResult
  → EngineDataView / PlotDocument
```

- `SourceDataset` 是一次确定性导入得到的不可变数值数据版本，保留源文件 SHA-256、解析配方、schema、单位建议、质量摘要和来源坐标。
- `FieldMapping` 只回答“导入字段在当前图形中扮演什么角色”。
- `PreparationSpec` 是本地程序由已经确认的导入结构、字段映射和图形注册表编译出的受限规格，不是模型可编排的步骤列表。
- `PreparedDataset` 是为了绘图复现而持久化的 Plot Data；可以被 PlotDocument、任务和导出引用，但不是资源库中可任意继续加工的新数据产品。
- 图形不可分割的固定计算由 `PlotCalculationSpec/Result` 表达，详见[固定绘图计算与科学边界](./ANALYSIS-ENGINE.md)。

v1 明确不提供通用 filter、dedupe、join、pivot、单位换算、算术派生、log/zscore、baseline、normalize、category recode、单元格编辑、SQL、Python、字符串表达式、UDF 或任意步骤串联。超出封闭 PreparationSpec 能力时返回稳定 `PREPARE_UNSUPPORTED`，不猜测替代做法。

## 2. SourceDataset 与不可变来源

每个 SourceDataset 至少保存：

- `source_object_hash`、`import_recipe_version`、`parser_version` 和 `unicode_normalization_version`。
- 逻辑 schema、物理类型、精度、单位原文与单位建议。
- Excel 的 workbook/sheet/cell-range/source-row；TXT/CSV 的 byte range/line range/block/channel/sweep/source-row。
- 缺失、NaN、正负 Inf、无法解析字段、有效行列数和质量警告的结构化计数。
- 原始行的稳定 `source_row_id`，由 source hash、sheet/block 和源行坐标组成。

原始文件与 SourceDataset 永远只读。重新导入、解析设置变化或源内容变化均创建新版本；已有图继续绑定旧版本。`0` 和 `False` 始终是有效值，不能用 truthiness 当缺失判断。

## 3. 两阶段确认，不是重复映射

### 3.1 阶段一：数据位置与结构

导入器回答“数据在哪里”。它确定 workbook sheet、TXT/CSV data region、header、delimiter、encoding、preamble/postamble 与 block/channel/sweep 边界。只有编码、分隔符、表头或区域存在多个同等合理解释时，才提出一个最小问题；问题解决后继续同一 ImportRecipe。

### 3.2 阶段二：当前图形字段语义

字段映射回答“字段在当前图中是什么”。在用户已经明确选择图形后，系统依据图形注册表展示 X、Y、group、error、lower、upper、matrix 等所需角色，预填高置信候选并让用户一次确认。

这两个阶段分别确认物理结构和图形语义，不是两轮字段映射。模型只能表达业务语义，不得输出 table id、sheet 内部对象、处理步骤或执行工具。

## 4. PreparationSpec 封闭联合

PreparationSpec 使用严格 Pydantic discriminated union，只允许以下由本地 compiler 生成的 kind：

- `select_fields`：选择当前图需要的字段并保留稳定 field id。
- `project_structure`：把已经确认的二维区域投影为当前图形所需的长/宽结构；不聚合、不推断。
- `isomorphic_concat`：仅在用户明确要求且 schema、逻辑类型、单位和语义完全一致时纵向拼接，并写入 `source_sheet` 或 `source_block`。
- `project_metadata_label`：仅把用户明确选择用于标签/分组的 InstrumentMetadata 字段投影为常量来源列。
- `apply_plot_order`：保存用户明确的类别/系列显示顺序，不改值、不删除行。
- `mask_for_plot`：只按 PlotCalculationSpec 的 `fail` 或 `exclude_with_report` 缺失策略产生绘图 mask；不修改 SourceDataset。

一个 PreparedDataset 的 PreparationSpec 是规范化后的单个封闭对象，不允许自由串联、运行时增加 kind、任意表达式或模型生成步骤。批次 fan-out 由本地 BatchService 将同一规格应用于完全同构输入。

## 5. Excel 多工作表规则

- `.xlsx`、`.xls`、`.xlsm` 只读取数据；宏、VBA、公式和外链绝不执行或刷新。
- 多个工作表默认形成独立 SourceDataset，并作为候选批次分别绘图。
- 只有用户明确要求，且字段集合、逻辑类型、单位与语义一致时，才允许 `isomorphic_concat`；结果必须保留 `source_sheet`。
- 永不自动跨 sheet join，也不把不同 sheet 的同名字段视为可合并依据。
- 公式只在文件内存在缓存值时作为数据导入，并记录 `cached_formula_value` provenance；没有缓存值时为 missing 或 NeedsInput。

## 6. TXT/CSV 仪器数据规则

TXT 导入先分离 `InstrumentMetadata`、一个或多个 `DataBlock` 与 `postamble`。普通 CSV 复用同一确定性文本路径，只是常见候选通常为单一 DataBlock。

- 带仪器前导/尾部信息时，元数据与数值区域分别保存，元数据默认不进入数据列。
- 存在多个 block、sweep 或 channel 时展示候选，默认作为独立 SourceDataset/批次项，不擅自拼接、透视或平均。
- 只有用户明确将某个元数据字段用于标签或分组时，才通过 `project_metadata_label` 投影常量来源列。
- 编码、分隔符、decimal mark、header、data region 有多个合理解释时只问一个最小问题；超出已列举解析模式时返回可操作拒绝。
- CSV/TXT 文本只作为 data，不解释为公式、命令、HTML、脚本或 Origin expression。

## 7. 单位与字段语义

- 单位行或表头中的单位只形成建议；确认后的 `UnitSpec` 保存 `source_text`、`canonical_unit`（如已确认）、`dimensionality`、`kind` 与 registry version。
- v1 不执行单位换算。需要换算时用户应在外部生成明确数值并重新导入；系统不得在 PlotDocument、renderer 或 Origin 中隐式换算。
- 不兼容单位不能共享坐标轴或进入同构批次。opaque 单位只与完全同名 opaque 单位兼容。
- 列名只做首尾空格清理和固定 Unicode 规范化；规范化后重复列名阻断，不做模糊改名。
- 整数与浮点可统一为逻辑 `numeric`，但物理类型、范围和精度必须保留。

## 8. 缺失、异常与完整数据

- PreparationSpec 不删除、填补、去重、过滤异常、裁剪或 winsorize 数据。
- NaN、Inf 与 missing 原样保留并在质量摘要中计数；绘图/固定计算只能选择 `fail` 或 `exclude_with_report`。
- `exclude_with_report` 只生成可审计 mask，保存纳入/排除行数和原因；SourceDataset 不变。
- log axis v1 仅 Log10，遇到任何参与绘图的非正值即阻断，不能通过 mask 静默跳过。
- 正式输出与固定计算在声明支持规模内使用完整数据；preview 的确定性视觉简化不改变范围、统计或计算输入。

## 9. 同构批量

批量要求规范化后的字段集合、逻辑类型、单位、语义、FieldMapping 和 PreparationSpec 完全一致；列顺序可以不同。Excel sheet 或 TXT block 只有通过这套签名才可组成同构批次。

- 不允许逐文件字段、单位、准备方式或缺失策略例外。
- 任何异构项拆为其他候选批次；v1 不通过通用变换“标准化后再批量”。
- 同一 PreparationSpec 可以部分成功；成功项保留，失败项记录稳定 `PREPARE_*` 错误。

## 10. 持久化与追溯

PreparedDataset 至少保存：

- SourceDataset 精确版本、FieldMapping、PreparationSpec 和 compiler version。
- 输入/输出 schema、单位、row/field provenance 与内容 SHA-256。
- 纳入/排除计数、来源 sheet/block/channel 分布和结构化 warning。
- 与 PlotCalculationResult、PlotDocument、任务和组合图组件版本的引用关系。

PreparedDataset 可进入完整/结果 `.plotproj` 与 OPJU 的 Plot Data，但 UI 不把它宣传为可任意加工的派生数据集。来源关系应显示“从何处导入、如何映射、为哪张图准备”。

## 11. 稳定错误与契约测试

错误族固定为 `IMPORT_*`、`MAPPING_*` 与 `PREPARE_*`，至少覆盖：

- 区域/编码/分隔符/表头歧义、重复规范化列名、无缓存公式值。
- 自动 join 请求、非同构 concat、单位不兼容、未支持准备操作。
- 必需角色缺失、字段候选同等、非有限值策略未确认、Log10 非正值。

测试必须覆盖 Excel 多 sheet、TXT preamble/block/postamble、CSV 复用路径、一个最小追问、可操作拒绝、`0/False`、NaN/Inf/missing、来源坐标、同构签名、PreparedDataset hash 与分层回放。测试 oracle 来自冻结 fixture/manifest，不在运行时生成。
