# PlotAgent 成本感知 Workflow 编排架构

> 状态：正式架构与实现合同。
> 当前实现：WorkflowRun、WorkflowContext、TaskDraft、TaskPlan 与 WorkflowRecipe 已成为唯一编排路径；旧编排已删除且不兼容读取。
> 适用范围：数据检查、任务拆解、自然语言参数翻译、分级 Agent 调用、WorkflowRecipe、确认、执行与失败恢复。
> 不改变：34 张正式单图范围、Matplotlib/Origin 双后端、Origin 原生可编辑产物、用户确认、项目版本和类型化引擎动作。

相关文档：

- [Agent Native 绘图引擎](./AGENT-NATIVE-PLOTTING-ENGINE.md)
- [Pi 通用 Agent 运行时](./PI-AGENT-RUNTIME.md)
- [受控数据准备](./DATA-TRANSFORMS.md)
- [任务运行时](./TASK-RUNTIME.md)
- [对话交互](./CONVERSATIONAL-INTERACTION.md)
- [产品决策](./PRODUCT-DECISIONS.md)

## 1. 决策摘要

PlotAgent 不把每个请求都直接交给大模型，也不把 Agent 缩减为自动填写字段映射表单。正式路由顺序为：

```text
确定性程序快速路径
  → WorkflowRecipe 匹配与重放
  → 单轮受限 Agent
  → 多轮数据探索 Agent
  → 用户追问
```

Agent 在产品中的职责固定为：

1. **任务编排**：理解目标、解析数据指代、拆分单图或批量任务、处理依赖与失败恢复。
2. **数据检查与处理规划**：按需读取原始数据，通过封闭数据工具提出可审计的数据准备步骤。
3. **参数翻译**：把自然语言转换为强类型的数据处理、字段绑定和绘图参数。

Agent 不直接绘制图形，不执行任意 Python、SQL、LabTalk、Origin C 或 Matplotlib 代码，不直接修改项目数据库，也不能绕过用户确认和 Core 校验。

## 2. 正式编排

```mermaid
flowchart TD
    A["用户上传数据并描述目标"] --> B["保留原始数据并建立本地索引"]
    B --> C["L0 确定性处理"]
    C -->|"规则成功"| H["TaskDraft"]
    C -->|"WorkflowRecipe 命中"| D["重放并校验"]
    D -->|"通过"| H
    D -->|"不匹配"| E["L1 单轮受限 Agent"]
    C -->|"规则不足"| E
    E -->|"计划完整"| H
    E -->|"仍有歧义"| F["L2 多轮探索 Agent"]
    F --> G["只读数据工具"]
    G --> F
    F -->|"计划完整"| H
    F -->|"预算耗尽或需要业务判断"| Q["向用户追问"]
    Q --> F
    H --> I["任务确认表"]
    I -->|"修改"| H
    I -->|"确认"| J["TaskCompiler"]
    J --> K["Core 校验与 TaskPlan"]
    K --> L["确定性执行"]
    L -->|"单项失败"| M["只修复失败任务"]
    M --> J
    L -->|"成功"| N["预览与导出"]
    N --> O["可选固化 WorkflowRecipe"]
```

该编排扩大受控读取和规划能力，同时继续收紧修改能力。

## 3. 设计原则

### 3.1 程序优先，Agent 逐级升级

- 能由确定性解析器完成的任务不得调用模型。
- WorkflowRecipe 重放必须早于模型调用。
- 单轮 Agent 只处理有限候选和轻度歧义。
- 多轮 Agent 只处理确实需要查看更多数据的任务。
- 每一级失败只是路由信号，不直接成为用户可见产品错误。

### 3.2 读取、规划和修改权限分离

| 权限 | 边界 |
|---|---|
| 数据读取 | 范围较大，但只读、分页、限额、记录审计 |
| 任务规划 | 范围较大，但只产生候选 TaskDraft，没有项目副作用 |
| 数据处理 | 只能提交封闭 DataOperation，由本地引擎创建新版本 |
| 绘图修改 | 只能提交图类 capability 中登记的强类型动作 |
| 项目提交 | 只由 Core 在用户确认和版本校验后执行 |

### 3.3 用户明确的要求是硬约束

以下内容不得被 Agent 静默替换：

- 用户指定的数据源、Sheet 或数据块。
- 用户指定的图类。
- 用户指定的字段角色。
- 用户指定的绘图参数、阈值、样式和导出格式。
- 用户明确要求保留、排除或排序的数据。

如果硬约束与能力或数据冲突，返回最小追问或明确不支持，不能自动换图或改变科学语义。

### 3.4 原始数据不可变

- 原始文件、SourceDataset 和来源坐标始终只读。
- 数据处理产生新的 `PreparedDataView` 或等价版本化对象。
- 每个处理结果保存输入版本、操作序列、参数、行列影响和内容哈希。
- Agent 不获得任意单元格写入能力。

### 3.5 Renderer 保持确定性

Agent 不接触 renderer 实现。TaskCompiler 输出当前绘图引擎已有的类型化动作，由各图独立 Matplotlib renderer 和 Origin 官方模板绑定器执行。

### 3.6 硬切换，不保留兼容架构

新编排采用单一工作流入口，不设置并行兼容层。完成切换时必须满足：

- 桌面、Core、Pi 和测试只存在一个 Workflow 入口；
- 桌面端只暴露 WorkflowRun、TaskDraft、TaskPlan 与只读检查工具；
- Provider 只通过 WorkflowRun 的 L1 上下文或 L2 只读工具工作；
- TaskDraft 是确认前唯一计划真值，TaskCompiler 是进入 TaskPlan 的唯一入口；
- 不双写旧计划表和新 Workflow 表，不读取旧计划作为 fallback；
- 不保留旧 Schema 的自动迁移、字段别名、旧状态映射或“若新路径失败则走旧路径”；
- 现有 renderer 公共 Engine Action 是稳定的执行边界，不属于要保留的旧 Agent 编排；
- 旧项目中只属于旧 Agent 编排的未执行计划不迁移，明确失效；已经提交的图、数据和导出不受影响。

最终门禁必须用源码搜索和负向测试证明旧模块、RPC、Schema、数据库表和兼容分支已经消失，不能只证明新路径可用。

## 4. 正式模块

```mermaid
flowchart LR
    UI["Conversation UI"] --> WR["WorkflowRouter"]
    WR --> DR["DeterministicResolver"]
    WR --> RS["WorkflowRecipeStore"]
    WR --> PI["Pi Agent Runtime"]
    PI --> DI["DataInspectionService"]
    DR --> TD["TaskDraft"]
    RS --> TD
    PI --> TD
    TD --> TC["TaskCompiler"]
    TC --> CV["Core Validator"]
    CV --> TP["TaskPlan Runtime"]
    TP --> DE["Data Engine"]
    TP --> PE["Plot Engine"]
    PE --> MPL["Matplotlib"]
    PE --> ORG["Origin"]
    TP --> ST["Project Storage / Audit"]
```

### 4.1 WorkflowRouter

负责一次用户目标的分级路由：

- 判断能否走 L0 确定性路径。
- 查询可用 WorkflowRecipe。
- 分配 L1/L2 Agent 预算。
- 记录选择了哪条路径、耗时、模型调用数和成本。
- 不负责字段语义或 renderer 细节。

### 4.2 DeterministicResolver

第一阶段至少处理：

- 数据 A/B/C、第一张表、第二个 Sheet、明确文件名/Sheet 名等指代。
- 正式图类 ID、中英文名称和已登记别名。
- 明确数值参数、颜色、线型、范围、阈值和导出格式。
- 高置信字段名/类型/单位匹配。
- 数据源数量、字段逻辑类型和图类 required roles。
- 单一明确目标对象，例如当前图唯一的 `series_2`。

解析结果必须带来源位置和置信等级，不能只返回字符串。

### 4.3 DataInspectionService

向 Agent 暴露只读工具，不暴露文件系统、数据库连接或任意代码执行：

- `list_data_sources`
- `inspect_data_source`
- `preview_rows`
- `read_range`
- `sample_rows`
- `profile_field`
- `search_values`
- `compare_schemas`
- `inspect_instrument_metadata`
- `validate_task_draft`

所有工具必须：

- 使用稳定 source/field alias。
- 限制行数、列数、字符串长度和总 scalar 数。
- 记录读取范围、用途、调用者和披露摘要。
- 小数据允许分页读完；大数据优先统计、采样和局部范围。
- 不把文件路径、凭据、宏、公式或可执行内容当指令解释。

### 4.4 TaskDraft

`TaskDraft` 是 Agent 与用户确认之间的高层结构，不直接等于绘图引擎动作。

建议最小结构：

```yaml
task_draft_id: task-draft:...
goal_text: 数据 A 画折线图，数据 B 画柱状图
items:
  - item_id: item:1
    source_refs: [source:A]
    chart_profile_id: K01
    data_operations: []
    bindings:
      x: field:time
      y: field:signal
    chart_parameters: {}
    exports: [png]
    confidence: high
    open_questions: []
  - item_id: item:2
    source_refs: [source:B]
    chart_profile_id: K08
    data_operations: []
    bindings:
      category: field:group
      value: field:mean
    chart_parameters:
      y_axis.minimum: 0
    exports: [png, opju]
    confidence: high
    open_questions: []
```

TaskDraft 必须保存每个任务的数据源、图类、字段绑定、数据操作、绘图参数和输出，不允许把批量任务的同名角色扁平合并。

### 4.5 TaskCompiler

TaskCompiler 是 Agent 与绘图引擎之间的确定性边界：

1. 将 DataOperation 编译为数据引擎规格。
2. 将绑定与参数编译为公开绘图引擎动作。
3. 固定 source/field/plot/object 版本。
4. 检查图类、角色、单位和 capability。
5. 生成 TaskPlan、TaskItem、依赖和幂等键。
6. 禁止任何未登记动作或后端专属脚本穿透。

### 4.6 WorkflowRecipeStore

WorkflowRecipe 是用户明确固化的任务处理流程，不等于 Origin renderer 使用的 OriginRecipe。

| 名称 | 用途 |
|---|---|
| WorkflowRecipe | 复用数据识别、处理、字段绑定、图类、参数和导出流程 |
| OriginRecipe | 某张正式图在 Origin 中的官方模板/菜单/X-Function 创建与读回合同 |

两者不能共用表、版本号或身份体系。

## 5. 分级路由

### 5.1 L0：确定性快速路径

典型命中条件：

- 用户已选数据和图类，required roles 存在唯一高置信匹配。
- 用户明确说出字段和参数。
- 当前目标对象唯一且参数解析无歧义。
- WorkflowRecipe 精确命中并通过完整校验。
- 已确认批次中的同构新数据只需重放。

L0 允许直接产生 TaskDraft，但仍然需要用户确认；不得因“不调用模型”而跳过确认。

### 5.2 L1：单轮受限 Agent

适用于：

- 候选字段或对象有限，但规则无法唯一选择。
- 用户用了登记外的自然语言别名，但语义明确。
- 批量任务的数据—图类关系需要一次语义拆解。
- 参数描述需要转换为有限枚举。

L1 获得静态 WorkflowContext、候选集和一个提交工具。它不能读取额外数据；若仍不确定，应请求升级 L2 或返回 NeedsInput，不得猜测。

### 5.3 L2：多轮探索 Agent

适用于：

- 表头、数据区域或仪器块边界仍有合理歧义。
- 必须查看更多原始值才能判断字段语义。
- 多个数据源需要比较结构或值域。
- 需要设计封闭的数据处理步骤。
- 某个 TaskItem 执行失败，需要针对性诊断和修复。

L2 可以多轮调用 DataInspectionService 和 `validate_task_draft`，但不能调用 Data Engine 或 Plot Engine 执行正式修改。

### 5.4 预算

预算必须由 WorkflowRouter 明确传入，不由模型自行决定：

- 最大模型轮次。
- 最大工具调用次数。
- 最大披露行、列和 scalar 数。
- 最大输入/输出 token。
- 最大墙钟时间。
- 最大估算费用。

达到预算后优先向用户提出一个合并后的最小问题，不进行无限自动修复。

## 6. 自然语言绘图参数

用户明确给出的绘图参数先走本地解析：

```text
“第二条线改成红色虚线，宽度 2”
  → target = series_2
  → color = red
  → line_style = dashed
  → line_width = 2
```

满足以下条件时不调用模型：

- 目标对象唯一。
- 参数名和值能映射到公开 capability。
- Matplotlib 与 Origin 都能表达并读回。
- 不涉及科学语义推断。

若“第二条线”对应多个候选、参数超出能力或后端不一致，再升级 Agent 或追问。

用户参数在 TaskDraft 中标记为 `hard_constraint`。Agent 不能在修复过程中删除、放宽或替换硬约束。

## 7. 数据处理权限

### 7.1 允许的方向

数据处理能力必须以版本化、强类型 `DataOperation` 逐项准入。目标最小集合：

- 选择文件、Sheet、数据块和二维区域。
- 指定表头、单位行、分隔符、编码、decimal mark 和日期解析策略。
- 选择字段、设置显示名和确认逻辑类型。
- 按明确条件筛选或排序，并保存影响行数。
- 宽表/长表的受控 reshape。
- 完全同构数据源 concat，并保留来源身份。
- 图类已有的冻结计算和掩码策略。

是否加入 join、任意公式派生、单位换算、归一化或复杂统计，必须分别定义 Schema、科学边界、双后端影响和验收；本文不自动授权。

### 7.2 禁止

- 任意 Python、SQL、JavaScript、LabTalk、Origin C、Shell 或 UDF。
- 直接修改 SourceDataset 或原始文件。
- 模型输出自由字符串表达式后由本地执行。
- 静默删除异常、填补缺失、排序、聚合或改变单位。
- 因 renderer 需要而在 renderer 内偷偷补列或改变数据。

## 8. 数据指代与批量任务

### 8.1 稳定身份

UI 为提供给 Agent 的每个数据源显示稳定引用：

```text
数据 A · experiment.xlsx > Run1
数据 B · experiment.xlsx > Run2
数据 C · instrument.txt > block_1
```

DeterministicResolver 先把“数据 A”“Run2”“第二个数据块”等解析为 source alias。Agent 接收的是解析后的候选与原文，不负责凭顺序记忆真实对象。

### 8.2 每个任务独立拥有图类

- 单图：用户可以预先选择图类，或在指令中明确图类。
- 同构批量：一个图类可应用于多个数据源。
- 异构批量：每个 TaskItem 分别保存图类和绑定。
- 信息不足时必须追问；不主动推荐或替换图类。

### 8.3 多数据同图

“多份数据画在同一张图”是单图多源任务，不是多面板组合图。TaskDraft 必须保存每个 source 的绑定和来源标签，TaskCompiler 只在图类声明支持且数据通过兼容性校验时编译。

产品没有多面板组合图能力。目标架构不保留组合图专属关键词拦截；能力目录中没有该动作，通用 capability 校验即可阻止生成。

## 9. 确认与对话 UI

### 9.1 用户确认对象

确认界面按 TaskItem 展示：

| 任务 | 数据 | 图类 | 数据处理 | 字段绑定 | 参数 | 输出 |
|---|---|---|---|---|---|---|
| 1 | 数据 A | K01 折线图 | 无 | Time→x, Signal→y | 线宽 2 | PNG |
| 2 | 数据 B | K08 柱状图 | Group 排序 | Group→category, Mean→value | Y 从 0 开始 | PNG, OPJU |

禁止把不同数据源的 `x/y/category/value` 扁平合并成一份绑定摘要。

### 9.2 数据预览

- 确认卡显示原始前几行或当前 PreparedDataView 预览。
- 字段角色贴近原始列名显示。
- 数据预览、Agent 建议和确认操作在视觉上分区。
- 若有数据处理，明确显示输入行数、输出行数和改变了什么。

### 9.3 实时状态

只展示真实阶段：

- 正在匹配已保存流程。
- 正在检查数据结构。
- 正在读取指定数据范围。
- 正在规划任务。
- 正在校验字段绑定。
- 正在等待确认。
- 正在处理数据。
- 正在调用 renderer。
- 正在验证 Origin 项目。

不得展示模型隐藏思维、伪造百分比或虚构剩余时间。

## 10. 执行与失败恢复

TaskPlan 继续由现有任务运行时执行。目标新增以下规则：

- TaskItem 是局部恢复和幂等重试的最小单位。
- 成功项不得因其他项失败而重复执行。
- 执行错误包含稳定 code、失败阶段、对象版本和可修复类别。
- 确定性参数错误先交给本地修正器。
- 需要重新解释数据或目标时，只把失败 TaskItem 送回 Agent。
- Agent 修复不得改变其他已确认 TaskItem 或用户硬约束。
- 修复方案仍需确认，除非只是无语义变化的安全重试。

## 11. WorkflowRecipe

### 11.1 触发

当任务成功执行并至少完成一次正式导出后，UI 可以显示一次非阻塞提示：

> 如果经常使用类似的数据绘图，可以固化本次数据处理与绘图流程。下次遇到同构数据时可直接复用，以节省时间和模型成本。

按钮：

- `固化流程`
- `查看流程`
- `暂不`

未经用户明确选择，不得静默保存 WorkflowRecipe。

### 11.2 内容

WorkflowRecipe 保存：

- 适用数据结构指纹。
- 文件格式、Sheet/block/区域和解析规则。
- 字段类型、单位、语义槽位和匹配规则。
- DataOperation。
- 图类、字段绑定和绘图参数。
- 导出设置。
- 创建时的数据引擎、图类 profile、renderer 和 Recipe schema 版本。
- 通过的机械验证和用户确认记录。

不保存：

- 原始真实数据值。
- 凭据、绝对敏感路径或对话全文。
- 任意脚本或可执行表达式。
- 未确认的模型推断。

### 11.3 匹配等级

| 等级 | 行为 |
|---|---|
| exact | 自动重放、完整校验、直接进入确认 |
| compatible | 显示结构差异，用户确认后重放 |
| weak | 不重放，只作为 Agent 候选参考 |
| invalid | 版本或能力已失效，阻止使用并说明原因 |

任何重放都必须重新校验字段、单位、角色、数据范围要求、图类 capability 和 renderer 版本。

### 11.4 生命周期

- WorkflowRecipe 本地保存并版本化。
- 修改 Recipe 创建新版本，不静默改变历史任务。
- renderer、profile、DataOperation schema 或解析器发生不兼容升级时自动失效。
- 用户可以查看、重命名、归档和删除；被历史任务引用的版本保留审计身份。

## 12. 状态与审计

WorkflowRun 使用以下规划状态：

```text
routing
deterministic_attempt
recipe_matching
recipe_replay
agent_single_turn
agent_exploration
needs_input
draft_ready
awaiting_confirmation
compiling
executing
repairing_failed_items
completed / partially_succeeded / failed / cancelled
```

每次 WorkflowRun 至少记录：

- 进入和退出的路由等级。
- 程序规则、Recipe 和模型版本。
- Agent 轮次与工具调用数。
- 披露字段、行、scalar 数摘要。
- token、延迟和估算成本。
- TaskDraft hash、确认版本和 TaskPlan ID。
- 成功、失败、跳过和重试的 TaskItem。
- 是否提示固化、用户是否接受。

## 13. 接口草案

### 13.1 WorkflowRouter

```python
route(goal, workflow_context, budget) -> RouteDecision
```

`RouteDecision` 只允许：

- `deterministic`
- `recipe_replay`
- `agent_single_turn`
- `agent_exploration`
- `needs_input`
- `unsupported`

### 13.2 DataInspectionService

```python
inspect_source(source_alias) -> SourceInspection
preview_rows(source_alias, columns, offset, limit) -> RowPage
profile_field(source_alias, field_alias) -> FieldProfile
compare_schemas(source_aliases) -> SchemaComparison
```

### 13.3 TaskCompiler

```python
validate_draft(task_draft, workflow_context) -> DraftValidation
compile_draft(task_draft, expected_revision) -> TaskPlan
```

### 13.4 WorkflowRecipeStore

```python
find_candidates(data_fingerprint, goal_signature) -> RecipeMatches
replay(recipe_version, source_refs) -> TaskDraft
save_from_success(workflow_run_id, user_confirmation) -> WorkflowRecipeVersion
```

## 14. 实现落点

- `contracts/workflows.py` 是 WorkflowRun、WorkflowContext、TaskDraft、TaskPlan 与 WorkflowRecipe 的唯一合同源。
- `workflows/router.py` 按 L0、Recipe、L1、L2 和追问顺序决定路径。
- `workflows/inspection.py` 提供有界、只读、可审计的数据检查。
- `workflows/data_ops.py` 只执行白名单 DataOperation，并保留血缘。
- `workflows/compiler.py` 是 TaskDraft 进入 TaskPlan 的唯一编译入口。
- `workflows/executor.py` 负责逐项执行、幂等与部分失败保真。
- `workflows/recipes.py` 负责成功流程的指纹、固化和严格重放。
- `desktop_core/workflow_service.py` 是 Core 的唯一工作流服务入口。
- Electron、preload 与 renderer 仅通过 `workflow.*` RPC 工作；Pi 只生成或修订 TaskDraft。
- 项目 schema v4 只含 Workflow 表；旧项目 schema 明确拒绝，不迁移、不双写。

## 15. 验收标准

### 15.1 确定性路径

- 明确单图、字段和参数的任务 0 次模型调用。
- 明确三数据三图任务由本地解析保存正确 source 对应关系。
- 参数解析结果在确认卡和两个后端读回一致。

### 15.2 数据探索

- Agent 能按需读取原始数据范围、字段 profile 和多源 schema。
- 未授权字段、超预算范围和任意路径读取稳定拒绝。
- 所有读取有审计，读取本身不改变项目版本。

### 15.3 TaskDraft 与执行

- 批量 TaskItem 不扁平丢失数据源身份。
- 确认前项目版本不变。
- 编译后仍只使用公开 engine action。
- 部分失败不重复成功项，修复只改变失败项。

### 15.4 WorkflowRecipe

- 成功导出后只提示一次，未经确认不保存。
- exact 同构数据重放 0 次模型调用并通过完整机械验证。
- 非同构数据不得因列名相似而误命中。
- 版本不兼容时稳定失效，不静默迁移。

### 15.5 成本与体验

- 报告 L0、Recipe、L1、L2 的命中率。
- 记录模型调用次数、token、估算成本和端到端延迟。
- 相比全量 Agent 路径，简单任务和 Recipe 重放显著降低延迟与成本。
- 用户始终能看到真实阶段、取消当前规划，并理解为什么需要追问。

### 15.6 迁移完整性

- 产品源码只保留 WorkflowRun、TaskDraft、TaskPlan 与 WorkflowRecipe 一套编排合同。
- 正式生成合同不包含任何已退役的计划或上下文 Schema。
- Electron、Core、Pi、持久化和 UI 不存在双入口、双写、fallback 或旧状态映射。
- 旧编排专属测试已删除；新测试直接覆盖 WorkflowRouter、TaskDraft、TaskCompiler、L0/L1/L2、Recipe 与失败项修复。
- 从正式 Windows Electron UI 发出的每个任务都能在审计中定位唯一 WorkflowRun 和 RouteDecision。

## 16. 明确非目标

- 不让 Agent 自主推荐或替换用户未确认的图类。
- 不开放多面板组合图。
- 不开放任意代码、Shell、SQL、Python、LabTalk 或 Origin C。
- 不允许 Agent 直接修改原始数据、项目数据库或 renderer 文件。
- 不用模型隐藏思维作为产品日志或审计证据。
- 不因引入 WorkflowRecipe 建立未经同意的跨项目隐式偏好。
- 不为新编排重写已经通过验收的 Matplotlib/Origin renderer。

## 17. 实现对照表

| 能力 | 正式模块 | 资格要求 |
|---|---|---|
| 确定性图类、参数与数据指代 | WorkflowRouter / DeterministicResolver | 明确任务 0 次模型调用 |
| 高层任务候选与确认 | TaskDraft / Confirmation UI | 确认前无项目副作用 |
| 数据检查与多轮预算 | DataInspectionService / Pi runtime | 只读、限额、全审计 |
| 封闭数据处理 | DataOperation / Data Engine | 原始数据不可变，结果有血缘 |
| 成功工作流固化 | WorkflowRecipeStore | 用户显式确认、严格指纹、失效闭锁 |
| 局部失败恢复 | TaskPlan Runtime | 成功项不重复，失败项可续跑 |
| 单一架构入口 | Electron / Core / Pi / Storage / UI | 无旧 RPC、Schema、表、别名或 fallback |

本文是判断“代码属于哪里、能拥有什么权限、何时应调用模型”的首要对照文档。Renderer 结构、正式图类和 Origin 原生证据仍以各自权威文档为准。
