# PlotAgent 外部 Agent 绘图引擎接口

> 状态：`codex/external-engine-sdk-mcp` 独立分支正在实现；不属于当前桌面候选，未完成本文件第 8 节资格前不得宣称正式交付。
>
> 适用范围：外部 Agent 通过 MCP 或 SDK 使用当前 34 图 PlotAgent 绘图引擎。
>
> 本文不继承旧 `codex/external-engine-interfaces` 分支的 35 图实现与资格结论；旧分支只用于参考协议、安全和等价测试方法。

## 1. 产品目标

PlotAgent 桌面版由内置 Pi Agent 使用绘图引擎；外部接入时，由外部 Agent 直接使用同一绘图引擎。

```text
PlotAgent 桌面版
用户 → 内置 Pi Agent → PlotAgent Core / 绘图引擎

外部 Agent 接入
用户 → 外部 Agent → MCP → PlotAgent Core / 绘图引擎

Python 程序接入
业务代码或 Agent runtime → SDK → PlotAgent Core / 绘图引擎
```

MCP/SDK 默认不再嵌套第二个 PlotAgent Agent。外部 Agent 保持用户对话、任务规划、追问、确认和下一步决策权；PlotAgent 提供领域能力、确定性执行、版本与产物验证。

未来可以单独设计“整项任务委托给 PlotAgent”的高级入口，但它不是当前 MCP/SDK 默认合同，也不能与直接引擎入口混为一谈。

## 2. 外部 Agent 与 PlotAgent 的职责

外部 Agent 负责：

1. 理解用户自然语言和目标；
2. 选择要检查的数据来源；
3. 根据检查结果决定数据整理步骤；
4. 选择 34 图闭集中的图类；
5. 决定字段绑定和公开视觉参数；
6. 向用户追问并展示确认内容；
7. 根据创建、读回和用户反馈继续修改；
8. 决定何时导出和交付。

PlotAgent 引擎负责：

1. 在授权范围内读取数据 schema、真实样本、单位和来源；
2. 提供强类型、可预演的数据整理操作；
3. 提供图类目录、字段要求、对象和公共编辑能力；
4. 校验数据、字段绑定、版本和绘图参数；
5. 调用 Matplotlib 或 Origin renderer 创建真实图；
6. 持久化 PlotDocument 和单调版本；
7. 读回实际标题、坐标轴、系列、图例、数据绑定和 Origin 对象；
8. 导出并验证 PNG、SVG、原生 OPJU；
9. 返回稳定错误、恢复信息、文件大小和哈希。

外部 Agent 不直接获得任意 Python、Shell、Matplotlib、LabTalk、Origin C、文件系统或 Origin 对象树权限。MCP/SDK 不能绕过 Engine Profile、版本、确认和授权边界。

## 3. MCP、SDK 与 API 的角色

### 3.1 MCP

MCP 是面向 Agent Host 的标准工具入口。Agent 可以发现工具及其强类型参数，在一次任务中反复观察、调用和决策。MCP server 只适配引擎合同，不维护第二套图类、renderer 或数据规则。

### 3.2 SDK

SDK 是同一能力的代码入口，供 Python Agent、Notebook 服务或同进程业务程序直接调用。SDK 与 MCP 必须返回相同的领域对象、错误码、版本和 readback；SDK 不能拥有 MCP 没有的绘图语义。

### 3.3 HTTP API

HTTP API 是可选的语言无关应用接口，不是当前外部 Agent 接入的第一优先级。若后续提供，它仍须复用 SDK/Core 合同，不直接暴露公网，也不能成为第四套行为。

## 4. 默认 MCP 能力面

默认工具面保持少而完整。当前分支将项目生命周期保留为显式工具，把数据视图的
`stage/apply/inspect/preview/commit` 五种动作合并为一个强类型工具，避免为每个数据操作
增加顶层工具。领域能力与实现工具的映射如下：

| 能力 | 目的 | 关键返回 |
| --- | --- | --- |
| `inspect_data` | 查看授权数据的结构、样本、类型、单位和来源 | 稳定 source/field ref、真实样本、问题列表 |
| `prepare_data` | 预演或提交筛选、排序、转换、合并、对齐和单位换算 | PreparedDataView、血缘、输入/输出摘要 |
| `list_chart_capabilities` | 查询 34 图目录、字段要求和公共编辑能力 | chart/profile、required roles、actions |
| `validate_plot` | 在产生副作用前验证数据、绑定、参数和目标版本 | validation report、精确缺口、可恢复动作 |
| `create_plot` | 按结构化图类、字段绑定和参数创建图版本 | project/plot ref、version、preview、readback |
| `inspect_plot` | 读取当前图的实际数据绑定和视觉对象 | PlotDocument、backend readback、capabilities |
| `edit_plot` | 对稳定 plot ref 应用公开编辑并创建新版本 | 新版本、动作、readback、可撤销性 |
| `export_plot` | 导出 PNG、SVG 或原生 OPJU | 路径、格式、大小、哈希、原生验证 |
| `get_project` / `get_plot` | 重启后恢复项目和继续编辑 | 当前版本、历史、产物和任务状态 |

当前实现中的正式工具名为：

- 项目：`plotagent_projects`、`plotagent_create_project`、`plotagent_open_project`；
- 数据：`plotagent_import_dataset`、`plotagent_datasets`、`plotagent_inspect_data`、`plotagent_data_view`；
- 图：`plotagent_chart_capabilities`、`plotagent_validate_action`、`plotagent_execute_action`、`plotagent_plots`、`plotagent_get_plot`、`plotagent_restore_plot`；
- 交付：`plotagent_export_plot`；另有无副作用的 `plotagent_health`。

`plotagent_execute_action` 使用 Engine Action 判别联合表达创建或编辑，不拆成几十个样式
工具。外部 Agent 必须先读取真实 field/profile/plot version；MCP 不解析自然语言，也不启动
内置 Pi。

数据处理、renderer 私有方法和 Origin 自动化步骤是内部实现，不逐项作为顶层 MCP 工具暴露。外部 Agent 可以看到公开数据操作及其结果，但不需要拼接 renderer 内部命令。

## 5. 产物合同

一次成功绘图产生两个必须同时存在的核心对象。

### 5.1 Agent 可继续操作的图实例

PlotAgent 持久化项目、稳定 plot ref、内部 plot id 和单调版本。外部 Agent 使用引用继续检查、编辑、撤销或导出，不通过解析文件名或聊天文本寻找目标。

```json
{
  "project_id": "project:...",
  "plot_ref": "@图1",
  "plot_id": "plot:...",
  "version": 3,
  "chart_id": "X38",
  "chart_name": "Y偏移堆叠线图"
}
```

### 5.2 用户可带走的原生交付物

Origin 后端的主要交付物是原生 OPJU：

- 包含实际使用的数据表、图页、layer、plot 和数据绑定；
- 不是嵌入 Matplotlib 位图；
- 用户可以在 Origin 中修改数据、标题、坐标轴、系列和图例；
- 保存、关闭和全新 Origin 会话重开后仍然有效；
- PlotAgent 导出前后可以机械读回关键对象。

PNG/SVG 是伴随预览和静态交付，不替代 OPJU 的可编辑性。

## 6. 绘图结果包

MCP/SDK 不能只返回“调用成功”或一个文件路径。完成结果至少包含：

```json
{
  "status": "completed",
  "project_id": "project:123",
  "plot_ref": "@图1",
  "plot_id": "plot:...",
  "version": 3,
  "chart": {
    "id": "X38",
    "name": "Y偏移堆叠线图"
  },
  "data_preparation": [],
  "field_bindings": {},
  "readback": {
    "backend": "origin",
    "verified": true
  },
  "artifacts": {
    "opju": {
      "path": "D:/outputs/图1-X38-Y偏移堆叠线图-v3.opju",
      "editable": true,
      "size_bytes": 30291,
      "sha256": "..."
    },
    "png": {
      "path": "D:/outputs/图1-X38-Y偏移堆叠线图-v3.png",
      "sha256": "..."
    },
    "svg": {
      "path": "D:/outputs/图1-X38-Y偏移堆叠线图-v3.svg",
      "sha256": "..."
    }
  }
}
```

结果中的路径必须位于明确授权的输出根；外部 Agent 不能自行指定任意本机位置。数据处理、字段绑定、动作、版本、readback 和文件哈希必须可追溯。

## 7. 长任务与确认

MCP 工具调用不能通过长时间阻塞伪装完整任务。数据量大或需要 Origin 时，接口使用持久任务状态：

- `running`：返回 task id 和真实阶段；
- `needs_input`：返回结构化缺口，由外部 Agent 询问用户；
- `confirmation_required`：返回可读计划、数据预览和一次性确认凭证；
- `completed`：返回图实例和结果包；
- `failed` / `cancelled`：返回稳定原因、影响范围和恢复动作。

是否向用户确认由外部 Agent 的产品交互承担；PlotAgent Core 仍负责确认凭证、授权范围、版本和执行事务，不能因外部 Agent 使用 MCP/SDK 而取消确认边界。

## 8. 验收标准

外部接口验收不是“工具能够被发现或调用”。当前 34 图基线至少需要：

1. 从构建产物安装 SDK、启动 MCP stdio，并通过官方协议完成 initialize、工具发现和调用；
2. SDK 与 MCP 对相同数据、动作和版本产生相同 PlotDocument、错误和 readback；
3. 外部 Agent 可以查看真实数据、选择图类、整理数据、绑定字段、创建、检查、编辑和导出；
4. 单图、多来源同图和批量多图的代表任务均不要求外部 Agent 接触内部 workflow/renderer ID；
5. 版本冲突、越界路径、非法动作、停止、失败恢复和重启续作无副作用；
6. PNG/SVG 文件真实存在并匹配返回哈希；
7. Windows + Origin 环境中生成 OPJU，打开后数据表和图页原生可编辑，修改、保存和 fresh-reopen 持久；
8. 至少一个真实外部 Agent Host 从自然语言目标出发完成多轮工具调用，而不是只用测试代码直接调用最终动作；
9. 接口层不维护第二套图类、数据合同或 renderer；当前 34 图共享引擎门禁继续全绿。

## 9. 当前交付状态

- 当前桌面候选已经交付并验证内置 Agent + 本地绘图引擎主链。
- `codex/external-engine-sdk-mcp` 从已验收桌面提交 `b6cea2d` 分出，新增 `plotagent.sdk`、
  `plotagent.mcp_server` 和外部专用 extension core；未修改 Electron、桌面 RPC、内置 Pi、
  Engine Profile 或 renderer。
- SDK 使用调用者提供的独立 engine root；MCP 另外限制 import roots 和 export root。外部
  数据整理复用正式 `StagedDataWorkspace`/`EngineDataViewRepository`，但不注册为桌面 RPC。
- 当前确定性增量已覆盖 SDK 生命周期、真实导入/检查、34 图目录、无副作用验证、确定性
  数据整理到 renderer、版本持久化、PNG 导出、路径隔离、MCP 工具发现、stdio initialize
  以及 SDK/MCP 目录等价；完整套件、构建产物安装、OPJU live/fresh-reopen 和真实外部 Agent
  Host 尚待本分支后续门禁。
- 旧 `codex/external-engine-interfaces` 分支曾验证 35 图时期 SDK/HTTP/MCP 的协议可行性，但它早于当前 34 图 renderer、数据、Agent、版本和导出合同，不得直接合入或复用 GO 结论。
- 本分支始终以当前 Core/Engine Profile 为唯一真源；若外部能力可在 extension core 完成，
  不改桌面路径。只有共享缺陷且桌面同样受益时，才允许另行评审共享改动。
