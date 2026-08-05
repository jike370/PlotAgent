export const DESKTOP_API_VERSION = '1.0' as const
export const CORE_PROTOCOL_VERSION = '1.0' as const

export type DesktopApiVersion = typeof DESKTOP_API_VERSION
export type CoreProtocolVersion = typeof CORE_PROTOCOL_VERSION

export type JsonPrimitive = boolean | number | string | null
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue }

export const IPC_CHANNELS = {
  cancelTask: 'plotagent:tasks:cancel',
  closeResponse: 'plotagent:lifecycle:close-response',
  coreStatusChanged: 'plotagent:core:status-changed',
  getBootstrap: 'plotagent:desktop:get-bootstrap',
  getTasks: 'plotagent:tasks:get-snapshot',
  lifecycleCloseRequested: 'plotagent:lifecycle:close-requested',
  openResourceRequested: 'plotagent:resources:open-requested',
  retryCore: 'plotagent:core:retry',
  taskEvent: 'plotagent:tasks:event',
} as const

export type CoreSupervisorPhase =
  | 'stopped'
  | 'starting'
  | 'ready'
  | 'restarting'
  | 'stopping'
  | 'failed'

export type CoreErrorCode =
  | 'CORE_ENTRYPOINT_MISSING'
  | 'CORE_HEARTBEAT_TIMEOUT'
  | 'CORE_NOT_READY'
  | 'CORE_PROCESS_EXITED'
  | 'CORE_PROTOCOL_INVALID_FRAME'
  | 'CORE_PROTOCOL_INVALID_MESSAGE'
  | 'CORE_PROTOCOL_VERSION_UNSUPPORTED'
  | 'CORE_REQUEST_FAILED'
  | 'CORE_REQUEST_TIMEOUT'
  | 'CORE_RESTART_LIMIT_REACHED'
  | 'CORE_SHUTDOWN_TIMEOUT'
  | 'CORE_START_FAILED'
  | 'CORE_START_TIMEOUT'

export interface PublicError {
  readonly code: CoreErrorCode | 'IPC_INVALID_ARGUMENT' | 'TASK_NOT_CANCELLABLE'
  readonly message: string
  readonly retryable: boolean
}

export type DesktopActionResult =
  | { readonly ok: true }
  | { readonly ok: false; readonly error: PublicError }

export interface CoreStatus {
  readonly phase: CoreSupervisorPhase
  readonly restartAttempt: number
  readonly error?: PublicError
}

export type TaskState =
  | 'queued'
  | 'preparing'
  | 'running'
  | 'committing'
  | 'succeeded'
  | 'cancelling'
  | 'cancelled'
  | 'failed'
  | 'partially_succeeded'
  | 'interrupted'

export type TaskProgressUnit = 'rows' | 'files' | 'plots' | 'bytes' | 'steps'

export interface TaskProgress {
  readonly completed: number
  readonly total?: number
  readonly unit: TaskProgressUnit
}

export interface TaskEvent {
  readonly schemaVersion: DesktopApiVersion
  readonly eventType: 'task.state'
  readonly taskId: string
  readonly sequence: number
  readonly state: TaskState
  readonly progress?: TaskProgress
}

export interface TaskSummary {
  readonly taskId: string
  readonly sequence: number
  readonly state: TaskState
  readonly cancellable: boolean
  readonly progress?: TaskProgress
}

export interface TaskSnapshot {
  readonly tasks: readonly TaskSummary[]
  readonly activeTaskCount: number
  readonly hasCommittingTask: boolean
}

export interface DesktopBootstrap {
  readonly apiVersion: DesktopApiVersion
  readonly platform: 'win32' | 'darwin' | 'linux'
  readonly core: CoreStatus
  readonly tasks: TaskSnapshot
}

export interface OpenResourceRequest {
  readonly schemaVersion: DesktopApiVersion
  readonly requestId: string
  readonly resourceId: string
  readonly kind: 'project-package'
}

export type CloseChoice = 'wait' | 'cancel-and-quit' | 'return'

export interface CloseRequest {
  readonly schemaVersion: DesktopApiVersion
  readonly requestId: string
  readonly activeTaskCount: number
  readonly hasCommittingTask: boolean
}

export interface CloseResponse {
  readonly requestId: string
  readonly choice: CloseChoice
}

export type Unsubscribe = () => void

export interface PlotAgentDesktopApi {
  readonly apiVersion: DesktopApiVersion
  getBootstrap(): Promise<DesktopBootstrap>
  getTasks(): Promise<TaskSnapshot>
  cancelTask(taskId: string): Promise<DesktopActionResult>
  retryCore(): Promise<DesktopActionResult>
  respondToCloseRequest(response: CloseResponse): Promise<DesktopActionResult>
  onCoreStatus(listener: (status: CoreStatus) => void): Unsubscribe
  onTaskEvent(listener: (event: TaskEvent) => void): Unsubscribe
  onOpenResourceRequested(listener: (request: OpenResourceRequest) => void): Unsubscribe
  onCloseRequested(listener: (request: CloseRequest) => void): Unsubscribe
}

export interface CoreRpcError {
  readonly code: string
  readonly message: string
  readonly data?: JsonValue
}

interface CoreMessageBase {
  readonly jsonrpc: '2.0'
  readonly protocol_version: CoreProtocolVersion
}

export interface CoreRequest extends CoreMessageBase {
  readonly id: string
  readonly method: string
  readonly params?: JsonValue
}

export interface CoreNotification extends CoreMessageBase {
  readonly method: string
  readonly params?: JsonValue
}

export interface CoreSuccessResponse extends CoreMessageBase {
  readonly id: string
  readonly result: JsonValue
}

export interface CoreErrorResponse extends CoreMessageBase {
  readonly id: string
  readonly error: CoreRpcError
}

export type CoreResponse = CoreSuccessResponse | CoreErrorResponse
export type CoreProtocolMessage = CoreRequest | CoreNotification | CoreResponse

const TASK_STATES = new Set<TaskState>([
  'queued',
  'preparing',
  'running',
  'committing',
  'succeeded',
  'cancelling',
  'cancelled',
  'failed',
  'partially_succeeded',
  'interrupted',
])

const TASK_PROGRESS_UNITS = new Set<TaskProgressUnit>([
  'rows',
  'files',
  'plots',
  'bytes',
  'steps',
])

const CLOSE_CHOICES = new Set<CloseChoice>(['wait', 'cancel-and-quit', 'return'])
const IDENTIFIER_PATTERN = /^[A-Za-z][A-Za-z0-9:._-]{0,127}$/
const METHOD_PATTERN = /^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$/
const ERROR_CODE_PATTERN = /^[A-Z][A-Z0-9_]{0,127}$/

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasExactKeys(
  value: Record<string, unknown>,
  required: readonly string[],
  optional: readonly string[] = [],
): boolean {
  const allowed = new Set([...required, ...optional])
  return required.every((key) => Object.hasOwn(value, key)) &&
    Object.keys(value).every((key) => allowed.has(key))
}

function isIdentifier(value: unknown): value is string {
  return typeof value === 'string' && IDENTIFIER_PATTERN.test(value)
}

export function isJsonValue(value: unknown, depth = 0): value is JsonValue {
  if (depth > 32) return false
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return true
  if (typeof value === 'number') return Number.isFinite(value)
  if (Array.isArray(value)) return value.every((item) => isJsonValue(item, depth + 1))
  if (!isRecord(value)) return false
  return Object.entries(value).every(
    ([key, item]) => key.length <= 128 && isJsonValue(item, depth + 1),
  )
}

function isCoreMessageBase(value: Record<string, unknown>): boolean {
  return value.jsonrpc === '2.0' && value.protocol_version === CORE_PROTOCOL_VERSION
}

function isCoreError(value: unknown): value is CoreRpcError {
  if (!isRecord(value) || !hasExactKeys(value, ['code', 'message'], ['data'])) return false
  return typeof value.code === 'string' &&
    ERROR_CODE_PATTERN.test(value.code) &&
    typeof value.message === 'string' &&
    value.message.length <= 512 &&
    (!Object.hasOwn(value, 'data') || isJsonValue(value.data))
}

export function parseCoreProtocolMessage(value: unknown): CoreProtocolMessage | null {
  if (!isRecord(value) || !isCoreMessageBase(value)) return null

  if (Object.hasOwn(value, 'method')) {
    if (typeof value.method !== 'string' || !METHOD_PATTERN.test(value.method)) return null
    if (Object.hasOwn(value, 'id')) {
      if (!hasExactKeys(value, ['jsonrpc', 'protocol_version', 'id', 'method'], ['params'])) {
        return null
      }
      if (!isIdentifier(value.id)) return null
    } else if (!hasExactKeys(value, ['jsonrpc', 'protocol_version', 'method'], ['params'])) {
      return null
    }
    if (Object.hasOwn(value, 'params') && !isJsonValue(value.params)) return null
    return value as unknown as CoreRequest | CoreNotification
  }

  if (!hasExactKeys(value, ['jsonrpc', 'protocol_version', 'id'], ['result', 'error'])) {
    return null
  }
  if (!isIdentifier(value.id)) return null
  const hasResult = Object.hasOwn(value, 'result')
  const hasError = Object.hasOwn(value, 'error')
  if (hasResult === hasError) return null
  if (hasResult && isJsonValue(value.result)) return value as unknown as CoreSuccessResponse
  if (hasError && isCoreError(value.error)) return value as unknown as CoreErrorResponse
  return null
}

export function createCoreRequest(
  id: string,
  method: string,
  params?: JsonValue,
): CoreRequest {
  const request: CoreRequest = {
    jsonrpc: '2.0',
    protocol_version: CORE_PROTOCOL_VERSION,
    id,
    method,
    ...(params === undefined ? {} : { params }),
  }
  if (parseCoreProtocolMessage(request) === null || !Object.hasOwn(request, 'id')) {
    throw new Error('Invalid Core request')
  }
  return request
}

export function parseTaskEvent(value: unknown): TaskEvent | null {
  if (!isRecord(value) || !hasExactKeys(
    value,
    ['schema_version', 'event_type', 'task_id', 'sequence', 'state'],
    ['progress'],
  )) return null
  if (value.schema_version !== DESKTOP_API_VERSION || value.event_type !== 'task.state') return null
  if (!isIdentifier(value.task_id) || !Number.isSafeInteger(value.sequence) || Number(value.sequence) < 0) {
    return null
  }
  if (typeof value.state !== 'string' || !TASK_STATES.has(value.state as TaskState)) return null

  let progress: TaskProgress | undefined
  if (Object.hasOwn(value, 'progress')) {
    if (!isRecord(value.progress) || !hasExactKeys(value.progress, ['completed', 'unit'], ['total'])) {
      return null
    }
    const { completed, total, unit } = value.progress
    if (!Number.isSafeInteger(completed) || Number(completed) < 0) return null
    if (typeof unit !== 'string' || !TASK_PROGRESS_UNITS.has(unit as TaskProgressUnit)) return null
    if (total !== undefined && (!Number.isSafeInteger(total) || Number(total) < Number(completed))) {
      return null
    }
    progress = {
      completed: Number(completed),
      ...(total === undefined ? {} : { total: Number(total) }),
      unit: unit as TaskProgressUnit,
    }
  }

  return {
    schemaVersion: DESKTOP_API_VERSION,
    eventType: 'task.state',
    taskId: value.task_id,
    sequence: Number(value.sequence),
    state: value.state as TaskState,
    ...(progress === undefined ? {} : { progress }),
  }
}

export function parseTaskId(value: unknown): string | null {
  if (!isRecord(value) || !hasExactKeys(value, ['taskId']) || !isIdentifier(value.taskId)) {
    return null
  }
  return value.taskId
}

export function parseCloseResponse(value: unknown): CloseResponse | null {
  if (!isRecord(value) || !hasExactKeys(value, ['requestId', 'choice'])) return null
  if (!isIdentifier(value.requestId)) return null
  if (typeof value.choice !== 'string' || !CLOSE_CHOICES.has(value.choice as CloseChoice)) {
    return null
  }
  return { requestId: value.requestId, choice: value.choice as CloseChoice }
}

export function isCoreResponse(message: CoreProtocolMessage): message is CoreResponse {
  return Object.hasOwn(message, 'id') && !Object.hasOwn(message, 'method')
}

export function isCoreNotification(message: CoreProtocolMessage): message is CoreNotification {
  return Object.hasOwn(message, 'method') && !Object.hasOwn(message, 'id')
}
