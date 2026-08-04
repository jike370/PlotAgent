# PlotAgent 派生数据、单位与血缘契约

> 状态：第一轮数据变换基线已确认  
> 日期：2026-08-05  
> 适用范围：DatasetVersion、TransformSpec、TransformPipeline、UnitSpec、字段与行级血缘、变换预检和同构批次  
> 相关文档：[项目存储、项目包与数据导入](./PROJECT-STORAGE.md)、[领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)、[分析计算层与科学边界](./ANALYSIS-ENGINE.md)、[拟合系统契约](./FITTING-SYSTEM.md)、[后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)、[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)

## 1. 对象与提交边界

### 1.1 DatasetVersion

每个原始或派生 DatasetVersion 都是不可变对象，至少保存：

- `dataset_id`、`dataset_version`、`schema_version` 和对象状态。
- `parent_refs`：一个或多个精确父对象版本引用。
- 原始数据的 ImportRecipe 引用，或派生数据的 TransformSpec 引用。
- 字段 schema、每个字段的 UnitSpec 与稳定 `field_id`。
- 规范化表数据的内容哈希和对象存储引用。
- row lineage 对象引用与 field lineage 定义。
- 行数、列数、缺失、NaN、Inf、重复键等 quality summary。
- 创建任务、引擎版本、时间与来源对话等审计信息。

原始 DatasetVersion 没有 TransformSpec；其 parent_refs 指向导入源对象与 ImportRecipe。派生 DatasetVersion 不能修改父版本，所有变化形成新版本与新内容哈希。

### 1.2 TransformSpec 与 TransformPipeline

一次 `create_derived_dataset` Action 携带一个 TransformSpec。TransformSpec 包含最多 16 个按顺序执行的 TransformStep：

```text
TransformSpec
├─ spec_id / schema_version / implementation_version
├─ primary_parent_ref
├─ additional_parent_refs[]
├─ steps[1..16]
├─ expected_parent_versions
├─ output_schema_contract
└─ batch/reference/error policy
```

- Pipeline 是线性的：每一步消费上一步的临时表。
- Join 和 Concat 可以在某一步读取显式 additional parent，因此最终 DatasetVersion 可以有多个父级。
- 中间表只存在于任务暂存区，不发布为 DatasetVersion，也不进入项目资源库。
- 只有全部步骤、质量校验和 lineage 生成成功后，最终 DatasetVersion 才原子注册。
- 如果用户需要保留中间结果，必须拆成多个 `create_derived_dataset` Action。

16 步是单个 Action 内的领域上限，不改变 ActionPlan 最多 8 个 Action 的上限。

## 2. 类型安全的变换联合

每个 TransformStep 都是 Pydantic discriminated union 的一个明确变体：

- 使用 `kind` 选择步骤类型。
- 每种类型有固定字段、固定 AST 节点和严格参数；未知字段被拒绝。
- 字段只通过稳定 `field_id` 引用，不以显示名称作为执行标识。
- 数值、字符串、日期时间、单位和空值使用严格基础类型。
- Schema 自动生成 JSON Schema 与 TypeScript 类型，模型和 UI 使用同一契约。

第一轮 TransformSpec 禁止：

- SQL、Python、JavaScript、命令行或 UDF。
- 作为字符串提交的算术、过滤或公式表达式。
- `eval`、任意属性路径、任意函数名或运行时加载代码。
- TransformStep 在执行时动态创建未声明步骤。

算术与条件使用带 discriminator 的类型化 AST，例如字段引用、字面量、二元算术、比较和布尔组合；所有允许节点和运算符都在 Schema 中枚举。

## 3. 第一轮变换白名单

### 3.1 字段与 schema

- `select_fields`：选择明确字段集合。
- `rename_fields`：修改显示名称，保留 field_id。
- `reorder_fields`：调整列顺序，保留 field_id。
- `cast_field`：显式转换逻辑/物理类型并记录失败策略。
- `declare_unit`：确认或修改 UnitSpec，不改变数值。
- `convert_unit`：按 UnitSpec 转换数值并生成派生字段或替换派生表中的字段版本。

### 3.2 行选择与顺序

- `filter_rows`：使用类型化条件 AST。
- `sort_rows`：显式字段、方向和空值顺序。
- `take_range`：按明确字段与数值/日期时间边界选择范围。
- `deduplicate_rows`：显式键、保留规则和成员 lineage；不自动去重。

第一轮不提供 row-index cell editing。用户不能通过“把第 15 行第 3 列改成 0”修改原始或派生表；应使用可复现的字段/条件变换或重新导入。

### 3.3 类别

- `recode_categories_exact`：旧值到新值的精确映射，不做模糊匹配。
- `set_category_order`：显式类别顺序与未知类别策略。
- `merge_categories_exact`：显式列出每个合并集合和目标类别。

未列出的类别默认保持原值；是否允许未列出值必须在步骤中明确，不能按语言模型猜测拼写相近项。

### 3.4 数值与派生字段

- 类型化字段/常量 arithmetic：加、减、乘、除。
- `power`、`abs`、`sqrt`、`log`、`exp`。
- `round_explicit`：显式位数和舍入模式。
- `subtract_baseline`：显式 baseline 字段、常量或 reference rule。
- `divide_reference`：显式 reference 字段、常量或 reference rule。
- `to_percent`、`min_max_scale`、`zscore`。

这些步骤是确定性表变换，不执行统计检验、拟合、KDE 或平滑。涉及引用值时，规则、选中行、实际值和 lineage 都必须保存。

### 3.5 结构重塑与多父级

- `melt`：显式 id fields、value fields 与输出字段。
- `pivot`：显式 index、columns、values 和 duplicate-key policy。
- `transpose`：显式标识字段与生成字段命名规则。
- `concat_isomorphic`：只连接 schema、逻辑类型、UnitSpec 和语义完全同构的数据。
- `join_checked`：显式左右键、输出字段、连接类型和预期 cardinality。

Pivot 遇到 duplicate keys 时默认失败；用户必须选择一个注册表内的明确 aggregate 及其参数后才能继续，系统不默认取第一项、求和或平均。

Join 第一轮只允许声明并通过校验的 `one_to_one`、`one_to_many` 或 `many_to_one`。预检与完整执行的实际 cardinality 不符时失败；`many_to_many` 第一轮一律阻止。

### 3.6 日期时间

- `parse_datetime_explicit`：显式格式、locale、错误策略和时区解释。
- `set_or_convert_timezone`：区分附加时区语义与时区转换。
- `datetime_difference`：显式单位和方向。

系统不根据少量样本猜测并直接应用日期格式或时区；导入候选只能提出建议，歧义时返回 NeedsInput。

## 4. 异常与禁止的隐式处理

产生类型错误、除零、无效定义域、溢出或解析失败的步骤必须选择统一 `error_policy`：

- `fail`：任一异常使整个 TransformSpec 失败；第一轮默认。
- `set_missing`：把异常结果设为 missing，并记录逐类计数与 row lineage。
- `filter_rows`：排除异常行，并记录排除 mask 与原因。

策略在执行前显示并写入 TransformSpec。同一 Pipeline 可以让不同步骤显式选择策略，但不能在运行后根据结果自动切换。

第一轮不自动或隐式执行：

- clipping 或 winsorization。
- missing value imputation。
- 离群值检测后的自动删除。
- 非有限值替换为零。
- duplicate rows、unmatched join rows 或非法类别的静默丢弃。

如用户明确需要筛除某些行，使用可审计的 `filter_rows` 并创建新 DatasetVersion；不能修改父数据或 analysis mask。

## 5. TransformSpec 与 AnalysisSpec 分离

### 5.1 不同输出对象

- TransformSpec 表达确定性表变换，输出 DatasetVersion。
- AnalysisSpec 表达统计汇总、区间、拟合、KDE、平滑或检验，输出 AnalysisResult。
- renderer 不执行两者中的任何隐藏步骤。
- TransformSpec 不包含统计方法，AnalysisSpec 不伪装成普通表变换。

例如，单位转换、显式 zscore 字段和结构 pivot 是 TransformSpec；KDE 密度、LOWESS 平滑和 FitResult 曲线是 AnalysisResult output port。

### 5.2 显式 materialize

用户需要把 AnalysisResult 的表格端口作为普通数据继续变换时，必须执行独立 `materialize_analysis_output` Action：

- 引用精确 AnalysisResult 版本和命名 output port。
- 验证端口是可物化的二维数值/类别表，并固定 schema 与 UnitSpec。
- 复制持久化结果表，不重新运行 AnalysisSpec。
- 创建新的 DatasetVersion，parent_refs 包含 AnalysisResult 及其输入数据引用。
- 保存 materialization spec、结果端口哈希和完整对象/字段/行 lineage。

普通 `create_derived_dataset` 不能把分析方法藏进 TransformPipeline；`materialize_analysis_output` 也不能改变分析结果数值。

## 6. UnitSpec

每个字段的单位语义由版本化 UnitSpec 表达：

```text
UnitSpec
├─ source_text
├─ canonical_unit
├─ dimensionality
├─ kind: physical | dimensionless | opaque
└─ registry_version
```

- `source_text` 保存源表头、单位行或用户输入的原始文本。
- `canonical_unit` 是 pinned registry 解析后的规范表示；opaque 时为规范化的项目文本标识。
- `dimensionality` 保存维度签名；dimensionless 明确保存无量纲。
- `kind` 区分可换算物理单位、无量纲值与未知但需保留的 opaque 单位。
- `registry_version` 固定解释该单位的注册表版本。

从表头或单位行识别出的单位只作为建议。只有导入映射确认或显式 `declare_unit` 后才成为 DatasetVersion 的权威 UnitSpec。

## 7. 单位运算与转换

### 7.1 变换规则

- 加减要求维度兼容，并把输入换算到明确目标单位后计算。
- 乘除生成规范复合单位与 dimensionality。
- `log` 和 `exp` 的输入必须 dimensionless；单位值不能通过忽略单位继续计算。
- `power` 对单位和指数执行注册表允许的维度校验。
- 温度的 offset quantity 与 temperature delta 是不同语义；相加、相减和换算遵循各自规则，不能把 °C 绝对温度当作 Δ°C。
- opaque 单位只能与 canonical 文本完全相同的 opaque 单位视为兼容，不参与物理换算。

单位转换始终创建派生 DatasetVersion。为单张图统一显示单位的 plot-only 转换也创建 `scope: plot_local` 的派生版本：

- 资源库默认折叠显示 plot-local 版本，避免噪声。
- 图表详情、血缘和导出中仍可展开审计。
- PlotSpec 精确引用该版本，不能只在轴 formatter 中假装数值已经换算。

### 7.2 Registry 与权威来源

- Python Core 在进程内以单例加载 pinned Pint registry，运行期间不动态变更。
- 项目可以增加 alias，把项目文本映射到既有标准单位或项目 opaque 单位。
- 项目 alias 不能重定义、覆盖或改变标准单位的维度与换算。
- project.sqlite3 中的 UnitSpec 是权威真值。
- Parquet field metadata 镜像 UnitSpec，便于交换与检查，但冲突时以数据库中的版本化 UnitSpec 为准并报告一致性错误。

## 8. 三层 lineage

### 8.1 对象级

对象级 lineage 保存：

- DatasetVersion 的 parent_refs。
- ImportRecipe、TransformSpec 或 materialization spec 引用。
- 每个父对象、规格、输出表和 lineage 对象的内容哈希。
- 创建任务、操作记录和实现版本。

Join/Concat 保留所有父级；不会把多父级关系压成一段不可解析的文字描述。

### 8.2 字段级

- 每个字段有稳定 field_id；rename 和 reorder 保留 ID。
- 新派生字段获得新 ID，并保存引用父 field_id 的类型化 expression AST。
- cast、unit conversion、recode、melt、pivot、join 和 concat 保存字段来源、变换节点、UnitSpec 变化和输出字段映射。
- field lineage 使用结构化节点与哈希，不保存可执行字符串表达式。

### 8.3 行级

- 原始 row ID 由 `source_hash + sheet/table locator + source_row_index` 确定性生成。
- filter 和 sort 保留原 row ID；被过滤行在质量摘要和预检中计数。
- concat 的输出 row ID 组合父 DatasetVersion 与父 row ID。
- join 的输出 row ID 组合左右父 row ID；unmatched 一侧使用明确空成员标记。
- dedupe、aggregate 和 pivot 将多行压成一行时，引用内容寻址的压缩成员关系对象。
- materialized analysis table 保存 output port 行与分析输入行/mask 的可用关系；不伪造不存在的一对一血缘。

大规模成员集合不内联进 SQLite 行；使用 `objects/sha256` 中的压缩 lineage 对象并由数据库保存哈希与索引。

## 9. Apply 前预检

TransformSpec 正式执行前展示基于完整 schema 和受控样本/扫描得到的预检：

- 预计或精确 row/column delta。
- 新增、删除、重命名、重排或类型变化字段。
- UnitSpec 声明、转换与 dimensionality 变化。
- 新增 missing、NaN、Inf 和异常策略影响。
- Join 的 unmatched 左/右行、实际 cardinality 和行数 expansion。
- Pivot duplicate keys、Concat 同构检查和去重成员数量。
- 少量 before/after sample；样本只用于解释，不代替完整执行校验。

普通变换因为父版本不可变且结果是新 DatasetVersion，不需要破坏性确认。以下情况仍不执行：

- 字段、单位、日期格式、reference rule 或目标语义有歧义时返回 NeedsInput。
- 违反 join cardinality、单位维度、Pipeline 上限或禁止能力时由本地 validator 阻止并返回稳定错误。
- 预检 warning 的继续选择写入操作记录，但 warning 不等同于破坏性确认。

完整执行可能发现样本预检未覆盖的问题；此时按 error policy 原子失败或记录，不能使用样本结果强行提交。

## 10. 同构批次

批量派生数据要求所有项使用规范化后完全相同的 TransformSpec：

- 相同步骤顺序、kind、字段角色、UnitSpec 目标、类型化 AST 和 error policy。
- 不允许逐文件字段、单位、公式、join cardinality、日期格式或异常策略例外。
- 完全同构签名在变换前和最终输出后都校验。

Reference rule 可以对每份数据按相同语义取值，例如“每份数据中 category 精确等于 control 的 baseline”：

- 规则 AST、字段角色和选择条件在批次中完全相同。
- 各数据解析出的具体 reference value 可以不同，并逐项记录值、来源 row lineage 和哈希。
- 找不到唯一 reference 时该项失败，系统不改用第一行、均值或其他规则。

批次可以 partial success：成功项各自原子提交 DatasetVersion，失败项保存步骤、错误和预检摘要。部分失败不允许给失败文件换字段、单位、公式或 error policy；修改规格必须创建新批次。

## 11. 第一轮契约测试

- DatasetVersion 必需元数据、不可变性、多父级和哈希。
- 1–16 步线性 Pipeline、只发布最终结果和 ActionPlan 上限独立。
- 所有 TransformStep discriminator、未知字段和 SQL/Python/string expression/UDF 拒绝。
- 字段、行、类别、数值、结构、join/concat 和日期时间白名单。
- row-index cell edit、many-to-many join 和隐式 pivot aggregate 阻止。
- fail/set_missing/filter_rows 及无 clipping、winsorization、imputation、outlier deletion。
- TransformSpec/AnalysisSpec 分离与 materialize_analysis_output 不重算。
- UnitSpec 建议确认、维度运算、offset/delta、opaque、alias 与 registry 固定。
- DB UnitSpec 权威与 Parquet metadata 一致性检查。
- 对象、字段和行 lineage，包括 filter/sort、concat/join 与压缩成员关系。
- apply 前 delta、质量、join expansion 和 before/after sample。
- 完全相同批次 TransformSpec、reference rule 逐项求值和 partial success。
