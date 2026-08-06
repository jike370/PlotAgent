# PlotAgent v1 规格索引与小规模邀请制 Beta 设计基线

> 状态：v1 数据/计算范围收敛；正式范围固定为 43 图，M6 基础泛化与逐图编辑/Origin 样式工程门禁已实现，内部可组合绘图底座仍待实现；M7 小规模邀请制 Beta qualification 尚未执行
> 基线日期：2026-08-07
> 适用范围：权威文档、冲突优先级、requirement/evidence matrix、workstream 入口与冻结变更流程
> 相关文档：[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)、[实施拆分与里程碑计划](./IMPLEMENTATION-PLAN.md)、[小规模 Beta 性能测试与发布门禁](./PERFORMANCE-TEST-RELEASE.md)

## 1. 冻结含义与非含义

“小规模邀请制 Beta 设计基线”表示：

- 第一轮产品行为、对象边界、进程/云/本地信任边界和跨模块 Schema 语义已足够直接拆分实施。
- 原 31 图加 X01/X02/X03/X05/X09/X13/X23/X24/X35/X36/X38/S07 形成正式 43 图；P1 另九图只保留内部代码/回归且不暴露 create/export。确定性导入/一次字段映射、九类固定绘图计算、预计算字段、批量/组合、自然语言、PNG/SVG/O1 OPJU和科学可追溯构成v1；通用数据处理与分析/拟合平台后移。
- M6 补充范围先固化基础泛化、正式/隐藏 availability、逐图编辑 capability、Origin 对齐12符号/适用interior/16色板，再实现 StructureUnitDefinition/ChartRecipe、封闭关系、确定性 compiler 和 43 图迁移；用户搭建器和自定义配方库在 M6 后实施。
- 每项核心需求都有权威契约、workstream、计划入口、稳定错误 owner 和未来验收 evidence。
- 冲突审计已按本文件矩阵完成，当前已知旧口径已清除。
- 后续产品或跨模块行为变化必须新增/更新 Decision ID 并同步权威文档，不得由实现自行选择。

它不表示：

- M7 的真实用户成功指标、生产签名发布、reference 性能与完整邀请制 Beta gate 已经通过。
- 43 图/固定计算/Origin 每个 adapter 的底层 property map 已在本文展开；逐图用户能力以 PRD §8.5 和版本化 profile 为准，后续 AnalysisSpec/FitSpec 尚不可用。
- 单一 Origin exact version 已完成一次 43 图合并 build/save/fresh-reopen 工程门禁；它不是 43 份发布 MatrixKey 与完整 evidence manifest，也不表示 reference 性能、安全或生产签名安装包 Beta gate 已通过。
- 当前 UI prototype 的种子数据或模拟交互是后端行为证据。

每图/每算法完整参数、property map 和fixture细节由W3/W4/W6 backlog在现有公共契约内细化；如果细化会改变用户选择、科学语义、对象版本、formal完整性或O1能力，必须回到Decision变更。

## 2. 权威层级与冲突处理

### 2.1 优先关系

1. 用户最新明确确认，必须先记录/更新到 `PRODUCT-DECISIONS.md`。
2. `PRODUCT-DECISIONS.md`：全部确认决策和冻结边界。
3. 对应专门契约文档：该领域可实施字段、状态机、错误、负面边界与验收。
4. `PRD.md`：跨领域产品流程、信息架构和第一轮总范围。
5. `BACKEND-ARCHITECTURE.md` / `DOMAIN-CONTRACTS.md`：系统总图、依赖方向与公共Schema。
6. `PRODUCT.md` / `DESIGN.md`：战略、品牌和UI视觉/交互约束。
7. `README.md`、研究资料、prototype code/seed/screenshots：导航、证据或探索材料，不覆盖冻结契约。

不同层出现冲突时停止实现：把最新确认写入Decision，修正专门契约与PRD，再继续。实现者不能通过“更具体文档优先”保留与新Decision冲突的旧细节。

### 2.2 文档权威范围

| Document | 权威范围 | Primary workstream | 计划实现入口 | Future acceptance evidence |
| --- | --- | --- | --- | --- |
| [PRODUCT-DECISIONS](./PRODUCT-DECISIONS.md) | 全部确认产品决策与变更ID | Product/Architecture | Decision review | ID唯一/连续、冲突矩阵 |
| [PRD](./PRD.md) | 用户流程、首轮范围、信息架构、总验收 | Product + all W | cross-workstream backlog | requirement coverage/E2E |
| [DESIGN](../DESIGN.md) | 浅色克制UI、tokens、排版、无障碍、禁忌 | W1/W5 UX | `src/renderer/` | visual/a11y/display matrix |
| [PRODUCT](../PRODUCT.md) | 产品定位、价值与高层方向 | Product | roadmap | scope review |
| [BACKEND-ARCHITECTURE](./BACKEND-ARCHITECTURE.md) | 进程、IPC、领域服务、依赖方向 | W0/W1/Core leads | Core/Main boundaries | architecture/E2E |
| [DOMAIN-CONTRACTS](./DOMAIN-CONTRACTS.md) | 公共对象、StructureUnit/ChartRecipe、AgentDecision/ActionPlan、Schema | W0/W4 | `src/plotagent/contracts/`, `schemas/`, recipe compiler | schema/codegen/graph validation/round-trip |
| [PROJECT-STORAGE](./PROJECT-STORAGE.md) | workspace、CAS、`.plotproj`、import | W2/W9 | storage/import packages | atomicity/archive/reopen |
| [DATA-TRANSFORMS](./DATA-TRANSFORMS.md) | FieldMapping、PreparationSpec/PreparedDataset、Unit/source provenance | W2 | preparation/units/provenance | import/preparation golden |
| [ANALYSIS-ENGINE](./ANALYSIS-ENGINE.md) | 九类 PlotCalculation、预计算字段与后续分析边界 | W3 | plot-calculations/precomputed validators | algorithm/field golden |
| [FITTING-SYSTEM](./FITTING-SYSTEM.md) | v1预计算拟合输入与未来拟合分期边界 | W3/W4/W6 | precomputed validators/adapters | no-fit/precomputed paths |
| [RENDERING-PIPELINE](./RENDERING-PIPELINE.md) | Recipe compiler、动态布局、Resolver、axes/ticks、physical/text/parity | W4/W6 | rendering/recipe/resolver | compiler/plan golden/generalization/parity |
| [ORIGIN-EXPORT](./ORIGIN-EXPORT.md) | OPJU content、O1、adapter、reopen | W6 | origin worker/adapters | 单一exact-version 93 matrix |
| [TASK-RUNTIME](./TASK-RUNTIME.md) | Interaction/Execution、scheduler/cancel/recovery | W1/W2/Core | task scheduler/events | fault/idempotency E2E |
| [AGENT-CONTEXT](./AGENT-CONTEXT-AND-PROVIDERS.md) | Context/Provider/Disclosure/AgentDecision/audit | W7 | agent/provider packages | provider/security matrix |
| [CLOUD-CONTROL-PLANE](./CLOUD-CONTROL-PLANE.md) | Invite/长期凭据/原子共享计数/proxy/人工包 | W8 | Beta control plane | idempotency/degrade/package verify |
| [LOCAL-SECURITY](./LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md) | local_only、安全、日志/本地诊断、known-pair兼容 | W9 | security/compatibility packages | zero-egress/fault/privacy |
| [PERFORMANCE-TEST-RELEASE](./PERFORMANCE-TEST-RELEASE.md) | 单一平台/规模/Origin、逻辑 MatrixKey、Beta blockers/checklist | W10 | release/evidence harness | Beta build checklist |
| [IMPLEMENTATION-PLAN](./IMPLEMENTATION-PLAN.md) | W0–W10、依赖、spikes、milestones | All owners | proposed entries per W | milestone exit evidence |
| [chart-library-research](./chart-library-research.md) | 157长期taxonomy与研究建议 | W4 research | registry backlog input | 仅研究，不等于准入 |
| [README](../README.md) | 仓库导航、当前prototype运行 | Repository maintainers | existing app skeleton | commands/current status |

## 3. Requirement / Evidence Matrix

`Status=frozen-design` 只表示契约完整一致；所有 `Future evidence` 仍须实现阶段产生。

| Req | Frozen requirement | Authority | W | Planned entry | Future evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R-START | 工作入口仅示例/导入/打开项目；模型模式不替代 | PD-B04/B05,Z01；PRD 5.1；LOCAL §1 | W1/W9 | renderer startup/model settings | first-run UI/E2E no-network | frozen-design |
| R-NETMODE | builtin/custom/local_only；localhost=custom；切换不改项目 | PD-Z02；LOCAL §1–2 | W9 | network-policy | mode/state/project hash tests | frozen-design |
| R-ZERO | strict local_only绝对零出站；第一轮无update_only例外 | PD-Y15,Z03；LOCAL §2；CLOUD §9 | W8/W9 | network policy | packet capture + denied endpoints | frozen-design |
| R-AGENT-UNION | 唯一四类 ActionPlan/NeedsInput/Unsupported/NoChange | PD-P13,X13；DOMAIN §7 | W0/W7 | AgentDecision schema | union invalid corpus/codegen | frozen-design |
| R-NO-TOOLS | 模型无本地/领域工具、URL/path、tool loop；structured transport非授权 | PD-J01,O02/O12,P17,X01；AGENT §1 | W7 | provider/validator | tool-like output rejection | frozen-design |
| R-CONTEXT | 本地Context/Conversation权威、版本refs、限样本出境与Disclosure | PD-X03–X09；AGENT §3–6 | W7 | context/reducer/disclosure | size/hash/stale/consent tests | frozen-design |
| R-PROVIDER | builtin proxy；custom Responses→Chat；P1/P2 one repair/P0 | PD-X10–X12；AGENT §7–10 | W7 | providers | synthetic probes/repair trace | frozen-design |
| R-INVITE | 无账号；同InviteGrant不限设备共享额度；无硬件指纹 | PD-L03–L06,Y01–Y06；CLOUD §3–4 | W8 | invite/credential | multi-device/reinstall/revoke | frozen-design |
| R-QUOTA | 原子共享计数+client_run幂等；无reserve/settle；custom不扣 | PD-Y07–Y14；CLOUD §5–8 | W8 | counter/proxy | timeout/restart/no-double-charge | frozen-design |
| R-STORAGE | 本机fixed-disk workspace；SQLite single writer；immutable CAS；`.plotproj` snapshot | PD-Q01–Q13,Z06；STORAGE §1–4,8 | W2/W9 | storage/project packages | crash/reopen/hash/network reject | frozen-design |
| R-IMPORT | Excel多sheet/TXT多block确定性导入；结构后一次mapping；只问一个问题或拒绝 | PD-D13,Q14–Q20,U06–U11,Z07/Z08；STORAGE §5–9 | W2/W9 | excel/text import pipeline | ~30 golden+layer replay/security | frozen-design |
| R-NO-CELL | 原始只读，无row-index任意改单元格 | PD-D01,H08,U02/U05；PRD 7.1 | W2/W5 | SourceDataset UI/services | forbidden action/schema tests | frozen-design |
| R-PREPARE | 仅本地封闭PreparationSpec；PreparedDataset不是通用数据产品；无开放Transform | PD-D02,U01–U20；TRANSFORMS | W2 | preparation/provenance | union/golden/no-hidden-transform | frozen-design |
| R-PLOTCALC | 九类固定PlotCalculation、完整数据、固定默认/mask/hash、三renderer同结果 | PD-H09,S01–S20；ANALYSIS | W3/W4/W6 | plot-calculation registry | algorithm golden/no-recompute | frozen-design |
| R-PRECOMPUTED | K05/K21/K22/S01/S05/S21/S25/S31/S34需预计算字段；v1无Analysis/Fit | PD-T01–T20；FITTING；PRD 9.2 | W3/W4/W6 | field validators/registry UI | valid/missing/invalid paths | frozen-design |
| R-CHARTS | v1正式43图：原31图+X01/X02/X03/X05/X09/X13/X23/X24/X35/X36/X38/S07 | PD-E08/E25；PRD 6.2/10.1 | W4/W6 | availability-aware chart registry | 43 official ID + 387 matrix | reopened |
| R-P1-EXT | 内部52图代码面分为12正式新增与9个internal_hidden；X24/S07标注合成视觉证据，双Y网格除外 | PD-E09/E26/E27；PRD 6.2；PERF §7.2 | W4/W6 | registry visibility + evidence provenance | 10同源+2合成视觉；9 hidden no capability | reopened |
| R-NO-IMAGE | v1无科研图像、地图、ROI或图表+图片混合 | PD-E24/E11,M03；PRD 5.5/17 | W4/W5 | registry/Figure schema | forbidden formats/actions | frozen-design |
| R-BATCH | 完全同构、一次mapping/同Preparation/PlotCalculation；partial成功，无逐文件例外 | PD-C,D,G,S20,U17/U18；PRD 5.2/6.4 | W2/W5 | BatchService/review | signature/partial/review E2E | frozen-design |
| R-FIGURE | 仅数值固定布局、版本refs、公共图例、源更新不自动替换 | PD-F01–F06；DOMAIN §5 | W5 | FigureService/UI | version/layout/legend tests | frozen-design |
| R-EXPORT3 | 正式导出仅PNG/SVG/OPJU；clipboard非正式 | PD-K01/K02；PRD 10.4 | W4/W6 | ExportService | format allowlist/records | frozen-design |
| R-FORMAL | 声明规模内Formal三格式full data；preview≤5k/20k且range/PlotCalculation full | PD-H11,V04/V05,AA05/AA06；RENDER §2；PERF §3–4 | W4/W6 | resolver/adapters | count/assertion/resource preflight | frozen-design |
| R-RECIPE | 结构单元与版本化ChartRecipe通过语义端口和封闭关系形成组件图；官方/自定义运行时同构；配方不含数据、FieldId、路径、计算结果或代码 | PD-E13–E23,P21–P27；DOMAIN §3.2；PRD 4.7/5.6 | W0/W4/W6 | recipe schemas/registry/validator/compiler | graph/port/relation/canonical compile/no-executable corpus | frozen-design-pending-implementation |
| R-GENERALIZE | 正式43图先通过冻结生成器与结构不变量；Matplotlib全矩阵、Origin按结构签名代表性验证；隐藏图回归不计正式覆盖 | PD-V21–V25,AA21–AA25；RENDER §2.1/14；PERF §7.6 | W4/W6/W10 | generalized fixture harness/layout invariants | fixed manifest/full mpl/representative Origin reports | baseline-implemented-origin-expansion-pending |
| R-EDIT-STYLE | 43图逐图编辑白名单；12种Origin对齐符号与适用interior、16冻结sRGB色板、>15颜色+符号不循环、双Y默认中性细线；未声明请求稳定不支持 | PD-I13–I18,P28–P32,V26,AA26–AA29；PRD §8.5–8.6；DOMAIN §4.4/6；RENDER §7；PERF §7.7 | W0/W4/W6/W10 | capability profiles/style registries/resolver/adapters | snapshot/allow-deny/parity/readback/capacity tests | engineering-gate-implemented-beta-evidence-pending |
| R-RENDER | 单一ResolvedRenderPlan、deterministic axes/ticks/layout/text/style；数据和画布驱动动态几何 | PD-V01–V26；RENDER | W4/W6 | recipe compiler/resolver | compiler/plan golden/generalization/style parity tolerance | reopened |
| R-OPJU | 正式43图OPJU全部O1；无LabTalk/raster fallback；两阶段原子；九图隐藏不承诺 | PD-K04,W01–W20,E26；ORIGIN；PERF §2 | W6 | origin adapters/worker | 单一 exact version 43 representative + 离线 edge/error | reopened-base31-implemented |
| R-ORIGIN-V | 每Beta build只声明一个qualified Origin exact version；其他unsupported | PD-K03/K12,W12,AA03；PERF §2 | W6/W10 | build declaration/preflight | one exact-version matrix | frozen-design |
| R-TASK | Interaction≠Execution；提交/取消/幂等；崩溃不损坏且用户明确重试 | PD-R01–R20,Z18；TASK | W1/W2 | scheduler/events | state/fault/commit E2E | frozen-design |
| R-LOCAL-PRIV | 无项目加密承诺；ACL/BitLocker；temp ACL；无secure erase宣称 | PD-L07/L08,Z04/Z05；LOCAL §3–4 | W9 | temp/security UI | ACL/wording/cleanup tests | frozen-design |
| R-LOG-DIAG | log allowlist14d/100MB；无analytics；Bundle默认结构/统计/hash，单次同意才含脱敏数据且仅本地 | PD-J10,Z10–Z12；LOCAL §8–10 | W9 | logger/local diagnostics | preview/consent/forbidden scan | frozen-design |
| R-MIGRATE | 不兼容默认拒绝；仅known source→target一次性迁移且不改science/visual | PD-Z13–Z18；LOCAL §11–12 | W9 | compatibility/known migrator | crash injection/semantic hash | frozen-design |
| R-CLOUD-MIN | 云仅redeem/credential/proxy/atomic quota/idempotency；无sync/config/update/diag | PD-L06,Y11–Y14；CLOUD §1–8 | W8 | Beta control plane | API/log/degrade tests | frozen-design |
| R-DISTRIBUTION | 无应用内更新；人工包验证发布签名/hash/code-sign | PD-Y15–Y19；CLOUD §10 | W8/W10 | package verification | three tamper blocks | frozen-design |
| R-PERF | 单一Win11 profile、100k正式规模、5k/20k preview、≤2GB与固定P95 | PD-AA01–AA11/AA15；PERF §1–6/9 | W10 | performance harness | reference baseline reports | frozen-design |
| R-MATRIX | 43×3×(PNG/SVG/OPJU)=387 个正式逻辑 MatrixKey；preview另测；Origin 43 representative live，其余 OPJU 离线 contract/error | PD-AA12/AA13；PERF §7 | W0/W4/W6/W10 | MatrixKey/evidence | zero-gap coverage reports | reopened-base279-implemented |
| R-RELEASE | 不可豁免底线、Beta checklist、first-beta go/no-go | PD-AA16–AA20；PERF §10–12 | W10/all | release/evidence | fixed hashes/checklist/user study | frozen-design |
| R-UI | 浅色克制、无卡片堆叠/玻璃/深色科幻/渐变文字，键盘/a11y/reduced motion | DESIGN；PD-D/F/L | W1/W5 | renderer design system | visual/a11y/display matrix | frozen-design |

## 4. Stable Error Ownership Index

| Owner | Prefix/family | Escalation boundary |
| --- | --- | --- |
| W0 Contracts | SCHEMA/PROTOCOL/registry | Schema shape与code唯一性 |
| W1 Desktop | CORE/IPC/SINGLE_INSTANCE/CREDENTIAL_ACCESS | 进程/桌面边界 |
| W2 Data | PROJECT_STORAGE/IMPORT/MAPPING/PREPARE/ARCHIVE/SOURCE_DATASET/UNIT | 导入、准备与存储 |
| W3 Plot Calculation | PLOTSPEC_CALCULATION/PLOTSPEC_PRECOMPUTED/MISSING_SEMANTICS | 固定计算与预计算字段 |
| W4 Render | PLOT/PATCH/CHART/AXIS/RENDER/PNG/SVG/FONT | Plot/Matplotlib |
| W5 Workflow | BATCH/ISOMORPHIC/REVIEW/FIGURE/SCOPE | 批次/组合 |
| W6 Origin | Origin fixed code registry | OPJU/preflight/validation |
| W7 Agent | PROVIDER/TLS/AUTH/SCHEMA_INVALID/EGRESS/TARGET | Provider/Agent boundary |
| W8 Cloud | INVITE/DEVICE_CREDENTIAL/QUOTA/RATE/IDEMPOTENCY | Beta control plane |
| W9 Local lifecycle | NETWORK/TEMP/LOG/DIAGNOSTIC/SCHEMA/KNOWN_MIGRATION/LEGACY | local security/compatibility |
| W10 Release | TEST_HARNESS/EVIDENCE/INSTALLER | gate orchestration only |

同名通用错误（例如 `RESOURCE_LIMIT`、`CANCELLED`）必须带结构化 `subsystem`/stage 或在registry中只有一个公共定义；不能让多个W创建语义不同的同名code。

## 5. Implementation-Readiness Checklist

| W | Contract | Dependency | Deliverables | Parallel boundary | Acceptance | Error owner | Done definition | Ready |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| W0 | DOMAIN + all schemas | none | schema/types/errors/fixtures/harness + recipe graph contracts | fixture/codegen split | round-trip/fuzz/graph validation | yes | explicit | reopened |
| W1 | BACKEND/TASK/LOCAL | W0 | Electron/preload/supervisor/events | supervisor/preload | security/crash/E2E | yes | explicit | yes |
| W2 | STORAGE/PREPARATION | W0 | SQLite/CAS/import/source/mapping/prepared | storage/excel/text/preparation | ~30 golden/atomic/security | yes | explicit | yes |
| W3 | PLOTCALC/FITTING-BOUNDARY | W2 | fixed calculations/precomputed validators | nine kinds after envelope | algorithm/field golden | yes | explicit | yes |
| W4 | RENDER/DOMAIN | W2,W3 | 43 official+9 hidden registry、edit/style profiles、resolver/PNG/SVG、generalized layout、recipe compiler | generalized/edit-style gates before compiler | 43 full generalized mpl + capability/parity + compiler/plan golden | yes | explicit | reopened |
| W5 | PRD/DOMAIN/TASK | W4 | batch/review/Figure | Core/UI | isomorphic/E2E | yes | explicit | yes |
| W6 | ORIGIN/RENDER/PERF | W4; spike early | 43 O1 adapters/worker/reopen + symbol/palette/edit readback + recipe parity | chart families after K01 | one-version43 representative + per-signature generalized Origin + style/readback + offline edge | yes | explicit | reopened |
| W7 | AGENT/DOMAIN | W1,W2 | context/provider/decision/validator | context/probe | privacy/provider matrix | yes | explicit | yes |
| W8 | CLOUD/AGENT/LOCAL | W7 | invite/credential/counter/proxy | redeem vs invoke | idempotency/degrade | yes | explicit | yes |
| W9 | LOCAL/STORAGE/TASK | W1,W2 | zero-egress/log/local diag/known compatibility | policy vs lifecycle | packet/fault/privacy | yes | explicit | yes |
| W10 | PERFORMANCE/all | W5,W6,W8,W9 | Beta evidence/generalization/installer/checklist | harness starts W0 | generalized gates + complete Beta checklist | yes | explicit | reopened |

审计结论：W0、W4、W6、W10 的新增范围契约已明确但实现/evidence 重新打开；其余 W 保持既有 ready 状态。`reopened` 不是 blocked，而是表示原完成切片不能覆盖新确认的退出证据；在对应 evidence 通过前不得恢复为 `yes`。

## 6. 冲突冻结审计

| Audit axis | Canonical result | Negative search/evidence expectation | Result |
| --- | --- | --- | --- |
| 启动入口 vs 服务模式 | 三工作入口；服务模式只在Agent/设置 | 无“邀请码/custom/local_only是三个启动入口” | pass-design |
| AgentDecision | 四类唯一union | 旧五类type names零残留 | pass-design |
| 模型工具 | no tool/no loop；structured transport only | 无模型调用领域工具口径 | pass-design |
| 图形范围 | 正式43纯数值；内部52分层为43 official+9 hidden；无K23/S45 | 九图不出现在create/export capability，无地图/图像承诺 | pass-design |
| OPJU | 正式43全O1；历史31矩阵与新增12证据分开 | 无首轮O2准入口径、无隐藏九图OPJU承诺 | pass-design |
| Formal data | PNG/SVG/OPJU full data | 无formal静默downsample/raster | pass-design |
| Local/cloud | 云最小且本地启动/项目不依赖 | 无cloud project/session truth/sync | pass-design |
| Batch | 完全同构/单mapping/同Spec | 无逐文件mapping/method/unit例外 | pass-design |
| 图像 | v1不导入/处理/混合科研图像 | 无K23/S45/图片panel首轮入口 | pass-design |
| Cell editing | 原始只读，无row-index cell edit | 无spreadsheet任意改单元格 | pass-design |
| Formal formats | 仅PNG/SVG/OPJU | 无PDF/EPS/EMF正式入口 | pass-design |
| Identity/quota | 无账号、InviteGrant不限设备共享额度 | 无per-install新额度/硬件指纹 | pass-design |
| local_only | strict零出站；无update_only | 无strict local_only例外联网 | pass-design |
| 387 logical matrix | 43×3×3 formal PNG/SVG/O1 OPJU；preview另测；昂贵 Origin 仅 representative 实跑 | 无把 387 全解释为 Origin COM 实跑；历史279只作基础证据 | pass-design |
| Origin versions | 每build唯一exact version | 无“2021+”或多版本当前门禁 | pass-design |
| Beta规模 | 100k×20、单图100k、20×10k、项目100、≤2GB | 无1M/10M/1000对象/6GB当前门禁 | pass-design |
| Cloud复杂度 | 长期凭据+原子共享计数+client_run幂等 | 无refresh/reserve/settle/config/update | pass-design |
| Diagnostics | 无analytics；Bundle只本地保存 | 无桌面analytics/诊断上传 | pass-design |
| Schema/backup | 默认拒绝+known pair迁移；无自动backup | 无通用N→N+1/每日三份/恢复UI | pass-design |
| Distribution | 人工安装包三重校验 | 无应用内/后台/自动更新 | pass-design |
| 数据处理边界 | Import→FieldMapping/Preparation→PlotCalculation/PlotSpec | 无通用Transform/derived workflow/data Agent | pass-design |
| 科学计算边界 | 九类固定计算；九图预计算输入；Analysis/Fit后移 | 无v1统计/拟合/平滑/基线/归一化承诺 | pass-design |
| Agent编排 | 单对话编排Agent、单Decision、同错二次即停 | 无多Agent/工具循环/模型处理步骤 | pass-design |
| OPJU计算边界 | direct Raw→Graph；fixed Raw+Plot Data→Graph | 无Analysis Template/formula/LabTalk/Raw自动重算承诺 | pass-design |
| 导入诊断 | ~30 goldens+43图fixtures+分层快照/错误族 | 无运行时oracle或下游掩盖上游偏差 | pass-design |
| 结构与数据边界 | ChartRecipe仅结构/端口/关系/策略；PlotSpec绑定数据、mapping、计算结果 | 无真实数据、FieldId、路径、自动range、可执行内容进入recipe | pass-design |
| 单图组合 vs Figure | 同一绘图区的结构组合属于PlotSpec；多面板布局属于FigureSpec | 无用Figure绕过单图recipe或把多面板塞入单Plot | pass-design |
| 官方与自定义身份 | 相同Schema/compiler/resolver/renderer；官方只增加准入证据 | 无官方chart ID专属隐藏结构算法 | pass-design |
| 外观证据 vs 泛化证据 | 同源Origin/期刊证据判默认外观；冻结变体判结构泛化 | 无合成数据冒充参考外观、无当前实现生成oracle | pass-design |
| 配方复用 | 普通输入校验和产物验证，不逐次重跑qualification | 无每次用户复用触发完整Origin/泛化准入 | pass-design |
| 编辑能力 | 43图版本化profile是UI/Agent/validator共同真值；未声明操作不支持 | 无任意Origin property/path、无adapter私有fallback | pass-design |
| 符号与色板 | 12符号、闭合符号3 interior、`plus/cross`非适用拒绝、16冻结sRGB palette；>15联合编码不循环 | 无Origin编号作为项目真值、无读取本机可变palette、无RGB漂移 | pass-design |
| 双Y默认 | X23/X24/X35/X36左右轴中性、正常字重、非加粗；显式请求才着色 | 无默认随系列着色/加粗或样式修改改变轴语义 | pass-design |
| 实施顺序 | 基础泛化稳定后才实现组合compiler | 无测试oracle与组合架构同时迁移 | pass-design |

本表的 `pass-design` 将由提交前全库脚本/`rg`、Decision ID、Markdown link、UTF-8 和 `git diff --check` 复核；它不等同于未来实现测试pass。

## 7. Freeze change process

1. 提议者指出受影响Requirement IDs、Decision IDs、专门契约和Workstreams。
2. 产品行为/跨模块语义变化新增或更新Decision ID；不能只改实现计划。
3. 同步PRD、权威专门契约、DOMAIN/BACKEND及本Matrix。
4. 更新fixture/golden/migration/compatibility/release evidence影响。
5. 重新运行冲突、ID、link、UTF-8与diff审计后建立新baseline。

不改变冻结行为的adapter内部实现细节可在对应backlog细化，但仍需版本化并满足evidence。任何“实现更容易”为理由的静默行为变化都不被接受。
