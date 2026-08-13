# PlotAgent v3 Agent Native 绘图引擎

> 当前基线：Pi 承担通用 Agent 运行循环；PlotAgent Core 负责领域约束、确认、版本与执行；34 张正式图各自拥有 Matplotlib renderer 与 Origin 官方模板绑定器。产品不支持组合图。

## 1. 产品结构

PlotAgent v3 是“绘图 Agent + 可独立接入的绘图引擎”，不是聊天壳，也不是开放式画布。

```text
用户目标、指定图类、数据
        ↓
Pi Agent runtime
        ↓ typed decision / tool call
PlotAgent Core
  ├─ 数据身份与字段契约
  ├─ 对象、权限、确认和版本
  ├─ 任务事务、恢复与审计
  └─ renderer 分派
        ↓
每图独立 renderer
  ├─ Matplotlib：PNG / SVG
  └─ Origin：官方模板 / 菜单 / X-Function → 原生 OPJU
```

Pi 可以替换，领域边界不能绕过。任何外部 Agent 也只能提交同一套强类型请求，由 Core 校验后执行。

## 2. 正式图形范围

正式范围是 34 张单图：

`K01 K02 K03 K04 K06 K07 K08 K09 K10 K11 K12 K13 K14 K15 K18 K19 K20 K21 K22 K24 S34 S61 X02 X03 X05 X09 X13 X23 X24 X35 X36 X38 X39 X40`

多面板组合图 `K25` 已从图形库、Agent capability、字段映射、契约、双后端、导出和验收清单删除。旧项目引用只返回 `CHART_TYPE_REMOVED`，不得创建近似图。

## 3. Renderer 设计原则

1. 每张图先核对 Origin 官方帮助、本机模板和菜单命令，再实现 renderer；禁止凭视觉猜结构。
2. Origin 默认态直接使用官方模板、菜单 dispatcher 或 X-Function；Python 只做数据适配、明确的图形参数和 Agent 编辑。
3. Matplotlib 与 Origin 共享语义契约，不共享几何实现，也不引入统一的中间绘图语言。
4. 默认样式尽量由模板管理；用户动作只修改被请求的对象。
5. 结构变化时允许从源数据重建图，并重放已验证的声明式编辑；不得回退到旧 renderer 或用位图伪装 OPJU。
6. OPJU 必须保留 worksheet、原生 plot/layer、数据绑定和可编辑对象。

## 4. Agent 可用动作

顶层动作保持少而强类型化：

- `create_plot`
- `bind_fields`
- `set_title`
- `set_axis`
- `set_series_style`
- `set_legend`
- `set_chart_parameter`
- `add_annotation`
- `export_plot`
- `undo` / `redo`

只开放 Matplotlib 与 Origin 都能稳定表达并读回的共同能力。后端专属枚举、任意脚本、任意统计分析和开放式数据变换不向 Agent 暴露。

## 5. 数据与图类契约

- 用户仍须选择图类；Agent 不在信息不足时擅自选图。
- Agent 可以提出字段绑定并生成确认卡；用户确认后才创建或修改版本。
- 数据层负责文件/工作表身份、类型识别、明确的宽长表适配和少量冻结计算。
- Renderer 不擅自排序、聚合、补列或改变科学含义。
- 预聚合与原始样本两种路径必须在图类契约中明确区分。

本轮黑盒问题对应的现行契约包括：双向误差棒使用绝对上下界；误差带使用中心/下界/上界；面积图、日期时间折线图和 Y 偏移堆叠线图支持 `series_1..series_N`；相关矩阵长表可适配为矩阵；蜂群图接受原始值与分组；前后对比图保留 Subject 与可选 Group 身份。

## 6. 可编辑产物

- PNG/SVG 是正式静态导出。
- OPJU 由 Origin 原生模板流程生成，不嵌入 Matplotlib 图片。
- 保存前与全新 Origin 会话重开后都要读回数据源、plot/layer 类型、Agent 编辑和文件身份。
- “文件存在”不等于可编辑通过；必须在 Origin 中打开、修改数据或样式、保存并重开验证。

## 7. 验收

资格分四层，不能互相替代：

1. 契约与单元测试；
2. Origin 原生结构、动态数据和 fresh-reopen 机械读回；
3. 34 图统一视觉审查；
4. 正式 Windows Electron 黑盒。

2026-08-12 的旧 35 图视觉审查包含现已删除的 K25。本轮又改变了 K06、X13、X38、X40 的当前实现，因此旧页面不能自动证明当前 34 图全部通过；这些变更图必须在新提交上复测。
