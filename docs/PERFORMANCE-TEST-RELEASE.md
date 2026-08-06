# PlotAgent 小规模邀请制 Beta 性能测试与发布门禁契约

> 状态：v1 正式 43 图、编辑/Origin 样式与数据计算范围收敛；43 图合并 Origin build/fresh-reopen 工程门禁已通过，完整 Beta qualification 尚未执行
> 日期：2026-08-07
> 适用范围：唯一正式平台与规模基线、43 图证据矩阵、逐图编辑/Origin 样式映射、单一 Origin 版本 qualification、Beta 发布检查单与用户成功标准
> 相关文档：[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)、[任务运行时、取消与崩溃恢复](./TASK-RUNTIME.md)、[渲染管线与跨 Renderer 一致性契约](./RENDERING-PIPELINE.md)、[原生 Origin OPJU 导出契约](./ORIGIN-EXPORT.md)、[本地安全、诊断与 Beta Schema 兼容契约](./LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md)、[项目存储、项目包与数据导入](./PROJECT-STORAGE.md)

本文件定义第一轮邀请制 Beta 的正式 qualification。正式图形范围为原 31 图加 12 个已准入 P1 图，共 43 图；另九个已存在的内部 adapter 对用户隐藏且不承诺 create/export。确定性导入/一次字段映射、九类固定绘图计算、预计算字段路径、PNG/SVG/O1 OPJU、full-data formal 和科学可追溯底线保持不变；通用数据处理、AnalysisSpec/FitSpec 与科研分析/拟合不在 v1。2026-08-07 已完成一次正式 43 图合并 OPJU 的 build/save/fresh-reopen 工程门禁和一份专属编辑非默认值实机读回；这不是 387 MatrixKey、性能、安全、安装包与人工视觉审计组成的完整 Beta qualification。

当前工程门禁的记录单位是一次合并运行而非 43 份发布 MatrixKey：全部 43 个正式图先逐项完成 formal Matplotlib 实绘与 strict O1 OriginPlan 编译，再合并进入一份 OPJU build/save/fresh-reopen；另以 10 个代表图覆盖七组非默认专属编辑。该门禁用于尽早发现 adapter、序列化与读回故障，不替代本文件第 7、11 节要求的正式 evidence manifest。

## 1. 唯一正式 Windows qualification profile

每个 Beta build 只声明一个完成 qualification 的 Windows 11 x64 reference profile：

| 项目 | 当前基线 |
| --- | --- |
| OS | 发布时仍受 Microsoft 支持的 Windows 11 x64；当前参考 Windows 11 25H2，build/edition/servicing state 随 Beta build 固定记录 |
| CPU/RAM/Disk | 6 cores、16 GB RAM、NVMe、无独显要求 |
| Display | 1920×1080；100% 与 150% DPI scaling |
| 角色 | 唯一正式功能、性能、UI 与安装资格环境 |

- Windows 10、Windows LTSC、ARM64、32-bit Windows、Windows Server、Wine/兼容层、minimum-machine profile 和 125%/200% DPI 完整矩阵均为后续 qualification，不属于当前 Beta 支持声明。
- 在其他环境可尝试运行，但 UI 和安装说明必须标为“未完成 Beta qualification”，不得暗示正式支持。
- 机器记录只保存本地测试所需的 OS/build、CPU、RAM、disk class、display/scaling；不采集硬件序列号，不自动上传。

## 2. 单一 Origin exact version qualification

- 每个 Beta build 只声明一个已完成完整 qualification 的 Origin exact version/build/bitness 组合。
- 该 exact version 必须完成正式 43 图全部 O1 OPJU 路径、live validation 和 fresh blank managed instance reopen/readback。
- 其他所有 Origin 版本一律在 preflight 返回 `VERSION_UNSUPPORTED`；不能以“2021+”、major range、相邻版本推断或 O2 降级代替 qualification。
- `originpro`、adapter、template、font、Windows build、license mode 与 43 图代表性 live OPJU evidence 都固定到该声明版本；每图 minimal/edge 的 OPJU 逻辑路径由离线 contract、validator 与稳定错误 evidence 覆盖。
- 架构仍允许后续增加 adapter/version qualification；增加版本时必须建立新的 Beta build 声明和 43 图代表性实机 evidence，不能沿用当前版本结论。当前已完成的 31 图矩阵是历史基础 evidence，新增 12 图未补齐前不得宣称 43 图 qualification 完成。

## 3. 唯一正式规模基线

第一轮只有一组正式 qualification 规模，不再维护 regular/large/boundary 多级门禁：

| 路径 | 正式 Beta qualification |
| --- | --- |
| Dataset | 100,000 rows × 20 columns |
| 单图 | 最多 100,000 plotted primitives |
| 单批次 | 20 files/charts × 每图 10,000 primitives |
| 项目 | 最多 100 charts；其中一次正式批量/导出仍受上行单批次限制 |
| 常规工作集 | 10 charts |

超过上述已验证范围允许通过 resource preflight 后 best effort 执行，但必须同时满足：

- UI 在开始前和结果上显示“超出 Beta 已验证范围”，列出超出的维度和估计资源。
- 不得静默 downsample/rasterize formal PNG/SVG/OPJU，不得改变 FieldMapping、PreparationSpec、PlotCalculation 算法/参数、预计算字段、单位或图形算法。
- 资源不足时稳定返回 `RESOURCE_LIMIT` 或 `DISK_SPACE_INSUFFICIENT`，项目权威状态不受损。
- 恢复建议只能是用户在外部显式准备较小数据、减少图表/批次或另存目标；系统不能借资源问题暴露隐藏 filter/aggregate 或自动改变科研语义。
- 超范围 best effort 的成功记录不是扩大正式支持范围的证据。

## 4. Preview 简化与正式完整性

- thumbnail 每视图最多 5,000 visible primitives。
- interactive 每 axes 最多 20,000 visible primitives。
- 简化规则版本化、确定性，并显示“预览已简化”、完整数量、显示数量和方法。
- autoscale range、PlotCalculationSpec、error/interval 始终使用 full data；preview 简化只改变可视采样。
- 声明支持规模内的 formal PNG、SVG 与 OPJU 一律使用 full PreparedDataset、PlotCalculationResult 或用户预计算表。
- 导出前按 100k 正式范围估计 primitive count、预计文件大小、内存和磁盘。估计接近当前资源能力时显示明确 warning；无法安全完成时返回稳定资源错误。不得以固定 2M primitives/200 MB 商业级阈值替代本 Beta 的实际 preflight。

## 5. Reference profile P95 预算

除明确标 P50 外，以下均在第 1 节唯一 reference profile 上测量。

### 5.1 启动与交互

| Scenario | Budget |
| --- | ---: |
| desktop shell interactive | ≤ 2 s |
| Python Core ready | ≤ 5 s |
| input/click/task-card acknowledgement | ≤ 100 ms |
| style-only patch preview | ≤ 2 s |

Shell interactive 不等待云、Origin 或 Core ready。任何预计或实际超过 2 秒的操作显示真实阶段/单位进度，不显示假进度或隐藏推理。

### 5.2 导入

| Scenario | Budget |
| --- | ---: |
| 100 MB CSV | ≤ 12 s |
| 50 MB XLSX | ≤ 30 s |

导入预算覆盖授权临时复制/hash、完整解析、内部格式、quality summary、对象移动与 SQLite commit；不能通过跳过安全或完整解析达标。1 GB CSV 不属于当前 Beta qualification。

### 5.3 Preview 与批次

| Scenario | Budget |
| --- | ---: |
| 100k-data preview，最多 20k visible primitives | ≤ 3 s |
| 20 charts × 10k batch preview | ≤ 30 s |

100k preview 的 range、quality summary 与固定 PlotCalculation 仍基于 full data。第一轮不设置 1M preview 性能门禁。

### 5.4 Formal export

| Scenario | Budget |
| --- | ---: |
| single 100k formal PNG | ≤ 5 s |
| single 100k formal SVG | ≤ 10 s |
| single 100k O1 OPJU build + fresh reopen | ≤ 60 s |
| 20-chart O1 OPJU build + fresh reopen | ≤ 180 s |

OPJU 预算只在该 Beta build 声明的唯一 exact Origin version 与可用 license 下测量，包含 preflight、build、save、exit、fresh reopen、readback 和 atomic move。

### 5.5 Agent

| Scenario | Budget |
| --- | ---: |
| ContextEnvelope build | P95 ≤ 1 s |
| built-in structured AgentDecision | provider-inclusive P50 ≤ 8 s；P95 ≤ 20 s |

Provider latency单独记录 DNS/connect/TLS/TTFB/complete，不删除慢样本美化端到端预算。

## 6. Memory 与磁盘

| State | Budget |
| --- | ---: |
| idle Electron + Python Core | ≤ 700 MB working set |
| 正式 qualification workload peak | ≤ 2 GB |

- 资源预检评估 Core、renderer、isolated worker 与 managed Origin 总峰值；无法在当前机器安全完成时，在启动正式任务前返回 `RESOURCE_LIMIT`。
- 内存压力下可把新计算任务并发降为 1，但不能改变算法、提交半对象或强杀 Core。
- 导入复制前，目标固定磁盘 free bytes 至少为 `estimated_landed_bytes × 2.5`；不足时在复制前返回 `DISK_SPACE_INSUFFICIENT`。
- 正式导出需预留 temp、final 与 validation 空间；第一轮无自动更新和每日备份磁盘预算。

## 7. 43 图正式能力矩阵

### 7.1 固定 387 paths

正式第一轮 43 个 chart type，每个至少三种 fixture：

1. `minimal_valid`：最小合法字段与数据。
2. `representative_research`：真实科研语义、单位、固定计算/预计算字段/annotation 的代表样本。
3. `edge_error`：缺失、非有限值、非法 Log10、字段/单位/预计算要求/Origin capability 等边界或稳定错误。

每个 fixture 固定 formal PNG、formal SVG、O1 OPJU 三个基础产物/预期错误 path，因此为 `43 × 3 × 3 = 387`：

- formal PNG：129 条。
- formal SVG：129 条。
- O1 OPJU：129 个逻辑 MatrixKey，其中 43 个 representative research 在当前 Beta build 声明的唯一 Origin exact version 完成 live+fresh-reopen；43 个 minimal valid 与 43 个 edge/error 通过同一 typed plan 的离线 contract/validator 和预期稳定错误 evidence，不重复启动 86 次 Origin COM。

### 7.2 Origin P1 正式/隐藏边界

P1 曾使内部代码面扩展为 52 图，但正式范围只增加 X01、X02、X03、X05、X09、X13、X23、X24、X35、X36、X38、S07；原 31 图与这 12 图合计 43 图。X07、X11、X12、X15、X16、X17、X18、X19、X37 标记为 `internal_hidden`，不进入 387 MatrixKey、图形库、Agent create capability 或正式导出承诺。

新增正式图的 visual evidence 优先满足以下硬门槛：

- A 级：Origin 随附 OPJU 中的图页与其链接工作表直接成对提取。
- C 级：只使用 Origin 随附官方样例数据，并在 Origin 中按固定模板/固定规则重新生成参考图。
- `reference.png`、`data.csv`、Matplotlib、产品 OPJU、fresh-reopen Origin PNG 和 provenance hash 必须属于同一案例。
- 缺少参考图或同源数据的新增图不得伪造 Origin 官方 evidence。X24 与 S07 作为明确例外，以固定合成数据建立 Matplotlib/Origin 三栏视觉基线并标注 `synthetic_visual_validation`；该标识不能省略，也不能视为 A/C 级 Origin 官方同源 evidence。

当前同源视觉审计覆盖 X01、X02、X03、X05、X09、X13、X23、X35、X36、X38；X24、S07 使用冻结合成视觉验证。九个隐藏图不计视觉通过数；双 Y 轴网格图不在实现范围。

Preview/interactive 是另外的必测路径，不计入 387。`edge_error` 可由匹配预期 code/schema/details 的稳定错误证据通过，不要求生成二进制；不得把应成功路径重标为预期失败。

### 7.3 覆盖维度

- PlotSpec canonical JSON、ResolvedRenderPlan normalized hash/golden。
- thumbnail/interactive、formal PNG/SVG、O1 live+fresh-reopen OPJU。
- BatchSpec、FigureSpec、PreparedDataset/PlotCalculationResult/预计算字段、axes/ticks、error/warning。
- 中文、英文与中英混合科研术语、SafeRichText 与字体 fallback。
- cancel、Core/worker crash、request idempotency、expected-version conflict。
- formal full-data assertion、preview simplification disclosure 与 parity tolerance。

### 7.4 MatrixKey 与 evidence

```text
MatrixKey
├─ beta_build
├─ chart_type_id
├─ fixture_id
├─ artifact_path: thumbnail | interactive | formal_png | formal_svg | opju_o1
├─ expectation: binary_artifact | stable_error
├─ renderer_or_adapter_version
├─ origin_version_exact? # opju_o1 必填且本 build 唯一
├─ windows_reference_profile
├─ locale_profile
└─ test_case_id
```

Evidence 固定 input/reference dataset、spec/plan、artifact/validator、dependency、fixture 与 build hashes，以及 timing/memory 和 stable error。重试不是新 case，不能覆盖第一次失败记录。

### 7.5 导入与分层诊断 fixtures

387 是图形三格式基础矩阵，不含导入 fixture。导入另设约 30 个冻结 golden：

- Excel 10：多 sheet、多个 region/header、`.xlsx/.xls/.xlsm` 只读、缓存公式值、单位行与来源坐标。
- TXT 10：preamble/DataBlock/postamble、encoding/delimiter/header、multi block/sweep/channel、metadata label 与普通 CSV 复用路径。
- 最小追问 5：每例只能生成一个明确问题。
- 可操作拒绝 5：超出清单、重复规范化列名、无缓存公式值等稳定拒绝。

边界变体由冻结 generator/version/seed 从基础 fixture 生成，但 expected oracle 随 manifest 固定，不能在运行时从被测实现生成。正式 43 图另有字段映射/准备/固定计算/预计算/PlotSpec fixtures。

每个 case 保存分层快照：`file read → region candidates/selection → table parse → mapping → PreparedDataset/PlotCalculationResult → PlotSpec → render → export`。首次偏差决定责任层；下游不得用容错掩盖上游错误。错误族按 `IMPORT/MAPPING/PREPARE/PLOTSPEC/RENDER/EXPORT/TEST` 归档并支持分层回放。

### 7.6 基础图形参数化泛化门禁

同源视觉 evidence 只证明某一已锚定案例的默认外观；基础泛化 evidence 证明绘图逻辑没有把组数、范围或样例几何写死。两者分别保存、分别判定，不得互相替代。

- 正式 43 图按结构签名归类，以冻结 generator version、seed、manifest 从独立基础 fixture 生成变体；expected oracle 随测试资产固定，运行时不得调用当前 compiler/resolver/renderer 生成 oracle。九个隐藏 adapter 可继续运行额外内部回归，但其结果不得计入正式 coverage。
- 适用结构至少覆盖组数 `1/2/3/5`、不同点数/类别数、量级缩放和平移、跨零与全负、零/对称/非对称误差、长中文/英文/混合标签及可选字段缺失；不适用维度须由结构签名显式声明，不能静默跳过。
- 每个适用 case 至少断言全部几何有限、同组柱/区间不重叠、正负堆积分别累加、误差棒绑定正确 series/axis、轴范围覆盖可见数据与误差、series-color-legend identity 一致；空间不足必须产生规定 warning/error，不能通过截断或隐藏通过。
- Matplotlib 对所有适用 case 执行完整矩阵；Origin 对每个结构签名执行代表性变体的 typed plan、build 与 fresh-reopen 检查。除显式标记合成视觉验证的 X24/S07 外，每个正式图仍至少保留一个参考图和同源数据锚定的 Origin 外观证据。
- 基础泛化门禁未通过前，不实现、不迁移组合 compiler 的测试 oracle；先修复现有基础函数和解析逻辑，再冻结新的组合基线。
- 用户重复使用已准入配方时只运行常规 Schema、mapping、capability、render/export 校验，不为每次复用重新执行本节 qualification。

### 7.7 逐图编辑、符号与色板门禁

- 冻结 43 图 `ChartEditCapabilityProfile` snapshot，并与 PRD §8.5 逐图白名单逐项对照；UI capability、Agent Context、validator 和 export adapter 必须由同一 profile 生成。九个隐藏 ID 出现在任一产品 capability 即失败。
- 每个 allowed operation 至少有一条成功 path，并验证新 PlotSpec/version/hash、Matplotlib 输出、Origin typed mapping 和适用时 fresh-reopen readback；每个未声明 operation/target/payload field 至少有稳定 `Unsupported`/`PATCH_CAPABILITY_NOT_SUPPORTED` 证据，原版本与批量事务不变。
- 全部 12 种 MarkerSymbol 与闭合符号的 `solid/open/hollow` 在代表性 line/scatter/error/dual-Y 结构中覆盖；`open` 必须遮住下层线，`hollow` 必须保留下层线，`plus/cross` 的 `open/hollow` 必须稳定不支持。Origin 原生值与 Matplotlib marker 可不同，但读回语义必须相同。
- 16 个 PaletteRef 固定 palette/version/source/hash 和全部 8-bit sRGB colors/stops；覆盖分类、连续、发散、反向、离散 levels 与自定义 `#RRGGBB`。跨 renderer RGB 每通道精确；指定 Origin 官方资产缺失或 hash 不一致时稳定失败，不得读取用户色板、同名替代品或产生漂移结果。
- 类别数 15、16 和超过颜色+符号容量的边界分别验证不循环、稳定 identity、联合编码与 warning/阻止；X23/X24/X35/X36 默认左右轴均为中性正常字重细线，显式轴着色只改变样式。

## 8. Beta 测试层级

1. Schema/domain strict union、generated TS types 与 stable error registry。
2. Excel/TXT/CSV deterministic import、FieldMapping、PreparationSpec/Unit/source coordinates、archive/Excel 安全与 `.plotproj` integrity。
3. 九类 PlotCalculation golden、43 图字段/固定计算/预计算契约、完整数据/mask/hash 与禁止通用 AnalysisSpec/FitSpec。
4. Resolver/render/layout/axis/ticks/font/color/physical size、逐图编辑 capability、Origin 对齐符号/色板与 cross-renderer semantic parity。
5. 单一 Origin exact version 的 O1 live/save/fresh-reopen/readback。
6. Electron↔Python E2E、single-instance、preload、task/cancel/crash/idempotency/version conflict。
7. strict local_only 零出站、credential/log/bundle 禁止字段、恶意 archive 与签名安装包验证。
8. Reference profile 性能/内存/磁盘与安装 smoke test。

模型相关测试分三层且不得混算：确定性程序测试；固定模型响应的 AgentDecision/validator 契约测试；真实模型的中英/混合科研术语质量评测。真实模型输出不作为确定性 oracle。

当前 Beta 不要求多 OS/DPI/minimum-machine、长时间 soak、生产级云攻击矩阵、SBOM 流程或多版本 Origin qualification。依赖名称、锁文件/包 hash、许可清单和已知风险仍随 build 固定，不能因简化流程绕过签名或 secret 边界。

## 9. 可复现测量协议

每个 performance case 固定：

- cold/warm state 与 cache policy。
- reference dataset/object/package/fixture hash。
- 本地 Windows reference profile、app commit/build、Python、SQLite、importer/preparation/plot-calculation、renderer、Origin/adapter/template/font/dependency versions。
- 预先定义的 sample count；普通路径至少 10 次，昂贵 OPJU 路径至少 5 次，并保留全部失败/timeout。
- P50/P95 使用 nearest-rank；失败不从结果中删除。
- 相对前一已批准 Beta baseline P95 退化 >15% 或越过绝对预算时阻断并调查。

修改 fixture、机器、测量点或算法版本会建立新 baseline，不能原地改写历史结果。

## 10. 不可豁免 Beta blockers

以下任一项出现时禁止分发 Beta build：

- data loss/corruption，任务失败或崩溃损坏已有项目权威状态。
- silent wrong science；导入区域、FieldMapping、UnitSpec、PreparationSpec、PlotCalculation 算法/参数/seed/missing policy 或用户预计算字段被静默改变。
- 声明支持规模内 formal downsample、renderer/plot-calculation algorithm swap 或 capability downgrade。
- 非原生结果被宣称为 O1，或声明的唯一 Origin exact version fresh reopen 关键语义失败。
- credential、prompt、文件路径、列名、单元格值、数据摘要或 secret 泄漏。
- 43 个正式图形中任一声明输出路径/适用 fixture 失败，或隐藏九图被产品 create/export capability 暴露。
- 当前声明的基础图在冻结泛化矩阵中违反有限几何、无重叠、堆积、误差绑定、范围覆盖或 series-color-legend identity 任一不变量，或测试 oracle 由被测实现动态生成。
- 任一逐图白名单操作不能稳定映射到 Matplotlib/Origin，未声明编辑被静默接受/近似，符号 interior 语义错误，palette RGB/version 漂移、类别颜色循环，或双 Y 默认轴被擅自加粗/着色。
- 安装包 signature、hash 或 Windows code signature 验证可被绕过。
- 已知 blocker/critical，或只有靠删除失败样本、放宽 fixture/tolerance、替换未审阅 golden 才通过。

这些底线不可 waiver。其他不影响正确性、安全、可追溯或完成路径的缺陷可以进入带 owner、影响、workaround 的 Beta known issues。

## 11. 每个 Beta build 发布检查单

1. 固定 commit、build、dependency lock/hash、fixture/golden 与 Decision baseline。
2. 43 图 387 个逻辑 MatrixKey coverage 和额外 preview/interactive coverage 零缺口；其中昂贵 Origin 自动化按 representative 实跑、其余离线验证拆分记录。
3. 当前 build 唯一 Origin exact version 的完整 43 图 representative O1 live+fresh-reopen report，以及 minimal/edge 的离线 contract/error report；X24/S07 合成视觉 evidence 与官方同源 evidence 分栏标识。
4. 约30个导入 golden、43图字段/准备/固定计算/预计算契约与 full-data formal assertions。
5. 当前基础图的冻结泛化 manifest、完整 Matplotlib matrix、按结构签名的代表性 Origin report、跳过原因和不变量结果；确认未用当前实现生成 oracle。
6. 43 图编辑 capability snapshot、allowed/unsupported 报告、隐藏九图无暴露断言、12种符号/闭合符号3种interior/`plus/cross`非适用拒绝、16色板 frozen-RGB/parity、类别容量边界和双Y默认样式报告。
7. Reference profile 性能、≤2 GB peak、磁盘/resource preflight 结果。
8. strict local_only、credential/log/DiagnosticBundle 禁止字段和恶意导入检查。
9. 简化云额度的共享计数与 `client_run_id` 重试不重复扣费检查；自定义 provider/本地能力不受影响。
10. 人工分发安装包的 SHA-256、发布签名与 Windows code signature 验证。
11. Known issues、稳定错误、恢复动作和单一 go/no-go 记录。

每份 evidence 固定 manifest/source/test-runner/app/PlotSpec/model/profile/prompt/Unicode normalization hashes；任何一项变化都形成新 evidence。测试运行时不得生成 oracle。

检查单由指定 Beta release owner 汇总并由对应科学/Origin实现负责人复核其专业证据；不要求商业级多角色签署链。任何 build 内容变化都生成新的 build/hash/checklist。

## 12. 首批 10–15 人成功门禁

这是第二批内测 go/no-go，不依赖 analytics：

- ≥80% 参与者在 sample project 上独立完成第一张图。
- ≥60% 用自己的真实数据在无 staff takeover 下完成第一张图。
- ≥60% 明确表示愿意用另一份真实数据继续使用。
- 至少 1 人完成批量绘图/审阅路径。
- 至少 1 名 Origin 用户导出 OPJU 并在 Origin 中继续编辑。

记录方式是经同意的任务观察、结构化访谈或问卷。Staff 一旦接管字段映射、方法选择或实际操作，该次不计“独立完成”。

## 13. 后续工程成熟度

多 Windows/DPI/minimum machine、多 Origin exact versions、1M/更大数据 qualification、长时间 soak、生产级云账本与攻击矩阵、自动更新、通用迁移/备份、SBOM 自动化和多角色签署均属于 Beta 验证后的后续工程化能力。引入时必须更新 Decision ID、PRD、本文件、SPEC-INDEX 与相应 evidence；不得把未来能力解释为当前 v1 强制要求。
