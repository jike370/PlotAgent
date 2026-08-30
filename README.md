# fig-agent

面向通用科研用户的 Windows 本地绘图 Agent。用户可以直接导入原始表格数据，不需要先整理成 fig-agent 的固定模板；随后通过图形库或自然语言完成单图、批量绘图和持续改图，并导出 PNG、SVG 和 Origin 原生可编辑的 `.opju` 文件。自然语言和界面修改会进入同一图形版本，并在再次导出时写入 OPJU 原生对象。内部 Python 包、协议与历史工程标识继续使用 `plotagent`，以保持兼容。

当前仓库包含一个可运行的 Windows 桌面应用、34 张正式单图、durable Agent task/TaskIntent/TaskPlan 编排、Pi 模型运行时、Matplotlib 预览/PNG/SVG，以及受控 Origin 原生 OPJU 自动化。界面覆盖项目、数据导入、对话、批量任务、字段确认、聚焦编辑、撤销/重做、任务状态和 Origin 不可用降级；不提供组合图或多面板自由编排。

Windows production packaging 现提供 PyInstaller onedir sidecar、NSIS 与离线完整性校验的轻量人工路径。开发态和打包态使用同一受限 `plotagent.desktop_core` RPC runtime；导入、绘图、Agent 与 Origin 等领域服务通过窄 `ServiceRegistry` 接入，不另建打包专用 mock。

v3 当前基线面向小规模邀请制 Beta：正式目录固定为 34 张单图，支持 CSV、TSV、TXT、DAT、XLS、XLSX、XLSM 多来源导入、批量任务、受控数据操作和 PNG/SVG/O1 OPJU。结构化 UI 可以零模型执行；自然语言任务统一由 Pi 在预算内检查数据并提交强类型任务，程序不通过关键词或正则替模型解释目标。通用分析/拟合、任意代码、组合图和 T2/T3 后端专属视觉能力不在当前范围。

权威文档入口见 [`docs/SPEC-INDEX.md`](docs/SPEC-INDEX.md)，施工—测试—发布顺序见 [`docs/IMPLEMENTATION-PLAN.md`](docs/IMPLEMENTATION-PLAN.md)。产品范围以 [`docs/PRODUCT-DECISIONS.md`](docs/PRODUCT-DECISIONS.md) 和 [`docs/PRD.md`](docs/PRD.md) 为准；编排见 [`docs/AGENT-ORCHESTRATION-ARCHITECTURE.md`](docs/AGENT-ORCHESTRATION-ARCHITECTURE.md)，后端见 [`docs/BACKEND-ARCHITECTURE.md`](docs/BACKEND-ARCHITECTURE.md)，Pi 运行时见 [`docs/PI-AGENT-RUNTIME.md`](docs/PI-AGENT-RUNTIME.md)，存储与导入见 [`docs/PROJECT-STORAGE.md`](docs/PROJECT-STORAGE.md)，发布门禁见 [`docs/PERFORMANCE-TEST-RELEASE.md`](docs/PERFORMANCE-TEST-RELEASE.md)。

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

`originpro` Python 包已列为核心依赖，但生成 `.opju` 时仍需要 Windows 环境中安装并授权可用的 Origin。当前只认证 OriginPro 2024（文件版本 10.1.0）；用户可在侧栏手动选择 Origin 主程序，选择结果会持久化，并同时用于环境检测和实际导出。检测到其他版本时会显示真实版本并明确提示不兼容，不会将其误报为“未安装”。

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
  -CertificatePath C:\authorized\fig-agent-code-signing.pfx `
  -CertificatePassword $certificatePassword `
  -TimestampServer https://authorized.example/timestamp

.\scripts\verify-windows-release.ps1 `
  -ManifestPath .\release\windows\publish\release-manifest.json `
  -AllowedPublisher "CN=Approved fig-agent Publisher, O=Example"
```

签名入口要求 Git worktree 干净；unsigned development manifest 会如实记录 `source_dirty`，不能作为 RC 来源声明。

严格 verifier 离线检查 detached CMS manifest signature、publisher allowlist、精确文件集合、大小/SHA-256 与每个 Windows executable 的 Authenticode。稳定阻断码为 `INSTALLER_PUBLISHER_SIGNATURE_INVALID`、`INSTALLER_HASH_INVALID` 和 `INSTALLER_WINDOWS_CODE_SIGNATURE_INVALID`。本路径不包含自动更新、下载器、云发布、CI/CD、SBOM、商业签署流程，也不应提交 `release` 二进制。

