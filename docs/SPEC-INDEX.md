# PlotAgent v3 规格索引

## 当前权威文档

1. [PRD](./PRD.md)：产品目标、用户流程和范围。
2. [产品决策](./PRODUCT-DECISIONS.md)：不可回退的产品与工程决定。
3. [Agent Native 绘图引擎](./AGENT-NATIVE-PLOTTING-ENGINE.md)：Pi、Core 与 renderer 边界。
4. [成本感知 Agent 编排架构](./AGENT-ORCHESTRATION-ARCHITECTURE.md)：确定性快速路径、数据探索、TaskDraft、WorkflowRecipe 与分级 Agent 施工基线。
5. [Origin 视觉能力全集与覆盖矩阵](./ORIGIN-VISUAL-CAPABILITY-MATRIX.md)：Origin 能力、Matplotlib 等价性、当前缺口与 T1/T2/T3 边界。
6. [Origin 官方模板映射](./ORIGIN-OFFICIAL-TEMPLATE-MAPPING.md)：34 图逐图官方路线。
7. [Origin Recipes](./ORIGIN-RECIPES.md)：运行时 recipe 合同。
8. [绘图引擎验收基线](./PLOTTING-ENGINE-REFACTOR-ACCEPTANCE.md)：机械、视觉和黑盒门禁。
9. [黑盒能力说明](./PLOTAGENT-V3-BLACK-BOX-CAPABILITY.md)：只描述用户可见能力和边界。
10. [探索性黑盒功能简报](./PLOTAGENT-V3-EXPLORATORY-BLACK-BOX-BRIEF.md)：只提供用户可见功能和边界，不提供测试答案。
11. [冻结黑盒回归](./PLOTAGENT-V3-BLACK-BOX-ACCEPTANCE-HANDOFF.md)：正式 Windows Electron 回归执行清单。
12. [对话交互](./CONVERSATIONAL-INTERACTION.md)：确认卡、阶段反馈、撤销和错误恢复。
13. [发布门禁](./PERFORMANCE-TEST-RELEASE.md)：Beta qualification。

## 阅读规则

- 当前正式产品是 34 张单图；不支持组合图，K25 已删除。
- Pi 是可替换的通用 Agent runtime；PlotAgent Core 是领域权威。
- `AGENT-ORCHESTRATION-ARCHITECTURE.md`、`PI-AGENT-RUNTIME.md` 和 `TASK-RUNTIME.md` 共同描述当前单一 WorkflowRun/TaskDraft/TaskPlan 编排链。
- 历史 SEQ 报告、旧视觉页和 35/38/43/45 图资料只作追溯，不能覆盖当前权威文档。
- `chart-library-research.md` 是长期研究 taxonomy，不是当前目录。
