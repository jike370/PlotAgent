# PlotAgent v3 渲染管线

> 当前范围：34张单图；Matplotlib和Origin各自使用每图独立renderer。不支持组合图。

## 执行链

```text
SourceDataset / PreparedDataset
        ↓ EngineDataView + FieldBinding
immutable PlotDocument
        ↓ validated EngineAction
profile-specific renderer
        ├─ Matplotlib → preview / PNG / SVG
        └─ Origin recipe → native OPJU
```

Pi或手动UI都不直接调用renderer。PlotAgent Core先验证profile、字段、对象、版本、权限、确认与动作，再进入同一渲染链。

## 共同语义

两端共享：数据版本、字段角色、系列身份、标题、轴语义、允许的系列样式、图例、图形参数和标注。两端不共享最终几何、artist、Origin对象路径或像素布局。

## Matplotlib

- 每图独立实现；
- 共享字体、色板、轴、图例、导出和边界工具；
- preview与formal export使用同一PlotDocument；
- 不为迁就Origin而退化成通用几何。

## Origin

- 每图绑定官方模板、菜单section或X-Function；
- 写入worksheet/matrix与designation后走官方创建入口；
- 只应用用户明确动作和已实证的必要T2配置；
- 保存前读回，另启全新Origin会话重开再读回；
- 禁止嵌入Matplotlib位图、手工近似专属图或回退旧renderer。

## 一致性

一致性指科学语义、数据身份、系列对象和用户编辑一致，不要求像素一比一。默认态分别遵循Matplotlib设计和Origin官方模板；Agent只开放两端都能稳定表达与读回的共同能力。

## 证据

机械通过不能自动写成视觉PASS。2026-08-12旧35图视觉页只作历史；本轮K06、X13、X38、X40发生变化，需当前提交的新视觉与正式UI证据。
