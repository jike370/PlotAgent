/** Run the frozen 24x3 SEQ-70 qualification through the production Pi runtime. */

import { execFileSync } from 'node:child_process'
import { createHash, randomUUID } from 'node:crypto'
import { promises as fs } from 'node:fs'
import { delimiter, join, resolve } from 'node:path'

import {
  createAssistantMessageEventStream,
  type AssistantMessage,
  type JsonValue,
  type Model,
} from '@earendil-works/pi-ai'
import type { StreamFn } from '@earendil-works/pi-agent-core'
import { streamSimple } from '@earendil-works/pi-ai/api/openai-completions'

import {
  PiAgentRuntime,
  type PiAgentRuntimeEvent,
  type PiCoreBridge,
} from '../src/main/agent/pi-runtime.js'
import { PythonCoreSupervisor } from '../src/main/core/python-supervisor.js'

type JsonObject = { [key: string]: JsonValue }

interface FixtureDefinition {
  readonly header: string[]
  readonly rows: JsonValue[][]
}

interface TaskExpectation extends JsonObject {
  readonly decision_types: string[]
}

interface EvalTask {
  readonly task_id: string
  readonly layer: 'model' | 'runtime'
  readonly category: string
  readonly fixture?: string
  readonly target?: 'source' | 'plot'
  readonly selected_profile_id?: string
  readonly instruction?: string
  readonly scenario?: string
  readonly expectation?: TaskExpectation
}

interface TaskSet {
  readonly schema_version: string
  readonly repeats: number
  readonly provider_config_id: string
  readonly pricing_cny_per_million_tokens: {
    readonly input_cache_hit: number
    readonly input_cache_miss: number
    readonly output: number
  }
  readonly thresholds: Record<string, number>
  readonly fixtures: Record<string, FixtureDefinition>
  readonly tasks: EvalTask[]
}

interface ImportedDataset {
  readonly source_dataset_id: string
  readonly source_version: number
  readonly content_hash: string
  readonly fields: { field_id: string; name: string; logical_type: string }[]
}

interface UsageRecord {
  input: number
  output: number
  cacheRead: number
  cacheWrite: number
}

interface EvalRecord {
  readonly task_id: string
  readonly repeat: number
  readonly layer: 'model' | 'runtime'
  readonly category: string
  readonly passed: boolean
  readonly accepted: boolean
  readonly latency_seconds: number
  readonly observation: string
  readonly decision?: JsonValue
  readonly error_code?: string
  readonly events: PiAgentRuntimeEvent[]
  readonly usage: UsageRecord
  readonly metrics: {
    plan_legal?: boolean
    target_correct?: boolean
    mapping_correct?: boolean
    necessary_question_correct?: boolean
    invalid_question?: boolean
    incorrect_auto_binding?: boolean
  }
}

const DECISION_SCHEMA: JsonObject = {
  type: 'object',
  properties: {
    schema_version: { const: 'engine-agent.v1' },
    decision_type: { const: 'no_change' },
    target_alias: { type: 'string' },
    explanation: { type: 'string' },
  },
  required: ['schema_version', 'decision_type', 'target_alias', 'explanation'],
  additionalProperties: false,
}

const SIMPLE_DECISION: JsonObject = {
  schema_version: 'engine-agent.v1',
  decision_type: 'no_change',
  target_alias: 'active_target',
  explanation: 'No mutation is needed.',
}

function asObject(value: JsonValue, label: string): JsonObject {
  if (value === null || Array.isArray(value) || typeof value !== 'object') {
    throw new Error(`${label} is not an object`)
  }
  return value
}

function errorCode(error: unknown): string {
  if (error !== null && typeof error === 'object' && 'code' in error) {
    return String((error as { code?: unknown }).code ?? 'UNKNOWN')
  }
  return error instanceof Error ? error.name : 'UNKNOWN'
}

function sha256(value: string | Buffer): string {
  return createHash('sha256').update(value).digest('hex')
}

function percentile(values: number[], fraction: number): number {
  if (values.length === 0) return 0
  const sorted = [...values].sort((left, right) => left - right)
  const index = Math.max(0, Math.ceil(sorted.length * fraction) - 1)
  return sorted[index]
}

function ratio(numerator: number, denominator: number): number {
  return denominator === 0 ? 1 : numerator / denominator
}

function csvCell(value: JsonValue): string {
  const raw = value === null ? '' : String(value)
  return /[",\r\n]/.test(raw) ? `"${raw.replaceAll('"', '""')}"` : raw
}

function csvText(fixture: FixtureDefinition): string {
  return [fixture.header, ...fixture.rows]
    .map((row) => row.map(csvCell).join(','))
    .join('\n') + '\n'
}

async function waitForCore(supervisor: PythonCoreSupervisor): Promise<void> {
  if (supervisor.getStatus().phase === 'ready') return
  await new Promise<void>((resolveReady, reject) => {
    const timer = setTimeout(() => {
      unsubscribe()
      reject(new Error('SEQ-70 Core did not become ready'))
    }, 15_000)
    const unsubscribe = supervisor.subscribeStatus((status) => {
      if (status.phase === 'ready') {
        clearTimeout(timer)
        unsubscribe()
        resolveReady()
      } else if (status.phase === 'failed') {
        clearTimeout(timer)
        unsubscribe()
        reject(new Error(`SEQ-70 Core failed: ${status.error?.code ?? 'UNKNOWN'}`))
      }
    })
    supervisor.start()
  })
}

function meteredStream(usage: UsageRecord): StreamFn {
  return async (model, context, options) => {
    const source = await streamSimple(
      model as Model<'openai-completions'>,
      context,
      options,
    )
    const proxy = createAssistantMessageEventStream()
    void (async () => {
      for await (const event of source) {
        if (event.type === 'done' || event.type === 'error') {
          const item = (event.type === 'done' ? event.message : event.error).usage
          usage.input += item.input
          usage.output += item.output
          usage.cacheRead += item.cacheRead
          usage.cacheWrite += item.cacheWrite
        }
        proxy.push(event)
      }
    })()
    return proxy
  }
}

function assistantStream(kind: 'none' | 'multiple'): ReturnType<StreamFn> {
  const stream = createAssistantMessageEventStream()
  const content: AssistantMessage['content'] = kind === 'none'
    ? [{ type: 'text', text: 'No tool call.' }]
    : [1, 2].map((index) => ({
      type: 'toolCall' as const,
      id: `call-${index}`,
      name: 'submit_plotagent_decision',
      arguments: { decision: SIMPLE_DECISION },
    }))
  const message: AssistantMessage = {
    role: 'assistant',
    content,
    api: 'openai-completions',
    provider: 'seq70',
    model: 'runtime-fixture',
    usage: {
      input: 0,
      output: 0,
      cacheRead: 0,
      cacheWrite: 0,
      totalTokens: 0,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
    },
    stopReason: kind === 'none' ? 'stop' : 'toolUse',
    timestamp: Date.now(),
  }
  queueMicrotask(() => {
    stream.push({ type: 'start', partial: message })
    content.forEach((item, contentIndex) => {
      if (item.type !== 'toolCall') return
      stream.push({ type: 'toolcall_start', contentIndex, partial: message })
      stream.push({ type: 'toolcall_end', contentIndex, toolCall: item, partial: message })
    })
    stream.push({ type: 'done', reason: kind === 'none' ? 'stop' : 'toolUse', message })
  })
  return stream
}

function preparedHandoff(): JsonObject {
  return {
    accepted: true,
    prepared: true,
    context_envelope: { context_hash: 'a'.repeat(64) },
    decision_schema: DECISION_SCHEMA,
    system_prompt: 'Return one decision.',
  }
}

function configuredProvider(): JsonObject {
  return { base_url: 'https://model.invalid/v1', model_id: 'runtime-fixture', api_key: 'hidden' }
}

async function runtimeScenario(task: EvalTask, repeat: number): Promise<EvalRecord> {
  const events: PiAgentRuntimeEvent[] = []
  const usage = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }
  const started = performance.now()
  let passed = false
  let observation: string
  let code: string | undefined
  try {
    if (task.scenario === 'deterministic_preflight') {
      const runtime = new PiAgentRuntime({
        core: { request: async () => ({ accepted: true, decision: SIMPLE_DECISION }) },
        emit: (event) => events.push(event),
        streamFn: () => { throw new Error('model must not run') },
      })
      const result = await runtime.decide({
        project_id: 'project:runtime',
        client_model_run_id: `runtime:${task.task_id}.${repeat}`,
      })
      passed = asObject(result, 'runtime result').accepted === true
      observation = 'Core preflight returned without provider execution.'
    } else if (task.scenario === 'provider_missing') {
      const runtime = new PiAgentRuntime({
        core: {
          request: async (method) => method === 'agent.engine.decide' ? preparedHandoff() : {},
        },
        emit: (event) => events.push(event),
        streamFn: () => { throw new Error('model must not run') },
      })
      try {
        await runtime.decide({
          project_id: 'project:runtime',
          client_model_run_id: `runtime:${task.task_id}.${repeat}`,
        })
      } catch (error) {
        code = errorCode(error)
      }
      passed = code === 'PROVIDER_NOT_CONFIGURED' && events.at(-1)?.stage === 'failed'
      observation = 'Missing provider failed closed with a terminal runtime event.'
    } else if (task.scenario === 'missing_tool' || task.scenario === 'multiple_decisions') {
      let externalCalls = 0
      const runtime = new PiAgentRuntime({
        core: {
          request: async (method, params) => {
            if (method === 'provider.runtime.get') return configuredProvider()
            const payload = asObject(params ?? {}, 'runtime params')
            if (payload.prepare_only === true) return preparedHandoff()
            externalCalls += 1
            return { accepted: true, decision: SIMPLE_DECISION }
          },
        },
        emit: (event) => events.push(event),
        streamFn: (() => assistantStream(
          task.scenario === 'missing_tool' ? 'none' : 'multiple',
        )) as StreamFn,
      })
      try {
        await runtime.decide({
          project_id: 'project:runtime',
          client_model_run_id: `runtime:${task.task_id}.${repeat}`,
        })
      } catch (error) {
        code = errorCode(error)
      }
      const expected = task.scenario === 'missing_tool'
        ? 'PI_DECISION_MISSING'
        : 'PI_MULTIPLE_DECISIONS'
      passed = code === expected && externalCalls === 0 && events.at(-1)?.stage === 'failed'
      observation = `${task.scenario} was rejected before Core persistence.`
    } else if (task.scenario === 'core_rejection') {
      const core: PiCoreBridge = {
        request: async (method, params) => {
          if (method === 'provider.runtime.get') return configuredProvider()
          const payload = asObject(params ?? {}, 'runtime params')
          if (payload.prepare_only === true) return preparedHandoff()
          return { accepted: false, error: { code: 'ENGINE_PLAN_INVALID' } }
        },
      }
      const singleTool: StreamFn = () => {
        const stream = createAssistantMessageEventStream()
        const call = {
          type: 'toolCall' as const,
          id: 'call-1',
          name: 'submit_plotagent_decision',
          arguments: { decision: SIMPLE_DECISION },
        }
        const message: AssistantMessage = {
          role: 'assistant', content: [call], api: 'openai-completions', provider: 'seq70',
          model: 'runtime-fixture', usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0,
            totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
          stopReason: 'toolUse', timestamp: Date.now(),
        }
        queueMicrotask(() => {
          stream.push({ type: 'start', partial: message })
          stream.push({ type: 'toolcall_start', contentIndex: 0, partial: message })
          stream.push({ type: 'toolcall_end', contentIndex: 0, toolCall: call, partial: message })
          stream.push({ type: 'done', reason: 'toolUse', message })
        })
        return stream
      }
      const authorityRuntime = new PiAgentRuntime({
        core,
        emit: (event) => events.push(event),
        streamFn: singleTool,
      })
      try {
        await authorityRuntime.decide({
          project_id: 'project:runtime',
          client_model_run_id: `runtime:${task.task_id}.${repeat}`,
        })
      } catch (error) {
        code = errorCode(error)
      }
      passed = code === 'ENGINE_PLAN_INVALID' && events.at(-1)?.stage === 'failed'
      observation = 'Structured Core rejection remained authoritative.'
    } else if (task.scenario === 'superseded_run') {
      let releaseFirst: ((value: JsonValue) => void) | undefined
      const firstPrepared = new Promise<JsonValue>((resolveFirst) => { releaseFirst = resolveFirst })
      let externalCalls = 0
      const core: PiCoreBridge = {
        request: async (method, params) => {
          const payload = asObject(params ?? {}, 'runtime params')
          const runId = String(payload.client_model_run_id ?? '')
          if (method === 'provider.runtime.get') return configuredProvider()
          if (payload.prepare_only === true && runId.endsWith('.first')) return firstPrepared
          if (payload.prepare_only === true) return { accepted: true, decision: SIMPLE_DECISION }
          externalCalls += 1
          return { accepted: true, decision: SIMPLE_DECISION }
        },
      }
      const runtime = new PiAgentRuntime({
        core,
        emit: (event) => events.push(event),
        streamFn: () => assistantStream('none'),
      })
      const first = runtime.decide({
        project_id: 'project:runtime',
        client_model_run_id: `runtime:${task.task_id}.${repeat}.first`,
      })
      await Promise.resolve()
      await runtime.decide({
        project_id: 'project:runtime',
        client_model_run_id: `runtime:${task.task_id}.${repeat}.second`,
      })
      releaseFirst?.(preparedHandoff())
      try {
        await first
      } catch (error) {
        code = errorCode(error)
      }
      passed = code === 'PI_RUN_SUPERSEDED' && externalCalls === 0
      observation = 'Older preparation was superseded without persistence.'
    } else {
      throw new Error(`Unknown runtime scenario: ${task.scenario ?? ''}`)
    }
  } catch (error) {
    code = errorCode(error)
    observation = error instanceof Error ? error.message : String(error)
  }
  return {
    task_id: task.task_id,
    repeat,
    layer: 'runtime',
    category: task.category,
    passed,
    accepted: passed,
    latency_seconds: (performance.now() - started) / 1000,
    observation,
    ...(code === undefined ? {} : { error_code: code }),
    events,
    usage,
    metrics: {},
  }
}

function evaluateDecision(task: EvalTask, result: JsonObject): {
  passed: boolean
  observation: string
  metrics: EvalRecord['metrics']
  decision?: JsonValue
} {
  const decision = result.decision
  const expected = task.expectation
  if (expected === undefined || decision === undefined) {
    return { passed: false, observation: 'Decision was absent.', metrics: {} }
  }
  const item = asObject(decision, 'decision')
  const decisionType = String(item.decision_type ?? '')
  const expectedTypes = expected.decision_types
  const typeCorrect = expectedTypes.includes(decisionType)
  const necessary = task.category === 'necessary_question'
  const invalidQuestion = decisionType === 'needs_input' && !expectedTypes.includes('needs_input')
  const incorrectAuto = necessary && decisionType === 'action_plan'
  const metrics: EvalRecord['metrics'] = {
    plan_legal: result.accepted === true,
    necessary_question_correct: necessary ? decisionType === 'needs_input' : undefined,
    invalid_question: invalidQuestion,
    incorrect_auto_binding: incorrectAuto,
  }
  if (!typeCorrect) {
    return {
      passed: false,
      observation: `Expected ${expectedTypes.join('/')} but received ${decisionType || 'none'}.`,
      metrics,
      decision,
    }
  }
  if (decisionType !== 'action_plan') {
    return { passed: true, observation: `Received ${decisionType}.`, metrics, decision }
  }
  const actions = Array.isArray(item.actions) ? item.actions : []
  const operation = String(expected.operation ?? '')
  const action = actions.find((candidate) => (
    candidate !== null && !Array.isArray(candidate) && typeof candidate === 'object'
      && candidate.operation === operation
  )) as JsonObject | undefined
  const targetCorrect = item.target_alias === 'active_target'
    && action !== undefined
    && (operation === 'create_plot'
      ? action.source_alias === 'active_target'
      : action.plot_alias === 'active_target')
  metrics.target_correct = targetCorrect
  if (action === undefined || actions.length !== 1) {
    return {
      passed: false,
      observation: `Expected exactly one ${operation} action.`,
      metrics,
      decision,
    }
  }
  let exact = targetCorrect
  if (expected.profile_id !== undefined) exact = exact && action.profile_id === expected.profile_id
  if (expected.text !== undefined) exact = exact && action.text === expected.text
  if (expected.axis_alias !== undefined) exact = exact && action.axis_alias === expected.axis_alias
  if (expected.label !== undefined) exact = exact && action.label === expected.label
  if (expected.scale !== undefined) exact = exact && action.scale === expected.scale
  if (expected.minimum !== undefined) exact = exact && action.minimum === expected.minimum
  if (expected.maximum !== undefined) exact = exact && action.maximum === expected.maximum
  if (expected.series_alias !== undefined) exact = exact && action.series_alias === expected.series_alias
  if (expected.color !== undefined) exact = exact && action.color === expected.color
  if (expected.line_width_pt !== undefined) exact = exact && action.line_width_pt === expected.line_width_pt
  if (expected.line_style !== undefined) exact = exact && action.line_style === expected.line_style
  if (expected.visible !== undefined) exact = exact && action.visible === expected.visible
  if (expected.format !== undefined) exact = exact && action.format === expected.format
  if (expected.output_name !== undefined) exact = exact && action.output_name === expected.output_name
  if (expected.bindings !== undefined) {
    const actual = new Map<string, string>()
    if (Array.isArray(action.bindings)) {
      for (const binding of action.bindings) {
        if (binding !== null && !Array.isArray(binding) && typeof binding === 'object') {
          actual.set(String(binding.role ?? ''), String(binding.field_alias ?? ''))
        }
      }
    }
    const expectedBindings = expected.bindings as JsonObject
    const mappingCorrect = Object.entries(expectedBindings).every(
      ([role, alias]) => actual.get(role) === alias,
    ) && actual.size === Object.keys(expectedBindings).length
    metrics.mapping_correct = mappingCorrect
    exact = exact && mappingCorrect
  }
  return {
    passed: exact,
    observation: exact ? `Exact ${operation} decision accepted.` : `${operation} differed from expectation.`,
    metrics,
    decision,
  }
}

async function modelTask(
  task: EvalTask,
  repeat: number,
  core: PythonCoreSupervisor,
  dataDir: string,
): Promise<EvalRecord> {
  if (task.fixture === undefined) throw new Error(`Missing fixture for ${task.task_id}`)
  const created = asObject(await core.request('projects.create', {
    display_name: `SEQ-70 ${task.task_id}.r${repeat}`,
    idempotency_key: `seq70-${task.task_id}-${repeat}-${randomUUID()}`,
  }), 'created task project')
  const projectId = String(created.project_id)
  const opened = asObject(await core.request('projects.open', {
    project_id: projectId,
  }), 'opened task project')
  let projectVersion = Number(opened.project_version)
  const imported = asObject(await core.request('datasets.import', {
    project_id: projectId,
    resource_id: `resource:seq70.${task.fixture}.${task.task_id}.${repeat}`,
    source_path: join(dataDir, `${task.fixture}.csv`),
    idempotency_key: `seq70-import-${task.task_id}-${repeat}-${randomUUID()}`,
    expected_version: projectVersion,
    options: {},
  }, 60_000), 'import task fixture')
  projectVersion = Number(imported.project_version)
  if (!Array.isArray(imported.datasets) || imported.datasets.length !== 1) {
    throw new Error(`Fixture ${task.fixture} did not import as one dataset`)
  }
  const fixture = imported.datasets[0] as unknown as ImportedDataset
  const plotId = `plot:seq70.${task.task_id.toLowerCase()}.${repeat}`
  if (task.target === 'plot') {
    const createdPlot = asObject(await core.request('engine.actions.execute', {
      project_id: projectId,
      expected_project_version: projectVersion,
      action: {
        operation: 'create_plot',
        action_id: `action:setup-${task.task_id.toLowerCase()}-${repeat}`,
        plot_id: plotId,
        profile_id: task.selected_profile_id ?? 'K01',
        data: {
          kind: 'source',
          dataset_id: fixture.source_dataset_id,
          version: fixture.source_version,
          content_hash: fixture.content_hash,
        },
        bindings: [
          { role: 'x', field_id: fixture.fields[0].field_id },
          { role: 'y', field_id: fixture.fields[1].field_id },
        ],
      },
    }, 60_000), 'create task plot')
    projectVersion = Number(createdPlot.project_version)
  }
  const events: PiAgentRuntimeEvent[] = []
  const usage = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }
  const runtime = new PiAgentRuntime({
    core,
    emit: (event) => events.push(event),
    streamFn: meteredStream(usage),
  })
  const runId = `model-run:seq70.${task.task_id}.${repeat}.${randomUUID()}`
  const params: JsonObject = {
    project_id: projectId,
    source_dataset_id: fixture.source_dataset_id,
    source_version: fixture.source_version,
    user_instruction: task.instruction ?? '',
    client_model_run_id: runId,
    expected_version: projectVersion,
    locale: 'zh-CN',
    ...(task.selected_profile_id === undefined
      ? {}
      : { selected_profile_id: task.selected_profile_id }),
    ...(task.target === 'plot' ? { target_plot_id: plotId } : {}),
  }
  const started = performance.now()
  try {
    const result = asObject(await runtime.decide(params), 'Pi result')
    const evaluated = evaluateDecision(task, result)
    return {
      task_id: task.task_id,
      repeat,
      layer: 'model',
      category: task.category,
      passed: evaluated.passed,
      accepted: result.accepted === true,
      latency_seconds: (performance.now() - started) / 1000,
      observation: evaluated.observation,
      ...(evaluated.decision === undefined ? {} : { decision: evaluated.decision }),
      events,
      usage,
      metrics: evaluated.metrics,
    }
  } catch (error) {
    return {
      task_id: task.task_id,
      repeat,
      layer: 'model',
      category: task.category,
      passed: false,
      accepted: false,
      latency_seconds: (performance.now() - started) / 1000,
      observation: error instanceof Error ? error.message : String(error),
      error_code: errorCode(error),
      events,
      usage,
      metrics: { plan_legal: false },
    }
  } finally {
    await core.request('projects.close', { project_id: projectId }).catch(() => undefined)
  }
}

async function setupCore(
  core: PythonCoreSupervisor,
  taskSet: TaskSet,
  output: string,
): Promise<{
  projectId: string
  projectVersion: number
  datasets: Map<string, ImportedDataset>
  plotId: string
  provider: JsonObject
}> {
  const provider = asObject(await core.request('provider.runtime.get', {}, 10_000), 'provider')
  const created = asObject(await core.request('projects.create', {
    display_name: 'SEQ-70 Pi qualification',
    idempotency_key: `seq70-${randomUUID()}`,
  }), 'created project')
  const projectId = String(created.project_id)
  const opened = asObject(await core.request('projects.open', { project_id: projectId }), 'opened project')
  let projectVersion = Number(opened.project_version)
  const dataDir = join(output, 'data')
  await fs.mkdir(dataDir, { recursive: true })
  const datasets = new Map<string, ImportedDataset>()
  for (const [name, fixture] of Object.entries(taskSet.fixtures)) {
    const path = join(dataDir, `${name}.csv`)
    await fs.writeFile(path, csvText(fixture), 'utf8')
    const imported = asObject(await core.request('datasets.import', {
      project_id: projectId,
      resource_id: `resource:seq70.${name}`,
      source_path: path,
      idempotency_key: `seq70-import-${name}-${randomUUID()}`,
      expected_version: projectVersion,
      options: {},
    }, 60_000), `import ${name}`)
    projectVersion = Number(imported.project_version)
    const items = imported.datasets
    if (!Array.isArray(items) || items.length !== 1) {
      throw new Error(`SEQ-70 fixture ${name} did not import as one dataset`)
    }
    datasets.set(name, items[0] as unknown as ImportedDataset)
  }
  const xy = datasets.get('xy')
  if (xy === undefined) throw new Error('xy fixture missing')
  const plotId = 'plot:seq70.k01'
  const createdPlot = asObject(await core.request('engine.actions.execute', {
    project_id: projectId,
    expected_project_version: projectVersion,
    action: {
      operation: 'create_plot',
      action_id: 'action:seq70-create-line',
      plot_id: plotId,
      profile_id: 'K01',
      data: {
        kind: 'source',
        dataset_id: xy.source_dataset_id,
        version: xy.source_version,
        content_hash: xy.content_hash,
      },
      bindings: [
        { role: 'x', field_id: xy.fields[0].field_id },
        { role: 'y', field_id: xy.fields[1].field_id },
      ],
    },
  }, 60_000), 'create line plot')
  projectVersion = Number(createdPlot.project_version)
  return { projectId, projectVersion, datasets, plotId, provider }
}

function aggregate(taskSet: TaskSet, records: EvalRecord[]): JsonObject {
  const model = records.filter((item) => item.layer === 'model')
  const runtime = records.filter((item) => item.layer === 'runtime')
  const mappings = model.filter((item) => item.category === 'plan_mapping')
  const targets = model.filter((item) => item.metrics.target_correct !== undefined)
  const necessary = model.filter((item) => item.category === 'necessary_question')
  const nonNecessary = model.filter((item) => item.category !== 'necessary_question')
  const latencies = model.map((item) => item.latency_seconds)
  const usage = records.reduce((total, item) => ({
    input: total.input + item.usage.input,
    output: total.output + item.usage.output,
    cacheRead: total.cacheRead + item.usage.cacheRead,
    cacheWrite: total.cacheWrite + item.usage.cacheWrite,
  }), { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 })
  const rates = {
    candidate_plan_legal_rate: ratio(model.filter((item) => item.metrics.plan_legal).length, model.length),
    local_validator_accept_rate: ratio(model.filter((item) => item.accepted).length, model.length),
    target_binding_accuracy: ratio(targets.filter((item) => item.metrics.target_correct).length, targets.length),
    incorrect_auto_binding_rate: ratio(necessary.filter((item) => item.metrics.incorrect_auto_binding).length, necessary.length),
    field_mapping_first_pass_rate: ratio(mappings.filter((item) => item.metrics.mapping_correct).length, mappings.length),
    necessary_question_rate: ratio(necessary.filter((item) => item.metrics.necessary_question_correct).length, necessary.length),
    invalid_question_rate: ratio(nonNecessary.filter((item) => item.metrics.invalid_question).length, nonNecessary.length),
    model_task_exact_success_rate: ratio(model.filter((item) => item.passed).length, model.length),
    runtime_task_success_rate: ratio(runtime.filter((item) => item.passed).length, runtime.length),
    model_latency_median_seconds: percentile(latencies, 0.5),
    model_latency_p95_seconds: percentile(latencies, 0.95),
    model_latency_max_seconds: latencies.length === 0 ? 0 : Math.max(...latencies),
  }
  const thresholds = taskSet.thresholds
  const gates: Record<string, boolean> = {
    candidate_plan_legal_rate: rates.candidate_plan_legal_rate >= thresholds.candidate_plan_legal_rate,
    local_validator_accept_rate: rates.local_validator_accept_rate >= thresholds.local_validator_accept_rate,
    target_binding_accuracy: rates.target_binding_accuracy >= thresholds.target_binding_accuracy,
    incorrect_auto_binding_rate: rates.incorrect_auto_binding_rate <= thresholds.incorrect_auto_binding_rate_max,
    field_mapping_first_pass_rate: rates.field_mapping_first_pass_rate >= thresholds.field_mapping_first_pass_rate,
    necessary_question_rate: rates.necessary_question_rate >= thresholds.necessary_question_rate,
    invalid_question_rate: rates.invalid_question_rate <= thresholds.invalid_question_rate_max,
    model_task_exact_success_rate: rates.model_task_exact_success_rate >= thresholds.model_task_exact_success_rate,
    runtime_task_success_rate: rates.runtime_task_success_rate >= thresholds.runtime_task_success_rate,
    model_latency_p95_seconds: rates.model_latency_p95_seconds <= thresholds.model_latency_p95_seconds_max,
  }
  const miss = usage.input
  const totalInput = usage.input + usage.cacheRead
  const pricing = taskSet.pricing_cny_per_million_tokens
  const estimatedCost = (
    usage.cacheRead * pricing.input_cache_hit
    + miss * pricing.input_cache_miss
    + usage.output * pricing.output
  ) / 1_000_000
  return {
    decision: Object.values(gates).every(Boolean) ? 'GO' : 'NO_GO',
    rates,
    gates,
    counts: {
      total: records.length,
      model: model.length,
      runtime: runtime.length,
      passed: records.filter((item) => item.passed).length,
      failed: records.filter((item) => !item.passed).length,
    },
    usage: {
      ...usage,
      input_total: totalInput,
      input_cache_miss: miss,
      estimated_cost_cny: estimatedCost,
    },
  }
}

function markdownReport(metadata: JsonObject, summary: JsonObject, records: EvalRecord[]): string {
  const rates = asObject(summary.rates, 'rates')
  const gates = asObject(summary.gates, 'gates')
  const usage = asObject(summary.usage, 'usage')
  const failures = records.filter((item) => !item.passed)
  const rows = [
    ['候选计划合法率', 'candidate_plan_legal_rate'],
    ['本地校验接受率', 'local_validator_accept_rate'],
    ['对象绑定准确率', 'target_binding_accuracy'],
    ['错误自动绑定率', 'incorrect_auto_binding_rate'],
    ['字段映射首轮正确率', 'field_mapping_first_pass_rate'],
    ['必要追问率', 'necessary_question_rate'],
    ['无效追问率', 'invalid_question_rate'],
    ['模型任务精确成功率', 'model_task_exact_success_rate'],
    ['运行时任务成功率', 'runtime_task_success_rate'],
    ['模型延迟 P95（秒）', 'model_latency_p95_seconds'],
  ].map(([label, key]) => `| ${label} | ${Number(rates[key]).toFixed(6)} | ${gates[key] ? 'PASS' : 'FAIL'} |`)
  return `# PlotAgent v3 SEQ-70 Pi Agent 资格报告

- 决策：**${summary.decision}**
- 源提交：\`${metadata.source_commit}\`
- Task set SHA-256：\`${metadata.task_set_sha256}\`
- Provider：\`${metadata.provider_config_id}\` / \`${metadata.model_id}\`
- 冻结任务：24 项 × 3 次 = 72 次

| 指标 | 结果 | 门禁 |
|---|---:|---|
${rows.join('\n')}

## 延迟与用量

- 中位延迟：${Number(rates.model_latency_median_seconds).toFixed(4)} 秒
- P95：${Number(rates.model_latency_p95_seconds).toFixed(4)} 秒
- 最大：${Number(rates.model_latency_max_seconds).toFixed(4)} 秒
- 输入 token：${usage.input_total}（cache read ${usage.cacheRead} / miss ${usage.input_cache_miss}）
- 输出 token：${usage.output}
- 估算成本：¥${Number(usage.estimated_cost_cny).toFixed(6)}

## 失败样例

${failures.length === 0 ? '无。' : failures.map((item) => `- ${item.task_id}.r${item.repeat}: ${item.observation}`).join('\n')}

## 说明

模型任务经生产 Pi runtime 调用，并把唯一工具决策交回隔离 desktop Core 做 schema、对象、字段和 profile 权威绑定；运行时任务覆盖确定性预检、Provider 缺失、漏调用工具、重复决策、Core 拒绝和陈旧请求抑制。评测不执行确认后的绘图计划，因此不会修改用户项目。
`
}

function htmlReport(markdown: string): string {
  const escaped = markdown
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
  return `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>SEQ-70 Pi Agent</title><style>body{font:16px/1.6 system-ui;margin:2rem auto;max-width:1100px;padding:0 1rem;white-space:pre-wrap;color:#172033} </style><body>${escaped}</body></html>`
}

async function main(): Promise<void> {
  const args = process.argv.slice(2)
  const validateOnly = args.includes('--validate-only')
  const preflightOnly = args.includes('--preflight-only')
  const outputIndex = args.indexOf('--output')
  const root = resolve(process.cwd())
  const taskPath = join(root, 'tests', 'fixtures', 'seq70', 'pi_agent_tasks.json')
  const rawTaskSet = await fs.readFile(taskPath, 'utf8')
  const taskSet = JSON.parse(rawTaskSet) as TaskSet
  if (taskSet.tasks.length !== 24 || taskSet.repeats !== 3) {
    throw new Error('SEQ-70 task set must remain exactly 24x3')
  }
  if (new Set(taskSet.tasks.map((item) => item.task_id)).size !== 24) {
    throw new Error('SEQ-70 task ids must be unique')
  }
  if (validateOnly) {
    console.log(JSON.stringify({ tasks: 24, repeats: 3, sha256: sha256(rawTaskSet) }))
    return
  }
  const stamp = new Date().toISOString().replaceAll(/[-:TZ.]/g, '').slice(0, 14)
  const output = resolve(outputIndex >= 0 && args[outputIndex + 1]
    ? args[outputIndex + 1]
    : join(root, 'build', 'seq70-agent-eval', `${stamp}-pi`))
  await fs.mkdir(output, { recursive: true })
  const python = join(root, '.venv', 'Scripts', 'python.exe')
  const env = { ...process.env }
  env.PYTHONPATH = env.PYTHONPATH === undefined
    ? join(root, 'src')
    : `${join(root, 'src')}${delimiter}${env.PYTHONPATH}`
  const supervisor = new PythonCoreSupervisor({
    launch: {
      command: python,
      args: [
        join(root, 'scripts', 'seq70_core_host.py'),
        '--root', join(output, 'core-state'),
        '--provider-catalog', join(
          process.env.LOCALAPPDATA ?? join(process.env.USERPROFILE ?? '', 'AppData', 'Local'),
          'PlotAgent',
          'catalog.sqlite3',
        ),
      ],
      cwd: root,
      env,
    },
    requestTimeoutMs: 40_000,
    heartbeatTimeoutMs: 15_000,
  })
  const records: EvalRecord[] = []
  try {
    await waitForCore(supervisor)
    const setup = await setupCore(supervisor, taskSet, output)
    const safeProvider = {
      provider_config_id: String(setup.provider.provider_config_id ?? ''),
      base_url: String(setup.provider.base_url ?? ''),
      model_id: String(setup.provider.model_id ?? ''),
    }
    if (safeProvider.provider_config_id !== taskSet.provider_config_id) {
      throw new Error(`Expected provider ${taskSet.provider_config_id}, got ${safeProvider.provider_config_id}`)
    }
    if (preflightOnly) {
      console.log(JSON.stringify({
        status: 'ready',
        provider_config_id: safeProvider.provider_config_id,
        model_id: safeProvider.model_id,
        datasets: setup.datasets.size,
        project_version: setup.projectVersion,
      }))
      return
    }
    const ordered = Array.from({ length: taskSet.repeats }, (_, index) => index + 1)
      .flatMap((repeat) => taskSet.tasks.map((task) => ({ task, repeat })))
    for (const [index, item] of ordered.entries()) {
      const record = item.task.layer === 'model'
        ? await modelTask(
          item.task,
          item.repeat,
          supervisor,
          join(output, 'data'),
        )
        : await runtimeScenario(item.task, item.repeat)
      records.push(record)
      await fs.appendFile(join(output, 'checkpoint.jsonl'), `${JSON.stringify(record)}\n`, 'utf8')
      console.log(`[${index + 1}/72] ${item.task.task_id}.r${item.repeat} ${record.passed ? 'PASS' : 'FAIL'} ${record.latency_seconds.toFixed(3)}s`)
    }
    const sourceCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim()
    const metadata: JsonObject = {
      schema_version: taskSet.schema_version,
      source_commit: sourceCommit,
      task_set_sha256: sha256(rawTaskSet),
      provider_config_id: safeProvider.provider_config_id,
      provider_base_url_origin: new URL(safeProvider.base_url).origin,
      model_id: safeProvider.model_id,
      started_from_clean_worktree: execFileSync('git', ['status', '--porcelain'], { cwd: root, encoding: 'utf8' }).trim() === '',
      output,
    }
    const summary = aggregate(taskSet, records)
    const payload = { metadata, summary, records }
    const markdown = markdownReport(metadata, summary, records)
    await fs.writeFile(join(output, 'report.json'), JSON.stringify(payload, null, 2), 'utf8')
    await fs.writeFile(join(output, 'REPORT.md'), markdown, 'utf8')
    await fs.writeFile(join(output, 'index.html'), htmlReport(markdown), 'utf8')
    console.log(JSON.stringify({ output, decision: summary.decision, summary }, null, 2))
    if (summary.decision !== 'GO') process.exitCode = 2
  } finally {
    await supervisor.stop()
  }
}

await main()
