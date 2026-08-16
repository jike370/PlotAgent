import engineProfileCatalog from '../../../shared/generated/engine-profile-catalog.json'

export type ChartLayer = 'core' | 'validation'
export type BatchMode = 'direct' | 'conditional' | 'manual'
export type LayoutMode = 'layer' | 'panel'
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
  optionalFields: string[]
  repeatableRolePrefixes: string[]
  optionalParameters: string[]
  batchMode: BatchMode
  layoutMode: LayoutMode
  export: { png: true; svg: 'vector'; opju: OpjuLevel }
  risk?: 'warning' | 'parameters'
  aliases?: string[]
  favorite?: boolean
  recent?: boolean
}

interface CatalogCopy {
  name: string
  category: string
  family: string
  purpose: string
  aliases?: string[]
}

const copy: Readonly<Record<string, CatalogCopy>> = {
  K01: { name: '折线图', category: '趋势与关系', family: '折线', purpose: '展示连续变量随 X 的变化' },
  K02: { name: '线点图', category: '趋势与关系', family: '线点', purpose: '同时呈现观测点与连接趋势' },
  K03: { name: '散点图', category: '趋势与关系', family: '散点', purpose: '观察两个连续变量的关系与分组' },
  K04: { name: '气泡图', category: '趋势与关系', family: '气泡', purpose: '用点面积或颜色编码额外变量' },
  K06: { name: '点估计与误差棒', category: '不确定性', family: '误差棒', purpose: '比较估计值与双向误差' },
  K07: { name: '误差带', category: '不确定性', family: '区间带', purpose: '展示连续趋势及其上下界' },
  K08: { name: '柱状图', category: '比较', family: '柱形', purpose: '比较类别数值' },
  K09: { name: '分组柱状图', category: '比较', family: '分组柱形', purpose: '在类别内比较多个分组' },
  K10: { name: '堆积柱状图', category: '比较', family: '堆积柱形', purpose: '比较总量与内部组成' },
  K11: { name: '百分比堆积柱状图', category: '比较', family: '百分比堆积', purpose: '比较各类别的相对组成' },
  K12: { name: '条带图', category: '分布', family: '条带', purpose: '保留每个观测值并比较分组' },
  K13: { name: '箱线图', category: '分布', family: '箱线', purpose: '以分位数概括分布' },
  K14: { name: '小提琴图', category: '分布', family: '小提琴', purpose: '比较分组分布形状' },
  K15: { name: '直方图', category: '分布', family: '直方', purpose: '查看连续变量的频数分布' },
  K18: { name: '面积图', category: '趋势与关系', family: '面积', purpose: '强调连续变化的累计量或区间' },
  K19: { name: '时间序列图', category: '趋势与关系', family: '时间序列', purpose: '展示日期时间上的连续变化' },
  K20: { name: '热图', category: '矩阵与场', family: '热图', purpose: '用颜色呈现二维数值矩阵' },
  K21: { name: '相关矩阵图', category: '矩阵与场', family: '相关矩阵', purpose: '呈现已经计算好的相关矩阵' },
  K22: { name: '填色等高线图', category: '矩阵与场', family: '等高线', purpose: '呈现二维连续场的等值范围' },
  K24: { name: '分面图', category: '组合与布局', family: '分面', purpose: '按变量拆分为共享语法的小面板' },
  S34: { name: 'Nyquist 图', category: '专业图形', family: '阻抗', purpose: '呈现复阻抗响应', aliases: ['EIS', '阻抗'] },
  S61: { name: '混淆矩阵', category: '专业图形', family: '混淆矩阵', purpose: '比较真实类别与预测类别', aliases: ['分类性能'] },
  X02: { name: '垂线图', category: '趋势与关系', family: '垂线', purpose: '从数据点向坐标框底部绘制垂线' },
  X03: { name: '棒棒糖图', category: '比较', family: '棒棒糖', purpose: '逐类别连接两个或更多数值系列' },
  X05: { name: '蜂群图', category: '分布', family: '蜂群', purpose: '无重叠展示分组原始观测' },
  X09: { name: '浮动柱状图', category: '比较', family: '浮动区间', purpose: '展示每个类别的有序边界区间' },
  X13: { name: '人口金字塔', category: '比较', family: '金字塔', purpose: '围绕共同零点比较两侧类别值' },
  X23: { name: '双 Y 轴折线图', category: '多轴', family: '双轴折线', purpose: '在明确轴归属下比较两组量纲' },
  X24: { name: '帕累托图', category: '比较', family: '帕累托', purpose: '显示降序频数与累计百分比' },
  X35: { name: '双 Y 轴柱状图', category: '多轴', family: '双轴柱形', purpose: '在两个纵轴上比较柱形系列' },
  X36: { name: '双 Y 轴柱线图', category: '多轴', family: '双轴柱线', purpose: '组合左轴柱形与右轴折线' },
  X38: { name: 'Y 偏移堆叠线图', category: '专业图形', family: '偏移堆叠', purpose: '按固定偏移展示多条曲线' },
  X39: { name: '线条序列图', category: '比较', family: '线条序列', purpose: '连接多个序列在相同对象上的数值' },
  X40: { name: '前后对比图', category: '比较', family: '前后对比', purpose: '连接同一对象的前后测量' },
}

const panelProfiles = new Set(['K20', 'K21', 'K22', 'K24', 'S61', 'X23', 'X35', 'X36'])
const conditionalProfiles = new Set(['K13', 'K14', 'K15', 'K21', 'S61'])
const favorites = new Set(['K01', 'K03', 'K13', 'K20'])
const recent = new Set(['K01', 'K03', 'K13', 'K21'])

export type EditCapability =
  | 'plot_title' | 'axis_label' | 'axis_range' | 'axis_scale' | 'axis_reverse'
  | 'legend_visibility' | 'legend_position' | 'safe_annotation' | 'line_style'
  | 'marker_style' | 'fill_style' | 'colormap' | 'error_style' | 'data_labels'
  | 'chart_parameters'

export interface ChartProductMetadata {
  admission: 'product'
  visualEvidence: 'engine_acceptance'
  editCapabilities: readonly EditCapability[]
}

type EngineProfile = (typeof engineProfileCatalog.profiles)[number]

const capabilityMap = (profile: EngineProfile): EditCapability[] => {
  const capabilities = new Map(profile.capabilities.map((item) => [item.operation, new Set(item.parameters)]))
  const series = capabilities.get('set_series_style') ?? new Set<string>()
  const axis = capabilities.get('set_axis') ?? new Set<string>()
  const legend = capabilities.get('set_legend') ?? new Set<string>()
  return [
    ...(capabilities.has('set_title') ? ['plot_title' as const] : []),
    ...(axis.has('label') ? ['axis_label' as const] : []),
    ...(axis.has('scale') ? ['axis_scale' as const] : []),
    ...(axis.has('bounds') ? ['axis_range' as const] : []),
    ...(axis.has('reverse') ? ['axis_reverse' as const] : []),
    ...([...series].some((item) => item.startsWith('line_')) ? ['line_style' as const] : []),
    ...([...series].some((item) => item.startsWith('marker_'))
      ? ['marker_style' as const] : []),
    ...([...series].some((item) => item.startsWith('fill_')) ? ['fill_style' as const] : []),
    ...(capabilities.has('set_colormap') ? ['colormap' as const] : []),
    ...(capabilities.has('set_error_style') ? ['error_style' as const] : []),
    ...(capabilities.has('set_data_labels') ? ['data_labels' as const] : []),
    ...(legend.has('visible') ? ['legend_visibility' as const] : []),
    ...(legend.has('anchor') ? ['legend_position' as const] : []),
    ...(capabilities.has('set_chart_parameter') ? ['chart_parameters' as const] : []),
    ...(capabilities.has('add_annotation') ? ['safe_annotation' as const] : []),
  ]
}

export const chartProductMetadata: Readonly<Record<string, ChartProductMetadata>> = Object.fromEntries(
  engineProfileCatalog.profiles.map((profile) => [profile.profile_id, {
    admission: 'product',
    visualEvidence: 'engine_acceptance',
    editCapabilities: capabilityMap(profile),
  }]),
)

export const paletteCatalog: readonly { palette_id: string; colors: readonly { value: string }[] }[] = [
  { palette_id: 'Default', colors: ['#2A6FDB', '#D94B4B', '#2F9D74', '#D48A00', '#7A5AF8'].map((value) => ({ value })) },
]

export const symbolCatalog: readonly { shape: string; allowed_interiors: readonly string[] }[] = [
  { shape: 'circle', allowed_interiors: ['solid'] },
  { shape: 'square', allowed_interiors: ['solid'] },
  { shape: 'diamond', allowed_interiors: ['solid'] },
  { shape: 'triangle_up', allowed_interiors: ['solid'] },
  { shape: 'triangle_down', allowed_interiors: ['solid'] },
  { shape: 'plus', allowed_interiors: ['solid'] },
  { shape: 'cross', allowed_interiors: ['solid'] },
]

const toChart = (profile: EngineProfile): ChartType => {
  const item = copy[profile.profile_id]
  if (!item) throw new Error(`Missing UI copy for engine profile ${profile.profile_id}`)
  const chartParameters = profile.capabilities.find(
    (capability) => capability.operation === 'set_chart_parameter',
  )?.parameters ?? []
  return {
    id: profile.profile_id,
    layer: profile.profile_id.startsWith('S') ? 'validation' : 'core',
    name: item.name,
    englishName: profile.display_name,
    category: item.category,
    family: item.family,
    purpose: item.purpose,
    dataShape: [profile.required_roles.join(' + ')],
    domains: profile.profile_id.startsWith('S') ? ['专业科研'] : ['通用科研'],
    requiredFields: [...profile.required_roles],
    optionalFields: [...profile.optional_roles],
    repeatableRolePrefixes: [...profile.repeatable_role_prefixes],
    optionalParameters: [...profile.optional_roles, ...chartParameters],
    batchMode: conditionalProfiles.has(profile.profile_id) ? 'conditional' : 'direct',
    layoutMode: panelProfiles.has(profile.profile_id) ? 'panel' : 'layer',
    export: { png: true, svg: 'vector', opju: profile.profile_id === 'K24' ? 'O2' : 'O1' },
    aliases: item.aliases,
    favorite: favorites.has(profile.profile_id),
    recent: recent.has(profile.profile_id),
  }
}

export const chartCatalog: ChartType[] = engineProfileCatalog.profiles.map(toChart)
export const allChartCatalog: readonly ChartType[] = chartCatalog

export interface ChartFilters {
  query: string
  layer: 'all' | ChartLayer
  category: string
  capability: 'all' | 'batch' | 'layout' | 'opju'
  collection: 'all' | 'favorites' | 'recent'
}

const normalize = (value: string): string => value.trim().toLocaleLowerCase('zh-CN')

export function filterCharts(charts: ChartType[], filters: ChartFilters): ChartType[] {
  const query = normalize(filters.query)
  return charts.filter((item) => {
    const searchable = normalize([
      item.id, item.name, item.englishName, item.category, item.family, item.purpose,
      ...item.dataShape, ...item.domains, ...(item.aliases ?? []),
    ].join(' '))
    return (query.length === 0 || searchable.includes(query))
      && (filters.layer === 'all' || item.layer === filters.layer)
      && (filters.category === '全部' || item.category === filters.category)
      && (filters.collection === 'all'
        || (filters.collection === 'favorites' && item.favorite === true)
        || (filters.collection === 'recent' && item.recent === true))
      && (filters.capability === 'all'
        || (filters.capability === 'batch' && item.batchMode !== 'manual')
        || (filters.capability === 'layout' && item.layoutMode !== 'layer')
        || (filters.capability === 'opju' && item.export.opju !== 'O3'))
  })
}

export const chartCategories = ['全部', ...new Set(chartCatalog.map((item) => item.category))]
