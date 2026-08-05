import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'

import {
  DESKTOP_API_VERSION,
  IPC_CHANNELS,
  type CloseRequest,
  type CloseResponse,
  type CoreStatus,
  type OpenResourceRequest,
  type PlotAgentDesktopApi,
  type TaskEvent,
} from '../shared/desktop-contract.js'

function createEventBridge<T>(channel: string, bufferLimit = 128): {
  subscribe: (listener: (value: T) => void) => () => void
} {
  const listeners = new Set<(value: T) => void>()
  const pending: T[] = []
  const handler = (_event: IpcRendererEvent, value: T): void => {
    if (listeners.size === 0) {
      pending.push(value)
      if (pending.length > bufferLimit) pending.shift()
      return
    }
    for (const listener of listeners) listener(value)
  }
  ipcRenderer.on(channel, handler)

  return {
    subscribe: (listener) => {
      listeners.add(listener)
      for (const value of pending.splice(0)) listener(value)
      return () => listeners.delete(listener)
    },
  }
}

const coreStatusEvents = createEventBridge<CoreStatus>(IPC_CHANNELS.coreStatusChanged, 8)
const taskEvents = createEventBridge<TaskEvent>(IPC_CHANNELS.taskEvent)
const openResourceEvents = createEventBridge<OpenResourceRequest>(IPC_CHANNELS.openResourceRequested, 32)
const closeRequestEvents = createEventBridge<CloseRequest>(IPC_CHANNELS.lifecycleCloseRequested, 4)

const desktop = {
  apiVersion: DESKTOP_API_VERSION,
  getBootstrap: () => ipcRenderer.invoke(IPC_CHANNELS.getBootstrap),
  getTasks: () => ipcRenderer.invoke(IPC_CHANNELS.getTasks),
  cancelTask: (taskId: string) => ipcRenderer.invoke(IPC_CHANNELS.cancelTask, { taskId }),
  retryCore: () => ipcRenderer.invoke(IPC_CHANNELS.retryCore),
  respondToCloseRequest: (response: CloseResponse) =>
    ipcRenderer.invoke(IPC_CHANNELS.closeResponse, response),
  onCoreStatus: (listener: (status: CoreStatus) => void) => coreStatusEvents.subscribe(listener),
  onTaskEvent: (listener: (event: TaskEvent) => void) => taskEvents.subscribe(listener),
  onOpenResourceRequested: (listener: (request: OpenResourceRequest) => void) =>
    openResourceEvents.subscribe(listener),
  onCloseRequested: (listener: (request: CloseRequest) => void) =>
    closeRequestEvents.subscribe(listener),
} satisfies PlotAgentDesktopApi

contextBridge.exposeInMainWorld('plotAgentDesktop', desktop)
