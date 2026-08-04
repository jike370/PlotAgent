# PlotAgent v1 规格索引与 Implementation-Ready 设计冻结基线

> 状态：v1 implementation-ready design baseline（产品/跨模块契约冻结；功能尚未实现或 qualification）
> 基线日期：2026-08-05
> 适用范围：权威文档、冲突优先级、requirement/evidence matrix、workstream 入口与冻结变更流程
> 相关文档：[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)、[实施拆分与里程碑计划](./IMPLEMENTATION-PLAN.md)、[性能测试与发布门禁契约](./PERFORMANCE-TEST-RELEASE.md)

## 1. 冻结含义与非含义

“Implementation-ready design baseline”表示：

- 第一轮产品行为、对象边界、进程/云/本地信任边界和跨模块 Schema 语义已足够直接拆分实施。
- 每项核心需求都有权威契约、workstream、计划入口、稳定错误 owner 和未来验收 evidence。
- 冲突审计已按本文件矩阵完成，当前已知旧口径已清除。
- 后续产品或跨模块行为变化必须新增/更新 Decision ID 并同步权威文档，不得由实现自行选择。

它不表示：

- 真实 Python Core、Agent、ModelProvider、云服务、OriginAdapter、迁移、更新或安全功能已经实现。
- 31 图/analysis/origin 每个 adapter 的完整参数表已经在本文伪造完成。
- 279基础矩阵、Origin per-version 93 paths、性能、安全或 installer release gates 已经运行通过。
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
| [DOMAIN-CONTRACTS](./DOMAIN-CONTRACTS.md) | 公共对象、AgentDecision/ActionPlan、Schema | W0 | `src/plotagent/contracts/`, `schemas/` | schema/codegen/round-trip |
| [PROJECT-STORAGE](./PROJECT-STORAGE.md) | workspace、CAS、`.plotproj`、import | W2/W9 | storage/import packages | atomicity/archive/reopen |
| [DATA-TRANSFORMS](./DATA-TRANSFORMS.md) | Transform/Unit/Lineage | W2 | transforms/units/lineage | golden/property tests |
| [ANALYSIS-ENGINE](./ANALYSIS-ENGINE.md) | Analysis registry/spec/result/science boundaries | W3 | analysis registry | scientific references |
| [FITTING-SYSTEM](./FITTING-SYSTEM.md) | Fit models/input/weights/solver/intervals | W3 | fitting package | formula/solver golden |
| [RENDERING-PIPELINE](./RENDERING-PIPELINE.md) | Resolver、axes/ticks、physical/text/parity | W4/W6 | rendering/resolver | plan golden/parity |
| [ORIGIN-EXPORT](./ORIGIN-EXPORT.md) | OPJU content、O1、adapter、reopen | W6 | origin worker/adapters | per-version 93 matrix |
| [TASK-RUNTIME](./TASK-RUNTIME.md) | Interaction/Execution、scheduler/cancel/recovery | W1/W2/Core | task scheduler/events | fault/idempotency E2E |
| [AGENT-CONTEXT](./AGENT-CONTEXT-AND-PROVIDERS.md) | Context/Provider/Disclosure/AgentDecision/audit | W7 | agent/provider packages | provider/security matrix |
| [CLOUD-CONTROL-PLANE](./CLOUD-CONTROL-PLANE.md) | Invite/token/quota/proxy/config/update | W8 | control plane/update client | ledger/tamper/degrade |
| [LOCAL-SECURITY](./LOCAL-SECURITY-MIGRATION-DIAGNOSTICS.md) | local_only、安全、日志诊断、迁移备份 | W9 | security/lifecycle packages | zero-egress/fault/privacy |
| [PERFORMANCE-TEST-RELEASE](./PERFORMANCE-TEST-RELEASE.md) | 平台、预算、matrix、blockers、RC evidence | W10 | release/evidence harness | RC qualification packet |
| [IMPLEMENTATION-PLAN](./IMPLEMENTATION-PLAN.md) | W0–W10、依赖、spikes、milestones | All owners | proposed entries per W | milestone exit evidence |
| [chart-library-research](./chart-library-research.md) | 157长期taxonomy与研究建议 | W4 research | registry backlog input | 仅研究，不等于准入 |
| [README](../README.md) | 仓库导航、当前prototype运行 | Repository maintainers | existing app skeleton | commands/current status |

## 3. Requirement / Evidence Matrix

`Status=frozen-design` 只表示契约完整一致；所有 `Future evidence` 仍须实现阶段产生。

| Req | Frozen requirement | Authority | W | Planned entry | Future evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R-START | 工作入口仅示例/导入/打开项目；模型模式不替代 | PD-B04/B05,Z01；PRD 5.1；LOCAL §1 | W1/W9 | renderer startup/model settings | first-run UI/E2E no-network | frozen-design |
| R-NETMODE | builtin/custom/local_only；localhost=custom；切换不改项目 | PD-Z02；LOCAL §1–2 | W9 | network-policy | mode/state/project hash tests | frozen-design |
| R-ZERO | 严格 local_only 零出站；OneTimeUpdateGrant transient update_only仅manifest/package | PD-Y15,Z03；LOCAL §2；CLOUD §10 | W8/W9 | update/network policy | packet capture + denied endpoints | frozen-design |
| R-AGENT-UNION | 唯一四类 ActionPlan/NeedsInput/Unsupported/NoChange | PD-P13,X13；DOMAIN §7 | W0/W7 | AgentDecision schema | union invalid corpus/codegen | frozen-design |
| R-NO-TOOLS | 模型无本地/领域工具、URL/path、tool loop；structured transport非授权 | PD-J01,O02/O12,P17,X01；AGENT §1 | W7 | provider/validator | tool-like output rejection | frozen-design |
| R-CONTEXT | 本地Context/Conversation权威、版本refs、限样本出境与Disclosure | PD-X03–X09；AGENT §3–6 | W7 | context/reducer/disclosure | size/hash/stale/consent tests | frozen-design |
| R-PROVIDER | builtin proxy；custom Responses→Chat；P1/P2 one repair/P0 | PD-X10–X12；AGENT §7–10 | W7 | providers | synthetic probes/repair trace | frozen-design |
| R-INVITE | 无账号；同InviteGrant不限设备共享额度；无硬件指纹 | PD-L03–L06,Y01–Y06；CLOUD §3–4 | W8 | invite/token | multi-device/reinstall/revoke | frozen-design |
| R-QUOTA | client_run幂等reserve/settle；custom不扣；云故障本地不受影响 | PD-Y07–Y14；CLOUD §6–8 | W8 | ledger/proxy | timeout/restart/no-double-charge | frozen-design |
| R-STORAGE | 本机fixed-disk workspace；SQLite single writer；immutable CAS；`.plotproj` snapshot | PD-Q01–Q13,Z06；STORAGE §1–4,8 | W2/W9 | storage/project packages | crash/reopen/hash/network reject | frozen-design |
| R-IMPORT | atomic import、ImportRecipe、一次mapping；archive/Excel不可信且不执行 | PD-Q14–Q20,Z07/Z08；STORAGE §5–9 | W2/W9 | import pipeline | parser/archive/macro/formula matrix | frozen-design |
| R-NO-CELL | 原始只读，无row-index任意改单元格 | PD-C08,M02,U05；PRD 7.1 | W2/W5 | Dataset UI/services | forbidden action/schema tests | frozen-design |
| R-TRANSFORM | whitelist Transform、UnitSpec、三层lineage、无SQL/Python/UDF | PD-U01–U20；TRANSFORMS | W2 | transform/unit/lineage | golden/property/preflight | frozen-design |
| R-ANALYSIS | 用户选方法；白名单AnalysisSpec/Result；无隐藏重算/结论 | PD-H01,S01–S20；ANALYSIS | W3 | analysis registry | scientific refs/failures | frozen-design |
| R-FIT | 固定Fit白名单、input/weight/solver/interval/curve结果 | PD-T01–T20；FITTING | W3 | fitting | formula/multistart/golden | frozen-design |
| R-CHARTS | v1精确31项纯数值：K01–K22,K24–K25+S01,S05,S21,S25,S31,S34,S61 | PD-E08/E09；PRD 6.2/10.1 | W4 | chart registry | 31 ID registry + matrix | frozen-design |
| R-NO-IMAGE | v1无科研图像、地图、ROI或图表+图片混合 | PD-E09/E11,M03；PRD 5.5/17 | W4/W5 | registry/Figure schema | forbidden formats/actions | frozen-design |
| R-BATCH | 完全同构、一次mapping/同Spec；partial成功，无逐文件例外 | PD-C,D,G,U20；PRD 5.2/6.4 | W2/W5 | BatchService/review | signature/partial/review E2E | frozen-design |
| R-FIGURE | 仅数值固定布局、版本refs、公共图例、源更新不自动替换 | PD-F01–F06；DOMAIN §5 | W5 | FigureService/UI | version/layout/legend tests | frozen-design |
| R-EXPORT3 | 正式导出仅PNG/SVG/OPJU；clipboard非正式 | PD-K01/K02；PRD 10.4 | W4/W6 | ExportService | format allowlist/records | frozen-design |
| R-FORMAL | Formal三格式full data；preview简化明示且range/stats full | PD-H11,V04/V05,AA05；RENDER §2；PERF §4 | W4/W6 | resolver/adapters | count/assertion/large SVG | frozen-design |
| R-RENDER | 单一ResolvedRenderPlan、deterministic axes/ticks/layout/text | PD-V01–V20；RENDER | W4/W6 | resolver | plan golden/parity tolerance | frozen-design |
| R-OPJU | 31图v1 OPJU全部O1；无LabTalk/raster fallback；两阶段原子 | PD-K04,W01–W20；ORIGIN | W6 | origin adapters/worker | per exact version 93 paths | frozen-design |
| R-ORIGIN-V | 2021技术下限；只支持明确qualification range，未测更高版unsupported | PD-K03/K12,W12,AA03；PERF §2 | W6/W10 | release manifest/preflight | Origin 2021 与每个 release manifest 明确声明的 exact version matrices | frozen-design |
| R-TASK | Interaction≠Execution；状态/提交/取消/幂等/crash recovery | PD-R01–R20；TASK | W1/W2 | scheduler/events | state/fault/commit E2E | frozen-design |
| R-LOCAL-PRIV | 无项目加密承诺；ACL/BitLocker；temp ACL；无secure erase宣称 | PD-L07/L08,Z04/Z05；LOCAL §3–4 | W9 | temp/security UI | ACL/wording/cleanup tests | frozen-design |
| R-LOG-DIAG | log allowlist14d/100MB；analytics opt-in；用户主动触发、逐项预览 DiagnosticBundle/30d | PD-J10,Z10–Z12；LOCAL §8–10 | W9 | logger/diagnostics | forbidden scan/retention | frozen-design |
| R-MIGRATE | backup→temp N+1→validate→atomic switch；不改science/visual | PD-Z13–Z18；LOCAL §11–13 | W9 | migration/backup | crash injection/semantic hash | frozen-design |
| R-CLOUD-MIN | 云仅invite/proxy/quota/config/update/active diag；无sync/remote science | PD-L06,Y11–Y14；CLOUD §2/8 | W8 | control plane | API/log/degrade tests | frozen-design |
| R-UPDATE | 无invite资格限制；签名/hash/codesign；用户重启；任务期间不装 | PD-Y15–Y19；CLOUD §9–10 | W8/W9 | update client/service | tamper/defer/update_only | frozen-design |
| R-PERF | Windows/machines/scales/budgets/memory/disk reproducible P95 | PD-AA01–AA11/AA15；PERF §1–6/9 | W10 | performance harness | baseline/regression reports | frozen-design |
| R-MATRIX | 31×3×(PNG/SVG/OPJU)=279；preview另测；每Origin版重跑93 | PD-AA12/AA13；PERF §7 | W0/W4/W6/W10 | MatrixKey/evidence | zero-gap coverage reports | frozen-design |
| R-RELEASE | 不可豁免blockers、RC evidence、first-beta go/no-go | PD-AA16–AA20；PERF §10–14 | W10/all | release/evidence | signed RC packet/user study | frozen-design |
| R-UI | 浅色克制、无卡片堆叠/玻璃/深色科幻/渐变文字，键盘/a11y/reduced motion | DESIGN；PD-D/F/L | W1/W5 | renderer design system | visual/a11y/display matrix | frozen-design |

## 4. Stable Error Ownership Index

| Owner | Prefix/family | Escalation boundary |
| --- | --- | --- |
| W0 Contracts | SCHEMA/PROTOCOL/registry | Schema shape与code唯一性 |
| W1 Desktop | CORE/IPC/SINGLE_INSTANCE/CREDENTIAL_ACCESS | 进程/桌面边界 |
| W2 Data | PROJECT_STORAGE/IMPORT/ARCHIVE/DATASET/TRANSFORM/UNIT/LINEAGE | 数据与存储 |
| W3 Scientific | ANALYSIS/FIT/SCIENTIFIC/CONVERGENCE | 科研计算 |
| W4 Render | PLOT/PATCH/CHART/AXIS/RENDER/PNG/SVG/FONT | Plot/Matplotlib |
| W5 Workflow | BATCH/ISOMORPHIC/REVIEW/FIGURE/SCOPE | 批次/组合 |
| W6 Origin | Origin fixed code registry | OPJU/preflight/validation |
| W7 Agent | PROVIDER/TLS/AUTH/SCHEMA_INVALID/EGRESS/TARGET | Provider/Agent boundary |
| W8 Cloud | INVITE/DEVICE/TOKEN/QUOTA/RATE/IDEMPOTENCY/UPDATE | control plane/update |
| W9 Local lifecycle | NETWORK/TEMP/LOG/DIAGNOSTIC/MIGRATION/LEGACY/BACKUP | local security/lifecycle |
| W10 Release | TEST_HARNESS/EVIDENCE/INSTALLER | gate orchestration only |

同名通用错误（例如 `RESOURCE_LIMIT`、`CANCELLED`）必须带结构化 `subsystem`/stage 或在registry中只有一个公共定义；不能让多个W创建语义不同的同名code。

## 5. Implementation-Readiness Checklist

| W | Contract | Dependency | Deliverables | Parallel boundary | Acceptance | Error owner | Done definition | Ready |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| W0 | DOMAIN + all schemas | none | schema/types/errors/fixtures/harness | fixture/codegen split | round-trip/fuzz | yes | explicit | yes |
| W1 | BACKEND/TASK/LOCAL | W0 | Electron/preload/supervisor/events | supervisor/preload | security/crash/E2E | yes | explicit | yes |
| W2 | STORAGE/TRANSFORMS | W0 | SQLite/CAS/import/data/unit/lineage | storage/parser/transform | atomic/golden/security | yes | explicit | yes |
| W3 | ANALYSIS/FITTING | W2 | registries/spec/results/ports | method families | scientific references | yes | explicit | yes |
| W4 | RENDER/DOMAIN | W2,W3 | 31 charts/resolver/PNG/SVG | resolver/adapters | 186 formal+preview | yes | explicit | yes |
| W5 | PRD/DOMAIN/TASK | W4 | batch/review/Figure | Core/UI | isomorphic/E2E | yes | explicit | yes |
| W6 | ORIGIN/RENDER/PERF | W4; spike early | O1 adapters/worker/reopen | chart families after K01 | per-version93 | yes | explicit | yes |
| W7 | AGENT/DOMAIN | W1,W2 | context/provider/decision/validator | context/probe | privacy/provider matrix | yes | explicit | yes |
| W8 | CLOUD/AGENT/LOCAL | W7 | invite/ledger/proxy/update | verifier vs ledger | idempotency/tamper | yes | explicit | yes |
| W9 | LOCAL/STORAGE/TASK | W1,W2 | zero-egress/log/diag/migrate/backup | policy vs lifecycle | packet/fault/privacy | yes | explicit | yes |
| W10 | PERFORMANCE/all | W5,W6,W8,W9 | RC evidence/installer/gates | harness starts W0 | complete RC packet | yes | explicit | yes |

审计结论：W0–W10 均具备 scope、out-of-scope、inputs/contracts、planned entry、deliverables、dependencies、parallel boundary、acceptance evidence、stable error ownership 和完成定义。若后续任一字段变为未知，对应W从Ready退回Blocked，不能保持“已冻结”标签掩盖缺口。

## 6. 冲突冻结审计

| Audit axis | Canonical result | Negative search/evidence expectation | Result |
| --- | --- | --- | --- |
| 启动入口 vs 服务模式 | 三工作入口；服务模式只在Agent/设置 | 无“邀请码/custom/local_only是三个启动入口” | pass-design |
| AgentDecision | 四类唯一union | 旧五类type names零残留 | pass-design |
| 模型工具 | no tool/no loop；structured transport only | 无模型调用领域工具口径 | pass-design |
| 图形范围 | 31纯数值，S61且无K23/S45 | v1无32/25+7旧计数和地图/图像承诺 | pass-design |
| OPJU | 首轮31全O1 | 无首轮O2准入口径 | pass-design |
| Formal data | PNG/SVG/OPJU full data | 无formal静默downsample/raster | pass-design |
| Local/cloud | 云最小且本地启动/项目不依赖 | 无cloud project/session truth/sync | pass-design |
| Batch | 完全同构/单mapping/同Spec | 无逐文件mapping/method/unit例外 | pass-design |
| 图像 | v1不导入/处理/混合科研图像 | 无K23/S45/图片panel首轮入口 | pass-design |
| Cell editing | 原始只读，无row-index cell edit | 无spreadsheet任意改单元格 | pass-design |
| Formal formats | 仅PNG/SVG/OPJU | 无PDF/EPS/EMF正式入口 | pass-design |
| Identity/quota | 无账号、InviteGrant不限设备共享额度 | 无per-install新额度/硬件指纹 | pass-design |
| local_only | strict零出站；update_only transient | 无strict local_only例外联网 | pass-design |
| 279 matrix | formal PNG/SVG/O1 OPJU；preview另测 | 无preview+PNG+SVG=279口径 | pass-design |
| Origin versions | 2021下限+明确qualification range | 无产品“2021+自动支持” | pass-design |

本表的 `pass-design` 将由提交前全库脚本/`rg`、Decision ID、Markdown link、UTF-8 和 `git diff --check` 复核；它不等同于未来实现测试pass。

## 7. Freeze change process

1. 提议者指出受影响Requirement IDs、Decision IDs、专门契约和Workstreams。
2. 产品行为/跨模块语义变化新增或更新Decision ID；不能只改实现计划。
3. 同步PRD、权威专门契约、DOMAIN/BACKEND及本Matrix。
4. 更新fixture/golden/migration/compatibility/release evidence影响。
5. 重新运行冲突、ID、link、UTF-8与diff审计后建立新baseline。

不改变冻结行为的adapter内部实现细节可在对应backlog细化，但仍需版本化并满足evidence。任何“实现更容易”为理由的静默行为变化都不被接受。
