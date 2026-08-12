# PlotAgent v3 规格索引

> 状态：Agent Native 绘图引擎现行文档入口，2026-08-11。

## 权威顺序

1. 用户最新明确决定；
2. [产品决策](./PRODUCT-DECISIONS.md) 与 [PRD](./PRD.md)；
3. 本页列出的当前领域契约；
4. 研究、差距审计和历史实施记录仅供追溯，不指导实现。

## 当前领域契约

| 文档 | 权威范围 |
|---|---|
| [后端架构](./BACKEND-ARCHITECTURE.md) | Agent 中立引擎、进程与依赖方向 |
| [领域契约](./DOMAIN-CONTRACTS.md) | EngineDataView、PlotDocument、公共动作和版本 |
| [Agent Native 引擎基线](./AGENT-NATIVE-PLOTTING-ENGINE.md) | 重写取舍、正式35图、删除墓碑与内置 Agent 位置 |
| [绘图执行管线](./RENDERING-PIPELINE.md) | 每图 renderer、模板、动态数据和视觉门禁 |
| [Origin 导出](./ORIGIN-EXPORT.md) | 原生 OPJU、安全与 fresh-reopen |
| [Origin 模板映射](./ORIGIN-OFFICIAL-TEMPLATE-MAPPING.md) | 正式35图—Origin官方模板与流程映射 |
| [项目存储](./PROJECT-STORAGE.md) | 数据、CAS、项目 schema v3 与动作日志 |
| [数据准备](./DATA-TRANSFORMS.md) | 受控派生数据与来源追溯 |
| [Agent 上下文](./AGENT-CONTEXT-AND-PROVIDERS.md) | ProjectContext、模型和披露边界 |
| [任务运行时](./TASK-RUNTIME.md) | 确认、部分失败与恢复 |
| [验收基线](./PLOTTING-ENGINE-REFACTOR-ACCEPTANCE.md) | 机械、视觉、黑盒与发布 Gate |
| [黑盒能力说明](./PLOTAGENT-V3-BLACK-BOX-CAPABILITY.md) | 外部验收可见功能与边界，不披露内部实现 |
| [黑盒验收交接](./PLOTAGENT-V3-BLACK-BOX-ACCEPTANCE-HANDOFF.md) | 正式桌面验收步骤、冻结输入、证据与判定模板；产品代码基线为`3dc154c` |

## 历史材料

`FRONTEND-P0-DIFFERENTIATION-SEQUENCE.md`、`SEQ-10-FRONTEND-GAP-AUDIT.md`、`chart-library-research.md` 和旧决策段落只记录探索过程。若与上述现行契约冲突，以现行契约为准。
