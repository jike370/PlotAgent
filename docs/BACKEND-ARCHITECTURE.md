# PlotAgent v3 后端架构

> 状态：Agent Native 绘图引擎现行架构，2026-08-11。

## 1. 产品边界

PlotAgent v3 由两部分组成：可被任意 Agent 调用的本地科研绘图引擎，以及作为一个客户端接入该引擎的内置 Agent。引擎不依赖模型供应商、提示词或内置 Agent 的决策类型。

```text
任意 Agent / 内置 Agent / 手动 UI
              |
              v
能力目录 + 公共 Engine Action Schema
              |
              v
本地校验、版本事务、动作日志
              |
              v
PlotDocument + EngineDataView
        |                    |
        v                    v
每图 Matplotlib renderer   每图 Origin 官方模板绑定器
        |                    |
        v                    v
     PNG / SVG          原生可编辑 OPJU
```

## 2. 保留的基础设施

- 安全导入、不可变 SourceDataset、字段与来源坐标；
- 项目工作区、CAS、SQLite 单写者、项目包与重启恢复；
- DataPreparationRecipe、WorkflowRun、WorkflowContext、TaskDraft 与 TaskPlan；
- Pi Provider、只读数据检查预算、部分失败、恢复执行、幂等与任务事件；
- Electron Main/Preload/Renderer 安全边界和资源授权；
- 受控数据准备与确定性固定计算。

这些服务通过稳定数据引用与公共动作连接绘图引擎，不了解后端图元。

## 3. Agent Native 引擎

引擎的公共入口是：

- `engine.catalog.get`：返回 Profile、字段角色、对象别名、能力和动作 JSON Schema；
- `engine.actions.execute`：校验并执行一条公共动作；
- `engine.plots.list/get`：读取版本化 PlotDocument；
- `engine.exports.execute`：导出 PNG、SVG 或 OPJU。

动作集合为 `create_plot`、`bind_fields`、`set_title`、`set_axis`、`set_series_style`、`set_legend`、`set_chart_parameter`、`add_annotation`、`export_plot`。任何 Agent 都可以直接按 Schema 调用；内置 Agent 的别名绑定器不是必经路径。

## 4. 数据与存储

`EngineDataView` 是 renderer 唯一可见的数据输入。`PlotDocument` 只保存图 ID、线性版本、Profile、不可变数据引用、字段绑定、组件引用与已应用动作 ID。每次非导出动作创建一个新版本，并与原动作原子写入动作日志。

项目 schema 保存 SourceDataset/CAS、DataPreparationRecipe/整理运行与 WorkflowRun/TaskDraft/TaskPlan 权威表，并持久化完整来源和任务失败语义。DataPreparationRecipe 与绘图 Workflow 分开：前者只产生规则数据表，后者从规则数据表开始规划绘图。旧 schema 原文件保持不变并明确拒绝打开，不存在迁移、双写或 fallback。

## 5. 后端

- Matplotlib：每个正式 Profile 使用独立 renderer，共享安全字体、输出和有限基础工具。
- Origin：每个正式 Profile 使用固定官方模板与最小原生绑定逻辑；OPJU 必须保存原生数据和图对象并通过 fresh-reopen 读回。
- 两端只共享公开语义与动作，不共享最终几何，也不通过统一 compiler 互相翻译。

## 6. 禁止项

- 模型输出 Python、Matplotlib、LabTalk、Origin 对象路径或任意属性；
- renderer 改变数据、偷偷拟合、选择图形或推断科研语义；
- 用旧编译链、旧解析计划或静默 fallback 冒充 Profile 成功；
- 把内置 Agent 的提示词、供应商协议或别名模型嵌入绘图引擎。
