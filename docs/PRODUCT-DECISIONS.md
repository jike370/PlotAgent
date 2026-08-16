# PlotAgent v3 产品决策

> 状态：当前权威决策。本文只描述现行产品，不保留已退役架构、图类或兼容方案。

## A. 产品定位

- PlotAgent 是面向科研绘图目标的 Agent 产品，同时提供可由其他 Agent 调用的本地绘图引擎。
- 核心价值是把自然语言目标、数据处理、字段绑定和视觉参数转换为可核对、可恢复的任务，并输出可编辑 Origin 原生图。
- 当前正式范围为 34 张单图；不提供多面板组合、自由画布或组合图对象。

## B. 图类与数据

- 用户显式选择图类；Agent 不在未选图时自行猜图。
- 支持 CSV/TSV/TXT/DAT 以及多工作表 Excel 的只读导入；仪器前导信息、数据块与尾部元数据分离保存。
- 支持“一批来源分别画图”和已声明 Profile 的“多份同构数据绘在同一张图”。后者是单图的数据合并，不是组合图。
- 原始 SourceDataset 永不修改。筛选、排序、宽长转换、同构拼接和登记的固定计算只产生新的只读 EngineDataView。

## C. 唯一编排链

- 正式链路为 `WorkflowRun → WorkflowContext → TaskDraft → TaskPlan → confirmation → execution`。
- WorkflowRouter 依次尝试确定性规则、用户明确保存的 WorkflowRecipe、Pi 单轮规划和 Pi 有界探索；简单任务不得无条件调用模型。
- Pi 可调用 `inspect_source`、`preview_rows`、`profile_field`、`compare_schemas` 四个只读工具；不能访问路径、文件系统、数据库、Shell、Python、Origin 或 renderer 对象。
- Pi 只能提交 TaskDraft。真实字段 ID、plot version、动作 ID 和幂等键由本地 TaskCompiler 绑定。
- 用户确认前零副作用；批量部分失败保留成功项，继续执行不重复成功项。
- 用户完成并导出一次任务后，可以明确选择固化 WorkflowRecipe；未经确认不得静默学习或跨项目保存偏好。

## D. 硬切换

- 项目 schema v5 只保存 WorkflowRun、WorkflowContext、TaskDraft、TaskPlan/TaskItem（含失败原因与可重试性）、事件和 WorkflowRecipe。
- 不双读、不双写、不提供旧计划别名、fallback、迁移器或兼容 RPC；非 v5 项目保持原文件不变并明确拒绝打开。
- Pi 是可替换运行时。任何替代 Agent 必须消费同一 WorkflowContext、遵守预算并提交同一 TaskDraft；不能改变本地编译、确认、执行和恢复语义。

## E. Agent Native 绘图引擎

- EngineCatalog/Profile、EngineDataView、PlotDocument 与公共 Engine Action 是引擎公开合同。
- Matplotlib 和 Origin 是两个独立 backend；共享字段、对象和公共动作语义，不共享私有图元、最终几何或统一中间绘图语言。
- Origin backend 必须从官方模板/菜单/X-Function 创建原生对象，保存 OPJU 后用新会话重开读回。
- 任何其他 Agent 可以绕过 Pi，直接通过同一 Workflow/Engine 合同接入；仍受本地权限、版本与能力校验。

## F. 当前视觉范围

- 本轮只实现 T1：用户可直接看到并能由 Matplotlib 与 Origin 共同稳定表达、保存、读回的视觉元素。
- T1 包括：线、符号、填充、文字、坐标轴/刻度/网格、图例、连续色板、误差棒/误差带和数据标签。
- 连续量使用数值区间，不离散成少量按钮：字号、线宽、边框宽度、符号大小、透明度等均为连续参数。
- 视觉能力必须同时可由自然语言 TaskDraft 和前端控件驱动，最终进入相同 Engine Action。
- 不实现 T2/T3：Origin 专属高级外观、分析 App、任意对象树、任意 LabTalk/Origin C 属性和后端专属效果不进入公开能力。

## G. 交互

- 基本一轮为：用户输入自然语言、选择图类并上传/选择数据；Agent 展示字段绑定和参数确认卡；用户确认后执行。
- 确认卡显示前几行只读数据、列名上方字段角色、逐任务图类和视觉改动。
- 执行时显示真实阶段，例如读取数据、字段绑定、生成 TaskDraft、本地校验、渲染、保存版本和导出。
- 所有已提交改图都支持撤销/重做；错误必须说明失败阶段、影响范围和可执行恢复动作。

## H. 输出与安全

- 正式导出为 PNG、SVG、OPJU。OPJU 必须包含原生可编辑图和实际使用的数据对象。
- 导出目标路径只由桌面保存对话框授权，不属于 Agent 权限。
- 凭据只存 Windows Credential Manager；renderer 保持 sandbox/context isolation，无 Node integration。
- 远程模型不可用时，导入、手动字段映射、前端控件绘图/编辑和本地导出继续可用。

## I. 明确不做

- 不做组合图、多面板自由编排、科研图像、数据库/实时仪器流、任意单元格编辑、任意 Python/SQL/Shell、开放式分析/拟合或任意 Origin 对象属性。
- 不反向导入 OPJU，不用嵌入图片伪装原生可编辑图，不让 renderer 偷改数据或推断科研结论。
