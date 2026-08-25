# PlotAgent SDK / MCP 独立分支资格报告

> 分支：`codex/external-engine-sdk-mcp`
>
> 实现提交：`5c7f0cf`、`f66fba5`
>
> 基线：`b6cea2d`
>
> 日期：2026-08-26

## 1. 结论

当前分支已经形成可安装、可调用的本地 Python SDK 与 MCP stdio 入口。两者复用当前
34 图 Core/Engine/Profile/renderer，不启动内置 Pi，也不维护第二套绘图语义。

本分支没有修改 Electron、renderer 前端、桌面 RPC 注册、内置 Pi、Engine Profile 或任一
图类 renderer。外部调用使用独立 engine root；MCP 另外限定 import roots 与 export root。
桌面版不会加载 `plotagent.sdk` 或 `plotagent.mcp_server`。

当前判定为：

- **SDK/MCP 本地引擎 V1：PASS**；
- **当前桌面候选：不受本分支影响，仍以原候选证据为准**；
- **合并/正式发布：尚未判定**。仍需一个真实外部 Agent Host 的自然语言多轮调用验收，
  以及决定 SDK/MCP 以独立 wheel 还是随桌面安装包附带。

## 2. 实现边界

直接复用共享 Core：

- 项目创建、打开、单写者锁与重启恢复；
- CSV/TSV/TXT/DAT/Excel 导入、字段类型、单位、元数据与样本；
- 34 图 Engine Catalog、PlotDocument、公共动作、版本冲突与 readback；
- Matplotlib PNG/SVG 和 Origin 原生 OPJU renderer；
- 项目数据视图、图版本与导出哈希持久化。

仅存在于 external extension core：

- 外部数据工作区的 stage/apply/inspect/preview/commit；
- 稳定且重启可恢复的外部 `@图N` 显示引用；
- MCP import/export 根路径授权；
- SDK 错误包装与 MCP 结构化结果。

没有复制完整 Core，也没有复制 renderer。external extension core 只在 SDK 构造时加载，
桌面 `DesktopApplication` 的服务表和项目 schema 不变。

## 3. 公开入口

Python 安装：

```powershell
pip install "plotagent-0.1.0-py3-none-any.whl[mcp]"
```

MCP stdio 需要三个显式环境变量：

```text
PLOTAGENT_ENGINE_ROOT
PLOTAGENT_ENGINE_IMPORT_ROOTS
PLOTAGENT_ENGINE_EXPORT_ROOT
```

然后启动 `plotagent-mcp`。MCP 共发现 15 个顶层工具：项目 3 个、数据 4 个、图形 6 个、
导出 1 个、健康检查 1 个。数据整理的五种阶段动作合并在一个强类型
`plotagent_data_view` 中；创建和编辑统一使用 Engine Action 判别联合，避免把每个颜色、
线型或轴参数拆成独立工具。

## 4. 验证结果

### 4.1 源码门禁

- Ruff：PASS；
- mypy：195 个 Python 源文件，PASS；
- Python 全量：`902 passed in 665.78s`；
- Vitest：31 个文件、296 项，全部 PASS；
- TypeScript：node/web 两套 `tsc --noEmit`，PASS；
- SDK/MCP 定向：8/8 PASS；
- SDK 与 MCP 的 34 图目录结果等价；
- MCP 官方 stdio initialize、list_tools、call_tool：PASS。

### 4.2 独立 wheel

- wheel：`build/external-engine-sdk-mcp/wheel/plotagent-0.1.0-py3-none-any.whl`；
- SHA-256：`04EC9CC77F36D625EEC49529C5348F262384018717B0E28A90A66944E6BA316F`；
- 在新 venv 中使用 `[mcp]` 安装：PASS；
- 安装后的 MCP：server `plotagent-engine`、version `1.0`、15 tools、health PASS；
- 安装后的 SDK：导入 Excel → 创建 K01 → PNG，PASS；
- 外部 `@图1` 在重开 SDK 后保持，PASS。

### 4.3 原生 OPJU

- 安装后的 SDK 创建 K01 v2，并应用标题编辑 `Installed SDK`；
- OPJU：`build/external-engine-sdk-mcp/installed-sdk-edited.opju`；
- 大小：29,867 bytes；
- SHA-256：`7A61742D87D5C65A6C4C194AED3284FC3B233D6F7CC0A02E72DD34D0C974E6E0`；
- 独立 Origin 进程 fresh-reopen：1 graph、1 worksheet、0 matrix；
- 标题读回：`Installed SDK`、visible；
- fresh-reopen 结果：`build/external-engine-sdk-mcp/installed-sdk-edited-fresh.json`；
- fresh PNG：`build/external-engine-sdk-mcp/installed-sdk-edited-fresh.png`，25,601 bytes，
  SHA-256 `B4D2203C2239105D96F9A942F853222676D8B59B69DE2ECCBB6DB18BB79FBE9`。

独立安装首次 OPJU 验证发现 Origin worker 实际依赖 `pandas`，但原项目依赖清单未声明。
本分支只补齐 `pyproject.toml` 的运行依赖，没有修改 renderer；重建 wheel 后 OPJU 与
fresh-reopen 通过。

## 5. 尚未由本报告证明

以下内容不能从上述 PASS 外推：

1. 真实外部 Agent Host 是否能从自然语言目标自行完成检查、整理、校验、创建、编辑与导出；
2. 外部 Agent 的确认卡、用户追问和批量任务交互质量；这些属于 Host，而不是 MCP server；
3. 34 图逐图通过 MCP 重新做 Origin fresh-reopen。本报告用全量共享 renderer 门禁加一个
   独立安装 K01 原生代表图证明接口没有另造 renderer，不替代历史 34 图 Origin 证据；
4. 公网、多租户或远程服务部署。当前 MCP/SDK 只承诺本地受限路径；
5. HTTP API。当前只实现 SDK 与 MCP；
6. 把 MCP 嵌入现有桌面安装包。当前建议先作为独立 wheel 交付，避免扩大桌面候选变更面。

## 6. 下一验收步

使用一个真实 Agent Host 连接安装后的 `plotagent-mcp`，只给产品能力说明和授权数据目录，
完成至少三项任务：单来源单图、多来源同图、整理数据后绘图。每项必须包含读取真实字段、
查询 Profile、无副作用校验、创建、一次编辑、PNG 与 OPJU 导出，并核对 `@图N`、版本、
readback、大小和哈希。该测试通过后，再决定是否合并到主开发分支及采用何种安装形态。
