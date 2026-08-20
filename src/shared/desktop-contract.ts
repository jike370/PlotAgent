export const DESKTOP_API_VERSION = '1.0' as const
export const CORE_PROTOCOL_VERSION = '1.0' as const

export type DesktopApiVersion = typeof DESKTOP_API_VERSION
export type CoreProtocolVersion = typeof CORE_PROTOCOL_VERSION

export type JsonPrimitive = boolean | number | string | null
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue }

export const IPC_CHANNELS = {
  workflowRun: 'plotagent:workflow:run',
  workflowRuntimeEvent: 'plotagent:workflow:runtime-event',
  taskPlanConfirm: 'plotagent:workflow:plan-confirm',
  taskPlanGet: 'plotagent:workflow:plan-get',
  taskPlanList: 'plotagent:workflow:plan-list',
  taskPlanResume: 'plotagent:workflow:plan-resume',
  taskPlanRun: 'plotagent:workflow:plan-run',
  cancelTask: 'plotagent:tasks:cancel',
  acceptPartialTask: 'plotagent:tasks:accept-partial',
  resumeAgentTask: 'plotagent:tasks:resume-agent',
  closeResponse: 'plotagent:lifecycle:close-response',
  coreStatusChanged: 'plotagent:core:status-changed',
  datasetDescribe: 'plotagent:datasets:describe',
  datasetImport: 'plotagent:datasets:import',
  datasetList: 'plotagent:datasets:list',
  exportOrigin: 'plotagent:exports:origin',
  exportPngSvg: 'plotagent:exports:png-svg',
  getBootstrap: 'plotagent:desktop:get-bootstrap',
  getTasks: 'plotagent:tasks:get-snapshot',
  lifecycleCloseRequested: 'plotagent:lifecycle:close-requested',
  openResourceRequested: 'plotagent:resources:open-requested',
  originStatus: 'plotagent:origin:status',
  engineActionExecute: 'plotagent:engine:actions:execute',
  enginePlotGet: 'plotagent:engine:plots:get',
  enginePlotList: 'plotagent:engine:plots:list',
  providerClear: 'plotagent:provider:clear',
  providerConfigure: 'plotagent:provider:configure',
  providerStatus: 'plotagent:provider:status',
  projectClose: 'plotagent:projects:close',
  projectCreate: 'plotagent:projects:create',
  projectDelete: 'plotagent:projects:delete',
  projectActivate: 'plotagent:projects:activate',
  projectList: 'plotagent:projects:list',
  projectOpen: 'plotagent:projects:open',
  projectOpenResource: 'plotagent:projects:open-resource',
  projectOpenSample: 'plotagent:projects:open-sample',
  projectRename: 'plotagent:projects:rename',
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
  readonly code: CoreErrorCode
    | 'DIALOG_CANCELLED'
    | 'IPC_INVALID_ARGUMENT'
    | 'ORIGIN_UNAVAILABLE'
    | 'RESOURCE_INVALID'
    | 'TASK_NOT_CANCELLABLE'
    | 'TASK_PARTIAL_RESULT_UNAVAILABLE'
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

export interface TaskFailure {
  readonly code: string
  readonly message: string
}

export interface TaskEvent {
  readonly schemaVersion: DesktopApiVersion
  readonly eventType: 'task.state'
  readonly taskId: string
  readonly sequence: number
  readonly state: TaskState
  readonly taskKind?: string
  readonly label?: string
  readonly progress?: TaskProgress
  readonly error?: TaskFailure
}

export interface TaskSummary {
  readonly taskId: string
  readonly sequence: number
  readonly state: TaskState
  readonly cancellable: boolean
  readonly taskKind?: string
  readonly label?: string
  readonly progress?: TaskProgress
  readonly error?: TaskFailure
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

export type DesktopResourceKind =
  | 'project-package'
  | 'import-source'
  | 'preview'
  | 'export'

export interface DesktopResource {
  readonly resourceId: string
  readonly kind: DesktopResourceKind
  readonly url?: string
  readonly mimeType?: 'image/png' | 'image/svg+xml'
  readonly byteLength?: number
  readonly fileName?: string
}

export interface OpenResourceRequest {
  readonly schemaVersion: DesktopApiVersion
  readonly requestId: string
  readonly resourceId: string
  readonly kind: 'project-package'
}

export type DesktopDataResult =
  | { readonly ok: true; readonly value: JsonValue }
  | { readonly ok: false; readonly error: PublicError }

export interface ProjectIdInput {
  readonly projectId: string
}

export interface ProjectResourceInput {
  readonly resourceId: string
}

export interface ProjectCreateInput {
  readonly name: string
}

export interface ProjectRenameInput extends ProjectIdInput {
  readonly name: string
}

export interface CustomProviderConfigureInput {
  readonly baseUrl: string
  readonly modelId: string
  readonly apiKey?: string
  readonly retentionAcknowledged: true
}

export interface DatasetDescribeInput extends ProjectIdInput {
  readonly datasetId: string
  readonly sourceVersion: number
}

export interface FieldMappingInput {
  readonly roles: Readonly<Record<string, string>>
}

export interface EngineActionInput extends ProjectIdInput {
  readonly expectedProjectVersion: number
  readonly action: JsonValue
}

export interface PlotIdInput extends ProjectIdInput {
  readonly plotId: string
  readonly plotVersion: number
}

export interface WorkflowRunInput extends ProjectIdInput {
  readonly selectedSources: readonly {
    readonly datasetId: string
    readonly sourceVersion: number
  }[]
  readonly expectedProjectVersion: number
  readonly selectedProfileIds?: readonly string[]
  readonly selectedPlotIds?: readonly string[]
  readonly continuationWorkflowRunId?: string
  readonly instruction: string
}

export type WorkflowRuntimeStage =
  | 'preparing_context'
  | 'inspecting_data'
  | 'planning'
  | 'validating_draft'
  | 'saving_plan'
  | 'completed'
  | 'cancelled'
  | 'failed'

export interface WorkflowRuntimeEvent {
  readonly schemaVersion: DesktopApiVersion
  readonly runId: string
  readonly projectId: string
  readonly taskId?: string
  readonly sequence: number
  readonly stage: WorkflowRuntimeStage
  readonly label: string
}

export interface TaskPlanInput extends ProjectIdInput {
  readonly planId: string
}

export interface TaskPlanConfirmInput extends TaskPlanInput {
  readonly accept: boolean
}

export interface PngSvgExportInput extends ProjectIdInput {
  readonly target: {
    readonly kind: 'plot'
    readonly id: string
    readonly version: number
  }
  readonly format: 'png' | 'svg'
}

export interface OriginExportInput extends ProjectIdInput {
  readonly target: {
    readonly kind: 'plot'
    readonly id: string
    readonly version: number
  }
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
  acceptPartialTask(taskId: string): Promise<DesktopActionResult>
  resumeAgentTask(taskId: string): Promise<DesktopDataResult>
  retryCore(): Promise<DesktopActionResult>
  getProviderStatus(): Promise<DesktopDataResult>
  configureCustomProvider(input: CustomProviderConfigureInput): Promise<DesktopDataResult>
  clearProvider(): Promise<DesktopDataResult>
  getOriginStatus(): Promise<DesktopDataResult>
  listProjects(): Promise<DesktopDataResult>
  createProject(input: ProjectCreateInput): Promise<DesktopDataResult>
  renameProject(input: ProjectRenameInput): Promise<DesktopDataResult>
  deleteProject(input: ProjectIdInput): Promise<DesktopDataResult>
  activateProject(input: ProjectIdInput): Promise<DesktopDataResult>
  openProject(): Promise<DesktopDataResult>
  openProjectResource(input: ProjectResourceInput): Promise<DesktopDataResult>
  openSampleProject(): Promise<DesktopDataResult>
  closeProject(input: ProjectIdInput): Promise<DesktopDataResult>
  importDatasets(input: ProjectIdInput): Promise<DesktopDataResult>
  listDatasets(input: ProjectIdInput): Promise<DesktopDataResult>
  describeDataset(input: DatasetDescribeInput): Promise<DesktopDataResult>
  executePlotAction(input: EngineActionInput): Promise<DesktopDataResult>
  getPlot(input: PlotIdInput): Promise<DesktopDataResult>
  listPlots(input: ProjectIdInput): Promise<DesktopDataResult>
  runWorkflow(input: WorkflowRunInput): Promise<DesktopDataResult>
  getTaskPlan(input: TaskPlanInput): Promise<DesktopDataResult>
  listTaskPlans(input: ProjectIdInput): Promise<DesktopDataResult>
  confirmTaskPlan(input: TaskPlanConfirmInput): Promise<DesktopDataResult>
  runTaskPlan(input: TaskPlanInput): Promise<DesktopDataResult>
  resumeTaskPlan(input: TaskPlanInput): Promise<DesktopDataResult>
  exportPngSvg(input: PngSvgExportInput): Promise<DesktopDataResult>
  exportOrigin(input: OriginExportInput): Promise<DesktopDataResult>
  respondToCloseRequest(response: CloseResponse): Promise<DesktopActionResult>
  onCoreStatus(listener: (status: CoreStatus) => void): Unsubscribe
  onTaskEvent(listener: (event: TaskEvent) => void): Unsubscribe
  onWorkflowRuntimeEvent(listener: (event: WorkflowRuntimeEvent) => void): Unsubscribe
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
const CHART_IDS = new Set([
  'K01', 'K02', 'K03', 'K04', 'K05', 'K06', 'K07', 'K08', 'K09', 'K10', 'K11',
  'K12', 'K13', 'K14', 'K15', 'K17', 'K18', 'K19', 'K20', 'K21', 'K22',
  'K24', 'S05', 'S25', 'S31', 'S34', 'S61',
  'X01', 'X02', 'X03', 'X05', 'X07', 'X09', 'X11', 'X12', 'X13', 'X15', 'X16',
  'X17', 'X18', 'X19', 'X23', 'X24', 'X35', 'X36', 'X37', 'X38', 'X39', 'X40',
  'S07',
])
const IDENTIFIER_PATTERN = /^[A-Za-z][A-Za-z0-9:._-]{0,127}$/
const METHOD_PATTERN = /^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$/
const ERROR_CODE_PATTERN = /^[A-Z][A-Z0-9_]{0,127}$/
const FORBIDDEN_PAYLOAD_KEY = /(?:path|secret|token|credential|api[_-]?key)/i
const ABSOLUTE_PATH_VALUE = /^(?:[A-Za-z]:[\\/]|\\\\|file:\/\/)/i

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

function hasControlCharacter(value: string): boolean {
  return [...value].some((character) => character.charCodeAt(0) < 32)
}

function isShortText(value: unknown, maximum: number): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= maximum &&
    !hasControlCharacter(value)
}

export function isSafeRendererPayload(value: unknown, depth = 0): value is JsonValue {
  if (depth > 12 || !isJsonValue(value, depth)) return false
  if (typeof value === 'string') return value.length <= 16_384 && !ABSOLUTE_PATH_VALUE.test(value)
  if (Array.isArray(value)) {
    return value.length <= 512 && value.every((item) => isSafeRendererPayload(item, depth + 1))
  }
  if (!isRecord(value)) return true
  const entries = Object.entries(value)
  return entries.length <= 256 && entries.every(([key, item]) => (
    !FORBIDDEN_PAYLOAD_KEY.test(key) && isSafeRendererPayload(item, depth + 1)
  ))
}

function parseProjectIdRecord(value: unknown, extraKeys: readonly string[] = []): Record<string, unknown> | null {
  if (!isRecord(value) || !hasExactKeys(value, ['projectId', ...extraKeys])) return null
  return isIdentifier(value.projectId) ? value : null
}

function parseId(value: unknown): string | null {
  return isIdentifier(value) ? value : null
}

function parseVersion(value: unknown, minimum = 0): number | null {
  return Number.isSafeInteger(value) && Number(value) >= minimum ? Number(value) : null
}

function parseTarget(value: unknown): { readonly kind: 'plot'; readonly id: string } | null {
  if (!isRecord(value) || !hasExactKeys(value, ['kind', 'id'])) return null
  if (value.kind !== 'plot') return null
  const id = parseId(value.id)
  return id === null ? null : { kind: value.kind, id }
}

function parseVersionedTarget(value: unknown): PngSvgExportInput['target'] | null {
  if (!isRecord(value) || !hasExactKeys(value, ['kind', 'id', 'version'])) return null
  const target = parseTarget({ kind: value.kind, id: value.id })
  const version = parseVersion(value.version, 1)
  return target === null || version === null ? null : { ...target, version }
}

export function parseProjectCreateInput(value: unknown): ProjectCreateInput | null {
  if (!isRecord(value) || !hasExactKeys(value, ['name'])) return null
  if (typeof value.name !== 'string') return null
  const name = value.name.trim()
  if (name.length === 0 || name.length > 120 || [...name].some((character) => character.charCodeAt(0) < 32)) return null
  return { name }
}

export function parseProjectRenameInput(value: unknown): ProjectRenameInput | null {
  if (!isRecord(value) || !hasExactKeys(value, ['projectId', 'name'])) return null
  const projectId = parseId(value.projectId)
  if (projectId === null || typeof value.name !== 'string') return null
  const name = value.name.trim()
  if (name.length === 0 || name.length > 120 || hasControlCharacter(name)) return null
  return { projectId, name }
}

export function parseCustomProviderConfigureInput(value: unknown): CustomProviderConfigureInput | null {
  if (!isRecord(value) || !hasExactKeys(value, ['baseUrl', 'modelId', 'retentionAcknowledged'], ['apiKey'])) return null
  if (value.retentionAcknowledged !== true || typeof value.baseUrl !== 'string' || typeof value.modelId !== 'string') return null
  let endpoint: URL
  try {
    endpoint = new URL(value.baseUrl)
  } catch {
    return null
  }
  const hostname = endpoint.hostname.toLocaleLowerCase('en-US')
  const loopback = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]' || hostname === '::1'
  const allowedTransport = endpoint.protocol === 'https:' || (endpoint.protocol === 'http:' && loopback)
  if (!allowedTransport || endpoint.username || endpoint.password || endpoint.hash || endpoint.search) return null
  const modelId = value.modelId.trim()
  if (modelId.length === 0 || modelId.length > 128 || hasControlCharacter(modelId)) return null
  if (value.apiKey !== undefined && (typeof value.apiKey !== 'string' || value.apiKey.length < 8 || value.apiKey.length > 4096 || hasControlCharacter(value.apiKey))) return null
  return {
    baseUrl: endpoint.toString().replace(/\/$/, ''),
    modelId,
    ...(typeof value.apiKey === 'string' ? { apiKey: value.apiKey } : {}),
    retentionAcknowledged: true,
  }
}

export function parseProjectIdInput(value: unknown): ProjectIdInput | null {
  const parsed = parseProjectIdRecord(value)
  return parsed === null ? null : { projectId: parsed.projectId as string }
}

export function parseProjectResourceInput(value: unknown): ProjectResourceInput | null {
  if (!isRecord(value) || !hasExactKeys(value, ['resourceId']) || !isIdentifier(value.resourceId)) {
    return null
  }
  return { resourceId: value.resourceId }
}

export function parseDatasetDescribeInput(value: unknown): DatasetDescribeInput | null {
  const parsed = parseProjectIdRecord(value, ['datasetId', 'sourceVersion'])
  const datasetId = parsed === null ? null : parseId(parsed.datasetId)
  const sourceVersion = parsed === null ? null : parseVersion(parsed.sourceVersion, 1)
  return parsed === null || datasetId === null || sourceVersion === null
    ? null
    : { projectId: parsed.projectId as string, datasetId, sourceVersion }
}

const ENGINE_OPERATIONS = new Set([
  'create_plot', 'bind_fields', 'set_title', 'set_axis', 'set_series_style',
  'set_legend', 'set_colormap', 'set_error_style', 'set_data_labels',
  'set_chart_parameter', 'add_annotation', 'export_plot',
])

export function parseEngineActionInput(value: unknown): EngineActionInput | null {
  const parsed = parseProjectIdRecord(value, ['expectedProjectVersion', 'action'])
  if (parsed === null || !isRecord(parsed.action)) return null
  const expectedProjectVersion = parseVersion(parsed.expectedProjectVersion)
  if (
    expectedProjectVersion === null
    || typeof parsed.action.operation !== 'string'
    || !ENGINE_OPERATIONS.has(parsed.action.operation)
    || !isSafeRendererPayload(parsed.action)
  ) return null
  return {
    projectId: parsed.projectId as string,
    expectedProjectVersion,
    action: parsed.action as JsonValue,
  }
}

export function parsePlotIdInput(value: unknown): PlotIdInput | null {
  const parsed = parseProjectIdRecord(value, ['plotId', 'plotVersion'])
  const plotId = parsed === null ? null : parseId(parsed.plotId)
  const plotVersion = parsed === null ? null : parseVersion(parsed.plotVersion, 1)
  return parsed === null || plotId === null || plotVersion === null ? null : { projectId: parsed.projectId as string, plotId, plotVersion }
}

export function parseWorkflowRunInput(value: unknown): WorkflowRunInput | null {
  if (!isRecord(value) || !hasExactKeys(
    value,
    ['projectId', 'selectedSources', 'expectedProjectVersion', 'instruction'],
    [
      'selectedProfileIds',
      'selectedPlotIds',
      'continuationWorkflowRunId',
    ],
  )) return null
  const projectId = parseId(value.projectId)
  const expectedProjectVersion = parseVersion(value.expectedProjectVersion)
  if (projectId === null || expectedProjectVersion === null || !Array.isArray(value.selectedSources)) return null
  const selectedSources = value.selectedSources.map((item) => {
    if (!isRecord(item) || !hasExactKeys(item, ['datasetId', 'sourceVersion'])) return null
    const datasetId = parseId(item.datasetId)
    const sourceVersion = parseVersion(item.sourceVersion, 1)
    return datasetId === null || sourceVersion === null ? null : { datasetId, sourceVersion }
  })
  if (selectedSources.length > 8 || selectedSources.some((item) => item === null)) return null
  const sourceKeys = selectedSources.map((item) => `${item?.datasetId}:${item?.sourceVersion}`)
  if (new Set(sourceKeys).size !== sourceKeys.length) return null
  const instruction = typeof value.instruction === 'string' ? value.instruction.trim() : ''
  if (!instruction || instruction.length > 4_096 || instruction.includes('\0')) return null
  const selectedProfileIds = value.selectedProfileIds === undefined
    ? undefined
    : Array.isArray(value.selectedProfileIds)
      && value.selectedProfileIds.length <= 8
      && value.selectedProfileIds.every((item) => typeof item === 'string' && CHART_IDS.has(item))
      ? value.selectedProfileIds as string[] : null
  const selectedPlotIds = value.selectedPlotIds === undefined
    ? undefined
    : Array.isArray(value.selectedPlotIds)
      && value.selectedPlotIds.length <= 8
      && value.selectedPlotIds.every((item) => parseId(item) !== null)
      ? value.selectedPlotIds as string[] : null
  const continuationWorkflowRunId = value.continuationWorkflowRunId === undefined
    ? undefined : parseId(value.continuationWorkflowRunId)
  if (
    selectedProfileIds === null
    || selectedPlotIds === null
    || continuationWorkflowRunId === null
  ) return null
  if (
    selectedSources.length === 0
    && (selectedPlotIds === undefined || selectedPlotIds.length === 0)
    && continuationWorkflowRunId === undefined
  ) return null
  if (selectedPlotIds !== undefined && new Set(selectedPlotIds).size !== selectedPlotIds.length) return null
  return {
    projectId,
    selectedSources: selectedSources as { datasetId: string; sourceVersion: number }[],
    expectedProjectVersion,
    ...(selectedProfileIds === undefined ? {} : { selectedProfileIds }),
    ...(selectedPlotIds === undefined ? {} : { selectedPlotIds }),
    ...(continuationWorkflowRunId === undefined ? {} : { continuationWorkflowRunId }),
    instruction,
  }
}

export function parseTaskPlanInput(value: unknown): TaskPlanInput | null {
  if (!isRecord(value) || !hasExactKeys(value, ['projectId', 'planId'])) return null
  const projectId = parseId(value.projectId)
  const planId = parseId(value.planId)
  return projectId === null || planId === null ? null : { projectId, planId }
}

export function parseTaskPlanConfirmInput(value: unknown): TaskPlanConfirmInput | null {
  if (!isRecord(value) || !hasExactKeys(value, ['projectId', 'planId', 'accept'])) return null
  const parsed = parseTaskPlanInput({ projectId: value.projectId, planId: value.planId })
  return parsed === null || typeof value.accept !== 'boolean'
    ? null
    : { ...parsed, accept: value.accept }
}

export function parsePngSvgExportInput(value: unknown): PngSvgExportInput | null {
  const parsed = parseProjectIdRecord(value, ['target', 'format'])
  const target = parsed === null ? null : parseVersionedTarget(parsed.target)
  if (parsed === null || target === null || (parsed.format !== 'png' && parsed.format !== 'svg')) return null
  return { projectId: parsed.projectId as string, target, format: parsed.format }
}

export function parseOriginExportInput(value: unknown): OriginExportInput | null {
  const parsed = parseProjectIdRecord(value, ['target'])
  const target = parsed === null ? null : parseVersionedTarget(parsed.target)
  return parsed === null || target === null ? null : { projectId: parsed.projectId as string, target }
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
    ['task_kind', 'label', 'progress', 'error'],
  )) return null
  if (value.schema_version !== DESKTOP_API_VERSION || value.event_type !== 'task.state') return null
  if (!isIdentifier(value.task_id) || !Number.isSafeInteger(value.sequence) || Number(value.sequence) < 0) {
    return null
  }
  if (typeof value.state !== 'string' || !TASK_STATES.has(value.state as TaskState)) return null

  const taskKind = Object.hasOwn(value, 'task_kind') ? value.task_kind : undefined
  if (taskKind !== undefined && !isShortText(taskKind, 48)) return null
  const label = Object.hasOwn(value, 'label') ? value.label : undefined
  if (label !== undefined && !isShortText(label, 120)) return null

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

  let error: TaskFailure | undefined
  if (Object.hasOwn(value, 'error')) {
    if (!isRecord(value.error) || !hasExactKeys(value.error, ['code', 'message'])) return null
    if (!isShortText(value.error.code, 64) || !isShortText(value.error.message, 240)) return null
    error = { code: value.error.code, message: value.error.message }
  }

  return {
    schemaVersion: DESKTOP_API_VERSION,
    eventType: 'task.state',
    taskId: value.task_id,
    sequence: Number(value.sequence),
    state: value.state as TaskState,
    ...(taskKind === undefined ? {} : { taskKind }),
    ...(label === undefined ? {} : { label }),
    ...(progress === undefined ? {} : { progress }),
    ...(error === undefined ? {} : { error }),
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
