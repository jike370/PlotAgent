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
  readonly clarificationHistory?: JsonValue
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
    ...(payload.clarification_history === undefined
      ? {}
      : { clarificationHistory: payload.clarification_history }),
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

function agentTurnBudget(context: JsonValue): number {
  const payload = record(context, 'Workflow context')
  const budget = payload.budget === undefined ? undefined : record(payload.budget, 'Workflow budget')
  const value = budget?.max_agent_turns
  return typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 6
    ? value
    : 2
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
      let finalOutcome: JsonValue | undefined
      let lastValidationError: string | undefined
      let completedAgentTurns = 0
      const maxAgentTurns = agentTurnBudget(prepared.context)
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
      const inspectionTools: AgentTool<TSchema, JsonValue>[] = [
        inspectTool('list_sources', '正在列出可用数据表', objectSchema({}, [])),
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
        inspectTool('sample_rows', '正在抽取代表性数据行', objectSchema({
          source_alias: { type: 'string' },
          field_aliases: {
            type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 24,
          },
          limit: { type: 'integer', minimum: 1, maximum: 40 },
        }, ['source_alias', 'field_aliases'])),
        inspectTool('search_values', '正在查找字段值', objectSchema({
          source_alias: { type: 'string' },
          field_alias: { type: 'string' },
          mode: { type: 'string', enum: ['equal', 'contains', 'prefix'] },
          query: { type: ['string', 'number', 'boolean', 'null'] },
          limit: { type: 'integer', minimum: 1, maximum: 40 },
        }, ['source_alias', 'field_alias', 'mode', 'query'])),
        inspectTool('compare_schemas', '正在比较数据表结构', objectSchema({
          source_aliases: {
            type: 'array', items: { type: 'string' }, minItems: 2, maxItems: 8,
          },
        }, ['source_aliases'])),
        inspectTool('inspect_instrument_metadata', '正在检查仪器元数据', objectSchema({
          source_alias: { type: 'string' },
        }, ['source_alias'])),
      ]
      const previewTool = (
        operation: string,
        label: string,
        properties: Record<string, unknown>,
        required: string[],
      ): AgentTool<TSchema, JsonValue> => ({
        name: `preview_${operation}`,
        label,
        description: `${label}。只生成有界预览，不修改项目；确认后由 Core 再执行同一操作。`,
        parameters: objectSchema({
          ...properties,
          limit: { type: 'integer', minimum: 1, maximum: 40 },
        }, required),
        executionMode: 'sequential',
        execute: async (_toolCallId, args) => {
          this.emit(clientRunId, projectId, 'inspecting_data', `${label}…`)
          const payload = record(args as JsonValue, 'Data operation preview arguments')
          const { limit, ...operationArguments } = payload
          const response = await this.core.request('workflow.preview_operation', {
            project_id: projectId,
            workflow_run_id: prepared.workflowRunId,
            operation: { operation, ...operationArguments },
            limit: typeof limit === 'number' ? limit : 5,
          }, 10_000)
          return {
            content: [{ type: 'text', text: JSON.stringify(response) }],
            details: response,
            terminate: false,
          }
        },
      })
      const dataTools: AgentTool<TSchema, JsonValue>[] = [
        previewTool('select_fields', '正在预览字段选择', {
          source_alias: { type: 'string' },
          field_aliases: { type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 128 },
        }, ['source_alias', 'field_aliases']),
        previewTool('filter_rows', '正在预览数据筛选', {
          source_alias: { type: 'string' },
          predicates: {
            type: 'array', minItems: 1, maxItems: 16,
            items: {
              type: 'object', additionalProperties: false,
              properties: {
                field_alias: { type: 'string' },
                operator: { type: 'string', enum: [
                  'equal', 'not_equal', 'less_than', 'less_or_equal',
                  'greater_than', 'greater_or_equal', 'is_missing', 'is_not_missing', 'in_values',
                ] },
                value: {},
              },
              required: ['field_alias', 'operator'],
            },
          },
          combine: { type: 'string', enum: ['all', 'any'] },
        }, ['source_alias', 'predicates']),
        previewTool('sort_rows', '正在预览数据排序', {
          source_alias: { type: 'string' },
          keys: {
            type: 'array', minItems: 1, maxItems: 8,
            items: {
              type: 'object', additionalProperties: false,
              properties: {
                field_alias: { type: 'string' },
                direction: { type: 'string', enum: ['ascending', 'descending'] },
                missing: { type: 'string', enum: ['first', 'last'] },
              },
              required: ['field_alias'],
            },
          },
        }, ['source_alias', 'keys']),
        previewTool('reshape_long_to_wide', '正在预览长表转宽表', {
          source_alias: { type: 'string' },
          index_field_aliases: { type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 8 },
          name_field_alias: { type: 'string' }, value_field_alias: { type: 'string' },
          output_fields: {
            type: 'array', minItems: 1, maxItems: 64,
            items: {
              type: 'object', additionalProperties: false,
              properties: { field_alias: { type: 'string' }, name: { type: 'string' } },
              required: ['field_alias', 'name'],
            },
          },
        }, ['source_alias', 'index_field_aliases', 'name_field_alias', 'value_field_alias', 'output_fields']),
        previewTool('reshape_wide_to_long', '正在预览宽表转长表', {
          source_alias: { type: 'string' },
          id_field_aliases: { type: 'array', items: { type: 'string' }, maxItems: 8 },
          value_field_aliases: { type: 'array', items: { type: 'string' }, minItems: 2, maxItems: 64 },
          output_name: { type: 'string' }, output_value: { type: 'string' },
        }, ['source_alias', 'value_field_aliases', 'output_name', 'output_value']),
        previewTool('concatenate_sources', '正在预览数据表拼接', {
          source_aliases: { type: 'array', items: { type: 'string' }, minItems: 2, maxItems: 8 },
          source_label_field: { type: 'string' },
          source_labels: { type: 'array', items: { type: 'string' }, maxItems: 8 },
        }, ['source_aliases']),
        previewTool('rename_field', '正在预览字段重命名', {
          source_alias: { type: 'string' }, field_alias: { type: 'string' },
          output_field_alias: { type: 'string' }, output_name: { type: 'string' },
        }, ['source_alias', 'field_alias', 'output_field_alias', 'output_name']),
        previewTool('derive_column', '正在预览派生字段', {
          source_alias: { type: 'string' },
          input_field_aliases: { type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 2 },
          operator: { type: 'string', enum: ['add', 'subtract', 'multiply', 'divide', 'absolute', 'negate', 'log10', 'ln', 'sqrt'] },
          scalar: { type: 'number' }, output_field_alias: { type: 'string' }, output_name: { type: 'string' },
        }, ['source_alias', 'input_field_aliases', 'operator', 'output_field_alias', 'output_name']),
        previewTool('convert_unit', '正在预览单位换算', {
          source_alias: { type: 'string' }, field_alias: { type: 'string' },
          target_unit: { type: 'string' }, output_field_alias: { type: 'string' },
          output_name: { type: 'string' },
        }, ['source_alias', 'field_alias', 'target_unit', 'output_field_alias', 'output_name']),
      ]
      const tools: AgentTool<TSchema, JsonValue>[] = [
        {
          name: 'list_plot_profiles',
          label: '查看图形目录',
          description: '列出当前绘图引擎允许的图类、字段角色、对象和可编辑能力；用于根据用户原文选择图类，禁止凭 ID 猜测。',
          parameters: objectSchema({}, []),
          executionMode: 'sequential',
          execute: async () => {
            this.emit(clientRunId, projectId, 'inspecting_data', '正在查看可用图类…')
            const response = await this.core.request('engine.catalog.get', {
              project_id: projectId,
            }, 10_000)
            return {
              content: [{ type: 'text', text: JSON.stringify(response) }],
              details: response,
              terminate: false,
            }
          },
        },
        ...inspectionTools,
        ...dataTools,
        {
          name: 'ask_user',
          label: '向用户澄清',
          description: '仅在完成任务确实缺少关键信息时，提出 1 至 4 个结构化问题并暂停本轮。',
          parameters: objectSchema({
            questions: {
              type: 'array', minItems: 1, maxItems: 4,
              items: {
                type: 'object', additionalProperties: false,
                properties: {
                  question_key: { type: 'string' },
                  prompt: { type: 'string' },
                  answer_kind: {
                    type: 'string',
                    enum: ['text', 'single_choice', 'multi_choice', 'field', 'profile'],
                  },
                  choices: { type: 'array', items: { type: 'string' }, maxItems: 24 },
                  required: { type: 'boolean' },
                },
                required: ['question_key', 'prompt', 'answer_kind'],
              },
            },
          }, ['questions']),
          executionMode: 'sequential',
          execute: async (_toolCallId, args) => {
            const payload = record(args as JsonValue, 'Clarification arguments')
            finalOutcome = await this.core.request('workflow.ask_user', {
              project_id: projectId,
              workflow_run_id: prepared.workflowRunId,
              questions: payload.questions,
            }, 10_000)
            return {
              content: [{ type: 'text', text: 'Clarification requested from the user.' }],
              details: finalOutcome,
              terminate: true,
            }
          },
        },
        {
          name: 'report_unsupported',
          label: '说明当前不支持',
          description: '只有在检查图形目录和允许工具后，仍无法在能力边界内满足目标时使用；给出具体原因，不得用它代替必要追问。',
          parameters: objectSchema({
            reason_code: { type: 'string' },
            message: { type: 'string' },
          }, ['reason_code', 'message']),
          executionMode: 'sequential',
          execute: async (_toolCallId, args) => {
            const payload = record(args as JsonValue, 'Unsupported workflow arguments')
            finalOutcome = await this.core.request('workflow.report_unsupported', {
              project_id: projectId,
              workflow_run_id: prepared.workflowRunId,
              reason_code: payload.reason_code,
              message: payload.message,
            }, 10_000)
            return {
              content: [{ type: 'text', text: 'Unsupported outcome recorded.' }],
              details: finalOutcome,
              terminate: true,
            }
          },
        },
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
              finalOutcome = await this.core.request('workflow.submit_draft', {
                project_id: projectId,
                workflow_run_id: prepared.workflowRunId,
                task_draft: payload.task_draft,
              }, 10_000)
              return {
                content: [{ type: 'text', text: 'TaskDraft accepted for user confirmation.' }],
                details: finalOutcome,
                terminate: true,
              }
            } catch (error) {
              lastValidationError = String(error)
              return {
                content: [{ type: 'text', text: `Local validation rejected this draft: ${lastValidationError}` }],
                details: { validationError: lastValidationError },
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
        shouldStopAfterTurn: () => {
          completedAgentTurns += 1
          return finalOutcome !== undefined || completedAgentTurns >= maxAgentTurns
        },
        sessionId: prepared.workflowRunId,
      })
      agent.subscribe((event) => {
        if (generation !== this.generation) return
        const next = lifecycleStage(event)
        if (next !== undefined) this.emit(clientRunId, projectId, next.stage, next.label)
      })
      this.active = { runId: clientRunId, generation, agent }
      const promptPayload = {
        workflow_context: prepared.context,
        ...(prepared.clarificationHistory === undefined
          ? {}
          : { clarification_history: prepared.clarificationHistory }),
      }
      await Promise.race([
        agent.prompt(JSON.stringify(promptPayload)),
        new Promise<never>((_resolve, reject) => {
          timeout = setTimeout(() => {
            timedOut = true
            agent?.abort()
            const detail = lastValidationError === undefined
              ? ''
              : ` Last local validation error: ${lastValidationError}`
            reject(new PiRuntimeError(
              'PI_MODEL_TIMEOUT',
              `The workflow draft exceeded its timeout.${detail}`,
            ))
          }, this.timeoutMs)
        }),
      ])
      this.assertCurrent(generation)
      if (finalOutcome === undefined) {
        throw new PiRuntimeError(
          completedAgentTurns >= maxAgentTurns ? 'PI_TURN_BUDGET_EXCEEDED' : 'PI_DRAFT_MISSING',
          completedAgentTurns >= maxAgentTurns
            ? 'The workflow exceeded its bounded model-turn budget.'
            : 'The model did not submit a valid TaskDraft.',
        )
      }
      const outcome = record(finalOutcome, 'Final workflow outcome')
      if (outcome.outcome === 'draft_ready') {
        this.emit(clientRunId, projectId, 'saving_plan', '正在保存待确认任务计划…')
        this.emit(clientRunId, projectId, 'completed', '任务计划已生成，等待确认。')
      } else {
        this.emit(clientRunId, projectId, 'completed', '需要你补充信息后继续。')
      }
      return finalOutcome
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
