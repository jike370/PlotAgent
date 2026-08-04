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

export const chartCatalog: ChartType[] = [
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
]

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
