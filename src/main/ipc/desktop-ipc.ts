import type { IpcMain } from 'electron'

import {
  DESKTOP_API_VERSION,
  IPC_CHANNELS,
  parseCloseResponse,
  parseTaskId,
  type DesktopActionResult,
  type DesktopBootstrap,
  type JsonValue,
} from '../../shared/desktop-contract.js'
import type { PythonCoreSupervisor } from '../core/python-supervisor.js'
import type { AppCloseController } from '../lifecycle/app-close-controller.js'
import { isTaskCancellable, type TaskTracker } from '../tasks/task-state.js'

export interface RegisterDesktopIpcOptions {
  readonly ipcMain: IpcMain
  readonly supervisor: PythonCoreSupervisor
  readonly tasks: TaskTracker
  readonly closeController: AppCloseController
}

function invalidArgument(message: string): DesktopActionResult {
  return {
    ok: false,
    error: { code: 'IPC_INVALID_ARGUMENT', message, retryable: false },
  }
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
}: RegisterDesktopIpcOptions): () => void {
  const channels = [
    IPC_CHANNELS.getBootstrap,
    IPC_CHANNELS.getTasks,
    IPC_CHANNELS.cancelTask,
    IPC_CHANNELS.retryCore,
    IPC_CHANNELS.closeResponse,
  ] as const
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

  return () => {
    for (const channel of channels) ipcMain.removeHandler(channel)
  }
}
