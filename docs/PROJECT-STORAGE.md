# PlotAgent v3 项目存储与数据导入

> 状态：项目 schema v7，2026-08-21。

## 1. 工作区

每个项目使用固定本机目录、SQLite 单写者和不可变 SHA-256 CAS。SQLite 保存元数据、版本、引用、对话和任务；大表与源文件进入 CAS。导入和正式状态提交使用事务，缓存可删除重建。

## 2. 数据

- `SourceDataset` 保存源文件哈希、工作表/数据块身份、字段、单位、来源坐标和版本；
- 原始数据只读；受控准备与固定计算产生新的不可变对象；
- renderer 只通过 `EngineDataView` 读取明确版本，不读取文件路径或导入器内部状态。

## 3. 绘图

新绘图状态使用两类表：

- `engine_plot_document_versions`：线性 PlotDocument 版本；
- `engine_plot_action_journal`：每个版本对应的公共动作、前后引用与时间。

schema v7 同时保存 WorkflowRun 投影与 durable Agent task ledger：TaskEnvelope、TaskIntent、TaskPlan、ExecutionGrant、事件、checkpoint、tool receipt、VerificationReport、逐项结果和可重试性。正式桌面以 Agent task ledger 为任务权威；旧 workflow RPC 和 Recipe save/replay 不属于公开入口。

## 4. 导入

正式支持 CSV、Excel 与登记文本格式。多工作表/数据块分别形成可识别数据集；真正歧义必须给出明确澄清或拒绝，不能静默猜测。导入失败不污染 CAS 或项目状态。

## 5. 项目包与恢复

`.plotproj` 是项目快照，不是 OPJU。恢复时验证 schema、对象哈希和引用；导入项目包要求当前 v7。已登记在本机的 v5/v6 工作区可在单一事务中追加 v7 所需任务表并更新版本；其他版本稳定拒绝。重开项目后可恢复数据身份、PlotDocument 最新版本、对话与安全 checkpoint。

## 6. 非目标

- 不把项目数据库当开放 SQL 接口；
- 不执行工作簿宏、公式或外链；
- 不从 OPJU 反向更新项目；
- 不保留旧绘图状态作为隐藏 fallback。
