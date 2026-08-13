# PlotAgent v3 领域契约

> 状态：Agent Native 绘图引擎公共契约，2026-08-11。

## 1. 数据合同

- `SourceDataset`：不可变导入结果，保存版本、字段、单位、来源坐标与内容哈希。
- `PreparedDataset` / 固定计算结果：受控派生数据，保存输入、参数和哈希。
- `EngineDataView`：renderer 使用的矩形只读视图；列具有稳定 ID、可读名称、类型、单位和值。
- `EngineDataRef`：PlotDocument 对数据版本的不可变引用。

renderer 不读取导入器内部对象，也不写回原始数据。

## 2. 绘图合同

`EngineProfile` 声明：Profile ID、字段角色、可重复角色、数据来源类型、语义对象和公共能力。

`PlotDocument` 是绘图状态的唯一领域真值：

- `plot_id / plot_version / parent_version`；
- `profile_id`；
- 数据引用与字段绑定；
- 精确组件版本；
- 已应用动作 ID。

它不包含 backend artist、Origin 对象 ID、脚本或最终布局。

## 3. 公共动作

九类动作组成封闭判别联合：

1. `create_plot`
2. `bind_fields`
3. `set_title`
4. `set_axis`
5. `set_series_style`
6. `set_legend`
7. `set_chart_parameter`
8. `add_annotation`
9. `export_plot`

每个变更动作包含稳定 `action_id`、精确 target 和期望图版本。Profile 能力目录在调用 backend 前验证字段、对象类型、参数名、范围与支持性。未声明能力必须稳定拒绝。

## 4. 后端端口

`PlotBackend` 只接受 `EngineRenderSource`，返回 `EngineReadback` 与正式 `EngineArtifact`。读回记录文档版本、数据哈希、对象状态和 backend 原生证据。Matplotlib 与 Origin 可使用不同内部结构，但不能改变字段身份、系列身份或动作语义。

## 5. Agent 接入

绘图引擎对 Agent 中立。客户端先读取能力目录和动作 Schema，再提交公共动作。内置 Agent 可用 `ProjectContextSnapshot` 将安全别名绑定为动作；其他 Agent 可以自行完成计划与对象解析，直接提交完全相同的动作。

模型响应永远不是领域真值。只有本地校验并提交后的 PlotDocument、动作日志和任务状态才是权威状态。

## 6. 任务合同

任务计划保存提案、已绑定动作、预期项目 revision、确认状态、下一动作位置和失败码。成功动作不会因恢复执行而重复；失败后从首个未完成动作继续。确认前不产生绘图副作用。

## 7. 版本与兼容

- SourceDataset、PlotDocument、项目 revision 和任务计划分别版本化；
- 写入采用线性版本与乐观并发；
- 旧绘图编译对象不属于当前 Schema，也不作为兼容 fallback；
- 已知项目升级只保留数据、项目与 Agent 运行时，移除旧绘图状态。
