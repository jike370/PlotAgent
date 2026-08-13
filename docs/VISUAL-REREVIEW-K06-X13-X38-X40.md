# K06 / X13 / X38 / X40 renderer 视觉复核

## 冻结范围

- Renderer 源提交：`e1f1febb3cb289c266d61b4de7cda47cf7c70c91`
- 审计入口：`D:\plotv3\build\visual-audit\renderer-rereview-4\index.html`
- 审计清单：`D:\plotv3\build\visual-audit\renderer-rereview-4\review-manifest.json`
- 审计状态：`PASS`
- 每张图均重新生成 Matplotlib 默认态、Matplotlib 代表编辑态、Origin 默认 OPJU、Origin 代表编辑 OPJU，并由新的 Origin 会话重开后导出 PNG。

## 逐图结论

| 图类 | 官方 Origin 路线 | 本轮重点 | 结论 |
|---|---|---|---|
| 双向误差棒图 | X Y Error / `ERRBAR.otpu` | X 误差使用原生 `-oxm/-oxp`，Y 误差使用 `-om/-op`；默认态和编辑态重开后均同时显示横、纵误差棒 | PASS |
| 人口金字塔图 | `Plot.ogs [PopulationPyramid]` / `PopulationPyramid.otpu` | 类别标签位于左右柱体中央接缝；隐藏外侧重复类别刻度；默认态和编辑态重开后保持 | PASS |
| Y 偏移堆叠线图 | `Plot.ogs [OffsetYs]` / `OffsetStackY.otp` | 使用官方 native offset 结构；默认图例规范化后完整显示，编辑态标题、图例和曲线无冲突 | PASS |
| 前后对比图 | `Plot.ogs [BeforeAfter]` / `BeforeAfter.otpu` | 保留 Subject 与 Group 身份；默认态 Before/After 颜色方向一致；代表编辑测试使用已证明稳定的 connector 样式，重开后标题与图例不重叠 | PASS |

## 机械门禁

- 4 图相关测试：`78 passed`
- `tests/engine`：`291 passed`
- Ruff：通过
- mypy：通过
- `git diff --check`：通过

本文件只确认上述四张图在该冻结提交上的 renderer 视觉与原生重开结果，不外推为其他图类或整个产品的视觉签名。
