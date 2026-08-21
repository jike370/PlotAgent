import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  DESKTOP_API_VERSION,
  type CoreStatus,
  type DesktopActionResult,
  type DesktopBootstrap,
  type DesktopDataResult,
  type JsonValue,
  type PlotAgentDesktopApi,
  type TaskEvent,
} from '../../shared/desktop-contract'
import { App } from './App'
import { suggestedFieldMapping } from './components/mappingSuggestions'

const ok = (value: JsonValue): DesktopDataResult => ({ ok: true, value })
const actionOk = async (): Promise<DesktopActionResult> => ({ ok: true })
const readyBootstrap = async (): Promise<DesktopBootstrap> => ({
  apiVersion: DESKTOP_API_VERSION,
  platform: 'win32',
  core: { phase: 'ready', restartAttempt: 0 },
  tasks: { tasks: [], activeTaskCount: 0, hasCommittingTask: false },
})

const dataset = {
  source_dataset_id: 'source:temperature',
  source_version: 1,
  content_hash: 'a'.repeat(64),
  row_count: 12,
  field_count: 3,
  fields: [
    { field_id: 'field:time', name: 'time_min', logical_type: 'numeric', physical_type: 'float64', unit: { source_text: 'min', canonical_unit: null, dimensionality: 'opaque', kind: 'opaque', registry_version: 'units.v1' } },
    { field_id: 'field:signal', name: 'fluorescence_au', logical_type: 'numeric', physical_type: 'float64', unit: { source_text: 'a.u.', canonical_unit: null, dimensionality: 'opaque', kind: 'opaque', registry_version: 'units.v1' } },
    { field_id: 'field:condition', name: 'condition', logical_type: 'categorical', physical_type: 'string', unit: null },
  ],
  sample_rows: [
    [1, 3.2, 'Control'],
    [2, 3.9, 'Control'],
    [3, 4.8, 'Treatment'],
    [4, 5.4, 'Treatment'],
    [5, 6.1, 'Treatment'],
  ],
  quality: { missing_count: 0, nonfinite_count: 0 },
  source_coordinate_kinds: ['text_row'],
}

const secondDataset = {
  ...dataset,
  source_dataset_id: 'source:pressure',
  source_file_name: 'pressure.csv',
  content_hash: 'c'.repeat(64),
  fields: dataset.fields.map((field) => ({
    ...field,
    field_id: field.field_id.replace('field:', 'field:pressure.'),
  })),
  sample_rows: [
    [10, 101.2, 'Baseline'],
    [20, 103.8, 'Baseline'],
    [30, 108.4, 'Stimulated'],
  ],
}

function enginePlotFixture(
  plotId = 'plot:one',
  plotVersion = 1,
  profileId = 'K01',
  projectVersion = plotVersion + 1,
  actions: JsonValue[] = [],
): JsonValue {
  const token = plotId.replace(/^plot:/, '')
  return {
    project_id: 'project:test',
    project_version: projectVersion,
    plot_id: plotId,
    plot_version: plotVersion,
    profile_id: profileId,
    plot_ref: {
      plot_id: plotId,
      plot_version: plotVersion,
      content_hash: 'b'.repeat(64),
    },
    document: {
      schema_version: '2.0', plot_id: plotId, plot_version: plotVersion,
      parent_version: plotVersion === 1 ? null : plotVersion - 1,
      profile_id: profileId,
      data: { kind: 'source', dataset_id: 'source:temperature', version: 1, content_hash: 'a'.repeat(64) },
      bindings: [{ role: 'x', field_id: 'field:time' }, { role: 'y', field_id: 'field:signal' }],
      applied_action_ids: actions.map((_, index) => `action:test.${index + 1}`),
    },
    actions,
    profile: {
      profile_id: profileId,
      objects: [
        { object_alias: 'x_axis', object_kind: 'axis', object_key: 'x' },
        { object_alias: 'y_axis', object_kind: 'axis', object_key: 'y' },
        { object_alias: 'series_1', object_kind: 'series', object_key: 'primary' },
        { object_alias: 'legend', object_kind: 'legend', object_key: 'main' },
      ],
      capabilities: [
        { operation: 'set_title', parameters: ['text'] },
        { operation: 'set_axis', parameters: ['label', 'scale', 'bounds', 'reverse'] },
        {
          operation: 'set_series_style',
          parameters: ['line_stroke_color', 'line_width_pt', 'line_style'],
        },
        { operation: 'set_legend', parameters: ['visible', 'anchor'] },
      ],
    },
    readback: { objects: [{ semantic_id: `series:${token}.primary` }] },
    preview: { resourceId: 'resource:preview', kind: 'preview', url: 'plotagent-resource://local/00000000-0000-0000-0000-000000000001', mimeType: 'image/png' },
  }
}

function workflowPlanFixture(
  state = 'awaiting_confirmation',
  stepState = state === 'succeeded' ? 'succeeded' : 'pending',
  options: {
    planId?: string
    plotVersion?: number
    failure?: {
      code: string
      message: string
      retryable: boolean
      category?: string
      requiresUser?: boolean
      sideEffectState?: string
    }
  } = {},
): JsonValue {
  const planId = options.planId ?? 'plan:one'
  const plotVersion = options.plotVersion
  const planState = state === 'needs_confirmation' ? 'awaiting_confirmation'
    : state === 'partially_failed' ? 'partially_succeeded' : state
  const progressState = stepState === 'ready' ? 'pending'
    : stepState === 'stale' ? 'failed' : stepState
  return {
    task_id: 'task:workflow:test',
    task_version: 3,
    plan: {
      schema_version: 'task-plan.v1',
      plan_id: planId,
      workflow_run_id: 'workflow:test',
      draft_hash: 'd'.repeat(64),
      expected_project_revision: 2,
      items: [{
        task_kind: 'edit',
        item_id: 'item:one',
        plot_alias: 'plot',
        plot_id: 'plot:one',
        profile_id: 'K01',
        target_plot_id: 'plot:one',
        target_plot_version: plotVersion === undefined ? 1 : Math.max(1, plotVersion - 1),
        sources: [],
        resolved_fields: [],
        data_operations: [],
        bindings: [],
        visual_actions: [{ operation: 'set_title', target_alias: 'plot', text: '更新后的标题' }],
        depends_on: [],
        idempotency_key: 'workflow:test:item:one',
      }],
    },
    state: planState,
    current_project_revision: 2,
    item_progress: [{
      item_id: 'item:one',
      state: progressState,
      attempt_count: progressState === 'pending' ? 0 : 1,
      ...(options.failure === undefined ? {} : {
        error_code: options.failure.code,
        error_message: options.failure.message,
        error_retryable: options.failure.retryable,
        ...(options.failure.category === undefined ? {} : {
          last_error: {
            code: options.failure.code,
            message: options.failure.message,
            retryable: options.failure.retryable,
            category: options.failure.category,
            requires_user: options.failure.requiresUser ?? false,
            side_effect_state: options.failure.sideEffectState ?? 'unknown',
          },
        }),
      }),
      ...(plotVersion === undefined ? {} : { output_plot_id: 'plot:one', output_plot_version: plotVersion }),
    }],
    created_at: '2026-08-16T00:00:00Z',
    updated_at: '2026-08-16T00:00:00Z',
  }
}

function workflowResultWithPlan(plan: JsonValue): JsonValue {
  return {
    outcome: 'draft_ready',
    task_plan: plan,
  }
}

function batchPlanFixture(state = 'awaiting_confirmation'): JsonValue {
  const planState = state === 'needs_confirmation' ? 'awaiting_confirmation' : state
  return {
    plan: {
      schema_version: 'task-plan.v1',
      plan_id: 'plan:batch',
      workflow_run_id: 'workflow:batch',
      draft_hash: 'e'.repeat(64),
      expected_project_revision: 2,
      items: [{
        task_kind: 'create',
        item_id: 'item:batch',
        plot_alias: 'plot_1',
        plot_id: 'plot:batch.one',
        profile_id: 'K01',
        sources: [{
          source_alias: 'source_1',
          source_dataset_id: 'source:temperature',
          source_version: 1,
          content_hash: 'a'.repeat(64),
          display_name: 'temperature',
          row_count: 12,
        }],
        resolved_fields: [],
        data_operations: [],
        bindings: [
          { role: 'x', source_alias: 'source_1', field_id: 'field:time' },
          { role: 'y', source_alias: 'source_1', field_id: 'field:signal' },
        ],
        visual_actions: [],
        depends_on: [],
        idempotency_key: 'workflow:batch:item:batch',
      }],
    },
    state: planState,
    current_project_revision: state === 'succeeded' ? 3 : 2,
    item_progress: [{
      item_id: 'item:batch',
      state: state === 'succeeded' ? 'succeeded' : 'pending',
      attempt_count: state === 'succeeded' ? 1 : 0,
      ...(state === 'succeeded' ? { output_plot_id: 'plot:batch.one', output_plot_version: 1 } : {}),
    }],
    created_at: '2026-08-16T00:00:00Z',
    updated_at: '2026-08-16T00:00:00Z',
  }
}

function multiSourceBatchPlanFixture(): JsonValue {
  const payload = structuredClone(batchPlanFixture()) as Record<string, JsonValue>
  const plan = payload.plan as Record<string, JsonValue>
  const items = plan.items as Array<Record<string, JsonValue>>
  const first = items[0]
  plan.items = [
    first,
    {
      ...first,
      item_id: 'item:batch.second',
      plot_alias: 'plot_2',
      plot_id: 'plot:batch.two',
      sources: [{
        source_alias: 'source_2',
        source_dataset_id: 'source:pressure',
        source_version: 1,
        content_hash: 'c'.repeat(64),
        display_name: 'pressure.csv',
        row_count: 12,
      }],
      bindings: [
        { role: 'x', source_alias: 'source_2', field_id: 'field:pressure.time' },
        { role: 'y', source_alias: 'source_2', field_id: 'field:pressure.signal' },
      ],
      idempotency_key: 'workflow:batch:item:batch.second',
    },
  ]
  payload.item_progress = [
    { item_id: 'item:batch', state: 'pending', attempt_count: 0 },
    { item_id: 'item:batch.second', state: 'pending', attempt_count: 0 },
  ]
  return payload
}

function failedCreatePlanFixture(): JsonValue {
  return {
    plan: {
      schema_version: 'task-plan.v1',
      plan_id: 'plan:failed-create',
      workflow_run_id: 'workflow:failed-create',
      draft_hash: 'f'.repeat(64),
      expected_project_revision: 2,
      items: [{
        task_kind: 'create',
        item_id: 'item:failed-k19',
        plot_alias: 'plot_1',
        plot_id: 'plot:failed-k19',
        profile_id: 'K19',
        sources: [{
          source_alias: 'data_2',
          source_dataset_id: 'source:temperature',
          source_version: 1,
          content_hash: 'a'.repeat(64),
          display_name: 'temperature.csv',
          row_count: 12,
        }, {
          source_alias: 'data_3',
          source_dataset_id: 'source:pressure',
          source_version: 1,
          content_hash: 'c'.repeat(64),
          display_name: 'pressure.csv',
          row_count: 12,
        }],
        resolved_fields: [],
        data_operations: [],
        bindings: [
          { role: 'time', source_alias: 'data_3', field_id: 'field:pressure.time' },
          { role: 'series_1', source_alias: 'data_3', field_id: 'field:pressure.signal' },
        ],
        visual_actions: [{ operation: 'set_axis', target_alias: 'y_axis', scale: 'log10' }],
        depends_on: [],
        idempotency_key: 'workflow:failed-create:item:failed-k19',
      }],
    },
    state: 'failed',
    current_project_revision: 2,
    item_progress: [{
      item_id: 'item:failed-k19',
      state: 'failed',
      attempt_count: 1,
      error_code: 'LOG_SCALE_NON_POSITIVE',
      error_message: 'Log10 轴包含 0 或负值。',
      error_retryable: false,
    }],
    created_at: '2026-08-16T00:00:00Z',
    updated_at: '2026-08-16T00:00:00Z',
  }
}

let coreListener: ((status: CoreStatus) => void) | undefined
let taskListener: ((event: TaskEvent) => void) | undefined
let workflowRuntimeListener: Parameters<PlotAgentDesktopApi['onWorkflowRuntimeEvent']>[0] | undefined

function fakeDesktop(overrides: Partial<PlotAgentDesktopApi> = {}): PlotAgentDesktopApi {
  const api: PlotAgentDesktopApi = {
    apiVersion: DESKTOP_API_VERSION,
    getBootstrap: vi.fn(readyBootstrap),
    getTasks: vi.fn(async () => ({ tasks: [], activeTaskCount: 0, hasCommittingTask: false })),
    cancelTask: vi.fn(actionOk),
    acceptPartialTask: vi.fn(actionOk),
    resumeAgentTask: vi.fn(async () => ok(workflowResultWithPlan(workflowPlanFixture()))),
    retryCore: vi.fn(actionOk),
    getProviderStatus: vi.fn(async () => ok({ configured: true, mode: 'custom_provider' })),
    configureCustomProvider: vi.fn(async () => ok({ configured: true, mode: 'custom_provider' })),
    clearProvider: vi.fn(async () => ok({ configured: false, mode: 'local_only' })),
    getOriginStatus: vi.fn(async () => ok({
      status: 'ready',
      display_name: 'OriginPro',
      display_version: '2025b',
      discovery_source: 'portable',
    })),
    listProjects: vi.fn(async () => ok({ projects: [] })),
    createProject: vi.fn(async () => ok({ project_id: 'project:test', display_name: '新建科研绘图项目', is_open: false })),
    renameProject: vi.fn(async (input) => ok({ project_id: input.projectId, display_name: input.name, is_open: true })),
    deleteProject: vi.fn(async (input) => ok({ project_id: input.projectId, status: 'deleted', cleanup_pending: false })),
    activateProject: vi.fn(async () => ok({ project_id: 'project:test', project_version: 0, status: 'open' })),
    openProject: vi.fn(async () => ok({ project_id: 'project:opened', display_name: '已打开项目', project_version: 2, status: 'open' })),
    openProjectResource: vi.fn(async () => ok({ project_id: 'project:opened', display_name: '已打开项目', project_version: 2, status: 'open' })),
    openExportResource: vi.fn(actionOk),
    revealExportResource: vi.fn(actionOk),
    openSampleProject: vi.fn(async () => ok({
      project: { project_id: 'project:sample', display_name: '温度响应示例', is_open: false },
      opened: { project_id: 'project:sample', project_version: 0, status: 'open' },
      imported: { kind: 'committed', project_version: 1, datasets: [dataset] },
    })),
    closeProject: vi.fn(async () => ok({ status: 'closed' })),
    importDatasets: vi.fn(async () => ok({ imports: [{ kind: 'committed', project_version: 1, datasets: [dataset] }], project_version: 1 })),
    listDatasets: vi.fn(async () => ok({ project_id: 'project:test', project_version: 1, datasets: [dataset] })),
    describeDataset: vi.fn(async () => ok({ dataset })),
    executePlotAction: vi.fn(async (input) => {
      const action = input.action as Record<string, JsonValue>
      return ok(enginePlotFixture(
        typeof action.plot_id === 'string' ? action.plot_id : 'plot:one',
        action.operation === 'create_plot' ? 1 : 2,
        typeof action.profile_id === 'string' ? action.profile_id : 'K01',
        action.operation === 'create_plot' ? 2 : 3,
        [input.action],
      ))
    }),
    getPlot: vi.fn(async (input) => ok(enginePlotFixture(input.plotId, input.plotVersion))),
    listPlots: vi.fn(async () => ok({ project_version: 1, plots: [] })),
    runWorkflow: vi.fn(async () => ok(workflowResultWithPlan(workflowPlanFixture()))),
    getTaskPlan: vi.fn(async () => ok({})),
    listTaskPlans: vi.fn(async () => ok({ task_plans: [] })),
    confirmTaskPlan: vi.fn(async () => ok(workflowPlanFixture('ready', 'ready'))),
    runTaskPlan: vi.fn(async () => ok({ task_plan: workflowPlanFixture('succeeded', 'succeeded', { plotVersion: 2 }) })),
    resumeTaskPlan: vi.fn(async () => ok({ task_plan: workflowPlanFixture('succeeded', 'succeeded', { plotVersion: 2 }) })),
    exportPngSvg: vi.fn(async (input) => ok({ export_id: 'export:one', plot_id: input.target.id, plot_version: input.target.version, artifact: { resource: { resourceId: 'resource:export', kind: 'export', fileName: `plot.${input.format}` }, content_hash: 'a'.repeat(64), size: 1_024 } })),
    exportOrigin: vi.fn(async (input) => ok({ export_id: 'export:origin', plot_id: input.target.id, plot_version: input.target.version, artifact: { resource: { resourceId: 'resource:origin', kind: 'export', fileName: 'plot.opju' }, content_hash: 'b'.repeat(64), size: 29_999 } })),
    respondToCloseRequest: vi.fn(actionOk),
    onCoreStatus: vi.fn((listener) => { coreListener = listener; return () => { coreListener = undefined } }),
    onTaskEvent: vi.fn((listener) => { taskListener = listener; return () => { taskListener = undefined } }),
    onWorkflowRuntimeEvent: vi.fn((listener) => {
      workflowRuntimeListener = listener
      return () => { workflowRuntimeListener = undefined }
    }),
    onOpenResourceRequested: vi.fn(() => () => undefined),
    onCloseRequested: vi.fn(() => () => undefined),
    ...overrides,
  }
  return api
}

function installApi(api: PlotAgentDesktopApi): void {
  Object.defineProperty(window, 'plotAgentDesktop', { value: api, configurable: true })
}

async function openSampleAndCreatePlot(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.click(await screen.findByRole('button', { name: '示例' }))
  expect(await screen.findByText('source:temperature')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '选择图形' }))
  await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K01')
  await user.click(screen.getByRole('button', { name: /K01.*折线图/ }))
  await user.click(screen.getByRole('button', { name: '选择此图形' }))
  await user.click(screen.getByRole('button', { name: '字段绑定' }))
  await user.click(screen.getByRole('button', { name: '确认并绘图' }))
  expect(await screen.findByRole('img', { name: '折线图 真实渲染预览' })).toHaveAttribute('src', expect.stringMatching(/^plotagent-resource:/))
  expect(screen.getByText('绘图完成')).toHaveClass('composer-success')
}

beforeEach(() => {
  coreListener = undefined
  workflowRuntimeListener = undefined
  taskListener = undefined
  window.localStorage.clear()
  installApi(fakeDesktop())
})

describe('PlotAgent real desktop workflow', () => {
  it('loads persisted projects after the Core becomes ready', async () => {
    let coreReady = false
    const api = fakeDesktop({
      getBootstrap: vi.fn(async (): Promise<DesktopBootstrap> => ({
        apiVersion: DESKTOP_API_VERSION,
        platform: 'win32',
        core: { phase: 'starting', restartAttempt: 0 },
        tasks: { tasks: [], activeTaskCount: 0, hasCommittingTask: false },
      })),
      listProjects: vi.fn(async (): Promise<DesktopDataResult> => coreReady
        ? ok({ projects: [{ project_id: 'project:persisted', display_name: '跨重启项目', is_open: false }] })
        : { ok: false, error: { code: 'CORE_NOT_READY', message: 'Core 尚未就绪', retryable: true } }),
    })
    installApi(api)
    render(<App />)

    await waitFor(() => expect(coreListener).toBeDefined())
    expect(screen.queryByRole('button', { name: '跨重启项目' })).not.toBeInTheDocument()
    await act(async () => {
      coreReady = true
      coreListener?.({ phase: 'ready', restartAttempt: 0 })
    })

    expect(await screen.findByRole('button', { name: '跨重启项目' })).toBeInTheDocument()
    expect(api.listProjects).toHaveBeenCalledTimes(1)
  })

  it('starts with three local entry points and no account or invitation gate', async () => {
    render(<App />)
  expect(await screen.findByRole('region', { name: '开始使用 PlotAgent' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '示例' })).toBeEnabled()
    expect(screen.getByRole('button', { name: /^导入/ })).toBeEnabled()
    expect(screen.getByRole('button', { name: '打开已有 .plotproj' })).toBeEnabled()
    expect(screen.getByText(/无需账号/)).toBeInTheDocument()
    expect(screen.queryByText(/邀请已激活/)).not.toBeInTheDocument()
  })

  it('keeps task and chart-library secondary surfaces concise', async () => {
    const user = userEvent.setup()
    render(<App />)

    await screen.findByRole('region', { name: '开始使用 PlotAgent' })
    await user.click(screen.getByRole('button', { name: /任务中心/ }))
    const taskDialog = screen.getByRole('dialog', { name: '任务中心' })
    expect(within(taskDialog).getByText('当前没有进行中的任务')).toBeInTheDocument()
    expect(within(taskDialog).queryByText('来自本地 Core 的任务事件')).not.toBeInTheDocument()
    expect(within(taskDialog).queryByText(/导入、渲染和导出时/)).not.toBeInTheDocument()
    expect(within(taskDialog).queryByText(/关闭窗口前/)).not.toBeInTheDocument()
    await user.click(within(taskDialog).getByRole('button', { name: '关闭任务中心' }))

    await user.click(screen.getByRole('button', { name: /新建项目/ }))
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    const library = screen.getByRole('dialog', { name: '图形库' })
    const detail = within(library).getByRole('complementary', { name: '线点图详情' })
    expect(within(library).queryByText(/首轮正式目标/)).not.toBeInTheDocument()
    expect(within(detail).queryByText('同时呈现实测点与连接趋势')).not.toBeInTheDocument()
    expect(within(detail).queryByText(/可在 Origin 中继续编辑/)).not.toBeInTheDocument()
    expect(within(detail).queryByText(/选择后将写入稳定类型/)).not.toBeInTheDocument()
    expect(within(detail).getByText('批量模式')).toBeInTheDocument()
    expect(within(detail).getByText('布局结构')).toBeInTheDocument()
    expect(within(library).getAllByText('直接批量')).toHaveLength(1)
    const k01Card = within(library).getByRole('button', { name: 'K01 折线图' })
    expect(k01Card).not.toHaveAttribute('aria-pressed')
    k01Card.focus()
    await user.keyboard('{Enter}')
    expect(k01Card).toHaveAttribute('aria-current', 'true')
  })

  it('provides a development-only interactive browser preview without a desktop bridge', async () => {
    const user = userEvent.setup()
    Reflect.deleteProperty(window, 'plotAgentDesktop')
    render(<App />)

    expect(screen.getByText('PlotAgent · 开发预览')).toBeInTheDocument()
    const sampleButton = screen.getByRole('button', { name: '示例' })
    await waitFor(() => expect(sampleButton).toBeEnabled())
    await user.click(sampleButton)

    expect(await screen.findByRole('heading', { name: '示例数据.xlsx > Sheet 1' })).toBeInTheDocument()
    expect(screen.getByText('已导入 3 个数据表。')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K01')
    await user.click(screen.getByRole('button', { name: /K01.*折线图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.click(screen.getByRole('button', { name: '字段绑定' }))
    await user.click(screen.getByRole('button', { name: '确认并绘图' }))

    expect(await screen.findByRole('img', { name: '折线图 界面预览' })).toHaveAttribute('src', expect.stringMatching(/^data:image\/svg\+xml/))
  })

  it('creates and activates a real project from the sidebar action', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop()
    installApi(api)
    render(<App />)

    const createButton = await screen.findByRole('button', { name: /新建项目/ })
    await waitFor(() => expect(createButton).toBeEnabled())
    await user.click(createButton)

    expect(api.createProject).toHaveBeenCalledWith({ name: '新建项目 1' })
    expect(api.activateProject).toHaveBeenCalledWith({ projectId: 'project:test' })
    expect(await screen.findByRole('button', { name: '新建科研绘图项目' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('上传数据文件，并告诉我你想画什么图。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '选择图形' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '上传数据' })).toBeInTheDocument()
  })

  it('keeps no-data Agent requests and guidance in the conversation timeline', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop()
    installApi(api)
    render(<App />)

    await user.click(await screen.findByRole('button', { name: /新建项目/ }))
    await user.type(screen.getByRole('textbox', { name: '描述绘图要求' }), '把标题改成温度响应')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    expect(await screen.findByText('把标题改成温度响应')).toBeInTheDocument()
    expect(await screen.findByText('请先上传数据')).toBeInTheDocument()
    expect(screen.getByText('收到你的要求了。上传数据后，我会继续声明字段绑定。')).toBeInTheDocument()
    expect(api.runWorkflow).not.toHaveBeenCalled()
  })

  it('lets the Agent resolve or clarify the chart when none is selected', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop()
    installApi(api)
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '示例' }))
    await user.type(screen.getByRole('textbox', { name: '描述绘图要求' }), '用这些数据画一张图。')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    await waitFor(() => expect(api.runWorkflow).toHaveBeenCalledWith({
      projectId: 'project:sample',
      selectedSources: [{ datasetId: 'source:temperature', sourceVersion: 1 }],
      expectedProjectVersion: 1,
      instruction: '用这些数据画一张图。',
    }))
  })

  it('lets the user choose a chart before uploading data', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop()
    installApi(api)
    render(<App />)

    await user.click(await screen.findByRole('button', { name: /新建项目/ }))
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K01')
    await user.click(screen.getByRole('button', { name: /K01.*折线图/ }))
    expect(screen.getByText('可先选择图形')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    expect(screen.getByRole('button', { name: '折线图' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '上传数据' }))
    expect(await screen.findByText('K01 · 折线图')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: '当前图形选择' })).not.toBeInTheDocument()
    expect(screen.queryByText('当前图形')).not.toBeInTheDocument()
    expect(screen.queryByText('下一步检查字段与数据样本')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '字段绑定' }))
    expect(screen.getByRole('heading', { name: '数据预览与字段绑定' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '折线图' })).toBeInTheDocument()
  })

  it('keeps a pending task when chart selection answers the Agent question', async () => {
    const user = userEvent.setup()
    const runWorkflow = vi.fn()
      .mockResolvedValueOnce(ok({
        outcome: 'needs_input',
        workflow_run_id: 'task:needs-chart',
        questions: [{
          question_key: 'chart_type',
          prompt: '请选择图类。',
          answer_kind: 'chart_type',
          choices: [],
          required: true,
        }],
      }))
      .mockResolvedValueOnce(ok(workflowResultWithPlan(workflowPlanFixture())))
    installApi(fakeDesktop({ runWorkflow }))
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '示例' }))
    const composer = screen.getByRole('textbox', { name: '描述绘图要求' })
    await user.type(composer, '用这些数据画图。')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))
    expect(await screen.findAllByText('请选择图类。')).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K01')
    await user.click(screen.getByRole('button', { name: /K01.*折线图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.type(composer, '就用这个图类。')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    expect(runWorkflow.mock.calls.at(-1)?.[0]).toMatchObject({
      continuationWorkflowRunId: 'task:needs-chart',
      selectedProfileIds: ['K01'],
      instruction: '就用这个图类。',
    })
  })

  it('opens project actions, renames inline, and deletes only after confirmation', async () => {
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const api = fakeDesktop({
      listProjects: vi.fn(async () => ok({ projects: [{
        project_id: 'project:managed',
        display_name: '原项目',
        is_open: false,
        last_opened_at: '2026-08-07T04:00:00.000Z',
      }] })),
    })
    installApi(api)
    render(<App />)

    const projectButton = await screen.findByRole('button', { name: '原项目' })
    await user.hover(projectButton)
    expect(await screen.findByRole('tooltip')).toHaveTextContent('原项目')

    await user.click(screen.getByRole('button', { name: '项目“原项目”操作' }))
    await user.click(screen.getByRole('menuitem', { name: '置顶项目' }))
    await waitFor(() => expect(window.localStorage.getItem('plotagent.sidebar.pinned-projects')).toContain('project:managed'))

    await user.click(screen.getByRole('button', { name: '项目“原项目”操作' }))
    await user.click(screen.getByRole('menuitem', { name: '重命名' }))
    const renameInput = screen.getByRole('textbox', { name: '重命名项目 原项目' })
    await user.clear(renameInput)
    await user.type(renameInput, '新项目名{Enter}')
    expect(api.renameProject).toHaveBeenCalledWith({ projectId: 'project:managed', name: '新项目名' })
    expect(await screen.findByRole('button', { name: '新项目名' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '项目“新项目名”操作' }))
    await user.click(screen.getByRole('menuitem', { name: '删除项目' }))
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('永久删除'))
    expect(api.deleteProject).toHaveBeenCalledWith({ projectId: 'project:managed' })
    await waitFor(() => expect(projectButton).not.toBeInTheDocument())
    confirm.mockRestore()
  })

  it('opens model service settings from the persistent sidebar entry', async () => {
    const user = userEvent.setup()
    render(<App />)
    expect(await screen.findByText('本地 Core')).toBeInTheDocument()
    expect(screen.getByText('已连接')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Origin 可用，重新检测/ })).toBeInTheDocument()
    const trigger = await screen.findByRole('button', { name: '模型服务 已配置' })
    await user.click(trigger)
    expect(screen.getByRole('dialog', { name: '模型服务' })).toBeInTheDocument()
    expect(screen.queryByText('只在首次使用 Agent 时配置，不影响本地绘图与导出。')).not.toBeInTheDocument()
    expect(screen.queryByText('表单仅用于检查交互，不发送或保存其中内容。')).not.toBeInTheDocument()
    expect(screen.queryByText('提交后只写入系统凭据库，不回显到界面或项目。')).not.toBeInTheDocument()
    expect(screen.getByLabelText('模型厂商')).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: '模型服务' })).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('configures a provider preset without asking for a Base URL or model ID', async () => {
    const user = userEvent.setup()
    const configureCustomProvider = vi.fn(async () => ok({
      configured: true,
      mode: 'custom_provider',
      endpoint_origin: 'https://open.bigmodel.cn/api/paas/v4',
      model_id: 'glm-4.7-flash',
    }))
    installApi(fakeDesktop({
      getProviderStatus: vi.fn(async () => ok({ configured: false, mode: 'local_only' })),
      configureCustomProvider,
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '模型服务 未配置' }))

    expect(screen.getByLabelText('模型厂商')).toHaveValue('zhipu')
    expect(screen.getByLabelText('模型')).toHaveValue('glm-4.7-flash')
    expect(screen.queryByLabelText('Base URL')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Model ID')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('API Key'), 'test-key')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '保存模型服务' }))

    expect(configureCustomProvider).toHaveBeenCalledWith({
      baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
      modelId: 'glm-4.7-flash',
      apiKey: 'test-key',
      retentionAcknowledged: true,
    })
  })

  it('filters local projects with a working clear action', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))
    expect(await screen.findByRole('button', { name: '温度响应示例' })).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: '搜索本机项目' }), '不存在')
    expect(screen.getByText('没有匹配的本机项目')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '清除项目搜索' }))
    expect(screen.getByRole('button', { name: '温度响应示例' })).toBeInTheDocument()
  })

  it('restores and renders the most recently committed plot when a persisted project is activated', async () => {
    const user = userEvent.setup()
    const getPlot = vi.fn(async (input) => ok(
      enginePlotFixture(input.plotId, input.plotVersion, 'K02', 7),
    ))
    const api = fakeDesktop({
      listProjects: vi.fn(async () => ok({
        projects: [
          { project_id: 'project:sample', display_name: '温度响应示例', project_version: 1, is_open: true },
          { project_id: 'project:recovered', display_name: '跨重启项目', project_version: 7, is_open: false },
        ],
      })),
      activateProject: vi.fn(async ({ projectId }) => ok({ project_id: projectId, project_version: 7, status: 'open' })),
      listDatasets: vi.fn(async (): Promise<DesktopDataResult> => ({
        ok: false,
        error: { code: 'IPC_INVALID_ARGUMENT', message: 'Legacy dataset metadata is unavailable.', retryable: false },
      })),
      listPlots: vi.fn(async ({ projectId }) => ok({
        project_id: projectId,
        project_version: 7,
        plots: [
          enginePlotFixture('plot:zeta', 3, 'K01', 7),
          enginePlotFixture('plot:alpha', 2, 'K02', 7),
        ],
      })),
      getPlot,
    })
    installApi(api)
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))
    await user.click(await screen.findByRole('button', { name: '跨重启项目' }))

    await waitFor(() => expect(getPlot).toHaveBeenCalledWith({
        projectId: 'project:recovered',
        plotId: 'plot:alpha',
        plotVersion: 2,
      }))
    expect(await screen.findByRole('img', { name: '线点图 真实渲染预览' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '@图2 · 线点图 · v2' })).toBeInTheDocument()
  })

  it('opens historical projects without silently replacing removed chart types', async () => {
    const user = userEvent.setup()
    const getPlot = vi.fn(async (input) => ok(
      enginePlotFixture(input.plotId, input.plotVersion, 'K02', 7),
    ))
    const api = fakeDesktop({
      listProjects: vi.fn(async () => ok({
        projects: [
          { project_id: 'project:historical', display_name: '历史项目', project_version: 7, is_open: false },
        ],
      })),
      activateProject: vi.fn(async ({ projectId }) => ok({ project_id: projectId, project_version: 7, status: 'open' })),
      listDatasets: vi.fn(async ({ projectId }) => ok({ project_id: projectId, project_version: 7, datasets: [dataset] })),
      listPlots: vi.fn(async ({ projectId }) => ok({
        project_id: projectId,
        project_version: 7,
        plots: [
          enginePlotFixture('plot:removed', 1, 'K25', 6),
          enginePlotFixture('plot:supported', 2, 'K02', 7),
        ],
      })),
      getPlot,
    })
    installApi(api)
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '历史项目' }))

    expect(await screen.findByText('图类已移除')).toBeInTheDocument()
    expect(screen.getByText(/K25.*不会被替换或重新渲染/)).toBeInTheDocument()
    expect(getPlot).toHaveBeenCalledWith({
      projectId: 'project:historical',
      plotId: 'plot:supported',
      plotVersion: 2,
    })
    expect(getPlot).not.toHaveBeenCalledWith(expect.objectContaining({ plotId: 'plot:removed' }))
    expect(await screen.findByRole('img', { name: '线点图 真实渲染预览' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '历史项目' })).toBeInTheDocument()
  })

  it('opens a persisted project with no plots in the normal data-ready empty state', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop()
    installApi(api)
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '打开已有 .plotproj' }))

    expect(await screen.findByRole('heading', { name: '已打开项目' })).toBeInTheDocument()
    expect(api.listPlots).toHaveBeenCalledWith({ projectId: 'project:opened' })
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '选择图形' })).toBeEnabled()
  })

  it('imports real Core fields, confirms one mapping, and displays a controlled preview resource', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop()
    installApi(api)
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /^导入/ }))
    expect(await screen.findByText('荧光强度')).toBeInTheDocument()
    expect(screen.getAllByTitle(/数值 · 浮点数/)).toHaveLength(2)
    expect(screen.getByText('a.u.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K01')
    await user.click(screen.getByRole('button', { name: /K01.*折线图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.click(screen.getByRole('button', { name: '字段绑定' }))
    expect(screen.getByRole('heading', { name: '数据预览与字段绑定' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '确认并绘图' }))
    expect(api.executePlotAction).toHaveBeenCalledWith(expect.objectContaining({
      expectedProjectVersion: 1,
      action: expect.objectContaining({
        operation: 'create_plot',
        profile_id: 'K01',
        bindings: expect.arrayContaining([
          { role: 'x', field_id: 'field:time' },
          { role: 'y', field_id: 'field:signal' },
        ]),
      }),
    }))
    expect(await screen.findByRole('img')).toHaveAttribute('src', expect.stringMatching(/^plotagent-resource:/))
  })

  it('reviews sample rows and edits field roles from the column headers', async () => {
    const user = userEvent.setup()
    const datasetSummary = Object.fromEntries(
      Object.entries(dataset).filter(([key]) => key !== 'sample_rows'),
    ) as JsonValue
    const api = fakeDesktop({
      importDatasets: vi.fn(async () => ok({
        imports: [{ kind: 'committed', project_version: 1, datasets: [datasetSummary] }],
        project_version: 1,
      })),
      describeDataset: vi.fn(async () => ok({ dataset })),
    })
    installApi(api)
    render(<App />)

    await user.click(await screen.findByRole('button', { name: /^导入/ }))
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K01')
    await user.click(screen.getByRole('button', { name: /K01.*折线图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.click(screen.getByRole('button', { name: '字段绑定' }))

    const review = screen.getByRole('group', { name: '数据预览与字段绑定' })
    expect(within(review).getByText('是否确认创建')).toBeInTheDocument()
    expect(within(review).getByText('K01 折线图')).toBeInTheDocument()
    expect(await within(review).findByText('3.2')).toBeInTheDocument()
    expect(api.describeDataset).toHaveBeenCalledWith({
      projectId: 'project:test', datasetId: 'source:temperature', sourceVersion: 1,
    })

    const yRoleTrigger = within(review).getByRole('button', { name: '荧光强度 的绘图角色：Y' })
    await user.click(yRoleTrigger)
    expect(screen.getByRole('menu', { name: '荧光强度 的绘图角色' })).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu', { name: '荧光强度 的绘图角色' })).not.toBeInTheDocument()
    expect(yRoleTrigger).toHaveFocus()

    await user.click(yRoleTrigger)
    const roleMenu = screen.getByRole('menu', { name: '荧光强度 的绘图角色' })
    await user.click(within(roleMenu).getByRole('menuitemradio', { name: '未使用' }))
    expect(within(review).getByText('还需绑定：Y')).toBeInTheDocument()
    expect(within(review).getByRole('button', { name: '确认并绘图' })).toBeDisabled()

    await user.click(within(review).getByRole('button', { name: '恢复 Agent 建议' }))
    expect(within(review).getByRole('button', { name: '荧光强度 的绘图角色：Y' })).toBeInTheDocument()
    expect(within(review).getByRole('button', { name: '确认并绘图' })).toBeEnabled()
  })

  it('closes a manual mapping review when the user cancels', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop()
    installApi(api)
    render(<App />)

    await user.click(await screen.findByRole('button', { name: /^导入/ }))
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K01')
    await user.click(screen.getByRole('button', { name: /K01.*折线图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.click(screen.getByRole('button', { name: '字段绑定' }))

    const review = screen.getByRole('group', { name: '数据预览与字段绑定' })
    await user.click(within(review).getByRole('button', { name: '取消' }))

    expect(screen.queryByRole('group', { name: '数据预览与字段绑定' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '字段绑定' })).toBeEnabled()
    expect(api.executePlotAction).not.toHaveBeenCalled()
  })

  it('submits only engine-supported K04 roles from the generated profile', async () => {
    const user = userEvent.setup()
    const bubbleDataset = {
      ...dataset,
      field_count: 5,
      fields: [
        ...dataset.fields,
        { field_id: 'field:size', name: 'bubble_size', logical_type: 'numeric', physical_type: 'float64', unit: null },
        { field_id: 'field:color', name: 'color_value', logical_type: 'numeric', physical_type: 'float64', unit: null },
      ],
      sample_rows: dataset.sample_rows.map((row, index) => [...row, index + 5, index / 4]),
    }
    const api = fakeDesktop({
      importDatasets: vi.fn(async () => ok({
        imports: [{ kind: 'committed', project_version: 1, datasets: [bubbleDataset] }],
        project_version: 1,
      })),
      describeDataset: vi.fn(async () => ok({ dataset: bubbleDataset })),
    })
    installApi(api)
    render(<App />)

    await user.click(await screen.findByRole('button', { name: /^导入/ }))
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K04')
    await user.click(screen.getByRole('button', { name: /K04.*气泡图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.click(screen.getByRole('button', { name: '字段绑定' }))

    const review = screen.getByRole('group', { name: '数据预览与字段绑定' })
    expect(within(review).queryByRole('menuitemradio', { name: /分组/ })).not.toBeInTheDocument()
    await user.click(within(review).getByRole('button', { name: '确认并绘图' }))

    await waitFor(() => expect(api.executePlotAction).toHaveBeenCalledTimes(1))
    const action = vi.mocked(api.executePlotAction).mock.calls[0]?.[0].action as { bindings: { role: string }[] }
    expect(action.bindings.map((binding) => binding.role)).toEqual(['x', 'y', 'size', 'color'])
    expect(action.bindings.some((binding) => binding.role === 'group')).toBe(false)
  })

  it('suggests the optional group role for grouped long K18 data', () => {
    const areaDataset = {
      ...dataset,
      row_count: 6,
      fields: [
        { fieldId: 'field:x', name: 'X', logicalType: 'numeric', physicalType: 'int64', unit: null },
        { fieldId: 'field:y', name: 'Y', logicalType: 'numeric', physicalType: 'float64', unit: null },
        { fieldId: 'field:group', name: 'Group', logicalType: 'categorical', physicalType: 'string', unit: null },
      ],
      sample_rows: [
        [1, 2.0, 'Base'],
        [2, 3.2, 'Base'],
        [3, 3.7, 'Base'],
        [1, 1.5, 'Variant'],
        [2, 2.7, 'Variant'],
      ],
    }
    expect(suggestedFieldMapping([
      { role: 'x', numeric: true, required: true },
      { role: 'series_1', numeric: true, required: true },
      { role: 'group', numeric: false, required: false },
    ], areaDataset as never)).toEqual({
      x: 'field:x',
      series_1: 'field:y',
      group: 'field:group',
    })
  })

  it('maps K06 error-magnitude columns to explicit asymmetric error roles', () => {
    const errorDataset = {
      ...dataset,
      fields: [
        { fieldId: 'field:x', name: 'X', logicalType: 'numeric', physicalType: 'int64', unit: null },
        { fieldId: 'field:y', name: 'Y', logicalType: 'numeric', physicalType: 'float64', unit: null },
        { fieldId: 'field:xm', name: 'XErrMinus', logicalType: 'numeric', physicalType: 'float64', unit: null },
        { fieldId: 'field:xp', name: 'XErrPlus', logicalType: 'numeric', physicalType: 'float64', unit: null },
        { fieldId: 'field:ym', name: 'YErrMinus', logicalType: 'numeric', physicalType: 'float64', unit: null },
        { fieldId: 'field:yp', name: 'YErrPlus', logicalType: 'numeric', physicalType: 'float64', unit: null },
      ],
    }

    expect(suggestedFieldMapping([
      { role: 'x', numeric: true, required: true },
      { role: 'center', numeric: true, required: true },
      { role: 'x_err_minus', numeric: true, required: true },
      { role: 'x_err_plus', numeric: true, required: true },
      { role: 'y_err_minus', numeric: true, required: true },
      { role: 'y_err_plus', numeric: true, required: true },
    ], errorDataset as never)).toEqual({
      x: 'field:x',
      center: 'field:y',
      x_err_minus: 'field:xm',
      x_err_plus: 'field:xp',
      y_err_minus: 'field:ym',
      y_err_plus: 'field:yp',
    })
  })

  it('keeps K19 datetime, value and long-series roles type safe', () => {
    const timeSeriesDataset = {
      ...dataset,
      fields: [
        { fieldId: 'field:timestamp', name: 'Timestamp', logicalType: 'datetime', physicalType: 'datetime64', unit: null },
        { fieldId: 'field:value', name: 'Value', logicalType: 'numeric', physicalType: 'float64', unit: null },
        { fieldId: 'field:series', name: 'Series', logicalType: 'categorical', physicalType: 'string', unit: null },
      ],
    }

    expect(suggestedFieldMapping([
      { role: 'time', numeric: false, datetime: true, required: true },
      { role: 'series_1', numeric: true, required: true },
      { role: 'group', numeric: false, required: false },
    ], timeSeriesDataset as never)).toEqual({
      time: 'field:timestamp',
      series_1: 'field:value',
      group: 'field:series',
    })
  })

  it('shows a user-facing file and worksheet identity instead of the internal dataset id', async () => {
    const user = userEvent.setup()
    installApi(fakeDesktop({
      importDatasets: vi.fn(async () => ok({
        imports: [{
          kind: 'committed',
          source_file_name: '仪器记录.xlsx',
          project_version: 1,
          datasets: [{ ...dataset, source_file_name: '仪器记录.xlsx', source_sheet_name: '动力学' }],
        }],
        project_version: 1,
      })),
    }))
    render(<App />)

    await user.click(await screen.findByRole('button', { name: /^导入/ }))
    expect(await screen.findByRole('heading', { name: '仪器记录.xlsx > 动力学' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'source:temperature' })).not.toBeInTheDocument()
  })

  it('keeps successful files when a multi-file import only partially succeeds', async () => {
    const user = userEvent.setup()
    installApi(fakeDesktop({
      importDatasets: vi.fn(async () => ok({
        selected_files: ['有效数据.xlsx', '损坏数据.txt', '未回执.dat'],
        imports: [
          {
            kind: 'committed',
            source_file_name: '有效数据.xlsx',
            project_version: 1,
            datasets: [{ ...dataset, source_file_name: '有效数据.xlsx', source_sheet_name: 'Sheet 1' }],
          },
          { kind: 'failed', source_file_name: '损坏数据.txt', error: { code: 'IMPORT_FAILED', message: '无法解析数据块。' } },
        ],
        project_version: 1,
      })),
    }))
    render(<App />)

    await user.click(await screen.findByRole('button', { name: /^导入/ }))
    expect(await screen.findByRole('heading', { name: '有效数据.xlsx > Sheet 1' })).toBeInTheDocument()
    expect(screen.getByText('部分文件未导入')).toBeInTheDocument()
    expect(screen.getByText(/已导入：有效数据.xlsx/)).toBeInTheDocument()
    expect(screen.getByText(/未导入：损坏数据.txt/)).toBeInTheDocument()
    expect(screen.getByText(/未导入：未回执.dat：未返回处理结果，请重试。/)).toBeInTheDocument()

    await user.type(screen.getByRole('textbox', { name: '描述绘图要求' }), '继续分析已导入的数据')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))
    await waitFor(() => expect(screen.getByText(/未导入：损坏数据.txt/)).toBeInTheDocument())
    expect(screen.getByText(/未导入：未回执.dat：未返回处理结果，请重试。/)).toBeInTheDocument()
  })

  it('prevents a second import while the first import request is pending', async () => {
    const user = userEvent.setup()
    let finishImport: ((result: DesktopDataResult) => void) | undefined
    const importDatasets = vi.fn(() => new Promise<DesktopDataResult>((resolve) => { finishImport = resolve }))
    const api = fakeDesktop({ importDatasets })
    installApi(api)
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /新建项目/ }))

    const upload = screen.getByRole('button', { name: '上传数据' })
    await user.click(upload)
    expect(screen.getByRole('button', { name: '正在导入' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '正在导入' }))
    expect(importDatasets).toHaveBeenCalledTimes(1)

    finishImport?.(ok({ imports: [{ kind: 'committed', project_version: 1, datasets: [dataset] }], project_version: 1 }))
    expect(await screen.findByText('数据已导入')).toBeInTheDocument()
  })

  it.each([
    ['clarification', { kind: 'clarification', prompt: '第 3 行和第 4 行都可能是表头，请选择后重新导入。' }, '导入需要确认'],
    ['rejection', { kind: 'rejection', message: '文件中没有可识别的数值数据块。' }, '数据未导入'],
  ])('renders an actionable import %s instead of fake data', async (_kind, result, expectedTitle) => {
    const user = userEvent.setup()
    const importDatasets = vi.fn(async () => ok(result))
    installApi(fakeDesktop({ importDatasets }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /^导入/ }))
    expect(await screen.findByText(expectedTitle)).toBeInTheDocument()
    expect(screen.queryByText('source:temperature')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重新选择文件' }))
    expect(importDatasets).toHaveBeenCalledTimes(2)
  })

  it('keeps the three entry points visible but disabled while Core is offline', async () => {
    installApi(fakeDesktop({ getBootstrap: vi.fn(async (): Promise<DesktopBootstrap> => ({ apiVersion: DESKTOP_API_VERSION, platform: 'win32', core: { phase: 'failed', restartAttempt: 3, error: { code: 'CORE_START_FAILED', message: '本地 Core 无法启动。', retryable: true } }, tasks: { tasks: [], activeTaskCount: 0, hasCommittingTask: false } })) }))
    render(<App />)
    expect(await screen.findByText('本地 Core 启动失败')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^导入/ })).toBeDisabled()
  })

  it('exports PNG through the narrow desktop API without exposing a path', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop()
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)
    await user.click(screen.getByRole('button', { name: '导出 PNG' }))
    expect(api.exportPngSvg).toHaveBeenCalledWith({
      projectId: 'project:sample',
      target: { kind: 'plot', id: expect.stringMatching(/^plot:ui\./), version: 1 },
      format: 'png',
    })
    expect(await screen.findAllByText('已导出 PNG')).not.toHaveLength(0)
    expect(screen.getByRole('status', { name: '导出记录' })).toHaveTextContent('PNG 导出完成')
    expect(screen.getByRole('status', { name: '导出记录' })).toHaveTextContent('plot.png')
    await user.click(screen.getAllByRole('button', { name: '打开文件' })[0])
    await user.click(screen.getAllByRole('button', { name: /打开.*文件夹/ })[0])
    expect(api.openExportResource).toHaveBeenCalledWith({ resourceId: 'resource:export' })
    expect(api.revealExportResource).toHaveBeenCalledWith({ resourceId: 'resource:export' })
    expect(document.body.textContent).not.toMatch(/[A-Za-z]:\\/)
  })

  it('synchronizes the displayed plot to the latest durable version before every export format', async () => {
    const user = userEvent.setup()
    let created = false
    const executePlotAction = vi.fn(async () => {
      created = true
      return ok(enginePlotFixture('plot:one', 1, 'K01', 2))
    })
    const listPlots = vi.fn(async () => ok({
      project_version: 5,
      plots: created ? [enginePlotFixture('plot:one', 4, 'K01', 5)] : [],
    }))
    const getPlot = vi.fn(async (input) => ok(enginePlotFixture(
      input.plotId,
      input.plotVersion,
      'K01',
      5,
    )))
    const exportPngSvg = vi.fn(async (input) => ok({
      export_id: `export:${input.format}`,
      plot_id: input.target.id,
      plot_version: input.target.version,
      artifact: {
        resource: {
          resourceId: `resource:${input.format}`,
          kind: 'export',
          fileName: `plot.${input.format}`,
        },
        content_hash: 'c'.repeat(64),
        size: 2_048,
      },
    }))
    const exportOrigin = vi.fn(async (input) => ok({
      export_id: 'export:opju',
      plot_id: input.target.id,
      plot_version: input.target.version,
      artifact: {
        resource: { resourceId: 'resource:opju', kind: 'export', fileName: 'plot.opju' },
        content_hash: 'd'.repeat(64),
        size: 30_001,
      },
    }))
    const api = fakeDesktop({ executePlotAction, listPlots, getPlot, exportPngSvg, exportOrigin })
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.click(screen.getByRole('button', { name: '导出 PNG' }))
    await screen.findByText('已导出 PNG', { selector: '.composer-success' })
    await user.click(screen.getByRole('button', { name: '导出 SVG' }))
    await screen.findByText('已导出 SVG', { selector: '.composer-success' })
    await user.click(screen.getByRole('button', { name: '导出 OPJU' }))
    await screen.findByText('已导出 OPJU', { selector: '.composer-success' })

    expect(listPlots).toHaveBeenCalledTimes(3)
    expect(getPlot).toHaveBeenCalledWith({
      projectId: 'project:sample', plotId: 'plot:one', plotVersion: 4,
    })
    expect(exportPngSvg).toHaveBeenNthCalledWith(1, {
      projectId: 'project:sample', target: { kind: 'plot', id: 'plot:one', version: 4 }, format: 'png',
    })
    expect(exportPngSvg).toHaveBeenNthCalledWith(2, {
      projectId: 'project:sample', target: { kind: 'plot', id: 'plot:one', version: 4 }, format: 'svg',
    })
    expect(exportOrigin).toHaveBeenCalledWith({
      projectId: 'project:sample', target: { kind: 'plot', id: 'plot:one', version: 4 },
    })
    expect(screen.getByRole('region', { name: /@图\d+.*v4/ })).toBeInTheDocument()
  })

  it('does not announce success when Core returns a different plot version than requested', async () => {
    const user = userEvent.setup()
    installApi(fakeDesktop({
      exportPngSvg: vi.fn(async (input) => ok({
        export_id: 'export:wrong-version',
        plot_id: input.target.id,
        plot_version: input.target.version + 1,
        artifact: {
          resource: { resourceId: 'resource:wrong-version', kind: 'export', fileName: 'plot.png' },
          content_hash: 'e'.repeat(64),
          size: 1_024,
        },
      })),
    }))
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.click(screen.getByRole('button', { name: '导出 PNG' }))

    expect(await screen.findByText(/导出返回的图形版本与当前版本不一致/)).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: '导出记录' })).not.toBeInTheDocument()
    expect(screen.queryByText('已导出 PNG')).not.toBeInTheDocument()
  })

  it('fails closed when the displayed plot version cannot be proven durable', async () => {
    const user = userEvent.setup()
    const exportPngSvg = vi.fn(async () => ok({}))
    installApi(fakeDesktop({
      listPlots: vi.fn(async () => ok({ project_version: 2, plots: [] })),
      getPlot: vi.fn(async (input) => ok(enginePlotFixture(
        input.plotId,
        input.plotVersion + 1,
      ))),
      exportPngSvg,
    }))
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.click(screen.getByRole('button', { name: '导出 PNG' }))

    expect(await screen.findByText(/Core 中找不到当前界面显示的图形版本/)).toBeInTheDocument()
    expect(exportPngSvg).not.toHaveBeenCalled()
    expect(screen.queryByRole('status', { name: '导出记录' })).not.toBeInTheDocument()
  })

  it('keeps OPJU progress explicit and announces a durable completion result', async () => {
    const user = userEvent.setup()
    let finishExport: ((result: DesktopDataResult) => void) | undefined
    let requestedTarget: { id: string; version: number } | undefined
    const exportOrigin = vi.fn((input) => {
      requestedTarget = input.target
      return new Promise<DesktopDataResult>((resolve) => { finishExport = resolve })
    })
    const api = fakeDesktop({ exportOrigin })
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.click(screen.getByRole('button', { name: '导出 OPJU' }))
    expect(await screen.findByText('正在生成并验证 OPJU…')).toBeInTheDocument()
    expect(screen.queryByText('OPJU 导出完成')).not.toBeInTheDocument()

    finishExport?.(ok({
      export_id: 'export:origin',
      plot_id: requestedTarget?.id ?? '',
      plot_version: requestedTarget?.version ?? 0,
      artifact: {
        resource: {
          resourceId: 'resource:origin',
          kind: 'export',
          fileName: 'plot.opju',
        },
        content_hash: 'b'.repeat(64),
        size: 29_999,
      },
    }))

    const result = await screen.findByRole('status', { name: '导出记录' })
    expect(result).toHaveTextContent('OPJU 导出完成')
    expect(result).toHaveTextContent('29,999 B')
    expect(result).toHaveTextContent('bbbbbbbbbbbb…')
    expect(screen.queryByText('正在生成并验证 OPJU…')).not.toBeInTheDocument()
    expect(screen.getByText('已导出 OPJU', { selector: '.composer-success' })).toBeInTheDocument()
    expect(screen.getByText('已导出 OPJU', { selector: '.product-toast strong' })).toBeInTheDocument()
  })

  it('does not announce OPJU success when the desktop boundary omits file proof', async () => {
    const user = userEvent.setup()
    installApi(fakeDesktop({
      exportOrigin: vi.fn(async () => ok({ export_id: 'export:unverified' })),
    }))
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.click(screen.getByRole('button', { name: '导出 OPJU' }))

    expect(await screen.findByText(/缺少可验证的文件记录/)).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: '导出记录' })).not.toBeInTheDocument()
    expect(screen.queryByText('已导出 OPJU')).not.toBeInTheDocument()
  })

  it('preflights Origin before OPJU export and keeps the save flow closed when unavailable', async () => {
    const user = userEvent.setup()
    const getOriginStatus = vi.fn(async () => ok({
      status: 'error',
      error: {
        code: 'LICENSE_UNAVAILABLE',
        message: 'Origin 许可证当前不可用。请启动 Origin 完成许可证验证后重新检测。',
        retryable: true,
      },
    }))
    const api = fakeDesktop({ getOriginStatus })
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)

    expect(await screen.findByRole('button', { name: /Origin 不可用，重新检测/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '导出 OPJU' }))

    expect(getOriginStatus).toHaveBeenCalled()
    expect(api.exportOrigin).not.toHaveBeenCalled()
    expect((await screen.findAllByText('Origin 不可用')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/启动 Origin 完成许可证验证后重新检测/)).toBeInTheDocument()
  })

  it('creates a persistent batch plan from dataset-specific immutable bindings', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop({
      runWorkflow: vi.fn(async () => ok(workflowResultWithPlan(batchPlanFixture()))),
      confirmTaskPlan: vi.fn(async () => ok(batchPlanFixture('ready'))),
      runTaskPlan: vi.fn(async () => ok({
        task_plan: batchPlanFixture('succeeded'),
        change_set: { plan_id: 'plan:batch', state: 'succeeded', items: [] },
      })),
    })
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.click(screen.getByRole('button', { name: /创建批次/ }))
    expect(api.runWorkflow).toHaveBeenCalledWith(expect.objectContaining({
      selectedProfileIds: ['K01'],
      selectedSources: [expect.objectContaining({
        datasetId: 'source:temperature', sourceVersion: 1,
      })],
    }))
    expect(await screen.findByRole('heading', { name: '任务计划' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).toHaveTextContent('字段绑定')
    expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).toHaveTextContent('时间')
    expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).toHaveTextContent('创建 K01')
    expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).toHaveTextContent('K01 折线图 · 新图')
    expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).not.toHaveTextContent('作用对象')
    expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).not.toHaveTextContent('使用数据')
    expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).not.toHaveTextContent('预计结果')
    expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).toHaveTextContent('原始数据 · 前 3 行')
    expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).not.toHaveTextContent('plot:one · v1')
    await user.click(screen.getByRole('button', { name: '确认并执行' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).toHaveTextContent('已完成'))
  })

  it('presents a terminal execution failure as stopped instead of resumable partial work', async () => {
    const user = userEvent.setup()
    installApi(fakeDesktop({
      runWorkflow: vi.fn(async () => ok(workflowResultWithPlan(batchPlanFixture()))),
      confirmTaskPlan: vi.fn(async () => ok(batchPlanFixture('ready'))),
      runTaskPlan: vi.fn(async () => ok({
        task_plan: workflowPlanFixture('failed', 'failed', {
          planId: 'plan:batch',
          failure: {
            code: 'UNSUPPORTED_OPERATION',
            message: '该操作不能执行。',
            retryable: false,
            category: 'unsupported',
            sideEffectState: 'known_none',
          },
        }),
      })),
    }))
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.click(await screen.findByRole('button', { name: /创建批次/ }))
    await user.click(await screen.findByRole('button', { name: '确认并执行' }))

    const card = (await screen.findByRole('heading', { name: '任务计划' })).closest('section')
    expect(card).toHaveTextContent('失败')
    expect(card).toHaveTextContent('下一步：修改要求后创建新任务')
    expect(screen.queryByRole('button', { name: '继续未完成步骤' })).not.toBeInTheDocument()
  })

  it('keeps a batch clarification in the conversation instead of reporting a missing plan', async () => {
    const user = userEvent.setup()
    const runWorkflow = vi.fn(async () => ok({
      outcome: 'needs_input',
      workflow_run_id: 'workflow:batch-clarification',
      questions: [{
        question_key: 'field_mapping',
        prompt: '第二个数据表的 Y 字段是哪一列？',
        answer_kind: 'field',
        choices: [],
        required: true,
      }],
    }))
    installApi(fakeDesktop({
      runWorkflow,
      openSampleProject: vi.fn(async () => ok({
        project: { project_id: 'project:sample', display_name: '多表项目', is_open: false },
        opened: { project_id: 'project:sample', project_version: 0, status: 'open' },
        imported: { kind: 'committed', project_version: 1, datasets: [dataset, secondDataset] },
      })),
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K01')
    await user.click(screen.getByRole('button', { name: /K01.*折线图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.click(screen.getByRole('button', { name: '字段绑定' }))
    await user.click(screen.getByRole('button', { name: '确认并绘图' }))
    await user.click(await screen.findByRole('button', { name: /创建批次/ }))

    expect(runWorkflow).toHaveBeenCalledWith(expect.objectContaining({
      selectedSources: [
        { datasetId: 'source:temperature', sourceVersion: 1 },
        { datasetId: 'source:pressure', sourceVersion: 1 },
      ],
    }))
    expect(await screen.findAllByText('第二个数据表的 Y 字段是哪一列？')).toHaveLength(1)
    expect(screen.queryByText('Core 未返回批量任务计划。')).not.toBeInTheDocument()
  })

  it('shows a repair question returned after partial execution and continues the same task', async () => {
    const user = userEvent.setup()
    const runWorkflow = vi.fn()
      .mockResolvedValueOnce(ok(workflowResultWithPlan(batchPlanFixture())))
      .mockResolvedValueOnce(ok(workflowResultWithPlan(workflowPlanFixture(
        'awaiting_reconfirmation',
        'succeeded',
        { planId: 'plan:revised', plotVersion: 1 },
      ))))
    const partial = workflowPlanFixture('partially_failed', 'failed', {
      planId: 'plan:batch',
      failure: { code: 'INVALID_DATA', message: '失败项数据不适用。', retryable: true },
    })
    const confirmTaskPlan = vi.fn()
      .mockResolvedValueOnce(ok(batchPlanFixture('ready')))
      .mockResolvedValueOnce(ok(workflowPlanFixture(
        'succeeded',
        'succeeded',
        { planId: 'plan:revised', plotVersion: 1 },
      )))
    const runTaskPlan = vi.fn(async () => ok({
      outcome: 'needs_input',
      workflow_run_id: 'task:partial-repair',
      questions: [{
        question_key: 'repair_choice',
        prompt: '失败项应取消，还是提供替代数据后重试？',
        answer_kind: 'text',
        choices: [],
        required: true,
      }],
    }))
    const api = fakeDesktop({
      runWorkflow,
      confirmTaskPlan,
      runTaskPlan,
      getTaskPlan: vi.fn(async () => ok(partial)),
    })
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)
    await user.click(screen.getByRole('button', { name: /创建批次/ }))
    await user.click(await screen.findByRole('button', { name: '确认并执行' }))

    expect((await screen.findAllByText('失败项应取消，还是提供替代数据后重试？')).length).toBeGreaterThan(0)
    await user.type(screen.getByRole('textbox', { name: '描述绘图要求' }), '取消失败项，保留成功结果。')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    expect(runWorkflow).toHaveBeenLastCalledWith(expect.objectContaining({
      continuationWorkflowRunId: 'task:partial-repair',
      instruction: '取消失败项，保留成功结果。',
    }))
    expect(await screen.findByRole('button', { name: '确认修订计划' })).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { name: '任务计划' }).at(-1)?.closest('section')).toHaveTextContent('等待重新确认')
    await user.click(screen.getByRole('button', { name: '确认修订计划' }))
    expect(await screen.findByText('更改已保存')).toBeInTheDocument()
    expect(runTaskPlan).toHaveBeenCalledTimes(1)
  })

  it('labels a rendered plot from its actual profile instead of the selected library card', async () => {
    const user = userEvent.setup()
    installApi(fakeDesktop({
      executePlotAction: vi.fn(async () => ok(enginePlotFixture('plot:actual-k03', 1, 'K03', 2))),
    }))
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '示例' }))
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K01')
    await user.click(screen.getByRole('button', { name: /K01.*折线图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.click(screen.getByRole('button', { name: '字段绑定' }))
    await user.click(screen.getByRole('button', { name: '确认并绘图' }))

    expect(await screen.findByRole('img', { name: '散点图 真实渲染预览' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '@图1 · 散点图 · v1' })).toBeInTheDocument()
  })

  it('plans one plot from explicitly selected compatible sources', async () => {
    const user = userEvent.setup()
    const planCombinedSources = vi.fn(async () => ok(workflowResultWithPlan(batchPlanFixture())))
    installApi(fakeDesktop({
      runWorkflow: planCombinedSources,
      openSampleProject: vi.fn(async () => ok({
        project: { project_id: 'project:sample', display_name: '多表项目', is_open: false },
        opened: { project_id: 'project:sample', project_version: 0, status: 'open' },
        imported: { kind: 'committed', project_version: 1, datasets: [dataset, secondDataset] },
      })),
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K03')
    await user.click(screen.getByRole('button', { name: /K03.*散点图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.click(screen.getByRole('button', { name: '字段绑定' }))
    await user.click(screen.getByRole('button', { name: '2 个数据表同图绘制' }))

    expect(planCombinedSources).toHaveBeenCalledWith(expect.objectContaining({
      selectedProfileIds: ['K03'],
      selectedSources: [
        { datasetId: 'source:temperature', sourceVersion: 1 },
        { datasetId: 'source:pressure', sourceVersion: 1 },
      ],
    }))
    expect(await screen.findByRole('heading', { name: '任务计划' })).toBeInTheDocument()
  })

  it('allows retry on a new target and ignores a late decision from the old target', async () => {
    const user = userEvent.setup()
    let finishOldDecision: ((result: DesktopDataResult) => void) | undefined
    const prepareWorkflow = vi.fn()
      .mockImplementationOnce(() => new Promise<DesktopDataResult>((resolve) => { finishOldDecision = resolve }))
      .mockResolvedValueOnce(ok(workflowResultWithPlan(workflowPlanFixture('needs_confirmation', 'pending', { planId: 'plan:new' }))))
    installApi(fakeDesktop({ runWorkflow: prepareWorkflow }))
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.type(screen.getByRole('textbox', { name: '描述绘图要求' }), '旧目标请求')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))
    expect(screen.getByRole('textbox', { name: '描述绘图要求' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: '选择其他图形' }))
    await user.clear(screen.getByRole('textbox', { name: '搜索图形库' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K02')
    await user.click(screen.getByRole('button', { name: /K02.*线点图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))

    await user.type(screen.getByRole('textbox', { name: '描述绘图要求' }), '新目标请求')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))
    expect(await screen.findByRole('heading', { name: '任务计划' })).toBeInTheDocument()
    expect(screen.getByText('新目标请求')).toBeInTheDocument()
    expect(prepareWorkflow).toHaveBeenLastCalledWith(expect.objectContaining({
      selectedProfileIds: ['K02'],
      selectedSources: [{ datasetId: 'source:temperature', sourceVersion: 1 }],
      instruction: '新目标请求',
    }))

    await act(async () => {
      finishOldDecision?.(ok({
        outcome: 'unsupported',
        workflow_run_id: 'workflow:old',
        reason_code: 'STALE_REQUEST',
        message: '陈旧结果不应显示',
      }))
    })
    expect(screen.queryByText('陈旧结果不应显示')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '任务计划' })).toBeInTheDocument()
  })

  it('keeps the plan in place, appends its result below it, and sends an explicit plot mention', async () => {
    const user = userEvent.setup()
    let finishDecision: ((result: DesktopDataResult) => void) | undefined
    const prepareWorkflow = vi.fn(() => new Promise<DesktopDataResult>((resolve) => { finishDecision = resolve }))
    installApi(fakeDesktop({
      runWorkflow: prepareWorkflow,
      executePlotAction: vi.fn(async () => ok(enginePlotFixture('plot:one', 1, 'K01', 2))),
    }))
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.type(screen.getByRole('textbox', { name: '描述绘图要求' }), '@图1 把标题改成温度响应')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    const activity = await screen.findByText('正在理解你的要求…')
    const plotCard = screen.getByRole('img', { name: '折线图 真实渲染预览' }).closest('section')
    expect(plotCard?.compareDocumentPosition(activity.closest('.message') as Node) ?? 0)
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING)

    await act(async () => {
      finishDecision?.(ok(workflowResultWithPlan(workflowPlanFixture())))
    })
    const planMessage = (await screen.findByRole('heading', { name: '任务计划' })).closest('.message')
    expect(plotCard?.compareDocumentPosition(planMessage as Node) ?? 0)
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    expect(prepareWorkflow).toHaveBeenCalledWith(expect.objectContaining({
      instruction: '@图1 把标题改成温度响应',
      selectedPlots: [{ plotId: 'plot:one', plotVersion: 1 }],
    }))

    await user.click(screen.getByRole('button', { name: '确认并执行' }))
    const resultPlot = await screen.findByRole('heading', { name: '@图1 · 折线图 · v2' })
    expect(planMessage?.compareDocumentPosition(resultPlot.closest('section') as Node) ?? 0)
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    expect(screen.getAllByRole('heading', { name: '任务计划' })).toHaveLength(1)
    expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).toHaveTextContent('已完成')
  })

  it('continues a pending question with the exact plot selected by an @ mention', async () => {
    const user = userEvent.setup()
    const runWorkflow = vi.fn()
      .mockResolvedValueOnce(ok({
        outcome: 'needs_input',
        workflow_run_id: 'task:needs-plot',
        questions: [{
          question_key: 'target_plot',
          prompt: '请指定要修改的图。',
          answer_kind: 'plot',
          choices: [],
          required: true,
        }],
      }))
      .mockResolvedValueOnce(ok(workflowResultWithPlan(workflowPlanFixture())))
    installApi(fakeDesktop({
      runWorkflow,
      executePlotAction: vi.fn(async () => ok(enginePlotFixture('plot:one', 1, 'K01', 2))),
    }))
    render(<App />)
    await openSampleAndCreatePlot(user)

    const composer = screen.getByRole('textbox', { name: '描述绘图要求' })
    await user.type(composer, '把横轴范围改成 30 到 90。')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))
    expect((await screen.findAllByText('请指定要修改的图。')).length).toBeGreaterThan(0)

    await user.type(composer, '@图1')
    expect(screen.getByText('@图1 · v1')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    expect(runWorkflow.mock.calls.at(-1)?.[0]).toMatchObject({
      continuationWorkflowRunId: 'task:needs-plot',
      instruction: '@图1',
      selectedPlots: [{ plotId: 'plot:one', plotVersion: 1 }],
    })
    expect(runWorkflow.mock.calls.at(-1)?.[0]).not.toHaveProperty('selectedProfileIds')
  })

  it('rejects unknown plot mentions and never turns vague references into a target', async () => {
    const user = userEvent.setup()
    const runWorkflow = vi.fn(async (input: Parameters<PlotAgentDesktopApi['runWorkflow']>[0]) => {
      void input
      return ok(workflowResultWithPlan(workflowPlanFixture()))
    })
    installApi(fakeDesktop({ runWorkflow }))
    render(<App />)
    await openSampleAndCreatePlot(user)

    const composer = screen.getByRole('textbox', { name: '描述绘图要求' })
    await user.type(composer, '@图99 修改标题')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))
    expect(screen.getByRole('alert')).toHaveTextContent('项目中不存在 @图99')
    expect(runWorkflow).not.toHaveBeenCalled()

    await user.clear(composer)
    await user.type(composer, '把上一张图改成红色')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))
    await screen.findByRole('heading', { name: '任务计划' })
    expect(runWorkflow).toHaveBeenCalledWith(expect.objectContaining({ instruction: '把上一张图改成红色' }))
    expect(runWorkflow.mock.calls.at(-1)?.[0]).not.toHaveProperty('selectedPlots')
  })

  it('opens the current-plot edit panel with only portable Origin-mapped categories', async () => {
    const user = userEvent.setup()
    installApi(fakeDesktop())
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.click(screen.getByRole('button', { name: '编辑图形' }))

    expect(await screen.findByRole('dialog', { name: '聚焦编辑' })).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: '图形参数' })).toBeInTheDocument()
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      '常规', '系列', '坐标轴', '图例',
    ])
    expect(screen.queryByText('批次 B-024')).not.toBeInTheDocument()
  })

  it('keeps the selected editor tab after a versioned edit remounts the plot', async () => {
    const user = userEvent.setup()
    let version = 0
    const actions: JsonValue[] = []
    installApi(fakeDesktop({
      executePlotAction: vi.fn(async (input) => {
        version += 1
        actions.push(input.action)
        return ok(enginePlotFixture('plot:one', version, 'K01', version + 1, [...actions]))
      }),
    }))
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.click(screen.getByRole('button', { name: '编辑图形' }))
    await user.click(await screen.findByRole('tab', { name: '系列' }))
    await user.selectOptions(screen.getByRole('combobox', { name: '线型' }), 'dash')
    await user.click(screen.getByRole('button', { name: '应用系列样式' }))

    expect(await screen.findByText('版本 v2')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '系列' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('combobox', { name: '线型' })).toHaveValue('dash')
  })

  it('does not silently accumulate browsed worksheets in the Agent context', async () => {
    const user = userEvent.setup()
    const prepareWorkflow = vi.fn(async () => ok(workflowResultWithPlan(workflowPlanFixture())))
    installApi(fakeDesktop({
      runWorkflow: prepareWorkflow,
      openSampleProject: vi.fn(async () => ok({
        project: { project_id: 'project:sample', display_name: '多表项目', is_open: false },
        opened: { project_id: 'project:sample', project_version: 0, status: 'open' },
        imported: { kind: 'committed', project_version: 1, datasets: [dataset, secondDataset] },
      })),
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))

    const datasetSwitcher = await screen.findByRole('combobox', { name: '数据表' })
    await user.selectOptions(datasetSwitcher, 'source:pressure')
    await user.selectOptions(datasetSwitcher, 'source:temperature')
    expect(screen.getByText('1/8')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K01')
    await user.click(screen.getByRole('button', { name: /K01.*折线图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.type(screen.getByRole('textbox', { name: '描述绘图要求' }), '声明字段绑定')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    await screen.findByRole('heading', { name: '任务计划' })
    expect(prepareWorkflow).toHaveBeenLastCalledWith(expect.objectContaining({
      selectedSources: [{ datasetId: 'source:temperature', sourceVersion: 1 }],
    }))
  })

  it('authorizes every imported worksheet without parsing a file name from the instruction', async () => {
    const user = userEvent.setup()
    const prepareWorkflow = vi.fn(async () => ok(workflowResultWithPlan(batchPlanFixture())))
    installApi(fakeDesktop({
      runWorkflow: prepareWorkflow,
      openSampleProject: vi.fn(async () => ok({
        project: { project_id: 'project:sample', display_name: '多表项目', is_open: false },
        opened: { project_id: 'project:sample', project_version: 0, status: 'open' },
        imported: { kind: 'committed', project_version: 1, datasets: [dataset, secondDataset] },
      })),
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K03')
    await user.click(screen.getByRole('button', { name: /K03.*散点图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.type(
      screen.getByRole('textbox', { name: '描述绘图要求' }),
      '把 pressure.csv 和当前数据画在同一张 K03 散点图中',
    )
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    await screen.findByRole('heading', { name: '任务计划' })
    expect(prepareWorkflow).toHaveBeenLastCalledWith(expect.objectContaining({
      selectedSources: [
        { datasetId: 'source:temperature', sourceVersion: 1 },
        { datasetId: 'source:pressure', sourceVersion: 1 },
      ],
      instruction: '把 pressure.csv 和当前数据画在同一张 K03 散点图中',
    }))
  })

  it('authorizes every imported worksheet without parsing a source count from the instruction', async () => {
    const user = userEvent.setup()
    const prepareWorkflow = vi.fn(async () => ok(workflowResultWithPlan(batchPlanFixture())))
    installApi(fakeDesktop({
      runWorkflow: prepareWorkflow,
      openSampleProject: vi.fn(async () => ok({
        project: { project_id: 'project:sample', display_name: '多表项目', is_open: false },
        opened: { project_id: 'project:sample', project_version: 0, status: 'open' },
        imported: { kind: 'committed', project_version: 1, datasets: [dataset, secondDataset] },
      })),
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K03')
    await user.click(screen.getByRole('button', { name: /K03.*散点图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))

    await user.type(
      screen.getByRole('textbox', { name: '描述绘图要求' }),
      '将已提供的 2 个数据表画在同一张 K03 散点图中。',
    )
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    await screen.findByRole('heading', { name: '任务计划' })
    expect(prepareWorkflow).toHaveBeenLastCalledWith(expect.objectContaining({
      selectedSources: [
        { datasetId: 'source:temperature', sourceVersion: 1 },
        { datasetId: 'source:pressure', sourceVersion: 1 },
      ],
      instruction: '将已提供的 2 个数据表画在同一张 K03 散点图中。',
    }))
  })

  it('lets an explicit multi-dataset request choose different chart types without a preselected chart', async () => {
    const user = userEvent.setup()
    const prepareWorkflow = vi.fn(async (input: unknown) => {
      void input
      return ok(workflowResultWithPlan(batchPlanFixture()))
    })
    installApi(fakeDesktop({
      runWorkflow: prepareWorkflow,
      openSampleProject: vi.fn(async () => ok({
        project: { project_id: 'project:sample', display_name: '多表项目', is_open: false },
        opened: { project_id: 'project:sample', project_version: 0, status: 'open' },
        imported: { kind: 'committed', project_version: 1, datasets: [dataset, secondDataset] },
      })),
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))

    await user.type(
      screen.getByRole('textbox', { name: '描述绘图要求' }),
      '数据一画 K01 折线图，数据二画 K03 散点图',
    )
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    expect(await screen.findByRole('heading', { name: '任务计划' })).toBeInTheDocument()
    expect(prepareWorkflow).toHaveBeenLastCalledWith(expect.objectContaining({
      selectedSources: [
        { datasetId: 'source:temperature', sourceVersion: 1 },
        { datasetId: 'source:pressure', sourceVersion: 1 },
      ],
      instruction: '数据一画 K01 折线图，数据二画 K03 散点图',
    }))
    expect(prepareWorkflow.mock.calls.at(-1)?.[0]).not.toHaveProperty('selectedProfileIds')
  })

  it('undoes an Agent edit by creating a new inverse-action version', async () => {
    const user = userEvent.setup()
    let version = 0
    const api = fakeDesktop({
      executePlotAction: vi.fn(async (input) => {
        version += 1
        const action = input.action as Record<string, JsonValue>
        return ok(enginePlotFixture('plot:one', version, typeof action.profile_id === 'string' ? action.profile_id : 'K01', version + 1, [input.action]))
      }),
    })
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.type(screen.getByRole('textbox', { name: '描述绘图要求' }), '修改标题')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))
    await user.click(await screen.findByRole('button', { name: '确认并执行' }))
    await user.click(await screen.findByRole('button', { name: '撤销本轮' }))

    expect(api.executePlotAction).toHaveBeenLastCalledWith(expect.objectContaining({
      action: expect.objectContaining({ operation: 'set_title', target: 'plot:one', text: '' }),
    }))
    expect(await screen.findByText('已撤销本轮修改')).toBeInTheDocument()
  })

  it('keeps one exact version through editor change, undo, redo, and all export formats', async () => {
    const user = userEvent.setup()
    let version = 0
    const actions: JsonValue[] = []
    const executePlotAction = vi.fn(async (input) => {
      version += 1
      actions.push(input.action)
      return ok(enginePlotFixture('plot:one', version, 'K01', version + 1, [...actions]))
    })
    const listPlots = vi.fn(async () => ok({
      project_version: version + 1,
      plots: version === 0 ? [] : [enginePlotFixture('plot:one', version, 'K01', version + 1, [...actions])],
    }))
    const getPlot = vi.fn(async (input) => ok(enginePlotFixture(
      input.plotId,
      input.plotVersion,
      'K01',
      version + 1,
      [...actions],
    )))
    const exportPngSvg = vi.fn(async (input) => ok({
      export_id: `export:${input.format}`,
      plot_id: input.target.id,
      plot_version: input.target.version,
      artifact: {
        resource: {
          resourceId: `resource:${input.format}`,
          kind: 'export',
          fileName: `plot.${input.format}`,
        },
        content_hash: 'f'.repeat(64),
        size: 2_048,
      },
    }))
    const exportOrigin = vi.fn(async (input) => ok({
      export_id: 'export:opju',
      plot_id: input.target.id,
      plot_version: input.target.version,
      artifact: {
        resource: { resourceId: 'resource:opju', kind: 'export', fileName: 'plot.opju' },
        content_hash: '1'.repeat(64),
        size: 30_002,
      },
    }))
    const api = fakeDesktop({ executePlotAction, listPlots, getPlot, exportPngSvg, exportOrigin })
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.click(screen.getByRole('button', { name: '编辑图形' }))
    const title = await screen.findByRole('textbox', { name: '图标题' })
    await user.clear(title)
    await user.type(title, '可撤销标题')
    await user.click(screen.getByRole('button', { name: '应用图标题' }))
    expect(await screen.findByText('版本 v2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '撤销' })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: '撤销' }))
    expect(await screen.findByText('版本 v3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重做' })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: '重做' }))
    expect(await screen.findByText('版本 v4')).toBeInTheDocument()

    for (const format of ['PNG', 'SVG', 'OPJU'] as const) {
      await user.click(screen.getByRole('button', { name: '导出' }))
      await user.click(screen.getByRole('menuitem', { name: new RegExp(`导出 ${format}`) }))
      await waitFor(() => expect(screen.getByText(`版本 v4`)).toBeInTheDocument())
    }

    expect(actions.map((action) => (
      typeof action === 'object' && action !== null && 'operation' in action
        ? action.operation : undefined
    ))).toEqual(['create_plot', 'set_title', 'set_title', 'set_title'])
    expect(exportPngSvg.mock.calls.map(([input]) => [input.format, input.target.version])).toEqual([
      ['png', 4], ['svg', 4],
    ])
    expect(exportOrigin.mock.calls[0]?.[0].target.version).toBe(4)
  })

  it('offers the optional count role for an aggregated S61 confusion matrix', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'S61')
    await user.click(screen.getByRole('button', { name: /S61.*混淆矩阵/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.click(screen.getByRole('button', { name: '字段绑定' }))
    const review = screen.getByRole('group', { name: '数据预览与字段绑定' })
    await user.click(within(review).getByRole('button', { name: /时间 的绘图角色/ }))
    expect(screen.getByRole('menuitemradio', { name: '已聚合计数（可选）' })).toBeInTheDocument()
  })

  it('restores a partial plan and resumes only its unfinished work', async () => {
    const user = userEvent.setup()
    const partial = workflowPlanFixture('partially_failed', 'failed', {
      failure: {
        code: 'ORIGIN_EXPORT_FAILED',
        message: 'OPJU 导出未完成。',
        retryable: true,
        category: 'deterministic_technical',
        sideEffectState: 'known_none',
      },
    })
    const resumeWorkflowPlan = vi.fn(async () => ok({
      task_plan: workflowPlanFixture('succeeded', 'succeeded', { plotVersion: 2 }),
    }))
    const api = fakeDesktop({
      listTaskPlans: vi.fn(async () => ok({ task_plans: [partial] })),
      resumeTaskPlan: resumeWorkflowPlan,
    })
    installApi(api)
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))

    expect(await screen.findByText('部分完成')).toBeInTheDocument()
    expect(screen.getByText('OPJU 导出未完成。')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '继续未完成步骤' }))

    expect(resumeWorkflowPlan).toHaveBeenCalledWith({ projectId: 'project:sample', planId: 'plan:one' })
    expect(await screen.findByText('更改已保存')).toBeInTheDocument()
    expect(screen.getAllByText('plot:one · v2').length).toBeGreaterThan(0)
  })

  it('sends a natural-language partial repair back to the same durable task', async () => {
    const user = userEvent.setup()
    const partial = workflowPlanFixture('partially_failed', 'failed', {
      failure: {
        code: 'FIELD_BINDING_INVALID',
        message: '第二项字段绑定不成立。',
        retryable: false,
        category: 'semantic_conflict',
        requiresUser: true,
        sideEffectState: 'known_none',
      },
    })
    const runWorkflow = vi.fn(async () => ok({
      outcome: 'needs_input',
      workflow_run_id: 'task:workflow:test',
      questions: [{
        question_key: 'replacement_field',
        prompt: '第二项应改用哪一列？',
        answer_kind: 'field',
        choices: [],
        required: true,
      }],
    }))
    installApi(fakeDesktop({
      listTaskPlans: vi.fn(async () => ok({ task_plans: [partial] })),
      runWorkflow,
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))
    expect(await screen.findByText('第二项字段绑定不成立。')).toBeInTheDocument()

    await user.type(
      screen.getByRole('textbox', { name: '描述绘图要求' }),
      '第二项改用信号列，保留已经成功的第一项。',
    )
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    expect(runWorkflow).toHaveBeenCalledWith(expect.objectContaining({
      continuationWorkflowRunId: 'task:workflow:test',
      instruction: '第二项改用信号列，保留已经成功的第一项。',
    }))
  })

  it('restores a pending question after restart and answers the same durable task', async () => {
    const user = userEvent.setup()
    const runWorkflow = vi.fn(async () => ok(workflowResultWithPlan(workflowPlanFixture())))
    installApi(fakeDesktop({
      listTaskPlans: vi.fn(async () => ok({
        task_plans: [],
        durable_tasks: [{
          task_id: 'task:restart-question',
          task_version: 4,
          state: 'awaiting_input',
          project_revision: 1,
          items: [],
        }],
        pending_inputs: [{
          outcome: 'needs_input',
          workflow_run_id: 'task:restart-question',
          questions: [{
            question_key: 'field_y',
            prompt: '哪一列应作为 Y？',
            answer_kind: 'field',
            choices: [],
            required: true,
          }],
        }],
      })),
      runWorkflow,
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))

    expect(await screen.findAllByText('哪一列应作为 Y？')).toHaveLength(1)
    await user.type(screen.getByRole('textbox', { name: '描述绘图要求' }), '使用 Response_mV。')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    expect(runWorkflow).toHaveBeenCalledWith(expect.objectContaining({
      continuationWorkflowRunId: 'task:restart-question',
      instruction: '使用 Response_mV。',
    }))
  })

  it('continues a multi-source task after one reply answers several binding questions', async () => {
    const user = userEvent.setup()
    const runWorkflow = vi.fn()
      .mockResolvedValueOnce(ok({
        outcome: 'needs_input',
        workflow_run_id: 'task:multi-sheet-bindings',
        questions: [
          { question_key: 'events_a.x', prompt: 'Events_A 的 X 是哪一列？', answer_kind: 'field', choices: [], required: true },
          { question_key: 'events_a.y', prompt: 'Events_A 的 Y 是哪一列？', answer_kind: 'field', choices: [], required: true },
          { question_key: 'events_b.x', prompt: 'Events_B 的 X 是哪一列？', answer_kind: 'field', choices: [], required: true },
          { question_key: 'events_b.y', prompt: 'Events_B 的 Y 是哪一列？', answer_kind: 'field', choices: [], required: true },
        ],
      }))
      .mockResolvedValueOnce(ok(workflowResultWithPlan(workflowPlanFixture())))
    installApi(fakeDesktop({
      openSampleProject: vi.fn(async () => ok({
        project: { project_id: 'project:sample', display_name: '多表项目', is_open: false },
        opened: { project_id: 'project:sample', project_version: 2, status: 'open' },
        imported: { kind: 'committed', project_version: 2, datasets: [dataset, secondDataset] },
      })),
      runWorkflow,
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K01')
    await user.click(screen.getByRole('button', { name: /K01.*折线图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))

    const composer = screen.getByRole('textbox', { name: '描述绘图要求' })
    await user.type(composer, '分别把两个数据表各画成一张 K01。')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))
    expect(await screen.findAllByText('Events_A 的 X 是哪一列？')).toHaveLength(1)

    const answer = (
      'Events_A：X=Time_min，Y=Signal_mV；'
      + 'Events_B：X=Dose_uM，Y=Response_mV。两个都用 K01。'
    )
    await user.type(composer, answer)
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    expect(runWorkflow.mock.calls.at(-1)?.[0]).toEqual(expect.objectContaining({
      projectId: 'project:sample',
      expectedProjectVersion: 2,
      selectedSources: [
        { datasetId: 'source:temperature', sourceVersion: 1 },
        { datasetId: 'source:pressure', sourceVersion: 1 },
      ],
      selectedProfileIds: ['K01'],
      continuationWorkflowRunId: 'task:multi-sheet-bindings',
      instruction: answer,
    }))
  })

  it('shows binding evidence and sample rows for every source in a multi-source plan', async () => {
    const user = userEvent.setup()
    installApi(fakeDesktop({
      openSampleProject: vi.fn(async () => ok({
        project: { project_id: 'project:sample', display_name: '多表项目', is_open: false },
        opened: { project_id: 'project:sample', project_version: 2, status: 'open' },
        imported: { kind: 'committed', project_version: 2, datasets: [dataset, secondDataset] },
      })),
      listTaskPlans: vi.fn(async () => ok({ task_plans: [multiSourceBatchPlanFixture()] })),
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))

    const previews = await screen.findAllByRole('region', { name: '计划字段绑定与数据样本' })
    expect(previews).toHaveLength(2)
    expect(within(previews[0]).getByText('source:temperature')).toBeInTheDocument()
    expect(within(previews[0]).getByText('3.2')).toBeInTheDocument()
    expect(within(previews[0]).getByText('X')).toBeInTheDocument()
    expect(within(previews[1]).getByText('pressure.csv')).toBeInTheDocument()
    expect(within(previews[1]).getByText('101.2')).toBeInTheDocument()
    expect(within(previews[1]).getByText('Y')).toBeInTheDocument()
    expect(screen.queryByText('首项示例')).not.toBeInTheDocument()
  })

  it('passes a retry request verbatim without rebuilding hidden task context', async () => {
    const user = userEvent.setup()
    const runWorkflow = vi.fn(async (
      input: Parameters<PlotAgentDesktopApi['runWorkflow']>[0],
    ) => {
      void input
      return ok({
        outcome: 'needs_input',
        workflow_run_id: 'workflow:retry',
        questions: [{
          question_key: 'field_time',
          prompt: '请选择时间字段。',
          answer_kind: 'field',
          choices: [],
          required: true,
        }],
      })
    })
    installApi(fakeDesktop({
      openSampleProject: vi.fn(async () => ok({
        project: { project_id: 'project:sample', display_name: '多表项目', is_open: false },
        opened: { project_id: 'project:sample', project_version: 0, status: 'open' },
        imported: { kind: 'committed', project_version: 2, datasets: [dataset, secondDataset] },
      })),
      listTaskPlans: vi.fn(async () => ok({ task_plans: [failedCreatePlanFixture()] })),
      runWorkflow,
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))
    expect(await screen.findByText('Log10 轴包含 0 或负值。')).toBeInTheDocument()

    await user.type(
      screen.getByRole('textbox', { name: '描述绘图要求' }),
      '仅重试上个批次失败的任务：K19 改为 linear，不要重复成功项。',
    )
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    expect(runWorkflow).toHaveBeenCalledWith(expect.objectContaining({
      selectedSources: [
        { datasetId: 'source:temperature', sourceVersion: 1 },
        { datasetId: 'source:pressure', sourceVersion: 1 },
      ],
      instruction: '仅重试上个批次失败的任务：K19 改为 linear，不要重复成功项。',
    }))
    expect(runWorkflow.mock.calls.at(-1)?.[0]).not.toHaveProperty('selectedProfileIds')
    expect(runWorkflow.mock.calls.at(-1)?.[0]).not.toHaveProperty('selectedPlots')

    await user.type(
      screen.getByRole('textbox', { name: '描述绘图要求' }),
      '仅重试上个批次失败的任务：K19 改为 linear，不要重复成功项。',
    )
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    expect(runWorkflow).toHaveBeenCalledTimes(2)
    expect(runWorkflow.mock.calls.at(-1)?.[0]).toEqual(expect.objectContaining({
      selectedSources: [
        { datasetId: 'source:temperature', sourceVersion: 1 },
        { datasetId: 'source:pressure', sourceVersion: 1 },
      ],
      continuationWorkflowRunId: 'workflow:retry',
      instruction: '仅重试上个批次失败的任务：K19 改为 linear，不要重复成功项。',
    }))
  })

  it('renders a rejected persisted plan as non-executable', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop({
      listTaskPlans: vi.fn(async () => ok({ task_plans: [workflowPlanFixture('rejected', 'failed')] })),
    })
    installApi(api)
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))

    expect(await screen.findByText('已拒绝')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /执行|继续/ })).not.toBeInTheDocument()
  })

  it('rejects a revised plan without claiming that earlier successful items vanished', async () => {
    const user = userEvent.setup()
    const pendingRevision = workflowPlanFixture(
      'awaiting_reconfirmation',
      'succeeded',
      { planId: 'plan:revision', plotVersion: 2 },
    )
    const rejectedRevision = workflowPlanFixture(
      'rejected',
      'succeeded',
      { planId: 'plan:revision', plotVersion: 2 },
    )
    installApi(fakeDesktop({
      listTaskPlans: vi.fn(async () => ok({ task_plans: [pendingRevision] })),
      confirmTaskPlan: vi.fn(async () => ok(rejectedRevision)),
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))

    await user.click(await screen.findByRole('button', { name: '拒绝修订计划' }))

    expect(await screen.findByText('计划已拒绝')).toBeInTheDocument()
    expect(screen.getByText('未执行修订计划；已保留此前完成的 1 项结果。')).toBeInTheDocument()
    expect(screen.getByText('已拒绝')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '确认修订计划' })).not.toBeInTheDocument()
  })

  it('turns a rejected current plan into non-executable conversation history', async () => {
    const user = userEvent.setup()
    const pendingPlan = workflowPlanFixture('awaiting_confirmation')
    const rejectedPlan = workflowPlanFixture('rejected', 'failed')
    installApi(fakeDesktop({
      runWorkflow: vi.fn(async () => ok(workflowResultWithPlan(pendingPlan))),
      confirmTaskPlan: vi.fn(async () => ok(rejectedPlan)),
    }))
    render(<App />)
    await openSampleAndCreatePlot(user)
    await user.type(screen.getByRole('textbox', { name: '描述绘图要求' }), '新建一张折线图')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))
    await user.click(await screen.findByRole('button', { name: '取消' }))

    expect(await screen.findByText('计划已拒绝')).toBeInTheDocument()
    expect(screen.getByText('已拒绝')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '确认并执行' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '修改绑定' })).not.toBeInTheDocument()
  })

  it.each([
    ['task_plan', workflowResultWithPlan(workflowPlanFixture()), '任务计划'],
    ['needs_input', { outcome: 'needs_input', workflow_run_id: 'workflow:test', questions: [{ question_key: 'legend_position', prompt: '“上面”是指图内还是图外？', answer_kind: 'text', choices: [], required: true }] }, '需要补充信息'],
    ['unsupported', { outcome: 'unsupported', workflow_run_id: 'workflow:test', reason_code: 'CAPABILITY_UNAVAILABLE', message: '不提供通用非线性拟合。' }, '当前不支持'],
  ])('shows the Agent %s outcome', async (_kind, decision, expectedTitle) => {
    const user = userEvent.setup()
    installApi(fakeDesktop({ runWorkflow: vi.fn(async () => ok(decision)) }))
    render(<App />)
    await openSampleAndCreatePlot(user)
    await user.type(screen.getByRole('textbox', { name: '描述绘图要求' }), 'Y axis 改为 log10')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))
    expect(await screen.findByText(expectedTitle)).toBeInTheDocument()
    if (_kind !== 'task_plan') {
      await waitFor(() => expect(
        Array.from({ length: window.localStorage.length }, (_, index) => window.localStorage.getItem(window.localStorage.key(index) ?? '')).join('\n'),
      ).toContain(expectedTitle))
    }
  })

  it('keeps deterministic workflows available when no model service is configured', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop({ getProviderStatus: vi.fn(async () => ok({ configured: false, mode: 'local_only' })) })
    installApi(api)
    render(<App />)
    expect(await screen.findByRole('button', { name: '模型服务 未配置' })).toBeInTheDocument()
    await openSampleAndCreatePlot(user)
    const instruction = screen.getByRole('textbox', { name: '描述绘图要求' })
    expect(instruction).toBeEnabled()
    await user.type(instruction, '把图例移到右侧')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))
    expect(await screen.findByRole('heading', { name: '任务计划' })).toBeInTheDocument()
    expect(api.runWorkflow).toHaveBeenCalled()
    expect(api.configureCustomProvider).not.toHaveBeenCalled()
  })

  it('updates task count from real task events', async () => {
    render(<App />)
    await screen.findByRole('region', { name: '开始使用 PlotAgent' })
    act(() => taskListener?.({ schemaVersion: DESKTOP_API_VERSION, eventType: 'task.state', taskId: 'task:one', sequence: 1, state: 'running', progress: { completed: 1, total: 3, unit: 'plots' } }))
    expect(screen.getByRole('button', { name: /任务中心.*1/ })).toBeInTheDocument()
  })

  it('refreshes the durable checkpoint when an Agent runtime reaches a failed terminal state', async () => {
    const user = userEvent.setup()
    const failedTask = {
      task_id: 'task:provider-failed',
      task_version: 3,
      state: 'failed',
      project_revision: 1,
      updated_at: '2026-08-19T06:00:00Z',
      items: [{
        item_id: 'item:provider-failed.1',
        state: 'failed',
        attempt_count: 0,
        last_error: {
          code: 'PI_V2_PROVIDER_FAILED',
          message: '模型服务余额不足',
          retryable: true,
        },
      }],
    }
    const listTaskPlans = vi.fn()
      .mockResolvedValueOnce(ok({ task_plans: [], durable_tasks: [] }))
      .mockResolvedValue(ok({ task_plans: [], durable_tasks: [failedTask] }))
    const api = fakeDesktop({ listTaskPlans })
    installApi(api)
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))
    await waitFor(() => expect(workflowRuntimeListener).toBeDefined())

    act(() => workflowRuntimeListener?.({
      schemaVersion: '1.0',
      runId: 'workflow:provider-failed',
      projectId: 'project:sample',
      taskId: 'task:provider-failed',
      sequence: 4,
      stage: 'failed',
      label: 'Agent 运行失败',
    }))

    await waitFor(() => expect(listTaskPlans).toHaveBeenCalledTimes(2))
    await user.click(screen.getByRole('button', { name: /任务中心/ }))
    const drawer = screen.getByRole('dialog', { name: '任务中心' })
    await user.click(within(drawer).getByRole('button', { name: /全部/ }))
    expect(within(drawer).getByText('模型服务余额不足')).toBeInTheDocument()
    expect(within(drawer).queryByRole('button', { name: '停止任务' })).not.toBeInTheDocument()
  })

  it('projects the refreshed cancelled checkpoint before describing retained results', async () => {
    const user = userEvent.setup()
    const cancelledTask: JsonValue = {
      task_id: 'task:cancel-boundary',
      task_version: 7,
      state: 'cancelled',
      project_revision: 2,
      updated_at: '2026-08-20T08:00:00Z',
      items: [{
        item_id: 'item:cancel-boundary.1',
        state: 'succeeded',
        attempt_count: 1,
        output_plot_id: 'plot:retained',
        output_plot_version: 1,
      }, {
        item_id: 'item:cancel-boundary.2',
        state: 'cancelled',
        attempt_count: 0,
      }],
    }
    const listTaskPlans = vi.fn()
      .mockResolvedValueOnce(ok({ task_plans: [], durable_tasks: [] }))
      .mockResolvedValue(ok({ task_plans: [], durable_tasks: [cancelledTask] }))
    const cancelTask = vi.fn(actionOk)
    installApi(fakeDesktop({ listTaskPlans, cancelTask }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))
    await waitFor(() => expect(workflowRuntimeListener).toBeDefined())
    act(() => workflowRuntimeListener?.({
      schemaVersion: '1.0',
      runId: 'workflow:cancel-boundary',
      projectId: 'project:sample',
      taskId: 'task:cancel-boundary',
      sequence: 2,
      stage: 'planning',
      label: 'Agent 正在规划…',
    }))
    await user.click(screen.getByRole('button', { name: /任务中心/ }))
    await user.click(within(screen.getByRole('dialog', { name: '任务中心' }))
      .getByRole('button', { name: '停止任务' }))

    expect(cancelTask).toHaveBeenCalledWith('task:cancel-boundary')
    expect(await screen.findByText('任务已停止，已保留 1 项成功结果。')).toBeInTheDocument()
  })

  it('continues an interrupted planning task from the task center', async () => {
    const user = userEvent.setup()
    const resumeAgentTask = vi.fn(async () => ok(
      workflowResultWithPlan(workflowPlanFixture()),
    ))
    installApi(fakeDesktop({
      listTaskPlans: vi.fn(async () => ok({
        task_plans: [],
        durable_tasks: [{
          task_id: 'task:restart-planning',
          task_version: 4,
          state: 'investigating',
          project_revision: 1,
          items: [],
        }],
      })),
      resumeAgentTask,
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))
    await user.click(screen.getByRole('button', { name: /任务中心/ }))
    await user.click(within(screen.getByRole('dialog', { name: '任务中心' }))
      .getByRole('button', { name: '继续任务' }))

    expect(resumeAgentTask).toHaveBeenCalledWith('task:restart-planning')
    expect(await screen.findByRole('heading', { name: '任务计划' })).toBeInTheDocument()
  })
})
