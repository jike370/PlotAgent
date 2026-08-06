# PlotAgent 原生 Origin OPJU 导出契约

> 状态：第一轮 OPJU 导出基线已确认  
> 日期：2026-08-05  
> 适用范围：OPJU 内容边界、OriginExportPlan、能力准入、OriginAdapter、两阶段验证、原子提交、外部修改和稳定错误  
> 相关文档：[小规模 Beta 性能测试与发布门禁契约](./PERFORMANCE-TEST-RELEASE.md)、[渲染管线与跨 Renderer 一致性契约](./RENDERING-PIPELINE.md)、[领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)、[任务运行时、取消与崩溃恢复](./TASK-RUNTIME.md)、[后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)、[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)

## 1. 产品边界

OPJU 是 target-scoped、self-contained、editable delivery，不是 PlotAgent 项目包：

- `.plotproj` 保存 PlotAgent 对话、对象关系、任务和完整版本历史。
- `.opju` 只交付本次 ExportSpec 选择的图形及其实际需要的 Raw Data、Plot Data、固定计算/用户预计算结果和审计元数据。
- Origin 中的编辑不回写 PlotAgent，也不改变 PlotSpec、PlotCalculationResult 或项目历史。
- 第一轮不导入、解析或 round-trip 用户修改后的 OPJU。

OPJU 不能包含：

- 与导出目标无关的项目数据、图表或对话。
- API key、邀请设备令牌、模型配置或其他 secret。
- 用户工作区绝对路径、项目目录、源文件绝对路径或临时路径。
- 未被绘图使用的原始列、Plot Data 或缓存。
- 外部数据链接、外部模板依赖或运行时必须访问的 PlotAgent 对象。

## 2. Target scope

ExportSpec 明确 `target_scope` 与精确对象版本：

### 2.1 `current_chart`

- 一个 Origin graph page。
- 只包含该图需要的 Raw/Plot worksheet 或 matrix、metadata 和 manifest mapping。
- 不捎带同一对话或批次的其他图。

### 2.2 `selected_charts` / `batch`

- 一个 OPJU 中包含多个独立 graph page。
- 相同 SourceDataset、PreparedDataset/PlotCalculationResult/用户预计算表和完全相同列布局在 Data/Analysis 中去重共享。
- 每个 graph 保持到共享数据对象的原生链接。
- 任何选中目标失败都使整份 OPJU 失败。

### 2.3 `figure`

- 一个原生可编辑的 multi-layer graph page 表达 FigureSpec。
- panel、layer、common legend、label 与物理布局来自同一 ResolvedRenderPlan。
- 不以多个无关 graph 或整页图片冒充组合图。

## 3. Project Explorer 结构与命名

第一轮 OPJU 使用固定顶层 folders：

```text
Data/
Analysis/
Graphs/
Metadata/
```

- `Data/`：直接图所需 Raw Data，以及固定计算图保留的必要 Raw Data。
- `Analysis/`：最终 Plot Data，包括 PreparedDataset、PlotCalculationResult 或用户提供的预计算表；目录名不表示 Origin/PlotAgent 分析链。
- `Graphs/`：单图 graph pages 与 Figure multi-layer graph。
- `Metadata/`：manifest、导出摘要、版本映射和验证信息。

所有内部 Short Name 使用稳定 ASCII 标识，只含允许字符并在同一 OPJU 内确定性去重。用户可读名称写入 Origin Long Name：

- Long Name 保留数据集、字段、图表和面板的可读名称。
- 重命名显示文本不改变 manifest 中的 PlotAgent object/version 映射。
- 不把文件系统路径或未经清理的原始文件名用作内部名称。

## 4. 最小自包含数据

每个图只包含实际用于渲染的：

- X、Y、Z、group/category 与 facet 字段。
- error、interval、weight 或其他直接绑定 geometry 的列。
- ResolvedRenderPlan 引用的 PlotCalculationResult output columns。
- 用户提供的 curve、band、step、matrix、effect/interval 等预计算列。
- raw observations；仅当 raw points 在图中可见时包含。

不包含未使用列、未绘制的中间表、完整父数据或为了“可能以后使用”而复制的内容。自包含的含义是当前图可以在脱离 PlotAgent 后继续编辑和查看，不是复制整个科研项目。

### 4.1 直接图与固定计算图

- **直接图：** `Raw Data worksheet → native Graph`。Graph 直接链接实际绘制列，编辑数据可按 Origin 原生链接更新。
- **固定计算图：** `Raw Data + Plot Data (PlotCalculationResult) + native Graph + Manifest`。Graph 链接最终 Plot Data；编辑 Plot Data 可更新图，编辑 Raw Data 不承诺自动重新执行 PlotAgent 计算。
- **用户预计算图：** 预计算曲线/矩阵等进入 Plot Data，并标记 `user_provided_precomputed`；PlotAgent/Origin 均不重算科学结果。

v1 不生成 Origin Analysis Template、worksheet formula、Fit Function 或分析重算链，也不执行用户/Agent/数据提供的 LabTalk。极少数 `originpro` 未暴露的纯显示属性允许使用应用内置、测试锁定的 Set 选项；它们不承载公式、分析、路径或自由文本。以上边界必须写入 Manifest 和导出说明。

## 5. Origin 数据对象语义

Worksheet 必须保存并在重新打开后读回：

- Long Name。
- Units。
- Comments；只包含必要的字段/版本/语义说明，不含路径或 secret。
- Column designation，如 X、Y、Z、Y Error、Label 或 Group。
- 数值、类别、日期时间、missing/NaN 语义和行数。

需要矩阵语义的正式 matrix chart 可以使用 Matrixbook，并保存维度、坐标映射、Units、missing 语义和 graph data link。不能把矩阵渲染成 raster 后嵌入来取得 O1。

## 6. PlotAgent Manifest

Metadata 中的 manifest 至少保存：

- PlotAgent object/version 与 Origin folder/book/sheet/matrix/page/layer/plot 的双向 map。
- SourceDataset、PreparedDataset、PlotCalculationSpec/Result、用户预计算表、PlotSpec/FigureSpec、ResolvedRenderPlan 和 ExportSpec 的版本与 hash。
- 数据链类型 `direct | fixed_plot_calculation | user_provided_precomputed`，以及 Raw Data 修改是否可触发重算（v1 固定为 false）。
- chart type、resolved style、publication profile、renderer/resolver 版本。
- OriginAdapter ID/version、Origin template ID/hash、`originpro` version 与实际 Origin version。
- export time、target scope、capability level 和验证报告 hash。
- O2 已知差异；第一轮正式 43 图不应产生 O2，但 Schema 为后续保留该字段。

Manifest 不包含绝对路径。PlotAgent 的外部 ExportRecord 保存最终路径，但该路径不写入 OPJU 内部 manifest。

## 7. 能力等级与正式准入

- **O1 — full native semantic parity**：数据原生 linked，graph/layer/plot、axis、ticks、legend、annotation 和 page 原生可编辑，关键语义与 RenderPlan 一致。
- **O2 — native editable with declared differences**：数据仍 linked、对象原生可编辑，但存在预先声明且非关键的视觉差异。
- **O3 — visual embedded/unlinked**：通过嵌入或未链接对象保持外观；第一轮不能作为正式 OPJU。
- **O0 — unavailable**：没有受支持的 Origin 导出能力。

第一轮正式 43 图若显示 OPJU 导出能力，必须在当前 Beta build 唯一声明的 Origin exact version 上逐项达到 O1。高级未来图形可以在产品另行批准后以 O2 准入，但必须在执行前披露已知差异；运行时不能把 O1 静默降为 O2/O3。

Origin P1 的 21 项仍可保留在同一 typed adapter/OPJU 内部代码面（双 Y 轴网格图除外），但产品分为 12 个正式新增与九个 `internal_hidden`。X01/X02/X03/X05/X09/X13/X23/X35/X36/X38 使用锚定图—数据对记录同源视觉 evidence；X24/S07 使用冻结合成数据并必须标记 `synthetic_visual_validation`；X07/X11/X12/X15/X16/X17/X18/X19/X37 不显示、不接受 create/export，也不计正式 qualification。原 31 图实机矩阵与新增 12 图补充报告分开记账。

O3/O0 不生成正式 OPJU。将 Matplotlib PNG/SVG/raster 嵌入 Origin 不能算作 O1 或 O2。

## 8. OriginAdapter 契约

每个版本化 OriginAdapter 注册：

- `chart_type_id` 与支持的 PlotAgent chart package/version。
- 当前 Beta build 支持的单一 Origin exact version/build 和 bitness。
- template ID、签名与 content hash。
- 宣称的 capability level。
- Raw Data/Plot Data workbook 或 Matrixbook layout。
- typed property map：RenderPlan 字段到允许 Origin 属性的固定映射。
- live/reopen validation rules 与 parity tolerance。
- O2 known differences；O1 必须为空。

Adapter 只接收经过本地校验的 typed OriginExportPlan，不接收模型、数据或应用其他层生成的：

- Python、LabTalk、Origin C 或任何脚本正文。
- 任意 property name/path/string。
- 任意模板路径、文件路径或 COM 调用名。

OriginAdapter 以 `originpro`/Python 的版本化类型化固定映射创建和设置对象，不开放 LabTalk 执行入口。唯一允许的 Set 选项是代码内固定的 `-l 2`（森林图区间连接）、`-vg 70`（分组柱间距），以及由 `ColorValue` 的严格 `#RRGGBB` 类型生成的 `-cf color("#RRGGBB")`（原生 area fill）；AST 门禁拒绝其余常量或动态参数。模型、字段名、单元格、标签、路径、模板或 adapter 配置均不能进入这些选项。任何还需要公式、分析命令或未登记 LabTalk 的图形都判为 `CAPABILITY_MISSING`。

## 9. Template 安全

- Origin templates 随官方 chart package 签名和版本化。
- 执行前验证签名、hash、适配器版本与当前 build 的 Origin exact version。
- 每个任务只把所需 template 复制到隔离临时目录。
- 不读取、不修改、不覆盖用户 Origin 全局 templates 或主题。
- 任务结束清理临时副本；正式 OPJU 不依赖临时 template 才能打开。

## 10. Typed OriginExportPlan

OriginExportPlan 由 ExportSpec、ResolvedRenderPlan 和已注册 OriginAdapter 在本地确定性生成，至少包含：

- target scope、全部精确目标与 plan hash。
- Project Explorer folders、ASCII internal names 与 Long Names。
- workbook/worksheet/matrix layout、列 designation、Units、Comments 与 data object refs。
- graph/page/layer/plot 创建顺序与 typed property values。
- axis、exact ticks/labels、legend、annotation、font、style 与物理 page rectangles。
- adapter/template/version/capability 与验证计划。
- target resource ref、expected existing file hash 和原子提交策略。

Origin Worker 只执行该 Plan，不重新读取未声明项目对象，也不自行决定数据布局、ticks、样式或 capability。

## 11. Preflight

正式任务开始前依次检查：

1. Windows 中已安装 Origin，且版本/build/bitness 精确匹配当前 Beta build 唯一完成正式 43 图 O1 qualification 的声明；任何其他版本返回 `VERSION_UNSUPPORTED`。已有 31 图实机矩阵只是该声明的历史基础 evidence，新增 12 图未补齐时不得发布 43 图声明。
2. Origin license 当前可用。
3. Electron/Python/Origin 的 bitness 组合受支持。
4. `originpro` 可导入且版本与该 exact Origin qualification 记录一致。
5. ResolvedRenderPlan 所需字体可供 Origin 使用。
6. 官方 template 存在、签名/hash 正确。
7. chart type adapter 存在、版本和 capability 满足 ExportSpec。
8. 目标目录已授权、可写且同文件系统临时路径可用。
9. 目标文件没有被锁定，既有 hash 与 ExportRecord 预期一致。

Preflight 失败不启动 Origin 实例，也不留下正式或未登记临时文件。

## 12. 受控 Origin 实例

- Origin 队列严格串行。
- 每次任务启动 PlotAgent 管理的 dedicated blank instance。
- 永不调用 `op.attach()`，不连接、读取、保存或关闭用户已打开的 Origin。
- 只记录 PlotAgent 启动实例的进程/automation identity。
- 取消或故障只能终止/退出 PlotAgent 管理实例，不按进程名扫描或强杀用户 Origin。
- 构建实例与重新打开验证实例相互独立，均从空白项目开始。

## 13. 两阶段验证

### 13.1 Phase A：Live structural validation

在构建实例中逐项检查：

- Data/Analysis/Graphs/Metadata folders。
- books、sheets、Matrixbooks、rows、columns、designations、Units 和 Comments。
- graph pages、layers、plots、data links 与 source ranges。
- axis scale/range/direction、exact ticks/labels、legend、annotation、page size、subplot rectangles 和 style。
- numeric/category/datetime/missing 语义与 RenderPlan 输入 hash。
- 无 external data/template/file links。

全部 live 检查通过后，保存到目标目录同文件系统的临时 OPJU；不直接写最终路径。

### 13.2 Phase B：Fresh reopen validation

1. 退出并清理构建实例。
2. 启动新的 dedicated blank Origin instance。
3. 打开临时 OPJU。
4. 重新枚举 Project Explorer 与所有对象。
5. 读回 books/sheets/rows/columns/designations/Units、pages/layers/plots/data links、axes/ticks、legend、page/style。
6. 比较 numeric/category/datetime/missing 语义、对象 map、数据 hash、物理尺寸与 [渲染一致性容差](./RENDERING-PIPELINE.md#10-跨-renderer-语义一致性)。
7. 确认没有 external link，关闭验证实例。

只有两阶段都成功，临时文件才可以进入原子提交。

## 14. 整文件原子性

一个 OPJU 是一个原子正式产物：

- current chart、selected、batch 或 Figure 的所有目标都必须构建并通过两阶段验证。
- 任一目标、共享数据表、图层或 manifest validation 失败，整份 OPJU 不生成最终文件。
- 不允许静默跳过失败图、替换为 raster、降级 capability 或发布“部分 OPJU”。
- 用户要排除失败目标时，必须回到界面明确选择并创建新的 ExportSpec；新 ExportSpec 和 target list 进入审计。
- 原子移动前再次检查 target lock 和 expected existing hash。

## 15. ExportRecord 与外部修改

成功后本地 ExportRecord 保存：

- 最终外部 path、file hash、size 和 mtime。
- ExportSpec hash、ResolvedRenderPlan hash、OriginExportPlan hash 与 validation report hash。
- adapter/template/originpro/Origin version 与 capability。
- target object/version 列表和完成任务 ID。

外部文件只作为导出结果定位：

- Origin 中的编辑不同步回 PlotAgent。
- 同路径再次导出前比较当前 hash/size/mtime 与 ExportRecord。
- 检测到外部修改时返回 `EXTERNAL_MODIFIED`，要求用户确认覆盖或 Save As。
- 默认文件命名仍避免覆盖；即使用户选择覆盖，也必须先通过修改检查。
- 第一轮没有 OPJU import、merge 或 round-trip。

## 16. 稳定错误与恢复

| Error code | 含义 | 首选恢复动作 |
| --- | --- | --- |
| `NOT_INSTALLED` | 未检测到 Origin | 安装 Origin 后重新自检 |
| `VERSION_UNSUPPORTED` | Origin/adapter 版本不兼容 | 使用受支持版本或更新 adapter |
| `LICENSE_UNAVAILABLE` | License 不可用 | 在 Origin 中恢复授权后重试 |
| `CAPABILITY_MISSING` | 图形没有满足目标等级的 adapter | 禁用 OPJU；使用 PNG/SVG 或等待正式 adapter |
| `TEMPLATE_OR_FONT_MISSING` | 签名 template 或 resolved font 缺失 | 修复安装资源/字体后重新 preflight |
| `START_FAILURE` | 受控实例无法启动 | 运行 Origin 自检并检查 COM/bitness |
| `BUILD_FAILURE` | 原生对象构建失败 | 查看失败对象与 adapter 诊断，保持原规格重试 |
| `SAVE_FAILURE` | 临时 OPJU 保存失败 | 检查目录、空间与权限后重试或 Save As |
| `REOPEN_FAILURE` | 新实例无法重新打开临时文件 | 检查 Origin/文件完整性后重试 |
| `VALIDATION_FAILURE` | 读回对象或 parity 不满足 | 不发布文件，报告差异与 adapter 版本 |
| `TARGET_LOCKED` | 目标被占用 | 关闭占用程序或 Save As |
| `EXTERNAL_MODIFIED` | 既有导出被外部修改 | 明确覆盖或 Save As |
| `CANCELLED` | 用户取消或安全终止 | 清理临时文件；需要时明确重新导出 |

错误保持原始 RenderPlan、ExportSpec 和已完成诊断，不自动改图、删目标、换 template 或降级 capability。修复后正式重跑由用户触发。

## 17. 第一轮契约测试

- `.plotproj` 与 target-scoped OPJU 边界、无无关数据/对话/secret/path。
- current/selected/batch/Figure scope、共享数据去重和 Figure multi-layer graph。
- 四 folders、ASCII Short Name、Long Name、Units、Comments 和 designation。
- 最小列集、raw points 条件、PlotCalculationResult/用户预计算 Plot Data 和 Matrixbook。
- direct/fixed/user-precomputed 三类数据链、Raw/Plot Data 链接方向和 Raw Data 不自动重算说明。
- 禁止 Origin Analysis Template、worksheet formula、Fit Function、任意/未登记 LabTalk 与科学重算链。
- manifest object map、全部 hash/version、capability 与 O2 differences。
- O1/O2/O3/O0 定义、31 项 O1 准入和无运行时降级。
- OriginAdapter registry、typed property map、三项 Set 选项白名单、其余 LabTalk 阻断与 template 安全。
- 全部 preflight 条件与 dedicated instance 隔离。
- live validation、same-directory temp save、fresh reopen readback 和无 external links。
- 整 OPJU 原子失败、排除目标必须新 ExportSpec。
- ExportRecord、外部修改、Save As、无同步和无 OPJU import。
- 每个稳定 error code、恢复动作、取消与临时文件清理。
