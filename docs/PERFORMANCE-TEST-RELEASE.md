# PlotAgent 性能测试与发布门禁契约

> 状态：第一轮邀请内测的 qualification 基线已确认
> 日期：2026-08-05
> 适用范围：支持平台、规模、性能/资源预算、31 图证据矩阵、Origin qualification、RC 门禁与内测成功标准
> 相关文档：[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)、[任务运行时、取消与崩溃恢复](./TASK-RUNTIME.md)、[渲染管线与跨 Renderer 一致性契约](./RENDERING-PIPELINE.md)、[原生 Origin OPJU 导出契约](./ORIGIN-EXPORT.md)、[本地安全、离线模式、诊断、迁移与恢复备份契约](./LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md)、[项目存储、项目包与数据导入](./PROJECT-STORAGE.md)

本文件定义未来 Release Candidate 必须生成的证据与门禁。当前设计文档通过不表示后端、Origin、安装包或自动化测试已经实现或通过。

## 1. 正式支持平台

### 1.1 Windows

- 正式邀请内测只声明支持：发布时仍处于 Microsoft 支持周期内的 Windows 11 x64。
- 当前参考 OS 是 Windows 11 25H2 x64；每个 RC 必须记录实际 edition、build 与 servicing state。
- Windows 10 22H2 仅作为兼容性观察，不是 release blocker，也不形成当前或后续兼容承诺。
- Windows LTSC 只有在该 LTSC 仍受支持、明确列入 release manifest，并完成与普通 Windows 11 同等级 qualification 后才可声明支持。
- ARM64、32-bit Windows、Wine/虚拟兼容层与 Windows Server 第一轮不在正式支持矩阵。

“Windows 11+”不能替代明确 release manifest。安装器、帮助和诊断都读取同一个版本化支持声明。

### 1.2 测试机器

| Profile | OS/CPU/RAM/Disk | Display | 角色 |
| --- | --- | --- | --- |
| reference | 支持的 Windows 11 x64；6 physical/logical cores profile；16 GB RAM；NVMe；无独显要求 | 1920×1080，100% 或 125% | 所有 P50/P95 预算的基准 |
| minimum beta | 支持的 Windows 11 x64；4 cores；8 GB RAM；SSD | 1366×768 | 可用性、资源拒绝与最低 UI qualification |

显示矩阵固定覆盖 100%、125%、150%、200% scaling；关键主窗口、聚焦编辑、图形库、批量审阅、资源库、迁移/安全确认与更新 UI 都需验证，无截断关键动作、不可达焦点或模糊错误缩放。

Machine profile 不要求 GPU，正式结果不能依赖 GPU 特性。测试记录可以保存本地硬件 fingerprint（CPU model/count、RAM、disk class、OS/build、display/scaling），但不能作为 telemetry 自动上传或用硬件序列号构建身份。

## 2. Origin qualification

- Origin 2021 是第一轮最低技术基线，不代表所有 2021 以上版本自动受支持。
- 每个 OriginAdapter 只声明已执行 qualification 的明确 Origin major/version range、bitness、originpro version、template hash 与 Windows profile。
- 未在当前 release manifest 中明确列出的版本，preflight 返回 `VERSION_UNSUPPORTED`；不能用“Origin 2021+”覆盖未测版本。
- 每个 RC 至少运行 Origin 2021 和发布日当前明确支持版本；若两者相同仍需一套明确证据。
- 所有声明支持的 Origin 版本都重复完整 31 图 O1 formal matrix，包括 live validation 与 fresh blank instance reopen readback。
- 某一版本失败只撤销该版本声明，不能把该版本静默标为 O2；第一轮 31 图只以 O1 准入 OPJU。

Qualification evidence 固定 `origin_version_exact`、build、bitness、license mode、originpro/adapter/template/font hashes、OS build 与 matrix run ID。

## 3. 数据规模等级

| Level | Reference workload | 用途 |
| --- | --- | --- |
| regular | 100k rows × 20 columns；10 charts | 日常路径与常规峰值 |
| large | 1M rows × 20 columns；100 files 或 100 charts | 大型导入、批次与预览 |
| boundary | 10M numeric cells；1000 project objects | 资源预检、索引与项目元数据边界 |

这些是 qualification 规模，不是静默硬上限。超过后可以尝试，但必须先执行 CPU/memory/disk/output complexity resource preflight：

- 预计可安全运行时允许，并记录估计与实际资源。
- 预计越过安全阈值时返回 `RESOURCE_LIMIT`，给出具体约束与缩小范围动作。
- 不能崩溃、挂死、损坏项目、静默抽稀 formal 输出或换算法。
- 手动拆批、减少目标或更换输出格式是用户显式恢复动作，不由系统暗中执行。

## 4. Preview 简化与正式完整性

- thumbnail 每视图最多 5,000 个 visible primitives。
- interactive 每 axes 最多 50,000 个 visible primitives。
- 简化使用版本化、确定性视觉规则；UI 显示“预览已简化”、完整数量、显示数量和方法。
- Autoscale range、统计、analysis、fit、error/interval 使用 full data，不能基于简化点重算。
- formal PNG、SVG 与 OPJU 使用 full data 和持久化 AnalysisResult/FitResult 表。
- SVG 预计超过 200 MB 或 2,000,000 vector primitives 时显示强 warning、估计大小/数量和 explicit confirm；不得自动 rasterize、downsample 或换 PNG。
- 用户取消大 SVG 不创建 ExportRecord；确认后仍执行 resource preflight 与原子文件提交。

## 5. P95 性能预算

除明确标 P50 外，以下均为 reference machine 的 end-to-end P95 gate：

### 5.1 启动与项目

| Scenario | Budget |
| --- | ---: |
| desktop shell interactive | ≤ 2 s |
| Python Core ready | ≤ 5 s |
| large project metadata open | ≤ 2 s |

Shell interactive 指可响应主窗口本地导航，不等待云、更新、Origin 或 Core ready。Core ready 独立计时并显示真实阶段。

### 5.2 导入

| Scenario | Budget |
| --- | ---: |
| 100 MB CSV | ≤ 12 s |
| 1 GB CSV | ≤ 90 s |
| 50 MB XLSX | ≤ 30 s |

导入预算覆盖临时复制/hash、完整解析、Arrow/Parquet、quality summary、对象移动与 SQLite commit；不通过跳过完整解析或降低安全校验达标。

### 5.3 Preview、批次与 patch

| Scenario | Budget |
| --- | ---: |
| 100k-point preview | ≤ 3 s |
| 1M-point simplified preview | ≤ 5 s |
| style-only patch preview | ≤ 2 s |
| 20 charts × 10k points batch preview | ≤ 30 s |

### 5.4 Formal export

| Scenario | Budget |
| --- | ---: |
| single 100k formal PNG | ≤ 5 s |
| single 100k formal SVG | ≤ 10 s |
| single 100k OPJU build + fresh reopen | ≤ 60 s |
| 20-chart OPJU build + fresh reopen | ≤ 180 s |

OPJU 预算只在明确 qualified Origin 版本和可用 license 下测量；preflight、build、save、process exit、fresh instance reopen、readback 与 atomic move 全部计入。

### 5.5 Agent 与反馈

| Scenario | Budget |
| --- | ---: |
| ContextEnvelope build | P95 ≤ 1 s |
| built-in structured AgentDecision | provider-inclusive P50 ≤ 8 s；P95 ≤ 20 s |
| input/click/task-card acknowledgement | ≤ 100 ms |

Provider latency 另外记录 DNS/connect/TLS/TTFB/stream complete，不用删除慢样本美化端到端预算。任何预计或实际超过 2 秒的操作显示真实本地阶段/单位进度；不显示假进度、隐藏推理或 chain-of-thought。

## 6. Memory、并发与磁盘

### 6.1 Memory

| State | Budget |
| --- | ---: |
| idle Electron + Python Core | ≤ 700 MB working set |
| regular workload peak | ≤ 2 GB |
| large workload peak | ≤ 6 GB |

- available memory 低于 15% 或 2 GB（任一触发）时，新计算任务并发降为 1。
- 资源预检估计任务启动后 available memory 将低于 10% 或 1 GB（任一触发）时，拒绝启动并返回 `RESOURCE_LIMIT`。
- 已运行任务到达压力阈值时优先停止新调度并 cooperative cancel 可控子任务；不得强杀 Core 或提交半对象。
- Memory gate 记录 Electron Main/renderer、Core、isolated worker 与 Origin managed instance 的分项峰值。

### 6.2 Disk

- 导入复制前，目标固定磁盘 free bytes 必须至少为 `estimated_landed_bytes × 2.5`。
- Estimated landed bytes 包含源临时副本、Arrow/Parquet/CAS、SQLite/WAL/indices 和安全余量；估计版本写入测试证据。
- 不足时在复制前返回 `DISK_SPACE_INSUFFICIENT`，不能先占满磁盘再失败。
- 正式导出和更新各自还需满足 temp + final + validation/backup 所需空间。

## 7. 31 图证据矩阵

### 7.1 每图 fixtures

正式第一轮 31 个 chart type，每个至少三种 fixture：

1. `minimal_valid`：最小合法字段与数据。
2. `representative_research`：真实科研语义、单位、误差/analysis/annotation 的代表样本。
3. `edge_error`：缺失、非有限值、非法 log、字段/单位/analysis/Origin capability 等边界或稳定错误。

每个 fixture 的三个基础产物/预期错误 path 固定为：formal PNG、formal SVG、O1 OPJU。因此基础逻辑矩阵为 `31 × 3 × 3 = 279` paths：

- formal PNG：93 条。
- formal SVG：93 条。
- O1 OPJU：93 条。

Preview/interactive 是另外的必测路径，不计入这 279。279 中的 OPJU 93 条不是只运行一次的抽样：必须针对 release manifest 中每个声明支持的 Origin exact version 分别完整重跑，实际 OPJU execution count 为 `93 × qualified Origin version count`。

`edge_error` path 可以用符合预期 code/schema/details 的稳定错误证据通过，不要求生成二进制；但不得用“预期失败”掩盖本应成功的 minimal/representative 路径。

### 7.2 覆盖维度

矩阵按适用能力覆盖：

- PlotSpec canonical JSON、ResolvedRenderPlan normalized hash/golden。
- thumbnail/interactive、formal PNG/SVG、O1 live+fresh-reopen OPJU。
- BatchSpec、FigureSpec、analysis/fit output ports、axes/ticks、error/warning。
- 中文、英文与中英混合术语、SafeRichText 与字体 fallback。
- cancel、Core/worker crash、idempotency、expected-version conflict。
- formal full-data assertion、preview simplification disclosure 与 parity tolerance。

### 7.3 可机器统计键

```text
MatrixKey
├─ release_candidate
├─ chart_type_id
├─ fixture_id
├─ artifact_path: thumbnail | interactive | formal_png | formal_svg | opju_o1
├─ expectation: binary_artifact | stable_error
├─ quality_tier
├─ renderer_or_adapter_version
├─ origin_version_exact? # opju_o1 必填
├─ os_profile
├─ locale_profile
└─ test_case_id
```

证据路径/逻辑名：

```text
evidence/<rc>/<chart_id>/<fixture_id>/<artifact_path>/
  <test_case_id>__<renderer_or_origin>__<os_profile>__<status>.<ext>
```

每个 evidence record 保存 input/reference dataset hash、spec/plan hash、expectation、可选 binary artifact hash、validator report hash、timing/memory、stable error 和 tool/dependency versions。OPJU MatrixKey 必须带 exact Origin version，报告不得把不同 Origin 版本折叠。报告按完整 MatrixKey 去重；重试不是新 case，也不能覆盖第一次失败记录。

## 8. 测试层级

1. Schema/domain unions、strict fields、generated TS types 与 stable error registry。
2. Import/Transform/Unit/Lineage、archive/Excel 安全与 `.plotproj` integrity。
3. Scientific reference datasets、AnalysisSpec/FitSpec、method/formula/version/diagnostics。
4. Resolver/render/layout/axis/ticks/font/color/physical size 与 cross-renderer semantic parity。
5. Origin O1 adapter、live validation、save/exit、fresh reopen、data link/semantics readback。
6. Electron↔Python JSON-RPC E2E、single-instance、preload boundary 与 task events。
7. Cancel/crash/timeout/idempotency/version conflict/partial batch fault injection。
8. Security/privacy/migration/local_only zero-egress/diagnostic-log allowlist/update tamper。
9. Performance/memory/disk/concurrency/large project/soak 与 leak regression。
10. Installer/update/rollback safety、Windows code signature、SBOM/license/dependency vulnerability audit。

每一层定义 owner、machine/profile、fixtures、repeat/sample count、evidence URI 和 failure disposition；不能只靠手工截图作为唯一证据。

## 9. 可复现性能测量协议

每个 performance case 固定并输出：

- cold/warm state；cold 明确清除哪些 app cache/OS cache，warm 明确预热次数。
- reference dataset/object/package hash 与生成器版本。
- 本地 machine fingerprint：OS/build、CPU model/count、RAM、disk class/model、display/scaling；不自动上传个人硬件 ID。
- app/installer、Python、SQLite、renderer、analysis、Origin/adapter/template/font versions。
- sample count；默认至少 30 个可用样本，若场景成本要求更少必须在 case definition 预先批准且不得少于 10。
- P50/P95 计算：排序后使用 nearest-rank；失败、timeout 和 cancel 不从 latency 样本中删除，而是单独计入 failure gate。
- cache policy、后台进程控制、网络/provider latency 分解与每次 run 原始 timing evidence。
- regression threshold：相对已批准 baseline P95 退化 >10% 或越过绝对预算即阻断；改善不能抵消功能失败。

修改 fixture、机器、测量点或算法版本会创建新 baseline，必须审阅并保留旧 baseline；不能原地重写历史数字。

## 10. Severity、owner 与 waiver

| Severity | 定义 | Release handling |
| --- | --- | --- |
| blocker | 数据损坏、安全/科学/签名关键边界、声明能力不可用 | 禁止发布，不可 waiver |
| critical | 可导致广泛错误结果、不可恢复失败或高影响泄露 | 禁止发布；本文件列出的 critical 不可 waiver |
| major | 关键路径明显失效但有安全、明确 workaround | 必须修复；例外需产品+工程+QA owner 书面、限期、known issue |
| minor | 不影响正确性/安全/完成路径的局部缺陷 | 可由明确 owner 接受并进入 known issues |

每个 failure 有唯一 triage owner、affected MatrixKeys、root cause、fix/evidence link 与 disposition。Waiver 必须包含范围、理由、用户影响、到期 RC 和批准者；不能用笼统“已知问题”。

## 11. 不可豁免 Release blockers

以下任一项出现时禁止发布邀请 RC：

- data loss/corruption、不可恢复 migration 或 restore 覆盖当前项目。
- silent wrong science；mapping/unit/statistical method/fit formula/seed/missing policy 被静默改变。
- formal data downsample、renderer/analysis algorithm swap 或 capability downgrade。
- 非原生结果被宣称为 O1，或任一已声明 Origin 版本的 fresh reopen 关键语义失败。
- credential、prompt、文件/路径、列名、单元格值、摘要或禁止诊断内容泄露。
- 31 个正式图形中的任何声明输出路径/适用 fixture 失败。
- update/config/manifest/package signature/hash/code-sign bypass。
- 已知 blocker/critical 缺陷。
- 测试门禁只有通过重跑、删除失败样本、放宽 fixture/tolerance 或替换未审阅 golden 才“变绿”。

上述项目不可 waiver；删除产品声明必须先更新 Decision/PRD/release manifest 并重新完整 qualification，不能作为临时豁免。

## 12. 每个 RC 的证据包

1. 自动化总报告与测试环境 manifest。
2. 31-chart 基础 279 MatrixKey coverage、额外 preview/interactive coverage 与缺口为零证明。
3. 每个明确支持 Origin 版本各自完整 93 条 O1 OPJU compatibility report，不合并版本或抽样。
4. Scientific reference/golden/diagnostic report。
5. Performance/memory/disk/soak 与相对 baseline regression report。
6. Security/privacy/local_only/diagnostic/migration fault-injection report。
7. SBOM、third-party licenses、dependency/vulnerability disposition。
8. 签名 installer/update manifest/package 和 Windows signature verification evidence。
9. Known issues、owner、severity、workaround 与所有允许 waiver。

Evidence 包本身不得包含用户项目、prompt、路径、列名/值、secret 或真实研究数据；fixtures 使用版本化合成/公开许可数据。

## 13. 首批 10–15 人成功门禁

这是第二批内测 go/no-go，不是匿名 telemetry 推断：

- ≥80% 参与者在 sample project 上独立完成第一张图。
- ≥60% 用自己的真实数据在无 staff takeover 下完成第一张图。
- ≥60% 明确表示愿意用另一份真实数据继续使用。
- 至少 1 人完成批量绘图/审阅路径。
- 至少 1 名 Origin 用户导出 OPJU 并在 Origin 中继续编辑。

记录方式是经同意的内测任务观察、结构化访谈/问卷和用户明确结果；默认关闭 telemetry 时不能把缺失事件当成失败或成功。Staff 可以解释任务，但一旦接管字段映射、方法选择或操作，即不计“独立完成”。

## 14. 发布审批

RC go/no-go 至少需要 Product、Desktop/Core Engineering、Scientific Validation、Origin Adapter、Security/Privacy 与 QA/Release owner 对各自 evidence 签署。审批记录固定 RC commit、installer hash、Decision baseline、matrix report 与 known issues。

只有所有不可豁免门禁通过、允许 waiver 未过期且 evidence 可复核时，RC 才可进入邀请内测。任何 post-sign 修改都会产生新 RC 和新证据，不能沿用旧审批。
