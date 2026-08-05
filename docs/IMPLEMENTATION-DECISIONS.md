# PlotAgent W2 实现决策记录

> 状态：M1/M2 数据与轻量项目核心实现记录  
> 日期：2026-08-05  
> 上位约束：`PROJECT-STORAGE.md`、`DATA-TRANSFORMS.md`、`LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md`、`TASK-RUNTIME.md`、`IMPLEMENTATION-PLAN.md`、`PRODUCT-DECISIONS.md`

本文只记录实现层选择，不改变产品决策或跨模块契约。若实现选择与权威文档冲突，以权威文档为准。

## ID-W2-001：W0 缺席时的协议边界

- 当前基线没有 `src/plotagent/contracts/` 或 W0 generated types。
- 本轮在 `plotagent.importing.models` 与 `plotagent.preparation.models` 中建立 `extra=forbid`、冻结、严格类型的本地协议边界。
- 不创建或修改 `contracts` 目录。未来 W0 到位时由独立变更迁移这些协议，不在本轮预建双份 schema。

## ID-W2-002：Excel 读取策略

- `.xlsx/.xlsm` 使用 `openpyxl` 的两个只读视图：公式视图只识别公式来源，`data_only` 视图只取文件已有缓存值。
- 两个视图都设置 `read_only=True`、`keep_links=False`、`keep_vba=False`；不计算公式、不刷新外链、不载入宏。
- `.xls` 使用单一轻量依赖 `xlrd>=2.0.1,<3`，只消费工作簿内已有值，不引入 Excel/LibreOffice 自动化。
- 多工作表默认形成独立 SourceDataset 候选；同一工作表多个等价区域只返回一次最小追问，不静默选择。

## ID-W2-003：文本检测与分层结果

- 编码只在 BOM/严格 UTF-8/UTF-16 特征/Windows-1252 的封闭顺序中检测，不使用概率模型。
- 分隔符、decimal、header 与 DataBlock 使用可解释、确定性的候选评分；同分时返回一个 clarification。
- InstrumentMetadata、DataBlock、postamble 分开保存；多个 DataBlock 各自形成候选，不自动拼接。
- 输出只有 imported、clarification、rejection；错误码按 sniff/detect/parse/validate 分层 trace。

## ID-W2-004：SourceDataset 表格表示

- 内存候选保存严格 schema、质量计数、稳定 field/source-row ID 与原始坐标。
- 正式列式表示使用 Parquet；数据字段以稳定 field ID 命名，来源坐标以保留前缀列写入。
- NaN、正负 Inf、missing、`0` 与 `False` 原样保留；质量摘要不使用 truthiness。
- Golden fixtures 由程序生成数据文件，但 `manifest.json` 的 oracle 与 SHA-256 在测试运行前冻结，测试不从解析器输出反推期望值。

## ID-W2-005：封闭 Preparation

- PreparationSpec 是六种 kind 的单个 discriminated union，不是步骤数组。
- 只实现 select、结构投影、显式同构纵向 concat、metadata 常量标签、显示顺序和绘图 mask。
- join、filter、dedupe、单位换算、任意公式及未知字段在 schema 边界直接拒绝，不提供 fallback。
- `exclude_with_report` 只产生 mask 和排除原因；SourceDataset 行和值永不修改。
