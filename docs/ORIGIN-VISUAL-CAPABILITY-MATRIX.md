# Origin 视觉能力全集与 PlotAgent 覆盖矩阵

> 状态：T1 公共视觉语言实施后的产品能力基线。
> 核查基准：OriginPro 2024 / 10.1 / Build 178 本机安装资产，以及 OriginLab 官方帮助。
> 产品范围：当前 34 张正式单图；Matplotlib 与 Origin 双后端；Origin 产物保持原生可编辑。
> 本轮施工范围：**只实现 T1 公共视觉语言**；T2 仅用于划清逐图边界，不在本轮新增；T3 不实现。
> 本文不是 Origin 设置面板复刻清单，也不是 UI 选项稿。

## 1. 目的

在决定 PlotAgent “应该支持哪些视觉编辑”之前，先回答四个问题：

1. Origin 实际提供什么能力；
2. Matplotlib 是否能表达相同语义；
3. PlotAgent 当前是否已经把该能力开放成强类型 Agent 动作；
4. 该能力应进入公共视觉语言、逐图参数，还是暂不开放。

不能因为某个 Origin 属性可以被 Python、LabTalk 或 Origin C 写入，就直接把它开放给 Agent。进入产品公共能力的属性必须同时满足：

- 用户能用稳定、可理解的自然语言表达；
- Matplotlib 与 Origin 都能表达相同语义；
- 属性不会悄悄改变数据或科研计算含义；
- 两端都能机械验证，Origin 保存后可在新会话读回；
- 动态数据、撤销、版本和失败语义可以保持一致。

## 2. 状态与层级

### 2.1 当前支持状态

| 状态 | 含义 |
|---|---|
| 已开放 | 当前公共 Engine Action 和对应 profile 已声明，Agent 可提交 |
| 部分开放 | 只有部分图类、部分参数或 renderer 内部实现，不能视为公共能力 |
| 内部默认 | renderer 或官方模板会使用，但 Agent 无法明确修改 |
| 未开放 | 当前公共合同中没有该能力 |

### 2.2 建议覆盖层级

| 层级 | 决策 |
|---|---|
| T1 公共视觉语言 | 高频、双后端同义、适合自然语言编辑；应优先覆盖 |
| T2 逐图能力 | 只对特定图类成立，由 profile 白名单和专属 renderer 实现 |
| T3 专家能力 | Origin 可以做到，但双后端语义、科学含义或稳定读回成本过高；暂不开放 |
| 不属于样式 | 会改变数据、统计计算或曲线几何，必须走数据处理或图类参数合同 |

## 3. 当前 PlotAgent 的真实基线

下表来自 `engine-profile.v1` 的 34 个正式 profile，而不是从 renderer 源码推测。

| 公共动作或参数 | 已声明图数 | 当前结论 |
|---|---:|---|
| 创建、字段绑定 | 34/34 | 已开放 |
| 图标题 | 34/34 | 文本、字体、字号、字重、斜体和颜色已开放 |
| 轴标题 | 34/34 | 已开放 |
| 轴类型 | 27/34 | 部分开放：linear/log10/datetime/categorical |
| 轴范围 | 30/34 | 部分开放；矩阵/类别轴及混合语义 Pareto 图除外 |
| 轴反转 | 33/34 | 部分开放 |
| 线颜色/宽度/线型/透明度 | 16/34 | 只对包含原生线对象的图类开放 |
| 符号形状/大小/内外颜色/透明度 | 15/34 | 只对包含原生符号对象的图类开放 |
| 填充/边框颜色、宽度、线型、透明度 | 13/34 | 只对柱、面积、箱体等对象开放 |
| 图例显示、位置、排版和字体 | 29/34 | 无图例语义对象的图类不开放 |
| 数据标签 | 12/34 | 只对稳定支持标签的图类开放 |
| 色板和颜色标尺 | 5/34 | 只对色图类开放 |
| 误差样式 | 2/34 | K06 仅误差棒；K07 仅误差带 |
| 图类参数 | 5/34 | 仅气泡标尺/色带、相关矩阵三角、等高线层级、Nyquist 等比例、混淆矩阵计数 |
| 独立文本标注 | 0/34 | 不属于当前产品范围，不在 profile 或 UI 开放 |
| PNG/SVG/OPJU 导出 | 34/34 | 已开放 |

当前公共合同仍没有独立表达：

- 逐目标能力白名单；当前能力粒度是“图类 + 动作”，不能区分混合图中左/右轴或柱/线系列的不同参数；
- 平滑、样条等会改变曲线几何的连接算法；
- 参考线、参考区间和特殊刻度；
- 图案填充、复杂渐变和任意属性按列映射；
- 页面尺寸、图层间距和面板布局。

因此，“Origin 模板默认看起来正确”不等于“Agent 已经拥有这些编辑能力”。

## 4. Origin 能力全集与产品决策

本章各表的“当前 PlotAgent”列保留 T1 施工前的差距记录，用来解释当时为什么纳入或排除某项能力；它不是当前计数。实施后的公开能力以第 3 节和《PlotAgent 产品测试覆盖审计》为准。

### 4.1 线和连接器

Origin 官方 [Line tab](https://docs.originlab.com/origin-help/pd-dialog-line-tab/) 提供：

- 连接方式：No Line、Straight、2/3 Point Segment、水平/垂直/居中阶梯、Spline、B-Spline、Bezier、Modified Bezier、Akima Spline；
- 线型、复合线型和自定义 dash；
- 连续线宽、颜色、透明度；
- 首尾闭合、子组内连接、箭头；
- 填充到基线、附加线或另一条曲线，并可区分上下区域颜色。

| 能力 | Matplotlib 等价性 | 当前 PlotAgent | 建议 |
|---|---|---|---|
| 线颜色 | 完整 | 28/34 的通用 `color` | T1，改为明确 `stroke_color` |
| 连续线宽 | 完整 | 20/34 | T1 |
| 常用线型 | 完整 | 13/34，4 种加 none | T1 |
| 线透明度 | 完整 | 未开放 | T1 |
| No Line / Straight | 完整 | 通过 line_style 间接表达 | T1，保持语义明确 |
| Step Horizontal/Vertical/Centered | 完整 | 未开放 | T2，限适用图类 |
| Spline/B-Spline/Bezier/Akima | 算法不完全相同 | 未开放 | 不属于普通样式；作为明确的曲线处理/连接算法单独评估 |
| 自定义 dash 数组 | 可表达，但跨后端细节不同 | 未开放 | T3 |
| 曲线下/曲线间填充 | 完整 | 多为 renderer 内部默认 | T2，面积图和误差带专属 |
| 箭头和闭合曲线 | 可表达 | 未开放 | T3 或标注能力 |

关键边界：平滑连接可能生成或解释新的曲线几何，不能被包装成无风险的“视觉样式修改”。

### 4.2 符号和散点

Origin 官方 [Symbol tab](https://docs.originlab.com/origin-help/pd-dialog-sym-tab/) 包括形状、连续大小、缩放、边缘、内部构造、透明度以及按列映射。Origin 常见原生形状包括方形、圆形、上下左右三角、菱形、加号、叉号、星号、五边形和六边形等；内部可为实心、空心、镂空、半填充或带中心构造。

| 能力 | Matplotlib 等价性 | 当前 PlotAgent | 建议 |
|---|---|---|---|
| 12 种常用几何符号 | 完整 | 12/34 可改 symbol | T1，沿用现有语义枚举 |
| 连续符号大小 | 完整 | 11/34 | T1 |
| 实心 / open / hollow | 完整 | 未开放 | T1 |
| 填充色与边缘色分离 | 完整 | 未开放 | T1 |
| 连续边缘宽度 | Matplotlib 可表达；Origin 2024 无稳定的原生读写合同 | 不开放，Origin 保留官方模板默认值 | 不纳入跨后端共同能力 |
| 符号透明度 | 完整 | 未开放 | T1 |
| 半填充和中心构造 | Matplotlib 仅部分直接等价 | 未开放 | T3 |
| 字符、数字、球体、用户位图符号 | 不稳定或语义不一致 | 未开放 | T3 |
| 大小/颜色按数据列映射 | 完整，但需要数据角色 | 气泡图有固定 size/color 角色 | T2，只通过图类声明的数据角色开放 |
| 任意符号属性按列映射 | 可编程实现 | 未开放 | T3 |

连续参数不应做成离散选项：符号大小由 profile 给出合法范围，UI 使用数值输入或滑杆。符号边缘宽度不进入 profile；Origin 始终保留官方模板默认值。

### 4.3 填充、边框和图案

Origin 官方 [Pattern tab](https://docs.originlab.com/origin-help/pd-dialog-pattern-tab/) 覆盖柱、条、面积、箱体等对象的填充色、边框、图案和透明度。

| 能力 | Matplotlib 等价性 | 当前 PlotAgent | 建议 |
|---|---|---|---|
| 填充色 | 完整 | 被通用 `color` 混合表达 | T1，独立 `fill_color` |
| 描边色 | 完整 | 未独立开放 | T1，独立 `stroke_color` |
| 连续边框宽度 | 完整 | 部分 renderer 借用 line width | T1 |
| 边框线型 | 完整 | 部分 renderer 借用 line style | T1 |
| 填充透明度 | 完整 | 未开放 | T1 |
| 边框透明度 | 完整 | 未开放 | T2 |
| 常用 hatch 图案 | 完整 | 未开放 | T2 |
| 渐变、双色和复杂图案 | Matplotlib 需要额外实现，语义难统一 | 未开放 | T3 |

### 4.4 分组和数据驱动样式

Origin 官方 [Group tab](https://docs.originlab.com/origin-help/pd-dialog-group-tab/) 可让组内系列按颜色、符号、线型、填充和其他属性递增，也可保存自定义列表。Origin 还允许按点、按系列或按工作表列映射属性。

| 能力 | Matplotlib 等价性 | 当前 PlotAgent | 建议 |
|---|---|---|---|
| 稳定类别颜色循环 | 完整 | 默认样式内部存在，Agent 无统一控制 | T1，按语义系列身份冻结 |
| 稳定符号/线型循环 | 完整 | 默认样式内部存在 | T1，用于颜色不足和可访问性 |
| 选择一个已登记的类别色表 | 完整 | 未开放 | T1 |
| 自定义递增列表 | 可实现 | 未开放 | T3 |
| 任意属性按列索引 | 可实现，但会扩大数据合同 | 未开放 | T3；气泡/色图等明确角色除外 |
| Group/Independent 原生物理模式 | Origin 专属 | 不应暴露 | 不开放给 Agent |

Agent 操作的是“语义系列和颜色循环”，不能操作 Origin 的物理 plot 编号、group head 或 Theme 节点。

### 4.5 数据标签和文本

Origin 官方 [Label tab](https://docs.originlab.com/origin-help/pd-dialog-label-tab/) 支持标签来源、数值格式、位置、偏移、旋转、字体、颜色、背景和引导线。

| 能力 | Matplotlib 等价性 | 当前 PlotAgent | 建议 |
|---|---|---|---|
| 图标题和轴标题文本 | 完整 | 34/34 | 已有 T1 |
| 字体、连续字号、颜色 | 完整 | 未开放 | T1 |
| 常规/加粗/斜体 | 完整 | 未开放 | T1 |
| 数据标签显示/隐藏 | 完整 | 多为图类默认 | T1 |
| 标签来源：数值/列名/指定列 | 完整，需要受控字段角色 | 未开放 | T2 |
| 数值格式、前后缀 | 完整 | 未开放 | T1 |
| 标签位置、偏移、旋转 | 完整 | 未开放 | T1 |
| 标签背景和引导线 | 完整 | 未开放 | T2 |
| 任意富文本、脚本或 HTML | 不应允许 | 禁止 | 继续使用 SafeRichText 白名单 |

### 4.6 坐标轴、刻度和网格

Origin 的 [Axis dialog](https://docs.originlab.com/origin-help/general-axis-dialog/) 将轴能力分为 Scale、Tick Labels、Title、Grids、Line and Ticks、Special Ticks、Reference Lines、Breaks 等页面；[Scale tab](https://docs.originlab.com/origin-help/axesref-scale/) 还包括范围、类型、反转和主次刻度。

| 能力 | Matplotlib 等价性 | 当前 PlotAgent | 建议 |
|---|---|---|---|
| 轴标题 | 完整 | 34/34 | 已有 T1 |
| linear/log10/datetime/categorical | 常用类型完整 | 27/34 | T1，按图类白名单 |
| 连续范围和反转 | 完整 | 29/34、33/34 | T1 |
| 主/次刻度数量或间隔 | 完整 | 未开放 | T1 |
| 刻度标签格式和旋转 | 完整 | 未开放 | T1 |
| 轴线颜色和宽度 | 完整 | 未开放 | T1 |
| 主/次网格显示和样式 | 完整 | 未开放 | T1 |
| 参考线和参考区间 | 完整 | 未开放 | T2，后续作为独立结构对象评估 |
| 特殊刻度 | 可实现 | 未开放 | T2 |
| 轴断点 | 两端都能实现但布局语义复杂 | 未开放 | T3 |
| Origin 全部轴类型和公式刻度 | 不完全同义 | 未开放 | T3 |

### 4.7 图例和颜色标尺

Origin 将 [图例](https://docs.originlab.com/origin-help/legend-colorscale/) 与 [颜色标尺](https://docs.originlab.com/origin-help/colorscale/) 作为独立可编辑对象，可设置来源、样本、布局、字体、标题、边框、级别和标签。

| 能力 | Matplotlib 等价性 | 当前 PlotAgent | 建议 |
|---|---|---|---|
| 图例显示/隐藏 | 完整 | 29/34 | T1 |
| inside/right/bottom 位置 | 完整 | 合同存在，profile 未声明 | T1 |
| 行列方向和列数 | 完整 | 未开放 | T1 |
| 字体、字号、颜色和标题 | 完整 | 未开放 | T1 |
| 条目顺序和语义标签 | 完整 | renderer 自动生成 | T1，来源必须绑定语义系列 |
| 边框和背景 | 完整 | 未开放 | T2 |
| 颜色标尺显示/位置 | 完整 | 仅 K04 有显示开关 | T1，限色图类 |
| 颜色标尺标签、刻度和标题 | 完整 | 未开放 | T1 |
| 同层多个独立颜色标尺 | 可实现但对象绑定复杂 | 未开放 | T3 |

### 4.8 色板和色域

Origin 官方 [Colormap tab](https://docs.originlab.com/origin-help/pd-dialog-colormap-tab/) 覆盖等级、填充、线、缺失值和颜色映射。本机 Origin 2024 安装包含 Viridis、Plasma、Inferno、Magma、BlueOrange、RedWhiteBlue、GrayScale、Fire、Rainbow_Modified 等官方 palette 资产。

| 能力 | Matplotlib 等价性 | 当前 PlotAgent | 建议 |
|---|---|---|---|
| 选择命名色板 | 完整 | 产品决策已有 16 个冻结资源，当前公共 Engine Action 未开放 | T1 |
| 色板反转 | 完整 | 未开放 | T1 |
| 自动/固定最小值和最大值 | 完整 | 未开放 | T1 |
| 发散色板中点 | 完整 | 未开放 | T1 |
| 连续/离散及等级数 | 完整 | K22 仅 levels | T1/T2 |
| 缺失值颜色 | 完整 | 未开放 | T1 |
| 等高线颜色和线宽 | 完整 | 未开放 | T2 |
| 任意用户色板文件 | 可读取但有安全和复现问题 | 未开放 | T3 |

命名色板必须保存冻结 RGB/stops、来源版本和 hash；不能在两个后端分别按同名色板猜颜色。

### 4.9 误差棒和误差带

Origin 官方 [Error Bar tab](https://docs.originlab.com/origin-help/pd-dialog-errbar-tab/) 提供颜色、样式、宽度、方向、端帽和透明度等设置。

| 能力 | Matplotlib 等价性 | 当前 PlotAgent | 建议 |
|---|---|---|---|
| 误差棒颜色和宽度 | 完整 | K06 借用系列 color/line width | T1，独立 error 样式 |
| 正/负/X/Y 方向 | 完整，但属于数据角色和结构 | 由 K06 绑定决定 | T2，不作为普通样式 |
| 连续端帽大小 | 完整 | 未开放 | T1 |
| 误差棒透明度 | 完整 | 未开放 | T1 |
| 误差带填充、边界和透明度 | 完整 | K07 多为内部默认 | T1 |
| 与中心线联动/独立 | 完整 | 未明确开放 | T2 |

### 4.10 柱、条、箱体和间距

Origin 官方 [Spacing tab](https://docs.originlab.com/origin-help/pd-dialog-spacing-tab/) 按图类提供柱/箱间距、组内组间间距、重叠、宽度和子组设置。

| 能力 | Matplotlib 等价性 | 当前 PlotAgent | 建议 |
|---|---|---|---|
| 柱/条/箱体宽度 | 完整 | 模板或 renderer 默认 | T2 |
| 组内/组间间距 | 完整 | 模板或 renderer 默认 | T2 |
| overlap | 完整 | 未开放 | T2 |
| 堆积/百分比堆积 | 完整 | 由图类决定 | 图类语义，不作为样式切换 |
| 数据列控制柱宽 | 可表达 | 只在专属浮动/气泡类有角色 | T3，除非图类明确声明 |
| 任意 subset/group 物理设置 | Origin 专属细节 | 不开放 | 不开放给 Agent |

### 4.11 统计图和分布图参数

Origin 的 [Box tab](https://docs.originlab.com/origin-help/pd-dialog-box-tab/)、[Distribution tab](https://docs.originlab.com/origin-help/pd-dialog-distribution-tab/) 和 [Data tab](https://docs.originlab.com/origin-help/pd-dialog-data-tab/) 包含箱线范围、须线、离群点、核函数、带宽、分箱和归一化等参数。

| 能力 | Matplotlib 等价性 | 当前 PlotAgent | 建议 |
|---|---|---|---|
| 箱体/须线/离群点视觉样式 | 完整 | 模板默认 | T2 |
| 四分位算法、须线系数 | 需要冻结同一算法 | renderer 固定 | 不属于样式；计算/图类参数 |
| 小提琴填充和边界 | 完整 | 模板默认 | T2 |
| KDE 核函数和带宽 | 算法需冻结 | renderer 固定 | 不属于样式；计算参数 |
| 直方图填充和边界 | 完整 | 通用 color 部分覆盖 | T2 |
| 分箱起点、终点、宽度、数量 | 算法需冻结 | renderer 固定 | 不属于样式；计算参数 |
| Count/Probability/Density | 会改变数值语义 | renderer 固定 | 不属于样式；计算参数 |

### 4.12 页面、图层、多轴和面板

Origin 可以控制 page、layer、轴链接、图层位置、面板间距和多轴关系。这些能力决定版面结构，而不只是对象外观。

| 能力 | Matplotlib 等价性 | 当前 PlotAgent | 建议 |
|---|---|---|---|
| 画布宽高和发表规格 | 完整 | renderer/profile 固定 | T1/T2，作为 publication profile |
| 页边距和图层矩形 | 完整 | 动态 renderer 内部 | T2，不直接暴露像素坐标 |
| 双 Y 轴标签和范围 | 完整 | 专属图类部分支持 | T2 |
| 多图层轴链接 | 完整 | 专属图类固定 | T2，只允许语义预设 |
| 面板行列、间距和共享轴 | 完整 | K24 等专属图类固定 | T2 |
| 任意 page/layer 树编辑 | 后端对象模型不同 | 未开放 | T3 |

### 4.13 3D 和 Origin 专属高级能力

Origin 还支持 3D surface、projection、plane、clipping、lighting、material、camera、OpenGL 等能力，例如官方 [3D Surface/Projections](https://docs.originlab.com/origin-help/pd-dialog-surfaceprojection-tab/) 与 [3D Fill](https://docs.originlab.com/origin-help/pd-dialog-colorfill-tab/)。当前 34 张正式图不以 3D 为产品范围。

| 能力 | Matplotlib 等价性 | 当前 PlotAgent | 建议 |
|---|---|---|---|
| 3D 相机、投影、灯光、材质 | 仅部分同义 | 未开放 | T3，当前不做 |
| 3D surface、plane、clipping | 仅部分同义 | 未开放 | T3，当前不做 |
| 任意 Origin Theme 树 | Origin 专属 | renderer 内部可能使用 | 永不作为公共 Agent API |
| LabTalk/Origin C 任意命令 | Origin 专属且不安全 | 禁止 | 永不开放 |
| Origin Gadget、App 和分析锁 | Matplotlib 无直接等价 | 不属于绘图样式 | 不进入公共视觉能力 |

## 5. 当前 T1 覆盖范围

当前 T1 不是“Origin 所有设置”，而是以下公共视觉语言。

### 5.1 线

- `stroke_color`
- `line_width_pt`（连续值）
- `line_style`: solid / dash / dot / dash_dot / none
- `line_opacity`（连续值）

### 5.2 符号

- `shape`: 当前 12 种 Origin 对齐几何符号
- `size_pt`（连续值）
- `interior`: solid / open / hollow
- `fill_color`
- `stroke_color`
- `stroke_width_pt`（连续值）
- `opacity`（连续值）

### 5.3 填充对象

- `fill_color`
- `fill_opacity`（连续值）
- `stroke_color`
- `stroke_width_pt`（连续值）
- `stroke_style`

适用对象由图类 profile 决定：柱、条、面积、误差带、箱体、小提琴、直方图、热图单元等不能共用同一个虚构系列对象。

### 5.4 文字和标签

- 字体族、连续字号、常规/加粗/斜体、颜色；
- 图标题和轴标题；
- 数据标签显示、数值格式、位置和旋转；
- 文字继续使用 SafeRichText，不接受任意 HTML/LaTeX/script。

### 5.5 坐标轴

- label、scale、bounds、reverse；
- 主/次刻度；
- 刻度格式和旋转；
- 轴线颜色和宽度；
- 主/次网格显示、颜色、线宽和线型。

### 5.6 图例和色标

- 显示、位置、方向/列数；
- 标题、字体、字号和颜色；
- 条目保持与语义系列绑定；
- 色标显示、位置、标题和刻度格式。

### 5.7 色板

- 从冻结的 Origin 对齐命名色板中选择；
- reverse；
- 自动或固定 domain；
- 发散中点；
- 连续/离散和等级数；
- 缺失值颜色。

### 5.8 误差

- 误差棒颜色、宽度、端帽大小和透明度；
- 误差带填充色、边界色、边界宽度和透明度。

这些字段不意味着必须增加同样数量的顶层 Agent operation。它们可以由少量强类型操作承载，但必须保留对象类型和适用范围，不能继续让一个 `color` 同时模糊表示线色、点色和填充色。

## 6. 当前明确不做

- Origin 全部连接算法；
- 任意自定义 dash、符号、色表或 Theme；
- 半填充、字符、数字、球体和用户位图符号；
- 复杂图案和渐变编辑器；
- 任意视觉属性按数据列映射；
- 任意 page/layer 物理树编辑；
- 轴断点和公式刻度；
- 3D 相机、灯光、材质、plane 和 projection；
- Origin Gadget、App 和分析设置；
- 任意 LabTalk、Origin C、Python 或 Matplotlib 参数透传。

“暂不做”不表示 renderer 不能使用官方模板中的这些默认值；它表示 Agent 不承诺安全、稳定、跨后端地编辑这些属性。

## 7. 逐图 T2 参数的判定规则（本轮不施工）

某个属性只有满足以下条件才进入图类 profile：

1. 官方文档或本机官方模板能证明其图类语义；
2. Matplotlib renderer 有同义实现；
3. 参数名描述科研/绘图语义，而不是 Origin 属性路径；
4. default、edited、dynamic data 均通过；
5. Origin 新进程重开后能读回；
6. 不支持时明确返回 `Unsupported`，不得近似或静默忽略。

典型 T2 参数包括：柱宽和间距、误差方向、气泡大小范围、箱线须线、小提琴带宽、直方图分箱、热图/等高线等级、双轴链接和面板布局。

## 8. 实施和验收顺序

### 8.1 施工顺序

1. 冻结本文的 T1/T2/T3 边界；
2. 将公共样式合同拆成 line / marker / fill / text / axis / legend / color-map / error；
3. 为 34 个 profile 逐项声明允许的 T1 对象和参数；
4. 建立 Matplotlib 与 Origin 的公共 adapter；
5. 只补齐 T1 映射，不新增 T2 图类参数，不允许 backend-specific fallback；
6. 以同一强类型合同接入自然语言和前端控件，禁止两套编辑逻辑。

### 8.2 每项能力的完成标准

一项能力只有同时满足以下条件才算完成：

- 强类型合同能表示；
- profile 明确声明支持；
- Agent 能从自然语言生成正确目标和参数；
- 用户确认前无副作用；
- Matplotlib 结果正确；
- Origin 使用原生对象表达；
- OPJU 保存并在新的 Origin 会话读回一致；
- 撤销恢复到上一版本；
- 不适用图类稳定返回 `Unsupported`；
- 黑盒 UI 能观察到操作、结果和错误。

Matplotlib 与 Origin 要求语义一致，不要求像素完全相同；不允许用截图嵌入 Origin 代替原生可编辑对象。

## 9. 来源

OriginLab 官方帮助：

- [Plot Details: Line](https://docs.originlab.com/origin-help/pd-dialog-line-tab/)
- [Plot Details: Symbol](https://docs.originlab.com/origin-help/pd-dialog-sym-tab/)
- [Plot Details: Pattern](https://docs.originlab.com/origin-help/pd-dialog-pattern-tab/)
- [Plot Details: Group](https://docs.originlab.com/origin-help/pd-dialog-group-tab/)
- [Plot Details: Label](https://docs.originlab.com/origin-help/pd-dialog-label-tab/)
- [Plot Details: Colormap](https://docs.originlab.com/origin-help/pd-dialog-colormap-tab/)
- [Plot Details: Error Bar](https://docs.originlab.com/origin-help/pd-dialog-errbar-tab/)
- [Plot Details: Spacing](https://docs.originlab.com/origin-help/pd-dialog-spacing-tab/)
- [Plot Details: Box](https://docs.originlab.com/origin-help/pd-dialog-box-tab/)
- [Plot Details: Distribution](https://docs.originlab.com/origin-help/pd-dialog-distribution-tab/)
- [Plot Details: Data](https://docs.originlab.com/origin-help/pd-dialog-data-tab/)
- [Axis Dialog](https://docs.originlab.com/origin-help/general-axis-dialog/)
- [Axis Scale](https://docs.originlab.com/origin-help/axesref-scale/)
- [Graph Legends](https://docs.originlab.com/origin-help/legend-colorscale/)
- [Color Scales](https://docs.originlab.com/origin-help/colorscale/)
- [3D Surface/Projections](https://docs.originlab.com/origin-help/pd-dialog-surfaceprojection-tab/)

本机证据：

- `D:\origin\Origin64.exe`：OriginPro 2024 / 10.1 / Build 178；
- `D:\origin\Plot.ogs`：本机菜单到模板/绘图流程的实际分派；
- `D:\origin\Palettes\`：本机随安装 palette 资产；
- `build/origin-native-proof-38/local-assets-core.*` 与 `local-assets-extended.*`：版本、路径、大小和 SHA-256 记录。
