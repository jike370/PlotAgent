# PlotAgent v3 实施计划

## 已完成

1. 数据身份、字段类型、受控准备、项目版本和任务事务落入本地 Core。
2. 34 张正式单图完成独立 Matplotlib renderer 与 Origin 官方模板绑定器。
3. 旧统一绘图编译链退出生产路径。
4. K16、K25、S01、S21 及此前删除图类只保留迁移墓碑。
5. Pi 接管通用 Agent 循环；Core 保持 capability、对象、确认、版本与执行权威。
6. 黑盒暴露的 K06/K07/K18/K19/K21/X05/X13/X38/X40 合同与 renderer 问题已按当前设计修正。

## 当前节点

1. 在当前提交上生成 34 图统一视觉审查页，重点重测双向误差棒、人口金字塔、Y 偏移堆叠线图和前后对比图。
2. 按 [黑盒交接文档](./PLOTAGENT-V3-BLACK-BOX-ACCEPTANCE-HANDOFF.md) 继续正式 Windows Electron 黑盒；不得用单测代替 UI 观察。
3. 完成 Agent 确认卡、真实阶段反馈、撤销/重做、批量恢复、重启、PNG/SVG/OPJU 与导出成功提示证据。
4. 运行完整 Python、TypeScript、打包与发布门禁。

## 不在范围

- 组合图、自由画布和任意布局；
- Agent 自动选图；
- 任意统计分析、拟合、代码执行和开放式数据清洗；
- 用近似图或旧 renderer 兼容已删除图类。
