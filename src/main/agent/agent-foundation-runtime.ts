import { randomUUID } from 'node:crypto'

import type { JsonValue } from '../../shared/desktop-contract.js'
import { CorePiRuntimeHostV2, type PiRuntimeCoreBridgeV2 } from './pi-runtime-host-v2.js'
import {
  PiRuntimeAdapterV2,
  type PiRuntimeV2Event,
} from './pi-runtime-v2.js'
import {
  AgentTaskPump,
  type ActivationRuntime,
  type TaskPumpEvent,
  type TaskPumpResult,
} from './task-pump.js'

export interface AgentFoundationRunInput {
  readonly projectId: string
  readonly selectedSources: readonly {
    readonly datasetId: string
    readonly sourceVersion: number
  }[]
  readonly selectedProfileIds?: readonly string[]
  readonly selectedPlotIds?: readonly string[]
  readonly expectedProjectVersion: number
  readonly instruction: string
}

export interface AgentFoundationPlanInput {
  readonly projectId: string
  readonly planId: string
}

export interface AgentFoundationRuntimeEvent {
  readonly schemaVersion: '1.0'
  readonly runId: string
  readonly projectId: string
  readonly sequence: number
  readonly stage:
    | 'preparing_context'
    | 'inspecting_data'
    | 'planning'
    | 'validating_draft'
    | 'saving_plan'
    | 'completed'
    | 'cancelled'
    | 'failed'
  readonly label: string
}

export interface AgentFoundationRuntimeOptions {
  readonly core: PiRuntimeCoreBridgeV2
  readonly emit: (event: AgentFoundationRuntimeEvent) => void
  readonly createRuntime?: (
    host: CorePiRuntimeHostV2,
    emit: (event: PiRuntimeV2Event) => void,
  ) => ActivationRuntime
  readonly clock?: () => Date
  readonly id?: () => string
}

export class AgentFoundationRuntimeError extends Error {
  constructor(readonly code: string, message: string) {
    super(message)
  }
}

interface PlanAuthority {
  readonly projectId: string
  readonly taskId: string
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new AgentFoundationRuntimeError('AGENT_V2_PROTOCOL_INVALID', `${label} was invalid.`)
  }
  return value as Record<string, unknown>
}

function string(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new AgentFoundationRuntimeError('AGENT_V2_PROTOCOL_INVALID', `${label} was invalid.`)
  }
  return value
}

function integer(value: unknown, label: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) {
    throw new AgentFoundationRuntimeError('AGENT_V2_PROTOCOL_INVALID', `${label} was invalid.`)
  }
  return value
}

function json(value: unknown): JsonValue {
  return JSON.parse(JSON.stringify(value)) as JsonValue
}

function sourceContentHash(
  value: unknown,
  datasetId: string,
  sourceVersion: number,
): string | undefined {
  const queue: unknown[] = [value]
  while (queue.length > 0) {
    const current = queue.shift()
    if (Array.isArray(current)) {
      queue.push(...current)
      continue
    }
    if (current === null || typeof current !== 'object') continue
    const candidate = current as Record<string, unknown>
    if (
      candidate.source_dataset_id === datasetId
      && candidate.source_version === sourceVersion
      && typeof candidate.content_hash === 'string'
      && /^[a-f0-9]{64}$/i.test(candidate.content_hash)
    ) return candidate.content_hash.toLowerCase()
    queue.push(...Object.values(candidate))
  }
  return undefined
}

function planIdentity(value: unknown): { planId: string; taskId: string } {
  const view = record(value, 'task plan view')
  const plan = record(view.plan, 'task plan')
  const task = record(view.task, 'task checkpoint')
  return {
    planId: string(plan.plan_id, 'plan ID'),
    taskId: string(task.task_id, 'task ID'),
  }
}

function stoppedBeforeConfirmation(result: TaskPumpResult): AgentFoundationRuntimeError {
  const yielded = result.terminalYield
  if (yielded?.outcome === 'runtime_failed') {
    if (yielded.error.code === 'PI_V2_PROVIDER_FAILED') {
      return new AgentFoundationRuntimeError(
        'AGENT_V2_PROVIDER_UNAVAILABLE',
        '模型服务不可用，未生成计划，也未修改项目。请检查 Base URL、网络或服务状态后重试。',
      )
    }
    return new AgentFoundationRuntimeError(
      'AGENT_V2_RUNTIME_FAILED',
      'Agent 运行失败，未生成计划，也未修改项目。请重试；若持续发生，请检查模型服务。',
    )
  }
  if (yielded?.outcome === 'budget_exhausted' && yielded.exhausted_budget === 'wall_time') {
    return new AgentFoundationRuntimeError(
      'AGENT_V2_DECISION_TIMEOUT',
      '模型服务响应超时，未生成计划，也未修改项目。可以直接重试。',
    )
  }
  if (yielded?.outcome === 'blocked') {
    return new AgentFoundationRuntimeError(
      'AGENT_V2_BLOCKED',
      `${yielded.message} 未生成计划，也未修改项目。`,
    )
  }
  if (yielded?.outcome === 'unsupported') {
    return new AgentFoundationRuntimeError('AGENT_V2_UNSUPPORTED', yielded.message)
  }
  if (yielded?.outcome === 'needs_input') {
    const prompts = yielded.questions.map((question) => question.prompt).join('；')
    return new AgentFoundationRuntimeError(
      'AGENT_V2_NEEDS_INPUT',
      `Agent 需要补充信息：${prompts}`,
    )
  }
  if (yielded?.outcome === 'cancelled') {
    return new AgentFoundationRuntimeError('AGENT_V2_CANCELLED', '本轮 Agent 任务已取消，项目未修改。')
  }
  return new AgentFoundationRuntimeError(
    'AGENT_V2_PLAN_NOT_READY',
    'Agent 未生成可确认计划，项目未修改。请重试。',
  )
}

/**
 * Test-gated Main coordinator for the durable Agent foundation.
 *
 * P7 accepts a bounded batch of immutable sources and user-selected chart
 * profiles while pre-existing plot targets remain outside this creation slice.
 */
export class AgentFoundationRuntime {
  private readonly core: PiRuntimeCoreBridgeV2
  private readonly emitEvent: AgentFoundationRuntimeOptions['emit']
  private readonly createRuntime: NonNullable<AgentFoundationRuntimeOptions['createRuntime']>
  private readonly clock: () => Date
  private readonly id: () => string
  private readonly authorityByPlan = new Map<string, PlanAuthority>()
  private sequence = 0

  constructor(options: AgentFoundationRuntimeOptions) {
    this.core = options.core
    this.emitEvent = options.emit
    this.createRuntime = options.createRuntime ?? ((host, emit) => (
      new PiRuntimeAdapterV2({ host, emit })
    ))
    this.clock = options.clock ?? (() => new Date())
    this.id = options.id ?? randomUUID
  }

  canRun(input: AgentFoundationRunInput): boolean {
    return input.selectedSources.length >= 1
      && input.selectedSources.length <= 8
      && (input.selectedProfileIds?.length ?? 0) >= 1
      && (input.selectedProfileIds?.length ?? 0) <= 34
      && (input.selectedPlotIds === undefined || input.selectedPlotIds.length === 0)
  }

  ownsPlan(planId: string): boolean {
    return this.authorityByPlan.has(planId)
  }

  async list(projectId: string): Promise<JsonValue> {
    const result = record(await this.core.request(
      'agent.tasks.list',
      { project_id: projectId, limit: 100 },
      15_000,
    ), 'durable task list')
    if (!Array.isArray(result.tasks)) {
      throw new AgentFoundationRuntimeError(
        'AGENT_V2_PROTOCOL_INVALID',
        'Core returned an invalid durable task list.',
      )
    }
    const tasks = result.tasks.flatMap((value) => {
      const task = record(value, 'durable task checkpoint')
      return task.intent === null || task.intent === undefined
        ? []
        : [{ taskId: string(task.task_id, 'task ID') }]
    })
    const newestFirst = await Promise.all(tasks.map(async ({ taskId }) => {
      const view = await this.core.request(
        'agent.tasks.plan.get',
        { project_id: projectId, task_id: taskId },
        15_000,
      )
      const identity = planIdentity(view)
      if (identity.taskId !== taskId) {
        throw new AgentFoundationRuntimeError(
          'AGENT_V2_TASK_MISMATCH',
          'Recovered plan does not belong to its durable task.',
        )
      }
      this.authorityByPlan.set(identity.planId, { projectId, taskId })
      return json(view)
    }))
    // Core lists durable tasks newest-first while the renderer selects the last plan.
    return { task_plans: newestFirst.reverse() }
  }

  async run(input: AgentFoundationRunInput): Promise<JsonValue> {
    if (!this.canRun(input)) {
      throw new AgentFoundationRuntimeError(
        'AGENT_V2_SLICE_UNSUPPORTED',
        '当前新 Agent 入口支持 1–8 个数据表和已选择图类的新建批量任务。',
      )
    }
    const profileIds = input.selectedProfileIds
    if (profileIds === undefined || profileIds.length === 0) {
      throw new AgentFoundationRuntimeError('AGENT_V2_SLICE_UNSUPPORTED', '任务范围不完整。')
    }
    const runToken = this.id()
    const taskId = `task:${runToken}`
    const runId = `workflow:${runToken}`
    this.emit(runId, input.projectId, 'preparing_context', '正在读取所选数据…')
    const selectedSources = await Promise.all(input.selectedSources.map(async (source) => {
      const described = await this.core.request('datasets.describe', {
        project_id: input.projectId,
        source_dataset_id: source.datasetId,
        source_version: source.sourceVersion,
      })
      const contentHash = sourceContentHash(described, source.datasetId, source.sourceVersion)
      if (contentHash === undefined) {
        throw new AgentFoundationRuntimeError(
          'AGENT_V2_SOURCE_IDENTITY_MISSING',
          '所选数据缺少不可变内容标识，请重新选择数据表。',
        )
      }
      return {
        source_dataset_id: source.datasetId,
        source_version: source.sourceVersion,
        content_hash: contentHash,
      }
    }))
    await this.core.request('agent.tasks.create', {
      project_id: input.projectId,
      envelope: {
        schema_version: 'task-envelope.v2',
        task_id: taskId,
        task_version: 1,
        project_id: input.projectId,
        project_revision: input.expectedProjectVersion,
        original_instruction: input.instruction,
        locale: 'zh-CN',
        selected_sources: selectedSources,
        selected_plots: [],
        selected_profile_ids: [...profileIds],
        authorized_resources: [],
        // Core owns the durable task ceiling. A zero cost budget is a hard stop,
        // so the desktop entry must provide an explicit finite allowance instead
        // of relying on TaskBudgetLimits' fail-closed default.
        budget: { max_estimated_cost: 10 },
        created_at: this.clock().toISOString(),
      },
    })

    const host = new CorePiRuntimeHostV2(this.core, input.projectId)
    const runtime = this.createRuntime(host, (event) => this.forwardRuntime(runId, input.projectId, event))
    const pump = new AgentTaskPump({
      core: this.core,
      runtime,
      emit: (event) => this.forwardPump(runId, input.projectId, event),
    })
    const drained = await pump.drain(input.projectId, taskId)
    if (drained.reason !== 'awaiting_confirmation') {
      throw stoppedBeforeConfirmation(drained)
    }
    const view = await this.core.request(
      'agent.tasks.plan.get',
      { project_id: input.projectId, task_id: taskId },
      15_000,
    )
    const identity = planIdentity(view)
    if (identity.taskId !== taskId) {
      throw new AgentFoundationRuntimeError('AGENT_V2_TASK_MISMATCH', '计划不属于当前任务。')
    }
    this.authorityByPlan.set(identity.planId, { projectId: input.projectId, taskId })
    this.emit(runId, input.projectId, 'completed', '计划已生成，等待确认')
    return json(view)
  }

  async get(input: AgentFoundationPlanInput): Promise<JsonValue> {
    const authority = this.authority(input)
    return json(await this.core.request('agent.tasks.plan.get', {
      project_id: authority.projectId,
      task_id: authority.taskId,
    }))
  }

  async confirm(input: AgentFoundationPlanInput): Promise<JsonValue> {
    const authority = this.authority(input)
    const view = record(await this.get(input), 'task plan view')
    const task = record(view.task, 'task checkpoint')
    await this.core.request('agent.tasks.plan.confirm', {
      project_id: authority.projectId,
      task_id: authority.taskId,
      expected_task_version: integer(task.task_version, 'task version'),
      user_event_id: `user-event:${this.id()}`,
      plan_hash: string(view.plan_hash, 'plan hash'),
    })
    return await this.get(input)
  }

  async reject(input: AgentFoundationPlanInput): Promise<JsonValue> {
    const authority = this.authority(input)
    const view = record(await this.get(input), 'task plan view')
    const task = record(view.task, 'task checkpoint')
    await this.core.request('agent.tasks.plan.reject', {
      project_id: authority.projectId,
      task_id: authority.taskId,
      expected_task_version: integer(task.task_version, 'task version'),
      user_event_id: `user-event:${this.id()}`,
      plan_hash: string(view.plan_hash, 'plan hash'),
    })
    return await this.get(input)
  }

  async execute(input: AgentFoundationPlanInput): Promise<JsonValue> {
    const authority = this.authority(input)
    let view = record(await this.get(input), 'durable task plan view')
    let task = record(view.task, 'durable execution task')
    if (task.state !== 'partial') {
      const executed = record(await this.core.request(
        'agent.tasks.execute',
        { project_id: authority.projectId, task_id: authority.taskId },
        900_000,
      ), 'durable execution result')
      task = record(executed.task, 'durable execution task')
    }
    if (task.state === 'partial') {
      const runId = `workflow:repair:${authority.taskId.replace(/^task:/, '')}`
      this.emit(runId, authority.projectId, 'planning', '正在分析失败项并保留已成功结果…')
      const host = new CorePiRuntimeHostV2(this.core, authority.projectId)
      const runtime = this.createRuntime(
        host,
        (event) => this.forwardRuntime(runId, authority.projectId, event),
      )
      const pump = new AgentTaskPump({
        core: this.core,
        runtime,
        emit: (event) => this.forwardPump(runId, authority.projectId, event),
      })
      const drained = await pump.drain(authority.projectId, authority.taskId)
      if (drained.reason === 'execution_pending') {
        this.emit(runId, authority.projectId, 'planning', '正在仅重试失败项…')
        await this.core.request(
          'agent.tasks.execute',
          { project_id: authority.projectId, task_id: authority.taskId },
          900_000,
        )
      }
    }
    view = record(await this.get(input), 'durable task plan view')
    return json(view)
  }

  private authority(input: AgentFoundationPlanInput): PlanAuthority {
    const authority = this.authorityByPlan.get(input.planId)
    if (authority === undefined || authority.projectId !== input.projectId) {
      throw new AgentFoundationRuntimeError(
        'AGENT_V2_PLAN_UNKNOWN',
        '当前桌面会话中找不到该 Agent 计划。',
      )
    }
    return authority
  }

  private forwardRuntime(runId: string, projectId: string, event: PiRuntimeV2Event): void {
    const details: Record<PiRuntimeV2Event['stage'], [AgentFoundationRuntimeEvent['stage'], string]> = {
      preparing_context: ['preparing_context', '正在准备 Agent 上下文…'],
      model_turn: ['planning', 'Agent 正在检查数据并规划…'],
      tool_started: ['inspecting_data', 'Agent 正在读取数据证据…'],
      tool_finished: ['planning', '数据证据已返回，继续规划…'],
      yielded: ['validating_draft', '正在校验字段绑定与图形合同…'],
      cancelled: ['cancelled', 'Agent 任务已取消'],
      failed: ['failed', 'Agent 运行失败'],
    }
    const [stage, label] = details[event.stage]
    this.emit(runId, projectId, stage, label)
  }

  private forwardPump(runId: string, projectId: string, event: TaskPumpEvent): void {
    if (event.stage === 'activation_started') {
      this.emit(runId, projectId, 'planning', 'Agent 正在生成结构化任务意图…')
    } else if (event.stage === 'activation_yielded') {
      this.emit(runId, projectId, 'saving_plan', '正在生成可确认计划…')
    } else if (event.stage === 'failed') {
      this.emit(runId, projectId, 'failed', '任务编排失败')
    }
  }

  private emit(
    runId: string,
    projectId: string,
    stage: AgentFoundationRuntimeEvent['stage'],
    label: string,
  ): void {
    this.sequence += 1
    this.emitEvent({
      schemaVersion: '1.0',
      runId,
      projectId,
      sequence: this.sequence,
      stage,
      label,
    })
  }
}

export function publicAgentFoundationError(error: unknown): {
  code: 'IPC_INVALID_ARGUMENT'
  message: string
  retryable: boolean
} | undefined {
  if (!(error instanceof AgentFoundationRuntimeError)) return undefined
  return {
    code: 'IPC_INVALID_ARGUMENT',
    message: error.message,
    retryable: false,
  }
}
