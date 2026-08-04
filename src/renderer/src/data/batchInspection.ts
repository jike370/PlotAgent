export type BatchItemStatus = 'success' | 'warning' | 'failed'
export type BatchViewMode = 'grid' | 'list' | 'carousel'
export type BatchStatusFilter = 'all' | BatchItemStatus
export type BatchIssueFilter = 'all' | 'anomaly' | 'scientific-warning' | 'excluded'
export type BatchSortMode = 'source-asc' | 'updated-desc' | 'temperature-asc' | 'status'

export interface BatchInspectionItem {
  id: string
  sourceName: string
  title: string
  temperature: number
  condition: string
  replicate: string
  status: BatchItemStatus
  updatedAt: string
  updatedRank: number
  version: string
  series: 'control' | 'treated' | 'recovery'
  anomalies: string[]
  scientificWarnings: string[]
  excluded: boolean
  failureReason?: string
}

export const batchInspectionItems: BatchInspectionItem[] = [
  {
    id: 'A-25',
    sourceName: 'sample_A_25C.csv',
    title: 'Sample A · 25 °C',
    temperature: 25,
    condition: 'Control',
    replicate: 'R1',
    status: 'success',
    updatedAt: '今天 14:51',
    updatedRank: 451,
    version: 'v3',
    series: 'control',
    anomalies: [],
    scientificWarnings: [],
    excluded: false,
  },
  {
    id: 'B-37',
    sourceName: 'sample_B_37C.csv',
    title: 'Sample B · 37 °C',
    temperature: 37,
    condition: 'Treated',
    replicate: 'R1',
    status: 'warning',
    updatedAt: '今天 14:50',
    updatedRank: 450,
    version: 'v3',
    series: 'treated',
    anomalies: [],
    scientificWarnings: ['末端 3 个点的置信区间变宽', '基线较组内中位数高 8.4%'],
    excluded: false,
  },
  {
    id: 'C-42',
    sourceName: 'sample_C_42C.csv',
    title: 'Sample C · 42 °C',
    temperature: 42,
    condition: 'Recovery',
    replicate: 'R2',
    status: 'success',
    updatedAt: '今天 14:49',
    updatedRank: 449,
    version: 'v3',
    series: 'recovery',
    anomalies: ['45 min 处峰值偏离相邻点 2.7 SD'],
    scientificWarnings: [],
    excluded: true,
  },
  {
    id: 'D-50',
    sourceName: 'sample_D_50C.csv',
    title: 'Sample D · 50 °C',
    temperature: 50,
    condition: 'Treated',
    replicate: 'R2',
    status: 'failed',
    updatedAt: '今天 14:43',
    updatedRank: 443,
    version: '未生成',
    series: 'treated',
    anomalies: [],
    scientificWarnings: [],
    excluded: true,
    failureReason: 'fluorescence 含 7 个文本值',
  },
]

export function filterBatchItems(
  items: BatchInspectionItem[],
  query: string,
  status: BatchStatusFilter,
  issue: BatchIssueFilter,
): BatchInspectionItem[] {
  const normalizedQuery = query.trim().toLocaleLowerCase('zh-CN')

  return items.filter((item) => {
    const searchableMetadata = `${item.sourceName} ${item.title} ${item.temperature} ${item.condition} ${item.replicate}`.toLocaleLowerCase('zh-CN')
    const matchesQuery = !normalizedQuery || searchableMetadata.includes(normalizedQuery)
    const matchesStatus = status === 'all' || item.status === status
    const matchesIssue = issue === 'all'
      || (issue === 'anomaly' && item.anomalies.length > 0)
      || (issue === 'scientific-warning' && item.scientificWarnings.length > 0)
      || (issue === 'excluded' && item.excluded)
    return matchesQuery && matchesStatus && matchesIssue
  })
}

export function sortBatchItems(items: BatchInspectionItem[], sort: BatchSortMode): BatchInspectionItem[] {
  const statusOrder: Record<BatchItemStatus, number> = { failed: 0, warning: 1, success: 2 }
  return [...items].sort((left, right) => {
    if (sort === 'updated-desc') return right.updatedRank - left.updatedRank
    if (sort === 'temperature-asc') return left.temperature - right.temperature
    if (sort === 'status') return statusOrder[left.status] - statusOrder[right.status]
    return left.sourceName.localeCompare(right.sourceName, 'en')
  })
}
