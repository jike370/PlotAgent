# Agent Native 绘图引擎验收基线

> 状态：代码重写和 35 图 Origin 机械资格完成；3 图明确拒绝；产品负责人已确认 35/35 图视觉验收通过，正式桌面黑盒待执行。

## 1. 验收对象

验收的是“可供任意 Agent 调用的绘图引擎”，不是某个模型的提示词效果。内置 Agent 另行验证其计划质量和项目上下文能力。

## 2. Gate

### Gate A：旧体系清除

- 生产源码不含旧绘图 compiler、resolver、共享最终 plan 或旧 Origin renderer；
- 新项目不创建旧绘图表；项目 v3 升级移除旧绘图状态；
- 前端、RPC、Schema 和现行文档不再暴露旧对象。

### Gate B：公共接入

- 不启动内置 Agent 也能读取能力目录并提交九类公共动作；
- 非法字段、对象、版本和参数在 backend 前拒绝；
- 动作 Schema 不包含 Python、Matplotlib、Origin 脚本或对象路径。

### Gate C：35 图纵向能力

- 每图有独立 Profile、Matplotlib renderer 和 Origin 官方模板绑定器；
- 默认态与代表性编辑态均可生成；
- Origin OPJU 通过 build/fresh-reopen；
- 动态数据测试覆盖 Profile 声明的变化。

### Gate D：状态与恢复

- PlotDocument 和动作日志原子持久化；
- 版本冲突、幂等、部分失败和恢复执行可验证；
- 项目重开后恢复数据身份、图版本和任务状态。

### Gate E：视觉

- 产品负责人逐图审查默认态和代表性编辑态；
- 只允许 `PASS / FAIL / BLOCKED / UNVERIFIED`；
- “执行成功”与“有截图”都不能自动等于 PASS。

### Gate F：正式桌面黑盒

只能经正式 Electron UI 和用户可见导出产物验收。源码、单测、静态视觉页不能替代黑盒证据。

## 3. 当前证据

- 35/35 机械通过，35/35 视觉已于 2026-08-12 签名通过；
- 核密度图、Kaplan–Meier 生存曲线、森林图在 OriginRecipe 选择阶段明确拒绝；
- 审查页：`build/visual-audit/origin-recipe-renderer-35/index.html`；
- 默认/编辑 contact sheet 与每图 OPJU/PNG/readback 位于同目录；
- 当前无签名安装包，正式开发入口为仓库根目录执行 `pnpm dev`。
