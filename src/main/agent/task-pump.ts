import type { AgentActivation, AgentYieldContract } from '../../shared/generated/contracts.js'

export interface DurableTaskCoreBridge {
  request(method: string, params: unknown, timeoutMs?: number): Promise<unknown>
}

export interface ActivationRuntime {
  run(activation: AgentActivation): Promise<AgentYieldContract>
  abort(activationId?: string): boolean
}

export type TaskPumpWaitReason =
  | 'idle'
  | 'awaiting_input'
  | 'awaiting_confirmation'
  | 'awaiting_reconfirmation'
  | 'blocked'
  | 'terminal'
  | 'execution_pending'
  | 'verification_pending'
  | 'delivery_pending'

export type TaskPumpDirective =
  | { readonly kind: 'run_activation'; readonly activation: AgentActivation }
  | { readonly kind: 'wait'; readonly reason: TaskPumpWaitReason; readonly taskState?: string }

export interface TaskPumpResult {
  readonly projectId: string
  readonly taskId: string
  readonly reason: TaskPumpWaitReason
  readonly taskState?: string
  readonly activationsRun: number
  /** The typed terminal yield that caused a non-confirmation wait point. */
  readonly terminalYield?: AgentYieldContract
}

export type TaskPumpStage =
  | 'checking_next_action'
  | 'activation_started'
  | 'activation_yielded'
  | 'waiting'
  | 'cancelled'
  | 'failed'

export interface TaskPumpEvent {
  readonly schemaVersion: '2.0'
  readonly projectId: string
  readonly taskId: string
  readonly sequence: number
  readonly stage: TaskPumpStage
  readonly activationId?: string
}

export interface AgentTaskPumpOptions {
  readonly core: DurableTaskCoreBridge
  readonly runtime: ActivationRuntime
  readonly emit: (event: TaskPumpEvent) => void
  readonly coreTimeoutMs?: number
  readonly maxImmediateActivations?: number
}

export class TaskPumpProtocolError extends Error {
  constructor(readonly code: string, message: string) {
    super(message)
  }
}

interface ActivePump {
  readonly key: string
  readonly generation: number
  activationId?: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function requiredString(value: unknown, name: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new TaskPumpProtocolError('TASK_PUMP_PROTOCOL_INVALID', `${name} was invalid.`)
  }
  return value
}

function requiredInteger(value: unknown, name: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 1) {
    throw new TaskPumpProtocolError('TASK_PUMP_PROTOCOL_INVALID', `${name} was invalid.`)
  }
  return value
}

function parseActivation(value: unknown): AgentActivation {
  if (!isRecord(value)) {
    throw new TaskPumpProtocolError('TASK_PUMP_PROTOCOL_INVALID', 'Activation was invalid.')
  }
  const activation: AgentActivation = value as AgentActivation
  requiredString(activation.activation_id, 'activation_id')
  requiredString(activation.task_id, 'task_id')
  requiredInteger(activation.task_version, 'task_version')
  if (!Array.isArray(activation.allowed_tools)) {
    throw new TaskPumpProtocolError('TASK_PUMP_PROTOCOL_INVALID', 'Activation tools were invalid.')
  }
  return activation
}

function parseDirective(value: unknown): TaskPumpDirective {
  if (!isRecord(value)) {
    throw new TaskPumpProtocolError('TASK_PUMP_PROTOCOL_INVALID', 'Core directive was invalid.')
  }
  if (value.kind === 'run_activation') {
    return { kind: 'run_activation', activation: parseActivation(value.activation) }
  }
  if (value.kind !== 'wait') {
    throw new TaskPumpProtocolError('TASK_PUMP_PROTOCOL_INVALID', 'Core directive kind was invalid.')
  }
  const reasons: ReadonlySet<string> = new Set([
    'idle',
    'awaiting_input',
    'awaiting_confirmation',
    'awaiting_reconfirmation',
    'blocked',
    'terminal',
    'execution_pending',
    'verification_pending',
    'delivery_pending',
  ])
  const reason = requiredString(value.reason, 'wait reason')
  if (!reasons.has(reason)) {
    throw new TaskPumpProtocolError('TASK_PUMP_PROTOCOL_INVALID', 'Core wait reason was invalid.')
  }
  return {
    kind: 'wait',
    reason: reason as TaskPumpWaitReason,
    ...(typeof value.task_state === 'string' ? { taskState: value.task_state } : {}),
  }
}

function assertYieldIdentity(
  activation: AgentActivation,
  yielded: AgentYieldContract,
): void {
  if (
    yielded.activation_id !== activation.activation_id
    || yielded.task_id !== activation.task_id
    || yielded.task_version !== activation.task_version
  ) {
    throw new TaskPumpProtocolError(
      'TASK_PUMP_YIELD_IDENTITY_MISMATCH',
      'Runtime yield does not belong to the active Core activation.',
    )
  }
}

/**
 * Pull-based coordinator for the v2 durable task chain.
 *
 * Core alone decides the next action and performs every state transition. The
 * pump only runs requested Pi activations and submits their typed terminal
 * yields back to Core. Execution/verification directives remain explicit wait
 * points until their P6 handlers are installed.
 */
export class AgentTaskPump {
  private readonly core: DurableTaskCoreBridge
  private readonly runtime: ActivationRuntime
  private readonly emitEvent: AgentTaskPumpOptions['emit']
  private readonly coreTimeoutMs: number
  private readonly maxImmediateActivations: number
  private active?: ActivePump
  private generation = 0
  private sequence = 0

  constructor(options: AgentTaskPumpOptions) {
    this.core = options.core
    this.runtime = options.runtime
    this.emitEvent = options.emit
    this.coreTimeoutMs = options.coreTimeoutMs ?? 15_000
    this.maxImmediateActivations = options.maxImmediateActivations ?? 4
  }

  cancel(projectId: string, taskId: string): boolean {
    const key = this.key(projectId, taskId)
    if (this.active?.key !== key) return false
    this.generation += 1
    this.runtime.abort(this.active.activationId)
    this.emit(projectId, taskId, 'cancelled', this.active.activationId)
    return true
  }

  async drain(projectId: string, taskId: string): Promise<TaskPumpResult> {
    const normalizedProjectId = requiredString(projectId, 'project_id')
    const normalizedTaskId = requiredString(taskId, 'task_id')
    if (this.active !== undefined) {
      throw new TaskPumpProtocolError(
        'TASK_PUMP_BUSY',
        'Another durable task pump is already active in this Main process.',
      )
    }
    const generation = ++this.generation
    const current: ActivePump = {
      key: this.key(normalizedProjectId, normalizedTaskId),
      generation,
    }
    this.active = current
    let activationsRun = 0
    let lastYield: AgentYieldContract | undefined
    try {
      while (activationsRun < this.maxImmediateActivations) {
        this.assertCurrent(generation)
        this.emit(normalizedProjectId, normalizedTaskId, 'checking_next_action')
        const rawDirective = await this.core.request(
          'agent.tasks.pump.next',
          { project_id: normalizedProjectId, task_id: normalizedTaskId },
          this.coreTimeoutMs,
        )
        this.assertCurrent(generation)
        const directive = parseDirective(rawDirective)
        if (directive.kind === 'wait') {
          this.emit(normalizedProjectId, normalizedTaskId, 'waiting')
          return {
            projectId: normalizedProjectId,
            taskId: normalizedTaskId,
            reason: directive.reason,
            ...(directive.taskState === undefined ? {} : { taskState: directive.taskState }),
            activationsRun,
            ...(directive.reason === 'awaiting_confirmation' || lastYield === undefined
              ? {}
              : { terminalYield: lastYield }),
          }
        }

        const activation = directive.activation
        if (activation.task_id !== normalizedTaskId) {
          throw new TaskPumpProtocolError(
            'TASK_PUMP_ACTIVATION_MISMATCH',
            'Core returned an activation for another task.',
          )
        }
        current.activationId = activation.activation_id
        await this.core.request(
          'agent.tasks.activation.running',
          { project_id: normalizedProjectId, activation_id: activation.activation_id },
          this.coreTimeoutMs,
        )
        this.assertCurrent(generation)
        this.emit(
          normalizedProjectId,
          normalizedTaskId,
          'activation_started',
          activation.activation_id,
        )
        const yielded = await this.runtime.run(activation)
        lastYield = yielded
        this.assertCurrent(generation)
        assertYieldIdentity(activation, yielded)
        await this.core.request(
          'agent.tasks.yield.accept',
          { project_id: normalizedProjectId, yield: yielded },
          this.coreTimeoutMs,
        )
        this.assertCurrent(generation)
        activationsRun += 1
        this.emit(
          normalizedProjectId,
          normalizedTaskId,
          'activation_yielded',
          activation.activation_id,
        )
        current.activationId = undefined
      }
      throw new TaskPumpProtocolError(
        'TASK_PUMP_IMMEDIATE_LIMIT',
        'Core kept requesting immediate activations without reaching a durable wait point.',
      )
    } catch (error) {
      if (generation !== this.generation) {
        return {
          projectId: normalizedProjectId,
          taskId: normalizedTaskId,
          reason: 'terminal',
          taskState: 'cancelled',
          activationsRun,
        }
      }
      this.emit(normalizedProjectId, normalizedTaskId, 'failed', current.activationId)
      throw error
    } finally {
      if (this.active?.generation === generation) this.active = undefined
    }
  }

  private key(projectId: string, taskId: string): string {
    return `${projectId}\u0000${taskId}`
  }

  private assertCurrent(generation: number): void {
    if (generation !== this.generation) {
      throw new TaskPumpProtocolError(
        'TASK_PUMP_SUPERSEDED',
        'The durable task pump was cancelled or superseded.',
      )
    }
  }

  private emit(
    projectId: string,
    taskId: string,
    stage: TaskPumpStage,
    activationId?: string,
  ): void {
    this.sequence += 1
    this.emitEvent({
      schemaVersion: '2.0',
      projectId,
      taskId,
      sequence: this.sequence,
      stage,
      ...(activationId === undefined ? {} : { activationId }),
    })
  }
}
