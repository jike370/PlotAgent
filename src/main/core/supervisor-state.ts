import type {
  CoreErrorCode,
  CoreStatus,
  PublicError,
} from '../../shared/desktop-contract.js'

export type SupervisorStateEvent =
  | { readonly type: 'start' }
  | { readonly type: 'spawned' }
  | { readonly type: 'ready' }
  | { readonly type: 'restart-scheduled'; readonly attempt: number; readonly error: PublicError }
  | { readonly type: 'stop' }
  | { readonly type: 'stopped' }
  | { readonly type: 'failed'; readonly error: PublicError }

export const INITIAL_CORE_STATUS: CoreStatus = {
  phase: 'stopped',
  restartAttempt: 0,
}

const LEGAL_EVENTS: Readonly<Record<CoreStatus['phase'], ReadonlySet<SupervisorStateEvent['type']>>> = {
  stopped: new Set(['start']),
  starting: new Set(['spawned', 'ready', 'restart-scheduled', 'stop', 'failed']),
  ready: new Set(['restart-scheduled', 'stop', 'failed']),
  restarting: new Set(['start', 'stop', 'failed']),
  stopping: new Set(['stopped', 'failed']),
  failed: new Set(['start', 'stop']),
}

export function reduceSupervisorState(
  current: CoreStatus,
  event: SupervisorStateEvent,
): CoreStatus {
  if (!LEGAL_EVENTS[current.phase].has(event.type)) {
    throw new Error(`Illegal Core supervisor transition: ${current.phase} + ${event.type}`)
  }

  switch (event.type) {
    case 'start':
    case 'spawned':
      return {
        phase: 'starting',
        restartAttempt: current.phase === 'restarting' ? current.restartAttempt : 0,
      }
    case 'ready':
      return { phase: 'ready', restartAttempt: current.restartAttempt }
    case 'restart-scheduled':
      return {
        phase: 'restarting',
        restartAttempt: event.attempt,
        error: event.error,
      }
    case 'stop':
      return { phase: 'stopping', restartAttempt: current.restartAttempt }
    case 'stopped':
      return { phase: 'stopped', restartAttempt: 0 }
    case 'failed':
      return {
        phase: 'failed',
        restartAttempt: current.restartAttempt,
        error: event.error,
      }
  }
}

export interface RestartDecision {
  readonly restart: boolean
  readonly attempt: number
  readonly delayMs: number
}

export class RestartBudget {
  private failures: number[] = []

  constructor(
    private readonly maximumRestarts = 3,
    private readonly windowMs = 60_000,
    private readonly baseDelayMs = 250,
  ) {
    if (maximumRestarts < 0 || windowMs <= 0 || baseDelayMs < 0) {
      throw new Error('Invalid restart policy')
    }
  }

  recordFailure(now: number): RestartDecision {
    this.failures = this.failures.filter((timestamp) => now - timestamp <= this.windowMs)
    if (this.failures.length >= this.maximumRestarts) {
      return { restart: false, attempt: this.failures.length, delayMs: 0 }
    }
    this.failures.push(now)
    const attempt = this.failures.length
    return {
      restart: true,
      attempt,
      delayMs: this.baseDelayMs * 2 ** (attempt - 1),
    }
  }

  reset(): void {
    this.failures = []
  }
}

const ERROR_MESSAGES: Readonly<Record<CoreErrorCode, { message: string; retryable: boolean }>> = {
  CORE_ENTRYPOINT_MISSING: { message: 'The local Core entrypoint is unavailable.', retryable: true },
  CORE_HEARTBEAT_TIMEOUT: { message: 'The local Core stopped responding.', retryable: true },
  CORE_NOT_READY: { message: 'The local Core is not ready.', retryable: true },
  CORE_PROCESS_EXITED: { message: 'The local Core exited unexpectedly.', retryable: true },
  CORE_PROTOCOL_INVALID_FRAME: { message: 'The local Core sent an invalid protocol frame.', retryable: true },
  CORE_PROTOCOL_INVALID_MESSAGE: { message: 'The local Core sent an invalid protocol message.', retryable: true },
  CORE_PROTOCOL_VERSION_UNSUPPORTED: { message: 'The local Core protocol version is unsupported.', retryable: false },
  CORE_REQUEST_FAILED: { message: 'The local Core rejected the request.', retryable: true },
  CORE_REQUEST_TIMEOUT: { message: 'The local Core request timed out.', retryable: true },
  CORE_RESTART_LIMIT_REACHED: { message: 'The local Core restart limit was reached.', retryable: true },
  CORE_SHUTDOWN_TIMEOUT: { message: 'The local Core did not stop in time.', retryable: false },
  CORE_START_FAILED: { message: 'The local Core could not be started.', retryable: true },
  CORE_START_TIMEOUT: { message: 'The local Core did not become ready in time.', retryable: true },
}

export function publicCoreError(code: CoreErrorCode): PublicError {
  return { code, ...ERROR_MESSAGES[code] }
}
