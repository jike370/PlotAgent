import styleCatalog from '../../../shared/generated/style-catalog.json'

export type ChartLayer = 'core' | 'validation'
export type BatchMode = 'direct' | 'conditional' | 'manual'
export type CompositionMode = 'layer' | 'panel'
export type OpjuLevel = 'O1' | 'O2' | 'O3'

export interface ChartType {
  id: string
  layer: ChartLayer
  name: string
  englishName: string
  category: string
  family: string
  purpose: string
  dataShape: string[]
  domains: string[]
  requiredFields: string[]
  optionalParameters: string[]
  batchMode: BatchMode
  compositionMode: CompositionMode
  export: {
    png: true
    svg: 'vector'
    opju: OpjuLevel
  }
  risk?: 'warning' | 'parameters'
  aliases?: string[]
  favorite?: boolean
  recent?: boolean
}

interface ChartSeed extends Omit<ChartType, 'export' | 'layer' | 'domains' | 'optionalParameters'> {
  layer?: ChartLayer
  domains?: string[]
  optionalParameters?: string[]
  opju?: OpjuLevel
}

const chart = ({
  layer = 'core',
  domains = ['全学科'],
  optionalParameters = ['分组', '坐标范围', '标记样式'],
  opju = 'O1',
  ...seed
}: ChartSeed): ChartType => ({
  ...seed,
  layer,
  domains,
  optionalParameters,
  export: { png: true, svg: 'vector', opju },
})

const allChartCatalogSeeds: ChartType[] = [
  chart({ id: 'K01', name: '折线图', englishName: 'Line plot', category: '时间与关系', family: 'line', purpose: '展示连续变量随时间或有序 X 的变化', dataShape: ['XY', 'XYY'], requiredFields: ['X', 'Y'], batchMode: 'direct', compositionMode: 'layer', favorite: true, recent: true, aliases: ['曲线图'] }),
  chart({ id: 'K02', name: '线点图', englishName: 'Line + symbol', category: '时间与关系', family: 'line-symbol', purpose: '同时呈现实测点与连接趋势', dataShape: ['XY', 'XYY'], requiredFields: ['X', 'Y'], batchMode: 'direct', compositionMode: 'layer', favorite: true }),
  chart({ id: 'K03', name: '散点图', englishName: 'Scatter plot', category: '关系', family: 'scatter', purpose: '观察两个连续变量的关系与分组', dataShape: ['XY', 'long'], requiredFields: ['X', 'Y'], batchMode: 'direct', compositionMode: 'layer', recent: true, aliases: ['散点'] }),
  chart({ id: 'K04', name: '气泡与颜色映射散点', englishName: 'Bubble & colormap scatter', category: '关系', family: 'bubble', purpose: '用面积或颜色编码额外变量', dataShape: ['XY + size', 'XY + color'], requiredFields: ['X', 'Y', '大小或颜色'], batchMode: 'direct', compositionMode: 'layer' }),
  chart({ id: 'K05', name: '回归散点与置信带', englishName: 'Regression plot', category: '关系', family: 'regression', purpose: '展示拟合关系、实测点与置信区间', dataShape: ['XY', 'long'], requiredFields: ['X', 'Y', '模型'], batchMode: 'conditional', compositionMode: 'layer', risk: 'parameters', optionalParameters: ['模型', '置信水平', '稳健或加权'] }),
  chart({ id: 'K06', name: '点估计与误差棒', englishName: 'Point estimate + error bar', category: '不确定性', family: 'errorbar', purpose: '比较估计值与明确含义的区间', dataShape: ['estimate + interval'], requiredFields: ['估计值', '下限', '上限'], batchMode: 'direct', compositionMode: 'layer', favorite: true }),
  chart({ id: 'K07', name: '误差带与置信带', englishName: 'Error ribbon', category: '不确定性', family: 'ribbon', purpose: '展示连续趋势及其不确定区间', dataShape: ['X + center + interval'], requiredFields: ['X', '中心值', '下限', '上限'], batchMode: 'direct', compositionMode: 'layer' }),
  chart({ id: 'K08', name: '柱状图', englishName: 'Column & bar', category: '比较', family: 'bar', purpose: '比较类别值或计数', dataShape: ['category + value'], requiredFields: ['类别', '数值'], batchMode: 'direct', compositionMode: 'layer', risk: 'parameters' }),
  chart({ id: 'K09', name: '分组柱状图', englishName: 'Grouped bar', category: '比较', family: 'grouped-bar', purpose: '在类别内比较多个实验组', dataShape: ['category × group'], requiredFields: ['类别', '分组', '数值'], batchMode: 'direct', compositionMode: 'layer' }),
  chart({ id: 'K10', name: '堆积柱状图', englishName: 'Stacked bar', category: '组成', family: 'stacked-bar', purpose: '比较总量及内部组成', dataShape: ['category × component'], requiredFields: ['类别', '组成', '数值'], batchMode: 'direct', compositionMode: 'layer' }),
  chart({ id: 'K11', name: '百分比堆积图', englishName: '100% stacked bar', category: '组成', family: 'stacked-bar', purpose: '比较各类别的相对组成', dataShape: ['category × component'], requiredFields: ['类别', '组成', '数值', '归一化规则'], batchMode: 'direct', compositionMode: 'layer' }),
  chart({ id: 'K12', name: '单变量点图与条带图', englishName: 'Dot & strip plot', category: '分布', family: 'strip', purpose: '保留每个观测值并比较分组', dataShape: ['long'], requiredFields: ['数值', '分组'], batchMode: 'direct', compositionMode: 'layer' }),
  chart({ id: 'K13', name: '箱线图', englishName: 'Box plot', category: '分布', family: 'box', purpose: '用分位数概括分布并保留异常点', dataShape: ['Y', 'long'], requiredFields: ['数值', '可选分组'], batchMode: 'conditional', compositionMode: 'layer', favorite: true, recent: true }),
  chart({ id: 'K14', name: '小提琴图', englishName: 'Violin plot', category: '分布', family: 'violin', purpose: '比较分组分布的形状与集中趋势', dataShape: ['Y', 'long'], requiredFields: ['数值', '分组'], batchMode: 'conditional', compositionMode: 'layer', optionalParameters: ['KDE 带宽', '裁剪', '内嵌统计'] }),
  chart({ id: 'K15', name: '直方图', englishName: 'Histogram', category: '分布', family: 'histogram', purpose: '查看连续变量的频数或密度分布', dataShape: ['Y'], requiredFields: ['数值'], batchMode: 'conditional', compositionMode: 'layer' }),
  chart({ id: 'K16', name: '核密度图', englishName: 'KDE density', category: '分布', family: 'density', purpose: '比较连续分布的平滑密度', dataShape: ['Y', 'long'], requiredFields: ['数值'], batchMode: 'conditional', compositionMode: 'layer', optionalParameters: ['核函数', '带宽', '边界'] }),
  chart({ id: 'K17', name: '经验累积分布', englishName: 'ECDF / CCDF', category: '分布', family: 'ecdf', purpose: '显示观测值的经验累积概率', dataShape: ['Y'], requiredFields: ['数值'], batchMode: 'conditional', compositionMode: 'layer' }),
  chart({ id: 'K18', name: '面积图', englishName: 'Area plot', category: '时间与关系', family: 'area', purpose: '强调连续变化的累计量或区间', dataShape: ['XY', 'XYY'], requiredFields: ['X', 'Y'], batchMode: 'direct', compositionMode: 'layer' }),
  chart({ id: 'K19', name: '时间序列图', englishName: 'Time-series plot', category: '时间与关系', family: 'timeseries', purpose: '处理日期、缺失与事件标记的连续趋势', dataShape: ['time + value'], requiredFields: ['时间', '数值'], batchMode: 'direct', compositionMode: 'layer' }),
  chart({ id: 'K20', name: '热图', englishName: 'Heatmap', category: '矩阵与场', family: 'heatmap', purpose: '用颜色显示矩阵或二维数值场', dataShape: ['matrix', 'XYZ', 'long'], requiredFields: ['行', '列', '数值'], batchMode: 'direct', compositionMode: 'panel', favorite: true }),
  chart({ id: 'K21', name: '相关矩阵图', englishName: 'Correlation matrix', category: '矩阵与场', family: 'correlation', purpose: '检查多变量相关结构', dataShape: ['wide', 'matrix'], requiredFields: ['至少 2 个数值字段', '相关方法'], batchMode: 'conditional', compositionMode: 'panel', risk: 'parameters', recent: true }),
  chart({ id: 'K22', name: '等高线与填色等值图', englishName: 'Contour', category: '矩阵与场', family: 'contour', purpose: '显示二维连续场的等值线与范围', dataShape: ['XYZ', 'grid'], requiredFields: ['X', 'Y', 'Z'], batchMode: 'direct', compositionMode: 'layer', optionalParameters: ['网格化', '插值', '等值级别', '实测点'] }),
  chart({ id: 'K24', name: '分面图', englishName: 'Faceted plot', category: '组合与布局', family: 'facet', purpose: '按数值变量拆分为共享视觉语法的小面板', dataShape: ['long + facet'], requiredFields: ['基础图字段', '分面变量'], batchMode: 'direct', compositionMode: 'panel', opju: 'O2' }),
  chart({ id: 'K25', name: '多面板复合图', englishName: 'Multi-panel figure', category: '组合与布局', family: 'multi-panel', purpose: '组合多个数值数据图表并统一面板编号', dataShape: ['chart scenes'], requiredFields: ['至少 2 个数值图表'], batchMode: 'manual', compositionMode: 'panel', opju: 'O2', favorite: true }),
  chart({ id: 'S01', layer: 'validation', name: 'KM 生存曲线', englishName: 'Kaplan–Meier curve', category: '临床与生物', family: 'survival', purpose: '展示删失数据的生存概率与风险人数', dataShape: ['time + event + group'], requiredFields: ['随访时间', '事件或删失', '可选分组'], batchMode: 'conditional', compositionMode: 'panel', domains: ['临床', '生命科学', '可靠性'], optionalParameters: ['删失定义', '风险人数', '置信区间', '检验'], recent: true, aliases: ['KM', 'survival', '生存'] }),
  chart({ id: 'S05', layer: 'validation', name: '剂量反应曲线', englishName: 'Dose–response / IC50', category: '临床与生物', family: 'dose-response', purpose: '拟合浓度或剂量与响应的非线性关系', dataShape: ['dose + response'], requiredFields: ['剂量', '响应', '重复或分组'], batchMode: 'conditional', compositionMode: 'layer', domains: ['药理', '毒理', '生命科学'], optionalParameters: ['4PL 或 5PL', '上下平台', 'Hill slope', '置信区间'], aliases: ['IC50', 'EC50', '4PL'] }),
  chart({ id: 'S21', layer: 'validation', name: '森林图', englishName: 'Forest & coefficient plot', category: '统计估计', family: 'forest', purpose: '比较效应估计、区间和权重', dataShape: ['effect + interval'], requiredFields: ['标签', '效应值', '下限', '上限'], batchMode: 'conditional', compositionMode: 'panel', domains: ['临床', 'Meta 分析', '社会科学'], optionalParameters: ['效应尺度', '无效线', '权重', '汇总效应'], favorite: true, aliases: ['forest', '系数图'] }),
  chart({ id: 'S25', layer: 'validation', name: '连续谱图', englishName: 'NMR / IR / Raman / UV–Vis spectra', category: '化学与材料', family: 'spectrum', purpose: '呈现强度随波数、位移或波长的连续谱线', dataShape: ['XYY'], requiredFields: ['谱轴', '强度', '样品'], batchMode: 'direct', compositionMode: 'layer', domains: ['化学', '材料', '物理'], optionalParameters: ['轴方向', '基线', '归一化', '峰标注'], favorite: true, aliases: ['NMR', 'IR', 'Raman', 'UV-Vis', '光谱'] }),
  chart({ id: 'S31', layer: 'validation', name: 'XRD 衍射图', englishName: 'XRD diffraction plot', category: '化学与材料', family: 'xrd', purpose: '呈现衍射强度、峰位与参考信息', dataShape: ['angle + intensity', 'XYY'], requiredFields: ['角度或 q', '强度'], batchMode: 'direct', compositionMode: 'layer', domains: ['材料', '化学', '地学'], optionalParameters: ['背景', '归一化', '峰宽', '参考卡', '波长'], recent: true, aliases: ['XRD', 'SAXS', 'WAXS'] }),
  chart({ id: 'S34', layer: 'validation', name: 'Nyquist 图', englishName: 'Nyquist plot', category: '化学与材料', family: 'nyquist', purpose: '在等比例坐标中展示复阻抗频率响应', dataShape: ["frequency + Z' + -Z''"], requiredFields: ['频率', "Z'", "-Z''"], batchMode: 'conditional', compositionMode: 'panel', domains: ['电化学', '控制', '材料'], optionalParameters: ['频率方向', '等比例轴', '等效电路', '拟合残差'], aliases: ['EIS', '阻抗'] }),
  chart({ id: 'S61', layer: 'validation', name: '混淆矩阵', englishName: 'Confusion matrix', category: '机器学习', family: 'confusion-matrix', purpose: '比较真实类别与预测类别的计数或比例', dataShape: ['class × class matrix', 'actual + predicted'], requiredFields: ['真实类别', '预测类别'], batchMode: 'conditional', compositionMode: 'panel', domains: ['机器学习', '生物信息', '临床预测'], optionalParameters: ['计数或比例', '归一化方向', '类别顺序', '颜色范围'], aliases: ['confusion matrix', '分类矩阵', '分类性能'] }),
  chart({ id: 'X01', name: '阶梯图', englishName: 'Step plot', category: '时间与关系', family: 'step', purpose: '呈现离散时刻发生的水平变化', dataShape: ['XY'], requiredFields: ['X', 'Y'], batchMode: 'direct', compositionMode: 'layer', aliases: ['水平阶梯', '垂直阶梯'] }),
  chart({ id: 'X02', name: '垂线图', englishName: 'Drop line plot', category: '时间与关系', family: 'drop-line', purpose: '从连续坐标点向坐标框底部 X 轴绘制垂线', dataShape: ['XY'], requiredFields: ['X', 'Y'], batchMode: 'direct', compositionMode: 'layer', aliases: ['Drop Line', '垂直线图'] }),
  chart({ id: 'X03', name: '棒棒糖图', englishName: 'Origin lollipop plot', category: '比较', family: 'lollipop', purpose: '逐行连接两个及以上数值系列；两系列时形成哑铃效果', dataShape: ['category + 2 or more numeric series'], requiredFields: ['类别', '至少 2 个数值系列'], batchMode: 'direct', compositionMode: 'layer', aliases: ['哑铃图', 'dumbbell', 'lollipop'] }),
  chart({ id: 'X05', name: '蜂群图', englishName: 'Beeswarm plot', category: '分布', family: 'beeswarm', purpose: '无重叠地展示分组原始观测', dataShape: ['value + group'], requiredFields: ['数值', '可选分组'], batchMode: 'direct', compositionMode: 'layer' }),
  chart({ id: 'X07', name: '山脊图', englishName: 'Ridgeline plot', category: '分布', family: 'ridgeline', purpose: '比较多组分布形状并保持组序', dataShape: ['value + group'], requiredFields: ['数值', '分组'], batchMode: 'conditional', compositionMode: 'layer' }),
  chart({ id: 'X09', name: '范围柱条图', englishName: 'Floating interval bar', category: '比较', family: 'floating-bar', purpose: '显示每个类别的明确起止区间，可选中间界限形成分段', dataShape: ['category + start + end', 'category + start + middle + end'], requiredFields: ['类别', '起点', '终点'], optionalParameters: ['中间界限'], batchMode: 'direct', compositionMode: 'layer' }),
  chart({ id: 'X11', name: '桥图', englishName: 'Bridge waterfall', category: '比较', family: 'bridge', purpose: '显示一系列正负变化的累计影响', dataShape: ['category + delta'], requiredFields: ['类别', '变化量'], batchMode: 'direct', compositionMode: 'layer', aliases: ['瀑布图'] }),
  chart({ id: 'X12', name: '子弹图', englishName: 'Bullet chart', category: '比较', family: 'bullet', purpose: '同时展示实际值、目标和定性区间', dataShape: ['item + actual + target + ranges'], requiredFields: ['项目', '实际值', '目标'], batchMode: 'direct', compositionMode: 'layer' }),
  chart({ id: 'X13', name: '人口金字塔', englishName: 'Population pyramid', category: '比较', family: 'pyramid', purpose: '围绕共同零点比较两侧类别值', dataShape: ['category + left + right'], requiredFields: ['类别', '左侧值', '右侧值'], batchMode: 'direct', compositionMode: 'layer', aliases: ['蝴蝶图'] }),
  chart({ id: 'X15', name: '散点矩阵', englishName: 'Scatter matrix', category: '关系', family: 'scatter-matrix', purpose: '在矩阵中检查三个数值变量的两两关系', dataShape: ['3 numeric columns'], requiredFields: ['数值字段 1', '数值字段 2', '数值字段 3'], batchMode: 'direct', compositionMode: 'panel' }),
  chart({ id: 'X16', name: '二维密度图', englishName: '2D density', category: '关系', family: 'density2d', purpose: '显示高密散点的二维计数密度', dataShape: ['XY'], requiredFields: ['X', 'Y'], batchMode: 'conditional', compositionMode: 'panel', aliases: ['2D KDE'] }),
  chart({ id: 'X17', name: '边际分布图', englishName: 'Marginal scatter', category: '关系', family: 'marginal', purpose: '组合中心散点和同源边际分布', dataShape: ['XY'], requiredFields: ['X', 'Y'], batchMode: 'conditional', compositionMode: 'panel' }),
  chart({ id: 'X18', name: 'Q-Q 概率图', englishName: 'Q-Q & probability plot', category: '分布', family: 'qq', purpose: '比较样本分位数与正态理论分位数', dataShape: ['Y'], requiredFields: ['数值'], batchMode: 'conditional', compositionMode: 'layer', aliases: ['概率图'] }),
  chart({ id: 'X19', name: 'Bland–Altman 图', englishName: 'Bland–Altman agreement', category: '统计估计', family: 'bland-altman', purpose: '检查两种测量方法的一致性与一致性限', dataShape: ['paired measurements'], requiredFields: ['方法 A', '方法 B'], batchMode: 'conditional', compositionMode: 'layer' }),
  chart({ id: 'X23', name: '双 Y 轴折线图', englishName: 'Dual-Y line', category: '多轴', family: 'dual-y-line', purpose: '在明确轴归属下比较共享 X 的两组量纲', dataShape: ['X + left Y + right Y'], requiredFields: ['X', '左轴 Y', '右轴 Y'], batchMode: 'direct', compositionMode: 'layer', risk: 'warning' }),
  chart({ id: 'X24', name: '帕累托图', englishName: 'Pareto chart', category: '比较', family: 'pareto', purpose: '按贡献降序显示频数和累计百分比', dataShape: ['category + value'], requiredFields: ['类别', '数值'], batchMode: 'direct', compositionMode: 'layer' }),
  chart({ id: 'X35', name: '双 Y 轴柱状图', englishName: 'Dual-Y column', category: '多轴', family: 'dual-y-column', purpose: '以两组明确量纲的柱比较共享类别', dataShape: ['category + left Y + right Y'], requiredFields: ['类别', '左轴 Y', '右轴 Y'], batchMode: 'direct', compositionMode: 'layer', risk: 'warning' }),
  chart({ id: 'X36', name: '双 Y 轴柱线图', englishName: 'Dual-Y column-line', category: '多轴', family: 'dual-y-column-line', purpose: '以左柱和右线呈现两组明确量纲', dataShape: ['category + left Y + right Y'], requiredFields: ['类别', '左轴 Y', '右轴 Y'], batchMode: 'direct', compositionMode: 'layer', risk: 'warning' }),
  chart({ id: 'X37', name: '双 Y 轴箱线图', englishName: 'Dual-Y box', category: '多轴', family: 'dual-y-box', purpose: '在两个明确量纲上比较分组原始分布', dataShape: ['group + left values + right values'], requiredFields: ['分组', '左轴数值', '右轴数值'], batchMode: 'conditional', compositionMode: 'layer', risk: 'warning' }),
  chart({ id: 'X38', name: 'Y 偏移堆积线图', englishName: 'Y-offset stacked line', category: '时间与关系', family: 'y-offset', purpose: '用仅影响显示的偏移分离多条曲线', dataShape: ['X + Y + series'], requiredFields: ['X', 'Y', '系列'], batchMode: 'direct', compositionMode: 'layer' }),
  chart({ id: 'X39', name: '线条序列图', englishName: 'Line series plot', category: '比较', family: 'line-series', purpose: '将每行观测跨两个及以上数值列连接为一条线点序列', dataShape: ['2 or more numeric columns'], requiredFields: ['至少 2 个数值系列'], batchMode: 'direct', compositionMode: 'layer', aliases: ['Line Series', 'BoxLser'] }),
  chart({ id: 'X40', name: '前后对比图', englishName: 'Before-after plot', category: '比较', family: 'before-after', purpose: '每相邻两列形成一组前后连接，奇数末列仅显示散点', dataShape: ['paired numeric columns'], requiredFields: ['至少 2 个数值系列'], batchMode: 'direct', compositionMode: 'layer', aliases: ['Before After', '配对变化图'] }),
  chart({ id: 'S07', layer: 'validation', name: '火山图', englishName: 'Volcano plot', category: '组学', family: 'volcano', purpose: '显示预计算效应量与显著性', dataShape: ['feature + log2FC + p/q'], requiredFields: ['特征', 'log2FC', 'P 值'], batchMode: 'direct', compositionMode: 'layer', domains: ['转录组', '蛋白组', '生物信息'], optionalParameters: ['FC 阈值', 'P/Q 阈值', '标签'], aliases: ['volcano'] }),
]

export type EditCapability =
  | 'plot_title' | 'axis_label' | 'axis_range' | 'axis_scale' | 'axis_ticks' | 'font'
  | 'legend_visibility' | 'legend_position' | 'canvas_size' | 'publication_profile'
  | 'safe_annotation' | 'series_color' | 'line_width' | 'line_style' | 'marker_size'
  | 'symbol_shape' | 'symbol_interior' | 'palette' | 'bar_fill' | 'bar_edge'
  | 'bar_width' | 'bar_gap' | 'error_style' | 'band_style' | 'colorbar'
  | 'dual_y_style' | 'panel_style' | 'y_offset'
  | 'chart_parameters'

export type PaletteId = (typeof styleCatalog.palettes)[number]['palette_id']
export type SymbolShape = (typeof styleCatalog.symbols)[number]['shape']

export interface ChartProductMetadata {
  admission: 'product' | 'internal_only' | 'removed'
  visualEvidence: 'origin_reference' | 'synthetic_visual' | 'unqualified'
  editCapabilities: readonly EditCapability[]
}

export const chartProductMetadata: Readonly<Record<string, ChartProductMetadata>> =
  Object.fromEntries(styleCatalog.charts.map((item) => [item.chart_type_id, {
    admission: item.admission as ChartProductMetadata['admission'],
    visualEvidence: item.visual_evidence as ChartProductMetadata['visualEvidence'],
    editCapabilities: item.edit_capabilities as EditCapability[],
  }]))

export const paletteCatalog = styleCatalog.palettes
export const symbolCatalog = styleCatalog.symbols

export const allChartCatalog: readonly ChartType[] = allChartCatalogSeeds
export const chartCatalog: ChartType[] = allChartCatalogSeeds.filter(
  (item) => chartProductMetadata[item.id]?.admission === 'product',
)

export interface ChartFilters {
  query: string
  layer: 'all' | ChartLayer
  category: string
  capability: 'all' | 'batch' | 'composition' | 'opju'
  collection: 'all' | 'favorites' | 'recent'
}

const normalize = (value: string): string => value.trim().toLocaleLowerCase('zh-CN')

export function filterCharts(charts: ChartType[], filters: ChartFilters): ChartType[] {
  const query = normalize(filters.query)

  return charts.filter((item) => {
    const searchable = normalize([
      item.id,
      item.name,
      item.englishName,
      item.category,
      item.family,
      item.purpose,
      ...item.dataShape,
      ...item.domains,
      ...(item.aliases ?? []),
    ].join(' '))

    const matchesQuery = query.length === 0 || searchable.includes(query)
    const matchesLayer = filters.layer === 'all' || item.layer === filters.layer
    const matchesCategory = filters.category === '全部' || item.category === filters.category
    const matchesCollection =
      filters.collection === 'all' ||
      (filters.collection === 'favorites' && item.favorite === true) ||
      (filters.collection === 'recent' && item.recent === true)
    const matchesCapability =
      filters.capability === 'all' ||
      (filters.capability === 'batch' && item.batchMode !== 'manual') ||
      (filters.capability === 'composition' && item.compositionMode !== 'layer') ||
      (filters.capability === 'opju' && item.export.opju !== 'O3')

    return matchesQuery && matchesLayer && matchesCategory && matchesCollection && matchesCapability
  })
}

export const chartCategories = ['全部', ...new Set(chartCatalog.map((item) => item.category))]
