# 真实科研任务升级：第一阶段完成审计

审计日期：2026-08-30
审计对象：`REAL-WORLD-RESEARCH-FIGURE-ROADMAP.md`、`REAL-WORLD-CASE-LEDGER.md`、当前工作区实现与本机真实后端证据。

本文件只判断用户指定的第一阶段交付是否成立，不把后续真实产品验收、34 图全部论文复刻或外部用户效果提前记为完成。

## 1. 逐项结论

| 第一阶段要求 | 权威证据 | 当前结论 | 不随本结论扩张的边界 |
|---|---|---|---|
| 路线与案例台账 | `docs/REAL-WORLD-RESEARCH-FIGURE-ROADMAP.md`；`docs/REAL-WORLD-CASE-LEDGER.md`；`C:\Users\pc\Desktop\实机演示` 下 34 个模板目录及 1 个独立 K08 Fig. 2F 案例目录 | **完成**。路线定义真实任务闭环、日更分级、能力准入和双后端门禁；台账逐案例记录资产、状态、缺口和下一检查 | 有目录不等于有合格案例；黄色/红色不能按模板数量冒充可录制库存 |
| 真实问题契约基线 | 路线文档第 4.1 节的元素级归因门槛；台账 RW-001–RW-042；每条新增能力要求文献面板、原始数据、产品失败、`in_scope/out_of_scope` | **完成**。基线可以区分作者数据缺口、作者方法缺口、产品能力缺口、执行器缺陷、评估器假阴性、证据不足和混合问题，并把裁决固定为修 Bug / 新增候选 / 不纳入 / 待补证据 | 截图数字化和合成数据只可用于诊断/演示，不能补写作者证据；证据不足时不得默认归因产品；结构化 readback PASS 不能替代可见产物验收 |
| X35/X36 数字类别契约修复及定向验证 | `tests/engine/test_remaining_t1_special_profiles.py` 覆盖 Profile—normalizer、Matplotlib 和 Origin 写入；`tests/engine/test_visual_t1.py` 覆盖双轴语义层；2026-08-30 重跑命令得到 `15 passed, 104 deselected` | **完成第一阶段口径**。`category` 角色可消费 numeric 值并按离散标签呈现，不要求用户先 `convert_type` 或破坏源列 | 项目 208 的真实 OPJU 轴色/系列色视觉对应仍是第二阶段门禁；定向测试不冒充该实机验收 |
| 首批日更案例分级 | 台账第一批分级；K02、K03 Fig. 2a、K08 Fig. 2F、K09 的产品主链和案例资产；K03/K08 当前资格证据分别位于 `build/real-world-k03-fig2a-agent-origin-fixed-20260830-r3/` 与 `build/real-world-k08-fig2f-product-requalify-20260830/` | **完成且已有 4 个绿色库存**：K02、K03 Fig. 2a、K08 Fig. 2F、K09。其余案例保持黄色/红色，不为日更删减目标元素 | “绿色”按具体论文面板而不是模板全局授予；例如 K08 Fig. 2F 通过不代表 K08 Fig. 1g/4b/4d 通过 |
| 下一项公共能力设计 | K13 Nature Communications 2023 Fig. 3c；`set_observation_overlay` 合同、Agent/编译器/执行器和双后端实现；`build/real-world-k13-observation-overlay-20260830/` 与 `build/real-world-k13-observation-overlay-origin-20260830/` 均为 PASS | **超过“设计”要求，最小能力切片已实现并验证**。56/56 同源观察值、确定性横向位置、样式和 Origin fresh-reopen 已闭环 | 不包含第二数据集、beeswarm/violin、配对线、显著性字母、二级类别轴或预计算箱线统计；K13 整体仍为黄色 |

## 2. 本轮重新验证

### 2.1 X35/X36

```text
python -m pytest -q \
  tests/engine/test_remaining_t1_special_profiles.py \
  tests/engine/test_visual_t1.py \
  -k "dual_y or numeric_category or category_role"

15 passed, 104 deselected
```

该范围直接覆盖第一阶段指定的数字类别契约以及与问题同时暴露的双轴语义归属；没有用全量测试的“无失败”替代目标断言。

### 2.2 第三个绿色日更案例

项目 216 保存的原始 K08 v7 产品请求在当前代码上重新执行：

- Matplotlib：13/13 类别、13 个论文原值、75×100 mm、灰色柱与隐藏图例通过；
- Origin worker：只物化当前版本，用时 12.77 s；
- 另一独立 Origin 进程：fresh-reopen、13 行数据、轴范围、画布、8 pt 刻度、9 pt 轴标题和请求颜色全部通过，用时 17.08 s；
- 相关导入、K08、排版和 recipe 定向套件：51 passed；
- 视觉检查：纵向 0–12 标签、轴标题和四侧图框均未裁切或重叠。

### 2.3 第四个绿色日更案例与验证器纠偏

K03 Fig. 2a 的同一 `k03-agent-v7-fixed.opju` 得到两种不同可见结果：

- `originpro`/COM fresh-reopen 导出的 PNG 出现轴标题、图例和普通文本上方横线；对象文本、Format Tree、边框和完整原生数据读回均没有对应装饰；
- 退出 COM 后直接启动 OriginPro 2024 SR1 的 `Origin64.exe`，打开相同 SHA-256 为 `C8B61A5150CF3F5103B67A767891F437469E034F21C03EBC71DC6E4482E230B2` 的 OPJU，再导出的 1600 px PNG 无横线；
- OriginLab 的同版本公开案例确认这是 2024 SR1 的嵌入/OLE 文本渲染缺陷，并称 2024b 已修复；
- 通用验证脚本现把结构读回和可见导出拆为两个进程边界：前者继续读原生对象，后者只由独立 Origin 可执行程序生成。

对照哈希和官方链接冻结在 `build/real-world-k03-fig2a-agent-origin-fixed-20260830-r3/standalone-visual-readback.json`。这关闭的是测试环境假阴性，不是通过新增 K03 特例绕过产品缺陷。

## 3. 第一阶段之后仍须诚实保留的边界

以下条目不是第一阶段“未完成”，而是第二阶段或持续产品目标：

1. X35/X36 真实项目的 Origin 轴色、系列色、尺寸和 fresh-reopen 可见验收。
2. X40 项目 210 重新导出后的真实 OPJU 身份列与标签可见性验收。
3. K13 二级分组与显著性字母的独立归因；现有观察值叠加通过不能替代它们。
4. K15 固定分箱仍缺少目标面板—数据—明确参数闭环，不立项、不从截图猜参数。
5. 34 个模板各自找到论文案例、整理数据并形成绿色库存；当前只有 4 个可直接录制。
6. 外部用户能否在不同数据、不同 Origin 环境下稳定完成任务，以及日更视频的实际传播效果。
7. OriginPro 2024 SR1 的 COM/OLE 会话不能作为 OPJU 最终可见产物的唯一证据；结构读回与独立可执行程序视觉复验必须同时保留。该版本边界不外推为“所有 Origin 版本都已验证”。

## 4. 第二阶段进入规则

下一案例先通过元素级七列门禁：目标元素、作者数据、作者方法、独立预期、当前产品结果、归因、是否纳入。新增公共能力还须同时满足：至少一个明确论文面板、可复用科研语义、双后端稳定表达、拒绝矩阵和 Origin fresh-reopen。若现有合同可以完成，优先形成绿色内容库存；若作者数据或方法不足，换案例而不是向产品写入猜测。
