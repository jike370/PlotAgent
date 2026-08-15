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
    { field_id: 'field:time', name: 'time_min', logical_type: 'numeric', physical_type: 'float64', unit: { symbol: 'min' } },
    { field_id: 'field:signal', name: 'fluorescence_au', logical_type: 'numeric', physical_type: 'float64', unit: { symbol: 'a.u.' } },
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
  content_hash: 'c'.repeat(64),
  fields: dataset.fields.map((field) => ({
    ...field,
    field_id: field.field_id.replace('field:', 'field:pressure.'),
  })),
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
        { operation: 'set_series_style', parameters: ['color', 'line_width_pt', 'line_style'] },
        { operation: 'set_legend', parameters: ['visible', 'anchor'] },
      ],
    },
    readback: { objects: [{ semantic_id: `series:${token}.primary` }] },
    preview: { resourceId: 'resource:preview', kind: 'preview', url: 'plotagent-resource://local/00000000-0000-0000-0000-000000000001', mimeType: 'image/png' },
  }
}

function agentPlanFixture(
  state = 'needs_confirmation',
  stepState = state === 'succeeded' ? 'succeeded' : 'pending',
  options: { planId?: string; plotVersion?: number; failure?: JsonValue } = {},
): JsonValue {
  const planId = options.planId ?? 'plan:one'
  const plotVersion = options.plotVersion
  const action = {
    operation: 'set_title',
    action_id: 'action:one',
    target_alias: 'active_target',
    patches: [{ operation: 'set_plot_title', target_alias: 'active_target', title: '更新后的标题' }],
  }
  return {
    plan_id: planId,
    state,
    confirmation_state: state === 'needs_confirmation' ? 'pending' : 'confirmed',
    next_action_index: state === 'succeeded' ? 1 : 0,
    current_project_revision: 2,
    error_code: options.failure === undefined ? null : 'SYNTHETIC_FAILURE',
    proposal: {
      schema_version: 'engine-agent.v1',
      decision_type: 'action_plan',
      plan_id: planId,
      target_alias: 'active_target',
      actions: [action],
    },
    bound_plan: {
      plan_id: planId,
      expected_project_revision: 2,
      actions: [{
        operation: 'set_title',
        action_id: 'action:one',
        target: 'plot:one',
        expected_plot_version: plotVersion === undefined ? 1 : plotVersion - 1,
        text: 'Updated title',
      }],
    },
    items: [{
      task_item_id: 'taskitem:one',
      action,
      state: stepState,
      attempt_count: stepState === 'pending' ? 0 : 1,
      outputs: plotVersion === undefined ? [] : [{ object_ref: { object_type: 'plot', object_id: 'plot:one', object_version: plotVersion } }],
      ...(options.failure === undefined ? {} : { failure: options.failure }),
    }],
  }
}

function agentDecisionWithPlan(plan: JsonValue): JsonValue {
  return {
    accepted: true,
    decision: { decision_type: 'action_plan', plan_id: 'plan:one', actions: [] },
    task_plan: plan,
  }
}

function batchPlanFixture(state = 'needs_confirmation'): JsonValue {
  const proposalAction = {
    operation: 'create_plot',
    action_id: 'action:batch',
    plot_alias: 'plot_1',
    profile_id: 'K01',
    source_alias: 'source_1',
    bindings: [
      { role: 'x', field_alias: 'field_1' },
      { role: 'y', field_alias: 'field_2' },
    ],
  }
  return {
    plan_id: 'plan:batch',
    state,
    confirmation_state: state === 'needs_confirmation' ? 'pending' : 'confirmed',
    next_action_index: state === 'succeeded' ? 1 : 0,
    current_project_revision: state === 'succeeded' ? 3 : 2,
    error_code: null,
    proposal: {
      schema_version: 'engine-agent.v1',
      decision_type: 'action_plan',
      plan_id: 'plan:batch',
      target_alias: 'source_1',
      actions: [proposalAction],
    },
    bound_plan: {
      plan_id: 'plan:batch',
      expected_project_revision: 2,
      actions: [{
        operation: 'create_plot',
        action_id: 'action:batch',
        plot_id: 'plot:batch.one',
        profile_id: 'K01',
        data: { kind: 'source', dataset_id: 'source:temperature', version: 1, content_hash: 'a'.repeat(64) },
        bindings: [{ role: 'x', field_id: 'field:time' }, { role: 'y', field_id: 'field:signal' }],
      }],
    },
  }
}

let coreListener: ((status: CoreStatus) => void) | undefined
let taskListener: ((event: TaskEvent) => void) | undefined

function fakeDesktop(overrides: Partial<PlotAgentDesktopApi> = {}): PlotAgentDesktopApi {
  const api: PlotAgentDesktopApi = {
    apiVersion: DESKTOP_API_VERSION,
    getBootstrap: vi.fn(readyBootstrap),
    getTasks: vi.fn(async () => ({ tasks: [], activeTaskCount: 0, hasCommittingTask: false })),
    cancelTask: vi.fn(actionOk),
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
    createPlotBatchPlan: vi.fn(async () => ok({ task_plan: batchPlanFixture() })),
    decideAgent: vi.fn(async () => ok(agentDecisionWithPlan(agentPlanFixture()))),
    getAgentPlan: vi.fn(async () => ok({})),
    listAgentPlans: vi.fn(async () => ok({ plans: [] })),
    confirmAgentPlan: vi.fn(async () => ok(agentPlanFixture('ready', 'ready'))),
    runAgentPlan: vi.fn(async () => ok({ task_plan: agentPlanFixture('succeeded', 'succeeded', { plotVersion: 2 }) })),
    resumeAgentPlan: vi.fn(async () => ok({ task_plan: agentPlanFixture('succeeded', 'succeeded', { plotVersion: 2 }) })),
    exportPngSvg: vi.fn(async () => ok({ export_id: 'export:one', artifact: { resource: { resourceId: 'resource:export', kind: 'export', fileName: 'plot.png' } } })),
    exportOrigin: vi.fn(async () => ok({ export_id: 'export:origin', result: { status: 'succeeded' } })),
    respondToCloseRequest: vi.fn(actionOk),
    onCoreStatus: vi.fn((listener) => { coreListener = listener; return () => { coreListener = undefined } }),
    onTaskEvent: vi.fn((listener) => { taskListener = listener; return () => { taskListener = undefined } }),
    onAgentRuntimeEvent: vi.fn(() => () => undefined),
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
  await user.click(screen.getByRole('button', { name: '手动映射' }))
  await user.click(screen.getByRole('button', { name: '确认并绘图' }))
  expect(await screen.findByRole('img', { name: '折线图 真实渲染预览' })).toHaveAttribute('src', expect.stringMatching(/^plotagent-resource:/))
  expect(screen.getByText('绘图完成')).toHaveClass('composer-success')
}

beforeEach(() => {
  coreListener = undefined
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
    await user.click(screen.getByRole('button', { name: '手动映射' }))
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
    expect(api.decideAgent).not.toHaveBeenCalled()
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
    expect(await screen.findByText('已选择图形')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '手动映射' }))
    expect(screen.getByRole('heading', { name: '数据预览与字段绑定' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '折线图' })).toBeInTheDocument()
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
    expect(screen.getByLabelText('Base URL')).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: '模型服务' })).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
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
    expect(screen.getByText('plot:alpha · v2')).toBeInTheDocument()
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
    expect(screen.getAllByText('浮点数', { exact: true })).toHaveLength(2)
    expect(screen.getByText('a.u.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K01')
    await user.click(screen.getByRole('button', { name: /K01.*折线图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.click(screen.getByRole('button', { name: '手动映射' }))
    expect(screen.getByRole('heading', { name: '数据预览与字段绑定' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '确认并绘图' }))
    expect(api.executePlotAction).toHaveBeenCalledWith(expect.objectContaining({
      expectedProjectVersion: 1,
      action: expect.objectContaining({
        operation: 'create_plot',
        profile_id: 'K01',
        bindings: [{ role: 'x', field_id: 'field:time' }, { role: 'y', field_id: 'field:signal' }],
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
    await user.click(screen.getByRole('button', { name: '手动映射' }))

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
    await user.click(screen.getByRole('button', { name: '手动映射' }))

    const review = screen.getByRole('group', { name: '数据预览与字段绑定' })
    await user.click(within(review).getByRole('button', { name: '取消' }))

    expect(screen.queryByRole('group', { name: '数据预览与字段绑定' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '手动映射' })).toBeEnabled()
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
    await user.click(screen.getByRole('button', { name: '手动映射' }))

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
    expect(screen.getByRole('status', { name: '导出记录' })).toHaveTextContent('export:one')
    expect(document.body.textContent).not.toMatch(/[A-Za-z]:\\/)
  })

  it('keeps OPJU progress explicit and announces a durable completion result', async () => {
    const user = userEvent.setup()
    let finishExport: ((result: DesktopDataResult) => void) | undefined
    const exportOrigin = vi.fn(() => new Promise<DesktopDataResult>((resolve) => { finishExport = resolve }))
    const api = fakeDesktop({ exportOrigin })
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.click(screen.getByRole('button', { name: '导出 OPJU' }))
    expect(await screen.findByText('正在生成并验证 OPJU…')).toBeInTheDocument()
    expect(screen.queryByText('OPJU 导出完成')).not.toBeInTheDocument()

    finishExport?.(ok({
      export_id: 'export:origin',
      plot_id: 'plot:one',
      artifact: { content_hash: 'b'.repeat(64), size: 29_999 },
    }))

    const result = await screen.findByRole('status', { name: '导出记录' })
    expect(result).toHaveTextContent('OPJU 导出完成')
    expect(result).toHaveTextContent('29,999 B')
    expect(result).toHaveTextContent('bbbbbbbbbbbb…')
    expect(screen.queryByText('正在生成并验证 OPJU…')).not.toBeInTheDocument()
    expect(screen.getByText('已导出 OPJU')).toHaveClass('composer-success')
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
      confirmAgentPlan: vi.fn(async () => ok(batchPlanFixture('ready'))),
      runAgentPlan: vi.fn(async () => ok({
        task_plan: batchPlanFixture('succeeded'),
        change_set: { plan_id: 'plan:batch', state: 'succeeded', items: [] },
      })),
    })
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.click(screen.getByRole('button', { name: /创建批次/ }))
    expect(api.createPlotBatchPlan).toHaveBeenCalledWith(expect.objectContaining({
      profileId: 'K01',
      datasets: [expect.objectContaining({
        bindings: { x: 'field:time', y: 'field:signal' },
      })],
    }))
    expect(await screen.findByRole('heading', { name: '任务计划' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).toHaveTextContent('字段绑定')
    expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).toHaveTextContent('时间')
    expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).toHaveTextContent('图形 K01')
    await user.click(screen.getByRole('button', { name: '确认并执行' }))
    expect(screen.getByRole('heading', { name: '任务计划' }).closest('section')).toHaveTextContent('已完成')
  })

  it('allows retry on a new target and ignores a late decision from the old target', async () => {
    const user = userEvent.setup()
    let finishOldDecision: ((result: DesktopDataResult) => void) | undefined
    const decideAgent = vi.fn()
      .mockImplementationOnce(() => new Promise<DesktopDataResult>((resolve) => { finishOldDecision = resolve }))
      .mockResolvedValueOnce(ok(agentDecisionWithPlan(agentPlanFixture('needs_confirmation', 'pending', { planId: 'plan:new' }))))
    installApi(fakeDesktop({ decideAgent }))
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
    expect(decideAgent).toHaveBeenLastCalledWith(expect.objectContaining({
      selectedChartId: 'K02',
      selectedDatasets: [{ datasetId: 'source:temperature', sourceVersion: 1 }],
      utterance: '新目标请求',
    }))

    await act(async () => {
      finishOldDecision?.(ok({
        accepted: false,
        decision: { decision_type: 'rejected', reason: '陈旧结果不应显示' },
      }))
    })
    expect(screen.queryByText('陈旧结果不应显示')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '任务计划' })).toBeInTheDocument()
  })

  it('keeps live Agent feedback and its confirmation card before the existing plot', async () => {
    const user = userEvent.setup()
    let finishDecision: ((result: DesktopDataResult) => void) | undefined
    const decideAgent = vi.fn(() => new Promise<DesktopDataResult>((resolve) => { finishDecision = resolve }))
    installApi(fakeDesktop({ decideAgent }))
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.type(screen.getByRole('textbox', { name: '描述绘图要求' }), '把标题改成温度响应')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    const activity = await screen.findByText('正在理解你的要求…')
    const plotCard = screen.getByRole('img', { name: '折线图 真实渲染预览' }).closest('section')
    expect(activity.closest('.message')?.compareDocumentPosition(plotCard as Node) ?? 0)
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING)

    await act(async () => {
      finishDecision?.(ok(agentDecisionWithPlan(agentPlanFixture())))
    })
    const planMessage = (await screen.findByRole('heading', { name: '任务计划' })).closest('.message')
    expect(planMessage?.compareDocumentPosition(plotCard as Node) ?? 0)
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
  })

  it('does not silently accumulate browsed worksheets in the Agent context', async () => {
    const user = userEvent.setup()
    const decideAgent = vi.fn(async () => ok(agentDecisionWithPlan(agentPlanFixture())))
    installApi(fakeDesktop({
      decideAgent,
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
    expect(decideAgent).toHaveBeenLastCalledWith(expect.objectContaining({
      sourceDatasetId: 'source:temperature',
      selectedDatasets: [{ datasetId: 'source:temperature', sourceVersion: 1 }],
    }))
  })

  it('lets an explicit multi-dataset request choose different chart types without a preselected chart', async () => {
    const user = userEvent.setup()
    const decideAgent = vi.fn(async (_input: unknown) => ok(agentDecisionWithPlan(batchPlanFixture())))
    installApi(fakeDesktop({
      decideAgent,
      openSampleProject: vi.fn(async () => ok({
        project: { project_id: 'project:sample', display_name: '多表项目', is_open: false },
        opened: { project_id: 'project:sample', project_version: 0, status: 'open' },
        imported: { kind: 'committed', project_version: 1, datasets: [dataset, secondDataset] },
      })),
    }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))

    await user.click(screen.getByText('提供给 Agent 的数据表'))
    await user.click(screen.getByRole('checkbox', { name: /source:pressure/ }))
    await user.type(
      screen.getByRole('textbox', { name: '描述绘图要求' }),
      '数据一画 K01 折线图，数据二画 K03 散点图',
    )
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))

    expect(await screen.findByRole('heading', { name: '任务计划' })).toBeInTheDocument()
    expect(decideAgent).toHaveBeenLastCalledWith(expect.objectContaining({
      sourceDatasetId: 'source:temperature',
      selectedDatasets: [
        { datasetId: 'source:temperature', sourceVersion: 1 },
        { datasetId: 'source:pressure', sourceVersion: 1 },
      ],
      utterance: '数据一画 K01 折线图，数据二画 K03 散点图',
    }))
    expect(decideAgent.mock.calls.at(-1)?.[0]).not.toHaveProperty('selectedChartId')
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

  it('offers the optional count role for an aggregated S61 confusion matrix', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'S61')
    await user.click(screen.getByRole('button', { name: /S61.*混淆矩阵/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.click(screen.getByRole('button', { name: '手动映射' }))
    const review = screen.getByRole('group', { name: '数据预览与字段绑定' })
    await user.click(within(review).getByRole('button', { name: /时间 的绘图角色/ }))
    expect(screen.getByRole('menuitemradio', { name: '已聚合计数（可选）' })).toBeInTheDocument()
  })

  it('restores a partial plan and resumes only its unfinished work', async () => {
    const user = userEvent.setup()
    const partial = agentPlanFixture('partially_failed', 'failed', {
      failure: { code: 'ORIGIN_EXPORT_FAILED', message: 'OPJU 导出未完成。', retryable: true },
    })
    const resumeAgentPlan = vi.fn(async () => ok({
      task_plan: agentPlanFixture('succeeded', 'succeeded', { plotVersion: 2 }),
    }))
    const api = fakeDesktop({
      listAgentPlans: vi.fn(async () => ok({ plans: [partial] })),
      resumeAgentPlan,
    })
    installApi(api)
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))

    expect(await screen.findByText('部分完成')).toBeInTheDocument()
    expect(screen.getByText('该动作未完成，可以从这里继续执行。')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '继续未完成步骤' }))

    expect(resumeAgentPlan).toHaveBeenCalledWith({ projectId: 'project:sample', planId: 'plan:one' })
    expect(await screen.findByText('更改已保存')).toBeInTheDocument()
    expect(screen.getAllByText('plot:one · v2').length).toBeGreaterThan(0)
  })

  it('renders a stale persisted plan as non-executable', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop({
      listAgentPlans: vi.fn(async () => ok({ plans: [agentPlanFixture('stale', 'stale')] })),
    })
    installApi(api)
    render(<App />)
    await user.click(await screen.findByRole('button', { name: '示例' }))

    expect(await screen.findByText('作用对象已变化，请重新描述任务生成新计划。')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /执行|继续/ })).not.toBeInTheDocument()
  })

  it.each([
    ['action_plan', agentDecisionWithPlan(agentPlanFixture()), '任务计划'],
    ['needs_input', { accepted: true, decision: { decision_type: 'needs_input', questions: [{ question_key: 'legend_position', prompt: '“上面”是指图内还是图外？' }] } }, '需要补充信息'],
    ['unsupported', { accepted: true, decision: { decision_type: 'unsupported', message: '不提供通用非线性拟合。' } }, '当前不支持'],
    ['rejected', { accepted: false, error: { code: 'AGENT_OUTPUT_REJECTED', message: '结果未通过本地权限校验。' } }, '指令未执行'],
  ])('shows the Agent %s outcome', async (_kind, decision, expectedTitle) => {
    const user = userEvent.setup()
    installApi(fakeDesktop({ decideAgent: vi.fn(async () => ok(decision)) }))
    render(<App />)
    await openSampleAndCreatePlot(user)
    await user.type(screen.getByRole('textbox', { name: '描述绘图要求' }), 'Y axis 改为 log10')
    await user.click(screen.getByRole('button', { name: '生成任务计划' }))
    expect(await screen.findByText(expectedTitle)).toBeInTheDocument()
    if (_kind !== 'action_plan') {
      await waitFor(() => expect(
        Array.from({ length: window.localStorage.length }, (_, index) => window.localStorage.getItem(window.localStorage.key(index) ?? '')).join('\n'),
      ).toContain(expectedTitle))
    }
  })

  it('opens provider settings when an unconfigured user sends an Agent instruction', async () => {
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
    const dialog = screen.getByRole('dialog', { name: '模型服务' })
    await user.type(within(dialog).getByLabelText('Base URL'), 'https://provider.example/v1')
    await user.type(within(dialog).getByLabelText('Model ID'), 'research-model')
    await user.click(within(dialog).getByRole('checkbox'))
    await user.click(within(dialog).getByRole('button', { name: '保存模型服务' }))
    expect(api.configureCustomProvider).toHaveBeenCalledWith(expect.objectContaining({ baseUrl: 'https://provider.example/v1', modelId: 'research-model', retentionAcknowledged: true }))
  })

  it('updates task count from real task events', async () => {
    render(<App />)
    await screen.findByRole('region', { name: '开始使用 PlotAgent' })
    act(() => taskListener?.({ schemaVersion: DESKTOP_API_VERSION, eventType: 'task.state', taskId: 'task:one', sequence: 1, state: 'running', progress: { completed: 1, total: 3, unit: 'plots' } }))
    expect(screen.getByRole('button', { name: /任务中心.*1/ })).toBeInTheDocument()
  })
})
