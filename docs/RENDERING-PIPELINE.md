# PlotAgent 渲染管线与跨 Renderer 一致性契约

> 状态：第一轮渲染基线已确认  
> 日期：2026-08-05  
> 适用范围：ResolvedRenderPlan、质量层级、坐标范围、刻度、物理尺寸、安全文本、Matplotlib/Origin 语义一致性与导出验证  
> 相关文档：[原生 Origin OPJU 导出契约](./ORIGIN-EXPORT.md)、[领域契约与 Schema 设计](./DOMAIN-CONTRACTS.md)、[派生数据、单位与血缘契约](./DATA-TRANSFORMS.md)、[分析计算层与科学边界](./ANALYSIS-ENGINE.md)、[拟合系统契约](./FITTING-SYSTEM.md)、[后端与 Agent 架构](./BACKEND-ARCHITECTURE.md)、[产品决策基线](./PRODUCT-DECISIONS.md)、[产品需求文档](./PRD.md)

## 1. 单一解析链

第一轮只有一套版本化 Render Resolver：

```text
PlotSpec / FigureSpec
+ immutable DatasetVersion / AnalysisResult refs
+ resolved style / publication profile
+ quality tier / output target
                 │
                 ▼
        ResolvedRenderPlan
          ├─ Matplotlib adapter
          └─ Origin adapter
```

Resolver 负责所有会影响科学语义或布局的决定。Matplotlib 与 Origin adapter 只能把 RenderPlan 映射为目标对象，不得各自：

- autoscale、选择刻度或格式化不同标签。
- 重算统计、拟合、分箱、平滑或误差。
- 自动换单位、使用不同数据版本或静默删点。
- 重新放置图例、标注、面板或改变图层顺序。
- 用目标软件默认值补齐 RenderPlan 已承诺的关键语义。

## 2. ResolvedRenderPlan

ResolvedRenderPlan 是严格、版本化、可哈希的下游执行契约，至少包含：

- resolver schema、算法和图形注册表版本。
- PlotSpec/FigureSpec、DatasetVersion、AnalysisResult、样式与 publication profile 的精确引用和哈希。
- 物理画布尺寸、背景和每个 subplot 的矩形位置。
- series、geometry、layer 与 drawing order。
- 每个图层的数据表或 AnalysisResult output port 引用、字段与行 mask。
- 完整解析后的颜色、透明度、线、marker、font 和文本 AST。
- 每个 axis 的 scale、方向、range、tick values、tick labels、exponent、precision、title 和 UnitSpec。
- legend、annotation、reference、panel label 和 common legend 的确定位置与锚点。
- 数据完整性、原始点数、实际绘制点数、downsample 方法与状态。
- warning、能力要求、目标 renderer 约束和全部依赖版本。

Plan 使用规范化序列化计算 `render_plan_hash`。正式 ExportSpec 必须固定并记录该 hash；输出文件与导出记录也保存 plan hash。输入引用、resolver 版本或任何解析结果变化都会生成不同 hash。

## 3. 质量层级

第一轮有三个 quality tier：

| Tier | 用途 | 数据规则 |
| --- | --- | --- |
| `thumbnail` | 图形库、批次缩略图和资源预览 | 可使用确定性视觉降采样，必须记录完整/显示点数 |
| `interactive` | 对话预览和聚焦编辑 | 可使用确定性视觉降采样，必须标识状态且不能成为分析输入 |
| `formal` | PNG、SVG、OPJU 正式导出 | 使用完整数据与持久化 AnalysisResult 表，不降采样 |

三个层级使用同一 resolver、坐标算法、样式解析、文本 AST 和 tick 算法。缩略图与交互预览可以改变像素尺寸和实际绘制数据引用，但不能改变图形类型、数据范围候选、统计结果、类别映射或轴语义。

降采样只影响 geometry 的视觉点集合：

- autoscale 使用完整可见数据的范围摘要，不使用降采样后的极值。
- Plan 保存方法、版本、完整点数、显示点数和 mask/hash。
- 界面展示“显示 n / 完整 N”。
- formal PNG/SVG/OPJU 一律重新解析为完整数据 Plan。
- SVG 不允许因元素较多而静默抽稀或栅格化。

## 4. 第一轮坐标类型

Axis scale 只允许：

- `linear`
- `log2`
- `ln`
- `log10`
- `datetime`
- `categorical`

第一轮不包含 symlog、probability 或 probit axis。请求未支持 scale 时返回 `Unsupported`，不能回退为 linear。

坐标显示 scale 与 [拟合系统契约](./FITTING-SYSTEM.md) 中的模型变换彼此独立。改变 axis scale 不会重算 FitSpec 或其他 AnalysisSpec。

## 5. 确定性 Autoscale

### 5.1 范围候选

每个 axis 的 raw range candidate 来自所有可见且绑定该轴的：

- 原始或派生数据 geometry。
- error bars 与 interval endpoints。
- FitResult 持久化 curve、confidence band 和 prediction interval。
- 分布图、堆积图等已持久化绘图计算端口。
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
- log2、ln 和 log10 遇到参与可见 geometry 的非正值时阻止渲染，不静默过滤或夹到正数。

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

Unit prefix 只能来自用户确认的 UnitSpec 转换和实际 plot-local DatasetVersion。Resolver 不能只把 `V` 标签改成 `mV`、设置 Origin display factor 或借 scientific notation 暗中换算数据单位。Scientific exponent 是数值格式，必须在 Plan 中显式记录。

## 7. 物理尺寸与色彩

- canvas、margin、gutter 和 subplot rectangle 使用 mm 保存。
- font size、line width 和 marker size 使用 pt 保存。
- PNG 由物理尺寸与 DPI 精确计算 pixel dimensions，并写入 DPI metadata。
- SVG 写入物理 width/height 与匹配的 viewBox。
- Origin page 使用与 Plan 相同的物理尺寸和 subplot rectangles。
- 第一轮只使用 sRGB；不提供 CMYK 或 renderer 私有色彩转换。

Resolver 统一执行单位换算，adapter 不使用目标库默认 figure size、margin、font size 或 color cycle。

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
- 数据、误差、区间和持久化 fit curve 不由 Origin 重算。
- 不把 Matplotlib raster、整图 SVG 或其他嵌入对象作为“原生”fallback。

如果 Origin adapter 无法表达关键语义或无法在重新打开后读回验证，OPJU 导出必须阻止。非关键可接受差异只有在能力契约明确允许并披露时才可进入其他能力等级；不能由运行时临时降级。

第一轮 31 项正式图形的 OPJU 能力全部要求 O1。具体 target scope、数据布局、OriginAdapter、manifest、两阶段读回与整文件原子性见 [原生 Origin OPJU 导出契约](./ORIGIN-EXPORT.md)。

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
- 六种 axis scale、未支持 scale 和 log nonpositive 阻止。
- 全部 autoscale 来源、include-zero、outlier、reference、padding、zero-span、fixed bound、reverse 与 batch union。
- exact ticks/labels/exponent/precision、碰撞消减和 UnitSpec 前缀规则。
- mm/pt/DPI/viewBox/Origin page 与 sRGB。
- SafeRichText AST、非法 LaTeX/HTML/script、字体解析与 fallback。
- SVG text-to-path 默认和 editable-text warning。
- 所有 parity 容差与允许的非缺陷像素差异。
- O1 原生链接对象、关键语义阻止和无 raster fallback。
- PNG/SVG/OPJU 验证、临时文件清理与原子替换。
