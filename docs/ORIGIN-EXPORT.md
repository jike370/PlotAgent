# PlotAgent v3 Origin 导出契约

> 状态：官方模板优先的原生 OPJU 导出，2026-08-11。

## 1. 目标

OPJU 必须包含实际绘图数据、worksheet/matrix、graph、layer、plot、坐标轴、图例和注释等原生对象，可脱离 PlotAgent 在 Origin 中继续编辑。嵌入 PNG 或未链接图元不算通过。

## 2. 执行模型

每个 Origin Profile 固定：官方模板文件与哈希、数据布局、列 designation、允许修改的原生对象、动态绑定逻辑和读回断言。执行器只消费 `EngineRenderSource`，不接收模型脚本或任意属性字符串。

默认态直接加载官方模板。代表性编辑只修改公共动作明确要求的对象。K25 使用 Origin 原生 graph merge 保留子图数据与图层，不把页面栅格化。

## 3. 安全边界

- 模板来自 build-pinned 目录并校验哈希；
- 不执行用户、模型或数据提供的 LabTalk/Python/Origin C；
- 不修改用户全局模板；
- 自动化只控制自己启动的 Origin 实例；
- 目标文件用临时路径构建、验证后原子替换。

## 4. 验证

每次正式导出必须完成：

1. build 后原生对象读回；
2. 保存 OPJU；
3. 新受控 Origin 会话 fresh-reopen；
4. 再次核对数据、图对象和公开编辑状态；
5. 记录文件哈希、大小和读回摘要。

当前 Origin/OPJU 正式范围为35图；核密度图、Kaplan–Meier生存曲线、森林图稳定拒绝。机械读回通过不等于视觉通过。

## 5. 非目标

- 不读取或合并用户修改后的 OPJU；
- 不承诺在 Origin 中重跑 PlotAgent 的固定计算；
- 不复制无关项目数据、对话或凭据；
- 不为追求像素一致重建模板内部全部图元。
