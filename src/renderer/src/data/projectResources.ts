export type ResourceKind =
  | 'raw-data'
  | 'derived-data'
  | 'plot-batch'
  | 'chart'
  | 'template'
  | 'export'

export interface ResourceVersion {
  id: string
  label: string
  detail: string
  createdAt: string
  author: string
}

export interface OperationStep {
  label: string
  detail: string
}

export interface ProjectResource {
  id: string
  kind: ResourceKind
  name: string
  summary: string
  updatedAt: string
  size?: string
  format?: string
  archived?: boolean
  parentIds: string[]
  referencedBy: string[]
  conversations: string[]
  versions: ResourceVersion[]
  operationChain?: OperationStep[]
  externalPath?: string
}

export const resourceKindLabels: Record<ResourceKind, string> = {
  'raw-data': '原始数据',
  'derived-data': '派生数据',
  'plot-batch': '绘图批次',
  chart: '图表',
  template: '模板',
  export: '导出',
}

export const projectResources: ProjectResource[] = [
  {
    id: 'RAW-001',
    kind: 'raw-data',
    name: 'temperature_series.zip',
    summary: '4 个同构 CSV，9,624 行，原始内容只读',
    updatedAt: '今天 14:32',
    size: '2.1 MB',
    format: 'ZIP · CSV',
    parentIds: [],
    referencedBy: ['DER-001', 'DER-002', 'BATCH-024'],
    conversations: ['温度响应批量绘图', '数据质量复核'],
    versions: [
      { id: 'manifest-v2', label: '导入清单 v2', detail: '补充 temperature 单位为 °C，原始文件未更改', createdAt: '今天 14:35', author: '你' },
      { id: 'manifest-v1', label: '导入清单 v1', detail: '复制 4 个 CSV 到本机项目并计算校验值', createdAt: '今天 14:32', author: 'fig-agent' },
    ],
  },
  {
    id: 'RAW-002',
    kind: 'raw-data',
    name: 'sample_D_50C_repaired.csv',
    summary: '待复核的修复副本，2,406 行',
    updatedAt: '今天 15:06',
    size: '482 KB',
    format: 'CSV',
    parentIds: [],
    referencedBy: [],
    conversations: ['温度响应批量绘图'],
    versions: [
      { id: 'raw-v1', label: '导入版本', detail: '从外部修复文件导入，尚未替换批次失败项', createdAt: '今天 15:06', author: '你' },
    ],
  },
  {
    id: 'DER-001',
    kind: 'derived-data',
    name: 'temperature_clean_v2.parquet',
    summary: '类型清洗、缺失值处理与归一化后的绘图输入',
    updatedAt: '今天 14:38',
    size: '1.4 MB',
    format: 'Parquet',
    parentIds: ['RAW-001'],
    referencedBy: ['BATCH-024', 'CHART-001', 'CHART-002'],
    conversations: ['温度响应批量绘图'],
    operationChain: [
      { label: '读取 temperature_series.zip', detail: '合并 4 个结构一致的 CSV' },
      { label: '校正字段类型', detail: 'time、temperature 与 fluorescence 转为数值' },
      { label: '移除无效观测', detail: '删除 7 个无法解析的 fluorescence 值' },
      { label: '按组归一化', detail: '以各 condition 的起始值为基准' },
    ],
    versions: [
      { id: 'derived-v2', label: 'v2 当前版本', detail: '增加按 condition 归一化字段 fluorescence_norm', createdAt: '今天 14:38', author: 'fig-agent' },
      { id: 'derived-v1', label: 'v1', detail: '完成字段类型清洗并移除 7 个无效观测', createdAt: '今天 14:36', author: 'fig-agent' },
    ],
  },
  {
    id: 'DER-002',
    kind: 'derived-data',
    name: 'temperature_group_summary.csv',
    summary: '按温度和条件汇总的均值、标准差与样本量',
    updatedAt: '今天 14:40',
    size: '18 KB',
    format: 'CSV',
    parentIds: ['RAW-001'],
    referencedBy: ['CHART-002'],
    conversations: ['温度响应批量绘图'],
    operationChain: [
      { label: '读取 temperature_series.zip', detail: '使用 4 个原始 CSV' },
      { label: '按温度与条件分组', detail: 'temperature × condition' },
      { label: '计算汇总统计', detail: '均值、标准差、n' },
    ],
    versions: [
      { id: 'summary-v1', label: 'v1 当前版本', detail: '首次生成分组汇总表', createdAt: '今天 14:40', author: 'fig-agent' },
    ],
  },
  {
    id: 'BATCH-024',
    kind: 'plot-batch',
    name: '温度响应 · 批次 B-024',
    summary: 'K02 线点图，3 张成功，1 张等待重试',
    updatedAt: '今天 14:51',
    format: '4 个任务',
    parentIds: ['RAW-001', 'DER-001'],
    referencedBy: ['CHART-001', 'CHART-002'],
    conversations: ['温度响应批量绘图'],
    versions: [
      { id: 'batch-v3', label: '批次设置 v3', detail: '统一图例位置与 0.8 pt 线宽', createdAt: '今天 14:51', author: '你' },
      { id: 'batch-v2', label: '批次设置 v2', detail: '应用 Nature 双栏发表规格', createdAt: '今天 14:46', author: '你' },
      { id: 'batch-v1', label: '批次设置 v1', detail: '确认字段映射并开始绘图', createdAt: '今天 14:42', author: '你' },
    ],
  },
  {
    id: 'CHART-001',
    kind: 'chart',
    name: 'Sample A · 25 °C',
    summary: 'K02 线点图，当前版本 v3',
    updatedAt: '今天 14:51',
    format: 'SVG 场景',
    parentIds: ['DER-001', 'BATCH-024'],
    referencedBy: ['EXPORT-001'],
    conversations: ['温度响应批量绘图'],
    versions: [
      { id: 'chart-a-v3', label: 'v3 当前版本', detail: '图例移至右上，线宽调整为 0.8 pt', createdAt: '今天 14:51', author: '你' },
      { id: 'chart-a-v2', label: 'v2', detail: '应用 Nature 双栏字体与尺寸', createdAt: '今天 14:46', author: '你' },
      { id: 'chart-a-v1', label: 'v1', detail: '根据批次 B-024 首次生成', createdAt: '今天 14:43', author: 'fig-agent' },
    ],
  },
  {
    id: 'CHART-002',
    kind: 'chart',
    name: '温度组间均值比较',
    summary: 'K07 分组柱状图，带标准差误差线',
    updatedAt: '今天 14:49',
    format: 'SVG 场景',
    parentIds: ['DER-002', 'BATCH-024'],
    referencedBy: ['EXPORT-001'],
    conversations: ['温度响应批量绘图'],
    versions: [
      { id: 'chart-b-v2', label: 'v2 当前版本', detail: '改用标准差误差线并显示 n', createdAt: '今天 14:49', author: '你' },
      { id: 'chart-b-v1', label: 'v1', detail: '使用分组汇总数据首次生成', createdAt: '今天 14:44', author: 'fig-agent' },
    ],
  },
  {
    id: 'TEMPLATE-001',
    kind: 'template',
    name: 'Nature · 双栏折线图',
    summary: '183 mm，Arial 7 pt，300 DPI，色盲安全配色',
    updatedAt: '7 月 28 日',
    format: '项目模板',
    parentIds: [],
    referencedBy: ['BATCH-024'],
    conversations: ['温度响应批量绘图', '模板校准'],
    versions: [
      { id: 'template-v4', label: 'v4 当前版本', detail: '更新 2026.07 期刊尺寸规则', createdAt: '7 月 28 日', author: '你' },
      { id: 'template-v3', label: 'v3', detail: '加入 SVG 字体嵌入检查', createdAt: '6 月 16 日', author: '你' },
    ],
  },
  {
    id: 'EXPORT-001',
    kind: 'export',
    name: 'temperature_series_figures_2026-08-05',
    summary: '3 PNG + 3 SVG，文件保存在项目外部',
    updatedAt: '今天 15:18',
    size: '8.6 MB',
    format: '外部文件记录',
    parentIds: ['CHART-001', 'CHART-002'],
    referencedBy: [],
    conversations: ['温度响应批量绘图'],
    externalPath: 'D:\\exports\\temperature_series',
    versions: [
      { id: 'export-v1', label: '导出记录', detail: '生成 3 个 PNG 与 3 个 SVG，记录外部保存位置', createdAt: '今天 15:18', author: 'fig-agent' },
    ],
  },
]

export function getResourceById(resources: ProjectResource[], id: string): ProjectResource | undefined {
  return resources.find((resource) => resource.id === id)
}
