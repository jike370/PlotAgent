<!-- SEED: re-run $impeccable document once there's code to capture the actual tokens and components. -->
---
name: PlotAgent
description: 面向通用科研用户的对话式本地绘图工作台
---

# Design System: PlotAgent

## 1. Overview

**Creative North Star: “校准工作台”**

界面像白昼实验室里整理干净、经过校准的仪器工作台。信息密度可以高，但每个对象都有明确归属；图表与数据是视觉主角，产品界面退居其后。整体气质严谨、清晰、有探索感，操作反馈直接而克制。首版视觉基线采用参考 PLOT 前端的灰白黑配色、组件比例和对话区尺寸，但不继承其三栏信息架构、常驻模型配置、Debug 或常驻版本栏。

产品采用接近 ChatGPT 的项目与对话结构，但数据集、绘图批次、图表版本和导出结果必须以明确的结构化对象出现。默认界面保持轻量，需要精确控制时才进入聚焦编辑，不让专业参数长期占据主对话。

第一阶段重做完整生产前端，所有现有生产页面与新增批量页面进入同一应用壳和设计系统，不保留长期新旧壳混用。设计蓝图与基础组件可以先行，真实页面接入必须使用稳定领域对象和真实 Core/Agent 结果；未实现能力不显示假按钮、占位页或 mock 结果。

产品明确拒绝传统后台管理系统的卡片堆叠、默认展开的复杂参数面板、过度科幻的深色界面，以及缺少数据与图形上下文的通用聊天机器人形态。

**Key Characteristics:**

- 灰白黑产品界面、纯白图表画布与低干扰工作区
- 对话优先、对象明确、复杂度逐步展开
- 密集但有秩序的科研信息
- 状态变化驱动的克制动效
- 图表配色与产品界面配色相互独立

## 2. Colors

采用参考 PLOT 前端的 Restrained 灰白黑色板。下列 8-bit sRGB 色值是首版产品界面的视觉真值；实现可保留语义化 token 名称，但不得重新加入绿色品牌底色。科研图表继续使用独立的 Origin 对照色板，不能从产品界面色板继承颜色。

### Neutral and action

| Token | Value | Use |
| --- | --- | --- |
| `bg-page` | `#f3f4f6` | 应用窗口外层与分隔背景 |
| `bg-shell` | `#fafafa` | 对话工作区背景 |
| `bg-panel` | `#ffffff` | 左侧栏、弹层、对象主表面与图表画布 |
| `bg-muted` | `#f5f5f5` | 次级工具、分组和 hover 基础 |
| `bg-subtle` | `#e7e7e7` | 强 hover 与轻量分隔 |
| `bg-selected` | `#e6e6e6` | 当前项目、对话、筛选和选中对象 |
| `bg-editor` | `#f2f2f2` | 专业编辑工作区 chrome |
| `border` | `#d4d4d4` | 输入、对象和分区边界 |
| `border-soft` | `rgba(115,115,115,0.28)` | 低权重分隔线 |
| `border-strong` | `#a3a3a3` | 活跃边界与高权重分隔 |
| `text` | `#171717` | 正文、标题和主操作 |
| `text-muted` | `#5f6368` | 次级信息、说明和 placeholder |
| `text-chip` | `#2f2f2f` | 标签和上下文 token |
| `accent` | `#171717` | 主按钮、当前操作和高权重选中 |
| `accent-strong` | `#000000` | 主按钮 hover/active |
| `accent-soft` | `#e5e5e5` | 次级操作 hover |
| `user-message` | `#f0f0f0` | 用户消息气泡 |

### Semantic state

| State | Foreground | Soft background |
| --- | --- | --- |
| Success | `#16805d` | `#e8f6ef` |
| Warning / NeedsInput | `#a15c00` | `#fff3d8` |
| Danger | `#b42318` | `#fdecec` |
| Info / keyboard focus | `#2563eb` | `#e8f0ff` |

正文 `#171717` 和次级文字 `#5f6368` 在白色/近白背景上满足 WCAG AA。参考实现的 placeholder `#6b7b78` 在白底约为 `4.44:1`，首版不照搬，统一使用 `#5f6368`。

**The Quiet Instrument Rule.** 黑色主操作与语义状态色只表达操作、选择和状态，不承担装饰。

**The Independent Plot Rule.** 产品界面颜色不得自动成为图表调色板；图表使用独立、色盲友好的科研配色体系。

## 3. Typography

**Display Font:** `Segoe UI Variable Text`, `Segoe UI`, `Microsoft YaHei UI`, `system-ui`, `sans-serif`
**Body Font:** `Segoe UI Variable Text`, `Segoe UI`, `Microsoft YaHei UI`, `system-ui`, `sans-serif`

**Character:** 单一、清晰、接近原生 Windows 工具的无衬线体系。界面字体服务于长时间阅读、数字比较和中英文混排，不使用展示字体制造品牌感。图表字体由项目发表规格独立控制。

### Hierarchy

- **Display:** 仅用于首次空状态的短标题，固定尺寸，不使用夸张的响应式字号。
- **Headline:** 用于项目、聚焦编辑和关键对话阶段标题。
- **Title:** 用于数据集、批次、图表和任务对象名称。
- **Body:** 用于对话与说明，长文本限制在可读行宽内。
- **Label:** 用于字段、状态、参数和元数据，不使用全大写中文或过度字距。

**The Data First Rule.** 界面标题不能比图表标题和关键数据更抢眼；层级依靠字重与间距，而不是超大字号。

### Fixed UI scale

- `12px`：元数据、状态、快捷键和标签，不再使用 7.5–10px 生产文字。
- `13px`：紧凑控件和辅助正文。
- `14px`：默认正文、输入和按钮。
- `16px`：工作区、对象和弹层标题。
- 字重以 `650 / 750 / 850` 为参考层级；系统字体不支持精确权重时选择最近的可用字重，不用字距制造层级。

## 4. Elevation

系统默认扁平，通过背景明度和清晰边界区分左侧栏、对话区、图表对象和参数面板。参考组件的轻量阴影语法可用于消息、提案、结果、菜单和弹层，但静态对象不得同时叠加 1px 边框与大范围柔和阴影。菜单、Popover 和 Dialog 可以使用更明显的 elevation；普通结构化对象优先使用背景与分隔线。

**The Flat-by-Default Rule.** 静态表面没有装饰性悬浮感，层级来自结构；阴影只证明一个对象当前确实位于另一个对象上方。

## 5. Reference component grammar

参考 PLOT 前端提供组件的视觉基线，不提供产品对象模型。所有组件必须以 PlotAgent 的真实状态、字段和动作重新实现。

- **间距：** `4 / 8 / 12 / 16 / 20 / 24px` 六级；同级组件不创建任意间距。
- **圆角：** `6 / 8 / 10 / 14px`；`999px` 只用于状态、筛选、文件、对象引用等 pill，不用于卡片和输入框。
- **按钮：** 黑色主按钮、灰色次按钮、文本/图标三级；主提交按钮高 40px，普通工具按钮 32–36px，紧凑菜单项仍保持至少 32px 点击热区。
- **输入：** 白/透明表面、清晰边界、蓝色 `2px` 键盘焦点；default、hover、focus、active、disabled、loading、error 必须完整。
- **消息：** 用户消息使用 `#f0f0f0` 气泡并靠右；Agent 文字、任务进度和结构化结果靠左，不能让所有对象都变成相同卡片。
- **提案与结果：** 沿用白色表面、10px 圆角、16px 内边距和紧凑动作组；数据、映射、警告、确认和产物必须来自真实对象。
- **标签与引用：** pill 仅表达状态、文件、图形、对象引用和作用范围；不能把普通元数据全部胶囊化。
- **菜单与弹层：** 使用标准 Popover/Dialog/Drawer，禁止在 overflow 容器内创建会被裁切的绝对定位菜单；Dialog 必须完成初始焦点、Tab 圈闭、Escape 和焦点恢复。
- **输入区：** 采用参考版 14px 圆角与 8px 内边距的组合输入容器；可用边框加微弱阴影，或无边框加浮层阴影，不复制“1px 边框 + 30px 模糊阴影”的组合。
- **图标：** 使用统一 Lucide 线性图标；有文字空间时不使用只有图标、含义不明确的动作。

## 6. Conversation geometry

主对话采用参考前端的阅读宽度和输入区尺度，同时允许复杂科研对象在同一内容轴内按需展开：

- 左侧项目/对话栏基准宽度 `258px`；最小窗口压缩到 `230px`。主对话永远不恢复常驻右栏。
- 工作区标题栏基准高度 `58px`。
- 对话内容轴基准宽度 `920px`，左右内边距使用 `max(28px, calc((100% - 920px) / 2))`，上下节奏以 `24px` 为基准。
- 普通 Agent 消息或提案默认最大宽度 `780px`；用户消息最大 `640px` 或内容轴的 `82%`；单图预览默认最大 `720px`。
- Dataset、Mapping、Batch、ChangeSet、ExportRecord 等确实需要横向信息的结构化对象可扩展到完整 `920px` 内容轴，但默认只展示摘要，详情按需展开。
- Composer 基准宽度 `840px`，距窗口底部 `22px`；文本区默认高 `40px`、最大高 `140px`。对象引用、作用范围、附件和图形选择在输入区上沿渐进展开。
- 对话正文行宽保持 `65–75ch`；结构化表格和图形预览不受正文字符行宽限制。

## 7. Mature product patterns

除参考 PLOT 的视觉语言外，交互设计只吸收成熟工具中能降低用户成本的通用模式，不拼贴其外观：

- **Windows desktop：** 标准控件、可预测 Tab 顺序、明确初始焦点、统一焦点视觉和键盘完整可达。
- **Notion：** 同一权威对象可以在对话、资源库和专业工作区用不同视图表达；`@` 用于显式引用，不依赖隐藏记忆。
- **Linear：** 批量审阅支持搜索、筛选、多选和同一套键盘/鼠标动作；相同操作在列表和缩略图视图保持语义一致。
- **Figma：** 只有进入聚焦编辑或组合图等专业工作区时才显示上下文属性；主对话不长期承担检查器。
- **Raycast：** `Ctrl+K`、搜索和 Action menu 提供专家效率，同时所有关键动作仍可通过可见界面发现。

模式来源：[Microsoft Windows keyboard interactions](https://learn.microsoft.com/en-us/windows/apps/develop/input/keyboard-interactions)、[Microsoft accessible Windows apps](https://learn.microsoft.com/en-au/windows/apps/design/accessibility/developing-inclusive-windows-apps)、[Notion database views](https://www.notion.com/help/category/database-views)、[Notion keyboard shortcuts](https://www.notion.com/help/keyboard-shortcuts)、[Linear board layout](https://linear.app/docs/board-layout)、[Figma properties panel](https://help.figma.com/hc/en-us/articles/360039832014-Design-Prototype-and-view-Code-in-the-Properties-Panel)、[Raycast keyboard shortcuts](https://manual.raycast.com/keyboard-shortcuts)。这些来源只作为交互原则依据，不改变 PlotAgent 已冻结的本地、明确选图、无常驻右栏和非分析平台边界。

## 8. Core Interaction Patterns

### 首次启动

- 应用无需账号、邀请码或联网即可直接进入主窗口空状态；内置模型服务只在首次需要 Agent 时轻量配置，不使用多页向导或账号表单。
- 空状态提供三个清晰层级的入口：主按钮“用示例项目试用”、次按钮“导入自己的数据”、文字入口“打开已有 `.plotproj`”。
- 示例入口说明可在约两分钟内看到完整结果；打开时创建本地副本，避免用户担心损坏示例。
- 三个入口直接执行对应任务，不放进相同权重的卡片网格。

### 对话与作用对象

- 数据集、映射、批次、图表、版本和导出以一致的结构化对象嵌入对话流。
- 导入结构确认与选图后的字段语义映射分开展示；图形需要外部分析结果时，在详情页和执行前明确标记“需要预计算字段”，不隐藏图形。
- 输入框附近常驻显示作用对象与范围；系列、坐标轴、图例、标注和面板选中后显示目标标签。
- 只有需要精确控制时进入全窗口聚焦编辑；检查器按需打开，不形成常驻右栏。

### 项目资源与批量审阅

- 项目资源库从项目标题或 `@` 打开为覆盖层/抽屉，支持资源、版本、血缘、归档和删除依赖查看。
- 第一阶段批量结果使用真实缩略图网格，支持多选、状态筛选、异常标记和失败项局部重试；列表、轮播、自由排序和叠加比较后移。
- 临时统一坐标或把当前图样式应用到选中图/批次时，必须显示共同适用能力和跳过项；未提交预览与正式新版本明确区分。

## 9. Do's and Don'ts

### Do:

- **Do** 使用纯白图表画布和低色度工作区，让科研图形成为视觉主角。
- **Do** 让项目、数据集、批次、图表版本和导出结果拥有一致的对象语法。
- **Do** 使用清晰焦点、键盘路径、色盲友好状态和 `prefers-reduced-motion`。
- **Do** 把常用操作放在对话中，把精确参数逐步展开到聚焦编辑。
- **Do** 把 PreparedDataset/Plot Data 标为绘图复现产物，把固定计算参数、排除计数与预计算来源做成可检查的结构化详情。
- **Do** 使用参考版 6/8/10/14px 圆角和六级间距，并保持按钮、输入框和对象容器的一致状态语法。
- **Do** 让主对话遵守 920px 内容轴和 840px Composer；只有真实横向信息需要时，结构化对象才扩展到内容轴全宽。

### Don't:

- **Don't** 采用传统后台管理系统的卡片堆叠。
- **Don't** 把复杂参数面板作为默认入口。
- **Don't** 采用过度科幻的深色界面、霓虹渐变或装饰性玻璃效果。
- **Don't** 把产品做成缺少数据与图形上下文的通用聊天机器人。
- **Don't** 在 v1 暴露通用数据处理、分析/拟合入口，或用模糊“自动计算”掩盖预计算字段要求。
- **Don't** 在同一静态容器上同时使用 1px 边框和大范围柔和阴影。
- **Don't** 使用渐变文字、彩色侧边条、超大圆角或没有状态意义的动画。
- **Don't** 因借鉴 Figma 等专业工具而在主对话恢复常驻右栏；上下文属性只属于全窗口专业模式或按需浮层。
