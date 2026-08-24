# PlotAgent 发布候选问题台账

> 冻结基线：`781e793694b9e27b8e29809e2e320eb67759af56`
> 冻结日期：2026-08-24
> 发现证据：`build/unified-ui-discovery-781e793-20260824/TEST-LEDGER.md`
>
> 本文件是集中施工的唯一问题入口。状态只允许“待修复”“待合入”“外部观察”“用户明确暂缓”“已关闭”；历史候选问题从 Git 与《PlotAgent 产品测试覆盖审计》追溯，不在这里重复堆叠。

## 1. 本轮必须集中修复

| ID | 问题族 | 证据与根因 | 集中修复范围 | 关闭标准 |
| --- | --- | --- | --- | --- |
| `AGENT-DATA-01` | 非同构宽表与长表无法在用户确认语义后合并 | 正式 Electron 项目 143：Agent 正确识别结构差异并追问，用户确认 `Sensor_A/B/C` 与 `Value_mV` 为同一物理量且均为 mV；首计划及一次自动修订仍以 `WORKFLOW_NON_ISOMORPHIC` 失败，项目无副作用。耐久记录显示：`reshape_wide_to_long` 生成的 value 单位为空、group 为 `categorical`；长表 `rename_field` 后 value 仍为 `mV`、group 仍为 `text`，而 `concatenate_sources` 正确要求名称、逻辑类型和单位完全一致。当前白名单没有把“用户确认缺失单位”转成可验证单位声明的操作。 | 新增只允许“原单位缺失且存在明确用户证据”的强类型单位声明操作；已知单位换算继续使用 `convert_unit`。让 Agent/修订提示能选择 `convert_type text→categorical`、单位声明、reshape、rename、concat 的正确顺序；合同、Schema/codegen、Core 编译/预演/执行、确认卡、持久化和错误语义同步修改。不得放宽 concat 为模糊兼容，也不得静默继承另一来源单位。 | 确定性正反例证明：有用户证据时宽/长表形成同构 PreparedDataView 并绘制 K03；缺证据时精确追问；已知冲突单位稳定拒绝；预演与正式执行同 schema/hash。正式 Electron 从零完成项目 143 等价任务，零原样重试、零副作用失败。 |
| `UI-DATA-01` | 数据处理确认卡没有完整展示整理后的数据 | 项目 152 的 ISO 日期输入在修订后正确产生 `date_ordinal` 并绘制 X38，但确认卡主要展示原始 date 文本；派生字段只在绑定文字中可见，用户不能直接核对整理后的输出 schema、单位和样本。项目 143 的 reshape/rename/concat 同样缺少一张统一的处理后预览，难以及时发现类型/单位仍未对齐。 | TaskPlan/Core 投影增加确定性数据操作预演摘要：输入/输出行列、输出字段名、逻辑类型、单位、前三行真实样本及来源；前端确认卡只消费结构化预演，不在浏览器复算。多来源逐来源证据与合并后 PreparedDataView 预览同时保留。 | 日期转序数、宽转长、单位声明、concat、align 各有确定性投影测试；正式 Electron 确认前可直接读到处理后字段、单位与样本，确认前项目 revision 不变。 |
| `UX-PROGRESS-01` | 长规划阶段反馈不够具体 | 同源两表合并计划约 90 秒；项目 152 首次计划约 3.5 分钟。长等待主要发生在真实模型调用，当前界面长时间只保留一条泛化阶段文字，且执行返修时可能沿用“检查数据并规划”措辞。用户没有要求时长预算，因此这不是延迟阈值 FAIL，但属于已确认的反馈缺口。 | 展示 durable 的真实阶段、当前工具/修订阶段和已用时；阶段变化只来自运行时事件，不伪造百分比。停止按钮继续直接中止 provider；合入已验收 motion 后只为阶段切换提供克制过渡。 | 通过假时钟和事件序列确定性测试验证阶段、已用时、停止、返修和恢复；正式 Electron 长调用中阶段与任务中心一致，不出现假进度或旧阶段回退。 |
| `UX-SOURCE-COUNT-01` | 来源数量文案容易被误读 | 多来源任务显示“本次任务数据 2/32、9/32”。`32` 实际是选择上限，不是本次任务总数，容易被理解成“第 2/32 个数据”。功能没有丢来源。 | 改为“已选 2 个来源”等直接文案；上限只在接近/达到限制或帮助信息中出现。保留 32 来源确定性边界，不改能力。 | 1、2、9、32、33 来源组件测试与正式 Electron 定向读回一致；33 来源仍稳定阻止继续。 |
| `AGENT-EDIT-01` | 已有 prepared 图无法进入 Pi 编辑规划 | `ef40c96` 正式 Electron 项目 154：多来源 prepared K03 已成功创建到项目 v3 / 图 v1；随后两次 `@图1` 标题编辑均在 26–59 ms 内失败，`model_calls=0`、无计划、无副作用。隔离复现显示 `AgentContextSnapshot` 报“selected plot context references an unauthorized field alias”：编译器已接受并执行 `declare_unit.output_field_alias=value_mv_a`，但已有图授权校验维护了另一份不完整输出名单。 | 将全部 15 类数据操作的输入/输出字段血缘收敛为单一函数，由编译器与已有图上下文共同消费；审计原始、单源 prepared、多源 prepared 三种已有图上下文以及标题、轴、系列、图例、图类参数、数据更新公共入口。不得给 K03、标题或 `value_mv_a` 加特例。 | 聚焦确定性门禁全绿；项目 154 等价正式 Electron 编辑能产生计划、确认并形成单调新图版本；独立长运行任务执行 Stop 后任务中心归零，项目/目标图版本和内容不变。 |
| `ORIGIN-FRAME-01` | Origin 默认输出缺少四侧完整轴框 | `eb99ab2` 当前 fresh PNG 仅稳定显示左、下主轴线；产品负责人确认 Origin 产物默认必须在每个原生图层显示上、下、左、右四侧轴框。本项是共享默认视觉规则，不是 Agent 编辑参数，也不要求 Matplotlib 同形。 | 在 Origin 共享原生后处理层对所有 graph layer 应用四侧轴线可见；随后重放显式轴线可见性动作，使用户覆盖仍为权威。Fresh reopen 必须逐层、逐侧机械读回默认态和显式覆盖；不得逐图打模板补丁。 | 聚焦单测覆盖多图层四侧应用、显式覆盖和读回失败；真实 K03 pilot 显示四侧轴框；新候选 34 图 Origin fresh-reopen、视觉签名与公共编辑矩阵全绿。 |

## 2. 已验收并合入

| ID | 内容 | 状态 | 处理 |
| --- | --- | --- | --- |
| `MOTION-01` | 克制的时间线进入、阶段文字切换、导出提示、任务抽屉、模型设置和导出菜单动效；含 `prefers-reduced-motion` 降级 | `cfb8b5c` 已由用户在 `codex/motion-design` 分支验收，并由 `95a1bb5` 合入当前施工分支 | 已完成；后续只随前端门禁与正式 Electron 定向测试复核，不再另开动效施工。 |

## 3. 外部观察，不冒充产品 FAIL

| ID | 观察 | 判定 | 后续门槛 |
| --- | --- | --- | --- |
| `PROVIDER-OBS-01` | 项目 153 在任务创建后约 0.6 秒收到 provider HTTP `402`：`Insufficient Balance`；耐久错误为 `PI_V2_PROVIDER_FAILED`、`retryable=true`、`known_none`，计划未生成、项目未修改。相同配置数分钟前曾完成项目 152。 | 上游服务真实返回 402，当前没有证据证明是 PlotAgent 错误映射；不能用用户账户页面的余额推翻实际响应，也不能据此修改数据/任务合同。 | 冻结黑盒前做 provider 冒烟；若仍失败记环境 `BLOCKED`，切换到用户配置的可用 provider 后从新候选重测。远程模型不可用时，本地导入、手动绘图/编辑和导出必须继续可用。 |

## 4. 用户明确暂缓

| ID | 问题 | 当前处理 | 发布说明 |
| --- | --- | --- | --- |
| `EXPORT-NAME-01` | OPJU 保存对话框默认文件名包含 plot ID 的冒号，例如 `plot:workflow...opju`，Windows 判定文件名无效。 | 用户明确要求本轮不修；正式 UI 操作时手动改为合法文件名。项目 144 使用 `project144-plot1-v11-final.opju` 成功导出 24,186 B，SHA-256 `468CB8D22A348607F09D9CC4BAE8E280FFF9479BEE0F88678CB8B04895832BD0`。 | 这是已知 UX 限制，不得在最终报告中写成“默认命名正常”；黑盒按手动合法命名执行，不因该暂缓项修改 renderer 或导出内容合同。 |

## 5. 本轮发现阶段已关闭，不进入重复施工

| 能力 | 结论 | 证据 |
| --- | --- | --- |
| 同构多来源单图 | PASS；`concatenate_sources`、Source 分组、确认卡逐来源样本、Composer K02 均正确 | 统一台账 `UI-DISC-MULTI-ONE-PLOT` |
| ISO 日期文本整理 | PASS；一次自动返修后生成 `date_ordinal`、X38 成功渲染、项目 v2 | `UI-DISC-DATE-ORDINAL`；只保留 `UI-DATA-01` 的确认可读性缺口 |
| 失败安全终态 | PASS；追问、一次修订、最终 failed、项目无修改、无盲循环 | `UI-DISC-WORKFLOW-REPAIR`；任务能力 FAIL 由 `AGENT-DATA-01` 统一修复 |
| 复合编辑撤销/重做 | PASS；项目 144、`@图4` v1→v5→v9→v10→v11，v10/v11 精确恢复四项状态 | `UI-DISC-COMPOUND-HISTORY` |
| 重启恢复与 OPJU 内容 | PASS；项目 v29 恢复 `@图4` v11；合法文件名 OPJU 导出成功 | `build/final-ui-evidence-781e793-20260824/FORMAL-UI-AFFECTED-PATHS.md` |
| 34 图、Origin 原生重开、公共编辑、数据/故障/打包矩阵 | 当前 `781e793` 证据全绿；本轮未发现 renderer/profile 问题 | `build/final-matrix-781e793-20260824/RELEASE-MATRIX-SUMMARY.md` |

## 6. 冻结后的施工与失效范围

1. `AGENT-DATA-01` 与 `UI-DATA-01` 必须作为同一数据能力纵切施工，不能只改 prompt、只放宽 concat 或只补一张前端说明。
2. `UX-PROGRESS-01`、`UX-SOURCE-COUNT-01` 与 `MOTION-01` 只改运行时事件投影和前端表现，不改变 renderer/profile。
3. 集中修复后必须重跑 Agent/任务状态、数据操作、Schema/codegen、Core、前端、持久化、故障和构建门禁，并进行受影响正式 Electron 定向测试。
4. 若未改 PlotSpec、34 个 profile、Matplotlib/Origin renderer 或 recipe，既有 34 图默认视觉审查不因上述施工失效；新候选仍按发布路线重跑 34 图机械矩阵和 Origin fresh-reopen。
5. 完整黑盒与唯一一次 SEQ-70 只能在新候选冻结后运行；任何后续产品代码修改都使受影响证据失效。

## 7. 集中施工记录（关闭前证据）

以下内容已由 `56397de` 实现并通过全量确定性门禁。第一节问题仍保持打开，直到正式 Electron 定向测试取得当前提交的用户可见证据，不提前写成发布通过：

| 问题族 | 已实现的纵切 | 当前确定性证据 | 尚需关闭证据 |
| --- | --- | --- | --- |
| `AGENT-DATA-01` | 新增有语义决定证据约束的 `declare_unit`；单位只附着到缺失单位的数值派生字段，值不变；宽转长保留真实逻辑类型和单位；派生字段可继续 rename/type/select；TaskIntent 编译后在展示确认卡前执行同源 PreparedDataView 预演，非同构结果直接退回 Agent，不留到确认后失败。 | 正反例覆盖无证据、非数值、已有单位、未知单位；宽表与长表经 declare/reshape/rename/type/select/concat 后形成 6 行×4 列同构数据，预演与正式注册 hash 相同，原始数据单位保持不变；全量 Python `872 passed`。 | 正式 Electron 从零完成项目 143 等价任务，并核对零原样重试、零副作用失败。 |
| `UI-DATA-01` | 新增 `PreparedDataPreview` 合同与 Schema；Core 使用正式执行同一数据程序投影输入/输出行列、输出字段名/类型/单位、前三行、来源和内容 hash；前端从 `draft_ready → task_plan` 和 durable plan 两种包装读取，不复算数据。 | Core API 集成测试证明确认前项目 revision 不变；解析和组件测试覆盖结构、单位、样本、角色徽标以及逐项结构化预演错误；contracts/codegen 与 Vitest `30 files / 289 tests` 全绿。 | 正式 Electron 确认卡人工读回。 |
| `UX-PROGRESS-01` | 运行事件增加稳定 `startedAt` 与逐事件 `occurredAt`；活动行展示真实阶段和已用时；继续、自动修订与失败证据修订使用不同文案，不伪造百分比。 | 假时钟证明一次运行的开始时间稳定、事件时间单调；自动修订不退回普通规划文案；全量任务状态、Vitest、typecheck、ESLint 与 production build 全绿。 | 正式 Electron 长调用、停止和任务中心一致性。 |
| `UX-SOURCE-COUNT-01` | 文案改为“已选 N 个来源”；仅在 28–32 个来源时补充“最多 32 个”；第 33 个来源不能加入当前 32 项选择。 | 2、9、32/33 来源组件边界、Main 拒绝、全量前端与构建门禁全绿。 | 正式 Electron 定向读回。 |
| `AGENT-EDIT-01` | 新增 `data_operation_field_aliases` 作为 15 类数据操作字段血缘的唯一真源；编译器与 `AgentContextSnapshot` 授权校验共同使用，补齐 `declare_unit` 并消除两套名单漂移。 | 隔离复制项目 154 后，原 11 步宽/长表程序成功恢复，`Time_s`、`value_mv_a`、`sensor_cat` 三个绑定均获授权；Python 聚焦 12/12 PASS，Main/Pi 62/62 PASS。 | 正式 Electron 仅复测已有图编辑计划/执行与 Stop 版本不变；两项通过后冻结候选。 |
| `ORIGIN-FRAME-01` | Origin 共享 visual pass 无论是否存在用户视觉动作，都会打开原生 OPJU、将每个 layer 的 bottom/left/top/right 轴线设为可见，再应用显式轴线可见性覆盖；fresh reopen 逐侧读回。 | 聚焦 `49 passed`，ruff/mypy 通过；真实 K03 pilot 已生成、保存、fresh reopen，四侧轴框可见且矩阵无 FAIL。 | 新提交上的 34 图 Origin、视觉签名与公共编辑矩阵。 |
