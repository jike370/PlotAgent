# PlotAgent 规格索引

> 本索引只列当前权威文档。历史提交交接、阶段资格报告、旧视觉审计和已被现架构替代的设计稿不留在 `docs/` 中。

## 1. 产品与交付

1. [PRD](./PRD.md)：当前用户目标、流程、范围和非功能要求。
2. [产品决策](./PRODUCT-DECISIONS.md)：不可由实现自行改写的产品边界。
3. [施工、测试与发布路线](./IMPLEMENTATION-PLAN.md)：从范围冻结到发布判定的唯一顺序。
4. [产品测试覆盖审计](./PLOTAGENT-PRODUCT-TEST-COVERAGE-AUDIT.md)：各测试层证明什么、当前缺口和 P0/P1/P2。
5. [Beta 性能测试与发布门禁](./PERFORMANCE-TEST-RELEASE.md)：冻结候选与最终发布条件。
6. [发布候选已知问题](./PLOTAGENT-V3-RELEASE-CANDIDATE-KNOWN-ISSUES.md)：当前仍未关闭的问题，不收录已经实现的事项。
7. [黑盒能力说明](./PLOTAGENT-V3-BLACK-BOX-CAPABILITY.md)：供测试者使用的当前用户可见能力，不包含历史结果。

## 2. Agent、任务与数据

1. [程序—Agent 编排架构](./AGENT-ORCHESTRATION-ARCHITECTURE.md)：自然语言、上下文、工具、TaskIntent/TaskPlan 与确认边界。
2. [Pi Agent 运行适配](./PI-AGENT-RUNTIME.md)：可替换模型—工具循环和 Core 权威。
3. [Agent 任务状态合同](./PLOTAGENT-AGENT-TASK-STATE-CONTRACT.md)：规划、追问、确认、执行、修复、取消和恢复语义。
4. [Agent 任务状态测试矩阵](./PLOTAGENT-AGENT-TASK-STATE-MATRIX.md)：不调用真实模型的确定性生命周期门禁。
5. [Durable Agent Task 与 TaskPlan](./TASK-RUNTIME.md)：任务对象、执行、持久化和恢复。
6. [数据工具与来源追溯](./DATA-TRANSFORMS.md)：原始数据检查、受控操作、预演和血缘。
7. [固定绘图计算](./ANALYSIS-ENGINE.md)：与图形不可分割的封闭计算及开放分析边界。

## 3. 绘图引擎与后端

1. [Agent Native 绘图引擎](./AGENT-NATIVE-PLOTTING-ENGINE.md)：Engine Profile、公共动作和双后端边界。
2. [后端架构](./BACKEND-ARCHITECTURE.md)：本地引擎服务、版本事务和公开入口。
3. [领域契约](./DOMAIN-CONTRACTS.md)：SourceDataset、EngineDataView 与 PlotDocument。
4. [渲染管线](./RENDERING-PIPELINE.md)：Matplotlib/Origin 独立 renderer 和输出路径。
5. [Origin 官方模板映射](./ORIGIN-OFFICIAL-TEMPLATE-MAPPING.md)：34 图逐图官方创建路线。
6. [Origin Recipes](./ORIGIN-RECIPES.md)：模板、菜单、X-Function、原生读回与 fresh-reopen。
7. [Origin 视觉能力矩阵](./ORIGIN-VISUAL-CAPABILITY-MATRIX.md)：T1 公共能力和 T2/T3 边界。
8. [Origin OPJU 导出](./ORIGIN-EXPORT.md)：原生可编辑产物合同。

## 4. 桌面、存储与安全

1. [任务型对话与交互](./CONVERSATIONAL-INTERACTION.md)：时间线、确认卡、阶段反馈和聚焦编辑。
2. [项目存储与导入](./PROJECT-STORAGE.md)：schema v7、CAS、导入、迁移和项目包。
3. [本地安全与诊断](./LOCAL-SECURITY-DIAGNOSTICS.md)：网络模式、Electron、本地文件与诊断边界。

## 5. 阅读规则

- 正式产品固定为 34 张单图；不支持组合图，删除图类只保留稳定墓碑。
- 当前自然语言任务统一进入 Pi/Core durable task 主链；旧 workflow RPC 和历史 Agent Foundation 阶段文档不构成产品能力。
- 当前公开能力以 Engine Profile 目录、PRD 和黑盒能力说明三者的交集为准；底层仍存在但没有 Profile/UI 入口的类型不算公开能力。
- 历史 commit、旧视觉页和历史测试目录只用于 Git/产物追溯，不得覆盖当前文档或当前候选证据。
