import { createHash, randomUUID } from 'node:crypto'
import { createReadStream } from 'node:fs'
import { basename } from 'node:path'
import { stat } from 'node:fs/promises'

import type { BrowserWindow, Dialog, IpcMain } from 'electron'

import {
  DESKTOP_API_VERSION,
  IPC_CHANNELS,
  parseAgentDecideInput,
  parseAgentPlanConfirmInput,
  parseAgentPlanInput,
  parseEngineBatchPlanCreateInput,
  parseCloseResponse,
  parseCustomProviderConfigureInput,
  parseDatasetDescribeInput,
  parseEngineActionInput,
  parseOriginExportInput,
  parsePlotIdInput,
  parsePngSvgExportInput,
  parseProjectCreateInput,
  parseProjectIdInput,
  parseProjectRenameInput,
  parseProjectResourceInput,
  parseTaskId,
  type DesktopActionResult,
  type DesktopBootstrap,
  type DesktopDataResult,
  type DesktopResourceKind,
  type JsonValue,
} from '../../shared/desktop-contract.js'
import type { PythonCoreSupervisor } from '../core/python-supervisor.js'
import type { AppCloseController } from '../lifecycle/app-close-controller.js'
import type { ResourceRegistry } from '../single-instance-routing.js'
import { isTaskCancellable, type TaskTracker } from '../tasks/task-state.js'

const IMPORT_FILTERS = [
  { name: '数值数据', extensions: ['csv', 'tsv', 'txt', 'dat', 'xls', 'xlsx', 'xlsm'] },
]
const PROJECT_FILTERS = [{ name: 'PlotAgent 项目', extensions: ['plotproj'] }]
const PRIVATE_RESULT_KEY = /(?:path|secret|token|credential|api[_-]?key)/i
const ARTIFACT_PATH_KEY = /^(?:artifact|preview|output)_path$/i
const ABSOLUTE_PATH_VALUE = /^(?:[A-Za-z]:[\\/]|\\\\|file:\/\/)/i

type DesktopDialog = Pick<Dialog, 'showOpenDialog' | 'showSaveDialog'>

export interface RegisterDesktopIpcOptions {
  readonly ipcMain: IpcMain
  readonly supervisor: PythonCoreSupervisor
  readonly tasks: TaskTracker
  readonly closeController: AppCloseController
  readonly dialog: DesktopDialog
  readonly getWindow: () => BrowserWindow | undefined
  readonly resources: ResourceRegistry
  readonly ensureSampleSource: () => Promise<string>
}

function invalidArgument(message: string): DesktopActionResult {
  return {
    ok: false,
    error: { code: 'IPC_INVALID_ARGUMENT', message, retryable: false },
  }
}

function invalidDataArgument(message: string): DesktopDataResult {
  return {
    ok: false,
    error: { code: 'IPC_INVALID_ARGUMENT', message, retryable: false },
  }
}

function cancelled(): DesktopDataResult {
  return {
    ok: false,
    error: { code: 'DIALOG_CANCELLED', message: '操作已取消。', retryable: false },
  }
}

async function existingFileSha256(path: string): Promise<string | undefined> {
  try {
    const metadata = await stat(path)
    if (!metadata.isFile()) return undefined
  } catch {
    return undefined
  }
  return await new Promise<string>((resolve, reject) => {
    const digest = createHash('sha256')
    const stream = createReadStream(path)
    stream.on('data', (chunk) => digest.update(chunk))
    stream.on('error', reject)
    stream.on('end', () => resolve(digest.digest('hex')))
  })
}

function resourceInvalid(): DesktopDataResult {
  return {
    ok: false,
    error: { code: 'RESOURCE_INVALID', message: 'Core 返回的本地资源不可用。', retryable: true },
  }
}

function sanitizeCoreValue(
  value: JsonValue,
  resources: ResourceRegistry,
  artifactKind: DesktopResourceKind,
  depth = 0,
): JsonValue {
  if (depth > 24) throw new Error('Core result exceeds desktop depth limit')
  if (typeof value === 'string') {
    if (ABSOLUTE_PATH_VALUE.test(value)) throw new Error('Unregistered path in Core result')
    return value
  }
  if (value === null || typeof value === 'boolean' || typeof value === 'number') return value
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeCoreValue(item, resources, artifactKind, depth + 1))
  }

  const sanitized: Record<string, JsonValue> = {}
  const nestedPath = value.path
  if (
    typeof nestedPath === 'string' && ABSOLUTE_PATH_VALUE.test(nestedPath) &&
    (Object.hasOwn(value, 'resource_id') || Object.hasOwn(value, 'content_hash'))
  ) {
    sanitized.resource = resources.registerFile(nestedPath, artifactKind) as unknown as JsonValue
  }
  for (const [key, item] of Object.entries(value)) {
    if (ARTIFACT_PATH_KEY.test(key)) {
      if (typeof item !== 'string' || !ABSOLUTE_PATH_VALUE.test(item)) throw new Error('Invalid artifact path')
      const kind = key.toLocaleLowerCase('en-US').startsWith('preview') ? 'preview' : artifactKind
      const outputKey = key.replace(/_path$/i, '_resource')
      sanitized[outputKey] = resources.registerFile(item, kind) as unknown as JsonValue
      continue
    }
    if (PRIVATE_RESULT_KEY.test(key)) continue
    sanitized[key] = sanitizeCoreValue(item, resources, artifactKind, depth + 1)
  }
  return sanitized
}

export function sanitizeCoreResult(
  value: JsonValue,
  resources: ResourceRegistry,
  artifactKind: DesktopResourceKind = 'preview',
): JsonValue {
  return sanitizeCoreValue(value, resources, artifactKind)
}

interface DatasetIdentity {
  readonly source_file_name: string
  readonly source_table_index: number
  readonly source_sheet_name?: string
}

function datasetSheetName(value: Record<string, JsonValue>): string | undefined {
  if (typeof value.source_sheet_name === 'string') return value.source_sheet_name
  if (typeof value.sheet_name === 'string') return value.sheet_name
  const samples = Array.isArray(value.source_coordinate_samples) ? value.source_coordinate_samples : []
  const coordinate = samples.find((item) => (
    item !== null && !Array.isArray(item) && typeof item === 'object' && typeof item.sheet_name === 'string'
  ))
  if (coordinate === undefined || coordinate === null || Array.isArray(coordinate) || typeof coordinate !== 'object') return undefined
  return typeof coordinate.sheet_name === 'string' ? coordinate.sheet_name : undefined
}

export function withImportSourceIdentity(value: JsonValue, sourceFileName: string): JsonValue {
  if (value === null || Array.isArray(value) || typeof value !== 'object') return value
  return {
    ...value,
    source_file_name: sourceFileName,
    ...(Array.isArray(value.datasets) ? { datasets: value.datasets.map((item, index) => {
      if (item === null || Array.isArray(item) || typeof item !== 'object') return item
      const sheetName = datasetSheetName(item)
      return {
        ...item,
        source_file_name: sourceFileName,
        source_table_index: index + 1,
        ...(sheetName === undefined ? {} : { source_sheet_name: sheetName }),
      }
    }) } : {}),
  }
}

async function requestCoreData(
  supervisor: PythonCoreSupervisor,
  resources: ResourceRegistry,
  method: string,
  params?: JsonValue,
  artifactKind: DesktopResourceKind = 'preview',
  timeoutMs?: number,
): Promise<DesktopDataResult> {
  try {
    const value = await supervisor.request(method, params, timeoutMs)
    return { ok: true, value: sanitizeCoreResult(value, resources, artifactKind) }
  } catch (error: unknown) {
    if (error instanceof Error && /(?:artifact|resource|path|depth)/i.test(error.message)) {
      return resourceInvalid()
    }
    return { ok: false, error: supervisor.toPublicResult(error) }
  }
}

export const AGENT_DECIDE_REQUEST_TIMEOUT_MS = 35_000

export function requestAgentDecision(
  supervisor: PythonCoreSupervisor,
  resources: ResourceRegistry,
  params: JsonValue,
): Promise<DesktopDataResult> {
  return requestCoreData(
    supervisor,
    resources,
    'agent.engine.decide',
    params,
    'preview',
    AGENT_DECIDE_REQUEST_TIMEOUT_MS,
  )
}

export function requestPlotList(
  supervisor: PythonCoreSupervisor,
  resources: ResourceRegistry,
  projectId: string,
): Promise<DesktopDataResult> {
  return requestCoreData(supervisor, resources, 'engine.plots.list', { project_id: projectId })
}

export const ORIGIN_EXPORT_REQUEST_TIMEOUT_MS = 925_000

function normalizeOriginExportResult(result: DesktopDataResult): DesktopDataResult {
  if (!result.ok || result.value === null || Array.isArray(result.value) || typeof result.value !== 'object') {
    return result
  }
  const outcome = result.value.result
  if (outcome === null || Array.isArray(outcome) || typeof outcome !== 'object' || outcome.status !== 'failed') {
    return result
  }
  const error = outcome.error
  const message = error !== null && !Array.isArray(error) && typeof error === 'object' && typeof error.message === 'string'
    ? error.message
    : 'Origin 导出未完成。'
  const retryable = error !== null && !Array.isArray(error) && typeof error === 'object' && typeof error.retryable === 'boolean'
    ? error.retryable
    : true
  return {
    ok: false,
    error: { code: 'CORE_REQUEST_FAILED', message, retryable },
  }
}

export async function requestOriginExport(
  supervisor: PythonCoreSupervisor,
  resources: ResourceRegistry,
  params: JsonValue,
): Promise<DesktopDataResult> {
  return normalizeOriginExportResult(await requestCoreData(
    supervisor,
    resources,
    'engine.exports.execute',
    params,
    'export',
    ORIGIN_EXPORT_REQUEST_TIMEOUT_MS,
  ))
}

function originDiagnostic(code: string, fallback: string): string {
  const messages: Record<string, string> = {
    NOT_INSTALLED: '未找到受支持的 Origin。请安装 Origin，或将便携版放置于 D:\\origin 后重新检测。',
    VERSION_UNSUPPORTED: '当前 Origin 版本不受支持。请安装产品要求的版本后重新检测。',
    LICENSE_UNAVAILABLE: 'Origin 许可证当前不可用。请启动 Origin 完成许可证验证后重新检测。',
    CAPABILITY_MISSING: 'Origin 缺少导出所需能力。请修复 Origin 安装后重新检测。',
    TEMPLATE_OR_FONT_MISSING: 'Origin 导出模板或字体不完整。请修复 PlotAgent 安装后重新检测。',
    START_FAILURE: 'Origin 无法启动。请关闭残留的 Origin 进程后重新检测。',
  }
  return messages[code] ?? (fallback || 'Origin 环境未通过检测。请检查安装与许可证后重新检测。')
}

export function normalizeOriginStatus(value: JsonValue): JsonValue {
  if (value === null || Array.isArray(value) || typeof value !== 'object') {
    throw new Error('Invalid Origin status response')
  }
  if (value.status === 'ready') {
    const environment = value.environment
    if (environment === null || Array.isArray(environment) || typeof environment !== 'object') {
      throw new Error('Invalid Origin environment response')
    }
    return {
      status: 'ready',
      display_name: typeof environment.display_name === 'string' ? environment.display_name : 'Origin',
      display_version: typeof environment.display_version === 'string' ? environment.display_version : '',
      discovery_source: typeof environment.discovery_source === 'string' ? environment.discovery_source : 'registry',
    }
  }
  const error = value.error
  if (value.status !== 'error' || error === null || Array.isArray(error) || typeof error !== 'object') {
    throw new Error('Invalid Origin status response')
  }
  const code = typeof error.code === 'string' ? error.code : 'UNKNOWN'
  return {
    status: 'error',
    error: {
      code,
      message: originDiagnostic(code, typeof error.message === 'string' ? error.message : ''),
      retryable: typeof error.retryable === 'boolean' ? error.retryable : true,
    },
  }
}

export const ORIGIN_STATUS_REQUEST_TIMEOUT_MS = 35_000

export async function requestOriginStatus(
  supervisor: PythonCoreSupervisor,
): Promise<DesktopDataResult> {
  try {
    return {
      ok: true,
      value: normalizeOriginStatus(await supervisor.request(
        'origin.status',
        {},
        ORIGIN_STATUS_REQUEST_TIMEOUT_MS,
      )),
    }
  } catch (error: unknown) {
    return { ok: false, error: supervisor.toPublicResult(error) }
  }
}

export async function preflightOriginExport(
  supervisor: PythonCoreSupervisor,
): Promise<DesktopActionResult> {
  const result = await requestOriginStatus(supervisor)
  if (!result.ok) return result
  if (result.value !== null && !Array.isArray(result.value) && typeof result.value === 'object' && result.value.status === 'ready') {
    return { ok: true }
  }
  const error = result.value !== null && !Array.isArray(result.value) && typeof result.value === 'object'
    ? result.value.error
    : undefined
  const message = error !== null && !Array.isArray(error) && typeof error === 'object' && typeof error.message === 'string'
    ? error.message
    : 'Origin 环境未通过检测。请重新检测后再导出。'
  const retryable = error !== null && !Array.isArray(error) && typeof error === 'object' && typeof error.retryable === 'boolean'
    ? error.retryable
    : true
  return { ok: false, error: { code: 'ORIGIN_UNAVAILABLE', message, retryable } }
}

function projectIdFromCoreResult(value: JsonValue): string | null {
  if (value === null || Array.isArray(value) || typeof value !== 'object') return null
  const projectId = value.project_id ?? value.id
  return typeof projectId === 'string' && /^[A-Za-z][A-Za-z0-9:._-]{0,127}$/.test(projectId)
    ? projectId
    : null
}

export async function requestCoreAction(
  supervisor: PythonCoreSupervisor,
  method: string,
  params?: JsonValue,
): Promise<DesktopActionResult> {
  try {
    await supervisor.request(method, params)
    return { ok: true }
  } catch (error: unknown) {
    return { ok: false, error: supervisor.toPublicResult(error) }
  }
}

export function registerDesktopIpc({
  ipcMain,
  supervisor,
  tasks,
  closeController,
  dialog,
  getWindow,
  resources,
  ensureSampleSource,
}: RegisterDesktopIpcOptions): () => void {
  const datasetIdentities = new Map<string, DatasetIdentity>()
  const identityKey = (projectId: string, datasetId: string, sourceVersion: number): string => (
    `${projectId}:${datasetId}@${sourceVersion}`
  )
  const rememberDatasetIdentities = (projectId: string, value: JsonValue): void => {
    if (Array.isArray(value)) {
      value.forEach((item) => rememberDatasetIdentities(projectId, item))
      return
    }
    if (value === null || typeof value !== 'object') return
    if (
      typeof value.source_dataset_id === 'string' &&
      typeof value.source_version === 'number' &&
      typeof value.source_file_name === 'string' &&
      typeof value.source_table_index === 'number'
    ) {
      const sheetName = typeof value.source_sheet_name === 'string' ? value.source_sheet_name : undefined
      datasetIdentities.set(identityKey(projectId, value.source_dataset_id, value.source_version), {
        source_file_name: value.source_file_name,
        source_table_index: value.source_table_index,
        ...(sheetName === undefined ? {} : { source_sheet_name: sheetName }),
      })
    }
    Object.values(value).forEach((item) => rememberDatasetIdentities(projectId, item))
  }
  const restoreDatasetIdentities = (projectId: string, value: JsonValue): JsonValue => {
    if (Array.isArray(value)) return value.map((item) => restoreDatasetIdentities(projectId, item))
    if (value === null || typeof value !== 'object') return value
    const restored = Object.fromEntries(Object.entries(value).map(([key, item]) => (
      [key, restoreDatasetIdentities(projectId, item)]
    ))) as Record<string, JsonValue>
    if (typeof value.source_dataset_id !== 'string' || typeof value.source_version !== 'number') return restored
    const identity = datasetIdentities.get(identityKey(projectId, value.source_dataset_id, value.source_version))
    return identity === undefined ? restored : { ...restored, ...identity }
  }
  const eventChannels = new Set<string>([
    IPC_CHANNELS.coreStatusChanged,
    IPC_CHANNELS.lifecycleCloseRequested,
    IPC_CHANNELS.openResourceRequested,
    IPC_CHANNELS.taskEvent,
  ])
  const channels = Object.values(IPC_CHANNELS).filter((channel) => !eventChannels.has(channel))
  for (const channel of channels) ipcMain.removeHandler(channel)

  ipcMain.handle(IPC_CHANNELS.getBootstrap, (): DesktopBootstrap => ({
    apiVersion: DESKTOP_API_VERSION,
    platform: process.platform === 'darwin'
      ? 'darwin'
      : process.platform === 'linux' ? 'linux' : 'win32',
    core: supervisor.getStatus(),
    tasks: tasks.snapshot(),
  }))

  ipcMain.handle(IPC_CHANNELS.getTasks, () => tasks.snapshot())

  ipcMain.handle(IPC_CHANNELS.cancelTask, async (_event, value: unknown) => {
    const taskId = parseTaskId(value)
    if (taskId === null) return invalidArgument('A valid task ID is required.')
    const task = tasks.get(taskId)
    if (task === undefined || !isTaskCancellable(task.state)) {
      return {
        ok: false,
        error: {
          code: 'TASK_NOT_CANCELLABLE',
          message: 'The task cannot be cancelled in its current state.',
          retryable: false,
        },
      } satisfies DesktopActionResult
    }
    return requestCoreAction(supervisor, 'tasks.cancel', { task_id: taskId })
  })

  ipcMain.handle(IPC_CHANNELS.retryCore, () => {
    if (!supervisor.retry()) return invalidArgument('The local Core is not in a retryable state.')
    return { ok: true } satisfies DesktopActionResult
  })

  ipcMain.handle(IPC_CHANNELS.providerStatus, () => (
    requestCoreData(supervisor, resources, 'provider.status')
  ))
  ipcMain.handle(IPC_CHANNELS.originStatus, () => requestOriginStatus(supervisor))
  ipcMain.handle(IPC_CHANNELS.providerConfigure, (_event, value: unknown) => {
    const input = parseCustomProviderConfigureInput(value)
    return input === null
      ? invalidDataArgument('模型服务配置无效。仅接受 HTTPS 地址和有效模型 ID。')
      : requestCoreData(supervisor, resources, 'provider.configure', {
        mode: 'custom_provider',
        provider_config_id: 'custom.default',
        base_url: input.baseUrl,
        model_id: input.modelId,
        ...(input.apiKey === undefined ? {} : { api_key: input.apiKey }),
        retention_acknowledged: true,
      })
  })
  ipcMain.handle(IPC_CHANNELS.providerClear, () => (
    requestCoreData(supervisor, resources, 'provider.clear')
  ))

  ipcMain.handle(IPC_CHANNELS.closeResponse, async (_event, value: unknown) => {
    const response = parseCloseResponse(value)
    return response === null
      ? invalidArgument('A valid close response is required.')
      : closeController.respond(response)
  })

  ipcMain.handle(IPC_CHANNELS.projectList, () => (
    requestCoreData(supervisor, resources, 'projects.list')
  ))
  ipcMain.handle(IPC_CHANNELS.projectCreate, (_event, value: unknown) => {
    const input = parseProjectCreateInput(value)
    return input === null
      ? invalidDataArgument('项目名称无效。')
      : requestCoreData(supervisor, resources, 'projects.create', {
        idempotency_key: `project-create:${randomUUID()}`,
        display_name: input.name,
      })
  })
  ipcMain.handle(IPC_CHANNELS.projectRename, (_event, value: unknown) => {
    const input = parseProjectRenameInput(value)
    return input === null
      ? invalidDataArgument('项目名称无效。')
      : requestCoreData(supervisor, resources, 'projects.rename', {
        project_id: input.projectId,
        display_name: input.name,
      })
  })
  ipcMain.handle(IPC_CHANNELS.projectDelete, (_event, value: unknown) => {
    const input = parseProjectIdInput(value)
    return input === null
      ? invalidDataArgument('项目 ID 无效。')
      : requestCoreData(supervisor, resources, 'projects.delete', { project_id: input.projectId })
  })
  ipcMain.handle(IPC_CHANNELS.projectActivate, (_event, value: unknown) => {
    const input = parseProjectIdInput(value)
    return input === null
      ? invalidDataArgument('项目 ID 无效。')
      : requestCoreData(supervisor, resources, 'projects.open', { project_id: input.projectId })
  })
  ipcMain.handle(IPC_CHANNELS.projectOpen, async () => {
    const owner = getWindow()
    if (owner === undefined) return invalidDataArgument('主窗口不可用。')
    const choice = await dialog.showOpenDialog(owner, {
      title: '打开 PlotAgent 项目',
      properties: ['openFile'],
      filters: [...PROJECT_FILTERS],
    })
    if (choice.canceled || choice.filePaths.length !== 1) return cancelled()
    const request = resources.registerProjectPackage(choice.filePaths[0])
    return requestCoreData(supervisor, resources, 'projects.open', {
      resource_id: request.resourceId,
      source_path: choice.filePaths[0],
    })
  })
  ipcMain.handle(IPC_CHANNELS.projectOpenResource, (_event, value: unknown) => {
    const input = parseProjectResourceInput(value)
    const entry = input === null ? undefined : resources.resolveEntry(input.resourceId)
    if (entry === undefined || entry.kind !== 'project-package') {
      return invalidDataArgument('项目资源无效或未由应用授权。')
    }
    return requestCoreData(supervisor, resources, 'projects.open', {
      resource_id: entry.resourceId,
      source_path: entry.path,
    })
  })
  ipcMain.handle(IPC_CHANNELS.projectOpenSample, async () => {
    try {
      const samplePath = await ensureSampleSource()
      const importResource = resources.registerFile(samplePath, 'import-source')
      const created = await supervisor.request('projects.create', {
        idempotency_key: `sample-project:${randomUUID()}`,
        display_name: '温度响应示例',
      })
      const projectId = projectIdFromCoreResult(created)
      if (projectId === null) return resourceInvalid()
      const opened = await supervisor.request('projects.open', { project_id: projectId })
      const imported = await supervisor.request('datasets.import', {
        project_id: projectId,
        resource_id: importResource.resourceId,
        source_path: samplePath,
        idempotency_key: `sample-import:${randomUUID()}`,
        expected_version: 0,
      })
      const identified = withImportSourceIdentity(imported, basename(samplePath))
      rememberDatasetIdentities(projectId, identified)
      return {
        ok: true,
        value: sanitizeCoreResult({ project: created, opened, imported: identified }, resources),
      } satisfies DesktopDataResult
    } catch (error: unknown) {
      return { ok: false, error: supervisor.toPublicResult(error) } satisfies DesktopDataResult
    }
  })
  ipcMain.handle(IPC_CHANNELS.projectClose, (_event, value: unknown) => {
    const input = parseProjectIdInput(value)
    return input === null
      ? invalidDataArgument('项目 ID 无效。')
      : requestCoreData(supervisor, resources, 'projects.close', { project_id: input.projectId })
  })

  ipcMain.handle(IPC_CHANNELS.datasetImport, async (_event, value: unknown) => {
    const input = parseProjectIdInput(value)
    const owner = getWindow()
    if (input === null || owner === undefined) return invalidDataArgument('项目 ID 无效。')
    const choice = await dialog.showOpenDialog(owner, {
      title: '导入数值数据',
      properties: ['openFile', 'multiSelections'],
      filters: [...IMPORT_FILTERS],
    })
    if (choice.canceled || choice.filePaths.length === 0) return cancelled()
    let expectedVersion = 0
    const listed = await supervisor.request('datasets.list', { project_id: input.projectId })
    if (listed !== null && !Array.isArray(listed) && typeof listed === 'object') {
      const current = listed.project_version
      if (typeof current === 'number' && Number.isSafeInteger(current) && current >= 0) expectedVersion = current
    }
    const imported: JsonValue[] = []
    for (const path of choice.filePaths) {
      try {
        const resource = resources.registerFile(path, 'import-source')
        const result = await supervisor.request('datasets.import', {
          project_id: input.projectId,
          resource_id: resource.resourceId,
          source_path: path,
          idempotency_key: `dataset-import:${randomUUID()}`,
          expected_version: expectedVersion,
        })
        const identified = withImportSourceIdentity(result, basename(path))
        rememberDatasetIdentities(input.projectId, identified)
        imported.push(identified)
        if (result !== null && !Array.isArray(result) && typeof result === 'object') {
          const current = result.project_version
          if (typeof current === 'number' && Number.isSafeInteger(current) && current >= expectedVersion) {
            expectedVersion = current
          }
        }
      } catch (error: unknown) {
        imported.push({
          kind: 'failed',
          source_file_name: basename(path),
          error: supervisor.toPublicResult(error) as unknown as JsonValue,
        })
      }
    }
    return { ok: true, value: sanitizeCoreResult({ imports: imported, project_version: expectedVersion }, resources) }
  })
  ipcMain.handle(IPC_CHANNELS.datasetList, async (_event, value: unknown) => {
    const input = parseProjectIdInput(value)
    if (input === null) return invalidDataArgument('项目 ID 无效。')
    try {
      const listed = await supervisor.request('datasets.list', { project_id: input.projectId })
      return {
        ok: true,
        value: sanitizeCoreResult(restoreDatasetIdentities(input.projectId, listed), resources),
      } satisfies DesktopDataResult
    } catch (error: unknown) {
      return { ok: false, error: supervisor.toPublicResult(error) } satisfies DesktopDataResult
    }
  })
  ipcMain.handle(IPC_CHANNELS.datasetDescribe, async (_event, value: unknown) => {
    const input = parseDatasetDescribeInput(value)
    if (input === null) return invalidDataArgument('数据集 ID 无效。')
    try {
      const described = await supervisor.request('datasets.describe', {
        project_id: input.projectId,
        source_dataset_id: input.datasetId,
        source_version: input.sourceVersion,
      })
      return {
        ok: true,
        value: sanitizeCoreResult(restoreDatasetIdentities(input.projectId, described), resources),
      } satisfies DesktopDataResult
    } catch (error: unknown) {
      return { ok: false, error: supervisor.toPublicResult(error) } satisfies DesktopDataResult
    }
  })

  ipcMain.handle(IPC_CHANNELS.engineActionExecute, (_event, value: unknown) => {
    const input = parseEngineActionInput(value)
    return input === null
      ? invalidDataArgument('绘图动作无效或包含未授权内容。')
      : requestCoreData(supervisor, resources, 'engine.actions.execute', {
        project_id: input.projectId,
        expected_project_version: input.expectedProjectVersion,
        action: input.action,
      }, 'preview')
  })
  ipcMain.handle(IPC_CHANNELS.enginePlotGet, (_event, value: unknown) => {
    const input = parsePlotIdInput(value)
    return input === null
      ? invalidDataArgument('绘图 ID 无效。')
      : requestCoreData(supervisor, resources, 'engine.plots.get', {
        project_id: input.projectId,
        plot_id: input.plotId,
        plot_version: input.plotVersion,
      })
  })
  ipcMain.handle(IPC_CHANNELS.enginePlotList, (_event, value: unknown) => {
    const input = parseProjectIdInput(value)
    return input === null
      ? invalidDataArgument('项目 ID 无效。')
      : requestPlotList(supervisor, resources, input.projectId)
  })
  ipcMain.handle(IPC_CHANNELS.engineBatchPlanCreate, (_event, value: unknown) => {
    const input = parseEngineBatchPlanCreateInput(value)
    return input === null
      ? invalidDataArgument('批量绘图请求无效。')
      : requestCoreData(supervisor, resources, 'agent.engine.plans.create_batch', {
        project_id: input.projectId,
        profile_id: input.profileId,
        source_datasets: input.datasets.map((item) => ({
          dataset_id: item.datasetId,
          version: item.sourceVersion,
          content_hash: item.contentHash,
          bindings: item.bindings,
        })),
        expected_project_version: input.expectedProjectVersion,
      })
  })
  ipcMain.handle(IPC_CHANNELS.agentDecide, (_event, value: unknown) => {
    const input = parseAgentDecideInput(value)
    return input === null
      ? invalidDataArgument('Agent 指令、作用对象或范围无效。')
      : input.scope !== 'current'
        || (input.target !== undefined && input.target.kind !== 'plot')
        ? invalidDataArgument('Agent Native currently accepts a dataset or one plot target.')
        : requestAgentDecision(supervisor, resources, {
        project_id: input.projectId,
        source_dataset_id: input.sourceDatasetId,
        source_version: input.sourceVersion,
        user_instruction: input.utterance,
        client_model_run_id: `model-run:${randomUUID()}`,
        expected_version: input.expectedVersion,
        locale: 'zh-CN',
        ...(input.conversationId === undefined
          ? {} : { conversation_id: input.conversationId }),
        ...(input.selectedChartId === undefined
          ? {} : { selected_profile_id: input.selectedChartId }),
        ...(input.target === undefined ? {} : { target_plot_id: input.target.id }),
      })
  })

  for (const [channel, method] of [
    [IPC_CHANNELS.agentPlanGet, 'agent.engine.plans.get'],
    [IPC_CHANNELS.agentPlanRun, 'agent.engine.plans.run'],
    [IPC_CHANNELS.agentPlanResume, 'agent.engine.plans.resume'],
  ] as const) {
    ipcMain.handle(channel, (_event, value: unknown) => {
      const input = parseAgentPlanInput(value)
      return input === null
        ? invalidDataArgument('Agent 计划参数无效。')
        : requestCoreData(supervisor, resources, method, {
          project_id: input.projectId,
          plan_id: input.planId,
        })
    })
  }

  for (const [channel, method] of [
    [IPC_CHANNELS.agentPlanList, 'agent.engine.plans.list'],
  ] as const) {
    ipcMain.handle(channel, (_event, value: unknown) => {
      const input = parseProjectIdInput(value)
      return input === null
        ? invalidDataArgument('Agent 上下文参数无效。')
        : requestCoreData(supervisor, resources, method, {
          project_id: input.projectId,
        })
    })
  }

  ipcMain.handle(IPC_CHANNELS.agentPlanConfirm, (_event, value: unknown) => {
    const input = parseAgentPlanConfirmInput(value)
    return input === null
      ? invalidDataArgument('Agent 计划确认参数无效。')
      : requestCoreData(supervisor, resources, input.accept
        ? 'agent.engine.plans.confirm'
        : 'agent.engine.plans.cancel', {
        project_id: input.projectId,
        plan_id: input.planId,
      })
  })

  ipcMain.handle(IPC_CHANNELS.exportPngSvg, async (_event, value: unknown) => {
    const input = parsePngSvgExportInput(value)
    const owner = getWindow()
    if (input === null || owner === undefined) return invalidDataArgument('导出请求无效。')
    const choice = await dialog.showSaveDialog(owner, {
      title: `导出 ${input.format.toLocaleUpperCase('en-US')}`,
      defaultPath: `${input.target.id}.${input.format}`,
      filters: [{ name: input.format.toLocaleUpperCase('en-US'), extensions: [input.format] }],
    })
    if (choice.canceled || choice.filePath === undefined) return cancelled()
    return requestCoreData(supervisor, resources, 'engine.exports.execute', {
      project_id: input.projectId,
      action: {
        operation: 'export_plot',
        action_id: `action:export.${randomUUID()}`,
        target: input.target.id,
        expected_plot_version: input.target.version,
        format: input.format,
        output_name: basename(choice.filePath),
      },
      destination_resource_id: resources.registerFile(choice.filePath, 'export').resourceId,
      destination_path: choice.filePath,
    }, 'export')
  })
  ipcMain.handle(IPC_CHANNELS.exportOrigin, async (_event, value: unknown) => {
    const input = parseOriginExportInput(value)
    const owner = getWindow()
    if (input === null || owner === undefined) return invalidDataArgument('Origin 导出请求无效。')
    const preflight = await preflightOriginExport(supervisor)
    if (!preflight.ok) return preflight
    const choice = await dialog.showSaveDialog(owner, {
      title: '导出 Origin 项目',
      defaultPath: `${input.target.id}.opju`,
      filters: [{ name: 'Origin 项目', extensions: ['opju'] }],
    })
    if (choice.canceled || choice.filePath === undefined) return cancelled()
    const expectedExistingSha256 = await existingFileSha256(choice.filePath)
    return requestOriginExport(supervisor, resources, {
      project_id: input.projectId,
      action: {
        operation: 'export_plot',
        action_id: `action:export.${randomUUID()}`,
        target: input.target.id,
        expected_plot_version: input.target.version,
        format: 'opju',
        output_name: basename(choice.filePath),
      },
      destination_resource_id: resources.registerFile(choice.filePath, 'export').resourceId,
      destination_path: choice.filePath,
      ...(expectedExistingSha256 === undefined
        ? {}
        : { expected_existing_sha256: expectedExistingSha256 }),
    })
  })

  return () => {
    for (const channel of channels) ipcMain.removeHandler(channel)
  }
}
