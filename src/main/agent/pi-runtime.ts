import { Agent, type AgentEvent, type AgentTool, type StreamFn } from '@earendil-works/pi-agent-core'
import { streamSimple } from '@earendil-works/pi-ai/api/openai-completions'
import type { JsonValue, Model, TSchema } from '@earendil-works/pi-ai'

export type PiAgentStage =
  | 'preparing_context'
  | 'inspecting_data'
  | 'planning'
  | 'validating_draft'
  | 'saving_plan'
  | 'completed'
  | 'cancelled'
  | 'failed'

export interface PiAgentRuntimeEvent {
  readonly schemaVersion: '1.0'
  readonly runId: string
  readonly projectId: string
  readonly sequence: number
  readonly stage: PiAgentStage
  readonly label: string
}

export interface PiCoreBridge {
  request(method: string, params?: JsonValue, timeoutMs?: number): Promise<JsonValue>
}

export interface PiAgentRuntimeOptions {
  readonly core: PiCoreBridge
  readonly emit: (event: PiAgentRuntimeEvent) => void
  readonly timeoutMs?: number
  readonly streamFn?: StreamFn
}

interface PreparedWorkflow {
  readonly workflowRunId: string
  readonly context: JsonValue
  readonly draftSchema: Record<string, unknown>
  readonly systemPrompt: string
}

interface RuntimeProvider {
  readonly baseUrl: string
  readonly modelId: string
  readonly apiKey: string
}

export class PiRuntimeError extends Error {
  constructor(readonly code: string, message: string) {
    super(message)
  }
}

export function publicPiAgentError(error: unknown): {
  code: 'CORE_REQUEST_TIMEOUT' | 'CORE_REQUEST_FAILED'
  message: string
  retryable: boolean
} | undefined {
  if (!(error instanceof PiRuntimeError)) return undefined
  if (error.code === 'PI_MODEL_TIMEOUT') {
    return {
      code: 'CORE_REQUEST_TIMEOUT',
      message: '模型响应超时，本轮没有修改项目。请重试。',
      retryable: true,
    }
  }
  if (error.code === 'PI_RUN_SUPERSEDED') {
    return {
      code: 'CORE_REQUEST_FAILED',
      message: '本轮请求已被更新的 Agent 请求替代。',
      retryable: false,
    }
  }
  return {
    code: 'CORE_REQUEST_FAILED',
    message: 'Agent 未能生成有效任务草稿，本轮没有修改项目。请重试。',
    retryable: true,
  }
}

function record(value: JsonValue, label: string): Record<string, JsonValue> {
  if (value === null || Array.isArray(value) || typeof value !== 'object') {
    throw new PiRuntimeError('PI_RUNTIME_PROTOCOL_INVALID', `${label} is not an object.`)
  }
  return value
}

function preparedWorkflow(value: JsonValue): PreparedWorkflow | undefined {
  const payload = record(value, 'Prepared workflow response')
  if (payload.outcome !== 'agent_required') return undefined
  if (
    typeof payload.workflow_run_id !== 'string'
    || typeof payload.system_prompt !== 'string'
    || payload.workflow_context === undefined
    || payload.task_draft_schema === null
    || Array.isArray(payload.task_draft_schema)
    || typeof payload.task_draft_schema !== 'object'
  ) {
    throw new PiRuntimeError('PI_RUNTIME_PROTOCOL_INVALID', 'Core returned an invalid workflow handoff.')
  }
  return {
    workflowRunId: payload.workflow_run_id,
    context: payload.workflow_context,
    draftSchema: payload.task_draft_schema,
    systemPrompt: payload.system_prompt,
  }
}

function runtimeProvider(value: JsonValue): RuntimeProvider {
  const payload = record(value, 'Provider runtime response')
  if (
    typeof payload.base_url !== 'string'
    || typeof payload.model_id !== 'string'
    || typeof payload.api_key !== 'string'
  ) {
    throw new PiRuntimeError('PROVIDER_NOT_CONFIGURED', 'The model provider is not configured.')
  }
  return { baseUrl: payload.base_url, modelId: payload.model_id, apiKey: payload.api_key }
}

function modelFor(provider: RuntimeProvider): Model<'openai-completions'> {
  return {
    id: provider.modelId,
    name: provider.modelId,
    api: 'openai-completions',
    provider: 'plotagent-custom',
    baseUrl: provider.baseUrl,
    reasoning: false,
    input: ['text'],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 128_000,
    maxTokens: 8_192,
  }
}

function objectSchema(properties: Record<string, unknown>, required: string[]): TSchema {
  return { type: 'object', properties, required, additionalProperties: false } as TSchema
}

function lifecycleStage(event: AgentEvent): { stage: PiAgentStage; label: string } | undefined {
  if (event.type === 'agent_start' || event.type === 'turn_start') {
    return { stage: 'planning', label: '正在理解目标并编排任务…' }
  }
  return undefined
}

/** Pi deliberates and inspects; Core alone validates, persists and executes. */
export class PiAgentRuntime {
  private readonly core: PiCoreBridge
  private readonly emitEvent: PiAgentRuntimeOptions['emit']
  private readonly timeoutMs: number
  private readonly streamFn: StreamFn
  private active?: { runId: string; generation: number; agent: Agent }
  private generation = 0
  private sequence = 0

  constructor(options: PiAgentRuntimeOptions) {
    this.core = options.core
    this.emitEvent = options.emit
    this.timeoutMs = options.timeoutMs ?? 60_000
    this.streamFn = options.streamFn ?? (streamSimple as StreamFn)
  }

  abort(): void {
    this.generation += 1
    this.active?.agent.abort()
  }

  async run(params: JsonValue): Promise<JsonValue> {
    const input = record(params, 'Pi workflow request')
    const projectId = typeof input.project_id === 'string' ? input.project_id : ''
    const clientRunId = typeof input.client_run_id === 'string' ? input.client_run_id : ''
    if (!projectId || !clientRunId) {
      throw new PiRuntimeError('PI_RUNTIME_PROTOCOL_INVALID', 'Missing run identity.')
    }

    this.active?.agent.abort()
    const generation = ++this.generation
    let agent: Agent | undefined
    let timeout: ReturnType<typeof setTimeout> | undefined
    let timedOut = false
    try {
      this.emit(clientRunId, projectId, 'preparing_context', '正在读取数据结构和图形能力…')
      const prepareInput = { ...input }
      delete prepareInput.client_run_id
      const preparedValue = await this.core.request('workflow.prepare', prepareInput, 10_000)
      this.assertCurrent(generation)
      const prepared = preparedWorkflow(preparedValue)
      if (prepared === undefined) {
        this.emit(clientRunId, projectId, 'completed', '已生成需要确认的任务。')
        return preparedValue
      }

      const provider = runtimeProvider(await this.core.request('provider.runtime.get', {}, 10_000))
      this.assertCurrent(generation)
      let submittedPlan: JsonValue | undefined
      const inspectTool = (
        name: string,
        label: string,
        parameters: TSchema,
      ): AgentTool<TSchema, JsonValue> => ({
        name,
        label,
        description: `${label}。只读、受预算限制，不会修改项目。`,
        parameters,
        executionMode: 'sequential',
        execute: async (_toolCallId, args) => {
          this.emit(clientRunId, projectId, 'inspecting_data', `${label}…`)
          const response = await this.core.request('workflow.inspect', {
            project_id: projectId,
            workflow_run_id: prepared.workflowRunId,
            tool_name: name,
            arguments: args as JsonValue,
          }, 10_000)
          return {
            content: [{ type: 'text', text: JSON.stringify(response) }],
            details: response,
            terminate: false,
          }
        },
      })
      const tools: AgentTool<TSchema, JsonValue>[] = [
        inspectTool('inspect_source', '正在检查数据表结构', objectSchema({
          source_alias: { type: 'string' },
        }, ['source_alias'])),
        inspectTool('preview_rows', '正在预览必要数据行', objectSchema({
          source_alias: { type: 'string' },
          field_aliases: {
            type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 24,
          },
          offset: { type: 'integer', minimum: 0 },
          limit: { type: 'integer', minimum: 1, maximum: 40 },
        }, ['source_alias', 'field_aliases'])),
        inspectTool('profile_field', '正在分析字段', objectSchema({
          source_alias: { type: 'string' },
          field_alias: { type: 'string' },
        }, ['source_alias', 'field_alias'])),
        inspectTool('compare_schemas', '正在比较数据表结构', objectSchema({
          source_aliases: {
            type: 'array', items: { type: 'string' }, minItems: 2, maxItems: 8,
          },
        }, ['source_aliases'])),
        {
          name: 'submit_task_draft',
          label: '提交任务草稿',
          description: '提交完整 TaskDraft，由 Core 绑定真实对象、验证并保存为待确认计划。',
          parameters: objectSchema({ task_draft: prepared.draftSchema }, ['task_draft']),
          constrainedSampling: { type: 'json_schema', strict: 'prefer' },
          executionMode: 'sequential',
          execute: async (_toolCallId, args) => {
            this.emit(clientRunId, projectId, 'validating_draft', '正在校验字段绑定和任务动作…')
            const payload = record(args as JsonValue, 'Task draft arguments')
            try {
              submittedPlan = await this.core.request('workflow.submit_draft', {
                project_id: projectId,
                workflow_run_id: prepared.workflowRunId,
                task_draft: payload.task_draft,
              }, 10_000)
              return {
                content: [{ type: 'text', text: 'TaskDraft accepted for user confirmation.' }],
                details: submittedPlan,
                terminate: true,
              }
            } catch (error) {
              return {
                content: [{ type: 'text', text: `Local validation rejected this draft: ${String(error)}` }],
                details: { validationError: String(error) },
                terminate: false,
              }
            }
          },
        },
      ]
      agent = new Agent({
        initialState: {
          systemPrompt: prepared.systemPrompt,
          model: modelFor(provider),
          thinkingLevel: 'off',
          tools,
          messages: [],
        },
        streamFn: this.streamFn,
        getApiKey: () => provider.apiKey,
        toolExecution: 'sequential',
        shouldStopAfterTurn: () => submittedPlan !== undefined,
        sessionId: prepared.workflowRunId,
      })
      agent.subscribe((event) => {
        if (generation !== this.generation) return
        const next = lifecycleStage(event)
        if (next !== undefined) this.emit(clientRunId, projectId, next.stage, next.label)
      })
      this.active = { runId: clientRunId, generation, agent }
      await Promise.race([
        agent.prompt(JSON.stringify({ workflow_context: prepared.context })),
        new Promise<never>((_resolve, reject) => {
          timeout = setTimeout(() => {
            timedOut = true
            agent?.abort()
            reject(new PiRuntimeError('PI_MODEL_TIMEOUT', 'The workflow draft exceeded its timeout.'))
          }, this.timeoutMs)
        }),
      ])
      this.assertCurrent(generation)
      if (submittedPlan === undefined) {
        throw new PiRuntimeError('PI_DRAFT_MISSING', 'The model did not submit a valid TaskDraft.')
      }
      this.emit(clientRunId, projectId, 'saving_plan', '正在保存待确认任务计划…')
      this.emit(clientRunId, projectId, 'completed', '任务计划已生成，等待确认。')
      return submittedPlan
    } catch (error: unknown) {
      const superseded = generation !== this.generation
      if (!superseded) {
        const aborted = !timedOut && agent?.signal?.aborted === true
        this.emit(
          clientRunId,
          projectId,
          aborted ? 'cancelled' : 'failed',
          aborted ? '本轮 Agent 任务已停止。' : 'Agent 未能生成有效任务草稿。',
        )
      }
      if (superseded) {
        throw new PiRuntimeError('PI_RUN_SUPERSEDED', 'A newer Agent run replaced this request.')
      }
      throw error
    } finally {
      if (timeout !== undefined) clearTimeout(timeout)
      if (this.active?.generation === generation) this.active = undefined
    }
  }

  private assertCurrent(generation: number): void {
    if (generation !== this.generation) {
      throw new PiRuntimeError('PI_RUN_SUPERSEDED', 'A newer Agent run replaced this request.')
    }
  }

  private emit(runId: string, projectId: string, stage: PiAgentStage, label: string): void {
    this.sequence += 1
    this.emitEvent({ schemaVersion: '1.0', runId, projectId, sequence: this.sequence, stage, label })
  }
}
