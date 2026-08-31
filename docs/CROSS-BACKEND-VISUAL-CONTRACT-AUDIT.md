# 34 模板跨后端视觉契约审计

本账本不是既有视觉冒烟页的改名。旧审计只能证明代表性产物曾经生成，
不能证明 Catalog 中每个公开参数都在 Matplotlib、Origin、保存和 fresh-reopen 后表达一致。

审计范围只来自三类权威输入：

1. `schemas/engine-profile-catalog.json` 中该模板已经公开的参数；
2. 同一份零编辑数据在 Matplotlib 与 Origin 中实际生成的默认外观；
3. 真实论文复刻明确要求、但 Catalog 尚未声明的参数。

`complete` 仅表示该模板的每个 Catalog 参数都有显式裁决，零编辑默认外观也已经裁决。
`partial`、`not_started` 不能用于宣称跨后端视觉一致。详细参数、证据、真实论文要求和边界见
[`visual-contracts/audit-ledger.json`](./visual-contracts/audit-ledger.json)。

| 模板 | Catalog 名称 | 已声明参数 | 已审参数 | 零编辑默认 | 总状态 |
|---|---|---:|---:|---|---|
| K01 | Line | 73 | 2 | passed | partial |
| K02 | Line and symbol | 77 | 0 | pending | not_started |
| K03 | Scatter | 75 | 0 | pending | not_started |
| K04 | Bubble and color-mapped scatter | 91 | 0 | pending | not_started |
| K06 | Point estimate and error bar | 79 | 11 | failed | partial |
| K07 | Error ribbon | 77 | 10 | allowed_difference | partial |
| K08 | Column | 84 | 0 | pending | not_started |
| K09 | Grouped column | 82 | 4 | passed | partial |
| K10 | Stacked column | 84 | 0 | pending | not_started |
| K11 | 100% stacked column | 84 | 0 | pending | not_started |
| K12 | Strip plot | 75 | 0 | pending | not_started |
| K13 | Box plot | 87 | 0 | pending | not_started |
| K14 | Violin plot | 77 | 10 | passed | partial |
| K15 | Histogram | 74 | 0 | pending | not_started |
| K18 | Area | 77 | 0 | pending | not_started |
| K19 | Time series | 73 | 0 | pending | not_started |
| K20 | Heatmap | 62 | 0 | pending | not_started |
| K21 | Correlation matrix | 63 | 0 | pending | not_started |
| K22 | Filled contour | 71 | 8 | failed | partial |
| K24 | Faceted plot | 50 | 0 | pending | not_started |
| S34 | Nyquist plot | 77 | 0 | pending | not_started |
| S61 | Confusion matrix | 63 | 0 | pending | not_started |
| X02 | Drop line | 77 | 0 | pending | not_started |
| X03 | Lollipop | 77 | 0 | pending | not_started |
| X05 | Beeswarm | 75 | 0 | pending | not_started |
| X09 | Floating column | 84 | 7 | allowed_difference | partial |
| X13 | Population pyramid | 83 | 0 | pending | not_started |
| X23 | Dual-Y line | 77 | 9 | failed | partial |
| X24 | Pareto | 85 | 0 | pending | not_started |
| X35 | Dual-Y column | 84 | 12 | failed | partial |
| X36 | Dual-Y column and line | 92 | 19 | failed | partial |
| X38 | Y-offset stacked line | 73 | 0 | pending | not_started |
| X39 | Line series | 77 | 0 | pending | not_started |
| X40 | Before and after | 78 | 14 | allowed_difference | partial |
