import { Agent, type AgentEvent, type AgentTool, type StreamFn } from '@earendil-works/pi-agent-core'
import { streamSimple } from '@earendil-works/pi-ai/api/openai-completions'
import type { JsonValue, Model, TSchema } from '@earendil-works/pi-ai'

export type PiAgentStage =
  | 'preparing_context'
  | 'planning'
  | 'validating_decision'
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

interface PreparedDecision {
  readonly prepared: boolean
  readonly contextEnvelope: JsonValue
  readonly decisionSchema: Record<string, unknown>
  readonly systemPrompt: string
}

interface RuntimeProvider {
  readonly baseUrl: string
  readonly modelId: string
  readonly apiKey: string
}

class PiRuntimeError extends Error {
  constructor(readonly code: string, message: string) {
    super(message)
  }
}

function record(value: JsonValue, label: string): Record<string, JsonValue> {
  if (value === null || Array.isArray(value) || typeof value !== 'object') {
    throw new PiRuntimeError('PI_RUNTIME_PROTOCOL_INVALID', `${label} is not an object.`)
  }
  return value
}

function preparedDecision(value: JsonValue): PreparedDecision | undefined {
  const payload = record(value, 'Prepared Agent response')
  if (payload.prepared !== true) return undefined
  if (
    typeof payload.system_prompt !== 'string'
    || payload.context_envelope === undefined
    || payload.decision_schema === null
    || Array.isArray(payload.decision_schema)
    || typeof payload.decision_schema !== 'object'
  ) {
    throw new PiRuntimeError('PI_RUNTIME_PROTOCOL_INVALID', 'Core returned an invalid Pi handoff.')
  }
  return {
    prepared: true,
    contextEnvelope: payload.context_envelope,
    decisionSchema: payload.decision_schema,
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

function lifecycleStage(event: AgentEvent): { stage: PiAgentStage; label: string } | undefined {
  if (event.type === 'agent_start' || event.type === 'turn_start') {
    return { stage: 'planning', label: '正在理解目标并规划绘图动作…' }
  }
  if (event.type === 'tool_execution_start') {
    return { stage: 'validating_decision', label: '正在校验字段绑定和绘图动作…' }
  }
  return undefined
}

/** Pi owns deliberation and tool execution; Core retains authority and persistence. */
export class PiAgentRuntime {
  private readonly core: PiCoreBridge
  private readonly emitEvent: PiAgentRuntimeOptions['emit']
  private readonly timeoutMs: number
  private readonly streamFn: StreamFn
  private active?: { runId: string; agent: Agent }
  private sequence = 0

  constructor(options: PiAgentRuntimeOptions) {
    this.core = options.core
    this.emitEvent = options.emit
    this.timeoutMs = options.timeoutMs ?? 35_000
    this.streamFn = options.streamFn ?? (streamSimple as StreamFn)
  }

  abort(): void {
    this.active?.agent.abort()
  }

  async decide(params: JsonValue): Promise<JsonValue> {
    const input = record(params, 'Pi Agent request')
    const projectId = typeof input.project_id === 'string' ? input.project_id : ''
    const runId = typeof input.client_model_run_id === 'string' ? input.client_model_run_id : ''
    if (!projectId || !runId) throw new PiRuntimeError('PI_RUNTIME_PROTOCOL_INVALID', 'Missing run identity.')

    this.abort()
    this.emit(runId, projectId, 'preparing_context', '正在读取数据结构和图形能力…')
    const preparedValue = await this.core.request(
      'agent.engine.decide',
      { ...input, prepare_only: true },
      10_000,
    )
    const prepared = preparedDecision(preparedValue)
    if (prepared === undefined) {
      this.emit(runId, projectId, 'completed', '已生成需要确认的结果。')
      return preparedValue
    }
    const provider = runtimeProvider(await this.core.request('provider.runtime.get', {}, 10_000))
    let decision: JsonValue | undefined
    const tool: AgentTool<TSchema, { accepted: boolean }> = {
      name: 'submit_plotagent_decision',
      label: '提交 PlotAgent 决策',
      description: 'Submit exactly one decision that conforms to the supplied PlotAgent decision schema.',
      parameters: prepared.decisionSchema as unknown as TSchema,
      constrainedSampling: { type: 'json_schema', strict: 'prefer' },
      executionMode: 'sequential',
      execute: async (_toolCallId, args) => {
        if (decision !== undefined) throw new PiRuntimeError('PI_MULTIPLE_DECISIONS', 'Only one decision is allowed.')
        decision = args as JsonValue
        return {
          content: [{ type: 'text', text: 'Decision received. Local validation is authoritative.' }],
          details: { accepted: true },
          terminate: true,
        }
      },
    }
    const agent = new Agent({
      initialState: {
        systemPrompt: `${prepared.systemPrompt}\n\nUse submit_plotagent_decision exactly once. Do not claim that any project mutation has occurred.`,
        model: modelFor(provider),
        thinkingLevel: 'off',
        tools: [tool],
        messages: [],
      },
      streamFn: this.streamFn,
      getApiKey: () => provider.apiKey,
      toolExecution: 'sequential',
      shouldStopAfterTurn: () => decision !== undefined,
      sessionId: runId,
    })
    agent.subscribe((event) => {
      const next = lifecycleStage(event)
      if (next !== undefined) this.emit(runId, projectId, next.stage, next.label)
    })
    this.active = { runId, agent }
    const timeout = setTimeout(() => agent.abort(), this.timeoutMs)
    try {
      await agent.prompt(JSON.stringify({ context_envelope: prepared.contextEnvelope }))
      if (decision === undefined) {
        if (agent.state.errorMessage) throw new PiRuntimeError('PI_MODEL_FAILED', agent.state.errorMessage)
        throw new PiRuntimeError('PI_DECISION_MISSING', 'The model did not submit a PlotAgent decision.')
      }
      this.emit(runId, projectId, 'saving_plan', '正在绑定对象并保存待确认计划…')
      const accepted = await this.core.request(
        'agent.engine.decide',
        { ...input, external_decision: decision },
        10_000,
      )
      this.emit(runId, projectId, 'completed', '计划已生成，等待确认。')
      return accepted
    } catch (error: unknown) {
      const aborted = agent.signal?.aborted === true
      this.emit(
        runId,
        projectId,
        aborted ? 'cancelled' : 'failed',
        aborted ? '本轮 Agent 任务已停止。' : 'Agent 未能生成有效计划。',
      )
      throw error
    } finally {
      clearTimeout(timeout)
      if (this.active?.runId === runId) this.active = undefined
    }
  }

  private emit(runId: string, projectId: string, stage: PiAgentStage, label: string): void {
    this.sequence += 1
    this.emitEvent({ schemaVersion: '1.0', runId, projectId, sequence: this.sequence, stage, label })
  }
}
