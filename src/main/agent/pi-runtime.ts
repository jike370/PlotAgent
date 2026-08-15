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
    message: 'Agent 未能生成有效计划，本轮没有修改项目。请重试。',
    retryable: true,
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

function acceptedCoreDecision(value: JsonValue): JsonValue {
  const payload = record(value, 'Core Agent response')
  if (payload.accepted === true) return value
  const error = payload.error
  const code = error !== null && !Array.isArray(error) && typeof error === 'object'
    && typeof error.code === 'string'
    ? error.code
    : 'PI_CORE_DECISION_REJECTED'
  throw new PiRuntimeError(code, 'Core rejected the model decision.')
}

const REPAIRABLE_DECISION_CODES = new Set([
  'COMBINED_ACTION_REQUIRED',
  'ENGINE_PLAN_INVALID',
  'FIELD_TYPE_INCOMPATIBLE',
  'SCHEMA_INVALID',
])

function rejectedCoreDecisionCode(value: JsonValue): string | undefined {
  const payload = record(value, 'Core Agent response')
  if (payload.accepted === true) return undefined
  const error = payload.error
  return error !== null && !Array.isArray(error) && typeof error === 'object'
    && typeof error.code === 'string'
    ? error.code
    : 'PI_CORE_DECISION_REJECTED'
}

function repairInstruction(code: string): string {
  if (code === 'FIELD_TYPE_INCOMPATIBLE') {
    return 'Local validation rejected the previous decision because a field logical type is incompatible with its proposed chart role. Re-read context_envelope field logical_type values, choose compatible roles or a compatible chart profile, and submit exactly one corrected decision.'
  }
  return `Local validation rejected the previous decision with ${code}. Re-read the supplied context and decision contract, then submit exactly one corrected decision.`
}

function decisionToolSchema(decisionSchema: Record<string, unknown>): TSchema {
  return {
    type: 'object',
    properties: { decision: decisionSchema },
    required: ['decision'],
    additionalProperties: false,
  } as unknown as TSchema
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
  private active?: { runId: string; generation: number; agent: Agent }
  private generation = 0
  private sequence = 0

  constructor(options: PiAgentRuntimeOptions) {
    this.core = options.core
    this.emitEvent = options.emit
    this.timeoutMs = options.timeoutMs ?? 35_000
    this.streamFn = options.streamFn ?? (streamSimple as StreamFn)
  }

  abort(): void {
    this.generation += 1
    this.active?.agent.abort()
  }

  async decide(params: JsonValue): Promise<JsonValue> {
    const input = record(params, 'Pi Agent request')
    const projectId = typeof input.project_id === 'string' ? input.project_id : ''
    const runId = typeof input.client_model_run_id === 'string' ? input.client_model_run_id : ''
    if (!projectId || !runId) throw new PiRuntimeError('PI_RUNTIME_PROTOCOL_INVALID', 'Missing run identity.')

    this.active?.agent.abort()
    const generation = ++this.generation
    let agent: Agent | undefined
    let timeout: ReturnType<typeof setTimeout> | undefined
    let timedOut = false
    try {
      this.emit(runId, projectId, 'preparing_context', '正在读取数据结构和图形能力…')
      const preparedValue = await this.core.request(
        'agent.engine.decide',
        { ...input, prepare_only: true },
        10_000,
      )
      this.assertCurrent(generation)
      const prepared = preparedDecision(preparedValue)
      if (prepared === undefined) {
        acceptedCoreDecision(preparedValue)
        this.emit(runId, projectId, 'completed', '已生成需要确认的结果。')
        return preparedValue
      }
      const provider = runtimeProvider(await this.core.request('provider.runtime.get', {}, 10_000))
      this.assertCurrent(generation)
      let decision: JsonValue | undefined
      let decisionCount = 0
      const tool: AgentTool<TSchema, { accepted: boolean }> = {
        name: 'submit_plotagent_decision',
        label: '提交 PlotAgent 决策',
        description: 'Submit exactly one candidate decision for this turn. PlotAgent Core validates it locally before it can become a plan.',
        parameters: decisionToolSchema(prepared.decisionSchema),
        constrainedSampling: { type: 'json_schema', strict: 'prefer' },
        executionMode: 'sequential',
        execute: async (_toolCallId, args) => {
          decisionCount += 1
          if (decisionCount > 1) {
            throw new PiRuntimeError('PI_MULTIPLE_DECISIONS', 'Only one decision is allowed.')
          }
          const payload = record(args as JsonValue, 'Pi decision tool arguments')
          if (payload.decision === undefined) {
            throw new PiRuntimeError('PI_RUNTIME_PROTOCOL_INVALID', 'The decision tool payload is missing.')
          }
          decision = payload.decision
          return {
            content: [{ type: 'text', text: 'Decision candidate received. PlotAgent Core validation follows.' }],
            details: { accepted: false },
            terminate: true,
          }
        },
      }
      agent = new Agent({
        initialState: {
          systemPrompt: `${prepared.systemPrompt}\n\nUse submit_plotagent_decision exactly once per turn. If local validation rejects the first candidate, correct it from the validation feedback and submit one replacement in the next turn. Never submit more than one candidate in a turn or more than two candidates in total. Do not claim that any project mutation has occurred.`,
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
        if (generation !== this.generation) return
        const next = lifecycleStage(event)
        if (next !== undefined) this.emit(runId, projectId, next.stage, next.label)
      })
      this.active = { runId, generation, agent }
      let accepted: JsonValue | undefined
      const decideAndValidate = async (): Promise<void> => {
        let prompt = JSON.stringify({ context_envelope: prepared.contextEnvelope })
        for (let attempt = 0; attempt < 2; attempt += 1) {
          decision = undefined
          decisionCount = 0
          await agent?.prompt(prompt)
          this.assertCurrent(generation)
          if (decisionCount > 1) {
            throw new PiRuntimeError('PI_MULTIPLE_DECISIONS', 'Only one decision is allowed per turn.')
          }
          if (decision === undefined || decisionCount !== 1) {
            if (agent?.state.errorMessage) {
              throw new PiRuntimeError('PI_MODEL_FAILED', agent.state.errorMessage)
            }
            throw new PiRuntimeError('PI_DECISION_MISSING', 'The model did not submit a PlotAgent decision.')
          }
          const response = await this.core.request(
            'agent.engine.decide',
            { ...input, external_decision: decision },
            10_000,
          )
          this.assertCurrent(generation)
          const rejectionCode = rejectedCoreDecisionCode(response)
          if (rejectionCode === undefined) {
            accepted = response
            return
          }
          if (!REPAIRABLE_DECISION_CODES.has(rejectionCode) || attempt === 1) {
            throw new PiRuntimeError(rejectionCode, 'Core rejected the model decision.')
          }
          prompt = repairInstruction(rejectionCode)
        }
      }
      await Promise.race([
        decideAndValidate(),
        new Promise<never>((_resolve, reject) => {
          timeout = setTimeout(() => {
            timedOut = true
            agent?.abort()
            reject(new PiRuntimeError('PI_MODEL_TIMEOUT', 'The model decision exceeded its fixed timeout.'))
          }, this.timeoutMs)
        }),
      ])
      this.assertCurrent(generation)
      if (accepted === undefined) {
        throw new PiRuntimeError('PI_DECISION_MISSING', 'The model did not submit an accepted PlotAgent decision.')
      }
      this.emit(runId, projectId, 'saving_plan', '正在绑定对象并保存待确认计划…')
      this.emit(runId, projectId, 'completed', '计划已生成，等待确认。')
      return accepted
    } catch (error: unknown) {
      const superseded = generation !== this.generation
      if (!superseded) {
        const aborted = !timedOut && agent?.signal?.aborted === true
        this.emit(
          runId,
          projectId,
          aborted ? 'cancelled' : 'failed',
          aborted ? '本轮 Agent 任务已停止。' : 'Agent 未能生成有效计划。',
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
