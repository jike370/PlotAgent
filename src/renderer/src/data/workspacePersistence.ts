import type { FieldMappingInput } from '../../../shared/desktop-contract'

const STORAGE_PREFIX = 'plotagent.workspace.v2:'
const WORKFLOW_SOURCE_MODE = 'explicit_extras_v1'

export interface PersistedWorkspaceSelection {
  datasetId?: string
  workflowSourceIds?: string[]
  chartId?: string
  mapping?: FieldMappingInput
}

function isSafeId(value: unknown): value is string {
  return typeof value === 'string' && /^[A-Za-z][A-Za-z0-9:._-]{0,191}$/.test(value)
}

function readMapping(value: unknown): FieldMappingInput | undefined {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return undefined
  const roles = (value as { roles?: unknown }).roles
  if (typeof roles !== 'object' || roles === null || Array.isArray(roles)) return undefined
  const entries = Object.entries(roles)
  if (entries.length === 0 || entries.length > 64 || entries.some(([role, fieldId]) => (
    !/^[a-z][a-z0-9_]{0,63}$/.test(role) || !isSafeId(fieldId)
  ))) return undefined
  return { roles: Object.fromEntries(entries) as Record<string, string> }
}

export function readWorkspaceSelection(
  storage: Pick<Storage, 'getItem'>,
  projectId: string,
): PersistedWorkspaceSelection | undefined {
  try {
    const raw = storage.getItem(STORAGE_PREFIX + projectId)
    if (raw === null || raw.length > 16_384) return undefined
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return undefined
    const record = parsed as { datasetId?: unknown; workflowSourceIds?: unknown; workflowSourceMode?: unknown; chartId?: unknown; mapping?: unknown }
    const datasetId = isSafeId(record.datasetId) ? record.datasetId : undefined
    const workflowSourceIds = record.workflowSourceMode === WORKFLOW_SOURCE_MODE
      && Array.isArray(record.workflowSourceIds)
      && record.workflowSourceIds.length > 0
      && record.workflowSourceIds.length <= 8
      && record.workflowSourceIds.every(isSafeId)
      && new Set(record.workflowSourceIds).size === record.workflowSourceIds.length
      ? record.workflowSourceIds : undefined
    const chartId = isSafeId(record.chartId) ? record.chartId : undefined
    const mapping = readMapping(record.mapping)
    if (datasetId === undefined && workflowSourceIds === undefined && chartId === undefined && mapping === undefined) return undefined
    return {
      ...(datasetId === undefined ? {} : { datasetId }),
      ...(workflowSourceIds === undefined ? {} : { workflowSourceIds }),
      ...(chartId === undefined ? {} : { chartId }),
      ...(mapping === undefined ? {} : { mapping }),
    }
  } catch {
    return undefined
  }
}

export function writeWorkspaceSelection(
  storage: Pick<Storage, 'setItem'>,
  projectId: string,
  selection: PersistedWorkspaceSelection,
): void {
  try {
    storage.setItem(STORAGE_PREFIX + projectId, JSON.stringify({ ...selection, workflowSourceMode: WORKFLOW_SOURCE_MODE }))
  } catch {
    // Workspace persistence is a convenience; storage failures must not block plotting.
  }
}
