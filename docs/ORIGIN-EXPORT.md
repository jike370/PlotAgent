# PlotAgent v3 原生 Origin OPJU 导出

> 正式范围：34张单图。K25和组合图不属于导出能力。

## 产品承诺

OPJU必须包含原生worksheet/matrix、plot/layer、数据绑定和可编辑对象；不得嵌入Matplotlib图片冒充Origin项目。

## 创建流程

1. 运行Origin可用性预检；
2. 解析并校验图类的官方recipe与本机资产；
3. 写入源数据、列designation或matrix坐标；
4. 调用官方模板、菜单section或X-Function；
5. 应用用户明确的共同编辑；
6. 读回数据、原生结构和编辑；
7. 原子保存OPJU；
8. 在新的Origin会话中重开并重复读回。

## UI行为

- Origin不可用时，在系统保存对话框前给出可操作诊断；
- 导出运行中显示真实阶段；
- 成功后明确显示文件名、路径和完成状态；
- 失败不得留下已登记成功的导出记录或半版本；
- 不覆盖旧文件，除非用户明确确认。

## 资格

文件存在或可打开不等于PASS。代表性OPJU必须在Origin中修改数据或样式、保存并重开，确认图页、数据对象和编辑仍然存在。34图每图至少一份当前build的live+fresh-reopen证据。

删除图类只返回`CHART_TYPE_REMOVED`，不创建近似OPJU。
