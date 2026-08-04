# PlotAgent

面向通用科研用户的对话式绘图 Agent。用户上传数据并明确选择图形，Agent 生成结果、接受自然语言修改，并导出 PNG、SVG 和 Origin `.opju` 文件。

当前仓库包含一个可运行的 Windows 桌面交互原型。界面覆盖项目与对话、结构化数据对象、批量图集、首轮 31 项纯数值数据图形目录、聚焦编辑、固定布局组合图、任务状态与 Origin 不可用降级。真实 Agent、Python 绘图工作进程和 Origin 自动化尚未接入。

产品范围以 [`docs/PRODUCT-DECISIONS.md`](docs/PRODUCT-DECISIONS.md) 的已确认决策基线和 [`docs/PRD.md`](docs/PRD.md) 的可实施需求为准；后端进程与 Agent 执行链见 [`docs/BACKEND-ARCHITECTURE.md`](docs/BACKEND-ARCHITECTURE.md)，ContextEnvelope、模型供应商、数据出境与审计见 [`docs/AGENT-CONTEXT-AND-PROVIDERS.md`](docs/AGENT-CONTEXT-AND-PROVIDERS.md)，InviteGrant、共享额度、最小云控制面和签名更新见 [`docs/CLOUD-CONTROL-PLANE.md`](docs/CLOUD-CONTROL-PLANE.md)，local_only、本地安全、诊断、迁移与恢复备份见 [`docs/LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md`](docs/LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md)，性能预算、31图证据矩阵与 RC 发布门禁见 [`docs/PERFORMANCE-TEST-RELEASE.md`](docs/PERFORMANCE-TEST-RELEASE.md)，PlotSpec、PlotPatch 和 ActionPlan 见 [`docs/DOMAIN-CONTRACTS.md`](docs/DOMAIN-CONTRACTS.md)，运行态工作区、`.plotproj` 与导入流水线见 [`docs/PROJECT-STORAGE.md`](docs/PROJECT-STORAGE.md)，派生数据、单位与三层血缘见 [`docs/DATA-TRANSFORMS.md`](docs/DATA-TRANSFORMS.md)，任务调度、取消和崩溃恢复见 [`docs/TASK-RUNTIME.md`](docs/TASK-RUNTIME.md)，分析注册表、AnalysisSpec/Result 与科学边界见 [`docs/ANALYSIS-ENGINE.md`](docs/ANALYSIS-ENGINE.md)，FitSpec/FitResult、非线性公式与导出契约见 [`docs/FITTING-SYSTEM.md`](docs/FITTING-SYSTEM.md)，坐标解析、物理布局与跨 renderer 一致性见 [`docs/RENDERING-PIPELINE.md`](docs/RENDERING-PIPELINE.md)，原生 OPJU 内容、准入与两阶段验证见 [`docs/ORIGIN-EXPORT.md`](docs/ORIGIN-EXPORT.md)。

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
