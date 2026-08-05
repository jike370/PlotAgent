import { randomUUID } from 'node:crypto'

import type { BrowserWindow, Dialog, IpcMain } from 'electron'

import {
  DESKTOP_API_VERSION,
  IPC_CHANNELS,
  parseAgentDecideInput,
  parseBatchCreateInput,
  parseBatchIdInput,
  parseBatchRunInput,
  parseCloseResponse,
  parseDatasetDescribeInput,
  parseFigureCreateInput,
  parseFigureIdInput,
  parseOriginExportInput,
  parsePlotCreateInput,
  parsePlotIdInput,
  parsePlotPatchInput,
  parsePlotRenderInput,
  parsePngSvgExportInput,
  parseProjectCreateInput,
  parseProjectIdInput,
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

async function requestCoreData(
  supervisor: PythonCoreSupervisor,
  resources: ResourceRegistry,
  method: string,
  params?: JsonValue,
  artifactKind: DesktopResourceKind = 'preview',
): Promise<DesktopDataResult> {
  try {
    const value = await supervisor.request(method, params)
    return { ok: true, value: sanitizeCoreResult(value, resources, artifactKind) }
  } catch (error: unknown) {
    if (error instanceof Error && /(?:artifact|resource|path|depth)/i.test(error.message)) {
      return resourceInvalid()
    }
    return { ok: false, error: supervisor.toPublicResult(error) }
  }
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
      return {
        ok: true,
        value: sanitizeCoreResult({ project: created, opened, imported }, resources),
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
      const resource = resources.registerFile(path, 'import-source')
      const result = await supervisor.request('datasets.import', {
        project_id: input.projectId,
        resource_id: resource.resourceId,
        source_path: path,
        idempotency_key: `dataset-import:${randomUUID()}`,
        expected_version: expectedVersion,
      })
      imported.push(result)
      if (result !== null && !Array.isArray(result) && typeof result === 'object') {
        const current = result.project_version
        if (typeof current === 'number' && Number.isSafeInteger(current) && current >= expectedVersion) {
          expectedVersion = current
        }
      }
    }
    return { ok: true, value: sanitizeCoreResult({ imports: imported, project_version: expectedVersion }, resources) }
  })
  ipcMain.handle(IPC_CHANNELS.datasetList, (_event, value: unknown) => {
    const input = parseProjectIdInput(value)
    return input === null
      ? invalidDataArgument('项目 ID 无效。')
      : requestCoreData(supervisor, resources, 'datasets.list', { project_id: input.projectId })
  })
  ipcMain.handle(IPC_CHANNELS.datasetDescribe, (_event, value: unknown) => {
    const input = parseDatasetDescribeInput(value)
    return input === null
      ? invalidDataArgument('数据集 ID 无效。')
      : requestCoreData(supervisor, resources, 'datasets.describe', {
        project_id: input.projectId,
        source_dataset_id: input.datasetId,
        source_version: input.sourceVersion,
      })
  })

  ipcMain.handle(IPC_CHANNELS.plotCreate, (_event, value: unknown) => {
    const input = parsePlotCreateInput(value)
    return input === null
      ? invalidDataArgument('绘图类型或字段映射无效。')
      : requestCoreData(supervisor, resources, 'plots.create', {
        project_id: input.projectId,
        plot_id: `plot:${randomUUID()}`,
        chart_type_id: input.chartId,
        source_dataset_id: input.datasetId,
        source_version: input.sourceVersion,
        field_mapping: input.fieldMapping.roles,
        idempotency_key: `plot-create:${randomUUID()}`,
        expected_version: input.expectedVersion,
      })
  })
  ipcMain.handle(IPC_CHANNELS.plotPatch, (_event, value: unknown) => {
    const input = parsePlotPatchInput(value)
    return input === null
      ? invalidDataArgument('绘图修改无效或包含未授权内容。')
      : requestCoreData(supervisor, resources, 'plots.patch', {
        project_id: input.projectId,
        plot_id: input.plotId,
        expected_version: input.plotVersion,
        idempotency_key: `plot-patch:${randomUUID()}`,
        patch: input.patch,
      })
  })
  ipcMain.handle(IPC_CHANNELS.plotGet, (_event, value: unknown) => {
    const input = parsePlotIdInput(value)
    return input === null
      ? invalidDataArgument('绘图 ID 无效。')
      : requestCoreData(supervisor, resources, 'plots.get', {
        project_id: input.projectId,
        plot_id: input.plotId,
        plot_version: input.plotVersion,
      })
  })
  ipcMain.handle(IPC_CHANNELS.plotRender, (_event, value: unknown) => {
    const input = parsePlotRenderInput(value)
    return input === null
      ? invalidDataArgument('绘图渲染请求无效。')
      : requestCoreData(supervisor, resources, 'plots.render', {
        project_id: input.projectId,
        plot_id: input.plotId,
        plot_version: input.plotVersion,
      }, 'preview')
  })

  ipcMain.handle(IPC_CHANNELS.batchCreate, (_event, value: unknown) => {
    const input = parseBatchCreateInput(value)
    return input === null
      ? invalidDataArgument('批量绘图请求无效。')
      : requestCoreData(supervisor, resources, 'batch.create', {
        project_id: input.projectId,
        task_id: `task:${randomUUID()}`,
        batch_id: `batch:${randomUUID()}`,
        chart_type_id: input.chartId,
        source_datasets: input.datasets.map((item) => ({
          source_dataset_id: item.datasetId,
          source_version: item.sourceVersion,
        })),
        field_mapping: input.fieldMapping.roles,
        idempotency_key: `batch-create:${randomUUID()}`,
        expected_version: input.expectedVersion,
      })
  })
  ipcMain.handle(IPC_CHANNELS.batchRun, (_event, value: unknown) => {
    const input = parseBatchRunInput(value)
    return input === null
      ? invalidDataArgument('批次任务 ID 无效。')
      : requestCoreData(supervisor, resources, 'batch.run', {
        project_id: input.projectId,
        task_id: input.taskId,
        idempotency_key: `batch-run:${randomUUID()}`,
        expected_version: input.expectedVersion,
      })
  })
  ipcMain.handle(IPC_CHANNELS.batchGet, (_event, value: unknown) => {
    const input = parseBatchIdInput(value)
    return input === null
      ? invalidDataArgument('批次 ID 无效。')
      : requestCoreData(supervisor, resources, 'batch.get', {
        project_id: input.projectId,
        batch_id: input.batchId,
      })
  })

  ipcMain.handle(IPC_CHANNELS.figureCreate, (_event, value: unknown) => {
    const input = parseFigureCreateInput(value)
    return input === null
      ? invalidDataArgument('组合图请求无效。')
      : requestCoreData(supervisor, resources, 'figures.create', {
        project_id: input.projectId,
        figure_id: `figure:${randomUUID()}`,
        plot_refs: input.plotRefs.map((item) => ({
          plot_id: item.plotId,
          plot_version: item.plotVersion,
        })),
        layout: input.layout,
        idempotency_key: `figure-create:${randomUUID()}`,
        expected_version: input.expectedVersion,
      })
  })
  for (const [channel, method] of [
    [IPC_CHANNELS.figureGet, 'figures.get'],
    [IPC_CHANNELS.figureRender, 'figures.render'],
  ] as const) {
    ipcMain.handle(channel, (_event, value: unknown) => {
      const input = parseFigureIdInput(value)
      return input === null
        ? invalidDataArgument('组合图 ID 无效。')
        : requestCoreData(supervisor, resources, method, {
          project_id: input.projectId,
          figure_id: input.figureId,
        })
    })
  }

  ipcMain.handle(IPC_CHANNELS.agentDecide, (_event, value: unknown) => {
    const input = parseAgentDecideInput(value)
    return input === null
      ? invalidDataArgument('Agent 指令、作用对象或范围无效。')
      : requestCoreData(supervisor, resources, 'agent.decide', {
        project_id: input.projectId,
        source_dataset_id: input.sourceDatasetId,
        source_version: input.sourceVersion,
        user_instruction: input.utterance,
        client_model_run_id: `model-run:${randomUUID()}`,
        network_mode: 'online',
        provider: { kind: 'builtin' },
        expected_version: input.expectedVersion,
        locale: 'zh-CN',
        target: input.target,
        scope: input.scope,
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
    return requestCoreData(supervisor, resources, 'exports.png_svg', {
      project_id: input.projectId,
      plot_id: input.target.id,
      plot_version: input.target.version,
      format: input.format,
      destination_resource_id: resources.registerFile(choice.filePath, 'export').resourceId,
      destination_path: choice.filePath,
      idempotency_key: `export-${input.format}:${randomUUID()}`,
      expected_version: input.target.version,
    }, 'export')
  })
  ipcMain.handle(IPC_CHANNELS.exportOrigin, async (_event, value: unknown) => {
    const input = parseOriginExportInput(value)
    const owner = getWindow()
    if (input === null || owner === undefined) return invalidDataArgument('Origin 导出请求无效。')
    const choice = await dialog.showSaveDialog(owner, {
      title: '导出 Origin 项目',
      defaultPath: `${input.target.id}.opju`,
      filters: [{ name: 'Origin 项目', extensions: ['opju'] }],
    })
    if (choice.canceled || choice.filePath === undefined) return cancelled()
    return requestCoreData(supervisor, resources, 'exports.origin', {
      project_id: input.projectId,
      plot_id: input.target.id,
      plot_version: input.target.version,
      destination_resource_id: resources.registerFile(choice.filePath, 'export').resourceId,
      destination_path: choice.filePath,
      idempotency_key: `export-origin:${randomUUID()}`,
      expected_version: input.target.version,
    }, 'export')
  })

  return () => {
    for (const channel of channels) ipcMain.removeHandler(channel)
  }
}
