# PlotAgent v3 当前实施计划

> 状态：Agent Native 引擎重写后的唯一实施顺序，2026-08-11。

## 已完成

1. 保留导入、数据版本、项目存储、ProjectContext 与 Agent 任务编排。
2. 删除旧绘图 compiler、解析计划、旧 Origin renderer 与旧 Schema。
3. 建立 EngineDataView、PlotDocument、九类公共动作和能力目录。
4. 接通 Desktop Core、手动 UI 与内置 Agent 客户端。
5. 完成 35 个 Origin 可渲染图的独立 Matplotlib renderer 与 Origin 官方模板绑定器；核密度图、Kaplan–Meier 生存曲线、森林图稳定拒绝。
6. 完成 35 图默认/代表性编辑机械读回和统一视觉审查页。
7. 产品负责人于 2026-08-12 确认 35/35 图视觉验收通过。

## 下一步顺序

1. 正式 Electron 黑盒验证导入、公共编辑、Agent 计划、批量/部分失败恢复、重启、K25 与三格式导出。
2. 对黑盒失败做最小修正并复测；证据不足保持 UNVERIFIED。
3. 完成性能、安装包、签名和唯一支持 Origin 版本的发布门禁。

## 并行边界

- Profile 修复可按图并行；Origin COM 实机任务必须串行。
- Agent 质量评测可与人工视觉审查并行，但不能替代它。
- 前端体验改进不得新增绕过公共动作的私有绘图状态。

## 完成条件

35 图人工视觉签名已经完成。正式发布仍要求桌面黑盒证据和发布门禁全部通过；三个稳定拒绝项不得计入通过数。
