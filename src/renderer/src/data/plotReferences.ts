const STORAGE_PREFIX = 'plotagent.plot-references.v1:'

export interface PlotReference {
  plotId: string
  number: number
}

interface StoredPlotReferences {
  nextNumber: number
  references: PlotReference[]
}

function readStored(storage: Pick<Storage, 'getItem'>, projectId: string): StoredPlotReferences {
  try {
    const raw = storage.getItem(STORAGE_PREFIX + projectId)
    if (raw === null || raw.length > 256_000) return { nextNumber: 1, references: [] }
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return { nextNumber: 1, references: [] }
    const record = parsed as Record<string, unknown>
    const references = Array.isArray(record.references) ? record.references.flatMap((value): PlotReference[] => {
      if (typeof value !== 'object' || value === null || Array.isArray(value)) return []
      const item = value as Record<string, unknown>
      return typeof item.plotId === 'string' && item.plotId.length > 0 && item.plotId.length <= 240
        && Number.isSafeInteger(item.number) && Number(item.number) >= 1
        ? [{ plotId: item.plotId, number: Number(item.number) }]
        : []
    }) : []
    const maximum = references.reduce((value, item) => Math.max(value, item.number), 0)
    const nextNumber = Number.isSafeInteger(record.nextNumber) && Number(record.nextNumber) > maximum
      ? Number(record.nextNumber)
      : maximum + 1
    return { nextNumber, references }
  } catch {
    return { nextNumber: 1, references: [] }
  }
}

export function registerPlotReferences(
  storage: Pick<Storage, 'getItem' | 'setItem'>,
  projectId: string,
  plotIds: readonly string[],
): PlotReference[] {
  const stored = readStored(storage, projectId)
  const byId = new Map(stored.references.map((item) => [item.plotId, item]))
  let nextNumber = stored.nextNumber
  for (const plotId of plotIds) {
    if (byId.has(plotId)) continue
    byId.set(plotId, { plotId, number: nextNumber })
    nextNumber += 1
  }
  const references = [...byId.values()].sort((left, right) => left.number - right.number)
  try {
    storage.setItem(STORAGE_PREFIX + projectId, JSON.stringify({ nextNumber, references }))
  } catch {
    // Stable display references improve usability but must never block plotting.
  }
  return references
}

export function parsePlotMentions(text: string): number[] {
  const numbers: number[] = []
  const seen = new Set<number>()
  for (const match of text.matchAll(/@图([1-9]\d*)/gu)) {
    const number = Number(match[1])
    if (!Number.isSafeInteger(number) || seen.has(number)) continue
    seen.add(number)
    numbers.push(number)
  }
  return numbers
}
