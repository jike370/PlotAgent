import type { ChartType } from './chartCatalog'

export interface DatasetCompatibilitySummary {
  totalFieldCount: number
  statusByProfile?: Readonly<Record<string, 'compatible' | 'incompatible'>>
}

export function chartCompatibility(
  chart: ChartType,
  summary: DatasetCompatibilitySummary | undefined,
): { compatible: boolean; awaitingData?: boolean; checking?: boolean } {
  if (!summary || summary.totalFieldCount === 0) return { compatible: true, awaitingData: true }
  if (summary.statusByProfile === undefined) return { compatible: false, checking: true }
  return { compatible: summary.statusByProfile[chart.id] === 'compatible' }
}
