# PlotAgent v3 绘图引擎重构与验收基线

> 状态：产品与验收契约已冻结；Gate 0、Gate 1、模板优先生产链与 Gate 3A 逐图机械编辑资格均已完成；Gate 3B 统一视觉审查页已生成并等待用户签名，任何图均未因机械通过自动取得视觉 PASS
>
> 适用范围：正式 T1/T2 38 图、Matplotlib PNG/SVG、Origin 原生 OPJU、Agent 创建/编辑、批量与组合图
>
> 关联文档：[Origin 官方模板映射](./ORIGIN-OFFICIAL-TEMPLATE-MAPPING.md)、[产品决策](./PRODUCT-DECISIONS.md)、[实施计划](./IMPLEMENTATION-PLAN.md)

## 1. 决策摘要

当前实施事实（2026-08-10）：正式库存为 38；官方模板目录与哈希已进入生产 plan；38 图共 368 个裸模板动态变体完成，结论为 28 `AUTO`＋10 `DECLARED_PATCH`；38/38 代表性默认态已完成真实 Origin build/fresh-reopen；旧 K01 专用导出路径已删除；38/38 独立 OPJU 已完成数据值＋代表性样式修改与 fresh-reopen 读回，Gate 3A 已关闭。统一 38 图视觉页为 `build/visual-audit/template-first-38/index.html`，Gate 3B 尚待用户逐图视觉签名与 33 个模板文件家族的代表图人工编辑签名。

产品目标和用户流程不变，改变的是绘图引擎内部实现：

- PlotAgent 仍是“绘图 Agent + 适合 Agent 操作的科研绘图引擎”。
- 用户仍可导入数据、明确选择图形、确认字段映射、用自然语言或手动控件创建和修改图、批量绘图、创建组合图，并导出 PNG、SVG 与原生可编辑 OPJU。
- Agent 仍使用项目级上下文、跨轮次作用对象、任务计划、部分失败和恢复执行；这些能力不因 renderer 重构而缩减。
- 原始数据保持只读；常规整理由受控数据准备动作生成可追溯派生数据，不要求用户事先把所有数据加工成最终绘图表。
- 正式图形范围以 T1/T2 共 38 图为准；已决定删除的七图不因本次重构恢复。

新的实现选择是：

1. Agent 输出受控、强类型的业务动作，不输出 Matplotlib、Origin、Python、脚本、对象路径或任意属性。
2. 动作经本地校验后生成或修改语义 PlotSpec；PlotSpec 是可版本化、可撤销、可恢复的产品真值。
3. 每张正式图有一个平坦的 `ChartProfile`，声明字段角色、共同编辑能力、Matplotlib renderer、Origin 模板/绑定器和验证规则。
4. Matplotlib 允许每图独立 renderer；共享字体、色板、轴、图例、色带、边界检测、导出与错误处理等基础工具，但不要求所有图经过一个统一几何计划。
5. Origin 优先使用映射表中的官方模板。T1 只做数据绑定和用户编辑；T2 只增加裸模板证据证明必要的少量原生配置。禁止用大量手工 Line/Text/Shape 重画 Origin 已支持的原生图。
6. StructureUnit、ChartRecipe 和统一 renderer 不再是第一阶段目标，也不作为验收条件。以后若重新引入，必须证明它降低维护成本，不能改变产品行为或牺牲绘图正确性。

## 2. 权威执行链

```text
User / Manual UI
        |
        v
Agent-native typed actions
        |
        v
Local target resolver + validator + transaction
        |
        v
Semantic PlotSpec / BatchSpec / FigureSpec
        |
        v
ChartProfile
   |                         |
   v                         v
Per-chart Matplotlib      Origin official template
renderer                 + per-chart binder/adapter
   |                         |
   v                         v
PNG / SVG                native editable OPJU
```

这里的 “Agent-native” 指动作契约为 Agent 设计，但执行权仍在本地确定性领域服务。模型不能直接操作 renderer 或 Origin。

## 3. PlotSpec 与 ChartProfile 边界

### 3.1 PlotSpec 只保存语义

PlotSpec 保存：

- 图形类型、数据版本、字段角色和系列身份；
- 用户明确选择的坐标、标题、样式、图例、色标、标注、布局和图形专属参数；
- publication profile、版本、父版本、来源与变更记录；
- 固定计算或受控数据准备结果的引用。

PlotSpec 不保存：

- Matplotlib artist、Origin object ID、LabTalk、Python 代码或任意属性路径；
- 最终像素坐标、Origin 页面内部坐标或跨后端强行统一的图元几何；
- renderer 为当前画布临时选择的碰撞避让结果；
- 隐藏统计、拟合、数据清洗或单位换算。

### 3.2 ChartProfile 是平坦能力目录

每张图的 ChartProfile 至少声明：

- `chart_type_id`、版本与可用状态；
- required/optional/repeatable 字段角色及类型、单位约束；
- 可用的数据准备与固定计算入口；
- 可向用户和 Agent 开放的共同编辑域；
- Matplotlib renderer 入口；
- Origin 官方模板、模板哈希、列 designation、T1/T2 结论和最小原生配置；
- 默认态、动态数据、代表性编辑态和持久化验证器；
- 明确不支持的请求和稳定错误。

ChartProfile 不是组件图、结构单元树或 renderer 配方语言。

## 4. Agent 动作边界

第一阶段保持少量顶层动作，细节放入强类型参数。建议冻结为 13 个顶层动作：

1. `request_import`
2. `prepare_data`
3. `create_plot`
4. `duplicate_plot`
5. `patch_plot`
6. `create_batch`
7. `patch_batch`
8. `create_figure`
9. `patch_figure`
10. `export_artifact`
11. `revert_changeset`
12. `retry_failed_items`
13. `resume_task`

`patch_plot.changes[]` 使用封闭、强类型编辑域：

- `bind_fields`
- `set_title`
- `set_axis`
- `set_series`
- `set_legend`
- `set_color_scale`
- `edit_annotation`
- `set_layout`
- `set_chart_parameter`
- `apply_publication_profile`

一次 `patch_plot` 是一个原子变更集。Agent 只看到当前 ChartProfile 允许的域和参数，不看到其他图无关的完整 Schema。

### 4.1 只开放双后端共同能力

正式 UI 与 Agent 只开放 Matplotlib 和 Origin 都能稳定表达、保存并重新读取的共同能力。共同能力至少包括适用图形上的：

- 字段重绑、系列增删/排序及左右轴归属；
- 图题、轴标题、字体、画布与 publication profile；
- 坐标范围、自动/固定、反向、linear/log10、刻度间隔和数字格式；
- 线色/宽/型，点色/形/大小/内部，填充/透明度，柱与误差样式；
- 图例显示、位置、列数、顺序、条目文本和样例；
- 连续/离散色标、范围、palette、反向和标题；
- 文本、参考线、参考带等受控标注的增删改；
- 图形专属但能在双后端保持语义一致的参数。

任一后端不能稳定表达的编辑不进入公共动作。不得在运行时近似替换、静默忽略或产生只对一个后端有效的 PlotSpec 状态。

## 5. 数据准备边界

用户不需要把数据完全整理成 renderer 的最终内部形状。`prepare_data` 可覆盖：

- 选择文件、工作表、数据块、表头和字段；
- 重命名、类型确认、缺失值策略、筛选和排序；
- 宽长表转换、受控 pivot/unpivot；
- 明确的聚合、类别顺序、单位声明与少量登记派生列；
- 为某一 ChartProfile 生成可追溯的 PreparedDataset。

原始 SourceDataset 不变，派生数据记录输入、参数、版本和哈希。影响科研结论的统计、拟合或领域计算必须使用独立的强类型计算对象并由用户明确确认，不能藏在 renderer 或模板中。任意 Excel 公式、自由 Python/SQL、复杂清洗和无法确定语义的表格仍需用户确认或在外部准备。

## 6. 验收原则

### 6.1 “执行过”不等于 PASS

每个用例只允许以下状态：

- `PASS`：预先写明的全部判据均满足，并保存足够的原始证据。
- `FAIL`：观察到产品输出违反判据。
- `BLOCKED`：外部环境阻止执行，且已有具体环境证据。
- `UNVERIFIED`：未执行完、证据不足或无法从证据确认。

启动成功、脚本退出码为零、OPJU 能打开、fresh-reopen 一致或“肉眼看起来可以”都不能单独等价于 PASS。未执行的功能不得由源码、单测或口头说明推定通过。

### 6.2 后端一致性是语义一致，不是像素一致

Matplotlib 与 Origin 必须一致的内容包括：

- 使用的数据和纳入/排除行；
- 字段角色、系列身份、图层/轴归属；
- 变换、范围、方向、刻度语义；
- 颜色、线、点、填充、误差、图例条目和标注语义；
- 用户编辑后的 PlotSpec 状态。

允许差异包括字体 hinting、抗锯齿、模板默认留白和不影响科研含义的原生布局差异。不得为了像素一致而破坏 Origin 原生性，也不得用“原生布局不同”掩盖裁切、重叠、缺图例样例、错误色带或错误坐标。

## 7. 38 图逐图验收矩阵

每张图至少完成以下五组测试。

### A. 默认图形正确性

- 使用有依据的同源数据和参考图；没有 A/C 证据时必须明确标为冻结合成基线，不能冒充官方同源。
- 字段映射、数据几何、轴语义、图例、色带、标签和默认样式符合 ChartProfile。
- 已知高风险项必须进入显式断言，例如 K04 不应无条件多出色带、K14 不得出现边缘竖线、图例必须含正确的线/点/柱样例。

### B. 动态数据泛化

按适用性覆盖：

| 维度 | 最低档位 |
| --- | --- |
| 行数/点数 | minimal、representative、large |
| 系列或组数 | 1、2、3、5 |
| 类别数 | 3、10、30 |
| 数值范围 | 小数、大数、全正、全负、跨零、零跨度 |
| 误差/区间 | 无、对称、非对称、跨零 |
| 标签 | 短英文、长英文、中文；校验内容、关联与字体，不以自动排版是否裁切/重叠作为阻断 |
| 缺失值 | 点缺失、整系列缺失、可选字段缺失 |
| 系列顺序 | 原顺序、重排、新增、删除 |

通过条件不是“生成文件”，而是数据不丢失、系列不串色、柱等数据几何不发生语义错误的重叠、轴范围覆盖全部可见数据几何且缺失规则正确。标签裁切、换行和相互遮挡不作为本轮资格阻断，但仍在证据页保留原始输出，供后续产品体验优化。

### C. 共同编辑能力

- ChartProfile 声明的每个编辑域至少一条合法测试；关键域需要边界值和组合编辑。
- 未声明能力必须稳定返回 Unsupported，不改变 PlotSpec 版本和已有产物。
- 同一 PlotSpec 编辑分别生成 Matplotlib 与 Origin 产物，检查语义一致。
- 编辑后保存项目并重开，PlotSpec 版本、目标和用户状态保持。

### D. Matplotlib 产物

- PNG/SVG 均使用完整 formal 数据；尺寸、DPI/viewBox、字体、CJK、颜色和矢量安全检查通过。
- 自动边界检查用于记录标题、轴标题、刻度、图例、色标、标注及数据图元的边界；本轮只把数据几何被裁掉、错误图元遮盖数据或科研语义不可读作为阻断，普通标签排版冲突不阻断。
- 每图独立 renderer 的默认态、代表性编辑态和动态风险态都保留视觉证据。

### E. Origin 原生可编辑性

- 使用登记的官方模板和冻结哈希；T2 只使用已声明最小原生配置。
- Worksheet/Matrix、Plot、Layer、Axis、Legend、Color Scale 和 Annotation 为原生对象，Plot 与数据保持链接。
- 每张图至少生成默认态和代表性编辑态 OPJU，并在新的空白 Origin 会话 fresh-reopen。
- 38 图逐图由自动化修改至少一个数据值和一个代表性允许样式，保存、fresh-reopen 后机械读取对象类型、数量、数据链接、关键样式和文本，并确认两项修改均持久化。
- 人工实际编辑不再要求覆盖 38 图。38 图迁移和机械读回全部完成后，再按 Origin 模板家族选择代表图：每个家族至少人工修改一个数据值和一个允许样式，保存、关闭、重开并确认原生可编辑。家族键由官方模板哈希、原生 Plot/Layer 结构和 T2 补丁签名共同确定，不能仅按图形名称合并。
- 禁止嵌入 Matplotlib 位图、外部文件依赖、任意脚本或不可追踪手工对象冒充原生图。

## 8. Agent 与产品链路验收

### 8.1 Agent 动作

至少覆盖：

- 明确指定图形的创建、字段自动预填与一次确认；
- 信息不足时只问必要问题，不猜图形类型或字段；
- 当前图、上一张图、选中图、批次、组合图等跨轮目标解析；
- 一次请求包含多个共同编辑时生成一个可核对原子变更集；
- 不适用能力在计划阶段即拒绝，不由 renderer 晚失败；
- 计划确认前无副作用，执行后产生新版本和 ChangeSet；
- stale target、权限不足、模型超时和非法输出均无半版本。

真实模型质量评测至少报告计划合法率、对象绑定准确率、字段映射首轮接受率、必要/无效追问率、执行成功率、延迟和成本。固定评测 GO 不能替代真实桌面黑盒。

### 8.2 批量、组合与恢复

- 同构批次一次映射、多图创建、共同编辑、部分失败保真和失败项局部重试；成功项不得重复执行。
- 组合图引用明确 PlotSpec 版本，子图仍可独立追溯；创建失败必须保留候选并显示原因。
- 任务中断后只从已提交边界恢复；恢复前显示将复用和重做的项，用户明确确认后执行。
- 应用重启后恢复项目、数据身份、最近图版本和可恢复任务，不恢复不可信进程内状态。

### 8.3 正式桌面黑盒

黑盒验收必须从正式 Electron 入口启动，记录 HEAD/build、命令、端口、项目 ID、数据版本、PlotSpec ID/version 和产物路径。验收人必须能实际操作 UI；打不开应用或没有原始截图/产物的项目只能记 BLOCKED/UNVERIFIED，不能由另一窗口的单测结论替代。

## 9. 阶段门禁

### Gate 0：契约冻结

- 38 图 registry、ChartProfile Schema、13 个 Agent 动作和共同编辑域冻结。
- 七个删除图从全部生产入口清除。
- 旧 StructureUnit/ChartRecipe/统一几何计划被标为历史契约，生产新链不再依赖。

### Gate 1：Origin 裸模板能力

- 38 图完成裸模板动态测试并得到 AUTO、DECLARED_PATCH 或退出范围结论。
- 任何需要超出 T2 的图停止迁移并回到产品决策，不能偷偷增加专属几何补丁。
- 本 Gate 只判定模板能力和原生结构，不进行探索性视觉审查，也不产生视觉 PASS。

### Gate 2：四图纵向切片

优先用 K01、K09、K04、K14 覆盖简单 T1、动态 T2、气泡/色带和复杂原生模板。四图只用于打通 Agent 动作、PlotSpec 版本、Matplotlib、Origin OPJU、共同编辑、动态数据和桌面黑盒的机械链路；不在此阶段要求用户分批审图，也不据此冻结视觉样式。

### Gate 3A：38 图机械迁移完成

状态：**PASS（机械资格）**。冻结证据为 `tests/fixtures/origin_template_migration/manifest.json`；38/38 每图独立 OPJU 均含默认态与代表编辑态，并完成实际数据值、代表允许样式和 fresh-reopen 原生读回。

- 38/38 默认态、动态矩阵、共同编辑、PNG/SVG、OPJU/fresh-reopen 完成。
- 所有机械阻断项为零；38 图机械修改读回全部通过。
- 旧 Origin 几何路径和对应测试在新证据通过后删除。
- 此时 38 图视觉状态仍统一为 `UNVERIFIED`，不得因机械测试通过改写为 PASS。

### Gate 3B：统一视觉审查与签名

状态：**OPEN / UNVERIFIED**。统一审查页已经生成，等待用户逐图判断；机械 PASS 不改变本状态。

- Gate 3A 完成后一次性生成 38 图统一审查页；不在迁移中途进行探索性或分批视觉审查。
- 每图并列提供官方模板参考、Matplotlib 默认/代表性编辑态、Origin 默认/代表性编辑态和可下载 OPJU。
- 用户逐图给出 PASS/FAIL；Origin 人工实际编辑按模板家族抽代表图签名。未签图保持 `UNVERIFIED`。
- 视觉 FAIL 返回对应的每图 renderer、模板绑定或已声明 T2 补丁修复；不得修改证据标准迁就实现。

### Gate 4：Agent 与工作流资格

- 项目上下文、任务编排、跨轮对象、批量、组合、失败恢复和真实模型评测通过。
- Agent 与手动 UI 使用同一动作、validator 和事务链。

### Gate 5：正式发布资格

- 正式 Electron 黑盒、重启恢复、安全、性能、签名安装包和目标 Origin exact version 通过。
- `UNVERIFIED` 不计通过；关键用例有任一 FAIL/BLOCKED/UNVERIFIED 均不得宣称完整发布资格。

## 10. 每图最小证据包

每张图的资格目录至少包含：

- ChartProfile 版本与哈希；
- 输入数据、来源、seed（如适用）和哈希；
- 官方模板路径、Origin/`originpro` 版本和模板哈希；
- 默认态、代表性编辑态、动态风险态的 Matplotlib PNG/SVG；
- 对应 Origin build PNG、OPJU、fresh-reopen PNG 和原生对象检查报告；
- 双后端语义对照表；
- 自动不变量与逐图机械修改读回结果、所属模板家族、用户逐图视觉结论、家族人工编辑签名、已知差异和最终状态；
- 失败时的原始错误、截图、日志与未发布证明。

证据 manifest 必须把 expected、observed、status 和 artifact 分开保存，禁止仅用 `passed: true` 代替判据。

## 11. 当前非目标

- 不以 StructureUnit、ChartRecipe、统一 renderer 或跨后端像素一致作为完成条件。
- 不开放 Origin-only、Matplotlib-only、任意 property/path、LabTalk、Python、Shell 或模型工具自治。
- 不在 renderer 中隐藏数据清洗、统计、拟合、单位换算或科研结论。
- 不因历史 45 图证据、文件可打开或测试数量多就继承新引擎资格。
