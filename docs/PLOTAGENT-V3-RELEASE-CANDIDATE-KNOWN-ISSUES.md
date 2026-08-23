# PlotAgent 发布候选已知问题

> 本文件只保留当前仍未关闭的问题。已经实现但待回归的事项进入测试矩阵，不继续占用 known issues；历史问题从 Git 追溯。

RC-UI-001 与 RC-UI-002 已在 `a99a416` 后通过正式 Windows Electron 定向复测关闭；关闭证据记录在《PlotAgent 产品测试覆盖审计》第 8 节。

RC-UI-PROFILE-PROJECTION 与 RC-PACKAGING-ENV 已完成能力族级修复并移入发布覆盖账本：
前者已在正式打包 Electron 覆盖显式图类、同类批量、异构批量、拒绝恢复和重启恢复；后者已在
候选 `8903c54` 发布脚本中完成 package 入口和直接 PowerShell 入口复核。

## 当前开放问题（2026-08-23 候选定向 UI）

### RC-PACK-FROZEN-BACKENDS

- `8903c54` 打包侧车执行 X38 轴范围编辑时缺少 `matplotlib.backends.backend_svg`。
- 原因：Matplotlib 按格式动态解析 backend，而 PyInstaller spec 未声明产品公开的 PNG/SVG backend。
- 修复：spec 显式包含 `backend_agg` 与 `backend_svg`；发布包矩阵新增真实 K01 渲染和 PNG/SVG 哈希验证。
- 状态：候选 `e434e41` 的扩展打包矩阵已用冻结 Core 真实生成并校验 PNG/SVG，`PACKAGED-CORE-RENDER-EXPORT` 为 PASS；X38 正式 UI 轴范围链路仍待定向复测。

### RC-PACK-FROZEN-ORIGIN-WORKER

- `8903c54` 项目 126 OPJU 导出超过 60 秒、无文件，停止后 Core 超时，应用无法正常退出。
- 原因：冻结 Core 中 `sys.executable -m plotagent...worker` 实际递归启动另一 Core，不会进入 Origin worker。
- 修复：冻结入口新增唯一 `--origin-worker REQUEST RESPONSE` 模式，源运行时仍使用 Python `-m`；发布包矩阵新增冻结 worker 路由门禁。
- 状态：候选 `e434e41` 的冻结 worker 入口门禁 PASS，34 图 Origin fresh-reopen 为 `306/306 PASS`；项目 126 正式打包 UI 的真实 OPJU 导出、成功回执和 Origin 新会话编辑仍待复测。

### RC-UI-PLAN-REVISION-ENTRY

- “修改绑定”曾先拒绝计划，再尝试打开只适用于“无现有图”的旧手动映射卡；有现有图时用户只看到计划被拒绝。
- 修复：保持原计划处于待确认态，提示用户在 Composer 中描述绑定调整，由同一耐久任务生成修订计划并重新确认。
- 状态：App 完整矩阵现为 `89 PASS / 0 FAIL`，等待新包正式 UI 复测。

RC-AGENT-PLOT-CONTEXT 与 RC-UI-MULTISOURCE-PROVENANCE 已完成族级修复并移入发布覆盖账本：
选中派生图时会恢复全部不可变来源、数据操作与字段绑定；确认卡按原始来源展示角色证据和
真实样本。确定性回归与正式 Electron 定向验证均已通过，候选冻结后仍须按账本重跑。

## 当前测试证据缺口

### RC-RUNTIME-STOP-EVIDENCE

确认前取消已经在正式 Electron 中通过，但真实模型约 3 秒内完成规划，没有稳定取得“运行中
停止”的有效点击证据。该项保持 `UNVERIFIED`，后续用确定性慢响应/可中断 provider 夹具验证
停止、迟到响应丢弃、输入恢复和重新提交；不能用确认前拒绝替代运行中停止。

详细探索证据见
`build/pre-release-exploration/619043c/REPORT.md`。
