# PlotAgent v3 绘图执行管线

> 状态：35 个 Origin 可渲染 Profile 的现行执行与验收边界，2026-08-12。

## 1. 执行顺序

```text
公共 Engine Action
  → Profile 能力校验
  → PlotDocument 版本事务
  → EngineDataView 解析
  → Profile 专属 backend
  → 原生读回
  → 正式产物
```

不存在中间统一绘图语言、统一最终几何或跨 backend compiler。

## 2. 默认态

- Origin 默认态来自该 Profile 固定的官方模板；只写数据、designation 和模板需要的最小动态绑定。
- Matplotlib 默认态由该 Profile 的独立 renderer 负责。
- 模板本身已有的布局、坐标、图例和样式不由 Python 重画。

## 3. 编辑态

公共动作只开放两端都能稳定表达并读回的能力。动作执行后：

- PlotDocument 产生新版本；
- Matplotlib renderer 消费新版本生成预览/导出；
- Origin 在模板原生对象上做最小修改并重新打开验证；
- 任一 backend 不支持时在执行前拒绝，不静默忽略或近似替换。

## 4. 动态数据

每个 Profile 必须覆盖与其语义相关的行数、系列数、类别数、范围、缺失值和可选字段变化。动态布局属于 Profile 或模板自身行为；公共层只负责验证数据形状与身份，不替每张图决定图元。

## 5. 视觉与机械资格

- 机械资格：创建、代表性编辑、读回、fresh-reopen、数据哈希、对象类型与导出存在性。
- 视觉资格：由产品负责人逐图审查默认态和编辑态。
- 机械通过不能自动写成视觉 PASS；产品负责人已于 2026-08-12 独立确认当前 35/35 图视觉验收通过。

产物入口：`build/visual-audit/origin-recipe-renderer-35/index.html`。
