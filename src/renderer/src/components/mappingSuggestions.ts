import type { ProductDataset } from '../data/productState'

export interface MappingSuggestionRole {
  role: string
  numeric: boolean
  required: boolean
}

const numericKinds = new Set(['numeric', 'integer', 'float', 'double', 'decimal'])

export function suggestedFieldMapping(
  roles: MappingSuggestionRole[],
  dataset: ProductDataset,
): Record<string, string> {
  const numeric = dataset.fields.filter((field) => numericKinds.has(field.logicalType.toLocaleLowerCase('en-US')))
  const other = dataset.fields.filter((field) => !numeric.includes(field))
  const normalizedName = (name: string): string => name.toLocaleLowerCase('en-US').replace(/[^a-z0-9]+/g, '')
  const optionalHints: Record<string, string[]> = {
    color: ['color', 'colour'],
    count: ['count', 'frequency', 'freq', 'weight'],
    error: ['error', 'err'],
    group: ['group', 'condition', 'class', 'treatment'],
    label: ['label', 'name'],
    middle: ['middle', 'mid'],
    pvalue: ['pvalue', 'pval'],
    qvalue: ['qvalue', 'qval', 'fdr'],
    series_2: ['series2'],
    series_3: ['series3'],
    size: ['size', 'bubble'],
  }
  const used = new Set<string>()
  const mapping: Record<string, string> = {}
  const orderedRoles = [...roles.filter((role) => role.required), ...roles.filter((role) => !role.required)]
  for (const role of orderedRoles) {
    const candidates = role.numeric ? numeric : other.length > 0 ? other : dataset.fields
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
