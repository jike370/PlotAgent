import type { WorkflowPlanView, ProductPlot } from './productState'

const LEGACY_STORAGE_PREFIX = 'plotagent.conversation.v1:'
const STORAGE_PREFIX = 'plotagent.conversation.v2:'
const MAX_ITEMS = 160
const MAX_TEXT_LENGTH = 4_000
const MAX_STORAGE_LENGTH = 2_000_000

interface TimelineItemBase {
  id: string
  createdAt: string
  turnId?: string
}

export interface ConversationTextItem extends TimelineItemBase {
  type: 'text'
  role: 'user' | 'agent'
  title?: string
  text: string
  questions?: string[]
  kind?: 'info' | 'success' | 'warning' | 'error'
}

export interface ConversationPlanItem extends TimelineItemBase {
  type: 'plan'
  plan: WorkflowPlanView
}

export interface ConversationPlotItem extends TimelineItemBase {
  type: 'plot'
  plotNumber: number
  plot: ProductPlot
}

export interface ConversationExportRecord {
  exportId: string
  resourceId: string
  fileName: string
  format: 'png' | 'svg' | 'opju'
  targetId: string
  plotVersion?: number
  artifactHash?: string
  artifactSize?: number
}

export interface ConversationExportItem extends TimelineItemBase {
  type: 'export'
  record: ConversationExportRecord
}

export type ConversationTimelineItem = ConversationTextItem | ConversationPlanItem | ConversationPlotItem | ConversationExportItem

function isBoundedString(value: unknown, maximum: number, allowEmpty = false): value is string {
  return typeof value === 'string' && value.length <= maximum && (allowEmpty || value.length > 0)
}

function isBaseItem(record: Record<string, unknown>): boolean {
  return isBoundedString(record.id, 200)
    && isBoundedString(record.createdAt, 64)
    && (record.turnId === undefined || isBoundedString(record.turnId, 200))
}

function isTextItem(record: Record<string, unknown>): boolean {
  return record.type === 'text'
    && (record.role === 'user' || record.role === 'agent')
    && (record.title === undefined || isBoundedString(record.title, 256, true))
    && isBoundedString(record.text, MAX_TEXT_LENGTH)
    && (record.questions === undefined || (
      Array.isArray(record.questions)
      && record.questions.length <= 20
      && record.questions.every((question) => isBoundedString(question, MAX_TEXT_LENGTH))
    ))
    && (record.kind === undefined || ['info', 'success', 'warning', 'error'].includes(String(record.kind)))
}

function isPlanItem(record: Record<string, unknown>): boolean {
  if (record.type !== 'plan' || typeof record.plan !== 'object' || record.plan === null || Array.isArray(record.plan)) return false
  const plan = record.plan as Record<string, unknown>
  return isBoundedString(plan.planId, 240) && isBoundedString(plan.state, 80)
    && Array.isArray(plan.steps) && plan.steps.length <= 100
}

function isPlotItem(record: Record<string, unknown>): boolean {
  if (record.type !== 'plot' || !Number.isSafeInteger(record.plotNumber) || Number(record.plotNumber) < 1) return false
  if (typeof record.plot !== 'object' || record.plot === null || Array.isArray(record.plot)) return false
  const plot = record.plot as Record<string, unknown>
  return isBoundedString(plot.plotId, 240)
    && Number.isSafeInteger(plot.plotVersion)
    && Number(plot.plotVersion) >= 1
    && isBoundedString(plot.chartId, 80)
}

function isExportItem(record: Record<string, unknown>): boolean {
  if (record.type !== 'export' || typeof record.record !== 'object' || record.record === null || Array.isArray(record.record)) return false
  const value = record.record as Record<string, unknown>
  return isBoundedString(value.exportId, 240)
    && isBoundedString(value.resourceId, 320)
    && isBoundedString(value.fileName, 512)
    && ['png', 'svg', 'opju'].includes(String(value.format))
    && isBoundedString(value.targetId, 240)
    && (value.plotVersion === undefined || (Number.isSafeInteger(value.plotVersion) && Number(value.plotVersion) >= 1))
}

function isTimelineItem(value: unknown): value is ConversationTimelineItem {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false
  const record = value as Record<string, unknown>
  return isBaseItem(record) && (isTextItem(record) || isPlanItem(record) || isPlotItem(record) || isExportItem(record))
}

function parseItems(raw: string | null): ConversationTimelineItem[] {
  if (raw === null || raw.length > MAX_STORAGE_LENGTH) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(isTimelineItem).slice(-MAX_ITEMS)
  } catch {
    return []
  }
}

function migrateLegacyMessages(raw: string | null): ConversationTimelineItem[] {
  if (raw === null || raw.length > 512_000) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.flatMap((value): ConversationTimelineItem[] => {
      if (typeof value !== 'object' || value === null || Array.isArray(value)) return []
      const record = value as Record<string, unknown>
      if (!isBoundedString(record.id, 160)
        || (record.role !== 'user' && record.role !== 'agent')
        || !isBoundedString(record.text, MAX_TEXT_LENGTH)
        || !isBoundedString(record.createdAt, 64)) return []
      return [{
        type: 'text', id: record.id, role: record.role, text: record.text, createdAt: record.createdAt,
        ...(typeof record.title === 'string' ? { title: record.title.slice(0, 256) } : {}),
        ...(['info', 'success', 'warning', 'error'].includes(String(record.kind))
          ? { kind: record.kind as ConversationTextItem['kind'] }
          : {}),
      }]
    }).slice(-MAX_ITEMS)
  } catch {
    return []
  }
}

export function readConversationTimeline(storage: Pick<Storage, 'getItem'>, projectId: string): ConversationTimelineItem[] {
  const current = storage.getItem(STORAGE_PREFIX + projectId)
  return current === null
    ? migrateLegacyMessages(storage.getItem(LEGACY_STORAGE_PREFIX + projectId))
    : parseItems(current)
}

export function writeConversationTimeline(
  storage: Pick<Storage, 'setItem'>,
  projectId: string,
  items: readonly ConversationTimelineItem[],
): void {
  try {
    storage.setItem(STORAGE_PREFIX + projectId, JSON.stringify(items.slice(-MAX_ITEMS)))
  } catch {
    // Conversation persistence is non-critical and must never block plotting.
  }
}
