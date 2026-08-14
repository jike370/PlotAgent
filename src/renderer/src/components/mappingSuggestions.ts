import type { ProductDataset } from '../data/productState'

export interface MappingSuggestionRole {
  role: string
  numeric: boolean
  datetime?: boolean
  required: boolean
}

const numericKinds = new Set(['numeric', 'integer', 'float', 'double', 'decimal'])
const datetimeKinds = new Set(['date', 'datetime', 'time', 'timestamp'])

export function fieldMatchesRole(
  role: MappingSuggestionRole,
  field: ProductDataset['fields'][number],
): boolean {
  const logicalType = field.logicalType.toLocaleLowerCase('en-US')
  if (role.datetime) return datetimeKinds.has(logicalType)
  if (role.numeric) return numericKinds.has(logicalType)
  return !numericKinds.has(logicalType) && !datetimeKinds.has(logicalType)
}

export function suggestedFieldMapping(
  roles: MappingSuggestionRole[],
  dataset: ProductDataset,
): Record<string, string> {
  const normalizedName = (name: string): string => name.toLocaleLowerCase('en-US').replace(/[^a-z0-9]+/g, '')
  const optionalHints: Record<string, string[]> = {
    color: ['color', 'colour'],
    count: ['count', 'frequency', 'freq', 'weight'],
    error: ['error', 'err'],
    group: ['group', 'series', 'condition', 'class', 'treatment'],
    label: ['label', 'name'],
    middle: ['middle', 'mid'],
    pvalue: ['pvalue', 'pval'],
    qvalue: ['qvalue', 'qval', 'fdr'],
    series_2: ['series2'],
    series_3: ['series3'],
    size: ['size', 'bubble'],
    time: ['timestamp', 'datetime', 'date', 'time'],
  }
  const used = new Set<string>()
  const mapping: Record<string, string> = {}
  const orderedRoles = [...roles.filter((role) => role.required), ...roles.filter((role) => !role.required)]
  for (const role of orderedRoles) {
    const candidates = dataset.fields.filter((field) => fieldMatchesRole(role, field))
    const hints = optionalHints[role.role] ?? [normalizedName(role.role)]
    const matchingField = candidates.find((candidate) => {
      if (used.has(candidate.fieldId)) return false
      const name = normalizedName(candidate.name)
      return hints.some((hint) => name.includes(hint))
    })
    const field = matchingField ?? (role.required
      ? candidates.find((candidate) => !used.has(candidate.fieldId))
      : undefined)
    if (!field) continue
    mapping[role.role] = field.fieldId
    used.add(field.fieldId)
  }
  return mapping
}
