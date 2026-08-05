import { randomUUID } from 'node:crypto'
import { existsSync } from 'node:fs'
import { delimiter, dirname, join } from 'node:path'
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'

import {
  CORE_PROTOCOL_VERSION,
  DESKTOP_API_VERSION,
  createCoreRequest,
  isCoreNotification,
  isCoreResponse,
  parseTaskEvent,
  type CoreErrorCode,
  type CoreProtocolMessage,
  type CoreResponse,
  type CoreStatus,
  type JsonValue,
  type PublicError,
  type TaskEvent,
} from '../../shared/desktop-contract.js'
import { encodeJsonLine, JsonLineDecoder, type FrameErrorCode } from './json-line-framing.js'
import {
  INITIAL_CORE_STATUS,
  publicCoreError,
  reduceSupervisorState,
  RestartBudget,
} from './supervisor-state.js'

export interface CoreLaunchSpec {
  readonly command: string
  readonly args: readonly string[]
  readonly cwd: string
  readonly env: NodeJS.ProcessEnv
}

export interface ResolveCoreLaunchSpecOptions {
  readonly appPath: string
  readonly isPackaged: boolean
  readonly platform: NodeJS.Platform
  readonly resourcesPath?: string
  readonly processEnv?: NodeJS.ProcessEnv
}

export const PACKAGED_CORE_RELATIVE_PATH = Object.freeze([
  'core',
  'plotagent-core',
  'plotagent-core.exe',
])

export function resolveCoreLaunchSpec({
  appPath,
  isPackaged,
  platform,
  resourcesPath,
  processEnv = process.env,
}: ResolveCoreLaunchSpecOptions): CoreLaunchSpec {
  if (isPackaged) {
    const packagedResourcesPath = resourcesPath ?? join(appPath, '..')
    const command = join(packagedResourcesPath, ...PACKAGED_CORE_RELATIVE_PATH)
    return {
      command,
      args: [],
      cwd: dirname(command),
      env: { ...processEnv },
    }
  }

  const configuredExecutable = processEnv.PLOTAGENT_CORE_EXECUTABLE?.trim()
  const developmentExecutable = platform === 'win32'
    ? join(appPath, '.venv', 'Scripts', 'python.exe')
    : join(appPath, '.venv', 'bin', 'python')
  const command = configuredExecutable ||
    (existsSync(developmentExecutable)
      ? developmentExecutable
      : platform === 'win32' ? 'python' : 'python3')

  const env = { ...processEnv }
  const sourcePath = join(appPath, 'src')
  env.PYTHONPATH = env.PYTHONPATH === undefined
    ? sourcePath
    : `${sourcePath}${delimiter}${env.PYTHONPATH}`

  return {
    command,
    args: ['-m', 'plotagent.desktop_core'],
    cwd: appPath,
    env,
  }
}

export interface PythonCoreSupervisorOptions {
  readonly launch: CoreLaunchSpec
  readonly startupTimeoutMs?: number
  readonly requestTimeoutMs?: number
  readonly heartbeatIntervalMs?: number
  readonly heartbeatTimeoutMs?: number
  readonly shutdownTimeoutMs?: number
  readonly maximumFrameBytes?: number
  readonly maximumRestarts?: number
  readonly restartWindowMs?: number
  readonly restartBaseDelayMs?: number
  readonly now?: () => number
  readonly spawnProcess?: (launch: CoreLaunchSpec) => ChildProcessWithoutNullStreams
}

interface PendingRequest {
  readonly resolve: (value: JsonValue) => void
  readonly reject: (error: Error) => void
  readonly timer: ReturnType<typeof setTimeout>
}

class CoreRequestError extends Error {
  constructor(readonly publicError: PublicError) {
    super(publicError.message)
  }
}

function isRecord(value: JsonValue): value is { [key: string]: JsonValue } {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function frameErrorToCoreError(code: FrameErrorCode): CoreErrorCode {
  return code === 'CORE_PROTOCOL_INVALID_MESSAGE'
    ? 'CORE_PROTOCOL_INVALID_MESSAGE'
    : 'CORE_PROTOCOL_INVALID_FRAME'
}

export class PythonCoreSupervisor {
  private status: CoreStatus = INITIAL_CORE_STATUS
  private child?: ChildProcessWithoutNullStreams
  private decoder: JsonLineDecoder
  private readonly restartBudget: RestartBudget
  private readonly statusListeners = new Set<(status: CoreStatus) => void>()
  private readonly taskListeners = new Set<(event: TaskEvent) => void>()
  private readonly pendingRequests = new Map<string, PendingRequest>()
  private startupTimer?: ReturnType<typeof setTimeout>
  private heartbeatTimer?: ReturnType<typeof setInterval>
  private restartTimer?: ReturnType<typeof setTimeout>
  private shutdownTimer?: ReturnType<typeof setTimeout>
  private stopPromise?: Promise<void>
  private resolveStop?: () => void
  private lastHeartbeatAt = 0
  private intentionalStop = false
  private failureInProgress = false
  private readonly startupTimeoutMs: number
  private readonly requestTimeoutMs: number
  private readonly heartbeatIntervalMs: number
  private readonly heartbeatTimeoutMs: number
  private readonly shutdownTimeoutMs: number
  private readonly maximumFrameBytes: number
  private readonly now: () => number
  private readonly spawnProcess: (launch: CoreLaunchSpec) => ChildProcessWithoutNullStreams

  constructor(private readonly options: PythonCoreSupervisorOptions) {
    this.startupTimeoutMs = options.startupTimeoutMs ?? 10_000
    this.requestTimeoutMs = options.requestTimeoutMs ?? 10_000
    this.heartbeatIntervalMs = options.heartbeatIntervalMs ?? 2_500
    this.heartbeatTimeoutMs = options.heartbeatTimeoutMs ?? 7_500
    this.shutdownTimeoutMs = options.shutdownTimeoutMs ?? 5_000
    this.maximumFrameBytes = options.maximumFrameBytes ?? 1024 * 1024
    this.now = options.now ?? Date.now
    this.spawnProcess = options.spawnProcess ?? ((launch) => spawn(
      launch.command,
      [...launch.args],
      {
        cwd: launch.cwd,
        env: launch.env,
        shell: false,
        windowsHide: true,
        stdio: ['pipe', 'pipe', 'pipe'],
      },
    ))
    this.decoder = new JsonLineDecoder(this.maximumFrameBytes)
    this.restartBudget = new RestartBudget(
      options.maximumRestarts ?? 3,
      options.restartWindowMs ?? 60_000,
      options.restartBaseDelayMs ?? 250,
    )
  }

  getStatus(): CoreStatus {
    return this.status
  }

  subscribeStatus(listener: (status: CoreStatus) => void): () => void {
    this.statusListeners.add(listener)
    return () => this.statusListeners.delete(listener)
  }

  subscribeTaskEvents(listener: (event: TaskEvent) => void): () => void {
    this.taskListeners.add(listener)
    return () => this.taskListeners.delete(listener)
  }

  start(): void {
    if (this.status.phase !== 'stopped' && this.status.phase !== 'failed' && this.status.phase !== 'restarting') {
      return
    }
    if (this.status.phase === 'failed') this.restartBudget.reset()
    this.intentionalStop = false
    this.failureInProgress = false
    this.transition({ type: 'start' })
    this.spawnCore()
  }

  retry(): boolean {
    if (this.status.phase !== 'failed') return false
    this.start()
    return true
  }

  rejectInvalidMessage(): void {
    this.handleFailure('CORE_PROTOCOL_INVALID_MESSAGE')
  }

  async request(method: string, params?: JsonValue): Promise<JsonValue> {
    if (this.status.phase !== 'ready') {
      throw new CoreRequestError(publicCoreError('CORE_NOT_READY'))
    }
    return this.sendRequest(method, params, this.requestTimeoutMs)
  }

  async stop(): Promise<void> {
    if (this.status.phase === 'stopped') return
    if (this.stopPromise !== undefined) return this.stopPromise

    this.intentionalStop = true
    this.clearRestartTimer()
    this.clearRuntimeTimers()
    this.transition({ type: 'stop' })

    if (this.child === undefined) {
      this.rejectAllPending(publicCoreError('CORE_NOT_READY'))
      this.finishStop()
      return
    }

    this.stopPromise = new Promise<void>((resolve) => {
      this.resolveStop = resolve
    })

    void this.sendRequest('system.shutdown', undefined, Math.min(2_000, this.shutdownTimeoutMs))
      .catch(() => undefined)

    this.shutdownTimer = setTimeout(() => {
      this.child?.kill()
      this.finishStop()
    }, this.shutdownTimeoutMs)

    return this.stopPromise
  }

  toPublicResult(error: unknown): PublicError {
    if (error instanceof CoreRequestError) return error.publicError
    return publicCoreError('CORE_REQUEST_FAILED')
  }

  private spawnCore(): void {
    this.decoder = new JsonLineDecoder(this.maximumFrameBytes)
    let child: ChildProcessWithoutNullStreams
    try {
      child = this.spawnProcess(this.options.launch)
    } catch {
      this.handleFailure('CORE_START_FAILED')
      return
    }

    this.child = child
    child.stdout.on('data', (chunk: Buffer) => this.handleStdout(child, chunk))
    // Core stderr is intentionally not persisted or forwarded; diagnostics own a scrubbed allowlist.
    child.stderr.on('data', () => undefined)
    child.once('error', () => {
      if (child === this.child) this.handleFailure('CORE_START_FAILED')
    })
    child.once('close', () => {
      if (child !== this.child) return
      for (const frame of this.decoder.end()) {
        if (frame.kind === 'error' && !this.intentionalStop) {
          this.handleFailure(frameErrorToCoreError(frame.code))
          return
        }
      }
      this.child = undefined
      if (this.intentionalStop) this.finishStop()
      else this.handleFailure('CORE_PROCESS_EXITED')
    })

    this.startupTimer = setTimeout(
      () => this.handleFailure('CORE_START_TIMEOUT'),
      this.startupTimeoutMs,
    )

    void this.sendRequest(
      'system.initialize',
      {
        protocol_version: CORE_PROTOCOL_VERSION,
        desktop_api_version: DESKTOP_API_VERSION,
      },
      this.startupTimeoutMs,
    ).then((result) => {
      if (child !== this.child || this.status.phase !== 'starting') return
      if (!isRecord(result) || result.protocol_version !== CORE_PROTOCOL_VERSION) {
        this.handleFailure('CORE_PROTOCOL_VERSION_UNSUPPORTED')
        return
      }
      if (this.startupTimer !== undefined) clearTimeout(this.startupTimer)
      this.startupTimer = undefined
      this.lastHeartbeatAt = this.now()
      this.transition({ type: 'ready' })
      this.startHeartbeat()
    }).catch((error: unknown) => {
      if (child !== this.child || this.intentionalStop) return
      const code = error instanceof CoreRequestError &&
        error.publicError.code === 'CORE_REQUEST_TIMEOUT'
        ? 'CORE_START_TIMEOUT'
        : 'CORE_START_FAILED'
      this.handleFailure(code)
    })
  }

  private handleStdout(child: ChildProcessWithoutNullStreams, chunk: Buffer): void {
    if (child !== this.child) return
    for (const frame of this.decoder.push(chunk)) {
      if (frame.kind === 'error') {
        this.handleFailure(frameErrorToCoreError(frame.code))
        return
      }
      this.handleMessage(frame.message)
    }
  }

  private handleMessage(message: CoreProtocolMessage): void {
    if (isCoreResponse(message)) {
      this.handleResponse(message)
      return
    }
    if (!isCoreNotification(message)) return

    if (message.method === 'health.heartbeat') {
      this.lastHeartbeatAt = this.now()
      return
    }
    if (message.method === 'task.event') {
      const event = parseTaskEvent(message.params)
      if (event === null) {
        this.handleFailure('CORE_PROTOCOL_INVALID_MESSAGE')
        return
      }
      for (const listener of this.taskListeners) listener(event)
    }
  }

  private handleResponse(response: CoreResponse): void {
    const pending = this.pendingRequests.get(response.id)
    if (pending === undefined) return
    this.pendingRequests.delete(response.id)
    clearTimeout(pending.timer)
    if ('error' in response) {
      pending.reject(new CoreRequestError(publicCoreError('CORE_REQUEST_FAILED')))
    } else {
      pending.resolve(response.result)
    }
  }

  private sendRequest(method: string, params: JsonValue | undefined, timeoutMs: number): Promise<JsonValue> {
    const child = this.child
    if (child === undefined || child.stdin.destroyed) {
      return Promise.reject(new CoreRequestError(publicCoreError('CORE_NOT_READY')))
    }
    const id = `req:${randomUUID()}`
    const request = createCoreRequest(id, method, params)

    return new Promise<JsonValue>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pendingRequests.delete(id)
        reject(new CoreRequestError(publicCoreError('CORE_REQUEST_TIMEOUT')))
      }, timeoutMs)
      this.pendingRequests.set(id, { resolve, reject, timer })
      child.stdin.write(encodeJsonLine(request), (error) => {
        if (error === null || error === undefined) return
        const pending = this.pendingRequests.get(id)
        if (pending === undefined) return
        this.pendingRequests.delete(id)
        clearTimeout(timer)
        reject(new CoreRequestError(publicCoreError('CORE_REQUEST_FAILED')))
      })
    })
  }

  private startHeartbeat(): void {
    this.heartbeatTimer = setInterval(() => {
      if (this.status.phase !== 'ready') return
      if (this.now() - this.lastHeartbeatAt > this.heartbeatTimeoutMs) {
        this.handleFailure('CORE_HEARTBEAT_TIMEOUT')
        return
      }
      void this.sendRequest('system.ping', undefined, this.heartbeatTimeoutMs)
        .then(() => {
          this.lastHeartbeatAt = this.now()
        })
        .catch(() => {
          if (this.now() - this.lastHeartbeatAt > this.heartbeatTimeoutMs) {
            this.handleFailure('CORE_HEARTBEAT_TIMEOUT')
          }
        })
    }, this.heartbeatIntervalMs)
  }

  private handleFailure(code: CoreErrorCode): void {
    if (this.intentionalStop || this.failureInProgress) return
    this.failureInProgress = true
    this.clearRuntimeTimers()
    this.rejectAllPending(publicCoreError(code))
    const failedChild = this.child
    this.child = undefined
    failedChild?.kill()

    const decision = this.restartBudget.recordFailure(this.now())
    if (!decision.restart || code === 'CORE_PROTOCOL_VERSION_UNSUPPORTED') {
      const finalCode = decision.restart || code === 'CORE_PROTOCOL_VERSION_UNSUPPORTED'
        ? code
        : 'CORE_RESTART_LIMIT_REACHED'
      this.transition({ type: 'failed', error: publicCoreError(finalCode) })
      this.failureInProgress = false
      return
    }

    this.transition({
      type: 'restart-scheduled',
      attempt: decision.attempt,
      error: publicCoreError(code),
    })
    this.restartTimer = setTimeout(() => {
      this.restartTimer = undefined
      this.failureInProgress = false
      if (this.status.phase !== 'restarting' || this.intentionalStop) return
      this.start()
    }, decision.delayMs)
  }

  private rejectAllPending(error: PublicError): void {
    for (const pending of this.pendingRequests.values()) {
      clearTimeout(pending.timer)
      pending.reject(new CoreRequestError(error))
    }
    this.pendingRequests.clear()
  }

  private clearRuntimeTimers(): void {
    if (this.startupTimer !== undefined) clearTimeout(this.startupTimer)
    if (this.heartbeatTimer !== undefined) clearInterval(this.heartbeatTimer)
    this.startupTimer = undefined
    this.heartbeatTimer = undefined
  }

  private clearRestartTimer(): void {
    if (this.restartTimer !== undefined) clearTimeout(this.restartTimer)
    this.restartTimer = undefined
  }

  private finishStop(): void {
    if (this.shutdownTimer !== undefined) clearTimeout(this.shutdownTimer)
    this.shutdownTimer = undefined
    this.child = undefined
    this.rejectAllPending(publicCoreError('CORE_NOT_READY'))
    if (this.status.phase === 'stopping') this.transition({ type: 'stopped' })
    const resolve = this.resolveStop
    this.resolveStop = undefined
    this.stopPromise = undefined
    resolve?.()
  }

  private transition(event: Parameters<typeof reduceSupervisorState>[1]): void {
    this.status = reduceSupervisorState(this.status, event)
    for (const listener of this.statusListeners) listener(this.status)
  }
}
