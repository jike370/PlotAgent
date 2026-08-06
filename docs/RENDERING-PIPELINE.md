# PlotAgent 渲染管线与跨 Renderer 一致性契约

> 状态：第一轮渲染基线已确认；M6 基础泛化、逐图编辑/Origin 样式与结构编译补充契约已冻结、实现门禁重新打开
> 日期：2026-08-06
> 适用范围：ResolvedRenderPlan、逐图编辑能力、Origin 对齐符号/色板、质量层级、坐标范围、刻度、物理尺寸、安全文本、Matplotlib/Origin 语义一致性与导出验证
> 相关文档：[小规模 Beta 性能测试与发布门禁契约](./PERFORMANCE-TEST-RELEASE.md)、[原生 Origin OPJU 导出契约](./ORIGIN-EXPORT.md)、[领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)、[受控数据准备、单位与来源追溯契约](./DATA-TRANSFORMS.md)、[固定绘图计算与科学边界](./ANALYSIS-ENGINE.md)、[拟合能力分期边界](./FITTING-SYSTEM.md)、[后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)、[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)

## 1. 单一解析链

第一轮只有一套版本化 Render Resolver：

```text
ChartRecipeRef + FieldMapping + data refs + explicit overrides
                 │
                 ▼
       deterministic Recipe Compiler
                 │
                 ▼
PlotSpec / FigureSpec
+ immutable PreparedDataset / PlotCalculationResult / precomputed refs
+ resolved style / publication profile
+ quality tier / output target
                 │
                 ▼
        ResolvedRenderPlan
          ├─ Matplotlib adapter
          └─ Origin adapter
```

Recipe Compiler 只把已验证的版本化组件图、语义端口映射和封闭关系编译为 PlotSpec；Resolver 负责所有会影响科学语义或布局的决定。Matplotlib 与 Origin adapter 只能把 RenderPlan 映射为目标对象，不得各自：

- autoscale、选择刻度或格式化不同标签。
- 重算分箱、KDE、summary/error、拟合、科学分析或预计算字段。
- 自动换单位、使用不同数据版本或静默删点。
- 重新放置图例、标注、面板或改变图层顺序。
- 用目标软件默认值补齐 RenderPlan 已承诺的关键语义。

## 2. ResolvedRenderPlan

ResolvedRenderPlan 是严格、版本化、可哈希的下游执行契约，至少包含：

- resolver schema、算法和图形注册表版本。
- PlotSpec/FigureSpec、PreparedDataset、PlotCalculationResult/用户预计算表、样式与 publication profile 的精确引用和哈希。
- 物理画布尺寸、背景和每个 subplot 的矩形位置。
- series、geometry、layer 与 drawing order。
- 每个图层的 Raw/Prepared/Plot Data 或 PlotCalculationResult 引用、字段与行 mask。
- 完整解析后的颜色、透明度、线、marker、font 和文本 AST。
- `ChartEditCapabilityProfile`、palette、marker 与双 Y default style 的精确 version/hash。
- 每个 axis 的 scale、方向、range、tick values、tick labels、exponent、precision、title 和 UnitSpec。
- legend、annotation、reference、panel label 和 common legend 的确定位置与锚点。
- 数据完整性、原始点数、实际绘制点数、downsample 方法与状态。
- warning、能力要求、目标 renderer 约束和全部依赖版本。

Plan 使用规范化序列化计算 `render_plan_hash`。正式 ExportSpec 必须固定并记录该 hash；输出文件与导出记录也保存 plan hash。输入引用、resolver 版本或任何解析结果变化都会生成不同 hash。

### 2.1 结构编译与动态布局

- 官方图与未来自定义图使用同一 `StructureUnitDefinition → ChartRecipe → PlotSpec → ResolvedRenderPlan` 路径；官方身份只增加准入证据，不允许 adapter 中存在另一套隐藏结构语义。
- Recipe Compiler 校验完整组件图、语义端口和关系闭包，不使用“任意两组件可组合”推断完整图合法，也不维护所有组合的穷举白名单。
- 数据、FieldId、文件路径、自动坐标结果、PlotCalculationResult 和 renderer 代码不得进入 ChartRecipe；它们只在具体 PlotSpec/Plan 中通过版本化引用出现。
- 同一 recipe version、mapping、data/style refs 和 compiler/resolver 版本必须产生相同的 canonical PlotSpec、Plan 与 hash。
- 组数、类别/点数、数值范围、误差结构、标签长度和物理画布变化必须驱动 bar width/dodge/stack、error attachment、offset、legend columns、tick density、padding 和 subplot rect；不能从 chart type ID 或 fixture 名称读取固定几何参数。
- 解析后的 Plan 必须满足：全部几何值有限；同组柱不重叠；正负堆积分别累加；误差绑定其系列及轴；轴范围覆盖全部可见数据/误差/区间；series、颜色和 legend identity 一致。
- 物理画布不足时输出版本化、可操作 warning 或稳定阻止结果，不允许靠重叠、丢图元、截断标签或缩小到不可读来满足布局。最小宽度、间距和文字阈值必须附 Origin/期刊证据来源与版本。

## 3. 质量层级

第一轮有三个 quality tier：

| Tier | 用途 | 数据规则 |
| --- | --- | --- |
| `thumbnail` | 图形库、批次缩略图和资源预览 | 可使用确定性视觉降采样，必须记录完整/显示点数 |
| `interactive` | 对话预览和聚焦编辑 | 可使用确定性视觉降采样，必须标识状态且不能成为 PlotCalculation 输入 |
| `formal` | PNG、SVG、OPJU 正式导出 | 使用完整 PreparedDataset、PlotCalculationResult 或用户预计算表，不降采样 |

三个层级使用同一 resolver、坐标算法、样式解析、文本 AST 和 tick 算法。缩略图与交互预览可以改变像素尺寸和实际绘制数据引用，但不能改变图形类型、数据范围候选、PlotCalculationResult、类别映射或轴语义。

降采样只影响 geometry 的视觉点集合：

- autoscale 使用完整可见数据的范围摘要，不使用降采样后的极值。
- Plan 保存方法、版本、完整点数、显示点数和 mask/hash。
- 界面展示“显示 n / 完整 N”。
- formal PNG/SVG/OPJU 一律重新解析为完整数据 Plan。
- SVG 不允许因元素较多而静默抽稀或栅格化。

## 4. 第一轮坐标类型

Axis scale 只允许：

- `linear`
- `log10`
- `datetime`
- `categorical`

第一轮不包含 log2、ln、symlog、probability 或 probit axis。请求未支持 scale 时返回 `Unsupported`，不能回退为 linear。

坐标显示 scale 只改变显示语义，不执行单位换算、科学变换或拟合。v1 Log10 遇到参与绘图的非正值即阻断。

## 5. 确定性 Autoscale

### 5.1 范围候选

每个 axis 的 raw range candidate 来自所有可见且绑定该轴的：

- Raw/Prepared/用户预计算数据 geometry。
- error bars 与 interval endpoints。
- 用户提供的 curve、confidence band、step、matrix 等预计算字段。
- 分布图、堆积图等持久化 PlotCalculationResult。
- 显式设置 `affect_range: true` 的 reference line 或 reference region。

以下内容不扩大范围：

- legend、annotation、panel label 和普通文字。
- `affect_range: false` 的 reference。
- hidden series 或被本次导出明确排除的项。
- NaN、Inf 和无效日期时间；Resolver 记录排除数量与原因。

离群值属于数据，默认包含在范围候选中。Resolver 不根据箱线规则或视觉密度自动排除极值。

### 5.2 图形家族规则

- bar、stack 和 area 的数值轴包含零。
- line、scatter 和 distribution 不强制包含零。
- categorical axis 在首尾类别中心外各保留半个 slot。
- continuous axis 在变换空间对 raw candidate 两端各加 5% padding。
- zero-span 使用版本化的 deterministic expansion rule，规则 ID 与结果写入 Plan。
- log10 遇到参与可见 geometry 的非正值时阻止渲染，不静默过滤或夹到正数。

每个 lower/upper bound 独立为 `auto` 或 `fixed`：

- fixed bound 保持用户数值，不参与 padding。
- auto bound 按完整候选和规则解析。
- 轴反向通过独立 `reversed: true` 表达，不交换或重写数据。

### 5.3 批次统一范围

批次开启 unified scale 时：

1. 每张图按完整可见数据计算未 padding 的 raw candidate。
2. Resolver 对所有候选取 union。
3. 图形家族的 include-zero 与 fixed-bound 约束先做一致性校验。
4. 只对 union 结果执行一次 padding 与 zero-span 规则。
5. 每张图写入完全相同的 resolved range 与 tick sequence。

不能先为每张图 padding 再取 union，否则图数和极值分布会改变最终留白。

## 6. Tick 与标签解析

Resolver 使用版本化 nice-number algorithm 生成：

- exact tick values。
- exact tick labels。
- scientific exponent 与显示位置。
- numeric precision、decimal separator 和 negative-zero 规则。
- datetime interval、format 与 timezone label。
- categorical tick order 与 label。

标签碰撞消减是确定性的：Plan 记录测量字体、可用长度、候选数量、保留索引、旋转/换行和算法版本。Matplotlib 与 Origin 不再自行删 tick 或修改精度。

v1 不执行 Unit prefix 换算。Resolver 不能只把 `V` 标签改成 `mV`、设置 Origin display factor 或借 scientific notation 暗中换算数据单位。Scientific exponent 只是数值格式，必须在 Plan 中显式记录且不改变 UnitSpec。

## 7. 物理尺寸与色彩

- canvas、margin、gutter 和 subplot rectangle 使用 mm 保存。
- font size、line width 和 marker size 使用 pt 保存。
- PNG 由物理尺寸与 DPI 精确计算 pixel dimensions，并写入 DPI metadata。
- SVG 写入物理 width/height 与匹配的 viewBox。
- Origin page 使用与 Plan 相同的物理尺寸和 subplot rectangles。
- 第一轮只使用 sRGB；不提供 CMYK 或 renderer 私有色彩转换。

Resolver 统一验证已经确认的 UnitSpec，但 v1 不执行单位换算；adapter 不使用目标库默认 figure size、margin、font size 或 color cycle。

### 7.1 逐图编辑解析

正式 create/edit/export capability 只包含 43 图；X07、X11、X12、X15、X16、X17、X18、X19、X37 即使内部 resolver/adapter 存在，也必须在 capability 构建阶段按 `availability=internal_hidden` 排除。每次 PlotPatch 依次执行：

1. 读取目标 chart type 固定版本的 `ChartEditCapabilityProfile`。
2. 校验 operation、semantic target、payload field、数值范围和 Matplotlib/Origin 双 renderer support。
3. 将强类型修改应用到新的 PlotSpec/resolved style 版本。
4. Resolver 生成包含 profile/style version 与全部解析值的新 RenderPlan/hash。
5. Adapter 只映射 Plan；没有 profile 声明的字段不得依赖目标软件默认值实现。

不支持请求由 Agent 表达为 `Unsupported(reason=chart_edit_capability_not_supported)`，本地 validator 使用 `PATCH_CAPABILITY_NOT_SUPPORTED` 并保持原 PlotSpec 不变。分箱、KDE 带宽、ECDF/CCDF 等改变绘图数值的参数先生成新的封闭 PlotCalculationResult，再进入上述渲染链，不作为 renderer-only style patch。

### 7.2 Origin 对齐符号

`MarkerSymbol` 只允许以下稳定交集：

| semantic enum | Origin 显示名 | Matplotlib |
| --- | --- | --- |
| `square` | Square | `s` |
| `circle` | Circle | `o` |
| `triangle_up` | Up Triangle | `^` |
| `triangle_down` | Down Triangle | `v` |
| `diamond` | Diamond | `D` |
| `plus` | Plus Sign | `+` |
| `cross` | Cross | `x` |
| `triangle_left` | Left Triangle | `<` |
| `triangle_right` | Right Triangle | `>` |
| `hexagon` | Hexagon | `h` |
| `star` | Star | `*` |
| `pentagon` | Pentagon | `p` |

项目和 Plan 保存 semantic enum，不保存 Origin 数字编号。闭合符号的 `MarkerInterior` 为 `solid | open | hollow`：`solid` 写显式 fill；`open` 写已经解析的 axes background fill 以遮挡下层线；`hollow` 写透明 fill 使下层线可见。`plus/cross` 无内部且只接受规范化 `solid`，请求 `open/hollow` 稳定不支持。背景、stroke、fill、size 和 width 全部在 resolver 中解析，adapter 不猜测。

### 7.3 Origin 对齐色板与类别分配

内置 palette allowlist 为 `ColorBlindSafe8`、`ColorBlindSafe15`、`BlueOrange`、`OrangeNavy`、`RedPurple`、`Viridis`、`Plasma`、`Inferno`、`Magma`、`GreyBlue`、`YellowBlue`、`YellowGreen`、`YellowPurple`、`GrayScale`、`Fire`、`Rainbow_Modified`。`GrayScale` 锚定 Origin 2024 SR1 随安装 `Palettes/GrayScale.PAL`；产品统一称为 PaletteRef，但必须保留 Origin 来源是 Color List 还是 Palette。每个版本冻结：

- Origin 来源名、`color_list/palette` 资产类型、`qualitative/sequential/diverging/special/grayscale` 配色类型与顺序。
- 8-bit sRGB colors 或 normalized stops，以及 source version/hash。
- reverse、离散采样与连续插值规则。

ResolvedRenderPlan 与 Matplotlib 直接使用同一组冻结 sRGB 值。原生 Origin 导出仅可使用已限定 Origin 版本安装目录中的对应官方 `.pal/.oth`，且必须在使用前核验 source hash；缺失或不一致时稳定失败，不读取用户色板，也不因目标环境中存在同名 palette 而替换。严格 `#RRGGBB` 可用于单一显式颜色。普通 Jet/Rainbow 不作为默认；`Rainbow_Modified` 只响应用户显式选择。

类别数不超过 15 时保持项目内稳定 color identity；类别缺失不重排。类别数超过 15 时禁止循环颜色，resolver 按冻结规则增加不同 symbol；如果编码组合或物理画布仍不足以区分，则产生可操作 warning 或稳定阻止。X23、X24、X35、X36 的左右轴默认解析为相同中性色、正常字重和非加粗细线；只有已允许的显式 patch 才能让轴颜色分别随系列变化。

## 8. 安全文本与字体

图表文字保存为 SafeRichText AST，只允许：

- plain text 与 newline。
- subscript 与 superscript。
- bold 与 italic。
- Unicode Greek 与常用科学符号。
- 有限、结构化的 numerator/denominator fraction。

AST 有固定节点、最大嵌套深度和长度。第一轮不接受任意 LaTeX、MathText、HTML、CSS、JavaScript、Origin escape/script 或目标 renderer 指令。输入框可以提供受控快捷语法，但保存与跨进程传输前必须解析并显示为安全 AST；无法解析时返回 NeedsInput。

默认图表 font stack 固定为：

```text
Arial -> Microsoft YaHei -> DejaVu Sans
```

Resolver 在生成 Plan 时解析每个文本 run 的实际 font family、font file hash、weight、style 和 fallback。正式导出前验证字体可用性；Matplotlib 与 Origin 必须使用 Plan 中同一解析字体。Publication profile 指定字体时同样先解析和验证，不能由 adapter 自行 fallback。

## 9. SVG 文本模式

- 默认 `text_to_path`，以图形轮廓保证跨设备视觉一致性。
- 可选 `editable_text` 保留 text element 与字体信息。
- editable text 在导出前显示字体可移植性 warning，并在 ExportSpec 与导出记录中保存选择。
- 两种模式都使用同一 SafeRichText AST、位置、font metrics 和 plan hash。
- SVG 不包含脚本、外部字体/图像引用或可执行事件属性。

## 10. 跨 Renderer 语义一致性

目标是 semantic parity，不是 pixel identity。必须一致的内容包括数据、图层、range、ticks、标签、物理布局、字体/线/marker 尺寸、颜色、透明度、图例、标注和面板关系。

第一轮自动校验容差：

| 项目 | 容差 |
| --- | --- |
| canvas physical size | ±0.2 mm |
| subplot rectangle / placement | ±1 mm |
| font size / line width | ±0.1 pt |
| marker size | ±0.25 pt |
| 8-bit RGB | 每通道精确相等 |
| alpha | ±0.01 |
| numeric range / tick value | `1e-10 × max(1, abs(value))` |

Font hinting、anti-aliasing、subpixel rasterization 和极短 dash 的 line-cap 像素差异不算缺陷。只要目标对象的读取值在上述容差内且语义完整，就不要求 PNG 与 Origin 截图逐像素相同。

## 11. Origin O1 渲染约束

O1 输出必须用 Origin 原生、链接的数据对象表达：

- worksheet/matrix 与 graph plot 保持数据链接。
- axis、tick、legend、annotation 和 page layout 可继续编辑。
- 数据、误差、区间、固定计算结果和用户预计算曲线不由 Origin 重算。
- 不把 Matplotlib raster、整图 SVG 或其他嵌入对象作为“原生”fallback。

如果 Origin adapter 无法表达关键语义或无法在重新打开后读回验证，OPJU 导出必须阻止。非关键可接受差异只有在能力契约明确允许并披露时才可进入其他能力等级；不能由运行时临时降级。

第一轮正式 43 图的 OPJU 能力全部要求 O1。已有 31 图 full live+fresh-reopen 矩阵是基础证据；新增 12 图必须在同一 exact Origin version 补齐后才能完成发布 qualification。具体 target scope、数据布局、OriginAdapter、manifest、两阶段读回与整文件原子性见 [原生 Origin OPJU 导出契约](./ORIGIN-EXPORT.md)。

正式新增 12 图与原 31 图共用单一 resolver、冻结 Origin 对照配色、坐标自动缩放和同一 ResolvedRenderPlan。图形特有几何（如哑铃连接线、蜂群避让、浮动柱区间、人口金字塔、Y 偏移、双 Y 轴分层）只能由固定 resolver 计算；Matplotlib 与 Origin adapter 不得各自猜测。视觉 oracle 以 Origin 模板/官方项目优先并要求图—数据同源；X24、S07 当前冻结合成证据必须单独标识。九个隐藏 P1 adapter 只保留内部回归，不属于正式渲染/导出承诺。

## 12. 正式产物验证

### 12.1 PNG

- 文件 signature 与解码成功。
- pixel width/height 与 Plan/DPI 一致。
- DPI metadata、color mode 和 alpha 与 ExportSpec 一致。
- 内容非空，预期画布与图层区域存在有效像素。

### 12.2 SVG

- XML 可安全解析，width/height/viewBox 与 Plan 一致。
- 不含 script、event handler、external reference 或不允许的嵌入内容。
- 关键 path/text/group/clip 等 element count 与 adapter 预期一致。
- text mode、颜色、透明度和物理尺寸通过检查。

### 12.3 OPJU

- 先在受控实例内检查 books、pages、layers、plots、data links、axes、ticks、legend、page 和 style。
- 保存后退出，再用新的空白受控 Origin 实例重新打开。
- 重新枚举并读取关键对象和值，按本文件容差比较 Plan。
- 任何关键语义、数据链接或物理布局验证失败都不产生正式文件。

## 13. 临时文件与原子提交

每个正式产物遵循：

1. 在与目标同一文件系统的任务临时路径写入。
2. 解析或重新打开并完成格式、结构、语义和 plan-hash 验证。
3. 验证通过后原子替换目标。
4. 失败或取消时不修改既有正式文件，并清理未注册临时产物。
5. 导出记录保存 ExportSpec、ResolvedRenderPlan、输出文件和验证报告的哈希。

## 14. 第一轮契约测试

- 同一 PlotSpec 和固定引用生成相同规范化 RenderPlan 与 hash。
- Matplotlib/Origin adapter 拒绝自行 autoscale、ticks、统计或单位换算。
- thumbnail/interactive 降采样标识与 formal 全量数据。
- linear/log10/datetime/categorical 四种 axis scale、未支持 scale 和 log nonpositive 阻止。
- 全部 autoscale 来源、include-zero、outlier、reference、padding、zero-span、fixed bound、reverse 与 batch union。
- exact ticks/labels/exponent/precision、碰撞消减和 UnitSpec 前缀规则。
- mm/pt/DPI/viewBox/Origin page 与 sRGB。
- SafeRichText AST、非法 LaTeX/HTML/script、字体解析与 fallback。
- SVG text-to-path 默认和 editable-text warning。
- 所有 parity 容差与允许的非缺陷像素差异。
- O1 原生链接对象、关键语义阻止和无 raster fallback。
- PNG/SVG/OPJU 验证、临时文件清理与原子替换。
- ChartRecipe graph/port/relation 校验、canonical compiler、官方/自定义同构路径，以及 recipe 不含数据、FieldId、路径、计算结果或可执行内容。
- 冻结泛化 generator/version/seed/manifest 独立于被测实现；oracle 不由当前 compiler、resolver 或 renderer 在测试时生成。
- 每种基础结构覆盖组数 1/2/3/5、点数/类别数、尺度和平移、跨零/全负、零/对称/非对称误差、长中英文标签和可选字段缺失，并断言有限几何、无重叠、堆积、误差、范围和 series-color-legend 身份不变量。
- Matplotlib 执行完整基础泛化矩阵；Origin 按结构签名选择代表性变体，同时每个正式图保留至少一个参考图与同源数据锚定的外观证据。两类 evidence 不互相替代。
- 已准入 ChartRecipe 的用户复用只运行普通 Schema/输入/capability 校验和产物验证，不重复执行泛化或 Origin qualification。
- 正式 43 图的 capability snapshot 精确匹配 PRD 逐图白名单；隐藏九图不出现在 create/edit/export capability，直接请求稳定失败。
- 每个 allowed patch 至少覆盖 Schema、目标、版本、事务提交和 Matplotlib/Origin mapping；每个未声明 operation/target/payload field 覆盖 `Unsupported` 与 `PATCH_CAPABILITY_NOT_SUPPORTED`，不得产生部分版本。
- 全部 12 种 MarkerSymbol 与闭合符号的 `solid/open/hollow` 按代表性 chart structure 验证，尤其区分 `open` 背景遮挡与 `hollow` 透明穿线；`plus/cross` 的 `open/hollow` 验证稳定不支持。Origin fresh-reopen 读回原生 symbol/interior，Matplotlib 检查 resolved path/fill。
- 16 个 palette 的 version/hash、顺序、reverse、离散/连续映射和 frozen RGB 通过 golden；跨 renderer 8-bit RGB 每通道精确，指定 Origin 官方资产通过 source hash 验证，缺失或修改后稳定失败且不得产生结果。
- 类别数 15/16/超过可区分组合的边界分别验证稳定颜色、颜色+符号不循环和 warning/阻止；双 Y 默认轴线验证中性、正常字重、非加粗，显式着色 patch 只改样式不改 axis assignment/range。
