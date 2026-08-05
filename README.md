# PlotAgent

面向通用科研用户的对话式绘图 Agent。用户上传数据并明确选择图形，Agent 生成结果、接受自然语言修改，并导出 PNG、SVG 和 Origin `.opju` 文件。

当前仓库包含一个可运行的 Windows 桌面交互原型，以及 W8/M6 的最小 Beta 云控制面实现。界面覆盖项目与对话、结构化数据对象、批量图集、首轮 31 项纯数值数据图形目录、聚焦编辑、固定布局组合图、任务状态与 Origin 不可用降级。真实 Agent、Python 绘图工作进程和 Origin 自动化尚未接入；控制面也未部署真实云或接入真实上游 provider。

Windows production packaging 现提供 PyInstaller onedir sidecar、NSIS 与离线完整性校验的轻量人工路径。开发态和打包态使用同一受限 `plotagent.desktop_core` RPC runtime；导入、绘图、Agent 与 Origin 等领域服务通过窄 `ServiceRegistry` 接入，不另建打包专用 mock。

v1 基线面向小规模邀请制 Beta：保留 31 种数值科研图形、同构批量/固定组合和 PNG/SVG/O1 OPJU，但数据能力收敛为确定性 Excel/TXT/CSV 导入、一次字段语义映射、受控 PreparationSpec 与九类固定 PlotCalculation。需要回归、相关、KM、剂量反应等分析的图形只接受预计算字段；通用数据变换、AnalysisSpec/FitSpec 与科学分析/拟合引擎均为后续阶段。这不表示真实后端、云服务、Origin 自动化或 Beta qualification 已完成。

权威范围与 requirement/evidence matrix 见 [`docs/SPEC-INDEX.md`](docs/SPEC-INDEX.md)，W0–W10、risk spikes 与 M0–M7 见 [`docs/IMPLEMENTATION-PLAN.md`](docs/IMPLEMENTATION-PLAN.md)。产品范围以 [`docs/PRODUCT-DECISIONS.md`](docs/PRODUCT-DECISIONS.md) 和 [`docs/PRD.md`](docs/PRD.md) 为准；后端与 Agent 见 [`docs/BACKEND-ARCHITECTURE.md`](docs/BACKEND-ARCHITECTURE.md)，Context/Provider/数据出境见 [`docs/AGENT-CONTEXT-AND-PROVIDERS.md`](docs/AGENT-CONTEXT-AND-PROVIDERS.md)，Invite/长期设备凭据/共享计数见 [`docs/CLOUD-CONTROL-PLANE.md`](docs/CLOUD-CONTROL-PLANE.md)，strict local_only/本地诊断/Beta schema兼容见 [`docs/LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md`](docs/LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md)，单一平台/规模/Origin与Beta检查单见 [`docs/PERFORMANCE-TEST-RELEASE.md`](docs/PERFORMANCE-TEST-RELEASE.md)，领域Schema见 [`docs/DOMAIN-CONTRACTS.md`](docs/DOMAIN-CONTRACTS.md)，存储/导入见 [`docs/PROJECT-STORAGE.md`](docs/PROJECT-STORAGE.md)，受控准备/来源追溯见 [`docs/DATA-TRANSFORMS.md`](docs/DATA-TRANSFORMS.md)，任务运行时见 [`docs/TASK-RUNTIME.md`](docs/TASK-RUNTIME.md)，固定绘图计算与科学/拟合分期见 [`docs/ANALYSIS-ENGINE.md`](docs/ANALYSIS-ENGINE.md) 和 [`docs/FITTING-SYSTEM.md`](docs/FITTING-SYSTEM.md)，渲染见 [`docs/RENDERING-PIPELINE.md`](docs/RENDERING-PIPELINE.md)，OPJU见 [`docs/ORIGIN-EXPORT.md`](docs/ORIGIN-EXPORT.md)。

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

## Windows 人工安装包

发布环境另需安装 release 依赖。默认入口只生成明确标记的 unsigned development installer，不会发现或假装使用系统中的证书：

```powershell
python -m pip install -e ".[dev,release]"
pnpm install --frozen-lockfile
.\scripts\release-windows.ps1 -DryRun
.\scripts\release-windows.ps1
```

入口只清理仓库内的 `release/windows`，依次构建 wheel、从 wheel staging 生成 onedir sidecar、Electron/NSIS 和 `release/windows/publish/release-manifest.json`。`publish` 目录是人工交付边界；`.venv`、tests、原始项目数据与 secrets 不在 electron-builder 的文件或 extraResources allowlist 中。

默认严格校验会阻断 unsigned output；只有本地 smoke 时才显式允许 unsigned development 模式：

```powershell
.\scripts\verify-windows-release.ps1 `
  -ManifestPath .\release\windows\publish\release-manifest.json `
  -AllowUnsignedDevelopment
```

正式签名必须显式提供 PFX；密码使用 `SecureString`，timestamp 也只在明确传入 URL 时启用：

```powershell
$certificatePassword = Read-Host "PFX password" -AsSecureString
.\scripts\release-windows.ps1 `
  -Sign `
  -CertificatePath C:\authorized\plotagent-code-signing.pfx `
  -CertificatePassword $certificatePassword `
  -TimestampServer https://authorized.example/timestamp

.\scripts\verify-windows-release.ps1 `
  -ManifestPath .\release\windows\publish\release-manifest.json `
  -AllowedPublisher "CN=Approved PlotAgent Publisher, O=Example"
```

签名入口要求 Git worktree 干净；unsigned development manifest 会如实记录 `source_dirty`，不能作为 RC 来源声明。

严格 verifier 离线检查 detached CMS manifest signature、publisher allowlist、精确文件集合、大小/SHA-256 与每个 Windows executable 的 Authenticode。稳定阻断码为 `INSTALLER_PUBLISHER_SIGNATURE_INVALID`、`INSTALLER_HASH_INVALID` 和 `INSTALLER_WINDOWS_CODE_SIGNATURE_INVALID`。本路径不包含自动更新、下载器、云发布、CI/CD、SBOM、商业签署流程，也不应提交 `release` 二进制。

