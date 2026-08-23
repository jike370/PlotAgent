# PlotAgent 发布覆盖账本

> 本文件由 `scripts/build_release_coverage_ledger.py` 生成。它只证明测试归属完整，
> 不证明候选已经通过；实际结果必须来自同一冻结 HEAD 的运行产物。

## 1. 发布规则

- 34 个公开图类必须各自具备数据合同、离线矩阵、Origin fresh-reopen、公共编辑、历史恢复、三格式导出和正式 UI case。
- 任务状态、数据输入、多来源、UI、故障恢复、导出、性能、打包、黑盒和 SEQ-70 必须各有可执行归属。
- 发布时任何必测项为 `FAIL`、`BLOCKED` 或 `UNVERIFIED` 都是 `NO-GO`。
- JSON 版本是机器事实源；本页只提供审阅视图。

## 2. 34 图逐项归属

| ID | 图类 | 离线 | Origin | 公共编辑 | 撤销/重做/重启 | 导出 | Windows UI |
|---|---|---|---|---|---|---|---|
| K01 | 折线图 | 9 MatrixKeys | ORIGIN-K01-REPRESENTATIVE-FRESH | EDIT-K01-* | RECOVERY-K01-UNDO-REDO-RESTART | EXPORT-K01-PNG-SVG-OPJU | BB-CHART-K01 |
| K02 | 线+符号图 | 9 MatrixKeys | ORIGIN-K02-REPRESENTATIVE-FRESH | EDIT-K02-* | RECOVERY-K02-UNDO-REDO-RESTART | EXPORT-K02-PNG-SVG-OPJU | BB-CHART-K02 |
| K03 | 二维散点图 | 9 MatrixKeys | ORIGIN-K03-REPRESENTATIVE-FRESH | EDIT-K03-* | RECOVERY-K03-UNDO-REDO-RESTART | EXPORT-K03-PNG-SVG-OPJU | BB-CHART-K03 |
| K04 | 索引大小气泡与颜色映射图 | 9 MatrixKeys | ORIGIN-K04-REPRESENTATIVE-FRESH | EDIT-K04-* | RECOVERY-K04-UNDO-REDO-RESTART | EXPORT-K04-PNG-SVG-OPJU | BB-CHART-K04 |
| K06 | XY双向误差棒图 | 9 MatrixKeys | ORIGIN-K06-REPRESENTATIVE-FRESH | EDIT-K06-* | RECOVERY-K06-UNDO-REDO-RESTART | EXPORT-K06-PNG-SVG-OPJU | BB-CHART-K06 |
| K07 | 误差带图 | 9 MatrixKeys | ORIGIN-K07-REPRESENTATIVE-FRESH | EDIT-K07-* | RECOVERY-K07-UNDO-REDO-RESTART | EXPORT-K07-PNG-SVG-OPJU | BB-CHART-K07 |
| K08 | 柱状图 | 9 MatrixKeys | ORIGIN-K08-REPRESENTATIVE-FRESH | EDIT-K08-* | RECOVERY-K08-UNDO-REDO-RESTART | EXPORT-K08-PNG-SVG-OPJU | BB-CHART-K08 |
| K09 | 分组柱状图（索引数据） | 9 MatrixKeys | ORIGIN-K09-REPRESENTATIVE-FRESH | EDIT-K09-* | RECOVERY-K09-UNDO-REDO-RESTART | EXPORT-K09-PNG-SVG-OPJU | BB-CHART-K09 |
| K10 | 堆积柱状图 | 9 MatrixKeys | ORIGIN-K10-REPRESENTATIVE-FRESH | EDIT-K10-* | RECOVERY-K10-UNDO-REDO-RESTART | EXPORT-K10-PNG-SVG-OPJU | BB-CHART-K10 |
| K11 | 100%堆积柱状图 | 9 MatrixKeys | ORIGIN-K11-REPRESENTATIVE-FRESH | EDIT-K11-* | RECOVERY-K11-UNDO-REDO-RESTART | EXPORT-K11-PNG-SVG-OPJU | BB-CHART-K11 |
| K12 | 列散点图（条带图） | 9 MatrixKeys | ORIGIN-K12-REPRESENTATIVE-FRESH | EDIT-K12-* | RECOVERY-K12-UNDO-REDO-RESTART | EXPORT-K12-PNG-SVG-OPJU | BB-CHART-K12 |
| K13 | 箱线图 | 9 MatrixKeys | ORIGIN-K13-REPRESENTATIVE-FRESH | EDIT-K13-* | RECOVERY-K13-UNDO-REDO-RESTART | EXPORT-K13-PNG-SVG-OPJU | BB-CHART-K13 |
| K14 | 小提琴图 | 9 MatrixKeys | ORIGIN-K14-REPRESENTATIVE-FRESH | EDIT-K14-* | RECOVERY-K14-UNDO-REDO-RESTART | EXPORT-K14-PNG-SVG-OPJU | BB-CHART-K14 |
| K15 | 直方图 | 9 MatrixKeys | ORIGIN-K15-REPRESENTATIVE-FRESH | EDIT-K15-* | RECOVERY-K15-UNDO-REDO-RESTART | EXPORT-K15-PNG-SVG-OPJU | BB-CHART-K15 |
| K18 | 面积图 | 9 MatrixKeys | ORIGIN-K18-REPRESENTATIVE-FRESH | EDIT-K18-* | RECOVERY-K18-UNDO-REDO-RESTART | EXPORT-K18-PNG-SVG-OPJU | BB-CHART-K18 |
| K19 | 日期时间折线图 | 9 MatrixKeys | ORIGIN-K19-REPRESENTATIVE-FRESH | EDIT-K19-* | RECOVERY-K19-UNDO-REDO-RESTART | EXPORT-K19-PNG-SVG-OPJU | BB-CHART-K19 |
| K20 | 热图 | 9 MatrixKeys | ORIGIN-K20-REPRESENTATIVE-FRESH | EDIT-K20-* | RECOVERY-K20-UNDO-REDO-RESTART | EXPORT-K20-PNG-SVG-OPJU | BB-CHART-K20 |
| K21 | 带标签热图（给定相关矩阵） | 9 MatrixKeys | ORIGIN-K21-REPRESENTATIVE-FRESH | EDIT-K21-* | RECOVERY-K21-UNDO-REDO-RESTART | EXPORT-K21-PNG-SVG-OPJU | BB-CHART-K21 |
| K22 | 填色等高线图 | 9 MatrixKeys | ORIGIN-K22-REPRESENTATIVE-FRESH | EDIT-K22-* | RECOVERY-K22-UNDO-REDO-RESTART | EXPORT-K22-PNG-SVG-OPJU | BB-CHART-K22 |
| K24 | Trellis分面图 | 9 MatrixKeys | ORIGIN-K24-REPRESENTATIVE-FRESH | EDIT-K24-* | RECOVERY-K24-UNDO-REDO-RESTART | EXPORT-K24-PNG-SVG-OPJU | BB-CHART-K24 |
| S34 | Nyquist图 | 9 MatrixKeys | ORIGIN-S34-REPRESENTATIVE-FRESH | EDIT-S34-* | RECOVERY-S34-UNDO-REDO-RESTART | EXPORT-S34-PNG-SVG-OPJU | BB-CHART-S34 |
| S61 | 带标签热图（混淆矩阵语义） | 9 MatrixKeys | ORIGIN-S61-REPRESENTATIVE-FRESH | EDIT-S61-* | RECOVERY-S61-UNDO-REDO-RESTART | EXPORT-S61-PNG-SVG-OPJU | BB-CHART-S61 |
| X02 | 垂线图 | 9 MatrixKeys | ORIGIN-X02-REPRESENTATIVE-FRESH | EDIT-X02-* | RECOVERY-X02-UNDO-REDO-RESTART | EXPORT-X02-PNG-SVG-OPJU | BB-CHART-X02 |
| X03 | 棒棒糖图 | 9 MatrixKeys | ORIGIN-X03-REPRESENTATIVE-FRESH | EDIT-X03-* | RECOVERY-X03-UNDO-REDO-RESTART | EXPORT-X03-PNG-SVG-OPJU | BB-CHART-X03 |
| X05 | 蜂群图 | 9 MatrixKeys | ORIGIN-X05-REPRESENTATIVE-FRESH | EDIT-X05-* | RECOVERY-X05-UNDO-REDO-RESTART | EXPORT-X05-PNG-SVG-OPJU | BB-CHART-X05 |
| X09 | 浮动柱状图 | 9 MatrixKeys | ORIGIN-X09-REPRESENTATIVE-FRESH | EDIT-X09-* | RECOVERY-X09-UNDO-REDO-RESTART | EXPORT-X09-PNG-SVG-OPJU | BB-CHART-X09 |
| X13 | 人口金字塔（龙卷风/蝴蝶图） | 9 MatrixKeys | ORIGIN-X13-REPRESENTATIVE-FRESH | EDIT-X13-* | RECOVERY-X13-UNDO-REDO-RESTART | EXPORT-X13-PNG-SVG-OPJU | BB-CHART-X13 |
| X23 | 双Y轴Y-Y图 | 9 MatrixKeys | ORIGIN-X23-REPRESENTATIVE-FRESH | EDIT-X23-* | RECOVERY-X23-UNDO-REDO-RESTART | EXPORT-X23-PNG-SVG-OPJU | BB-CHART-X23 |
| X24 | 帕累托图（分箱数据） | 9 MatrixKeys | ORIGIN-X24-REPRESENTATIVE-FRESH | EDIT-X24-* | RECOVERY-X24-UNDO-REDO-RESTART | EXPORT-X24-PNG-SVG-OPJU | BB-CHART-X24 |
| X35 | 双Y轴柱状图 | 9 MatrixKeys | ORIGIN-X35-REPRESENTATIVE-FRESH | EDIT-X35-* | RECOVERY-X35-UNDO-REDO-RESTART | EXPORT-X35-PNG-SVG-OPJU | BB-CHART-X35 |
| X36 | 双Y轴柱线图 | 9 MatrixKeys | ORIGIN-X36-REPRESENTATIVE-FRESH | EDIT-X36-* | RECOVERY-X36-UNDO-REDO-RESTART | EXPORT-X36-PNG-SVG-OPJU | BB-CHART-X36 |
| X38 | Y偏移堆叠线图 | 9 MatrixKeys | ORIGIN-X38-REPRESENTATIVE-FRESH | EDIT-X38-* | RECOVERY-X38-UNDO-REDO-RESTART | EXPORT-X38-PNG-SVG-OPJU | BB-CHART-X38 |
| X39 | 线条序列图 | 9 MatrixKeys | ORIGIN-X39-REPRESENTATIVE-FRESH | EDIT-X39-* | RECOVERY-X39-UNDO-REDO-RESTART | EXPORT-X39-PNG-SVG-OPJU | BB-CHART-X39 |
| X40 | 前后对比图 | 9 MatrixKeys | ORIGIN-X40-REPRESENTATIVE-FRESH | EDIT-X40-* | RECOVERY-X40-UNDO-REDO-RESTART | EXPORT-X40-PNG-SVG-OPJU | BB-CHART-X40 |

## 3. 跨图类产品域归属

| 域 | 范围 | 冻结 case | 可执行来源 | 候选证据 |
|---|---|---|---|---|
| TASK-STATE | 任务状态与副作用 | TASK-BATCH-01、TASK-BATCH-02、TASK-BATCH-03、TASK-BATCH-04、TASK-BATCH-05、TASK-BATCH-06、TASK-LEGACY-PLAN-SCHEMA-COMPAT、TASK-DATA-UPDATE-UNDO-REDO | `docs/PLOTAGENT-AGENT-TASK-STATE-MATRIX.md`<br>`scripts/run_release_operational_matrix.py`<br>`src/main/agent/agent-foundation-runtime.test.ts`<br>`src/main/agent/task-pump.test.ts`<br>`src/renderer/src/components/TaskDrawer.test.tsx`<br>`src/renderer/src/data/plotHistory.test.ts`<br>`src/renderer/src/data/productState.test.ts`<br>`tests/contracts/test_agent_tasks.py`<br>`tests/desktop_core/test_agent_foundation.py`<br>`tests/desktop_core/test_application.py`<br>`tests/tasking/test_task_ledger.py` | UNVERIFIED |
| DATA-INPUT | 导入、类型、单位与数据边界 | IMPORT-CSV-100K、IMPORT-XLSX-MULTISHEET、IMPORT-TXT-INSTRUMENT、IMPORT-TXT-MULTIBLOCK、LARGE-K01-100K-RENDER、MISSING-K01-GAPS、MISSING-K20-HEATMAP、EXTREME-K01-LINE、EXTREME-K08-COLUMN、DYNAMIC-X03-2-4-2、DYNAMIC-X38-1-4-2、DYNAMIC-X39-2-5-2 | `scripts/run_release_data_stress_matrix.py`<br>`scripts/run_release_operational_matrix.py`<br>`tests/desktop_core/test_application.py`<br>`tests/engine/test_release_data_stress_matrix.py`<br>`tests/importing/test_goldens.py`<br>`tests/storage/test_project_storage.py`<br>`tests/workflows/test_data_ops.py` | UNVERIFIED |
| MULTI-SOURCE | 批量任务与多来源合并 | MULTI-BATCH-DIFFERENT-CHARTS、MULTI-ALIGN-ON-X、MULTI-CONCATENATE、MULTI-PARTIAL-REPAIR、MULTI-DERIVED-PLOT-CONTEXT-RECOVERY、MULTI-CONFIRMATION-PROVENANCE、MULTI-CONFIRMATION-SAMPLES-ALL-SOURCES | `scripts/run_release_operational_matrix.py`<br>`src/renderer/src/App.test.tsx`<br>`tests/desktop_core/test_application.py`<br>`tests/workflows/test_data_ops.py`<br>`tests/workflows/test_workflow_contracts.py` | UNVERIFIED |
| UI | 正式桌面交互 | RC-UI-01、RC-UI-02、RC-UI-03、RC-UI-04、RC-UI-05、RC-UI-06、RC-UI-07 | `src/main/ipc/desktop-ipc.test.ts`<br>`src/renderer/src/App.test.tsx`<br>`src/renderer/src/components/ChartLibrary.test.tsx`<br>`src/renderer/src/components/FocusEditor.test.tsx`<br>`src/renderer/src/components/TaskDrawer.test.tsx`<br>`src/renderer/src/styles.test.ts` | UNVERIFIED |
| FAULT-RECOVERY | 模型、Core、Origin、存储与锁故障 | FAULT-TIMEOUT、FAULT-RATE-LIMIT、FAULT-OFFLINE、FAULT-PROXY、FAULT-BAD-PROVIDER-JSON、FAULT-BAD-CORE-JSON、FAULT-CANCEL、FAULT-PARTIAL、FAULT-TRANSIENT-RETRY、FAULT-EXPLICIT-SAFE-RETRY、FAULT-UNRECOVERABLE、FAULT-UNSAFE-RETRY-REJECTED、FAULT-ATOMIC-DISK-WRITE、FAULT-CORE-CRASH-RECOVERY、FAULT-ORIGIN-UNAVAILABLE、FAULT-OPJU-EXPORT、FAULT-DISK-FULL、FAULT-DEAD-WRITER-LOCK、FAULT-LIVE-WRITER-LOCK | `scripts/run_release_fault_matrix.py`<br>`scripts/run_release_packaged_matrix.py`<br>`src/main/core/supervisor-state.test.ts`<br>`src/main/ipc/desktop-ipc.test.ts`<br>`tests/desktop_core/test_application.py`<br>`tests/engine/test_release_fault_matrix.py`<br>`tests/storage/test_project_storage.py` | UNVERIFIED |
| EXPORT | PNG、SVG、OPJU 与版本一致性 | EXPORT-34-PNG-SVG-OPJU、EXPORT-LATEST-VERSION、EXPORT-OPJU-NATIVE-FRESH、EXPORT-FAILURE-NO-SUCCESS、EXPORT-PROJECT-126 | `scripts/run_release_edit_matrix.py`<br>`scripts/run_release_matrix.py`<br>`scripts/run_release_origin_matrix.py`<br>`src/main/ipc/desktop-ipc.test.ts`<br>`src/renderer/src/App.test.tsx`<br>`tests/desktop_core/test_application.py`<br>`tests/engine/test_release_matrix.py` | UNVERIFIED |
| PERFORMANCE | 性能与资源边界 | LARGE-K01-100K-RENDER、IMPORT-CSV-100K | `scripts/run_release_data_stress_matrix.py`<br>`scripts/run_release_operational_matrix.py`<br>`tests/engine/test_release_data_stress_matrix.py`<br>`tests/engine/test_release_operational_matrix.py` | UNVERIFIED |
| PACKAGING | Windows 打包、隔离配置与安装产物 | PACKAGED-INTEGRITY、PACKAGED-ORIGIN-MISSING、PACKAGED-ORIGIN-WRONG-VERSION、PACKAGED-ORIGIN-SUPPORTED、PACKAGED-ELECTRON-ISOLATED-PROFILE | `scripts/run_release_packaged_matrix.py`<br>`tests/engine/test_release_packaged_matrix.py`<br>`tests/packaging/windows-release-tools.test.ps1` | UNVERIFIED |
| BLACKBOX | 完整 Windows 回归与探索性黑盒 | BB-FROZEN-REGRESSION、BB-EXPLORATORY | `docs/PLOTAGENT-RELEASE-COVERAGE-LEDGER.json`<br>`docs/PLOTAGENT-V3-BLACK-BOX-CAPABILITY.md` | UNVERIFIED |
| SEQ70 | 真实模型 24×3 语义评测 | SEQ70-24X3 | `scripts/run_seq70_workflow_eval.ts`<br>`tests/fixtures/seq70/workflow_tasks.json` | UNVERIFIED |

## 4. 产物关系

1. `run_release_matrix.py` 生成 306 个唯一 MatrixKey。
2. `run_release_origin_matrix.py` 在同一 HEAD 上关闭 34 个 representative OPJU 的 live/fresh 证据。
3. `run_release_edit_matrix.py` 逐能力执行 Matplotlib 与 Origin 编辑，并保存独立参数合同。
4. 数据、故障、运行与打包 runner 各自产生 `run-metadata.json`、CSV 和报告。
5. Windows 黑盒与 SEQ-70 只能在候选冻结后执行，不能替代上述确定性证据。
