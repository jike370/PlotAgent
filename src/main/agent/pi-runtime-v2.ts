import { createHash } from 'node:crypto'

import {
  Agent,
  type AgentEvent,
  type AgentMessage,
  type AgentTool,
  type StreamFn,
} from '@earendil-works/pi-agent-core'
import { streamSimple } from '@earendil-works/pi-ai/api/openai-completions'
import type { JsonValue, Model, TSchema } from '@earendil-works/pi-ai'

import type {
  AgentActivation,
  AgentContextSnapshot,
  AgentToolResult as CoreToolResult,
  AgentYieldContract,
  ToolContract,
  ToolInvocation,
} from '../../shared/generated/contracts.js'

const TERMINAL_TOOL_NAME = 'submit_agent_yield'
const TERMINAL_YIELD_RECOVERY_PROMPT = [
  'Protocol recovery: your previous turn ended without calling submit_agent_yield.',
  'Do not explain in prose and do not repeat completed tool calls.',
  'Call submit_agent_yield exactly once with the typed terminal result for this activation.',
].join(' ')

export interface PiRuntimeProviderV2 {
  readonly baseUrl: string
  readonly modelId: string
  readonly apiKey: string
}

export interface PiRuntimeToolDefinitionV2 {
  readonly contract: ToolContract
  readonly inputSchema: TSchema
  readonly authority?: {
    readonly itemId: string
    readonly executionGrantId: string
  }
}

export interface PiActivationEnvironmentV2 {
  readonly context: AgentContextSnapshot
  readonly systemPrompt: string
  readonly provider: PiRuntimeProviderV2
  /** Complete JSON Schema for the terminal AgentYield object. */
  readonly yieldSchema: TSchema
  readonly tools: ReadonlyArray<PiRuntimeToolDefinitionV2>
}

export interface PiRuntimeHostV2 {
  prepare(
    activation: AgentActivation,
    signal: AbortSignal,
  ): Promise<PiActivationEnvironmentV2>
  invokeTool(
    invocation: ToolInvocation,
    argumentsValue: JsonValue,
    signal: AbortSignal,
  ): Promise<CoreToolResult>
  validateYield(
    activation: AgentActivation,
    candidate: JsonValue,
    signal: AbortSignal,
  ): Promise<AgentYieldContract>
  transformContext?(
    activation: AgentActivation,
    messages: AgentMessage[],
    signal: AbortSignal,
  ): Promise<AgentMessage[]>
}

export type PiRuntimeV2Stage =
  | 'preparing_context'
  | 'model_turn'
  | 'tool_started'
  | 'tool_finished'
  | 'yielded'
  | 'cancelled'
  | 'failed'

export interface PiRuntimeV2Event {
  readonly schemaVersion: '2.0'
  readonly activationId: string
  readonly taskId: string
  readonly taskVersion: number
  readonly sequence: number
  readonly stage: PiRuntimeV2Stage
  readonly toolName?: string
  readonly toolCallId?: string
}

export interface PiRuntimeAdapterV2Options {
  readonly host: PiRuntimeHostV2
  readonly emit: (event: PiRuntimeV2Event) => void
  readonly streamFn?: StreamFn
  readonly clock?: () => Date
}

export class PiRuntimeV2ProtocolError extends Error {
  constructor(readonly code: string, message: string) {
    super(message)
  }
}

interface ActiveRun {
  readonly activation: AgentActivation
  readonly generation: number
  readonly controller: AbortController
  agent?: Agent
}

interface RuntimeCounters {
  modelTurns: number
  modelCalls: number
  inputTokens: number
  outputTokens: number
  toolCalls: number
  disclosedScalars: number
  estimatedCost: number
}

function modelFor(provider: PiRuntimeProviderV2): Model<'openai-completions'> {
  let samplingParams: Record<string, unknown> | undefined
  try {
    const host = new URL(provider.baseUrl).hostname.toLocaleLowerCase('en-US')
    if (host === 'api.deepseek.com') {
      samplingParams = { thinking: { type: 'disabled' } }
    } else if (host === 'dashscope.aliyuncs.com' || host.endsWith('.maas.aliyuncs.com')) {
      // Alibaba's OpenAI-compatible API uses a different thinking toggle.
      samplingParams = { enable_thinking: false }
    }
  } catch {
    // The Core validates provider URLs before this trusted runtime sees them. Keep this
    // helper fail-neutral so a custom test adapter still receives the original endpoint.
  }
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
    maxTokens: 2_048,
    ...(samplingParams === undefined ? {} : { samplingParams }),
  }
}

function canonicalValue(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return value.map((item) => canonicalValue(item))
  if (value === null || typeof value !== 'object') return value
  return Object.fromEntries(
    Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, canonicalValue(item)]),
  )
}

function canonicalHash(value: JsonValue): string {
  return createHash('sha256').update(JSON.stringify(canonicalValue(value))).digest('hex')
}

function iso(value: Date): string {
  return value.toISOString().replace('.000Z', 'Z')
}

function asJson(value: unknown, label: string): JsonValue {
  if (value === undefined) {
    throw new PiRuntimeV2ProtocolError('PI_V2_PROTOCOL_INVALID', `${label} is not JSON.`)
  }
  try {
    return JSON.parse(JSON.stringify(value)) as JsonValue
  } catch {
    throw new PiRuntimeV2ProtocolError('PI_V2_PROTOCOL_INVALID', `${label} is not JSON.`)
  }
}

function sameIdentity(
  activation: AgentActivation,
  value: Pick<CoreToolResult, 'task_id' | 'task_version' | 'activation_id'>,
): boolean {
  return value.task_id === activation.task_id
    && value.task_version === activation.task_version
    && value.activation_id === activation.activation_id
}

function runtimeFailure(
  activation: AgentActivation,
  code: string,
  message: string,
): AgentYieldContract {
  return {
    outcome: 'runtime_failed',
    activation_id: activation.activation_id,
    task_id: activation.task_id,
    task_version: activation.task_version,
    error: {
      code,
      category: 'runtime',
      message,
      retryable: true,
      requires_user: false,
      side_effect_state: 'known_none',
    },
  }
}

function safeProviderDiagnostic(message: string): string {
  return message
    .replace(/Bearer\s+\S+/gi, 'Bearer [redacted]')
    .replace(/\bsk-[A-Za-z0-9_-]{8,}\b/g, '[redacted]')
    .replace(/\b(api[_-]?key|authorization)\s*[:=]\s*\S+/gi, '$1=[redacted]')
    .trim()
    .slice(0, 800)
}

function cancelledYield(activation: AgentActivation): AgentYieldContract {
  return {
    outcome: 'cancelled',
    activation_id: activation.activation_id,
    task_id: activation.task_id,
    task_version: activation.task_version,
    message: 'The Agent activation was cancelled before a terminal result was accepted.',
  }
}

function budgetYield(
  activation: AgentActivation,
  exhaustedBudget:
    | 'model_calls'
    | 'model_turns'
    | 'input_tokens'
    | 'output_tokens'
    | 'tool_calls'
    | 'disclosed_scalars'
    | 'wall_time'
    | 'estimated_cost',
): AgentYieldContract {
  return {
    outcome: 'budget_exhausted',
    activation_id: activation.activation_id,
    task_id: activation.task_id,
    task_version: activation.task_version,
    exhausted_budget: exhaustedBudget,
    message: `The Agent stopped at its ${exhaustedBudget} budget without committing project changes.`,
  }
}

function validateEnvironment(
  activation: AgentActivation,
  environment: PiActivationEnvironmentV2,
): void {
  if (
    environment.systemPrompt.trim().length === 0
    || environment.provider.baseUrl.trim().length === 0
    || environment.provider.modelId.trim().length === 0
    || environment.provider.apiKey.length === 0
  ) {
    throw new PiRuntimeV2ProtocolError(
      'PI_V2_ENVIRONMENT_INVALID',
      'Core returned an incomplete activation environment.',
    )
  }
  if (
    environment.context.activation_id !== activation.activation_id
    || environment.context.task_id !== activation.task_id
    || environment.context.task_version !== activation.task_version
    || environment.context.task_state !== activation.task_state
  ) {
    throw new PiRuntimeV2ProtocolError(
      'PI_V2_CONTEXT_MISMATCH',
      'Core context does not match the requested activation.',
    )
  }
  const names = environment.tools.map((item) => item.contract.tool_name)
  if (names.length !== new Set(names).size || names.includes(TERMINAL_TOOL_NAME)) {
    throw new PiRuntimeV2ProtocolError(
      'PI_V2_TOOL_DEFINITION_INVALID',
      'Core returned duplicate or reserved tool names.',
    )
  }
  if (
    names.length !== activation.allowed_tools.length
    || names.some((name) => !activation.allowed_tools.includes(name))
  ) {
    throw new PiRuntimeV2ProtocolError(
      'PI_V2_TOOL_ALLOWLIST_MISMATCH',
      'Core tool definitions differ from the activation allowlist.',
    )
  }
  const contextTools = new Map(environment.context.tools.map((item) => [item.tool_name, item]))
  if (contextTools.size !== environment.tools.length) {
    throw new PiRuntimeV2ProtocolError(
      'PI_V2_CONTEXT_TOOL_MISMATCH',
      'Context tool references differ from the executable tool definitions.',
    )
  }
  const phaseRank = { p0_read: 0, p1_staged: 1, p2_confirmed: 2, p3_expanded: 3 } as const
  const contextSideEffect = {
    none: 'none',
    staged: 'staged',
    committed: 'confirmed_write',
    expanded_risk: 'expanded_risk',
  } as const
  for (const definition of environment.tools) {
    const contextTool = contextTools.get(definition.contract.tool_name)
    if (
      contextTool === undefined
      || contextTool.permission_phase !== definition.contract.permission_phase
      || contextTool.input_schema_hash !== definition.contract.input_schema_hash
      || contextTool.output_schema_hash !== definition.contract.output_schema_hash
      || contextTool.side_effect !== contextSideEffect[definition.contract.side_effect]
      || !definition.contract.allowed_task_states.includes(activation.task_state)
      || phaseRank[definition.contract.permission_phase] > phaseRank[activation.permission_phase]
    ) {
      throw new PiRuntimeV2ProtocolError(
        'PI_V2_CONTEXT_TOOL_MISMATCH',
        'Context tool references differ from the executable tool definitions.',
      )
    }
    const committed = definition.contract.permission_phase === 'p2_confirmed'
      || definition.contract.permission_phase === 'p3_expanded'
    if (committed !== (definition.authority !== undefined)) {
      throw new PiRuntimeV2ProtocolError(
        'PI_V2_TOOL_AUTHORITY_INVALID',
        'Committed tools require Core-bound item and grant authority.',
      )
    }
  }
}

/**
 * Test-gated v2 adapter. Pi owns the model/tool loop; Core owns context,
 * permissions, tool execution and terminal yield validation.
 */
export class PiRuntimeAdapterV2 {
  private readonly host: PiRuntimeHostV2
  private readonly emitEvent: PiRuntimeAdapterV2Options['emit']
  private readonly streamFn: StreamFn
  private readonly clock: () => Date
  private active?: ActiveRun
  private generation = 0
  private sequence = 0

  constructor(options: PiRuntimeAdapterV2Options) {
    this.host = options.host
    this.emitEvent = options.emit
    const providerStream = options.streamFn ?? (streamSimple as StreamFn)
    this.streamFn = (model, context, streamOptions) => providerStream(model, context, {
      ...streamOptions,
      // The provider adapter retries only request-creation failures that are safe by
      // HTTP semantics (disconnect/408/409/429/5xx). No model output or Core tool can
      // exist yet at this boundary, so one bounded retry cannot duplicate a side
      // effect. Authentication, balance and invalid-request responses remain terminal.
      maxRetries: 1,
      maxRetryDelayMs: 5_000,
    })
    this.clock = options.clock ?? (() => new Date())
  }

  abort(activationId?: string): boolean {
    if (this.active === undefined) return false
    if (activationId !== undefined && this.active.activation.activation_id !== activationId) {
      return false
    }
    this.generation += 1
    this.active.controller.abort()
    this.active.agent?.abort()
    return true
  }

  steer(input: {
    activationId: string
    taskId: string
    taskVersion: number
    message: string
  }): boolean {
    const current = this.active
    if (
      current === undefined
      || current.activation.activation_id !== input.activationId
      || current.activation.task_id !== input.taskId
      || current.activation.task_version !== input.taskVersion
      || input.message.trim().length === 0
    ) return false
    if (current.agent === undefined) return false
    current.agent.steer({ role: 'user', content: input.message, timestamp: this.clock().getTime() })
    return true
  }

  async run(activation: AgentActivation): Promise<AgentYieldContract> {
    this.active?.controller.abort()
    this.active?.agent?.abort()
    const generation = ++this.generation
    const controller = new AbortController()
    this.active = { activation, generation, controller }
    const counters: RuntimeCounters = {
      modelTurns: 0,
      modelCalls: 0,
      inputTokens: 0,
      outputTokens: 0,
      toolCalls: 0,
      disclosedScalars: 0,
      estimatedCost: 0,
    }
    let finalYield: AgentYieldContract | undefined
    let fatalProtocolError: PiRuntimeV2ProtocolError | undefined
    let agent: Agent | undefined
    let timeout: ReturnType<typeof setTimeout> | undefined
    let timeoutPromise: Promise<never> | undefined
    let timedOut = false

    try {
      this.emit(activation, 'preparing_context')
      const activationDeadline = activation.deadline === null || activation.deadline === undefined
        ? undefined
        : new Date(activation.deadline).getTime()
      if (activationDeadline !== undefined && activationDeadline <= this.clock().getTime()) {
        return budgetYield(activation, 'wall_time')
      }
      const configuredTimeout = activation.activation_budget.timeout_ms
      if (configuredTimeout !== null && configuredTimeout !== undefined) {
        const timeoutMs = Math.max(0, Math.min(
          configuredTimeout,
          activationDeadline === undefined
            ? 2_147_483_647
            : activationDeadline - this.clock().getTime(),
          2_147_483_647,
        ))
        timeoutPromise = new Promise<never>((_resolve, reject) => {
          timeout = setTimeout(() => {
            timedOut = true
            controller.abort()
            agent?.abort()
            reject(new PiRuntimeV2ProtocolError('PI_V2_TIMEOUT', 'Activation timed out.'))
          }, timeoutMs)
        })
      }
      const withActivationTimeout = <T>(pending: Promise<T>): Promise<T> => (
        timeoutPromise === undefined ? pending : Promise.race([pending, timeoutPromise])
      )
      const environment = await withActivationTimeout(
        this.host.prepare(activation, controller.signal),
      )
      this.assertCurrent(generation)
      validateEnvironment(activation, environment)
      const initiallyExhausted = this.exhaustedBudget(activation, counters)
      if (initiallyExhausted !== undefined) {
        return budgetYield(activation, initiallyExhausted)
      }

      const toolByName = new Map(environment.tools.map((item) => [item.contract.tool_name, item]))
      const ordinaryTools = environment.tools.map((definition): AgentTool<TSchema, CoreToolResult> => ({
        name: definition.contract.tool_name,
        label: definition.contract.description,
        description: definition.contract.description,
        parameters: definition.inputSchema,
        executionMode: 'sequential',
        execute: async (providerToolCallId, args, signal) => {
          this.assertCurrent(generation)
          const now = this.clock()
          const callDigest = canonicalHash({
            activation_id: activation.activation_id,
            provider_tool_call_id: providerToolCallId,
            ordinal: counters.toolCalls,
          })
          const toolCallId = `toolcall:${callDigest.slice(0, 32)}`
          const argumentsValue = asJson(args, 'Tool arguments')
          const toolDeadline = now.getTime() + definition.contract.timeout_ms
          const absoluteDeadline = activationDeadline === undefined
            ? toolDeadline
            : Math.min(activationDeadline, toolDeadline)
          const invocation: ToolInvocation = {
            tool_call_id: toolCallId,
            task_id: activation.task_id,
            task_version: activation.task_version,
            activation_id: activation.activation_id,
            ...(definition.authority === undefined ? {} : {
              item_id: definition.authority.itemId,
              execution_grant_id: definition.authority.executionGrantId,
            }),
            ...(definition.contract.permission_phase === 'p0_read'
              ? {}
              : { idempotency_key: `idem:${callDigest.slice(0, 32)}` }),
            tool_name: definition.contract.tool_name,
            permission_phase: definition.contract.permission_phase,
            arguments_hash: canonicalHash(argumentsValue),
            activation_tool_calls_before: counters.toolCalls,
            activation_disclosed_scalars_before: counters.disclosedScalars,
            expected_project_revision: environment.context.project_revision,
            deadline: iso(new Date(absoluteDeadline)),
          }
          counters.toolCalls += 1
          this.emit(activation, 'tool_started', toolCallId, definition.contract.tool_name)
          const result = await this.host.invokeTool(
            invocation,
            argumentsValue,
            signal ?? controller.signal,
          )
          this.assertCurrent(generation)
          if (
            !sameIdentity(activation, result)
            || result.tool_call_id !== toolCallId
            || result.tool_name !== definition.contract.tool_name
          ) {
            fatalProtocolError = new PiRuntimeV2ProtocolError(
              'PI_V2_TOOL_RESULT_MISMATCH',
              'Core tool result identity differs from the invocation.',
            )
            agent?.abort()
            throw fatalProtocolError
          }
          counters.disclosedScalars += result.disclosed_scalar_count ?? 0
          this.emit(activation, 'tool_finished', toolCallId, definition.contract.tool_name)
          return {
            content: [{ type: 'text', text: JSON.stringify(result) }],
            details: result,
            terminate: false,
          }
        },
      }))
      const terminalTool: AgentTool<TSchema, AgentYieldContract> = {
        name: TERMINAL_TOOL_NAME,
        label: 'Submit the terminal Agent result',
        description: 'Return exactly one typed AgentYield after all required inspection is complete.',
        // OpenAI-compatible function tools require an object at the schema root.
        // AgentYield itself is a discriminated union, so expose it as one
        // explicitly named argument and let Core validate the nested value.
        parameters: {
          type: 'object',
          properties: { agent_yield: environment.yieldSchema },
          required: ['agent_yield'],
          additionalProperties: false,
        } as TSchema,
        constrainedSampling: { type: 'json_schema', strict: 'prefer' },
        executionMode: 'sequential',
        execute: async (_toolCallId, args, signal) => {
          const payload = asJson(args, 'Terminal tool arguments')
          if (payload === null || Array.isArray(payload) || typeof payload !== 'object') {
            throw new PiRuntimeV2ProtocolError(
              'PI_V2_PROTOCOL_INVALID',
              'Terminal tool arguments were invalid.',
            )
          }
          const validated = await this.host.validateYield(
            activation,
            asJson(payload.agent_yield, 'Agent yield'),
            signal ?? controller.signal,
          )
          this.assertCurrent(generation)
          if (!sameIdentity(activation, validated)) {
            fatalProtocolError = new PiRuntimeV2ProtocolError(
              'PI_V2_YIELD_IDENTITY_MISMATCH',
              'Validated Agent yield differs from the activation identity.',
            )
            agent?.abort()
            throw fatalProtocolError
          }
          finalYield = validated
          return {
            content: [{ type: 'text', text: 'The typed Agent yield was accepted.' }],
            details: validated,
            terminate: true,
          }
        },
      }

      agent = new Agent({
        initialState: {
          systemPrompt: environment.systemPrompt,
          model: modelFor(environment.provider),
          thinkingLevel: 'off',
          tools: [...ordinaryTools, terminalTool],
          messages: [],
        },
        streamFn: this.streamFn,
        getApiKey: () => environment.provider.apiKey,
        toolExecution: 'sequential',
        sessionId: activation.task_id,
        transformContext: async (messages, signal) => {
          if (this.host.transformContext === undefined) return messages
          try {
            return await this.host.transformContext(
              activation,
              messages,
              signal ?? controller.signal,
            )
          } catch {
            return messages
          }
        },
        beforeToolCall: async ({ toolCall }, signal) => {
          this.assertCurrent(generation)
          if (finalYield !== undefined) {
            return { block: true, terminate: true, reason: 'A terminal yield already exists.' }
          }
          if (toolCall.name !== TERMINAL_TOOL_NAME && !toolByName.has(toolCall.name)) {
            return { block: true, terminate: true, reason: 'The tool is outside the activation.' }
          }
          if (toolCall.name !== TERMINAL_TOOL_NAME) {
            const exhausted = this.exhaustedToolBudget(activation, counters)
            if (exhausted !== undefined) {
              finalYield = budgetYield(activation, exhausted)
              return { block: true, terminate: true, reason: `The ${exhausted} budget is exhausted.` }
            }
          }
          if ((signal ?? controller.signal).aborted) {
            return { block: true, terminate: true, reason: 'The activation was cancelled.' }
          }
          return undefined
        },
        afterToolCall: async ({ result }) => {
          if (fatalProtocolError !== undefined) {
            return { isError: true, terminate: true, details: { fatal: true } }
          }
          const details = result.details as CoreToolResult | AgentYieldContract
          const exhausted = this.exhaustedToolBudget(activation, counters)
          if (exhausted !== undefined) {
            finalYield = budgetYield(activation, exhausted)
            return { terminate: true, details }
          }
          if ('status' in details && details.status === 'failed') {
            return { isError: true, details }
          }
          return undefined
        },
        shouldStopAfterTurn: ({ message }) => {
          counters.modelCalls += 1
          counters.modelTurns += 1
          counters.inputTokens += message.usage.input
          counters.outputTokens += message.usage.output
          counters.estimatedCost += message.usage.cost.total
          if (finalYield !== undefined) return true
          const exhausted = this.exhaustedBudget(activation, counters)
          if (exhausted !== undefined) {
            finalYield = budgetYield(activation, exhausted)
            return true
          }
          return false
        },
      })
      agent.subscribe((event) => this.handleAgentEvent(activation, event, generation))
      this.active.agent = agent

      const prompt = JSON.stringify({ context_snapshot: environment.context })
      await withActivationTimeout(agent.prompt(prompt))
      if (fatalProtocolError !== undefined) throw fatalProtocolError
      this.assertCurrent(generation)
      if (finalYield === undefined && agent.state.errorMessage !== undefined) {
        throw new PiRuntimeV2ProtocolError(
          'PI_V2_PROVIDER_FAILED',
          safeProviderDiagnostic(agent.state.errorMessage)
            || 'The model provider ended the activation before a typed Agent yield was accepted.',
        )
      }
      if (finalYield === undefined) {
        await withActivationTimeout(agent.prompt(TERMINAL_YIELD_RECOVERY_PROMPT))
        if (fatalProtocolError !== undefined) throw fatalProtocolError
        this.assertCurrent(generation)
        if (finalYield === undefined && agent.state.errorMessage !== undefined) {
          throw new PiRuntimeV2ProtocolError(
            'PI_V2_PROVIDER_FAILED',
            safeProviderDiagnostic(agent.state.errorMessage)
              || 'The model provider ended protocol recovery before a typed Agent yield was accepted.',
          )
        }
      }
      if (finalYield === undefined) {
        finalYield = runtimeFailure(
          activation,
          'AGENT_YIELD_MISSING',
          'Pi ended without submitting a typed AgentYield.',
        )
      }
      this.emit(activation, 'yielded')
      return finalYield
    } catch (error) {
      if (fatalProtocolError !== undefined) {
        this.emit(activation, 'failed')
        return runtimeFailure(activation, fatalProtocolError.code, fatalProtocolError.message)
      }
      const superseded = generation !== this.generation
      if (superseded || (!timedOut && agent?.signal?.aborted === true)) {
        this.emit(activation, 'cancelled')
        return cancelledYield(activation)
      }
      if (timedOut) {
        this.emit(activation, 'failed')
        return budgetYield(activation, 'wall_time')
      }
      this.emit(activation, 'failed')
      return runtimeFailure(
        activation,
        error instanceof PiRuntimeV2ProtocolError ? error.code : 'PI_V2_RUNTIME_FAILED',
        error instanceof PiRuntimeV2ProtocolError
          ? error.message
          : error instanceof Error
            ? error.message
            : 'The Pi runtime failed before a typed terminal result was accepted.',
      )
    } finally {
      controller.abort()
      if (timeout !== undefined) clearTimeout(timeout)
      if (this.active?.generation === generation) this.active = undefined
    }
  }

  private exhaustedBudget(
    activation: AgentActivation,
    counters: RuntimeCounters,
  ):
    | 'model_calls'
    | 'model_turns'
    | 'input_tokens'
    | 'output_tokens'
    | 'tool_calls'
    | 'disclosed_scalars'
    | 'estimated_cost'
    | undefined {
    const limits = activation.task_budget.limits
    const usage = activation.task_budget.usage ?? {}
    const remainingModelCalls = (limits.max_model_calls ?? Number.POSITIVE_INFINITY)
      - (usage.model_calls ?? 0)
    const remainingModelTurns = (limits.max_model_turns ?? Number.POSITIVE_INFINITY)
      - (usage.model_turns ?? 0)
    const remainingInput = (limits.max_input_tokens ?? Number.POSITIVE_INFINITY)
      - (usage.input_tokens ?? 0)
    const remainingOutput = (limits.max_output_tokens ?? Number.POSITIVE_INFINITY)
      - (usage.output_tokens ?? 0)
    const remainingEstimatedCost = (limits.max_estimated_cost ?? Number.POSITIVE_INFINITY)
      - (usage.estimated_cost ?? 0)
    if (counters.modelCalls >= remainingModelCalls) return 'model_calls'
    if (
      counters.modelTurns >= (activation.activation_budget.max_model_turns ?? Number.POSITIVE_INFINITY)
      || counters.modelTurns >= remainingModelTurns
    ) return 'model_turns'
    if (counters.inputTokens >= remainingInput) return 'input_tokens'
    if (counters.outputTokens >= remainingOutput) return 'output_tokens'
    if (counters.estimatedCost >= remainingEstimatedCost) return 'estimated_cost'
    return this.exhaustedToolBudget(activation, counters)
  }

  private exhaustedToolBudget(
    activation: AgentActivation,
    counters: RuntimeCounters,
  ): 'tool_calls' | 'disclosed_scalars' | undefined {
    const limits = activation.task_budget.limits
    const usage = activation.task_budget.usage ?? {}
    const remainingToolCalls = Math.min(
      activation.activation_budget.max_tool_calls ?? Number.POSITIVE_INFINITY,
      (limits.max_tool_calls ?? Number.POSITIVE_INFINITY) - (usage.tool_calls ?? 0),
    )
    const remainingDisclosedScalars = Math.min(
      activation.activation_budget.max_disclosed_scalars ?? Number.POSITIVE_INFINITY,
      (limits.max_disclosed_scalars ?? Number.POSITIVE_INFINITY)
        - (usage.disclosed_scalars ?? 0),
    )
    if (counters.toolCalls >= remainingToolCalls) return 'tool_calls'
    if (counters.disclosedScalars >= remainingDisclosedScalars) return 'disclosed_scalars'
    return undefined
  }

  private handleAgentEvent(
    activation: AgentActivation,
    event: AgentEvent,
    generation: number,
  ): void {
    if (generation !== this.generation) return
    if (event.type === 'turn_start') this.emit(activation, 'model_turn')
  }

  private assertCurrent(generation: number): void {
    if (generation !== this.generation) {
      throw new PiRuntimeV2ProtocolError(
        'PI_V2_RUN_SUPERSEDED',
        'A newer activation superseded this run.',
      )
    }
  }

  private emit(
    activation: AgentActivation,
    stage: PiRuntimeV2Stage,
    toolCallId?: string,
    toolName?: string,
  ): void {
    this.sequence += 1
    this.emitEvent({
      schemaVersion: '2.0',
      activationId: activation.activation_id,
      taskId: activation.task_id,
      taskVersion: activation.task_version,
      sequence: this.sequence,
      stage,
      ...(toolCallId === undefined ? {} : { toolCallId }),
      ...(toolName === undefined ? {} : { toolName }),
    })
  }
}
