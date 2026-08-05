# PlotAgent

面向通用科研用户的对话式绘图 Agent。用户上传数据并明确选择图形，Agent 生成结果、接受自然语言修改，并导出 PNG、SVG 和 Origin `.opju` 文件。

当前仓库包含一个可运行的 Windows 桌面交互原型。界面覆盖项目与对话、结构化数据对象、批量图集、首轮 31 项纯数值数据图形目录、聚焦编辑、固定布局组合图、任务状态与 Origin 不可用降级。真实 Agent、Python 绘图工作进程和 Origin 自动化尚未接入。

v1 基线保持专业能力完整，并把工程 qualification 收敛为小规模邀请制 Beta；这不表示真实后端、云服务、Origin 自动化或 Beta qualification 已完成。权威范围与 requirement/evidence matrix 见 [`docs/SPEC-INDEX.md`](docs/SPEC-INDEX.md)，W0–W10、risk spikes 与 M0–M7 见 [`docs/IMPLEMENTATION-PLAN.md`](docs/IMPLEMENTATION-PLAN.md)。产品范围以 [`docs/PRODUCT-DECISIONS.md`](docs/PRODUCT-DECISIONS.md) 和 [`docs/PRD.md`](docs/PRD.md) 为准；后端与 Agent 见 [`docs/BACKEND-ARCHITECTURE.md`](docs/BACKEND-ARCHITECTURE.md)，Context/Provider/数据出境见 [`docs/AGENT-CONTEXT-AND-PROVIDERS.md`](docs/AGENT-CONTEXT-AND-PROVIDERS.md)，Invite/长期设备凭据/共享计数见 [`docs/CLOUD-CONTROL-PLANE.md`](docs/CLOUD-CONTROL-PLANE.md)，strict local_only/本地诊断/Beta schema兼容见 [`docs/LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md`](docs/LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md)，单一平台/规模/Origin与Beta检查单见 [`docs/PERFORMANCE-TEST-RELEASE.md`](docs/PERFORMANCE-TEST-RELEASE.md)，领域Schema见 [`docs/DOMAIN-CONTRACTS.md`](docs/DOMAIN-CONTRACTS.md)，存储/导入见 [`docs/PROJECT-STORAGE.md`](docs/PROJECT-STORAGE.md)，变换/单位/血缘见 [`docs/DATA-TRANSFORMS.md`](docs/DATA-TRANSFORMS.md)，任务运行时见 [`docs/TASK-RUNTIME.md`](docs/TASK-RUNTIME.md)，分析与拟合见 [`docs/ANALYSIS-ENGINE.md`](docs/ANALYSIS-ENGINE.md) 和 [`docs/FITTING-SYSTEM.md`](docs/FITTING-SYSTEM.md)，渲染见 [`docs/RENDERING-PIPELINE.md`](docs/RENDERING-PIPELINE.md)，OPJU见 [`docs/ORIGIN-EXPORT.md`](docs/ORIGIN-EXPORT.md)。

## 桌面端开发

需要 Node.js 24 与 pnpm 11。

```powershell
pnpm install
pnpm dev
```

仅在浏览器中检查渲染层：

```powershell
pnpm dev:web
```

生产构建与质量检查：

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

桌面端采用 electron-vite，Electron 主进程、preload 安全边界和 React 渲染层分别位于 `src/main`、`src/preload` 与 `src/renderer`。`contextIsolation` 和 sandbox 默认开启，渲染层不启用 Node.js 集成。

## 本地环境

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

`originpro` Python 包已列为核心依赖，但生成 `.opju` 时仍需要 Windows 环境中安装并授权可用的 Origin。

```powershell
python -m pytest
```
