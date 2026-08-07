import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  DESKTOP_API_VERSION,
  type DesktopActionResult,
  type DesktopBootstrap,
  type DesktopDataResult,
  type JsonValue,
  type PlotAgentDesktopApi,
  type TaskEvent,
} from '../../shared/desktop-contract'
import { App } from './App'

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
  row_count: 12,
  field_count: 3,
  fields: [
    { field_id: 'field:time', name: 'time_min', logical_type: 'numeric', physical_type: 'float64', unit: { symbol: 'min' } },
    { field_id: 'field:signal', name: 'fluorescence_au', logical_type: 'numeric', physical_type: 'float64', unit: { symbol: 'a.u.' } },
    { field_id: 'field:condition', name: 'condition', logical_type: 'categorical', physical_type: 'string', unit: null },
  ],
  quality: { missing_count: 0, nonfinite_count: 0 },
  source_coordinate_kinds: ['text_row'],
}

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
    createPlot: vi.fn(async (input) => ok({ project_id: input.projectId, project_version: 2, plot_id: 'plot:one', plot_version: 1, chart_type_id: input.chartId })),
    patchPlot: vi.fn(async () => ok({ project_version: 3, plot_id: 'plot:one', plot_version: 2, chart_type_id: 'K01' })),
    getPlot: vi.fn(async () => ok({ project_version: 2, plot_id: 'plot:one', plot_version: 1, chart_type_id: 'K01' })),
    renderPlot: vi.fn(async (input) => ok({ plot_id: input.plotId, plot_version: input.plotVersion, artifact: { resource: { resourceId: 'resource:preview', kind: 'preview', url: 'plotagent-resource://local/00000000-0000-0000-0000-000000000001', mimeType: 'image/png' } } })),
    createBatch: vi.fn(async () => ok({ task_id: 'task:batch', batch_id: 'batch:one', state: 'queued', project_version: 2 })),
    runBatch: vi.fn(async () => ok({ task_id: 'task:batch', batch_id: 'batch:one', state: 'succeeded', project_version: 4, items: [{ item_id: 'item.1', state: 'succeeded' }] })),
    getBatch: vi.fn(async () => ok({ batch_id: 'batch:one', state: 'succeeded' })),
    createFigure: vi.fn(async () => ok({ project_version: 5, figure: { figure_id: 'figure:one', figure_version: 1 } })),
    getFigure: vi.fn(async () => ok({ figure: { figure_id: 'figure:one', figure_version: 1 } })),
    renderFigure: vi.fn(async () => ok({ figure_id: 'figure:one', figure_version: 1, artifact: { resource: { resourceId: 'resource:figure', kind: 'preview', url: 'plotagent-resource://local/00000000-0000-0000-0000-000000000002' } } })),
    decideAgent: vi.fn(async () => ok({ accepted: true, decision: { decision_type: 'action_plan', plan_id: 'plan:one', actions: [] }, execution: { project_version: 3, plot_id: 'plot:one', plot_version: 2, chart_type_id: 'K01' } })),
    exportPngSvg: vi.fn(async () => ok({ export_id: 'export:one', artifact: { resource: { resourceId: 'resource:export', kind: 'export', fileName: 'plot.png' } } })),
    exportOrigin: vi.fn(async () => ok({ export_id: 'export:origin', result: { status: 'succeeded' } })),
    respondToCloseRequest: vi.fn(actionOk),
    onCoreStatus: vi.fn(() => () => undefined),
    onTaskEvent: vi.fn((listener) => { taskListener = listener; return () => { taskListener = undefined } }),
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
  await user.click(screen.getByRole('button', { name: '确认映射并绘图' }))
  expect(await screen.findByRole('img', { name: '折线图 真实渲染预览' })).toHaveAttribute('src', expect.stringMatching(/^plotagent-resource:/))
}

beforeEach(() => {
  taskListener = undefined
  window.localStorage.clear()
  installApi(fakeDesktop())
})

describe('PlotAgent real desktop workflow', () => {
  it('starts with three local entry points and no account or invitation gate', async () => {
    render(<App />)
  expect(await screen.findByRole('region', { name: '开始使用 PlotAgent' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '示例' })).toBeEnabled()
    expect(screen.getByRole('button', { name: /^导入/ })).toBeEnabled()
    expect(screen.getByRole('button', { name: '打开已有 .plotproj' })).toBeEnabled()
    expect(screen.getByText(/无需账号/)).toBeInTheDocument()
    expect(screen.queryByText(/邀请已激活/)).not.toBeInTheDocument()
  })

  it('provides a development-only interactive browser preview without a desktop bridge', async () => {
    const user = userEvent.setup()
    Reflect.deleteProperty(window, 'plotAgentDesktop')
    render(<App />)

    expect(screen.getByText('PlotAgent · 开发预览')).toBeInTheDocument()
    const sampleButton = screen.getByRole('button', { name: '示例' })
    await waitFor(() => expect(sampleButton).toBeEnabled())
    await user.click(sampleButton)

    expect(await screen.findByRole('heading', { name: 'source:sample-sheet-1' })).toBeInTheDocument()
    expect(screen.getAllByText(/内存示例数据/).length).toBeGreaterThan(0)
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K01')
    await user.click(screen.getByRole('button', { name: /K01.*折线图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    await user.click(screen.getByRole('button', { name: '确认映射并绘图' }))

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
    expect(screen.getByRole('heading', { name: '导入数值数据' })).toBeInTheDocument()
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
    const trigger = await screen.findByRole('button', { name: /Agent 服务/ })
    await user.click(trigger)
    expect(screen.getByRole('dialog', { name: '模型服务' })).toBeInTheDocument()
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

  it('imports real Core fields, confirms one mapping, and displays a controlled preview resource', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop()
    installApi(api)
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /^导入/ }))
    expect(await screen.findByText('fluorescence_au')).toBeInTheDocument()
    expect(screen.getAllByText('float64', { exact: true })).toHaveLength(2)
    expect(screen.getByText('a.u.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '选择图形' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K01')
    await user.click(screen.getByRole('button', { name: /K01.*折线图/ }))
    await user.click(screen.getByRole('button', { name: '选择此图形' }))
    expect(screen.getByRole('heading', { name: '确认字段映射' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '确认映射并绘图' }))
    expect(api.createPlot).toHaveBeenCalledWith(expect.objectContaining({ chartId: 'K01', fieldMapping: { roles: { x: 'field:time', y: 'field:signal' } } }))
    expect(await screen.findByRole('img')).toHaveAttribute('src', expect.stringMatching(/^plotagent-resource:/))
  })

  it.each([
    ['clarification', { kind: 'clarification', prompt: '第 3 行和第 4 行都可能是表头，请选择后重新导入。' }, '导入需要确认'],
    ['rejection', { kind: 'rejection', message: '文件中没有可识别的数值数据块。' }, '数据未导入'],
  ])('renders an actionable import %s instead of fake data', async (_kind, result, expectedTitle) => {
    const user = userEvent.setup()
    installApi(fakeDesktop({ importDatasets: vi.fn(async () => ok(result)) }))
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /^导入/ }))
    expect(await screen.findByText(expectedTitle)).toBeInTheDocument()
    expect(screen.queryByText('source:temperature')).not.toBeInTheDocument()
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
    expect(api.exportPngSvg).toHaveBeenCalledWith({ projectId: 'project:sample', target: { kind: 'plot', id: 'plot:one', version: 1 }, format: 'png' })
    expect(await screen.findAllByText('已导出 PNG')).not.toHaveLength(0)
    expect(document.body.textContent).not.toMatch(/[A-Za-z]:\\/)
  })

  it('reuses the confirmed mapping unchanged for a batch and exports the real batch target', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop()
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.click(screen.getByRole('button', { name: /创建批次/ }))
    expect(api.createBatch).toHaveBeenCalledWith(expect.objectContaining({
      chartId: 'K01',
      fieldMapping: { roles: { x: 'field:time', y: 'field:signal' } },
    }))
    expect(await screen.findByText(/批次 batch:one/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /导出批次 OPJU/ }))
    expect(api.exportOrigin).toHaveBeenCalledWith({
      projectId: 'project:sample',
      target: { kind: 'batch', id: 'batch:one', version: 1 },
    })
  })

  it('sends a batch Agent instruction to the batch target without changing the current plot', async () => {
    const user = userEvent.setup()
    const decideAgent = vi.fn(async () => ok({
      accepted: true,
      decision: { decision_type: 'action_plan', plan_id: 'plan:batch', actions: [] },
      executions: [
        { plot_id: 'plot:one', plot_version: 2, chart_type_id: 'K01' },
        { plot_id: 'plot:two', plot_version: 2, chart_type_id: 'K01' },
      ],
      scope_execution: {
        target_kind: 'batch',
        target_id: 'batch:one',
        target_version: 2,
        project_version: 6,
        updated_plot_count: 2,
        batch: { item_states: [{ item_id: 'item.1', state: 'succeeded' }] },
      },
    }))
    const api = fakeDesktop({ decideAgent })
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)
    await user.click(screen.getByRole('button', { name: /创建批次/ }))
    await screen.findByText(/批次 batch:one/)

    await user.click(screen.getByRole('button', { name: '整个批次' }))
    await user.type(screen.getByRole('textbox', { name: '描述绘图修改要求' }), '统一 line width 为 1.5 pt')
    await user.click(screen.getByRole('button', { name: '发送绘图指令' }))

    expect(decideAgent).toHaveBeenCalledWith(expect.objectContaining({
      target: { kind: 'batch', id: 'batch:one' },
      scope: 'batch',
    }))
    expect(await screen.findByText(/共创建 2 个可追溯版本/)).toBeInTheDocument()
    expect(api.renderPlot).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: '检查批次' }))
    expect(await screen.findByText('批次 batch:one · 版本 2')).toBeInTheDocument()
  })

  it('keeps K25 out of field mapping and asks for two existing plot versions', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop()
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)

    await user.click(screen.getByRole('button', { name: '选择其他图形' }))
    await user.clear(screen.getByRole('textbox', { name: '搜索图形库' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K25')
    await user.click(screen.getByRole('button', { name: /K25.*多面板复合图/ }))
    expect(screen.getByText(/不进入数据字段映射或 plots.create/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '创建组合图' }))

    expect(await screen.findByText('还需要一张图')).toBeInTheDocument()
    expect(api.createPlot).toHaveBeenCalledTimes(1)
    expect(api.createFigure).not.toHaveBeenCalled()
  })

  it('creates K25 from two fixed plot versions instead of calling plots.create', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop()
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)
    await user.type(screen.getByRole('textbox', { name: '描述绘图修改要求' }), '把线宽改为 1.5 pt')
    await user.click(screen.getByRole('button', { name: '发送绘图指令' }))
    await screen.findByText('修改已通过本地校验')

    await user.click(screen.getByRole('button', { name: '选择其他图形' }))
    await user.clear(screen.getByRole('textbox', { name: '搜索图形库' }))
    await user.type(screen.getByRole('textbox', { name: '搜索图形库' }), 'K25')
    await user.click(screen.getByRole('button', { name: /K25.*多面板复合图/ }))
    await user.click(screen.getByRole('button', { name: '创建组合图' }))

    expect(api.createFigure).toHaveBeenCalledWith(expect.objectContaining({
      plotRefs: [
        { plotId: 'plot:one', plotVersion: 1 },
        { plotId: 'plot:one', plotVersion: 2 },
      ],
      layout: '1x2',
    }))
    expect(api.createPlot).toHaveBeenCalledTimes(1)
    expect(await screen.findByText(/组合图 figure:one/)).toBeInTheDocument()
  })

  it.each([
    ['action_plan', { accepted: true, decision: { decision_type: 'action_plan', plan_id: 'plan:one', actions: [] }, execution: { project_version: 3, plot_id: 'plot:one', plot_version: 2, chart_type_id: 'K01' } }, '修改已通过本地校验'],
    ['needs_input', { accepted: true, decision: { decision_type: 'needs_input', questions: [{ prompt: '“上面”是指图内还是图外？' }] } }, '需要补充信息'],
    ['unsupported', { accepted: true, decision: { decision_type: 'unsupported', message: '不提供通用非线性拟合。' } }, '当前不支持'],
    ['rejected', { accepted: false, error: { code: 'AGENT_OUTPUT_REJECTED', message: '结果未通过本地权限校验。' } }, '指令未执行'],
  ])('shows the Agent %s outcome', async (_kind, decision, expectedTitle) => {
    const user = userEvent.setup()
    installApi(fakeDesktop({ decideAgent: vi.fn(async () => ok(decision)) }))
    render(<App />)
    await openSampleAndCreatePlot(user)
    await user.type(screen.getByRole('textbox', { name: '描述绘图修改要求' }), 'Y axis 改为 log10')
    await user.click(screen.getByRole('button', { name: '发送绘图指令' }))
    expect(await screen.findByText(expectedTitle)).toBeInTheDocument()
  })

  it('blocks Agent until a custom provider is explicitly configured', async () => {
    const user = userEvent.setup()
    const api = fakeDesktop({ getProviderStatus: vi.fn(async () => ok({ configured: false, mode: 'local_only' })) })
    installApi(api)
    render(<App />)
    await openSampleAndCreatePlot(user)
    expect(screen.getByRole('textbox', { name: '描述绘图修改要求' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '配置模型服务' }))
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
