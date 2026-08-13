import { join } from 'node:path'

import { app, BrowserWindow, dialog, ipcMain, protocol, session } from 'electron'

import { PythonCoreSupervisor, resolveCoreLaunchSpec } from './core/python-supervisor.js'
import { PiAgentRuntime } from './agent/pi-runtime.js'
import { registerDesktopIpc, requestCoreAction } from './ipc/desktop-ipc.js'
import { AppCloseController } from './lifecycle/app-close-controller.js'
import {
  InMemoryResourceRegistry,
  SingleInstanceOpenRouter,
} from './single-instance-routing.js'
import {
  assertSecureWebPreferences,
  hardenSession,
  hardenWebContents,
} from './security/window-security.js'
import { registerResourceProtocol } from './security/resource-protocol.js'
import { ensureBundledSampleSource } from './sample-source.js'
import { TaskTracker } from './tasks/task-state.js'
import { IPC_CHANNELS } from '../shared/desktop-contract.js'

let mainWindow: BrowserWindow | undefined

protocol.registerSchemesAsPrivileged([{
  scheme: 'plotagent-resource',
  privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: false },
}])

const resourceRegistry = new InMemoryResourceRegistry()
const openRouter = new SingleInstanceOpenRouter(resourceRegistry)
const tasks = new TaskTracker()
const supervisor = new PythonCoreSupervisor({
  launch: resolveCoreLaunchSpec({
    appPath: app.getAppPath(),
    isPackaged: app.isPackaged,
    platform: process.platform,
    resourcesPath: process.resourcesPath,
  }),
})

function sendToRenderer(channel: string, value: unknown): void {
  if (mainWindow === undefined || mainWindow.isDestroyed()) return
  mainWindow.webContents.send(channel, value)
}

const piAgentRuntime = new PiAgentRuntime({
  core: supervisor,
  emit: (event) => sendToRenderer(IPC_CHANNELS.agentRuntimeEvent, event),
})

const closeController = new AppCloseController({
  getTasks: () => tasks.snapshot(),
  cancelAllTasks: () => requestCoreAction(supervisor, 'tasks.cancel_all'),
  stopCore: () => supervisor.stop(),
  emitCloseRequest: (request) => sendToRenderer(IPC_CHANNELS.lifecycleCloseRequested, request),
  quit: () => app.quit(),
})

function createWindow(): BrowserWindow {
  const webPreferences = {
    preload: join(__dirname, '../preload/index.cjs'),
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true,
    webSecurity: true,
    webviewTag: false,
    allowRunningInsecureContent: false,
    navigateOnDragDrop: false,
    safeDialogs: true,
    spellcheck: false,
  } as const
  assertSecureWebPreferences(webPreferences)

  const window = new BrowserWindow({
    width: 1440,
    height: 940,
    minWidth: 1100,
    minHeight: 720,
    show: false,
    backgroundColor: '#ffffff',
    title: 'PlotAgent',
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#f4f7f5',
      symbolColor: '#26352e',
      height: 36,
    },
    webPreferences,
  })

  window.once('ready-to-show', () => window.show())
  window.on('close', (event) => closeController.handleWindowClose(event))
  window.on('closed', () => {
    if (mainWindow === window) mainWindow = undefined
  })

  if (process.env.ELECTRON_RENDERER_URL) {
    void window.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    void window.loadFile(join(__dirname, '../renderer/index.html'))
  }

  return window
}

function focusMainWindow(): void {
  if (mainWindow === undefined) return
  if (mainWindow.isMinimized()) mainWindow.restore()
  mainWindow.show()
  mainWindow.focus()
}

const hasSingleInstanceLock = app.requestSingleInstanceLock()

if (!hasSingleInstanceLock) {
  app.quit()
} else {
  app.on('second-instance', (_event, commandLine, workingDirectory) => {
    openRouter.routeCommandLine(commandLine, workingDirectory)
    focusMainWindow()
  })

  app.on('open-file', (event, path) => {
    event.preventDefault()
    openRouter.routePath(path)
  })

  app.on('before-quit', (event) => closeController.handleBeforeQuit(event))

  supervisor.subscribeStatus((status) => {
    sendToRenderer(IPC_CHANNELS.coreStatusChanged, status)
  })

  supervisor.subscribeTaskEvents((event) => {
    if (!tasks.apply(event)) {
      supervisor.rejectInvalidMessage()
      return
    }
    sendToRenderer(IPC_CHANNELS.taskEvent, event)
  })

  tasks.subscribe((snapshot) => closeController.handleTaskSnapshot(snapshot))

  openRouter.routeCommandLine(process.argv.slice(1), process.cwd())

  app.whenReady().then(() => {
    hardenSession(session.defaultSession)
    registerResourceProtocol(session.defaultSession, resourceRegistry)
    app.on('web-contents-created', (_event, contents) => hardenWebContents(contents))
    registerDesktopIpc({
      ipcMain,
      supervisor,
      tasks,
      closeController,
      dialog,
      getWindow: () => mainWindow,
      resources: resourceRegistry,
      ensureSampleSource: () => ensureBundledSampleSource(app.getPath('userData')),
      piAgentRuntime,
    })
    mainWindow = createWindow()
    mainWindow.webContents.once('did-finish-load', () => {
      openRouter.setListener((request) => {
        sendToRenderer(IPC_CHANNELS.openResourceRequested, request)
        focusMainWindow()
      })
    })
    supervisor.start()

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) mainWindow = createWindow()
    })
  })

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit()
  })
}
