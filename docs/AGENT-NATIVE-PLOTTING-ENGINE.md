# Agent Native 科研绘图引擎重写基线

> 状态：当前唯一有效的绘图引擎重写边界。旧 PlotSpec、resolver、Origin plan 和统一 renderer 文档仅作为历史记录，不得指导新实现。

## 1. 产品目标

PlotAgent v3 的核心交付物是一个 **Agent Native 科研绘图引擎**，而不是一套只能由仓库内置 Agent 使用的绘图流程。

引擎必须允许不同 Agent 通过受控、强类型动作完成：

1. 选择图形 Profile 并绑定数据字段；
2. 创建高质量默认图；
3. 修改标题、坐标轴、系列样式、图例、图形专属参数和注释；
4. 批量执行、部分失败保真、恢复执行和幂等重放；
5. 导出 Matplotlib PNG/SVG；
6. 导出包含原生数据表和原生图对象、可在 Origin 中继续编辑的 OPJU。

Origin 的官方模板是 Origin 默认视觉的事实来源。Agent 只修改公开参数，不负责重建模板内每个对象。

## 2. 现有代码的取舍

### 2.1 保留能力和基础设施

- 安全文件导入、表格识别和多工作表身份；
- 不可变 SourceDataset、字段快照、单位、来源坐标和质量摘要；
- 项目目录、CAS、SQLite 单写者、项目打包和重启恢复；
- 模型 Provider、凭据边界、ProjectContext、TaskPlan、确认、任务事件、取消、部分失败和恢复语义；
- Electron 安全壳、资源授权、预览和导出对话框；
- 确定性固定计算，但其输入输出必须改接新数据视图。

保留的是这些产品能力，不承诺保留其当前类名、数据库表或调用路径。

### 2.2 必须重写的接线

- 内置 Agent 的绘图决策：从生成 PlotSpec 改为调用公开 Engine Action；
- 绘图存储：从序列化 PlotSpec 改为保存 PlotDocument 与动作日志；
- Desktop Core 的 create/patch/render/export 路径；
- 绘图准备中所有 PlotSpec 专属对象；
- 前端和 RPC 中所有直接暴露旧 PlotSpec/Patch 的契约。

### 2.3 必须删除的旧绘图体系

- PlotSpec 作为渲染权威；
- resolver / ResolvedPlot / ResolvedRenderPlan；
- Origin plan compiler 和旧 Origin renderer；
- 统一 Matplotlib renderer 及按旧结构单元组合最终图元的路径；
- 为旧路径冻结的视觉资格、兼容分支和生成脚本。

旧体系只有在新纵向切片接管生产路径后才能物理删除，但不得再新增功能或修视觉问题。

## 3. 新的稳定边界

### 3.1 EngineDataView

数据层把指定不可变数据版本物化为有界、矩形的数据视图：

- 数据版本与内容哈希；
- 稳定字段 ID、用户可读名称、逻辑类型和单位；
- 稳定行 ID 和按行对齐的列值。

数据层负责解析、来源、缺失值和受控计算；renderer 不读取导入器内部对象，也不自行改变数据。

### 3.2 PlotDocument

PlotDocument 只保存：

- 图对象 ID 与线性版本；
- Profile ID；
- 不可变数据引用；
- 语义字段绑定；
- 已应用动作 ID。

它不是场景图，不保存 Origin 图层、Matplotlib Artist 或模板内部对象。

### 3.3 Public Engine Actions

顶层动作固定为小而稳定的集合：

- `create_plot`
- `bind_fields`
- `set_title`
- `set_axis`
- `set_series_style`
- `set_legend`
- `set_chart_parameter`
- `add_annotation`
- `export_plot`

每个 Profile 声明自己支持的动作、字段角色和参数。参数不在能力表内时，本地校验必须在调用 renderer 前拒绝。

### 3.4 Backend Profile

同一个公开 Profile 对应两个独立后端实现：

- **Origin Profile**：加载构建固定的官方模板，写入数据列与 designation，调用模板自身的动态行为，只对公开动作做最小原生修改并读回验证；
- **Matplotlib Profile**：每图独立 renderer，可共享字体、色板、边距和导出工具，但不经过旧统一 resolver。

两端不要求内部结构相同，只要求共同公开动作、数据语义和用户可见结果一致。

## 4. 内置 Agent 的位置

仓库内置 Agent 是新引擎的一个客户端，不是引擎的组成部分。它继续负责：

- 理解用户目标和项目上下文；
- 解析跨轮次作用对象；
- 生成可审查的任务计划；
- 选择并填写公开 Engine Action；
- 在确认后执行，记录部分成功并恢复未完成项。

它不得输出 Origin 脚本、Matplotlib 代码、模板对象 ID 或任意未声明参数。其它 Agent 可以使用同一动作 Schema 和能力目录接入。

## 5. 重写顺序

1. 冻结 PlotDocument、EngineDataView、公共动作、Profile 与后端端口；
2. 建立新动作日志和版本存储，不复用 PlotSpec JSON 表；
3. 选四个不同模板家族做新纵向切片，接通数据、动作、Matplotlib、Origin 和读回；
4. 将内置 Agent 与 Desktop Core 改接新服务；
5. 按图迁移其余正式 Profile；
6. 新路径覆盖生产入口后，物理删除旧绘图编译体系及绑定测试；
7. 重新执行动态数据、机械修改读回、视觉、Agent 任务、重启恢复和黑盒资格。

迁移期间禁止用旧 renderer 兜底冒充新 Profile 成功。

## 6. 验收原则

- **默认正确性**：Origin 默认态来自指定官方模板；Matplotlib 默认态按独立 Profile 验收；
- **动态数据**：行数、系列数、类别、范围和缺失值变化不破坏数据语义；
- **动作读回**：声明开放的动作在两端执行后可机械读回；
- **Origin 原生性**：OPJU 重开后数据表、图层、坐标轴、系列、图例和注释可继续人工编辑；
- **Agent 可控性**：未开放参数拒绝，确认前无副作用，部分失败不重复成功项；
- **独立接入**：不使用内置 Agent，也能通过公开 Schema 创建和编辑图；
- **无旧路径**：生产代码、运行时依赖和测试清单中不存在旧 PlotSpec/resolver/plan renderer 兜底。

视觉审查位于每个 Profile 完成动态与机械读回之后、发布资格之前。机械通过不能代替人工视觉签名。

## 7. 当前迁移证据

截至本分支当前实现，新架构已经完成十六类代码级纵向切片：

| Profile | 数据语义 | Matplotlib | Origin 官方模板 | 原生结构 |
|---|---|---|---|---|
| K01 | `x / y` | 独立折线 renderer | `LINE.otpu` | worksheet + 1 条原生线 |
| K02 | `x / y` | 独立线点 renderer | `LINESYMB.otpu` | worksheet + 1 条原生复合线点系列 |
| K03 | `x / y / group?` | 独立动态分组散点 renderer | `SCATTER.OTP` | 每个分组一对 X/Y 列和一条原生散点 Plot |
| K06 | `x / center / x_error / y_error` | 独立双向误差棒 renderer | `ERRBAR.otpu` | worksheet + 原生 X/Y 误差列与中心点 |
| K07 | `x / center / lower / upper` | 独立误差带 renderer | `ERRORBAND.otp` | worksheet + 中心线、下界和上界原生 Plot |
| K08 | `category / value` | 独立柱图 renderer | `COLUMN.otpu` | worksheet + 1 组原生柱 |
| K09 | `category / group / value` | 独立动态分组柱 renderer | `COLUMN.otpu` | worksheet + 动态原生分组柱；柱宽只按组数受控调整 |
| K10 | `category / component / value` | 独立堆积柱 renderer | `STACKCOLUMN.otp` | worksheet + 模板定义的动态原生堆积系列 |
| K11 | `category / component / value` | 独立百分比堆积 renderer | `StackColP.otp` | worksheet 写入单次预计算百分比 + 模板原生堆积系列 |
| K12 | `value / group?` | 独立确定性条带 renderer | `ColumnScatter.otp` | 每组一列原始观测 + 模板原生 Column Scatter plot |
| K13 | `value / group?` | 独立 Tukey 箱线 renderer | `BOX.OTP` | 每组一列原始观测 + 模板原生 box plot |
| K14 | `value / group?` | 独立小提琴 renderer | `Violin.otpu` | 每组一列原始观测 + 模板原生 violin plot；禁止线/填充模拟轮廓 |
| K18 | `x / y` | 独立面积图 renderer | `AREA.otpu` | worksheet + 官方模板原生面积 Plot |
| K20 | `row / column / value` | 独立热图 renderer | `Heat_Map.otpu` | matrixbook + 1 个原生 matrix plot |
| X02 | `x / y` | 独立底轴垂线 renderer | `DROPLINE.OTP` | worksheet + 官方模板原生 drop-line Plot |
| X23 | `x / left / right` | 独立双 Y renderer | `DOUBLEY.OTP` | worksheet + 2 个模板图层，各 1 条原生线 |

十六个切片均只消费 `EngineDataView`、`PlotDocument` 和公开 Engine Action，不导入旧
`PlotSpec`、resolver、`ResolvedPlot` 或 Origin plan。K01/K02/K03/K06/K07/K08/K09/K10/K11/K12/K13/K14/K18/K20/X02/X23 已有独立渲染、
模板哈希、对象结构和修改读回门禁；真实 Origin fresh-reopen 与人工视觉签名仍须在
不占用用户 Origin 实例的受控资格批次中执行，未完成前不得声称这些 Profile 已发布。
