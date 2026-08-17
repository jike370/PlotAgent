# PlotAgent Agent 基础设施设计记录

> 状态：讨论中的权威决策记录。
> 基线：`c477b34`，已回退 DataPreparationRecipe、自动候选、发布与复用流程，恢复基础 Pi Agent。
> 规则：本文件区分“提案”和“已确认”。只有用户明确确认的内容才构成施工依据；每轮讨论结束后必须同步更新本文件。

相关文档：

- [程序—Agent 编排架构](./AGENT-ORCHESTRATION-ARCHITECTURE.md)
- [Pi Agent 运行时](./PI-AGENT-RUNTIME.md)
- [任务运行时](./TASK-RUNTIME.md)
- [Agent Native 绘图引擎](./AGENT-NATIVE-PLOTTING-ENGINE.md)

## 1. 本轮目标

先做好一个可靠的基础绘图 Agent。Agent 应能读取原始数据、理解任务、整理数据、调用绘图引擎、检查结果并在必要时修正，而不是由程序使用关键词、正则或固定语义路由代替模型判断。

本轮不重新引入：

- DataPreparationRecipe 自动匹配、候选索引、发布与复用；
- 由程序解释自然语言或决定数据—图形对应关系；
- 为了减少模型调用而提前固化尚未证明可靠的复杂编排；
- 多 Agent 编排。

## 2. 十项设计总表

| 序号 | 设计项 | 当前状态 | 需要回答的核心问题 |
|---|---|---|---|
| 1 | 任务合同 | 已确认 | Agent 怎样知道目标、输入、约束、成功标准和交付物？ |
| 2 | 领域说明 | 待讨论 | 哪些绘图知识、科学边界和标准案例应提供给 Agent？ |
| 3 | 上下文机制 | 已确认 | Agent 每轮能看到什么，怎样按需读取数据而不淹没上下文？ |
| 4 | 运行循环 | 待讨论 | Agent 怎样观察、行动、检查、修复、停止或追问？ |
| 5 | 工具体系 | 已确认 | Agent 需要哪些检查、整理、绘图、读回和交付工具？ |
| 6 | 验证器 | 已确认 | 怎样独立证明数据、科学语义、图形和导出物正确？ |
| 7 | 权限与回滚 | 提案待确认 | 哪些动作可自动执行，哪些需要确认，失败如何撤销？ |
| 8 | 工作记忆 | 待讨论 | 一次任务中应记住哪些决定、结果和失败，哪些不得长期保存？ |
| 9 | 可观察性 | 待讨论 | 用户和开发者怎样看到阶段、进度、原因、成本与结果？ |
| 10 | 评测体系 | 待讨论 | 怎样证明 Agent 稳定、正确、可恢复，并控制时长和成本？ |

建议讨论顺序不是表格顺序，而是：任务合同 → 运行循环 → 上下文 → 工具 → 验证器 → 权限与回滚 → 工作记忆 → 可观察性 → 领域说明 → 评测体系。前一项会约束后一项，避免先堆工具再倒推 Agent 行为。

### 2.1 Pi Agent 与 PlotAgent 的设计边界（已确认）

项目当前使用 `@earendil-works/pi-agent-core 0.84.1`。Pi 是通用 Agent loop，不理解绘图、数据语义、Origin、项目版本或产品完成标准。

九项基础设施（工具另列）的复用边界如下：

| 设计项 | Pi 可提供 | PlotAgent 必须设计 | 结论 |
|---|---|---|---|
| 任务合同 | 无领域任务合同 | TaskEnvelope、TaskIntent、TaskState、确认与完成条件 | 产品自研 |
| 领域说明 | 承载 `systemPrompt` | 绘图知识、科学边界、标准案例、按图类说明 | 产品自研内容 |
| 上下文机制 | messages、`transformContext`、`convertToLlm`、自定义消息 | 数据按需检索、披露预算、图类合同注入、压缩与恢复策略 | Pi 机制 + 产品策略 |
| 运行循环 | 模型调用、工具循环、顺序/并行执行、turn stop、continue、steering/follow-up、abort | 阶段机、最大轮次、提交/追问/失败的退出语义 | 主要复用 Pi |
| 验证器 | 工具参数 Schema 和调用结果通道 | 数据、科学语义、Renderer、Origin、导出物和项目状态验证 | 产品自研 |
| 权限与回滚 | `beforeToolCall`、`afterToolCall`、abort | 工具风险等级、用户授权、临时对象、事务、版本、撤销与幂等 | Pi 钩子 + 产品策略 |
| 工作记忆 | 内存 messages/state、continue、上下文变换；持久 session 后端需另配 | 任务事实、对象句柄、已通过部分、错误、项目持久状态和保留期限 | Pi 容器 + 产品模型 |
| 可观察性 | Agent/turn/message/tool streaming events | 用户阶段文案、任务中心、trace 持久化、对象/版本、成本与审计 | Pi 事件 + 产品呈现 |
| 评测体系 | 可注入 stream/provider，便于构造测试 | 绘图任务集、结果 grader、轨迹 grader、重复运行和发布门槛 | 产品自研 |

工具体系本身也是混合边界：Pi 提供 `AgentTool`、参数 Schema、执行模式、事件和前后钩子；PlotAgent 定义工具语义、数据权限、实现、返回合同和验证。

建议保持 Pi 可替换：PlotAgent 的任务合同、图类合同、验证器、项目事务和评测不得写进 Pi 分支或依赖 Pi 私有消息格式。两者之间使用 `PiRuntimeAdapter` 连接。

当前集成已经使用 Pi 的 Agent loop、顺序工具执行、turn stop、abort 和生命周期事件；尚未充分使用 `transformContext`、steering/follow-up、工具前后权限钩子和持久会话。当前每次运行创建新的 Agent 且 `messages=[]`，`sessionId` 主要用于 Provider 会话/缓存关联，不能视为已经具备跨任务工作记忆。

确认结论：Pi 只作为运行循环、模型调用和通用工具调度底座。除运行循环外，任务合同、领域说明、上下文策略、验证、权限与回滚、工作记忆、可观察性和评测都必须由 PlotAgent 根据产品目标自行设计；工具的框架能力复用 Pi，工具语义与实现由 PlotAgent 设计。

## 3. 共同边界

以下边界作为本轮讨论起点，尚不替代后续逐项设计：

- 模型负责理解目标、判断数据语义、规划步骤、选择工具、解释工具结果和处理真正的歧义。
- 程序负责安全读取、确定性执行、状态保存、Schema 校验、权限、回滚、审计和结果验证。
- 程序不得通过自然语言关键词、正则或图类别名表替模型决定任务语义。
- Agent 不直接执行任意 Python、Shell、SQL、JavaScript、LabTalk 或 Origin C；需要的能力通过受控工具提供。
- 原始数据只读；Agent 的数据整理先形成临时结果，正式提交后才成为项目版本。
- 任务完成必须依据真实结果和验证报告，不能依据 Agent 自述“已完成”。

## 4. 设计项 1：任务合同

### 4.0 名词解释与作用

“任务合同”是内部工程名称，用户界面不需要显示这个术语；用户看到的可以是“任务卡”“执行确认”或自然语言对话。

它不是法律合同、用户填写的需求表、预先写死的工作流，也不是可跨任务复用的 Recipe。它是一次任务从开始到结束持续存在的共享记录，用来回答：

- 用户原本要求什么；
- 用户明确选择了哪些数据、图类和对象；
- Agent 当前怎样理解目标；
- 已经观察到什么、完成了什么、还差什么；
- 哪些步骤可以自主执行，哪些正式变更需要确认；
- 满足哪些条件后才能宣布任务完成。

需要任务合同的原因不是模型不会理解一句话，而是绘图任务通常会跨越多轮模型调用和多个工具。自然语言保留用户目标，但不能单独承担运行状态、权限、对象版本、部分成功和机械完成条件。若只有聊天记录，容易出现目标漂移、重复执行、错用旧对象、失败后从头再来，或者 Agent 仅凭自己的文字结论声称完成。

任务合同承担六个作用：

1. **保持目标**：多轮调用后仍以用户原始要求为准；
2. **限制权限**：明确 Agent 可以读取、临时处理和正式修改哪些对象；
3. **协调执行**：让 Agent 与程序共享当前步骤、对象句柄和版本；
4. **支持恢复**：记录已成功部分，只重试失败部分；
5. **定义完成**：把用户目标与程序可验证的交付条件连接起来；
6. **承载确认**：从同一记录生成用户可读的确认卡，而不是另造一份可能不一致的摘要。

任务合同不要求用户在开始前把需求完整结构化。程序先建立只含原始指令、显式选择、权限和版本的空壳；Agent 查看数据并调用工具后逐步补全其语义理解；程序持续维护执行状态。用户只在正式提交边界确认关键结果。

### 4.1 已确认设计

不建议把所有内容塞进一个由模型自由生成的大 JSON。任务合同拆成三个互相连接、权威来源不同的对象：

#### A. TaskEnvelope：程序提供，不解释语义

- `task_id`；
- 用户原始指令，逐字保留；
- 用户显式选择的数据源、图类、当前图和输出位置；
- Agent 可访问的安全数据句柄；
- 本轮允许的工具、权限和预算；
- 当前项目 revision 与对象版本。

TaskEnvelope 只保存事实、选择和权限。程序不得从用户文本补出图类、字段、单位、操作或数据—图形对应关系。

#### B. TaskIntent：Agent 负责形成

- Agent 对目标的简明理解；
- 一个或多个任务项，以及数据源—图类—输出的对应关系；
- 每项需要的数据整理、字段绑定和绘图参数；
- 用户约束与不可改变项；
- 可机械检查的成功标准；
- 仍未解决、且会实质影响正确性的歧义。

TaskIntent 可随着工具观察而逐步完善，不要求 Agent 在第一轮凭列名猜完整计划。

#### C. TaskState：运行时维护

- 当前阶段与正在执行的步骤；
- 已完成且已验证的步骤；
- 临时数据、预览图和结果对象句柄；
- 失败步骤、错误类别和剩余修复预算；
- 用户确认、取消、撤销与最终交付状态。

TaskState 由程序持久化，Agent 只能通过受控动作推进，不能自行声称修改状态。

### 4.2 建议的确认边界

Agent 可以先自主检查和临时整理数据，再形成用户可读的 TaskIntent。用户确认的是“将要正式提交什么”，而不是确认 Agent 每一次只读查询和临时计算。

最低确认内容建议为：

- 使用哪些数据；
- 每份数据对应什么图；
- 关键字段绑定；
- 会发生哪些不可逆或会改变科学含义的数据操作；
- 主要绘图参数；
- 预期交付物。

### 4.3 已确认边界

1. 用户显式选择图类后，把它视为不可被 Agent 改写的硬约束；Agent 发现不兼容时只能解释并建议更换。
2. 临时数据检查和整理允许 Agent 自动执行，直到正式写入项目才统一确认。
3. 成功标准由 Agent 提出业务与科学目标，程序补充结构、文件和版本门禁；程序不能补充业务语义。

### 4.4 图类数据合同与任务合同的关系

提案：每个图类需要的数据格式必须有正式合同，但不把 34 个图类的完整定义复制进每一份任务合同。

职责分为两层：

1. **EngineProfile / Renderer Data Contract 是图类规则的唯一真值**，保存 required、optional、repeatable roles，允许的数据类型，wide/long/matrix 形态，行级关系、配对/分组要求和图类固定科学语义；
2. **TaskContract 是一次任务的实例记录**，引用选定的 `profile_id`、合同版本或 hash，并保存本次 source、临时整理结果、具体字段绑定、数据操作和验证结论。

例如双向误差棒图的图类合同定义需要 X、Y、X error、Y error 及其类型和方向语义；某次任务合同只记录本次 `Time -> X`、`Mean -> Y`、`SD_X -> X error`、`SD_Y -> Y error`，以及该绑定是否通过合同校验。

这样设计的原因：

- 避免在每个任务中复制图类规则并产生版本漂移；
- 避免把所有图类定义一次性塞进模型上下文；
- renderer 合同变更时可以用 hash 判断旧任务是否需要重新编译；
- 任务记录仍能独立证明本次用了什么数据、怎样绑定、是否满足当时合同。

Agent 选择或用户显式选择图类后，程序按需把该图类合同提供给 Agent。Agent 可以据此检查和整理数据，但不能改写图类合同。Core 在正式执行前以同一合同重新验证，不能依赖 Agent 自述“格式已经正确”。

### 4.5 已确认任务生命周期

一条可执行目标建立一个任务；普通知识咨询不建立任务。是否构成可执行目标由 Agent 判断，程序不使用关键词或正则路由。

批量目标仍是一个任务，内部包含多个独立 TaskItem，例如“数据 A → 折线图、数据 B → 柱状图”。每个 TaskItem 分别记录临时结果、确认、执行、验证、失败和交付状态。

标准生命周期为：

```text
用户提出目标
→ 建立任务
→ Agent 检查并临时整理数据
→ 形成任务理解或提出实质追问
→ 用户集中确认正式变更
→ 冻结任务版本并执行
→ 验证
→ 完成 / 部分完成 / 失败 / 取消
```

已确认六条原则：

1. 一条可执行目标建立一个任务，批量绘图是一个任务下的多个 TaskItem；
2. Agent 可以自主查看原始数据并执行只读检查和临时数据整理；
3. 正式修改项目前只进行一次集中确认，不逐步确认内部尝试；
4. 工具参数、临时文件、renderer 调用等技术修复不重新确认；图类、字段、单位、统计定义、分组或有效数据取舍等语义变化必须生成新任务版本并重新确认；
5. 批量任务保留已成功并验证的 TaskItem，只重试失败项；
6. 只有真实结果通过验证器后才能标记完成，Agent 自述不构成完成证据。

用户确认后冻结 `TaskIntent` 版本。技术修复只能在不改变该版本语义的范围内进行；需要改变语义时生成新版本并展示差异。部分成功不是整轮失败，必须保留并独立呈现。

## 5. 设计项 2：上下文机制

### 5.0 名词解释

上下文是模型在某一轮实际收到的工作材料，不等于聊天记录。它包括系统职责、当前任务、数据事实、图类合同、工具结果和运行状态。

目标不是把项目全部内容一次性塞给模型，而是让 Agent 始终看到完成当前决策所需的最小充分事实，并可主动取得更多原始证据。

### 5.1 三层上下文

#### A. 固定领域上下文

每轮都提供但保持精简：

- Agent 的职责和程序边界；
- 不得猜测的科学语义；
- 工具使用、确认、完成和失败原则；
- 少量跨图类通用规则。

具体图类和长篇说明不常驻系统提示。

#### B. 当前任务快照

由 PlotAgent ContextBuilder 从权威状态重建：

- 用户原始指令；
- 用户显式选择的数据源、图类和当前图；
- 当前 TaskIntent 版本、TaskItem 状态和未解决问题；
- 有权访问的数据源目录及稳定用户可读别名；
- 对显式选择或本轮附带数据的轻量真实数据预览；
- 当前选定图类的数据合同摘要；
- 已验证结果、最近一次相关失败和剩余预算。

轻量预览必须包含实际数据值，而不只是列名和类型。默认只提供足以开始判断的少量行、列和来源坐标，并明确是否截断。

#### C. 按需证据

Agent 通过只读工具主动取得：

- 原始文件结构、编码、分隔符、表头和数据区候选；
- 指定行列范围、分页预览、随机或分层样本；
- 字段类型、缺失、唯一值、分布和异常值；
- 行身份、配对、分组、排序和跨表关系；
- 仪器元数据、单位原文和来源位置；
- 指定图类的完整数据合同与示例；
- 临时数据整理结果和 renderer 读回。

小数据允许 Agent 通过分页读取完整内容；大数据优先使用 profile、采样和局部范围，但不能因此禁止 Agent 查看解决歧义所需的原始行。

### 5.2 ContextBuilder 的边界

程序只依据显式选择、访问权限、对象版本、大小和 token 预算机械组装上下文，不根据关键词、列名或自然语言推断“哪些数据最相关”。

每次模型调用前，从 TaskContract、项目对象和证据句柄重新构建上下文。Pi 的 message history 只是本轮推理载体，不是任务状态的唯一真值。

压缩时必须保留：

- 用户原始指令；
- 已确认的 TaskIntent；
- 当前 TaskItem 与未解决问题；
- 已验证通过的部分；
- 会影响下一步的工具结果、错误和对象句柄；
- 用户后来追加或修改的约束。

可以删除或改写为结构化摘要：重复解释、已被新结果替代的预览、冗长成功日志和不再影响决策的旧工具输出。不得压缩掉数据来源、单位、分组、配对、统计定义或确认记录。

### 5.3 多数据源与图类合同

数据源目录必须提供文件名、Sheet/block 名、用户可读别名、shape、字段摘要和稳定句柄。Agent 可以根据用户原文和实际数据决定数据—图形对应关系；程序不得按上传顺序或字段相似度自动绑定。

用户显式选择图类时，只注入该图类完整合同。尚未选择图类时提供精简图类目录，并允许 Agent 按需查询候选合同，不一次注入全部图类说明。

### 5.4 数据披露与预算

- 所有工具结果标明来源、截断、采样方法和生成时间；
- 远程模型读取原始数据必须服从用户的数据出境授权；
- ContextBuilder 只裁剪展示，不改变数据内容或科学含义；
- token 预算不足时先压缩历史解释，再压缩重复工具结果，最后减少预览；不得优先删除任务目标和已确认语义；
- Agent 达到读取或轮次预算时，应说明还缺什么证据并停止或追问，不能以猜测补齐。

### 5.5 已确认原则

1. Agent 每轮始终看到用户原始指令和当前任务状态；
2. 显式选择或本轮附带的数据默认提供含真实值的轻量预览，而不只提供 schema；
3. Agent 可通过工具继续读取原始文件和任意必要范围，小数据可分页读完；
4. 具体图类合同按需注入，不把全部图类说明常驻上下文；
5. 每轮上下文从 PlotAgent 权威状态重建，Pi 聊天历史不作为唯一真值；
6. 程序只能按权限、对象和预算机械组装上下文，不做语义路由；
7. 压缩不得丢失原始目标、已确认语义、来源、单位、分组、配对和完成证据。

## 6. 设计项 3：工具体系

### 6.0 目标和边界

工具是 Agent 观察环境和改变环境的唯一通道。工具应足够通用，使 Agent 能组合完成未预先写死的绘图任务；同时必须类型化、可审计、可取消、可验证，不开放任意 Python、Shell、SQL、JavaScript、LabTalk、Origin C 或 renderer 私有参数。

工具描述能力，不描述固定流程。Agent 决定何时调用和怎样组合；程序只按 TaskState、权限和预算决定哪些工具当前可用。

### 6.1 五类工具

#### A. 数据与来源检查

保留并整合当前 `list_sources`、`inspect_source`、`preview_rows`、`sample_rows`、`profile_field`、`search_values`、`compare_schemas` 和 `inspect_instrument_metadata`，并补充：

- `inspect_raw_source`：查看编码、分隔符、原始行、preamble/postamble、表头和数据区域候选；
- `analyze_relationships`：检查唯一性、重复、行身份、配对、分组、排序和跨字段关系；
- `compare_sources`：比较多个 Sheet/block 的字段、单位、key 和可拼接关系。

检查工具必须返回实际证据、来源坐标、截断/采样方式和审计信息，不能只返回“兼容/不兼容”的结论。

#### B. 临时数据工作区

目标操作集合：

- 重新解析原始来源和选择数据区域；
- 选择、重命名、转换类型；
- 筛选、排序、去重；
- 安全派生字段和单位换算；
- long/wide reshape；
- concatenate 和 keyed join；
- 显式分组聚合；
- 保留或建立稳定行身份、配对和来源列。

每个操作接受 `input_handle`，返回新的不可变 `DataViewHandle`。后续工具可以继续使用该 handle，形成链式整理；不要求每一步都回到原始 `source_alias`。

不使用任意代码。派生、转换和聚合使用登记过的类型化算子；Agent 选择算子、字段和参数，程序确定性执行。会改变科学语义的聚合、单位、配对、有效数据删除等操作写入 TaskIntent 并在正式提交前展示。

#### C. 图类、沙箱渲染与编辑

- `list_plot_profiles`：精简图类目录；
- `get_plot_profile`：单个图类完整数据和动作合同；
- `preview_plot`：用 DataViewHandle、绑定和公开绘图参数在沙箱生成目标后端预览；
- `inspect_plot`：读取字段绑定、图形对象、轴、系列、图例、注释和后端原生结构；
- `apply_plot_edits`：只接受 Matplotlib 和 Origin 都支持的公开视觉动作，在沙箱产生新 PlotHandle。

`preview_plot` 返回图像句柄和结构化读回。模型支持图像时可查看预览；不支持时至少依据机械读回继续。Origin 目标应在需要证明原生结构时使用真实 Origin 沙箱，不能用 Matplotlib 预览替代 Origin 可编辑性证据。

#### D. 任务控制与正式执行

- `ask_user`：只询问会实质影响正确性的歧义；
- `submit_task_intent`：提交完整任务理解并生成确认卡；
- `execute_task_item`：只在用户确认后的授权范围执行一个 TaskItem；
- `export_artifact`：只导出已验证结果和已授权格式/位置；
- `report_unsupported`：完成必要检查后明确说明能力边界。

确认前 Agent 只能产生 staged 对象。用户确认后，Core 为冻结的 TaskIntent 生成执行授权；Agent 不能借执行工具改变已确认的图类、字段、单位或统计语义。

#### E. 验证与交付证据

数据操作、渲染、编辑、执行和导出工具完成后，程序自动运行对应验证器并把报告附在工具结果中。Agent 不需要靠记忆额外调用“验证一下”，也不能跳过验证。

必要时提供 `inspect_validation_report` 读取详细报告，但完成状态只由权威验证结果推进。

### 6.2 统一工具结果合同

所有工具返回同一外壳：

```text
status
output_handle / artifact_handle
summary
schema_or_structure
bounded_preview
provenance
validation_report
warnings
side_effect: none | staged | committed
error: code, category, retryable, repair_hint
```

禁止只向 Agent 返回不透明的 “invalid parameters” 或异常字符串。错误至少分为：

- `AGENT_REPAIRABLE`：参数、字段、合同不匹配，Agent 可根据结构化信息修复；
- `USER_INPUT_REQUIRED`：科学语义或授权缺失，需要用户回答；
- `TRANSIENT`：超时、进程或后端暂时失败，可安全重试；
- `UNSUPPORTED`：当前产品能力不支持；
- `FATAL`：项目或环境损坏，需要停止。

错误结果必须说明是否产生副作用。验证失败不得登记正式项目版本。重复请求通过 task/item/tool idempotency key 防止重复提交。

### 6.3 工具暴露与预算

不把全部工具永久暴露给每一轮模型。工具集合只依据 TaskState 和授权阶段机械变化：

- 调查阶段：检查、临时数据、图类合同、沙箱渲染、追问、提交 Intent；
- 已确认执行阶段：冻结任务范围内的执行、检查、技术修复和验证；
- 已验证交付阶段：导出和交付检查。

这种裁剪不解释自然语言，只减少工具歧义和越权面。每个工具声明成本等级、超时、最大返回量和是否占用 Origin。廉价检查优先；真实 Origin、视觉评估和导出属于高成本操作，由预算限制但不能用廉价替代品伪造通过。

工具 Schema 错误、合同错误和瞬时执行错误属于技术修复，不占用视觉修改次数。视觉修改次数只在成功生成可审查预览后计算。

### 6.4 当前基线与明确缺口

当前已有：8 个只读检查工具、9 个数据预演工具、图类目录、追问、报告不支持和 TaskDraft 提交。

当前主要缺口：

- 不能检查和重新解析原始文件布局；
- 临时数据操作以 `source_alias` 为主，缺少统一可链式 DataViewHandle；
- 缺少类型转换、keyed join、去重、显式聚合和关系分析；
- 缺少 Agent 可用的沙箱 render、原生结构读回和局部修正；
- Agent 提交 TaskDraft 后退出，不能持续完成执行、验证、技术修复和交付；
- 多数错误仍不足以告诉 Agent 怎样安全修复。

### 6.5 已确认原则

1. 不开放任意代码，只提供足以组合完成任务的类型化工具；
2. 数据操作统一使用不可变、可链式 DataViewHandle，原始数据只读；
3. 补齐原始来源检查、关系分析、类型转换、join、去重和显式聚合；
4. preview 与正式执行使用同一实现，确认前 staged，确认后按冻结 TaskIntent 提交；
5. 增加沙箱渲染、结构读回和局部编辑，使 Agent 能完成“渲染—检查—修正”闭环；
6. 每个工具自动附带来源、验证、警告、副作用和结构化错误；
7. 技术错误允许 Agent 修复，不占用视觉修改次数；
8. 工具按 TaskState 和权限阶段暴露，不通过自然语言路由；
9. 正式执行和导出只能作用于用户已确认的语义范围；
10. Agent 在同一任务中持续到验证和交付完成，而不是提交 TaskDraft 后立即退出。

### 6.6 设计依据与 PlotAgent 取舍

本项不是照抄单一框架，而是综合以下公开工程实践、协议和论文：

- [OpenAI《A practical guide to building agents》](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)：工具应标准化、文档化、可复用和充分测试；工具过载的关键是重叠和歧义；按只读/写入、可逆性和影响进行风险分级，并为高风险动作设置人工介入。
- [Anthropic《Writing effective tools for agents》](https://www.anthropic.com/engineering/writing-tools-for-agents)：工具要有清晰边界和 namespace，返回对 Agent 有意义且 token 高效的上下文，并用真实 Agent 任务评测工具是否可理解、可组合。
- [Model Context Protocol 2025-11-25 Tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)：工具使用输入/输出 Schema 和结构化结果；可修复的执行错误应作为模型可见的 tool result 返回，使模型能够自我修正；客户端应验证结果、设置超时、记录调用并对敏感操作确认。
- [ReAct](https://arxiv.org/abs/2210.03629)：推理和行动交替，Agent 根据环境观察更新计划并处理异常，而不是一次生成完整计划后停止。
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code/cli-usage)：成熟产品公开区分 allowed/disallowed tools、permission mode、最大轮次、continue/resume 和 verbose trace，证明权限、预算、恢复和可观察性应围绕工具运行时设计。

本地产品证据来自 `D:\fig-claw-teacher-lab` 的真实绘图任务记录，尤其是 `teacher_evaluation_027_034.md` 和 `_project_output_protocol_v1.md`。记录显示任务反复涉及字段绑定、图形意图、层结构、记录身份、视觉编码、坐标尺度、行关系、数据变换和统计定义；运行失败中存在可由结构化错误修复的 Schema/合同问题，近期任务普遍需要一次局部视觉修正。因此 PlotAgent 需要“真实数据观察—类型化变换—沙箱渲染—读回—局部修正”的闭环，不能只提交计划。

以下部分是 PlotAgent 特有设计，不是上述来源的直接结论：

- 不可变 DataViewHandle 和原始数据只读；
- Matplotlib/Origin 共同动作与真实 Origin 原生读回；
- 技术修复不占视觉修改次数；
- 用户确认后用冻结 TaskIntent 限定正式执行语义；
- 每个工具自动附带 PlotAgent 数据、图形和交付验证报告。

## 7. 设计项 4：验证器

### 7.0 作用和边界

验证器回答的是“实际结果是否忠实实现已确认任务和图类合同”，不是替用户决定应该画什么、应该使用哪种统计定义或哪种视觉偏好。

模型负责提出语义解释；程序只能验证该解释是否被精确执行，以及是否违反已知图类、数据、单位和项目合同。存在无法从事实和合同判定的科学歧义时交还 Agent 追问用户，不能由验证器补语义。

### 7.1 七层验证

#### A. 任务与授权验证

- task、TaskItem、TaskIntent version 和 project revision 一致；
- 执行动作没有超出用户确认的 source、profile、bindings、数据操作、视觉动作和输出范围；
- idempotency key、对象版本和授权仍有效；
- 技术修复没有暗中改变任务语义。

#### B. 数据与来源验证

- 原始 source hash、DataViewHandle、操作链和结果 hash 可追溯；
- 行列数、类型、缺失、有限性、单位和来源坐标符合预期；
- key、行身份、配对、分组、排序与 TaskIntent 一致；
- 未确认的有效行删除、聚合、去重、填补和单位变化均被拒绝；
- 结果满足目标图类的 renderer data contract。

#### C. 科学语义执行验证

程序验证已选择的语义是否被正确执行，例如 V→mV 的量纲和数值、mean/median/SD/SEM/CI 算子的定义、log 变换、阈值、误差方向和配对 key。

程序不判断用户是否“应该”使用 SEM 而不是 SD。若 TaskIntent 没有明确该语义，必须由 Agent 根据证据判断或追问用户。

#### D. Plot/Engine 合同验证

- profile ID、合同版本/hash 和 renderer 版本一致；
- required/optional/repeatable roles 和实际字段绑定一致；
- PlotDocument、公开语义对象、视觉动作和轴/系列目标正确；
- 动态数据导致的对象增删符合图类规则，无残留、重复或错绑；
- Matplotlib 与 Origin 只执行各自受支持且已公开的动作。

#### E. 后端最终状态读回

验证必须读取已生成对象的最终状态，不能只相信 renderer 返回“成功”。

- Matplotlib：读取最终 Figure/Artist 状态、绑定、轴、系列、图例、注释和导出结果；
- Origin：读取原生 Worksheet/Matrix/Graph/Layer/DataPlot、源 range、PID、分组、对象属性和数据值；
- OPJU 交付：在新的 Origin 会话中保存、关闭、重开，再次验证源数据、原生结构和 Agent 编辑；
- 读回结果与 TaskIntent、DataView 和 PlotDocument hash 绑定。

#### F. 产物验证

- 文件存在、非空、hash 和格式正确；
- PNG/SVG 可解码，尺寸和页面对象有效；
- OPJU 可由目标 Origin 版本打开，图和数据对象存在且可继续编辑；
- 导出路径、文件名、数量和 TaskIntent 一致；
- 产物验证完成前不显示“已完成”或“导出成功”。

#### G. 视觉验证

视觉验证与机械验证分开：

1. 机械视觉检查：画布、对象边界、颜色/线型/符号/字号等已请求参数和显著渲染异常；
2. Agent 视觉检查：有视觉模型时查看真实预览，根据用户要求、图类基线和有限 rubric 提出局部修正；
3. 用户视觉判断：审美偏好、科研表达取舍和新 renderer 默认态由用户最终决定。

普通用户任务在确认卡前完成沙箱视觉检查，用户确认后正式结果必须与已确认预览和参数一致；不要求用户在每个技术步骤重复验收。新增/重构 renderer、修改默认模板或发布版本时，必须单独进行人工视觉审查，不能用 Agent 自评代替。

### 7.2 统一 VerificationReport

每个验证问题至少包含：

```text
validator
status
severity
code
task_item_id
object_or_field
expected
observed
evidence_handle
repair_scope
changes_semantics
retryable
```

TaskItem 的聚合状态为：

- `PASS`：所有本项必需门禁通过；
- `REPAIRABLE`：可在冻结 TaskIntent 内自动修复；
- `RECONFIRM_REQUIRED`：修复会改变字段、单位、统计、分组、图类或其他语义；
- `USER_REVIEW_REQUIRED`：机械正确但存在只能由用户判断的视觉/科研表达问题；
- `BLOCKED`：环境、权限或外部依赖阻断；
- `FAIL`：观察到产品错误且自动修复预算耗尽。

不同交付物启用不同必需门禁。只导出 PNG 不要求 Origin；请求 OPJU 时 fresh reopen 和原生可编辑性是强制门禁。

### 7.3 修复与完成循环

```text
执行工具
→ 自动验证
→ PASS：推进 TaskItem
→ REPAIRABLE：把结构化报告交给 Agent，只修失败部分
→ RECONFIRM_REQUIRED：形成 TaskIntent 新版本和差异确认
→ USER_REVIEW_REQUIRED：展示证据并请求用户判断
→ BLOCKED / FAIL：保留已成功项并明确停止原因
```

验证器必须给出修复范围，Agent 不得借修复重做已经通过的对象。Schema、参数、临时进程和 renderer 技术错误使用独立技术预算；成功生成可审查预览后才计入视觉修改预算。

任务只有在所有必需 TaskItem 和交付门禁均为 PASS 时标记 `completed_verified`。部分通过时标记 `partial`，不能把任务整体包装成成功或丢弃通过项。

### 7.4 证据和可复现性

VerificationReport 保存：

- 用户确认的 TaskIntent hash；
- source/DataView/Profile/Renderer/PlotDocument hash 与版本；
- 工具调用和后端 session 身份；
- 读回快照、文件 hash、预览/截图和 Origin reopen 结果；
- 验证器版本和发生时间。

报告引用真实项目对象和产物，不把聊天文字、renderer 自述或测试夹具当作本次任务证据。

### 7.5 当前基线和缺口

当前已有 Profile/TaskDraft 编译校验、EngineReadback、source hash 校验、多数 Origin profile 的原生结构读回和 fresh reopen，以及大量逐图测试。

当前缺少：

- 跨 TaskContract、DataView、renderer 和 artifact 的统一 VerificationReport；
- 数据关系、单位和科学操作的统一任务级验证；
- 可直接交给 Agent 修复的结构化问题与 repair scope；
- 机械视觉、Agent 视觉和人工视觉的明确分层；
- 按交付物聚合的任务完成门禁；
- 验证失败后只修失败项并继续同一任务的正式闭环。

### 7.6 已确认原则

1. 验证器证明“已确认语义是否被正确执行”，不替用户选择科学语义；
2. 验证分为任务授权、数据来源、科学执行、Plot 合同、后端读回、产物和视觉七层；
3. 所有改变环境的工具完成后自动验证，Agent 不能跳过；
4. 最终状态和真实产物读回优先于 renderer 自述；
5. 请求 OPJU 时必须在新 Origin 会话中重开并验证原生可编辑性；
6. 视觉验证分为机械、Agent 和用户三层，普通任务不要求用户重复验收每个技术步骤；
7. VerificationReport 必须结构化并包含 expected、observed、证据和 repair scope；
8. 冻结 TaskIntent 内的技术错误由 Agent 自动修，语义变化必须重新确认；
9. 只修失败项并保留已通过项，技术预算和视觉修改预算分开；
10. 所有必需门禁 PASS 后才能标记 `completed_verified`，部分通过只能标记 `partial`。

## 8. 设计项 5：权限与回滚

### 8.0 目标

权限设计同时满足两点：Agent 能连续自主完成任务；一次确认不能变成对整个项目和文件系统的无限授权。

采用“最小权限 + 分阶段能力授权”：用户确认 TaskIntent 时只确认任务语义和交付范围，Core 随后签发仅能完成该冻结版本的 ExecutionGrant。内部只读、临时整理和沙箱尝试不逐次弹窗。

### 8.1 四级动作风险

| 等级 | 动作 | 默认行为 |
|---|---|---|
| P0 | 读取项目目录、数据结构、原始行、图类合同和验证报告 | 在既有数据披露授权内自动执行 |
| P1 | 创建临时 DataView/PlotHandle、沙箱渲染、机械验证 | 自动执行；只写 task staging，可取消和清理 |
| P2 | 创建正式 DataView/Plot 版本、应用确认内编辑、生成确认内交付物 | 用户确认 TaskIntent 后由 ExecutionGrant 授权，不逐工具重复确认 |
| P3 | 扩大数据源/对象范围、改变语义、发送新数据到远程、覆盖外部文件或写入未确认位置 | step-up 确认或生成 TaskIntent 新版本 |

Agent 不获得物理删除项目历史、任意文件删除、任意路径写入、终止用户进程或任意代码执行权限。产品删除优先使用 archive/tombstone 和新项目 revision。

### 8.2 ExecutionGrant

ExecutionGrant 由 Core 持有，模型只能使用受它约束的工具，不能编辑授权本身。最低包含：

```text
grant_id
task_id
task_intent_version / hash
project_id / expected_revision
allowed_task_items
allowed_sources / plots / profiles
allowed_data_operations / bindings / visual_actions
allowed_output_formats / destinations / overwrite_policy
expires_at
retry_and_cost_budget
```

以下情况立即使授权失效：用户取消、TaskIntent 语义变化、项目 revision 冲突、对象版本被外部修改、授权过期或预算耗尽。技术重试沿用同一语义授权；不能通过修改工具参数扩大 scope。

### 8.3 Staging、原子提交与批量部分成功

每个任务有隔离 staging workspace。确认前产生的 DataViewHandle、PlotHandle、预览和临时 OPJU 都在 staging 中，带 task/item 身份和 TTL，不进入正式项目目录。

正式提交以 TaskItem 为最小事务：

```text
准备 staged 结果
→ 验证
→ 检查 expected project revision
→ 原子登记 DataView + Plot/Artifact + VerificationReport
→ 生成新 project revision
```

同一个 TaskItem 的数据与图必须一起成功或一起不发布。批量任务不使用全批 all-or-nothing：每个 TaskItem 独立原子提交，因此已通过项保留，失败项可以单独重试。

### 8.4 幂等、重试与未知结果协调

每个有副作用的逻辑步骤使用稳定 idempotency key：

```text
task_id + task_intent_version + task_item_id + logical_step
```

相同 key 和相同参数重复调用时返回第一次已记录结果，不重复创建对象或文件；相同 key 但参数不同必须拒绝。

连接中断、超时或进程异常后，Core 先查询 StepReceipt 和最终对象状态，再决定返回既有结果、继续清理或安全重试。结果未知时禁止盲目重放写操作。技术 attempt 编号用于审计，但不能改变同一逻辑步骤的 idempotency key。

### 8.5 取消和超时

取消信号沿 `Pi → Core → tool → renderer/Origin automation` 传播。状态至少区分：

- `cancel_requested`；
- `cancelling`；
- `cancelled_clean`；
- `completed_before_cancel`；
- `cleanup_required`。

取消后停止启动新工具。正在执行的只读或 staged 操作在安全点中止并清理；数据库 commit、文件原子发布等短临界区不在中间强杀，完成后按实际结果报告。

模型超时本身不能产生正式项目副作用。工具超时必须返回已知 side-effect 状态；若无法确认，进入协调/清理而不是自动重试。

Origin 只终止本任务创建且身份可验证的自动化实例，绝不结束用户手工 Origin。取消或异常后释放自动化 lease、临时项目和文件句柄。

### 8.6 撤销与外部文件

项目内撤销通过不可变版本实现：撤销创建新的 project revision，恢复上一份 DataView/Plot 引用并保留审计历史，不原地反向修改或物理删除旧版本。

导出文件先写到同卷临时路径，关闭句柄、验证完成后再原子发布到目标名。默认不覆盖；覆盖必须在确认卡中明确。外部文件一旦交付不能假装可由项目 undo 自动收回，UI 应显示路径并把删除/覆盖作为新的显式用户动作。

### 8.7 并发与租约

- 项目允许并发读取，但正式写入使用单写者 lease 和 expected revision；
- 进程退出后通过 owner identity、heartbeat 和项目状态安全回收 stale lease；
- revision 冲突时重新读取任务状态，不能静默覆盖或在语义对象变化后自动 rebase；
- Origin 自动化使用独立全局 lease/队列并串行执行，不与用户 Origin 混用；
- 多个不占 Origin 的只读/临时步骤可在预算允许时并行。

### 8.8 用户体验和审计

确认卡展示语义变化、正式对象和交付位置，不展示每个内部只读调用。任务运行中提供取消；完成结果提供撤销。只有扩大 scope、改变语义、覆盖文件或新增数据披露时再次确认。

每次有副作用的调用记录 task/item、ExecutionGrant、idempotency key、输入/输出 hash、before/after revision、工具 session、side effect、验证结果、取消/超时和操作者。

### 8.9 设计依据

- [NIST：least privilege](https://csrc.nist.gov/glossary/term/least_privilege) 要求只授予完成任务所需的最小资源和权限，对应按任务范围签发 ExecutionGrant。
- [OpenAI《A practical guide to building agents》](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/) 建议按只读/写入、可逆性和影响为工具分级，并对高风险动作设置人工介入。
- [MCP 2025-11-25 Security](https://modelcontextprotocol.io/specification/2025-11-25) 强调用户同意、数据控制、访问控制和工具安全；[MCP Authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) 采用最小 scope、资源绑定和 step-up authorization。
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code/cli-usage) 公开区分 allowed/disallowed tools、permission mode、最大轮次、continue/resume 和详细 trace，说明成熟 Agent 产品把权限、预算、恢复和可观察性作为运行时能力。
- [Stripe Idempotent Requests](https://docs.stripe.com/api/idempotent_requests) 使用 idempotency key 保存首次执行结果并拒绝同 key 不同参数，支持网络失败后的安全重试。
- Garcia-Molina 与 Salem 的 [Sagas](https://www.cs.princeton.edu/research/techreps/598) 将长任务拆成可独立提交的步骤，并在部分执行后用补偿恢复；PlotAgent 采用每 TaskItem 原子提交和不可变版本恢复，而不是持有一个覆盖整轮模型运行的长事务。

PlotAgent 的 TaskIntent 单次集中确认、DataView/Plot 不可变版本、外部导出不可假装自动撤销、Origin 自动化与用户实例隔离，是针对本产品的具体取舍。

### 8.10 当前基线与缺口

当前已有项目 revision、部分 undo/redo、单写者控制、engine staging/readback、Pi abort/generation 和部分 Origin 自动化清理。

仍需统一：

- 与冻结 TaskIntent 绑定的 ExecutionGrant；
- 所有写工具共享的 idempotency key 与 StepReceipt；
- Agent、Core、renderer 和 Origin 的端到端取消状态；
- DataView + Plot + VerificationReport 的 TaskItem 原子提交；
- stale writer/Origin lease 的确定恢复规则；
- 项目 undo 与外部导出边界的统一 UI 和审计。

### 8.11 本项待确认原则

1. P0 只读和 P1 staged 操作自动执行；P2 在 TaskIntent 集中确认后执行；P3 扩权或改变语义再次确认；
2. 用户确认后由 Core 签发绑定任务版本、对象、动作、输出和预算的最小 ExecutionGrant；
3. 每个 TaskItem 独立原子提交，批量任务保留部分成功；
4. 所有写操作使用稳定 idempotency key，并在重试前协调实际结果；
5. 取消和超时端到端传播，但不在数据库/文件原子发布临界区强杀；
6. Origin 只控制可验证属于本任务的自动化实例，绝不终止用户 Origin；
7. 项目撤销通过不可变 revision 恢复，不物理删除历史；
8. 导出先 staged、验证再原子发布，默认不覆盖，外部文件不伪装成可由项目 undo 自动收回；
9. 项目单写者和 Origin 自动化使用可恢复 lease，revision 冲突不静默覆盖；
10. 确认卡只展示语义和正式副作用，内部工具不重复弹窗；所有副作用完整审计。

## 已确认决定日志

### 2026-08-17：回退复杂数据准备流程

- 已确认回退 DataPreparationRecipe、自动候选、发布与复用流程。
- 当前目标是先做好基础单 Agent，不以 Recipe 减少模型调用。
- 回退提交：`c477b34`。
- 回退门禁：Python `610 passed`；TypeScript typecheck、ESLint、Vitest `150 passed`、production build 均通过。

### 2026-08-17：确认 Pi Agent 复用边界

- Pi 只作为通用运行循环、模型调用和工具调度底座。
- 除运行循环外，其余 Agent 产品基础设施均由 PlotAgent 自行设计。
- 不把 Pi 的 messages、events、hooks 或 session ID 误写成已经完成的任务合同、记忆、产品反馈或权限系统。
- 保持 `PiRuntimeAdapter` 边界，使绘图领域合同、项目状态和验证器不依赖 Pi 私有实现。

### 2026-08-17：确认任务合同

- 一条可执行目标对应一个任务，批量目标由同一任务下的多个 TaskItem 表达。
- Agent 可自主检查和临时整理数据，正式项目变更前集中确认一次。
- 技术修复可自动进行；任何语义变化必须生成新任务版本并重新确认。
- 部分成功必须保留，只重试失败项。
- 完成状态以验证器结果为准，不接受 Agent 自述作为完成证据。

### 2026-08-17：确认上下文机制

- Agent 每轮始终获得用户原始指令和当前任务状态。
- 显式选择或本轮附带的数据默认提供包含真实值的轻量预览，Agent 可按需继续读取原始文件和必要范围。
- 小数据允许分页读完；大数据使用 profile、采样和局部读取，但不得阻断解决歧义所需的原始证据。
- 图类合同按需注入，不把全部图类说明常驻上下文。
- 每轮上下文从 PlotAgent 权威状态重建，Pi 聊天历史不是任务状态的唯一真值。
- 程序只按权限、对象和预算机械组装上下文，不做语义路由。
- 上下文压缩不得丢失原始目标、已确认语义、来源、单位、分组、配对和完成证据。

### 2026-08-18：确认工具体系

- 不开放任意代码，提供可组合的类型化工具。
- 原始数据只读，数据操作产生不可变、可链式 DataViewHandle。
- 补齐原始来源检查、关系分析、类型转换、join、去重和显式聚合。
- 预演与正式执行使用同一实现；确认前 staged，确认后按冻结 TaskIntent 提交。
- 增加沙箱渲染、原生读回和局部修正，使 Agent 完成渲染—检查—修正闭环。
- 工具自动返回来源、验证、副作用和结构化错误；技术错误允许自动修复且不占视觉修改次数。
- 工具按 TaskState 与授权阶段暴露，不通过自然语言路由。
- Agent 持续运行到验证和交付完成，不在提交 TaskDraft 后退出。

### 2026-08-18：确认验证器

- 验证器证明已确认语义是否被正确执行，不替用户选择科学语义。
- 验证覆盖任务授权、数据来源、科学执行、Plot 合同、后端读回、产物和视觉七层。
- 所有改变环境的工具完成后自动验证；最终状态和真实产物读回优先于 renderer 自述。
- 请求 OPJU 时必须在新的 Origin 会话中重开并验证原生可编辑性。
- 视觉验证分为机械、Agent 和用户三层；普通任务不要求用户重复验收每个技术步骤。
- VerificationReport 必须结构化并包含 expected、observed、证据和 repair scope。
- 冻结 TaskIntent 内的技术错误由 Agent 自动修；语义变化必须重新确认。
- 只修失败项并保留已通过项，技术预算与视觉修改预算分开。
- 所有必需门禁通过后才标记 `completed_verified`，部分通过只能标记 `partial`。

## 文档更新规则

每确认一项，至少记录：

1. 用户目标与典型示例；
2. 最终产品行为；
3. 模型职责；
4. 程序职责；
5. 数据与状态合同；
6. 失败、追问、取消和恢复行为；
7. 用户可见表现；
8. 验收用例与明确不支持项。

未确认的提案必须保留“待确认”标记；被否决的方案应移入变更记录并说明原因，不能悄悄保留在实现中。
