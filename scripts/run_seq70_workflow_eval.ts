/** Run the frozen workflow-era SEQ-70 qualification against Pi and Desktop Core. */

import { createHash, randomUUID } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

import { streamSimple } from '@earendil-works/pi-ai/api/openai-completions'
import type {
  Api,
  AssistantMessageEventStream,
  Context,
  JsonValue,
  Model,
  SimpleStreamOptions,
  Usage,
} from '@earendil-works/pi-ai'
import type { StreamFn } from '@earendil-works/pi-agent-core'

import { AgentFoundationRuntime } from '../src/main/agent/agent-foundation-runtime.js'
import { PiRuntimeAdapterV2 } from '../src/main/agent/pi-runtime-v2.js'
import { PythonCoreSupervisor, type CoreLaunchSpec } from '../src/main/core/python-supervisor.js'

type JsonRecord = { [key: string]: JsonValue }

interface ExpectedVisualAction extends JsonRecord {
  operation: string
}

interface WorkflowTask {
  task_id: string
  layer: 'workflow'
  fixture_keys: string[]
  instruction: string
  selected_profile_ids: string[]
  setup_plot_profile?: string
  expected_outcome: 'draft_ready' | 'needs_input' | 'unsupported'
  expected_route: string
  expected_profiles?: string[]
  expected_bindings?: Record<string, string>
  expected_visual_actions?: ExpectedVisualAction[]
  expected_data_operations?: string[]
  require_inspection?: boolean
}

interface RuntimeTask {
  task_id: string
  layer: 'runtime'
  scenario: string
}

type EvalTask = WorkflowTask | RuntimeTask

interface TaskSet {
  schema_version: 'seq70-workflow-eval-v1'
  repeats: number
  pricing_cny_per_million_tokens: {
    input_cache_hit: number
    input_cache_miss: number
    output: number
  }
  thresholds: Record<string, number>
  tasks: EvalTask[]
}

interface ImportedDataset {
  source_dataset_id: string
  source_version: number
  display_name: string
  field_schema: { field_id: string; name: string }[]
}

interface UsageRecord {
  runKey: string
  modelId: string
  usage: Usage
}

interface CaseResult {
  task_id: string
  repeat: number
  layer: 'workflow' | 'runtime'
  passed: boolean
  route_ok?: boolean
  validator_ok?: boolean
  bindings_expected?: number
  bindings_matched?: number
  visual_expected?: number
  visual_matched?: number
  data_operations_expected?: number
  data_operations_matched?: number
  inspection_required?: boolean
  inspection_calls?: number
  confirmation_no_side_effect?: boolean
  model_calls: number
  latency_seconds: number
  failure?: string
}

const REPOSITORY = resolve(process.cwd())
const TASK_SET_PATH = join(REPOSITORY, 'tests', 'fixtures', 'seq70', 'workflow_tasks.json')

function record(value: JsonValue, label: string): JsonRecord {
  if (value === null || Array.isArray(value) || typeof value !== 'object') {
    throw new Error(`${label} is not an object`)
  }
  return value
}

function array(value: JsonValue | undefined, label: string): JsonValue[] {
  if (!Array.isArray(value)) throw new Error(`${label} is not an array`)
  return value
}

function text(value: JsonValue | undefined, label: string): string {
  if (typeof value !== 'string' || value.length === 0) throw new Error(`${label} is missing`)
  return value
}

function integer(value: JsonValue | undefined, label: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value)) throw new Error(`${label} is invalid`)
  return value
}

function sha256(path: string): string {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

function percentile(values: number[], quantile: number): number {
  if (values.length === 0) return 0
  const sorted = [...values].sort((left, right) => left - right)
  const index = Math.min(sorted.length - 1, Math.ceil(quantile * sorted.length) - 1)
  return sorted[Math.max(0, index)]
}

function waitUntilReady(supervisor: PythonCoreSupervisor): Promise<void> {
  const current = supervisor.getStatus()
  if (current.phase === 'ready') return Promise.resolve()
  if (current.phase === 'failed') return Promise.reject(new Error(current.error?.message ?? 'Core failed'))
  return new Promise<void>((resolvePromise, reject) => {
    const timer = setTimeout(() => {
      unsubscribe()
      reject(new Error('Core did not become ready within 20 seconds'))
    }, 20_000)
    const unsubscribe = supervisor.subscribeStatus((status) => {
      if (status.phase === 'failed') {
        clearTimeout(timer)
        unsubscribe()
        reject(new Error(status.error?.message ?? 'Core failed'))
      } else if (status.phase === 'ready') {
        clearTimeout(timer)
        unsubscribe()
        resolvePromise()
      }
    })
  })
}

function writeFixtures(root: string): Record<string, string> {
  const fixtureRoot = join(root, 'fixtures')
  mkdirSync(fixtureRoot, { recursive: true })
  const fixtures: Record<string, string> = {
    xy: 'X,Response\n1,1.0\n2,2.5\n3,4.0\n4,3.5\n5,6.0\n',
    xy_second: 'X,Response\n1,2.0\n2,3.0\n3,2.0\n4,5.0\n5,7.0\n',
    column: 'Category,Value\nA,3\nB,5\nC,4\nD,7\n',
    heatmap: 'Row,Column,Value\nA,X,-3\nA,Y,-1\nA,Z,0\nB,X,-2\nB,Y,0\nB,Z,4\nC,X,-0.75\nC,Y,4.5\nC,Z,9\n',
    error: 'X,Mean,XLower,XUpper,Lower,Upper\n1,2,0.9,1.2,1.7,2.4\n2,3.5,1.8,2.25,3.1,4.0\n3,5,2.85,3.2,4.65,5.45\n',
    ambiguous: 'Alpha,Beta\n1,5\n2,4\n3,7\n4,6\n',
    before_after: 'Subject,Before,After,Group\nS1,10,12,Control\nS2,11,13,Control\nS3,9,14,Treated\nS4,12,15,Treated\n',
  }
  const paths: Record<string, string> = {}
  for (const [key, contents] of Object.entries(fixtures)) {
    const path = join(fixtureRoot, `${key}.csv`)
    writeFileSync(path, contents, 'utf8')
    paths[key] = path
  }
  return paths
}

function taskSet(): TaskSet {
  const parsed: unknown = JSON.parse(readFileSync(TASK_SET_PATH, 'utf8'))
  return parsed as TaskSet
}

class EvalHarness {
  readonly core: PythonCoreSupervisor
  readonly agent: AgentFoundationRuntime
  readonly usage: UsageRecord[] = []
  activeRunKey = 'unattributed'
  coreCalls = new Map<string, number>()

  constructor(root: string, providerCatalog: string) {
    const python = join(REPOSITORY, '.venv', 'Scripts', 'python.exe')
    const env = { ...process.env, PYTHONPATH: join(REPOSITORY, 'src') }
    const launch: CoreLaunchSpec = {
      command: python,
      args: [
        join(REPOSITORY, 'scripts', 'seq70_core_host.py'),
        '--root', root,
        '--provider-catalog', providerCatalog,
      ],
      cwd: REPOSITORY,
      env,
    }
    this.core = new PythonCoreSupervisor({
      launch,
      startupTimeoutMs: 15_000,
      requestTimeoutMs: 15_000,
      shutdownTimeoutMs: 3_000,
      maximumRestarts: 0,
    })
    const streamFn: StreamFn = async (
      model: Model<Api>,
      context: Context,
      options?: SimpleStreamOptions,
    ): Promise<AssistantMessageEventStream> => {
      const stream = await streamSimple(
        model as Model<'openai-completions'>,
        context,
        options,
      )
      const runKey = this.activeRunKey
      void stream.result().then((message) => {
        this.usage.push({ runKey, modelId: model.id, usage: message.usage })
      })
      return stream
    }
    this.agent = new AgentFoundationRuntime({
      core: {
        request: async (method, params, timeoutMs) => {
          const key = `${this.activeRunKey}:${method}`
          this.coreCalls.set(key, (this.coreCalls.get(key) ?? 0) + 1)
          return this.core.request(method, params, timeoutMs)
        },
      },
      emit: () => undefined,
      createRuntime: (host, emit) => new PiRuntimeAdapterV2({ host, emit, streamFn }),
    })
  }

  async start(): Promise<void> {
    this.core.start()
    await waitUntilReady(this.core)
  }

  async stop(): Promise<void> {
    await this.core.stop()
  }

  calls(runKey: string, method: string): number {
    return this.coreCalls.get(`${runKey}:${method}`) ?? 0
  }

  modelCalls(runKey: string): number {
    return this.usage.filter((item) => item.runKey === runKey).length
  }
}

async function createProject(harness: EvalHarness, key: string): Promise<{ projectId: string; revision: number }> {
  const created = record(await harness.core.request('projects.create', {
    idempotency_key: `seq70:${key}`,
    display_name: `SEQ-70 ${key}`,
  }), 'project create')
  const projectId = text(created.project_id, 'project_id')
  const opened = record(await harness.core.request('projects.open', { project_id: projectId }), 'project open')
  return { projectId, revision: integer(opened.project_version, 'project_version') }
}

async function importFixtures(
  harness: EvalHarness,
  projectId: string,
  revision: number,
  fixtureKeys: string[],
  fixturePaths: Record<string, string>,
): Promise<{ revision: number; datasets: ImportedDataset[] }> {
  let currentRevision = revision
  for (const [position, fixtureKey] of fixtureKeys.entries()) {
    const path = fixturePaths[fixtureKey]
    if (path === undefined) throw new Error(`unknown fixture ${fixtureKey}`)
    const imported = record(await harness.core.request('datasets.import', {
      project_id: projectId,
      resource_id: `resource:${fixtureKey}:${position}`,
      source_path: path,
      idempotency_key: `import:${fixtureKey}:${position}:${randomUUID()}`,
      expected_version: currentRevision,
    }, 20_000), 'dataset import')
    currentRevision = integer(imported.project_version, 'import project_version')
  }
  const listed = record(await harness.core.request('datasets.list', { project_id: projectId }), 'dataset list')
  return {
    revision: integer(listed.project_version, 'dataset project_version'),
    datasets: array(listed.datasets, 'datasets').map((item) => record(item, 'dataset') as unknown as ImportedDataset),
  }
}

function selectedSources(datasets: ImportedDataset[]): { datasetId: string; sourceVersion: number }[] {
  return datasets.map((dataset) => ({
    datasetId: dataset.source_dataset_id,
    sourceVersion: dataset.source_version,
  }))
}

function planFrom(response: JsonRecord): JsonRecord | undefined {
  if (response.plan === undefined || response.task === undefined) return undefined
  return response
}

function compiledItems(response: JsonRecord): JsonRecord[] {
  const snapshot = planFrom(response)
  if (snapshot === undefined) return []
  const plan = record(snapshot.plan, 'plan')
  return array(plan.items, 'plan.items').map((item) => record(item, 'compiled item'))
}

function responseRoute(response: JsonRecord): string {
  return response.plan !== undefined || response.outcome === 'needs_input' ? 'agent' : ''
}

function valueMatches(observed: JsonValue | undefined, expected: JsonValue): boolean {
  if (typeof expected === 'number' && typeof observed === 'number') {
    return Math.abs(observed - expected) <= 1e-9
  }
  return observed === expected
}

function subsetMatches(observed: JsonRecord, expected: JsonRecord): boolean {
  return Object.entries(expected).every(([key, value]) => valueMatches(observed[key], value))
}

function scoreWorkflowResponse(
  task: WorkflowTask,
  response: JsonRecord,
  inspectionCalls: number,
): Omit<CaseResult, 'task_id' | 'repeat' | 'layer' | 'latency_seconds' | 'model_calls'> {
  const outcome = response.plan !== undefined
    ? 'draft_ready'
    : typeof response.outcome === 'string' ? response.outcome : ''
  const routeOk = responseRoute(response) === task.expected_route
  const outcomeOk = outcome === task.expected_outcome
  const items = compiledItems(response)
  const observedProfiles = items.map((item) => text(item.profile_id, 'profile_id')).sort()
  const expectedProfiles = [...(task.expected_profiles ?? [])].sort()
  const profilesOk = expectedProfiles.length === 0
    || JSON.stringify(observedProfiles) === JSON.stringify(expectedProfiles)

  const bindingPairs: [string, string][] = []
  for (const item of items) {
    const namesById = new Map<string, string>()
    for (const rawField of array(item.resolved_fields, 'resolved_fields')) {
      const field = record(rawField, 'resolved field')
      namesById.set(text(field.field_id, 'field_id'), text(field.name, 'field name'))
    }
    for (const rawBinding of array(item.bindings, 'bindings')) {
      const binding = record(rawBinding, 'binding')
      bindingPairs.push([
        text(binding.role, 'binding role'),
        namesById.get(text(binding.field_id, 'binding field_id')) ?? '',
      ])
    }
  }
  const expectedBindings = Object.entries(task.expected_bindings ?? {})
  const bindingsMatched = expectedBindings.filter(([role, name]) =>
    bindingPairs.some(([observedRole, observedName]) => observedRole === role && observedName === name)).length

  const visualActions = items.flatMap((item) =>
    array(item.visual_actions, 'visual_actions').map((action) => record(action, 'visual action')))
  const expectedVisuals = task.expected_visual_actions ?? []
  const visualMatched = expectedVisuals.filter((expected) =>
    visualActions.some((observed) => subsetMatches(observed, expected))).length

  const operations = items.flatMap((item) =>
    array(item.data_operations, 'data_operations').map((operation) =>
      text(record(operation, 'data operation').operation, 'data operation name')))
  const expectedOperations = task.expected_data_operations ?? []
  const operationsMatched = expectedOperations.filter((expected) => operations.includes(expected)).length
  const inspectionOk = task.require_inspection !== true || inspectionCalls > 0
  const passed = outcomeOk
    && routeOk
    && profilesOk
    && bindingsMatched === expectedBindings.length
    && visualMatched === expectedVisuals.length
    && operationsMatched === expectedOperations.length
    && inspectionOk
  return {
    passed,
    route_ok: routeOk,
    validator_ok: task.expected_outcome !== 'draft_ready' || outcome === 'draft_ready',
    bindings_expected: expectedBindings.length,
    bindings_matched: bindingsMatched,
    visual_expected: expectedVisuals.length,
    visual_matched: visualMatched,
    data_operations_expected: expectedOperations.length,
    data_operations_matched: operationsMatched,
    inspection_required: task.require_inspection === true,
    inspection_calls: inspectionCalls,
    failure: passed ? undefined : `outcome=${outcome}; route=${responseRoute(response)}; profiles=${observedProfiles.join(',')}`,
  }
}

async function createSetupPlot(
  harness: EvalHarness,
  projectId: string,
  revision: number,
  dataset: ImportedDataset,
  profileId: string,
): Promise<{ plotId: string; revision: number }> {
  const prepared = record(await harness.agent.run({
    projectId,
    expectedProjectVersion: revision,
    instruction: `用 ${profileId} 绘制这张表`,
    selectedSources: selectedSources([dataset]),
    selectedProfileIds: [profileId],
  }), 'setup workflow')
  const plan = record(prepared.plan, 'setup plan')
  const planId = text(plan.plan_id, 'setup plan id')
  await harness.agent.confirm({ projectId, planId })
  const completed = record(await harness.agent.execute({ projectId, planId }), 'setup plan run')
  const task = record(completed.task, 'setup task')
  const progress = record(array(task.items, 'setup progress')[0], 'setup item progress')
  return {
    plotId: text(progress.output_plot_id, 'setup plot id'),
    revision: integer(task.project_revision, 'setup revision'),
  }
}

async function runWorkflowCase(
  harness: EvalHarness,
  task: WorkflowTask,
  repeat: number,
  fixturePaths: Record<string, string>,
): Promise<CaseResult> {
  const runKey = `${task.task_id}.r${repeat}`
  harness.activeRunKey = runKey
  const started = performance.now()
  try {
    const project = await createProject(harness, runKey)
    const imported = await importFixtures(
      harness, project.projectId, project.revision, task.fixture_keys, fixturePaths,
    )
    let revision = imported.revision
    let plotIds: string[] = []
    if (task.setup_plot_profile !== undefined) {
      const setup = await createSetupPlot(
        harness, project.projectId, revision, imported.datasets[0], task.setup_plot_profile,
      )
      revision = setup.revision
      plotIds = [setup.plotId]
    }
    const before = record(await harness.core.request('projects.open', {
      project_id: project.projectId,
    }), 'project before workflow')
    const beforeRevision = integer(before.project_version, 'before revision')
    const response = record(await harness.agent.run({
      projectId: project.projectId,
      selectedSources: plotIds.length === 0 ? selectedSources(imported.datasets) : [],
      selectedProfileIds: task.selected_profile_ids,
      selectedPlotIds: plotIds,
      expectedProjectVersion: revision,
      instruction: task.instruction,
    }), 'Agent response')
    const after = record(await harness.core.request('projects.open', {
      project_id: project.projectId,
    }), 'project after workflow')
    const noSideEffect = integer(after.project_version, 'after revision') === beforeRevision
    const scored = scoreWorkflowResponse(
      task,
      response,
      harness.calls(runKey, 'agent.tools.invoke'),
    )
    return {
      task_id: task.task_id,
      repeat,
      layer: 'workflow',
      latency_seconds: (performance.now() - started) / 1000,
      model_calls: harness.modelCalls(runKey),
      confirmation_no_side_effect: noSideEffect,
      ...scored,
      passed: scored.passed && noSideEffect,
    }
  } catch (error) {
    return {
      task_id: task.task_id,
      repeat,
      layer: 'workflow',
      passed: false,
      latency_seconds: (performance.now() - started) / 1000,
      model_calls: harness.modelCalls(runKey),
      confirmation_no_side_effect: false,
      failure: error instanceof Error ? error.message : String(error),
    }
  }
}

async function agentPlan(
  harness: EvalHarness,
  key: string,
  fixturePaths: Record<string, string>,
): Promise<{
  projectId: string
  revision: number
  dataset: ImportedDataset
  planId: string
}> {
  const project = await createProject(harness, key)
  const imported = await importFixtures(harness, project.projectId, 0, ['xy'], fixturePaths)
  const prepared = record(await harness.agent.run({
    projectId: project.projectId,
    expectedProjectVersion: imported.revision,
    instruction: '用 K01 折线图绘制这张表',
    selectedSources: selectedSources([imported.datasets[0]]),
    selectedProfileIds: ['K01'],
  }), 'runtime prepare')
  const plan = record(prepared.plan, 'runtime plan')
  return {
    projectId: project.projectId,
    revision: imported.revision,
    dataset: imported.datasets[0],
    planId: text(plan.plan_id, 'runtime plan id'),
  }
}

async function plotCount(harness: EvalHarness, projectId: string): Promise<number> {
  const listed = record(await harness.core.request('engine.plots.list', {
    project_id: projectId,
  }), 'plot list')
  return array(listed.plots, 'plots').length
}

async function runRuntimeScenario(
  harness: EvalHarness,
  task: RuntimeTask,
  repeat: number,
  fixturePaths: Record<string, string>,
): Promise<CaseResult> {
  const runKey = `${task.task_id}.r${repeat}`
  harness.activeRunKey = runKey
  const started = performance.now()
  try {
    const setup = await agentPlan(harness, runKey, fixturePaths)
    let passed = false
    if (task.scenario === 'confirmation_no_side_effect') {
      passed = await plotCount(harness, setup.projectId) === 0
    } else if (task.scenario === 'confirmed_plan_executes') {
      await harness.agent.confirm({ projectId: setup.projectId, planId: setup.planId })
      const completed = record(await harness.agent.execute({
        projectId: setup.projectId,
        planId: setup.planId,
      }), 'completed plan')
      const checkpoint = record(completed.task, 'completed task')
      passed = checkpoint.state === 'completed_verified'
        && await plotCount(harness, setup.projectId) === 1
    } else if (task.scenario === 'rejected_plan_no_side_effect') {
      const rejected = record(await harness.agent.reject({
        projectId: setup.projectId,
        planId: setup.planId,
      }), 'rejected plan')
      const checkpoint = record(rejected.task, 'rejected task')
      passed = checkpoint.state === 'rejected'
        && await plotCount(harness, setup.projectId) === 0
    } else if (task.scenario === 'stale_plan_rejected') {
      await importFixtures(harness, setup.projectId, setup.revision, ['xy_second'], fixturePaths)
      try {
        await harness.agent.confirm({ projectId: setup.projectId, planId: setup.planId })
        const completed = record(await harness.agent.execute({
          projectId: setup.projectId,
          planId: setup.planId,
        }), 'stale plan result')
        const checkpoint = record(completed.task, 'stale task')
        passed = checkpoint.state !== 'completed_verified'
          && await plotCount(harness, setup.projectId) === 0
      } catch {
        passed = await plotCount(harness, setup.projectId) === 0
      }
    } else if (task.scenario === 'recipe_replay') {
      const python = join(REPOSITORY, '.venv', 'Scripts', 'python.exe')
      execFileSync(python, [
        '-m', 'pytest', '-q',
        'tests/desktop_core/test_application.py::test_agent_v2_preserves_successful_items_when_one_batch_item_fails',
      ], {
        cwd: REPOSITORY,
        encoding: 'utf8',
        env: { ...process.env, PYTHONPATH: join(REPOSITORY, 'src') },
      })
      passed = true
    } else if (task.scenario === 'restart_recovers_plan') {
      await harness.core.stop()
      harness.core.start()
      await waitUntilReady(harness.core)
      const recovered = record(await harness.agent.get({
        projectId: setup.projectId,
        planId: setup.planId,
      }), 'recovered plan')
      const checkpoint = record(recovered.task, 'recovered task')
      passed = checkpoint.state === 'awaiting_confirmation'
    } else {
      throw new Error(`unknown runtime scenario ${task.scenario}`)
    }
    return {
      task_id: task.task_id,
      repeat,
      layer: 'runtime',
      passed,
      latency_seconds: (performance.now() - started) / 1000,
      model_calls: 0,
      confirmation_no_side_effect: task.scenario.includes('no_side_effect') ? passed : undefined,
      failure: passed ? undefined : `runtime scenario failed: ${task.scenario}`,
    }
  } catch (error) {
    return {
      task_id: task.task_id,
      repeat,
      layer: 'runtime',
      passed: false,
      latency_seconds: (performance.now() - started) / 1000,
      model_calls: 0,
      failure: error instanceof Error ? error.message : String(error),
    }
  }
}

function ratio(numerator: number, denominator: number): number {
  return denominator === 0 ? 1 : numerator / denominator
}

function aggregate(taskSetValue: TaskSet, results: CaseResult[], usage: UsageRecord[]): JsonRecord {
  const workflow = results.filter((result) => result.layer === 'workflow')
  const runtime = results.filter((result) => result.layer === 'runtime')
  const validators = workflow.filter((result) => result.validator_ok !== undefined)
  const bindingsExpected = workflow.reduce((sum, result) => sum + (result.bindings_expected ?? 0), 0)
  const bindingsMatched = workflow.reduce((sum, result) => sum + (result.bindings_matched ?? 0), 0)
  const visualsExpected = workflow.reduce((sum, result) => sum + (result.visual_expected ?? 0), 0)
  const visualsMatched = workflow.reduce((sum, result) => sum + (result.visual_matched ?? 0), 0)
  const dataExpected = workflow.reduce((sum, result) => sum + (result.data_operations_expected ?? 0), 0)
  const dataMatched = workflow.reduce((sum, result) => sum + (result.data_operations_matched ?? 0), 0)
  const inspections = workflow.filter((result) => result.inspection_required)
  const modelCases = workflow.filter((result) => result.model_calls > 0 || result.failure !== undefined)
  const modelErrors = modelCases.filter((result) => result.failure !== undefined && result.model_calls > 0)
  const confirmationCases = workflow.filter((result) => result.confirmation_no_side_effect !== undefined)
  const modelLatencies = workflow.filter((result) => result.model_calls > 0).map((result) => result.latency_seconds)
  const totals = usage.reduce((accumulator, item) => {
    accumulator.input += item.usage.input
    accumulator.output += item.usage.output
    accumulator.cacheRead += item.usage.cacheRead
    accumulator.cacheWrite += item.usage.cacheWrite
    return accumulator
  }, { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 })
  const price = taskSetValue.pricing_cny_per_million_tokens
  const cacheMiss = Math.max(0, totals.input - totals.cacheRead)
  const estimatedCost = (
    totals.cacheRead * price.input_cache_hit
    + cacheMiss * price.input_cache_miss
    + totals.output * price.output
  ) / 1_000_000
  return {
    task_exact_rate: ratio(results.filter((result) => result.passed).length, results.length),
    local_validator_accept_rate: ratio(validators.filter((result) => result.validator_ok).length, validators.length),
    route_accuracy: ratio(workflow.filter((result) => result.route_ok).length, workflow.length),
    binding_accuracy: ratio(bindingsMatched, bindingsExpected),
    visual_action_accuracy: ratio(visualsMatched, visualsExpected),
    data_operation_accuracy: ratio(dataMatched, dataExpected),
    required_inspection_rate: ratio(inspections.filter((result) => (result.inspection_calls ?? 0) > 0).length, inspections.length),
    runtime_success_rate: ratio(runtime.filter((result) => result.passed).length, runtime.length),
    confirmation_no_side_effect_rate: ratio(confirmationCases.filter((result) => result.confirmation_no_side_effect).length, confirmationCases.length),
    model_error_rate: ratio(modelErrors.length, modelCases.length),
    latency_median_seconds: percentile(modelLatencies, 0.5),
    latency_p95_seconds: percentile(modelLatencies, 0.95),
    latency_max_seconds: percentile(modelLatencies, 1),
    model_calls: usage.length,
    input_tokens: totals.input,
    input_cache_hit_tokens: totals.cacheRead,
    input_cache_miss_tokens: cacheMiss,
    output_tokens: totals.output,
    estimated_cost_cny: estimatedCost,
  }
}

function qualification(taskSetValue: TaskSet, metrics: JsonRecord): { decision: 'GO' | 'NO_GO'; failures: string[] } {
  const failures: string[] = []
  for (const [name, threshold] of Object.entries(taskSetValue.thresholds)) {
    const maximum = name.endsWith('_max')
    const metricName = maximum ? name.slice(0, -4) : name
    const value = metrics[metricName]
    if (typeof value !== 'number' || (maximum ? value > threshold : value < threshold)) {
      failures.push(`${metricName}=${String(value)} ${maximum ? '>' : '<'} ${threshold}`)
    }
  }
  return { decision: failures.length === 0 ? 'GO' : 'NO_GO', failures }
}

function renderRawReport(
  metadata: JsonRecord,
  metrics: JsonRecord,
  decision: { decision: 'GO' | 'NO_GO'; failures: string[] },
  results: CaseResult[],
): string {
  const failed = results.filter((result) => !result.passed)
  const rows = Object.entries(metrics).map(([name, value]) => `| ${name} | ${typeof value === 'number' ? value.toFixed(6) : value} |`).join('\n')
  const failures = failed.length === 0
    ? '无。'
    : failed.map((result) => `- ${result.task_id}.r${result.repeat}: ${result.failure ?? 'score mismatch'}`).join('\n')
  return `# Agent Foundation P10 原始评测结果\n\n` +
    `- 决策：**${decision.decision}**\n` +
    `- HEAD：\`${metadata.git_commit}\`\n` +
    `- E3 真实模型：18 × 3；E2 运行时：6 × 1；总执行：${metadata.execution_count}\n` +
    `- 评测器：${metadata.schema_version}\n` +
    `- 冻结任务 SHA-256：\`${metadata.task_set_sha256}\`\n\n` +
    `## 指标\n\n| 指标 | 值 |\n|---|---:|\n${rows}\n\n` +
    `## 阈值失败\n\n${decision.failures.length === 0 ? '无。' : decision.failures.map((item) => `- ${item}`).join('\n')}\n\n` +
    `## 失败样例\n\n${failures}\n`
}

async function main(): Promise<void> {
  const tasks = taskSet()
  const debugIds = new Set(
    (process.env.SEQ70_DEBUG_TASKS ?? '').split(',').map((item) => item.trim()).filter(Boolean),
  )
  const debug = debugIds.size > 0
  if (!debug && (tasks.tasks.length !== 24 || tasks.repeats !== 3)) {
    throw new Error('SEQ-70 task set must be frozen at 24 tasks × 3 repeats')
  }
  const executionTasks = debug
    ? tasks.tasks.filter((task) => debugIds.has(task.task_id))
    : tasks.tasks
  if (executionTasks.length === 0) throw new Error('SEQ-70 debug task filter matched no tasks')
  const repeats = debug ? 1 : tasks.repeats
  const providerCatalog = join(process.env.LOCALAPPDATA ?? '', 'PlotAgent', 'catalog.sqlite3')
  if (!existsSync(providerCatalog)) throw new Error(`provider catalog is missing: ${providerCatalog}`)
  const gitCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: REPOSITORY, encoding: 'utf8' }).trim()
  const status = execFileSync(
    'git',
    ['status', '--porcelain', '--untracked-files=no'],
    { cwd: REPOSITORY, encoding: 'utf8' },
  ).trim()
  if (status.length !== 0) throw new Error('SEQ-70 requires a clean frozen worktree')
  const stamp = new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14)
  const outputRoot = join(REPOSITORY, 'build', 'seq70-workflow-eval', `${stamp}-${gitCommit.slice(0, 7)}`)
  const runtimeRoot = join(tmpdir(), `plotagent-seq70-${randomUUID()}`)
  mkdirSync(outputRoot, { recursive: true })
  mkdirSync(runtimeRoot, { recursive: true })
  const fixturePaths = writeFixtures(runtimeRoot)
  const harness = new EvalHarness(join(runtimeRoot, 'app'), providerCatalog)
  const results: CaseResult[] = []
  try {
    await harness.start()
    for (let repeat = 1; repeat <= repeats; repeat += 1) {
      for (const task of executionTasks) {
        if (!debug && task.layer === 'runtime' && repeat > 1) continue
        const result = task.layer === 'workflow'
          ? await runWorkflowCase(harness, task, repeat, fixturePaths)
          : await runRuntimeScenario(harness, task, repeat, fixturePaths)
        results.push(result)
        process.stdout.write(`${result.passed ? 'PASS' : 'FAIL'} ${task.task_id}.r${repeat} ${result.latency_seconds.toFixed(3)}s\n`)
      }
    }
  } finally {
    await harness.stop()
  }
  const metrics = aggregate(tasks, results, harness.usage)
  const gate = qualification(tasks, metrics)
  const metadata: JsonRecord = {
    schema_version: 'agent-foundation-eval-raw-v1',
    git_commit: gitCommit,
    task_set_sha256: sha256(TASK_SET_PATH),
    task_count: executionTasks.length,
    repeats,
    execution_count: results.length,
    debug_task_filter: debug ? [...debugIds] : [],
    generated_at: new Date().toISOString(),
  }
  const report = {
    metadata,
    thresholds: tasks.thresholds,
    metrics,
    qualification: gate,
    results,
  }
  const rawPath = join(outputRoot, 'raw-results.json')
  writeFileSync(rawPath, JSON.stringify(report, null, 2), 'utf8')
  const markdown = renderRawReport(metadata, metrics, gate, results)
  writeFileSync(join(outputRoot, 'RAW-REPORT.md'), markdown, 'utf8')
  if (debug) {
    process.stdout.write(`AGENT_FOUNDATION_DEBUG_${gate.decision} ${outputRoot}\n`)
    if (gate.decision !== 'GO') process.exitCode = 1
    return
  }
  if (gate.decision !== 'GO') {
    process.stdout.write(`AGENT_FOUNDATION_RAW_NO_GO ${outputRoot}\n`)
    process.exitCode = 1
    return
  }
  const python = join(REPOSITORY, '.venv', 'Scripts', 'python.exe')
  execFileSync(python, [
    join(REPOSITORY, 'scripts', 'finalize_agent_foundation_eval.py'),
    '--raw', rawPath,
    '--output', outputRoot,
    '--repository', REPOSITORY,
  ], {
    cwd: REPOSITORY,
    stdio: 'inherit',
    env: { ...process.env, PYTHONPATH: join(REPOSITORY, 'src') },
  })
}

void main().catch((error: unknown) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`)
  process.exitCode = 1
})
