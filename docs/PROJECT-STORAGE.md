# PlotAgent v3 项目存储与数据导入

> 状态：项目 schema v3，2026-08-11。

## 1. 工作区

每个项目使用固定本机目录、SQLite 单写者和不可变 SHA-256 CAS。SQLite 保存元数据、版本、引用、对话和任务；大表与源文件进入 CAS。导入和正式状态提交使用事务，缓存可删除重建。

## 2. 数据

- `DataPreparationRecipe` 保存原始文件到规则数据表的非语义机械步骤、匹配合同、输出保证、不可变版本、用户作用域和健康状态；
- `SourceDataset` 保存源文件哈希、工作表/数据块身份、整理 Recipe/运行引用、字段、单位、来源坐标和版本；
- 原始数据只读；受控准备与固定计算产生新的不可变对象；
- renderer 只通过 `EngineDataView` 读取明确版本，不读取文件路径或导入器内部状态。

## 3. 绘图

新绘图状态使用两类表：

- `engine_plot_document_versions`：线性 PlotDocument 版本；
- `engine_plot_action_journal`：每个版本对应的公共动作、前后引用与时间。

项目 schema 以 DataPreparationRecipe/整理运行分表保存来源匹配、沙箱结果、正式整理和输出验证；以 WorkflowRun、WorkflowContext、TaskDraft、TaskPlan/TaskItem 与事件分表保存绘图提案、确认、执行位置、完整失败原因和可重试性。不存在保存整条绘图流程的 WorkflowRecipe。旧项目 schema 不在原文件上迁移；当前 build 只打开完整的受支持项目，避免双写和兼容分支污染权威状态。

个人 Recipe 库拥有 Recipe 内容和版本；项目只保存 Recipe ID/版本引用、运行 trace、输入结构摘要、输出对象和校验结果。Recipe 版本不可变，修订创建新版本；失败运行不能回写放宽原版本。用户删除/退役 Recipe 不删除项目中已经生成的 SourceDataset 和历史 provenance。

## 4. 导入

正式支持 CSV、Excel 与登记文本格式。上传、新 sheet/block、替换来源或重新整理自动触发 DataPreparationRecipe 结构匹配和有界沙箱试运行；唯一合格候选自动应用，同级候选由用户选择，全部失败时回退 Agent。多工作表/数据块分别形成可识别数据集；真正歧义必须给出明确澄清或拒绝，不能静默猜测。导入失败不污染 CAS 或项目状态。

Recipe 运行以源文件对象为输入，可原子登记该文件成功验证的一个或多个独立 SourceDataset。批量导入的事务边界按文件隔离：一个文件失败不回滚其他文件；同一文件内部若 Recipe 声明的输出保证不完整，则该文件本次整理整体不发布半成品。跨来源合并只由确认后的 DataOperation 产生 PreparedDataView。

Agent 辅助整理在确认前只保存 staging 对象和候选计划，不登记可见 SourceDataset、不推进项目版本。确认卡显示机械动作、输出结构和风险；确认后才一次性发布数据版本并可被后续 TaskItem 引用。放弃候选不产生可绘图数据或版本；下游 renderer 失败不回滚已发布的数据版本。重新整理创建新版本，旧版本只要仍被 PlotDocument/任务引用就保留。

## 5. 项目包与恢复

`.plotproj` 是项目快照，不是 OPJU。恢复时验证 schema、对象哈希和引用；未知版本默认拒绝。重开项目后可恢复数据身份、PlotDocument 最新版本、对话与未完成任务。

## 6. 非目标

- 不把项目数据库当开放 SQL 接口；
- 不执行工作簿宏、公式或外链；
- 不从 OPJU 反向更新项目；
- 不保留旧绘图状态作为隐藏 fallback。
