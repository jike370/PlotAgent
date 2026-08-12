const STORAGE_PREFIX = 'plotagent.conversation.v1:'
const MAX_MESSAGES = 100
const MAX_TEXT_LENGTH = 4_000

export interface ConversationMessage {
  id: string
  role: 'user' | 'agent'
  title?: string
  text: string
  createdAt: string
  kind?: 'info' | 'success' | 'warning' | 'error'
}

function isMessage(value: unknown): value is ConversationMessage {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false
  const record = value as Record<string, unknown>
  return typeof record.id === 'string'
    && record.id.length <= 160
    && (record.role === 'user' || record.role === 'agent')
    && (record.title === undefined || (typeof record.title === 'string' && record.title.length <= 256))
    && typeof record.text === 'string'
    && record.text.length > 0
    && record.text.length <= MAX_TEXT_LENGTH
    && typeof record.createdAt === 'string'
    && record.createdAt.length <= 64
    && (record.kind === undefined || ['info', 'success', 'warning', 'error'].includes(String(record.kind)))
}

export function readConversationMessages(
  storage: Pick<Storage, 'getItem'>,
  projectId: string,
): ConversationMessage[] {
  try {
    const raw = storage.getItem(STORAGE_PREFIX + projectId)
    if (raw === null || raw.length > 512_000) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(isMessage).slice(-MAX_MESSAGES)
  } catch {
    return []
  }
}

export function writeConversationMessages(
  storage: Pick<Storage, 'setItem'>,
  projectId: string,
  messages: readonly ConversationMessage[],
): void {
  try {
    storage.setItem(STORAGE_PREFIX + projectId, JSON.stringify(messages.slice(-MAX_MESSAGES)))
  } catch {
    // Conversation persistence is non-critical and must never block plotting.
  }
}
