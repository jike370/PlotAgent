import type { ChartType } from './chartCatalog'

export interface DatasetCompatibilitySummary {
  numericFieldCount: number
  categoricalFieldCount: number
  datetimeFieldCount?: number
  totalFieldCount: number
}

type CompatibilityBucket = 'numeric' | 'categorical' | 'datetime'

const roleBuckets = (fieldTypes: readonly string[]): CompatibilityBucket[] => {
  const buckets = new Set<CompatibilityBucket>()
  if (fieldTypes.includes('numeric')) buckets.add('numeric')
  if (fieldTypes.some((fieldType) => ['categorical', 'text', 'boolean'].includes(fieldType))) {
    buckets.add('categorical')
  }
  if (fieldTypes.includes('datetime')) buckets.add('datetime')
  return [...buckets]
}

const requiredRolesCanBeAssigned = (
  chart: ChartType,
  summary: DatasetCompatibilitySummary,
): boolean => {
  const roles = chart.requiredFields
    .map((role) => roleBuckets(chart.roleFieldTypes[role] ?? []))
    .sort((left, right) => left.length - right.length)
  if (roles.some((buckets) => buckets.length === 0)) return false

  const remaining: Record<CompatibilityBucket, number> = {
    numeric: summary.numericFieldCount,
    categorical: summary.categoricalFieldCount,
    datetime: summary.datetimeFieldCount ?? 0,
  }
  const assign = (index: number): boolean => {
    if (index === roles.length) return true
    for (const bucket of roles[index]) {
      if (remaining[bucket] === 0) continue
      remaining[bucket] -= 1
      if (assign(index + 1)) return true
      remaining[bucket] += 1
    }
    return false
  }
  return assign(0)
}

export function chartCompatibility(
  chart: ChartType,
  summary: DatasetCompatibilitySummary | undefined,
): { compatible: boolean; awaitingData?: boolean } {
  if (!summary || summary.totalFieldCount === 0) return { compatible: true, awaitingData: true }
  return {
    compatible: requiredRolesCanBeAssigned(chart, summary),
  }
}
