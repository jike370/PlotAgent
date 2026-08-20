# PlotAgent v3 Beta 性能测试与发布门禁

> 当前范围：34张单图、Pi Agent runtime、Windows Electron、PNG/SVG与原生可编辑 OPJU。不支持组合图。

施工与测试必须先按[施工、测试与发布路线](./IMPLEMENTATION-PLAN.md)完成组件、功能、视觉、确定性门禁和定向 UI，再冻结候选执行本文件的完整黑盒与 SEQ-70。

## 1. 发布原则

- 工程测试、机械读回、视觉、正式UI黑盒和目标用户验证分开记账。
- 未执行为 `UNVERIFIED`，环境阻断为 `BLOCKED`，观察到产品错误为 `FAIL`。
- 任何关键 `FAIL`、`BLOCKED` 或应测项 `UNVERIFIED` 都不能写“完整通过”。
- 历史31/35/38/43/45图证据不能自动继承。

## 2. 唯一平台基线

- Windows 11 x64；
- 正式 Electron 入口；
- 打包版 Python Core；
- 当前声明的单一 Origin exact version；
- 同一提交、干净工作树、冻结输入和独立输出目录；
- Pi/provider状态与本地 Core 状态分开记录。

## 3. 34图矩阵

每图三类 fixture：minimal、representative、edge/error。每个 fixture 覆盖 PNG、SVG、OPJU 或明确稳定错误，共 `34 × 3 × 3 = 306` 个逻辑 MatrixKey。

- PNG/SVG：306个逻辑产物/错误路径离线覆盖；
- OPJU：34个 representative 在声明的 Origin 版本 live+fresh-reopen；minimal/edge 由同一合同、validator和稳定错误覆盖；
- 当前 renderer 变化后，K06、X13、X38、X40必须重新生成视觉和原生产物证据。

冻结夹具位于 `scripts/release_matrix_cases.py`，离线阶段执行命令为：

```powershell
.venv\Scripts\python.exe scripts\run_release_matrix.py
```

离线阶段必须得到306个唯一MatrixKey、68份PNG、68份SVG；预期只有34个
`representative:opju` 保持 `UNVERIFIED`，等待后续真实Origin live+fresh阶段关闭。
离线报告不得把这34项写成PASS，也不得用历史OPJU替代当前提交的原生证据。

真实Origin阶段以离线目录为输入，逐图执行“生成→新进程编辑→另一新进程复核”：

```powershell
.venv\Scripts\python.exe scripts\run_release_origin_matrix.py `
  --offline build\release-matrix\offline-<commit>-<timestamp>
```

只有34项均生成非零OPJU，且编辑后由独立Origin进程重开、机械读回并导出fresh
PNG，才可把 `representative:opju` 从 `UNVERIFIED` 升为 `PASS`。

公共编辑阶段以该Origin基线为输入，对34图分别顺序执行标题、轴、系列以及该图
支持的图例编辑；Matplotlib必须逐版本发布，Origin必须每个动作形成独立线性版本，
并由另一个Origin进程复核最终版本：

```powershell
.venv\Scripts\python.exe scripts\run_release_edit_matrix.py `
  --origin-baseline build\release-matrix\origin-<commit>-<timestamp>
```

两个后端必须独立记账，不能以一个后端的PASS遮蔽另一个后端的FAIL。Origin的原生
存储分辨率也必须显式解释：线宽和边框宽度允许半个0.1 pt存储步长，单列图例的
`ncols=0`自动纵向布局规范化为公共合同的一列；其他数值与多列图例仍按合同精确
读回。

正式图清单以 [Origin 官方模板映射](./ORIGIN-OFFICIAL-TEMPLATE-MAPPING.md) 为准。K16、K25、S01、S21及其他删除图只验证不可发现与 `CHART_TYPE_REMOVED`，不计入34图通过数。

## 4. 图形门禁

每图至少验证：

1. 字段角色、数据类型、可重复系列和错误输入；
2. 默认、代表性编辑和动态数据；
3. Matplotlib画布与PNG/SVG；
4. Origin官方模板/菜单/X-Function provenance；
5. worksheet/matrix、plot/layer、数据源和Agent编辑读回；
6. 全新Origin会话重开；
7. 用户视觉签名。

## 5. Agent门禁

- Pi只提交结构化decision，Core拒绝越权或不合法计划；
- 没有数据或图类时追问，不擅自选图；
- 字段绑定、目标对象和版本正确；
- 确认前无副作用；
- 运行时显示真实阶段，停止/超时不产生半版本；
- 部分失败保留成功项且只重试失败项；
- 撤销/重做、陈旧计划拒绝和重启恢复正确；
- 固定SEQ-70任务达到冻结阈值后才可声明Agent资格。

## 6. 桌面与导出门禁

- 导入、文件/工作表身份、连续导入和歧义处理；
- 34图逐项创建，重点复测K06/K07/K18/K19/K21/X05/X13/X38/X40；
- 批量、聚焦编辑、撤销/重做和项目重启；
- PNG/SVG独立打开；
- OPJU非零、Origin可打开、修改数据/样式后保存并重开持久；
- 导出完成给出明确成功提示与路径；
- Origin不可用时在保存对话框前阻断并给诊断；
- K25与组合图入口不可发现，旧引用稳定报墓碑。

## 7. 性能阈值

冻结测试机上记录而不是估算：

- 应用启动与Core ready；
- 10万行导入与首图预览；
- 普通Agent请求median/p95/max；
- PNG/SVG导出；
- Origin预检、构建、保存和fresh-reopen；
- 批量任务吞吐、内存峰值与取消延迟。

具体数值随Beta硬件基线冻结在run metadata，不在实现代码中硬编码营销承诺。

## 8. 安全与可追溯

- local_only零远程出站；
- online provider只接收经批准的最小上下文，不上传原文件；
- 宏、外链、公式执行、任意Shell/Python和未授权路径被阻止；
- manifest固定source、app、model、prompt、dependency、Origin、fixture和artifact hashes；
- 原始输入测试前后hash不变。

## 9. 发布检查单

发布包必须包含：

1. 干净提交与构建hash；
2. Python/TypeScript/打包门禁；
3. 34图306 MatrixKey coverage；
4. 34份Origin representative live+fresh报告；
5. 当前视觉签名；
6. 正式Electron黑盒报告与原始截图/导出；
7. Agent qualification报告；
8. 导入golden、编辑capability、删除项墓碑和安全报告；
9. known issues与未验证清单。

满足以上条件且关键项为零FAIL、零BLOCKED、零UNVERIFIED后，才可进入邀请制Beta。
