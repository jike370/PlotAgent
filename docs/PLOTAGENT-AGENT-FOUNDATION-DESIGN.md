# PlotAgent Agent 基础设施设计记录

> 状态：权威决策记录；P0–P10 与 2026-08-19 黑盒后加固均已完成。当前运行时代码为 `a03a04a6bdbba7146ad870da8ed483947076d9a7`；完整机械门禁和本地缺陷定向黑盒通过。旧 `29bfefd` 的 regression suite v2 GO 只保留为历史证据，当前模型服务 HTTP 402 导致新 SEQ-70 为 NO_GO，不能沿用旧 GO 代替当前发布资格。
> 历史起点：`c477b34`，当时回退 DataPreparationRecipe、自动候选、发布与复用流程，恢复基础 Pi Agent。
> 规则：本文件区分“提案”和“已确认”。只有用户明确确认的内容才构成施工依据；每轮讨论结束后必须同步更新本文件。

相关文档：

- [Agent 基础设施施工计划](./PLOTAGENT-AGENT-FOUNDATION-IMPLEMENTATION-PLAN.md)
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
| 2 | 领域说明 | 已确认 | 哪些绘图知识、科学边界和标准案例应提供给 Agent？ |
| 3 | 上下文机制 | 已确认 | Agent 每轮能看到什么，怎样按需读取数据而不淹没上下文？ |
| 4 | 运行循环 | 已确认 | Agent 怎样观察、行动、检查、修复、停止或追问？ |
| 5 | 工具体系 | 已确认 | Agent 需要哪些检查、整理、绘图、读回和交付工具？ |
| 6 | 验证器 | 已确认 | 怎样独立证明数据、科学语义、图形和导出物正确？ |
| 7 | 权限与回滚 | 已确认 | 哪些动作可自动执行，哪些需要确认，失败如何撤销？ |
| 8 | 工作记忆 | 已确认 | 一次任务中应记住哪些决定、结果和失败，哪些不得长期保存？ |
| 9 | 可观察性 | 已确认 | 用户和开发者怎样看到阶段、进度、原因、成本与结果？ |
| 10 | 评测体系 | 已确认 | 怎样证明 Agent 稳定、正确、可恢复，并控制时长和成本？ |

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

### 8.11 已确认原则

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

## 9. 设计项 6：工作记忆

### 9.0 定义与边界

工作记忆不是“把聊天记录长期塞给模型”，而是让同一任务在多轮工具调用、上下文压缩、应用重启和技术重试后仍保持目标、语义、证据和进度一致。

本项只解决任务内连续性和项目内可恢复性。它不负责自动学习用户偏好，不自动把成功流程固化为 Recipe，不把相似历史任务的结论直接套到新任务，也不允许模型把未经确认的猜测写成项目事实。跨任务复用若以后恢复，应作为用户明确创建、可检查、可版本化的项目资产另行设计。

### 9.1 四类记录必须分离

| 层 | 内容 | 权威性 | 生命周期 |
|---|---|---|---|
| Task Ledger | 原始指令、TaskIntent 版本、确认、TaskItem 状态、授权、项目 revision、交付物和验证结论 | 唯一任务真相 | 项目内持久保存，直到项目删除 |
| Task Checkpoint | 当前阶段、已完成/失败项、活跃 handle、预算、下一安全动作和最后事件序号 | 可由 Ledger 重建的运行快照 | 任务运行、暂停和恢复期间保存 |
| Working Notes | Agent 的事实摘记、待验证假设、失败尝试和下一步 | 非权威；必须带类别和证据引用 | 任务结束后清理或压缩成审计摘要 |
| Conversation View | 用户和 Agent 的可见消息、确认卡、进度与结果说明 | 交互记录，不是执行真相 | 本地项目 UX 记录；清空聊天不改变任务/项目状态 |

工具产生的大型表格、图片、完整原生读回和日志不复制进上述文本记录。它们进入有 TTL 的 observation/staging store，工作记忆只保存安全 handle、内容 hash、有界摘要和验证状态；需要时再通过工具按需读取。

### 9.2 必须记住什么

每个活动任务至少保留：

- 用户原始指令原文和后续明确纠正；
- 显式选择的数据源、图、图类、输出位置及其稳定 ID、版本和 hash；
- 已确认的字段绑定、单位、换算、筛选、分组、配对、统计语义、视觉参数和交付范围；
- TaskIntent 每个版本、确认者、确认时间，以及旧版本为何失效；
- 每个 TaskItem 的当前状态、已通过门禁、失败门禁和未完成原因；
- 已调用工具的 StepReceipt、输入/输出 handle、side-effect 状态和验证结果；
- 已尝试但失败的技术方案、结构化错误码、失败作用域和是否允许重试；
- ExecutionGrant、预算、取消状态、project revision 和 lease 信息；
- 最终 DataView、Plot、PNG/SVG/OPJU 等交付物引用及 VerificationReport。

不得长期保存：模型隐藏推理、API key/credential、无界原始工具输出、重复预览副本、临时绝对路径、未经验证的自由文本猜测，以及用户没有明确要求固化的偏好或 Recipe。

### 9.3 记录合同

不对整个产品采用重型 Event Sourcing，只对 Agent 任务使用“小型追加式 TaskEvent 日志 + 当前 TaskCheckpoint 快照”。这样保留恢复和审计能力，同时避免让项目数据、图和 UI 全部被事件流绑架。

`TaskEvent` 至少包含：

```text
task_id / task_item_id
event_seq / event_type / occurred_at
intent_version / intent_hash
project_revision_before / after
tool_call_id / idempotency_key / attempt
input_handles / output_handles / evidence_handles
status / error_code / side_effect
execution_grant_id / actor
```

`TaskCheckpoint` 至少包含：

```text
task_id / checkpoint_version / last_event_seq
original_instruction_hash
active_intent_version / hash
expected_project_revision / execution_grant_id
per_item_state / passed_gates / failed_gates
active_handles / pending_questions
technical_budget / visual_budget / cost_and_time_usage
last_safe_stage / next_safe_action
```

Agent 只能通过类型化的 `record_working_note` 提议临时摘记，类别限定为 `fact`、`hypothesis`、`failed_attempt`、`decision_rationale`、`next_action`。其中 `fact` 必须引用数据或工具证据；`hypothesis` 不能进入 TaskIntent 或验证结论；`decision_rationale` 只保存用户可解释的简短依据，不保存隐藏思维链。Core 校验并写入，模型不能修改历史事件或把 note 提升为授权。

### 9.4 何时写入与检查点

以下边界必须由 Core 原子写事件并刷新 checkpoint：

1. 接收原始指令或用户回答；
2. TaskIntent 创建、确认、作废或生成新版本；
3. 每个工具调用完成、失败、超时或 side-effect 状态未知；
4. 每个验证门禁完成；
5. TaskItem staged、正式提交、部分成功或回滚；
6. 用户取消、应用关闭、进程异常或任务暂停；
7. 交付物发布和任务终止。

不按模型 token、流式片段或每条内部自述写 checkpoint。checkpoint 必须位于可恢复的工具/事务边界，避免“文字说已完成，但对象尚未落盘”的假进度。

### 9.5 上下文恢复与压缩

每轮模型调用由 ContextBuilder 从权威状态重建最小上下文：原始目标、活动 TaskIntent、当前 TaskItem、最近用户纠正、已通过/失败门禁、相关 working notes 和可用 handle。完整历史和大型观察结果不常驻上下文。

模型上下文压缩只影响下一轮输入，不得修改 Task Ledger、TaskEvent 或项目对象。压缩结果必须通过必填字段校验，至少保留原始目标、确认语义、来源、单位、分组、配对、失败尝试、已完成项、未完成项和验证证据引用。缺一项就拒绝该摘要并从 checkpoint 重新组装。

应用或模型 Provider 会话丢失后，从 Core checkpoint 和当前项目 revision 恢复；不得依赖 Pi 的 `messages` 或 Provider `sessionId` 才能继续。同一技术失败已有明确 receipt 时，恢复后的 Agent不能无理由重复相同调用。

### 9.6 生命周期、清理与隐私

- 运行中：原始数据仍由 SourceDataset 管理，memory 只记稳定引用；临时 DataView/Plot/观察结果留在 task staging。
- 暂停或异常：保留 checkpoint、必要 staging 和协调状态，直到用户继续、放弃或达到明确的清理期限。
- 成功结束：保留 Task Ledger、确认语义、正式对象、交付物、VerificationReport 和精简失败审计；删除 working hypotheses、重复预览、临时 OPJU 和无引用 observation。
- 用户放弃：保留最小取消/审计事实，清理 task-owned staging；不得留下会被下一任务误取的临时 handle。
- 删除项目：删除该项目的任务记忆、对话视图和项目内证据引用；外部已交付文件仍按外部文件规则处理。

诊断包不得默认包含聊天、原始指令、列名、单元格值、文件路径、Working Notes 或模型请求/响应。远程模型只获得当前任务授权允许的有界上下文；不会因为“记忆”而扩大数据披露范围。

### 9.7 跨任务和相似任务检索

第一阶段不使用向量相似度自动注入历史任务，也不自动生成“用户偏好记忆”。任务恢复只按 task/project/item/object/version 等确定性键检索。

若用户明确选择“沿用上一张图设置”或选择某个已保存项目资产，Agent 可通过工具读取该对象的正式 spec 和验证记录；这是显式对象引用，不是模糊记忆。未经用户选择的历史假设、失败参数和旧字段映射不能进入新 TaskIntent。

### 9.8 用户可见表现

用户不需要看到“记忆表”。界面只提供：

- 继续任务时显示上次安全阶段、已完成项、失败项和待确认项；
- 任务时间线显示关键确认、执行、验证、部分成功、取消和交付事件；
- 结果页可查看“用了哪些数据、做了哪些确认内变换、生成了什么、哪些门禁通过”；
- 技术失败后说明将从哪个安全点继续，避免表现为从头重做；
- 用户可清空对话、放弃任务或删除项目，并清楚知道各动作影响聊天、任务还是正式产物。

模型的内部工作摘记和隐藏推理不展示；对用户有决策价值的依据应由 Agent 生成单独、简洁、可追溯的说明。

### 9.9 设计依据

- [Anthropic《Effective context engineering for AI agents》](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) 把上下文视为有限资源，推荐 just-in-time retrieval、compaction 和 structured note-taking；对应 PlotAgent 的 handle 按需读取、结构化 checkpoint 与高保真压缩。
- [Anthropic《Effective harnesses for long-running agents》](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) 指出单靠 compaction 不足以支撑长任务，需要跨会话留下明确的进度和可继续工件；对应 PlotAgent 的 Core checkpoint 和正式对象，而不是依赖模型聊天历史。
- [MemGPT](https://arxiv.org/abs/2310.08560) 通过分层记忆管理有限上下文；PlotAgent 同样区分热的任务摘要与冷的 observation/object store，但关键语义采用确定性引用，不让模型自由改写长期事实。
- [Generative Agents](https://arxiv.org/abs/2304.03442) 展示 observation、reflection 和动态检索对长期行为的价值；PlotAgent 借鉴观察与摘记分离，但科研绘图的授权和已确认语义不采用基于相关度的模糊召回。
- [Microsoft Event Sourcing pattern](https://learn.microsoft.com/azure/architecture/patterns/event-sourcing) 说明追加事件可用于审计和状态重建，同时明确该模式复杂且应选择性使用；因此这里只对任务运行采用 TaskEvent + snapshot，不把整个项目改造成 Event Store。
- [OpenAI《A practical guide to building agents》](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/) 将 Agent 定义为模型在工具和 guardrail 下持续执行、判断完成并从失败中恢复；工作记忆为这种恢复提供可验证状态，不把模型自述当完成事实。

### 9.10 当前基线与缺口

当前已有 WorkflowRun、clarification history、TaskPlan/TaskItem 状态、部分 resume、项目 revision，以及前端按项目写入 localStorage 的最多 100 条对话。Pi runtime 每次仍以 `messages=[]` 创建 Agent，`sessionId` 只绑定 workflow run；这恰好说明当前聊天恢复、Provider 会话和任务恢复并不是同一件事。

仍缺少：

- 统一的追加式 TaskEvent 和可校验 TaskCheckpoint；
- Agent 可写但非权威的结构化 Working Notes；
- tool observation 的 handle/TTL/清理策略；
- compaction 前后的必填语义保真校验；
- Provider 会话丢失后的完整任务恢复；
- terminal task 的 scratch 清理和最小审计保留；
- 聊天、任务状态、正式项目对象三者在 UI 和删除行为上的清晰边界。

### 9.11 已确认原则

1. 工作记忆只服务当前任务连续性和项目恢复，不自动学习偏好或生成跨任务 Recipe；
2. Task Ledger、Task Checkpoint、Working Notes 和 Conversation View 分层保存，聊天不是真相；
3. 原始目标、确认语义、对象版本、每项状态、工具 receipt、失败尝试、验证和交付引用必须记住；
4. 隐藏推理、凭证、无界工具输出、临时路径、未确认偏好和自由文本猜测不得长期保存；
5. 只对任务运行使用追加式 TaskEvent + 当前 snapshot，不对整个产品采用重型 Event Sourcing；
6. Agent 只能写分类明确、带证据的临时 note，不能改事件历史、授权或确认语义；
7. 在用户回答、工具结束、验证、提交、取消和交付等安全边界写 checkpoint，不按 token 写假进度；
8. ContextBuilder 从 Core 权威状态恢复；压缩不得改变 Ledger，Provider/Pi 会话丢失不影响继续任务；
9. 任务结束后保留正式事实和精简审计，清理假设、重复预览、临时对象和无引用 observation；
10. 第一阶段只按确定性 ID 恢复，不用相似度自动注入历史任务；用户通过简洁时间线和“继续任务”入口感知记忆，而不是查看内部记忆表。

## 10. 设计项 7：可观察性

### 10.0 目标与边界

可观察性回答三个不同问题：

1. 用户：现在真实在做什么，哪些已经完成，是否需要我操作，失败后怎么办？
2. 开发者：一次任务经过 Pi、模型、Core、工具、renderer、Origin、验证器和存储时，具体在哪一步变慢或出错？
3. 产品与评测：成功率、恢复率、追问、重试、时长和成本是否达到发布标准？

三者必须来自同一条受关联 ID 约束的真实事件链，但采用不同、安全的投影。用户界面不展示工具日志和内部参数；工程 trace 不默认记录提示词、原始数据和工具载荷；评测指标不从聊天文本猜测结果。

### 10.1 四种信号分工

| 信号 | 用途 | 是否持久/完整 | 典型内容 |
|---|---|---|---|
| TaskEvent | 任务进度、恢复、审计和用户时间线的领域事实 | 关键事件不采样，项目内持久 | 状态迁移、确认、工具结果、验证、提交、取消 |
| Trace/Span | 跨组件定位一次运行的执行路径和耗时 | 本地有界保留；可按策略采样 | model turn、tool、renderer、Origin session、verification |
| Metric | 观察总体质量、性能、成本和回归 | 聚合值，不包含用户内容 | 成功率、p50/p95、token、重试、恢复率 |
| Diagnostic Log | 记录离散技术故障和环境信息 | 本地分级、脱敏、有期限 | 稳定错误码、组件版本、进程退出、stack scrub |

TaskEvent 是任务事实；Trace 是技术解释；Metric 是统计；Log 是补充。不能用“日志里好像成功”替代 VerificationReport，也不能为了做产品分析把用户原始内容写进 telemetry。

### 10.2 统一关联模型

每个可观察事件至少携带以下安全标识：

```text
trace_id / span_id / parent_span_id
task_id / task_item_id / workflow_run_id
task_event_seq / attempt
project_id_alias / project_revision
intent_version / execution_grant_id
component / operation / stage / status
started_at / ended_at / duration_ms
error_code / retryable / side_effect
```

根 trace 表示一个用户任务或一次明确恢复；子 span 至少覆盖：

```text
context_build
agent_turn
model_generation
tool_call
data_operation
sandbox_render
matplotlib_render
origin_session / origin_render
verification_gate
project_commit
artifact_export
```

跨 Electron main、Python Core、renderer 进程和 Origin automation 传播同一 trace ID，并为每次调用生成新的 span ID。恢复任务创建新的 run/root span，但用 link 指回原 task trace 和 checkpoint；不能把崩溃后的运行伪装成同一条未中断 span。

### 10.3 用户可见阶段

用户阶段由真实 Core/工具边界事件驱动，不由计时器模拟。基础阶段词汇为：

- 正在整理任务上下文；
- 正在理解要求；
- 正在检查数据；
- 正在准备确认方案；
- 等待确认；
- 正在准备绘图数据；
- 正在调用 Matplotlib；
- 正在调用 Origin；
- 正在验证图形与产物；
- 正在保存项目版本；
- 正在导出文件；
- 已完成 / 部分完成 / 需要输入 / 已阻止 / 已取消 / 失败。

阶段不是硬编码工作流。Agent 可以按任务需要重复检查、渲染和修复；UI 更新时间线和当前活动阶段，并显示“第 2 次验证”之类的 attempt，而不是把循环压成一条假直线。

发送指令后应立即回显用户消息和任务已接收状态。长步骤显示克制的呼吸状态和已持续时间；只有组件真实发出 liveness heartbeat 时才表示仍在运行，heartbeat 不得伪装成进度。

### 10.4 进度与预计时间

只有总量可数且完成定义稳定时使用 determinate progress，例如“10 个 TaskItem 已完成 7 个”“4 个验证门禁通过 3 个”。百分比表示已完成工作单位，不表示模型主观完成度，也不按阶段数量平均分配。

模型推理、未知复杂度的数据探索和 Origin 单图创建默认使用 indeterminate 状态并显示当前阶段。第一阶段不显示虚假 ETA；若以后有足够同版本、同图类、同后端的历史分布，只能显示带置信范围的经验估计，并在任务条件变化后撤销估计。

批量任务同时显示总进度和当前 TaskItem。已成功项不会因后续项失败而退回；进度不能倒退。到达 100% 只代表所有必需门禁和提交完成，不能在 renderer 返回图片时提前显示。

### 10.5 结果、失败与恢复信息

成功结果卡至少显示：

- 完成/部分完成的 TaskItem；
- 正式 plot ID、版本和后端；
- 交付物格式、路径别名、大小和验证状态；
- 使用的数据源和确认内变换摘要；
- 可执行动作：打开、导出、撤销、查看验证记录。

失败或阻止状态必须说明：

```text
失败阶段
稳定错误码和用户可理解原因
影响的 TaskItem/对象
已经成功并保留的内容
项目是否发生正式变更
可自动重试、需要用户输入、需要重新确认或不支持
下一步动作
可复制的 diagnostic_id
```

技术细节默认折叠。不能只显示“Core rejected”“unknown error”“请重试”，也不能在 side-effect 未知时声称“没有任何改变”。恢复后时间线应明确“从验证阶段继续”，不伪装为从头新任务。

### 10.6 成本、时长与预算

一次任务记录：

- 端到端 wall time，以及 Agent、模型、数据工具、Matplotlib、Origin、验证和导出分段耗时；
- 模型调用次数、输入/输出 token、cache hit/miss（Provider 提供时）；
- 实际或估算成本、估价规则版本、未知费用标记；
- 工具调用、技术重试、视觉修复、追问和用户等待次数；
- 每个 TaskItem 的首次成功、最终成功和失败作用域。

用户默认只在任务详情和完成摘要看到总耗时、模型调用/额度消耗与重试；开发模式可展开阶段耗时。
端到端时长当前是观测与发布指标，不设置产品层硬截止；接近模型、Token、工具、Origin 或成本预算时
显示真实警告，达到这些预算后进入可恢复的 `blocked_budget`，不能静默继续消费。

不同 Provider 无法提供可靠价格时只显示 token/调用量和“费用未知”，不得伪造人民币金额。成本指标必须区分计分模型调用、能力探测、缓存命中和本地工具成本。

### 10.7 工程 trace 与诊断

本地 trace viewer 按瀑布图展示 Agent turn、工具、renderer、Origin、验证和提交的父子关系，并允许从 TaskItem 或 diagnostic ID 定位 span。每个 span 只保存低敏元数据、时长、状态、错误码和安全对象别名；模型和工具输入/输出正文默认关闭。

异常路径至少保留：组件版本、协议/schema 版本、退出码、timeout/cancel、重试决定、side-effect、lease/revision 冲突和 scrubbed stack。Origin 记录自动化 session 身份、启动/退出、模板/profile ID、保存/重开阶段，但不记录用户绝对路径或终止无关进程。

出现长时间无结束事件时，监控器可生成 `suspected_stall`，但只能说明“此阶段耗时超过本版本历史阈值”，不能自动判失败。随后若完成，span 正常关闭并记录 stall；若超时，按真实取消/协调结果结束。

### 10.8 指标与发布评测

指标从 TaskEvent、VerificationReport 和 trace 数值字段计算，禁止从自然语言日志分类。最低覆盖：

- task/item verified success、partial、blocked、failed、cancelled；
- 首次通过率、最终通过率、validator reject、自动修复成功率；
- 必要追问率、无效追问率、错误自动绑定率；
- 部分失败保真、失败项恢复、成功项重复执行；
- stale revision 拒绝、重启恢复、幂等重复抑制；
- 各阶段 p50/p95/max、模型 token/调用/成本；
- Matplotlib/Origin/OPJU 的结构与 fresh-reopen 资格结果。

SEQ-70 和黑盒验收应消费相同稳定事件与验证结果，但测试报告仍需独立证据。线上运行指标不能替代正式 UI 黑盒，也不能把未执行项算 PASS。

### 10.9 隐私、留存与上传

默认本地、无后台 telemetry 上传。TaskEvent 和项目审计随项目保存；trace/log 使用独立有界保留策略；Metric 采用低基数聚合。失败 trace 和权限/副作用事件不得被随机采样掉，但其 payload 仍必须脱敏。

默认禁止进入 trace、metric 和 diagnostic log：用户 prompt/聊天、文件名和路径、列名、单元格值、数据预览、模型请求/响应正文、工具正文、API key、credential 和原生项目内容。只记录 ID、hash、大小、计数、类型、阶段和稳定错误码。

生成诊断包时必须本地预览、明确列出文件、再次征得用户同意；上传是新的 P3 数据披露授权。开发者临时启用敏感 payload tracing 时使用独立开发环境、明显警告和自动过期，不能成为发布默认值。

### 10.10 无障碍与交互约束

- 当前阶段使用 `role=status`/礼貌 live region；错误使用 alert，但避免每个 heartbeat 重复播报；
- 状态变化依靠文本和图标，不只依靠颜色或动画；
- `prefers-reduced-motion` 下取消呼吸和位移动画；
- 任务运行时始终提供可发现的取消入口，进入不可中断的短提交区时说明“正在完成安全保存”；
- 历史阶段默认折叠，当前阶段、用户需要操作和失败原因保持可见；
- 多任务并行时对话显示当前任务，任务中心汇总全部任务，二者消费同一 TaskEvent projection。

### 10.11 设计依据

- [OpenTelemetry Observability Primer](https://opentelemetry.io/docs/concepts/observability-primer/) 区分 trace、span、metric 和 log，并强调使用 trace/span 关联离散事件；对应 PlotAgent 的四类信号分工。
- [OpenTelemetry Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/) 将 span 定义为带父子关系、时间、属性、事件和状态的工作单元；对应任务根 trace 与 model/tool/renderer/verification 子 span。
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) 标准化跨组件传播 trace ID 和 parent ID；对应 Electron、Core、renderer 与 Origin automation 之间的关联标识。
- [OpenAI Agents SDK Tracing](https://openai.github.io/openai-agents-python/tracing/) 覆盖 agent、turn、generation、tool、guardrail 和 custom span，并明确敏感输入/输出需可关闭；PlotAgent 采用同类层级，但默认仅本地和 payload-off。
- [Windows Progress Controls](https://learn.microsoft.com/windows/apps/develop/ui/controls/progress-controls) 区分可计算总量的 determinate progress 与未知时长的 indeterminate progress，并要求配合文字说明；对应不伪造百分比和 ETA。
- [Microsoft Visual Studio progress guidance](https://learn.microsoft.com/visualstudio/extensibility/ux-guidelines/notifications-and-progress-for-visual-studio) 要求 determinate 进度只在任务有稳定边界时使用、完成前不达到 100%，长任务可同时展示总体和当前步骤；对应批量 TaskItem 进度。
- 现有 [本地安全诊断规范](./LOCAL-SECURITY-DIAGNOSTICS.md) 已明确禁止 prompt、聊天、路径、列名、单元格和 credential 进入默认诊断；本设计沿用这一产品隐私边界。

### 10.12 当前基线与缺口

当前已有 TaskEvent sequence/state/progress、Pi lifecycle stage、部分 Agent/Core/renderer 状态文案、任务中心、Workflow tool audit、模型 token/cost 字段、OPJU 明确进度与完成提示，以及本地诊断脱敏规范。

仍缺少：

- TaskEvent、TraceSpan、Metric 和 DiagnosticLog 的统一关联合同；
- 跨 Electron、Python Core、renderer 和 Origin 的 trace/span 传播；
- 用户阶段到真实工具/验证事件的一对一投影和 attempt 表达；
- 分项进度、部分成功、恢复点和 side-effect 的统一结果卡；
- 端到端分段耗时、token/cost/budget 的一致统计；
- 本地 trace viewer 和 diagnostic ID 定位；
- stall、cancel、timeout、resume 和 revision conflict 的完整 trace；
- 由相同事件生成的 SEQ-70、发布门禁和黑盒证据索引。

### 10.13 已确认原则

1. 用户状态、工程 trace、聚合指标和诊断日志来自同一真实事件链，但使用不同安全投影；
2. TaskEvent 是任务事实，Trace 解释执行路径，Metric 做统计，Log 只补充故障，彼此不得冒充；
3. 一个任务对应根 trace，Pi、模型、Core、工具、renderer、Origin、验证、提交和导出使用关联 span；
4. 用户阶段只由真实事件驱动，允许循环和 attempt，不用计时器伪造 Agent 行为；
5. 只有总量可数时显示 determinate progress，未知工作使用阶段+持续时间，不伪造百分比或 ETA；
6. 失败必须说明阶段、原因、影响范围、已保留结果、副作用、恢复动作和 diagnostic ID；
7. 记录端到端及分段时长、模型调用/token/成本、重试和预算；未知价格不得伪造费用；
8. 指标由结构化事件和验证报告计算，SEQ-70、发布门禁和黑盒仍保留独立证据要求；
9. 默认本地、payload-off、无后台 telemetry 上传；诊断上传属于新的 P3 数据披露授权；
10. UI 使用可访问的真实状态、取消、部分成功和恢复反馈，用户无需阅读内部 trace 才知道发生了什么。

## 11. 设计项 8：评测体系

> 状态：已确认。本节构成后续施工与发布验收依据。

### 11.0 评测对象与基本原则

PlotAgent 的评测对象不是孤立的语言模型，也不是一段聊天答案，而是实际运行的完整系统：模型、Pi 运行循环、PlotAgent 上下文与工具、任务合同、权限、Core、数据处理、renderer、验证器、Windows 桌面环境、Origin 和文件系统共同产生的真实结果。

运行时验证器回答“这一次任务是否正确完成”；评测体系回答“这一版本在一组代表性任务上是否稳定、是否可发布”。二者不得互相替代。

评测以真实环境中的状态和产物为准，不以 Agent 自述、提示词匹配或某条固定工具轨迹为准。只有安全协议要求固定行为时，才把轨迹纳入门禁，例如确认前不得正式写入、越权工具不得被调用、已成功项目不得重复执行。

### 11.1 七层评测结构

评测按成本从低到高分成七层；低成本层先运行，但高成本层不能被低成本层替代：

| 层级 | 评测内容 | 主要证明 |
|---|---|---|
| E0 合同与静态检查 | Schema、codegen、类型、lint、能力注册、权限表和打包清单 | 接口与声明没有漂移 |
| E1 确定性单元与性质测试 | 导入、数据工具、编译器、验证器、幂等、版本和错误分类 | 程序部件在给定输入下正确 |
| E2 集成与运行时测试 | Pi adapter、Core、工具、TaskState、取消、恢复、fake provider | Agent 基础设施闭环可运行 |
| E3 真实模型 Agent 行为 | 真实指令、多轮追问、工具选择、修复、成本与延迟 | 模型在产品约束下能稳定完成任务 |
| E4 引擎与产物资格 | 34 图、Matplotlib、Origin、PNG/SVG/OPJU、fresh reopen | 图形语义、原生结构与可编辑交付达标 |
| E5 正式 Windows Electron 黑盒 | 用户可见导入、对话、确认、任务、撤销、重启和导出 | 产品从真实 UI 入口可用 |
| E6 发布与非功能 | 打包、启动、性能、资源、隐私、安全、恢复和兼容环境 | 构建具备交付条件 |

### 11.2 EvalCase：一条评测用例的合同

每条正式用例都必须是版本化的 `EvalCase`，至少冻结：

- `eval_case_id`、suite 版本和要证明的单一 claim；
- suite 类型：regression、capability、safety、recovery 或 exploratory；
- 用户指令和 locale；
- 输入 fixture manifest、原始文件 hash、初始项目状态和环境；
- 用户显式选择的数据、图类、对象与权限；
- 模型、provider、Pi、系统提示、工具 Schema、EngineProfile 和 renderer 版本；
- token、时间、轮次、工具调用、修复和副作用预算；
- 必须出现的结果与不变量；
- 明确禁止出现的结果；
- grader、证据要求、trial 策略和是否阻断发布；
- 必要时保存参考解或参考产物，但不得把答案泄露给 Agent。

claim 必须窄而明确，例如“清晰 CSV 在正式 UI 中能创建一张原生可编辑的 K08 OPJU”，不能只写“绘图成功”。Agent 不得看到 grader 答案、参考解、其他 trial 结果或 holdout 标签。

### 11.3 五类 suite 分开管理

1. **Regression suite**：冻结已经承诺的能力和真实缺陷复现。目标接近全绿，每个已确认产品缺陷都必须新增回归用例；不能为了恢复通过率删除失败项。
2. **Capability suite**：测尚在爬坡的新能力，可以保留失败，用于比较方案和扩大边界；只有达到冻结标准后才晋升为发布回归。
3. **Safety/permission suite**：同时测试允许与拒绝。既要证明合法操作能做，也要证明越权、覆盖、错误对象和未确认正式写入不会发生。
4. **Recovery/chaos suite**：注入模型、工具、Core、Electron、Origin、磁盘、revision、lease、预算、超时和取消故障，证明部分成功保留且任务可恢复。
5. **Exploratory/human suite**：测试者只获得产品功能说明，自行设计路径；发现的可复现问题进入冻结回归。探索结果不能直接改写原 regression 的既定判据。

### 11.4 Grader 层级与边界

grader 优先级固定为：**确定性结果检查 > 结构化 trace 检查 > 模型 grader > 人工审查**。

- 数据值、来源、项目版本、对象 ID、PlotSpec、文件 hash、Origin 原生结构和 fresh reopen 使用确定性 grader；
- 只有确认前无副作用、禁止越权、成功项不重复执行等协议要求使用 trace grader；
- 模型 grader 只承担难以机械量化的指令遵循和视觉初筛，rubric 必须单一、允许 `UNKNOWN`，并用人工样本校准；
- 人工审查用于最终视觉、交互体验和专业领域判断。

评测主要检查结果，不要求模型复制某一条参考工具序列。不同的合法路线可以通过；但模型 grader 绝不能成为科学语义、数据值或 Origin 原生结构的唯一发布门禁。

### 11.5 非确定性与重复运行

- 确定性测试必须可精确重复；真实模型评测在运行前冻结 trial 数，不得失败后选择性重跑来“洗掉”失败；
- 报告保留原始 `通过次数/总次数`，不只给平均分；
- regression 和 safety 关注 `pass^k` 一致性，即关键任务每次都成功；
- capability 同时报告 pass@1、任务成功分布、置信区间、延迟和成本；
- 当前 SEQ-70 的 24×3 可作为旧架构的阶段基线，但新 TaskContract、工具和完成语义落地后必须升 suite 版本，旧 72 次结果不能自动继承；
- 3 次重复只能证明发布一致性门槛，不能被表述为“99.9% 可靠”；
- 模型、provider、API 版本、系统提示、工具 Schema、Pi 版本、采样参数、预算和缓存策略任一关键项变化，都触发相应重评。

### 11.6 隔离、fixture 与数据集划分

每个 trial 使用新项目、新输出目录和干净的进程状态；聊天、working notes、staging、Origin 会话、输出文件和缓存默认不跨 trial 共享，除非该用例明确就是测试恢复或缓存。输入 fixture 测试前后必须 hash 一致。

评测数据分成：

- 可反复调试的 development set；
- 发布使用的 frozen regression set；
- 不参与日常调参的 holdout set；
- 由真实线上/黑盒缺陷沉淀的 bug set。

用例必须同时包含正向与反向行为：信息明确时不得追问；真正缺少语义时必须追问；授权允许时必须完成；授权不足时必须拒绝或请求扩权。

### 11.7 PlotAgent 专属覆盖矩阵

Agent 行为至少覆盖：

- 单图、批量分别绘图、多数据同图和混合任务；
- 用户先选图、自然语言明确图类、自然语言含糊图类；
- CSV、多 sheet Excel、含仪器信息的 TXT，以及不同表头、列序、单位和缺失值；
- 原始数据检查、筛选、排序、类型转换、单位换算、join、去重和显式聚合；
- 必填绑定、repeatable series、分组、配对、误差、阈值和视觉参数；
- 必要追问、用户修正、重新确认和拒绝越权；
- 确认前无正式副作用、部分成功、只重试失败项、幂等、取消、恢复、stale revision 和预算耗尽；
- PNG、SVG、OPJU、可编辑性、项目 undo 和导出完成反馈。

每个正式图类至少有 minimal、representative、edge/error 三类数据，覆盖 default、edited、dynamic 三态；适用时同时覆盖 Matplotlib 和 Origin。已删除图类也要有 tombstone 用例，证明 UI、合同、Agent 和文档不会重新暴露它们。

### 11.8 性质测试与蜕变测试

除了固定答案，还要验证在合法变换下应保持的关系：

- 增加未使用列，不改变已有图的语义与几何；
- 在稳定字段 ID 和绑定不变时调整物理列序，结果等价；
- 增加数据行或系列时，对象数、源绑定和图例按图类合同变化，不能残留旧对象；
- 单位换算后物理量几何等价，列值与轴单位同步更新；
- 批量 TaskItem 调整执行顺序，不改变数据—图形对应关系；
- 相同 idempotency key 不产生重复项目版本或重复导出；
- Matplotlib 与 Origin 比较共同语义和数据来源，不做逐像素相等；
- 配对图、线序列等顺序敏感数据不得被静默排序。

这些关系必须来自 EngineProfile、图类合同或工具合同，不能由一个“通用绘图规则”猜测所有图形。

### 11.9 图形、视觉与 Origin 资格

图形资格分成三个相互独立的门：

1. 机械合同：数据、绑定、对象数、参数和导出文件正确；
2. 后端持久化：Origin 原生对象读回、保存、全新会话重开和可编辑；
3. 人工视觉：默认态、编辑态和动态态在代表数据上视觉可接受。

视觉 golden 不能替代 Origin 原生结构读回；原生结构通过也不能替代人工视觉签名。所有证据必须绑定 source digest、EngineProfile、renderer、Origin 模板、fixture、Origin 版本和 git commit。

变化影响规则：

- 单图专属 renderer 改动：重测该图全部状态、双后端和同家族代表图；
- shared resolver、数据、视觉、导出或 Origin 基础设施改动：重测所有受影响图；无法可靠判定影响时跑完整 34 图；
- Origin 版本或模板变化：完整 Origin live + fresh reopen；
- 发布里程碑：重新生成当前 34 图库存与证据 manifest。

### 11.10 正式 Windows UI 黑盒

冻结回归与探索性黑盒必须分开：

- 冻结回归按版本化用例执行，证明既有承诺没有回退；
- 探索性测试者只获得用户可见功能说明，不读取源码、内部接口、历史缺陷答案或冻结脚本，自行设计使用路径。

正式黑盒必须使用 Electron 正式入口、冻结 commit、全新项目和独立输出目录。只有实际 UI 观察和真实产物可以记为 PASS；单测、源码分析、静态审计页或口头说明不能补黑盒证据。截图必须能识别项目、数据表、图类和结果上下文。证据不足就记 `UNVERIFIED`，不得推定通过。

覆盖导入、聊天、确认卡、真实阶段反馈、追问、批量、部分成功、取消、撤销、重启恢复、导出、Origin 不可用、错误恢复和键盘/可访问性。

### 11.11 状态与重跑纪律

正式状态只有：

- `PASS`：claim 和全部证据门满足；
- `FAIL`：观察到产品行为违反 claim；
- `BLOCKED`：外部环境或权限阻止执行，未观察到产品结果；
- `UNVERIFIED`：执行或证据不足，不能证明通过或失败；
- `EVAL_INVALID`：评测器、fixture、grader 或聚合本身无效。

BLOCKED 和 UNVERIFIED 不是产品 FAIL，但对强制发布用例同样不能贡献 GO。已知且在声明范围内的问题必须记 FAIL，不能用 xfail 掩盖。

产品修复后使用新 run ID 重跑；不得删除旧失败 trial。环境恢复重试保留原 trial。若聚合器崩溃，只能从不可变原始 trial 做有记录的重新聚合，不得修改 trial 内容。

### 11.12 发布门槛

一次 GO 必须同时满足：

- 所有测试针对同一冻结、干净 commit，依赖、模型、Origin、fixture 和 manifest 已记录；
- E0–E2 确定性门禁 100% 通过；
- 权限、安全、数据不可变和副作用用例全部 trial 通过；
- Agent 冻结 regression 达到版本化门槛，关键任务 3/3；错误自动绑定、无效追问、成功项重复执行为 0；
- 34 图机械资格完成，受影响视觉完成签名，代表 OPJU 通过 live 与 fresh reopen；
- 正式 UI 必测项没有 FAIL、BLOCKED 或 UNVERIFIED；
- 取消、内存、token 和成本满足已冻结的安全/资源预算；端到端延迟当前只记录和比较，不设 GO/NO-GO 硬阈值；
- 打包、启动、重启、清理、隐私、安全和诊断链通过。

阈值写在版本化 `EvalPolicy` 和 run manifest 中，不能在看到结果后调整。GO 报告必须陈述被证明的精确 claim、环境和仍未覆盖范围，不能笼统写“产品完全可用”。已知问题只有明确位于发布声明范围之外才能保留；不能因测试失败临时缩小范围。

### 11.13 变更影响与运行频率

| 变更 | 最低重测范围 |
|---|---|
| 模型、provider、Pi、系统指令 | Agent regression、安全、成本与延迟 |
| 工具、TaskContract、权限、记忆 | 相关 Agent 用例、E0–E3、恢复与安全 |
| 图类 profile 或专属 renderer | 该图全部状态/后端/导出 + 家族代表 |
| shared renderer、数据或视觉层 | 全部受影响图；影响不明时完整 34 图 |
| Origin 版本、模板或自动化 | 完整 Origin live + fresh reopen |
| UI | 受影响黑盒 + 主链 smoke + 可访问性 |
| 存储、revision、lease、打包 | 恢复、并发、安装、重启和完整 UI 主链 |

每次提交运行 E0–E2 与影响集；每日或候选节点运行真实模型子集；发布候选运行完整多 trial Agent、图形资格、正式 UI 和 E6。

### 11.14 性能与成本报告

性能必须区分 cold/warm、数据规模、图类、后端、Origin fresh reopen 和缓存命中。每组报告 median、p95、max、失败数和超时数；样本量很小时同时列出全部原始值，不能只报 p95。

只有环境、模型、数据、预算和缓存策略相同的运行才可直接比较。决策优先级固定为：正确性与安全 > 恢复能力 > 时长 > 成本；不能为了降低 token 或耗时把语义判断重新塞回关键词路由。

### 11.15 评测产物

一次正式运行至少产出：

- `run-metadata.json`；
- `fixture-manifest.json`；
- `eval-policy.json`；
- `case-results.csv` 和 `report.json`；
- `REPORT.md` 与可选 `index.html`；
- 每个 case/trial 的 trace、evidence、exports 和 failure 记录。

报告必须保留 case/trial 粒度，记录环境、commit、模型、预算、grader、恢复动作、最终状态和失败原因，不能只保留一个总分。构建目录可被 gitignore，但发布证据需按 hash 归档为不可变产物。

### 11.16 设计参考

本提案参考：

- Anthropic 对 Agent eval 的 task、trial、grader、harness、outcome/trajectory、pass@k/pass^k 和多次运行划分：[Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)；
- OpenAI 对可信第三方评测中 claim、环境、证据与可复核性的要求：[Trustworthy third-party evaluations](https://openai.com/index/trustworthy-third-party-evaluations-foundations/)；
- AgentBench 对多轮 Agent 在交互环境中的评估方式：[AgentBench](https://arxiv.org/abs/2308.03688)；
- METR 对开发集/测试集、重复运行、置信度和评测故障来源的协议化记录：[Example evaluation protocol](https://evaluations.metr.org/example-protocol/)；
- 蜕变测试通过输入变换与输出关系发现无单一 oracle 问题：[Metamorphic Testing](https://arxiv.org/abs/1804.11121)；
- Origin 项目文件作为图、数据和分析对象的原生容器：[Origin Project File](https://docs.originlab.com/origin-help/origin-project-file/)。

这些参考提供评测方法，不替 PlotAgent 决定图形语义、发布范围或用户体验。

### 11.17 当前基础与缺口

项目已有可复用基础：较完整的 Python/TypeScript 测试、EngineProfile 和 renderer qualification、34 图发布矩阵、Origin fresh reopen、Windows UI 黑盒、性能记录，以及旧 SEQ-70 24×3 真实模型评测。

仍缺少统一的新架构 `EvalCase` Schema、suite 分类、fixture/holdout 划分、grader 边界与校准、TaskEvent/trace/证据统一关联、合同驱动的蜕变测试、变更影响选择器、`EVAL_INVALID` 与评测器恢复规范，以及以明确 claim 为中心的发布决策。旧评测产物可作历史基线，但不能替代这些新合同。

### 11.18 已确认原则

1. 评测完整产品和真实结果，不把模型答案或 Agent 自述当作成功；
2. 使用 E0–E6 七层门禁，低层不能替代真实模型、Origin 或正式 UI；
3. 每个 EvalCase 冻结 claim、环境、输入、预期、禁止结果、grader、trial 和参考；
4. regression、capability、safety、recovery、exploratory 分开管理；
5. grader 优先确定性结果，trace 只检查必要协议，模型 grader 经校准且不独占科学/结构判定；
6. 多 trial 策略运行前冻结，关键 regression 要求全部通过，保留所有失败；
7. trial 相互隔离，使用 development、frozen regression、holdout 和真实 bug 集；
8. 性质测试由图类/工具合同定义，双后端比较语义与原生结构，不做逐像素相等；
9. 状态严格使用 PASS、FAIL、BLOCKED、UNVERIFIED、EVAL_INVALID，强制用例的任何非 PASS 都不能支持 GO；
10. 发布必须在同一冻结 commit 上同时关闭 Agent 多 trial、34 图资格、正式 UI、性能、安全与可追溯性。

## 12. 设计项 2：领域说明

> 状态：已确认。本节构成后续施工与验收依据。

### 12.0 领域说明解决什么问题

领域说明是 PlotAgent 提供给模型的、版本化且可追溯的绘图知识。它让模型知道产品承诺的图类、数据合同、科学语义、公共动作和边界，而不是让模型依赖训练记忆猜 Origin、猜列角色或猜 renderer 行为。

领域说明不是：

- 一份把 34 张图全部塞进 system prompt 的百科；
- 由程序通过关键词或正则替模型选择图类的路由表；
- renderer 的 LabTalk、Origin C、Matplotlib artist 或对象编号说明；
- 固定执行步骤的 Recipe；
- 用户偏好记忆；
- 可以覆盖真实数据、TaskContract、工具返回或验证结果的“提示词真相”。

它的职责是提供可用知识与明确边界。模型仍负责理解用户意图、选择图类、判断字段语义和决定是否追问；程序负责按权限取回知识、保证版本一致，并用同一领域合同做确定性校验。

### 12.1 知识权威顺序

发生冲突时按以下顺序处理：

1. **程序领域合同**：EngineProfile、数据/计算合同、公共动作 Schema、验证规则，是产品可执行能力的唯一真值；
2. **经审查的领域知识卡**：解释用途、语义、正反例和边界，必须绑定上述合同版本；
3. **本机目标版本与官方资料**：Origin 官方帮助、本机菜单 dispatcher、模板资产和版本化 readback，用于证明后端事实；
4. **当前任务事实**：用户原始指令、显式选择、真实数据和工具观察；
5. **模型先验知识**：只能形成待验证假设，不能覆盖前四项或直接作为完成证据。

用户可以选择图类、字段、单位、计算定义和视觉偏好；但如果要求违反图类硬合同、产品安全边界或数学不变量，Agent 必须解释冲突并追问或报告不支持，不能静默修改合同。

### 12.2 六层领域知识

领域说明拆成六层，按任务需要组合：

| 层 | 内容 | 注入策略 |
|---|---|---|
| D0 Agent constitution | 职责、数据不可信、必须用工具、不得猜完成、何时追问 | 每轮常驻，保持短小 |
| D1 通用绘图语义 | 来源、单位、wide/long/matrix、缺失、分组、配对、误差、顺序和聚合边界 | 任务开始提供摘要，相关时展开 |
| D2 ChartKnowledgeCard | 单个图类的用途、数据合同、对象、固定语义、允许/禁止处理、正反例 | 用户选择或模型候选确定后按需注入 |
| D3 CalculationContract | 统计量、公式、参数、缺失值、边界条件和版本 | 只有图类或用户请求涉及计算时注入 |
| D4 Tool/Action contract | 工具参数、返回、错误、副作用、公共视觉动作 | 由当前阶段真实 Schema 暴露 |
| D5 Evidence/example | 最小例、代表例、反例、近似但不同的图类对照和官方依据 | Agent 请求或歧义需要时提供 |

D0 不能承载具体图类清单；D2/D3 不得常驻全部上下文；D4 不能靠自由文本复制，必须来自实际工具 Schema。

### 12.3 通用绘图语义 D1

D1 只记录跨图类稳定的原则：

- 原始来源只读，任何整理结果保留 lineage；
- 列名、单位、类型、值分布和仪器元数据都是证据，不等于用户意图；
- 选择列、单位换算、排序、筛选、聚合和 join 都是显式语义动作，不得静默发生；
- wide、long、matrix、paired、grouped 和 repeated-measure 具有不同结构含义；
- 缺失值、重复键、顺序、类别顺序和时区必须显式处理；
- error、lower/upper、confidence interval、SD、SE 等不能只凭数值形状互换；
- 配对图、线序列、时间序列等顺序敏感数据不得由通用清洗自动排序；
- renderer 需要的物理表结构不等于用户数据的科学语义，数据整理与字段绑定必须分开记录。

D1 不给出“列名含 time 就绑定 X”之类规则，也不规定某个自然语言短语对应哪个图类。

### 12.4 ChartKnowledgeCard 合同

每个正式图类对应一个版本化 `ChartKnowledgeCard`，建议至少包含：

```text
profile_id / knowledge_version / engine_profile_version
display_name_zh / official_name / user_facing_description
intended_questions / unsuitable_questions
source_shapes / required_roles / optional_roles / repeatable_roles
field_type_constraints / row_relations / ordering_semantics
fixed_scientific_semantics / user_selectable_semantics
allowed_preparations / forbidden_preparations
semantic_objects / public_actions / unsupported_actions
minimal_example / representative_example / counterexamples
validation_claims / evidence_refs / reviewed_origin_version
```

其中：

- `intended_questions` 描述该图回答什么问题，不是关键词列表；
- `required_roles` 等结构字段从 EngineProfile/Renderer Data Contract 生成或交叉校验，不能维护第二份漂移真值；
- `fixed_scientific_semantics` 记录不可被样式编辑改变的含义；
- `allowed_preparations` 只说明哪些数据变换在该图语义下可能合法，真正执行仍需 Agent 依据任务决定；
- `forbidden_preparations` 明确禁止排序、预聚合、转置、归一化或复制边界等会改变含义的行为；
- `semantic_objects` 使用 `plot`、`x_axis`、`series_1` 等公共对象，不暴露 Origin plot index；
- `validation_claims` 与验证器使用同一 claim ID，使模型说明、执行合同和机械门禁能互相追溯。

### 12.5 CalculationContract：科学计算不能藏在散文中

涉及直方分箱、核密度、箱线须、置信区间、累计百分比、混淆矩阵计数等计算时，必须有独立、版本化的 `CalculationContract`：

- 输入角色与允许类型；
- 公式或算法名称与精确定义；
- 参数、默认值和可编辑范围；
- 缺失值、零、负值、重复和小样本行为；
- 输出列、单位和 lineage；
- Matplotlib 与 Origin 需要保持的共同语义；
- 验证 oracle 和边界用例。

Agent 可以根据用户明确要求选择合同或请求参数，但不能自行发明统计定义。renderer 也不能把后端默认值冒充产品科学定义。

### 12.6 按需检索，不做隐藏语义路由

领域知识通过显式工具访问，例如：

- `list_chart_catalog`：返回产品支持图类的用户可见名称和一句话用途；
- `get_chart_knowledge(profile_id)`：返回指定 ChartKnowledgeCard；
- `compare_chart_profiles(profile_ids)`：返回数据要求、语义和边界的结构化差异；
- `get_calculation_contract(contract_id)`：返回相关计算合同；
- `get_domain_example(profile_id, example_id)`：返回审查过的正例或反例。

用户已选择图类时，ContextBuilder 直接注入该卡；用户只用自然语言描述图类时，模型先读取目录，必要时比较候选，再作选择或追问。程序只执行 ID、权限和版本过滤，不根据关键词、列名或正则替模型决定候选与最终图类。

如果模型请求不存在或未审查的图类知识，系统稳定返回 `DOMAIN_KNOWLEDGE_UNAVAILABLE`；Agent 不得退回训练记忆伪装成产品支持。

### 12.7 示例怎样设计

示例的作用是展示合同，不是教模型背固定列名。每个图类优先保留四类：

1. **minimal positive**：最小合法结构；
2. **representative positive**：真实数量级、单位、分组和可选角色；
3. **near-miss counterexample**：外观相近但应选择另一图类或需要追问；
4. **invalid example**：明确违反类型、行关系或科学不变量。

示例字段使用语义名称并说明为什么合法/不合法；不得把 `column_1`、固定位置或某个 fixture 文件名写成通用规则。示例中来自文件的文本仍按不可信数据处理，不能携带可执行指令。

### 12.8 后端知识与 Agent 公共语义隔离

Agent 默认只学习 Matplotlib 与 Origin 共同的公共语义：标题、轴、系列、颜色、线、符号、图例、注释和图类参数。以下内容属于 renderer/验证器知识，不应进入普通 Agent 上下文：

- Origin 模板绝对路径、LabTalk/Origin C 命令、PID、layer index、Theme 节点；
- Matplotlib artist、Axes、Line2D、Collection 等对象结构；
- 模板修复、fresh reopen 自动化和后端私有重建策略。

只有诊断工具内部可以使用后端知识，并把结果投影为公共对象和结构化验证报告。这样既能保持 Agent 工具稳定，也能更换 renderer 实现而不重写模型知识。

### 12.9 领域知识的来源、版本与审核

每张知识卡必须记录：

- 负责的产品合同版本；
- 官方帮助 URL、页面标题和审查日期；
- 本机目标 Origin 版本、菜单入口、模板 identity 或实证引用；
- 领域 reviewer、review 状态和最后一次变更原因；
- 与 EngineProfile、CalculationContract 和验证 claim 的一致性检查结果。

普通任务运行时不实时浏览互联网，也不把未审查网页直接注入模型。官方资料先进入离线研究与人工审核，再发布为版本化知识卡。Origin 官方说明数据选择与列 designation 会决定绘图语义，模板再控制图类和外观，因此领域卡必须同时保存数据要求与图类事实，不能只保存一张参考图。

知识卡变化视为产品行为变化：需要 code review、合同一致性测试、受影响 Agent regression 和图形资格。单纯修改解释文字也要确认没有扩大已支持范围。

### 12.10 用户知识、冲突与追问

用户在当前任务中的明确说明，例如“第三列是标准误”“每行是同一个受试者”“不要排序”，高于模型先验和示例，但不会自动修改全局领域合同。

冲突处理：

- 用户说明与数据证据一致且合同允许：记录进 TaskIntent；
- 数据不足以验证但合同允许：向用户展示假设并确认；
- 用户说明与数据观测冲突：指出具体列和值的冲突并追问；
- 用户要求违反图类硬合同：解释原因，建议合法替代或报告不支持；
- 用户提供新的专业定义：只在当前任务中作为显式参数使用，除非经过产品审核成为新 CalculationContract。

Agent 不得为了少问一次而把示例中的常见做法套到当前数据，也不得把用户一次选择保存成跨任务默认偏好。

### 12.11 程序与模型的职责

模型负责：

- 读取相关知识卡和真实数据；
- 理解用户想回答的问题；
- 比较候选图类；
- 判断字段语义和必要的数据操作；
- 识别合同内的歧义并追问；
- 把自然语言转为 TaskIntent 和公共动作。

程序负责：

- 保存、版本化和按权限提供知识；
- 从当前真实 EngineProfile/工具 Schema 构造结构字段；
- 校验知识卡引用、版本和完整性；
- 限制上下文预算并防止未授权数据披露；
- 以同一合同验证 TaskIntent、数据视图和 renderer 结果；
- 在知识缺失、过期或冲突时 fail closed。

程序不得读取用户自然语言后自行选择知识卡、图类、字段或数据操作。模型也不得修改卡片、合同、验证规则或支持范围。

### 12.12 用户可见表现

领域说明大部分是内部基础设施，但用户应能看到它带来的结果：

- 图形库显示准确的中文图类名、官方名称、用途和数据要求；
- Agent 说明建议图类的理由，而不是只输出代号；
- 映射确认卡显示字段角色、样本值、单位和关键图类约束；
- 追问指出缺少的具体语义，例如“上下界还是对称误差”，而不是泛化地要求补充信息；
- 不支持时说明是数据不满足、图类不支持该参数，还是产品没有该能力；
- 必要时允许用户展开“为什么这样判断”，显示所依据的数据事实和产品合同摘要，而不是隐藏推理。

不向普通用户展示 Origin PID、模板 hash、内部 claim ID 或 renderer 命令。

### 12.13 当前实现差距

当前 `_system_prompt()` 只为候选 profile 注入 required/optional/repeatable roles、对象别名和视觉 operation；`EngineProfile` 本身也主要声明角色、对象和 capability。项目虽然已有 Origin Recipe、官方 URL、图类研究、renderer 特殊语义和大量测试，但这些信息分散且没有形成可按需检索、与合同版本绑定的领域知识层。

因此后续施工需要：

1. 定义 `ChartKnowledgeCard` 与 `CalculationContract` Schema；
2. 以现有 34 个 EngineProfile 为库存建立完整卡片，不从旧 renderer 猜语义；
3. 将官方研究、本机模板实证和用户已签名视觉结果绑定为 evidence refs；
4. 增加 catalog/get/compare/example 只读工具；
5. 让 ContextBuilder 按选择和模型请求注入，而不是扩大 system prompt；
6. 增加知识—EngineProfile—验证 claim 一致性门禁；
7. 删除 system prompt 中会重复或漂移的图类散文，只保留 D0 constitution。

### 12.14 验收用例

- 34 个正式图类均有通过 Schema 和引用完整性检查的知识卡；
- required/optional/repeatable roles、对象和 actions 与 EngineProfile 无漂移；
- 图类硬科学语义与验证 claim 一一对应；
- 用户已选图时只注入对应卡，不加载 34 图全文；
- 自然语言未选图时，模型可读取目录、比较候选并追问，程序不做关键词路由；
- 图类近似对照用例能区分浮动柱/浮动条、线序列/普通折线、箱线/列散点等已知高风险组合；
- 用户指定字段语义时能覆盖示例惯例但不能突破硬合同；
- 官方资料与本机版本冲突时显示版本化事实，不静默采用网页最新行为；
- 数据单元格、仪器元数据和外部文档中的指令不会被当作系统说明；
- 知识缺失、版本不匹配或合同冲突稳定失败，不以模型记忆继续；
- context trace 能证明实际注入了哪些知识版本，且不泄露未授权数据；
- 图形库、Agent 解释、TaskIntent、renderer 验证使用同一 profile identity。

### 12.15 设计参考

- Origin 官方说明先由列 Plot Designation 和数据选择确定角色，再由模板/Theme 控制图类和外观：[Basic Graphing](https://docs.originlab.com/origin-help/basic-graphing)；
- Origin 为不同图类明确列出列数、X/Y/error/size/color 等数据选择要求，说明图类知识不能被简化为通用 X/Y：[Data Selection Requirements for Origin Graph Types](https://docs.originlab.com/origin-help/graph-type-data-req/)；
- RAG 研究说明参数内记忆在知识密集任务上的精确访问、更新和来源追溯存在局限，支持使用显式、可更新知识而非依赖模型记忆：[Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401)；
- NIST AI RMF 要求记录系统知识边界、目标使用范围、科学完整性和人类监督，为领域卡的范围、来源、限制和审核提供治理依据：[AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/)。

这些参考支持“显式、可追溯、按需提供、记录边界”的方法；具体 34 图语义仍必须由 PlotAgent 的官方研究、本机实证和用户视觉签名决定。

### 12.16 已确认原则

1. 领域说明提供版本化知识，不替模型通过关键词或正则决定图类、字段和数据操作；
2. 程序合同、审查知识卡、官方/本机证据、任务事实和模型先验有明确权威顺序；
3. 知识分 D0–D5 六层，常驻内容短小，图类、计算和示例按需注入；
4. 每个正式图类有 ChartKnowledgeCard，并与 EngineProfile/验证 claim 交叉校验而非复制第二份真值；
5. 科学计算使用独立 CalculationContract，不把公式和默认值藏在 prompt 或 renderer 中；
6. 用户未选图时由模型显式读取目录和比较候选，程序只做权限/ID/版本过滤；
7. 示例包含最小、代表、近似反例和非法例，不把固定列名或位置固化为规则；
8. Agent 只接触跨后端公共语义，Origin/Matplotlib 私有实现留在 renderer 与验证器；
9. 官方资料先审核并版本化，普通任务不实时把网页注入模型；知识变化触发相关回归；
10. 用户明确知识进入当前 TaskIntent；冲突时追问或拒绝，不自动写成跨任务偏好；
11. 知识缺失、过期或冲突时 fail closed，不以模型训练记忆伪装支持；
12. 用户可见的是准确图类说明、判断依据、字段角色和具体追问，不暴露后端内部实现。

## 13. 设计项 4：运行循环

> 状态：已确认。本节构成后续施工与验收依据。

### 13.0 总体判断：复用 Pi 内循环，自研耐久产品外循环

PlotAgent 不重新实现模型—工具循环。Pi 继续负责：模型调用、消息追加、工具选择、顺序/并行工具执行、turn 生命周期、continue、steering/follow-up、abort、上下文变换和事件流。

PlotAgent 自行负责：任务阶段、权威状态、工具暴露、确认点、ExecutionGrant、项目事务、验证、修复范围、预算、部分成功、恢复、取消和最终完成条件。

二者关系：

```text
PlotAgent Task Orchestrator（耐久、权威、可恢复）
  └─ AgentActivation
       └─ Pi Agent（本次激活的自主内循环）
            ├─ 观察上下文
            ├─ 选择并调用允许工具
            ├─ 根据真实结果调整
            └─ AgentYield
  └─ 保存状态 / 等待用户 / 执行计划 / 验证 / 再次激活 Pi
```

Pi 的一次 `prompt()` 结束只代表本次 Agent activation 结束，不代表产品任务完成。产品只有在验证器证明全部必需交付物通过后才能进入 `completed_verified`。

### 13.1 为什么采用“多次激活”而不是常驻会话

任务可能等待用户确认数分钟、Origin 导出数分钟、桌面重启数小时，不能依赖内存中的 Pi Agent、Provider session 或 messages 一直存活。采用多次激活：

- 每次 activation 从 Core 的 Task Ledger、Checkpoint、TaskIntent、工具 receipt 和 VerificationReport 重建上下文；
- Pi messages 可以用于本次激活的推理连续性，但不是任务权威状态；
- 等待用户、等待外部资源或进程退出时不占用模型和常驻循环；
- Electron、Provider 或 Pi 崩溃后可从最后 checkpoint 重新激活；
- 切换模型或压缩上下文不会丢失已确认语义和已完成项目。

这类似耐久工作流中的“等待外部事件后恢复”，但 PlotAgent 不引入新的云工作流框架；只采用持久状态、唯一事件 ID、超时和幂等恢复原则。

### 13.2 三个不同的状态对象

不得把 Pi turn、UI loading 和产品任务状态混成一个枚举：

| 对象 | 生命周期 | 示例状态 | 权威方 |
|---|---|---|---|
| TaskState | 整个用户任务 | investigating、awaiting_confirmation、executing、verifying、partial、completed_verified | Core |
| AgentActivationState | 一次 Pi 激活 | starting、running、yielded、aborted、runtime_failed | Main/Pi adapter，结果回写 Core |
| TaskItemState | 批量任务单项 | pending、staged、running、succeeded、repairable_failed、failed、cancelled | Core |

UI 阶段由这三类真实状态和 TaskEvent 投影，不能让 `turn_start` 直接把整个产品任务标为“处理中”，也不能让 Pi 的 `agent_end` 把任务标为成功。

### 13.3 TaskState 主状态机

建议正式状态：

```text
created
  → investigating
  → awaiting_input ──用户回答──→ investigating
  → intent_staged
  → awaiting_confirmation
       ├─拒绝→ rejected
       └─确认→ executing
  → verifying
       ├─全部通过→ delivering → completed_verified
       ├─技术可修→ repairing → executing/verifying
       ├─语义需变→ awaiting_reconfirmation
       ├─部分不可修→ partial
       └─全部不可修→ failed

任意可取消阶段 → cancelling → cancelled 或 partial
外部环境暂不可用 → blocked，可显式恢复
能力边界不支持 → unsupported
```

`awaiting_input`、`awaiting_confirmation`、`blocked` 和 `partial` 是耐久状态，不占用 Pi 循环。`partial` 必须记录成功项和失败项，可由用户选择重试失败项、接受部分结果或取消剩余项。

### 13.4 AgentActivation 合同

每次需要模型判断时，Core 生成只读、版本化 `AgentActivation`：

```text
activation_id / task_id / task_version / reason
task_snapshot / original_instruction / current_user_message
confirmed_intent / item_statuses / working_notes
available_context_refs / domain_knowledge_refs
verification_reports / prior_tool_receipts
allowed_tools / permission_phase
remaining_budgets / deadline / locale
```

`reason` 只能是有限集合：

- `new_task`；
- `user_answered`；
- `user_corrected`；
- `verification_failed`；
- `external_blocker_cleared`；
- `resume_after_restart`。

activation 绑定 task version。旧 activation 的迟到工具调用和 yield 必须稳定拒绝，不能覆盖较新的用户修正。

### 13.5 AgentYield：Pi 退出的结构化原因

Pi 不以自由文本决定外层状态，只能产生以下 typed yield：

| yield | 含义 | Core 下一步 |
|---|---|---|
| `intent_ready` | 已形成完整 TaskIntent 和 staged 预览 | 本地编译验证，生成确认卡 |
| `needs_input` | 只有用户能解决的语义缺口 | 持久化问题，进入 awaiting_input |
| `technical_repair_ready` | 针对 VerificationReport 提出合同内修复 | 校验 repair scope，执行后复验 |
| `unsupported` | 已检查能力仍无法满足 | 记录具体边界与替代建议 |
| `blocked` | 环境依赖暂不可用 | 保存 blocker 和恢复条件 |
| `budget_exhausted` | 模型/工具/时间/修复预算耗尽 | 保留 staged/成功结果并让用户决定 |
| `cancelled` | 已响应取消 | 进入安全取消收口 |
| `runtime_failed` | Provider/Pi/协议故障 | 无项目副作用，按错误策略恢复 |

Pi 正常结束但没有合法 yield 时，只允许一次不重复业务工具调用的协议纠正；纠正后仍没有合法
yield 才是 `AGENT_YIELD_MISSING`，绝不视为任务完成。Core 对每个 yield 做 Schema、任务版本、权限和
状态转移校验。

### 13.6 一次完整任务的执行路径

1. Core 建立 TaskEnvelope、Task Ledger 和 `new_task` activation；
2. ContextBuilder 按权限组装当前任务、轻量数据预览、领域说明和工具；
3. Pi 自主检查原始数据、读取图类知识、预览数据操作并形成 TaskIntent；
4. Core 编译、验证并 materialize staged 数据/沙箱图，生成同源确认卡；
5. 用户集中确认，Core 签发绑定 task version、对象、动作和预算的 ExecutionGrant；
6. Core 以确定性 TaskPlanExecutor 执行数据操作和公共绘图动作；Pi 不需要逐条重新决定已经确认的动作；
7. 每个 TaskItem 原子提交，记录 tool/action receipt 和项目 revision；
8. 验证器检查数据、科学语义、Plot 合同、后端读回、产物和必要视觉；
9. 全部通过则执行已请求的交付并进入 `completed_verified`；
10. 技术失败则以 `verification_failed` 再激活 Pi，只开放失败范围内的诊断/修复工具；
11. 修复仍在冻结 TaskIntent 内可自动执行；改变字段、图类、统计定义或用户可见语义则生成新 task version 并重新确认；
12. 批量任务始终保留已经通过的 TaskItem，只重试失败项。

### 13.7 Main、Core 与 Pi 的进程职责

建议由 Main 实现轻量 `TaskPump`，但状态权威仍在 Core：

```text
Renderer UI
  → Main TaskPump
       → Core task.advance(event?)
            ← next_action: agent_activation | execute | verify | wait | terminal
       → 若 agent_activation：PiRuntimeAdapter.run(activation)
            ↔ Core 受控工具 RPC
            → Core task.accept_yield(yield)
       → 再次 task.advance，直到 wait 或 terminal
```

- Core 决定状态转移、工具权限、事务、验证和 next action；
- Main 持有模型凭证、启动 Pi、转发流式事件和管理进程级 abort；
- Pi 只接触 activation 投影和受控工具；
- Renderer 只提交用户事件、显示状态和确认，不直接拼计划或推动隐藏步骤。

`TaskPump` 不是另一套 Agent 框架，只是持续向 Core 询问“下一步是否可机械推进或需要激活 Pi”，在遇到 wait/terminal 时立即退出。不得 busy polling。

### 13.8 验证—修复循环

VerificationReport 必须先由程序分类：

| 分类 | 示例 | 处理 |
|---|---|---|
| transient_external | Provider/Origin 临时不可用、文件暂时锁定 | 有界基础设施重试或 blocked |
| deterministic_technical | renderer 参数拒绝、源绑定读回不符、导出缺失 | 进入 scoped Agent repair 或确定性修复 |
| semantic_conflict | 字段含义不明、单位假设变化、统计定义需变 | 重新询问/确认 |
| stale_or_concurrent | revision、lease、对象版本冲突 | 停止写入并重建上下文 |
| unsupported | 产品合同无法表达目标 | unsupported |
| safety_or_permission | 授权不足、输出越界、数据披露扩大 | 请求 P3 授权或拒绝 |

每次 repair assignment 固定：失败 claim、expected/observed、证据、允许修改对象、不可改变语义、剩余预算和已尝试签名。相同“错误码 + 对象版本 + 修复参数”不得重复执行；修复后必须运行原失败 claim 和受影响回归 claim。

修复循环的停止条件：通过、需要用户语义、无进展、相同失败重复、预算耗尽、取消或不可恢复。不得只按固定两次重试，也不得无限重试。

### 13.9 用户输入、steering 与 follow-up

用户消息根据任务阶段进入不同语义：

- `awaiting_input`：作为当前 task version 的结构化回答，触发 `user_answered` activation；
- `awaiting_confirmation`：修改映射或参数会创建新 intent version，旧确认失效；
- `investigating/repairing`：普通补充可通过 Pi steering 在安全工具边界进入当前 activation；改变目标、对象或权限则先取消当前 activation，再创建 `user_corrected` 新版本；
- `executing/verifying`：不在原子写入中途注入新语义；记录 correction，安全点停止剩余项并创建新版本；
- `completed_verified`：继续编辑同一图可创建关联 follow-up task，但不是悄悄改写已完成任务历史。

Pi 的 steering/follow-up 用于消息送达和本轮协作，不决定任务版本。Core 根据状态与内容来源决定它是回答、修正还是新任务；程序不解释自然语言语义，只按用户选择的 UI 操作和当前状态建立相应事件，模型在 activation 中理解内容。

### 13.10 预算模型

预算必须同时有 task-wide 和 per-activation 两层：

- 模型 turn、输入/输出 token、调用次数和估算成本；
- 只读数据披露行数、单元格数和字节数；
- 工具调用、沙箱渲染、Origin 会话和 fresh reopen 次数；
- 技术修复次数、视觉修改次数；
- 端到端 wall time 只测量、不设产品硬上限；单个 Provider/工具调用保留传输 timeout；
- staged 文件空间和输出文件数量。

per-activation 防止一次模型循环失控；task-wide 防止反复恢复绕过总预算。预算接近上限时向 Agent提供真实剩余额度；耗尽后保留成功项和 staged 证据，用户可以增加预算、接受部分结果或停止。程序不能为了省 token 改回关键词语义路由。

### 13.11 错误、重试与幂等

重试分三层：

1. **传输重试**：只对明确 retryable、无副作用或带幂等键的 RPC/Provider 请求，使用短次数和退避；
2. **工具重试**：依据 ToolReceipt 协调实际状态，确认未成功后再重试；
3. **Agent 修复**：任务已经得到有效失败证据，需要改变技术方案时才重新激活模型。

禁止将本地 validation reject、科学合同失败、权限拒绝或 stale revision 当作瞬时错误盲重试。所有写操作使用稳定 idempotency key；外部事件带 event ID 并去重；迟到结果必须检查 activation/task version。

模型 timeout、Provider 断连或 Pi runtime crash 默认不修改项目。若故障发生在工具调用之后，必须先读取 receipt/项目 revision/输出 staging，不能直接宣称“无副作用”或重复执行。

### 13.12 取消、暂停与恢复

取消链：UI → Main TaskPump/Pi abort → Core cancel token → 工具/renderer/Origin。行为遵循已确认权限与回滚设计：

- 只读和可中断 staged 操作尽快停止；
- 数据库事务、文件原子发布等临界区完成到一致边界后停止；
- 已成功 TaskItem 和已发布合法产物保留并报告；
- 自动化只终止身份可验证的本任务 Origin 实例；
- 取消结果为 `cancelled` 或 `partial`，不是 generic failed。

暂停只发生在耐久 wait 状态。桌面重启后，Core 从 checkpoint 判定：等待用户则恢复确认/问题卡；可机械推进则 TaskPump 继续；需要模型则生成 `resume_after_restart` activation；外部副作用不明则先 reconcile，绝不从头重复整条任务。

### 13.13 并发与批量调度

第一阶段保持单 Agent、每项目一个写入任务和 Pi 工具顺序执行：

- 不引入多 Agent；
- 同一项目只有一个 TaskPump 获得 writer lease；
- 独立 TaskItem 可在计划层表示依赖，但项目写入先按确定顺序提交，降低 revision 冲突；
- 数据只读检查未来可以在工具实现内部安全并行，不由模型同时写多个对象；
- Origin 自动化使用全局可恢复 lease；
- 批量任务按 TaskItem 分别记录状态、预算和验证，某项失败不回滚其他成功项。

只有性能证据证明串行成为瓶颈且并行不会破坏可恢复性时，才开放受控并发。

### 13.14 完成与停止条件

Pi 内循环停止条件与产品任务停止条件必须分开。

Pi activation 可以因合法 yield、turn/token/time/tool 预算、abort、Provider 错误或 runtime 错误结束。只有合法 yield 能推动产品状态。

产品进入 `completed_verified` 必须同时满足：

- 所有必需 TaskItem 为 succeeded；
- TaskIntent 与 ExecutionGrant 版本一致；
- 所有项目写入和输出均有 receipt；
- 必需 VerificationReport claim 全部通过；
- 用户要求的 PNG/SVG/OPJU 等交付物已生成、验证并发布；
- 没有未解决 blocker、待回答问题、待确认语义或不明副作用；
- 最终项目 revision、plot ID/version 和 artifact hash 已写入 Task Ledger。

Agent 文本中的“完成”“应该可以”或 Pi `agent_end` 不参与完成判定。

### 13.15 施工前实现差距（历史，现已关闭）

以下条目记录 P0–P10 施工前的基线，不再描述当前产品：

- 每次 run 新建 Agent、`messages=[]`，只在本轮依赖内存状态；
- Pi 提交 draft 或 ask_user 后立即 terminate；
- Core 编译并保存待确认计划，确认后的 `TaskPlanExecutor.run()` 与 Pi 分离；
- 执行失败和 VerificationReport 不会重新进入 Agent；
- 最多 2–6 turn 与 60 秒 timeout 只约束草稿生成，不是完整任务预算；
- `agent_end` 周围只有粗粒度阶段，缺少 durable activation/yield/checkpoint；
- Main 的 abort 主要停止当前 Pi，不等同于端到端任务取消；
- Provider sessionId 和 Pi messages 不能恢复 TaskState；
- 当前 lifecycle 的 `completed` 实际可能只表示“计划已生成等待确认”，容易与任务完成混淆。

上述差距已关闭：正式链已收敛为 `PiRuntimeAdapterV2`、Core Task Orchestrator、Main TaskPump、验证回灌和 durable state；端到端 wall time 当前只记录和评测，不设置产品硬截止。

### 13.16 最小施工顺序

1. 定义 TaskState、AgentActivation、AgentYield、next action 和错误分类 Schema；
2. 将现有 workflow run/plan/item 状态迁移到统一 Task Ledger，不改变 renderer；
3. 把 `PiAgentRuntime.run()` 改成 activation adapter，并保留现有只读/preview/draft 工具；
4. 实现 Core `task.advance` / `task.accept_yield` 与 Main TaskPump；
5. 接入确认、ExecutionGrant 和现有确定性 TaskPlanExecutor；
6. 接入 VerificationReport，先完成单次 scoped technical repair；
7. 扩展为多次修复、partial、cancel、blocked 和 restart resume；
8. 接入完整 TaskEvent/trace/budget；
9. 最后启用 Pi steering/follow-up 与上下文压缩，不把它们作为前置依赖；
10. 以新 EvalCase/SEQ-70/Windows 黑盒验证后替换旧 workflow 入口。

每一步都保留可运行的正式 UI 主链；不在同一提交同时重写 TaskState、Pi adapter、数据工具、renderer 和前端。

### 13.17 验收用例

- 简单明确任务由一次 activation 形成 intent，确认后机械执行、验证并完成；
- 数据需检查时 Pi 可多次调用只读/preview 工具，不被固定步骤限制；
- 真正缺语义时进入 awaiting_input，回答后即使桌面重启也能恢复原 task version；
- 信息明确时不得产生无效追问；
- 用户拒绝确认时无项目副作用；修改确认卡后旧 intent/grant 失效；
- 执行期 deterministic technical failure 会生成 VerificationReport 并触发 scoped repair；
- repair 不改变语义时自动完成，改变字段/图类/统计定义时必须重新确认；
- 相同失败方案不会循环，预算耗尽保留 staged/成功结果；
- 批量 3 项中 2 成功 1 失败时只修/重试失败项；
- Provider timeout、Pi crash、Core restart、Electron restart 和 Origin blocker 均可从 checkpoint 恢复；
- 写工具返回前断连时先 reconcile receipt，不产生重复版本或重复文件；
- 用户在 investigating、awaiting_confirmation、executing 和 completed 后发修正时分别遵循 steering/version/follow-up 语义；
- 取消能贯穿 Pi、Core、renderer 和本任务 Origin，且不终止用户 Origin；
- stale activation、迟到 yield 和重复外部事件被拒绝或去重；
- `completed_verified` 只有在全部 required claim 和 artifact receipt 通过后出现；
- UI 的阶段、耗时、部分成功和错误均来自真实 TaskEvent，不把 Pi `agent_end` 显示为任务完成。

### 13.18 设计参考

- Anthropic 将 Agent 描述为在工具和环境反馈中自主计划、行动、观察、调整，直到完成或需要人类输入，并强调清晰成功标准、反馈循环、停止条件和人类检查点：[Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)；
- Anthropic 进一步区分模型、harness、工具和环境，指出 Agent 的有用性与安全性依赖人类控制、权限和在歧义处正确 check in，而不是只依赖模型：[Trustworthy agents in practice](https://www.anthropic.com/research/trustworthy-agents)；
- Azure Durable Functions 的外部事件模式说明等待人工确认应持久休眠，并使用事件 ID 去重和 timeout，支持 PlotAgent 的 awaiting_input/confirmation 与多次 activation 设计：[Handle external events in durable orchestrations](https://learn.microsoft.com/en-us/Azure/Azure-functions/durable/durable-functions-external-events)；
- Agent eval 实践强调 Agent 跨多轮调用工具、改变环境并根据中间结果适应，说明运行循环的成功应由环境结果而非单轮文本判定：[Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)。

这些参考提供自主循环、耐久等待和监督原则。PlotAgent 不引入云 Durable Functions，也不照搬其他 Agent 框架；Pi 是内循环，Core 的本地持久 TaskState 是产品外循环。

### 13.19 已确认原则

1. 最大化复用 Pi 的模型—工具内循环，不自行重写通用 Agent loop；
2. PlotAgent 自研耐久外循环，Core 的 TaskState 与真实环境结果是权威；
3. 使用多次 AgentActivation，而非依赖一个常驻 Pi 会话跨确认、Origin 和桌面重启；
4. Pi 每次以 typed AgentYield 退出，无合法 yield 的 `agent_end` 不是任务完成；
5. 确认后由 Core 确定性执行冻结 TaskPlan，Pi 不逐条重决策已确认动作；
6. 验证失败通过 scoped VerificationReport 再激活 Pi，技术修复自动，语义变化重新确认；
7. Main TaskPump 只协调 Core next action 与 Pi activation，不保存权威任务状态，也不 busy polling；
8. steering/follow-up 负责消息送达，Core task version 决定回答、修正和后续任务边界；
9. task-wide 与 per-activation 双层预算限制模型、数据披露、工具、Origin、修复、时间和成本；
10. retry 区分传输、工具 reconcile 和 Agent 修复，写操作幂等，迟到 activation/yield 稳定拒绝；
11. 取消贯穿 UI、Pi、Core、工具、renderer 和本任务 Origin，原子边界与已成功项保留；
12. 第一阶段单 Agent、单项目 writer、顺序工具与确定性 TaskItem 提交，不提前引入并行/多 Agent；
13. completed_verified 只由必需验证 claim、receipt、交付物和最终 revision 共同决定；
14. 现有 PiRuntime 收敛为 adapter，按 Schema→状态→执行→验证→恢复逐步迁移，不一次重写全部系统。

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

### 2026-08-18：确认权限与回滚

- P0 只读和 P1 staged 操作自动执行；P2 在 TaskIntent 集中确认后执行；P3 扩权或改变语义时再次确认。
- Core 签发绑定任务版本、对象、动作、输出位置和预算的最小 ExecutionGrant，模型不能修改授权本身。
- 每个 TaskItem 独立原子提交，批量任务保留部分成功；写操作使用稳定 idempotency key，并在重试前协调实际结果。
- 用户取消贯穿 Pi、Core、工具、renderer 与 Origin；Provider/工具传输超时仍保留，但不设置 Agent
  端到端时长预算，且任何取消或超时都不在数据库/文件原子发布临界区强杀。
- Origin 只控制身份可验证、属于本任务的自动化实例，绝不终止用户 Origin。
- 项目撤销通过不可变 revision 恢复；导出先 staged、验证后原子发布，默认不覆盖，外部文件不伪装成可由项目 undo 收回。
- 项目写入和 Origin 自动化使用可恢复 lease，revision 冲突不得静默覆盖。
- 用户只集中确认语义和正式副作用，内部工具不重复弹窗；所有副作用必须保留完整审计记录。

### 2026-08-18：确认工作记忆

- 工作记忆只服务当前任务连续性和项目恢复，不自动学习偏好或生成跨任务 Recipe。
- Task Ledger、Task Checkpoint、Working Notes 和 Conversation View 分层保存，聊天记录不作为任务真相。
- 原始目标、确认语义、对象版本、TaskItem 状态、工具 receipt、失败尝试、验证和交付引用必须持久保留。
- 隐藏推理、凭证、无界工具输出、临时路径、未确认偏好和自由文本猜测不得长期保存。
- 只对任务运行采用轻量 TaskEvent + snapshot；Agent 只能写有类别、有证据的临时 note，不能修改授权和历史事实。
- ContextBuilder 从 Core 权威状态恢复，模型上下文压缩和 Provider/Pi 会话丢失均不得影响任务继续。
- 任务结束后保留正式事实和精简审计，清理假设、重复预览、临时对象和无引用 observation。
- 第一阶段只按确定性 ID 恢复，不通过相似度自动注入历史任务。

### 2026-08-18：确认可观察性

- 用户状态、工程 trace、聚合指标和诊断日志来自同一真实事件链，但采用不同的安全投影。
- TaskEvent 是任务事实，Trace 解释执行路径，Metric 做聚合统计，Log 只补充故障，彼此不得冒充。
- 一个任务对应根 trace，Pi、模型、Core、工具、renderer、Origin、验证、提交和导出使用关联 span。
- 用户阶段只能由真实事件驱动，允许循环和 attempt，不通过计时器伪造 Agent 行为。
- 只有总量可计算时显示确定进度；未知工作显示阶段和持续时间，不伪造百分比或 ETA。
- 失败必须说明阶段、原因、影响范围、已保留结果、副作用、恢复动作和 diagnostic ID。
- 记录端到端与分段耗时、模型调用/token/成本、重试和预算；价格未知时不伪造费用。
- 指标来自结构化事件和 VerificationReport；SEQ-70、发布门禁与黑盒测试仍保留独立证据要求。
- 默认本地、payload-off、无后台 telemetry 上传；诊断上传需要新的 P3 数据披露授权。
- UI 使用可访问的真实状态、取消、部分成功和恢复反馈，用户无需阅读内部 trace 才能理解任务状态。

### 2026-08-18：确认评测体系

- 评测完整产品与真实结果，不把模型回答、Agent 自述、单测或截图单独视为任务完成。
- 使用 E0–E6 七层评测，覆盖静态合同、确定性程序、Agent 运行时、真实模型、双后端产物、正式 Windows UI 与发布非功能门禁。
- 每个 EvalCase 冻结 claim、环境、fixture、预期与禁止结果、grader、预算和 trial 策略。
- regression、capability、safety、recovery 与 exploratory suite 分开管理；真实可复现缺陷必须沉淀为冻结回归。
- grader 优先确定性结果与原生读回，trace 只检查必要安全协议；模型 grader 不得独占科学语义、数据值或 Origin 结构判定。
- 真实模型 trial 数在运行前冻结，关键回归要求全部通过，失败不得通过选择性重跑被覆盖。
- trial 相互隔离，输入保持不可变；采用 development、frozen regression、holdout 和真实 bug set。
- 图形评测同时保留机械合同、Origin fresh reopen 与人工视觉三道独立门，并使用合同驱动的性质测试。
- 正式状态为 PASS、FAIL、BLOCKED、UNVERIFIED、EVAL_INVALID；发布必测项的任何非 PASS 都不能支持 GO。
- 发布候选必须在同一冻结 commit 上关闭 Agent 多 trial、34 图资格、正式 UI、性能、安全、隐私、恢复与证据追溯。

### 2026-08-18：确认领域说明

- 领域说明是版本化、可追溯、按需提供的产品知识，不是巨型 system prompt、关键词路由表或 renderer Recipe。
- 知识权威依次为程序领域合同、经审查知识卡、官方/本机证据、当前任务事实与仅可形成假设的模型先验。
- 领域知识分为 Agent constitution、通用绘图语义、图类知识卡、计算合同、工具合同和证据/示例六层。
- 34 个正式图类分别建立 ChartKnowledgeCard，并与 EngineProfile、CalculationContract 和验证 claim 自动检查一致性。
- 科学计算使用独立、版本化 CalculationContract，公式、默认值和边界行为不得隐藏在 prompt 或 renderer 中。
- 用户未选图时由模型显式读取目录、比较知识卡并选择或追问；程序不以关键词、正则、列名或数据形状替模型路由。
- 示例包含最小、代表、近似反例和非法例，不把固定列名、位置或 fixture 固化为规则。
- Agent 只接触 Matplotlib 与 Origin 的公共语义，后端命令、模板路径、PID、layer 和 artist 留在 renderer 与验证器。
- 官方资料先经离线研究、版本核验和人工审核再发布；普通任务不把实时网页直接注入上下文。
- 用户提供的专业知识只进入当前 TaskIntent；冲突时展示证据并追问或报告不支持，不自动形成跨任务偏好。
- 知识缺失、过期或合同冲突时 fail closed，不以模型训练记忆冒充产品能力。
- 用户可见图类用途、数据要求、判断依据和具体追问，不暴露底层实现细节。

### 2026-08-18：确认运行循环

- Pi 完整承担模型调用、消息、工具选择与执行、turn、continue、steering/follow-up、abort 和上下文变换等通用 Agent 内循环。
- PlotAgent 自研以 Core TaskState 为权威的耐久外循环，负责阶段、确认、授权、事务、验证、修复、预算、取消、恢复和完成条件。
- 一次任务由多个版本化 AgentActivation 组成，不依赖常驻 Pi 会话跨越用户等待、Origin、桌面退出和 Provider 变化。
- Pi 必须产生 typed AgentYield；无合法 yield 的 agent_end 不能改变产品任务状态或被视为完成。
- 用户确认后由 Core 按冻结 TaskPlan 确定性执行，Pi 不逐条重新决定已确认动作。
- VerificationReport 失败时按 scoped repair 再激活 Pi；冻结语义内技术修复可自动执行，字段、图类、统计定义或其他语义变化必须重新确认。
- Main TaskPump 只协调 Core next action、Pi activation 和流式事件，不保存权威状态、不解释自然语言、不 busy polling。
- steering/follow-up 负责消息送达，Core task version 与用户显式 UI 事件决定回答、修正和后续任务的边界。
- 使用 per-activation 与 task-wide 双层预算，覆盖模型、数据披露、工具、Origin、修复和成本；端到端
  时长只记录并进入发布评测，当前不作为终止条件。
- retry 区分传输重试、工具 receipt reconcile 与 Agent 技术修复；写操作幂等，旧 activation、迟到 yield 和重复事件稳定拒绝。
- 取消贯穿 UI、Pi、Core、工具、renderer 和本任务 Origin，在一致性边界停止并保留已成功 TaskItem。
- 第一阶段保持单 Agent、每项目一个 writer、顺序工具和确定性 TaskItem 提交，不提前引入多 Agent 或写入并行。
- completed_verified 只由必需验证 claim、receipt、交付物、最终 revision 和无未决状态共同决定。
- 旧 PiAgentRuntime 已按阶段收敛为 PiRuntimeAdapterV2；施工过程没有在一个提交中同时重写任务状态、工具、renderer 和前端。

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
