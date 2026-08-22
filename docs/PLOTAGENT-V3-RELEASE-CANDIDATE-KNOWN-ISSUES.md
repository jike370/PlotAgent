# PlotAgent 发布候选已知问题

> 本文件只保留当前仍未关闭的问题。已经实现但待回归的事项进入测试矩阵，不继续占用 known issues；历史问题从 Git 追溯。

RC-UI-001 与 RC-UI-002 已在 `a99a416` 后通过正式 Windows Electron 定向复测关闭；关闭证据记录在《PlotAgent 产品测试覆盖审计》第 8 节。

当前无已知产品开放问题。

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
