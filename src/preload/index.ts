import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'

import {
  DESKTOP_API_VERSION,
  IPC_CHANNELS,
  type CloseRequest,
  type CloseResponse,
  type CoreStatus,
  type CustomProviderConfigureInput,
  type WorkflowRunInput,
  type WorkflowRuntimeEvent,
  type TaskPlanConfirmInput,
  type TaskPlanInput,
  type DatasetDescribeInput,
  type EngineActionInput,
  type OpenResourceRequest,
  type OriginExportInput,
  type PlotAgentDesktopApi,
  type PlotIdInput,
  type PlotRestoreInput,
  type PngSvgExportInput,
  type ProjectCreateInput,
  type ProjectIdInput,
  type ProjectRenameInput,
  type ProjectResourceInput,
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
const workflowRuntimeEvents = createEventBridge<WorkflowRuntimeEvent>(
  IPC_CHANNELS.workflowRuntimeEvent,
  32,
)
const openResourceEvents = createEventBridge<OpenResourceRequest>(IPC_CHANNELS.openResourceRequested, 32)
const closeRequestEvents = createEventBridge<CloseRequest>(IPC_CHANNELS.lifecycleCloseRequested, 4)

const desktop = {
  apiVersion: DESKTOP_API_VERSION,
  getBootstrap: () => ipcRenderer.invoke(IPC_CHANNELS.getBootstrap),
  getTasks: () => ipcRenderer.invoke(IPC_CHANNELS.getTasks),
  cancelTask: (taskId: string) => ipcRenderer.invoke(IPC_CHANNELS.cancelTask, { taskId }),
  acceptPartialTask: (taskId: string) => ipcRenderer.invoke(
    IPC_CHANNELS.acceptPartialTask,
    { taskId },
  ),
  resumeAgentTask: (taskId: string) => ipcRenderer.invoke(
    IPC_CHANNELS.resumeAgentTask,
    { taskId },
  ),
  retryCore: () => ipcRenderer.invoke(IPC_CHANNELS.retryCore),
  getProviderStatus: () => ipcRenderer.invoke(IPC_CHANNELS.providerStatus),
  configureCustomProvider: (input: CustomProviderConfigureInput) =>
    ipcRenderer.invoke(IPC_CHANNELS.providerConfigure, input),
  clearProvider: () => ipcRenderer.invoke(IPC_CHANNELS.providerClear),
  getOriginStatus: () => ipcRenderer.invoke(IPC_CHANNELS.originStatus),
  listProjects: () => ipcRenderer.invoke(IPC_CHANNELS.projectList),
  createProject: (input: ProjectCreateInput) => ipcRenderer.invoke(IPC_CHANNELS.projectCreate, input),
  renameProject: (input: ProjectRenameInput) => ipcRenderer.invoke(IPC_CHANNELS.projectRename, input),
  deleteProject: (input: ProjectIdInput) => ipcRenderer.invoke(IPC_CHANNELS.projectDelete, input),
  activateProject: (input: ProjectIdInput) => ipcRenderer.invoke(IPC_CHANNELS.projectActivate, input),
  openProject: () => ipcRenderer.invoke(IPC_CHANNELS.projectOpen),
  openProjectResource: (input: ProjectResourceInput) =>
    ipcRenderer.invoke(IPC_CHANNELS.projectOpenResource, input),
  openExportResource: (input: ProjectResourceInput) =>
    ipcRenderer.invoke(IPC_CHANNELS.resourceOpen, input),
  revealExportResource: (input: ProjectResourceInput) =>
    ipcRenderer.invoke(IPC_CHANNELS.resourceReveal, input),
  openSampleProject: () => ipcRenderer.invoke(IPC_CHANNELS.projectOpenSample),
  closeProject: (input: ProjectIdInput) => ipcRenderer.invoke(IPC_CHANNELS.projectClose, input),
  importDatasets: (input: ProjectIdInput) => ipcRenderer.invoke(IPC_CHANNELS.datasetImport, input),
  listDatasets: (input: ProjectIdInput) => ipcRenderer.invoke(IPC_CHANNELS.datasetList, input),
  describeDataset: (input: DatasetDescribeInput) => ipcRenderer.invoke(IPC_CHANNELS.datasetDescribe, input),
  executePlotAction: (input: EngineActionInput) =>
    ipcRenderer.invoke(IPC_CHANNELS.engineActionExecute, input),
  getPlot: (input: PlotIdInput) => ipcRenderer.invoke(IPC_CHANNELS.enginePlotGet, input),
  listPlots: (input: ProjectIdInput) => ipcRenderer.invoke(IPC_CHANNELS.enginePlotList, input),
  restorePlotVersion: (input: PlotRestoreInput) =>
    ipcRenderer.invoke(IPC_CHANNELS.enginePlotRestore, input),
  runWorkflow: (input: WorkflowRunInput) => ipcRenderer.invoke(IPC_CHANNELS.workflowRun, input),
  getTaskPlan: (input: TaskPlanInput) =>
    ipcRenderer.invoke(IPC_CHANNELS.taskPlanGet, input),
  listTaskPlans: (input: ProjectIdInput) =>
    ipcRenderer.invoke(IPC_CHANNELS.taskPlanList, input),
  confirmTaskPlan: (input: TaskPlanConfirmInput) =>
    ipcRenderer.invoke(IPC_CHANNELS.taskPlanConfirm, input),
  runTaskPlan: (input: TaskPlanInput) =>
    ipcRenderer.invoke(IPC_CHANNELS.taskPlanRun, input),
  resumeTaskPlan: (input: TaskPlanInput) =>
    ipcRenderer.invoke(IPC_CHANNELS.taskPlanResume, input),
  exportPngSvg: (input: PngSvgExportInput) => ipcRenderer.invoke(IPC_CHANNELS.exportPngSvg, input),
  exportOrigin: (input: OriginExportInput) => ipcRenderer.invoke(IPC_CHANNELS.exportOrigin, input),
  respondToCloseRequest: (response: CloseResponse) =>
    ipcRenderer.invoke(IPC_CHANNELS.closeResponse, response),
  onCoreStatus: (listener: (status: CoreStatus) => void) => coreStatusEvents.subscribe(listener),
  onTaskEvent: (listener: (event: TaskEvent) => void) => taskEvents.subscribe(listener),
  onWorkflowRuntimeEvent: (listener: (event: WorkflowRuntimeEvent) => void) =>
    workflowRuntimeEvents.subscribe(listener),
  onOpenResourceRequested: (listener: (request: OpenResourceRequest) => void) =>
    openResourceEvents.subscribe(listener),
  onCloseRequested: (listener: (request: CloseRequest) => void) =>
    closeRequestEvents.subscribe(listener),
} satisfies PlotAgentDesktopApi

contextBridge.exposeInMainWorld('plotAgentDesktop', desktop)
