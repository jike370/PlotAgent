import type { ChartType } from './chartCatalog'

export interface DatasetCompatibilitySummary {
  numericFieldCount: number
  categoricalFieldCount: number
  totalFieldCount: number
}

export function chartCompatibility(
  chart: ChartType,
  summary: DatasetCompatibilitySummary | undefined,
  availablePlotCount: number,
): { compatible: boolean; awaitingData?: boolean } {
  if (chart.id === 'K25') return { compatible: availablePlotCount >= 2 }
  if (!summary || summary.totalFieldCount === 0) return { compatible: true, awaitingData: true }
  const numericRequirements: Record<string, number> = {
    K04: 3, K06: 3, K07: 4, K09: 1, K10: 1, K11: 1, K20: 1, K21: 2, K22: 3,
    S61: 0,
  }
  const totalRequirements: Record<string, number> = {
    K04: 3, K06: 3, K07: 4, K09: 3, K10: 3, K11: 3, K20: 3, K22: 3,
    K24: 3, S61: 2,
  }
  const numericNeeded = numericRequirements[chart.id] ?? (['K08', 'K12', 'K13', 'K14', 'K15'].includes(chart.id) ? 1 : 2)
  const totalNeeded = totalRequirements[chart.id] ?? Math.max(numericNeeded, Math.min(chart.requiredFields.length, 4))
  return {
    compatible: summary.numericFieldCount >= numericNeeded && summary.totalFieldCount >= totalNeeded,
  }
}
