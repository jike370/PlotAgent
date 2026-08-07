import {
  DESKTOP_API_VERSION,
  type DesktopActionResult,
  type DesktopDataResult,
  type JsonValue,
  type PlotAgentDesktopApi,
} from '../../../shared/desktop-contract'

type JsonRecord = { [key: string]: JsonValue }

interface PreviewProject {
  projectId: string
  name: string
  projectVersion: number
  isOpen: boolean
  lastOpenedAt: string
  datasets: JsonRecord[]
}

interface PreviewBatch {
  taskId: string
  batchId: string
  version: number
  projectId: string
  itemIds: string[]
}

const ok = (value: JsonValue): DesktopDataResult => ({ ok: true, value })
const actionOk = async (): Promise<DesktopActionResult> => ({ ok: true })

function missing(message: string): DesktopDataResult {
  return {
    ok: false,
    error: { code: 'RESOURCE_INVALID', message, retryable: false },
  }
}

function richText(text: string): JsonRecord {
  return { nodes: [{ kind: 'text', text }] }
}

function previewDataset(datasetId: string, label: string, index: number): JsonRecord {
  return {
    source_dataset_id: datasetId,
    source_version: 1,
    row_count: 24 + index * 8,
    field_count: 8,
    fields: [
      { field_id: `${datasetId}:time`, name: 'time_min', logical_type: 'numeric', physical_type: 'float64', unit: { symbol: 'min' } },
      { field_id: `${datasetId}:signal`, name: 'signal_au', logical_type: 'numeric', physical_type: 'float64', unit: { symbol: 'a.u.' } },
      { field_id: `${datasetId}:value`, name: 'value', logical_type: 'numeric', physical_type: 'float64', unit: { symbol: 'a.u.' } },
      { field_id: `${datasetId}:error`, name: 'error', logical_type: 'numeric', physical_type: 'float64', unit: { symbol: 'a.u.' } },
      { field_id: `${datasetId}:pvalue`, name: 'p_value', logical_type: 'numeric', physical_type: 'float64', unit: null },
      { field_id: `${datasetId}:group`, name: 'group', logical_type: 'categorical', physical_type: 'string', unit: null },
      { field_id: `${datasetId}:category`, name: 'category', logical_type: 'categorical', physical_type: 'string', unit: null },
      { field_id: `${datasetId}:label`, name: label, logical_type: 'categorical', physical_type: 'string', unit: null },
    ],
    quality: { missing_count: index === 2 ? 1 : 0, nonfinite_count: 0 },
    source_coordinate_kinds: ['preview_row'],
  }
}

function previewDatasets(prefix: string): JsonRecord[] {
  return [
    previewDataset(`source:${prefix}-sheet-1`, 'Sheet 1', 0),
    previewDataset(`source:${prefix}-sheet-2`, 'Sheet 2', 1),
    previewDataset(`source:${prefix}-sheet-3`, 'Sheet 3', 2),
  ]
}

function svgDataUrl(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}

function plotPreviewSvg(chartId: string, version: number): string {
  const points = [
    [92, 408], [190, 342], [288, 360], [386, 250], [484, 292], [582, 178], [680, 218], [778, 126],
  ].map(([x, y]) => `${x},${y}`).join(' ')
  return `<svg xmlns="http://www.w3.org/2000/svg" width="960" height="560" viewBox="0 0 960 560">
    <rect width="960" height="560" fill="#ffffff"/>
    <text x="56" y="48" fill="#171717" font-family="Arial, sans-serif" font-size="22" font-weight="600">${chartId} 科研图预览</text>
    <text x="904" y="48" text-anchor="end" fill="#777777" font-family="Arial, sans-serif" font-size="13">界面预览 · v${version}</text>
    <line x1="74" y1="468" x2="884" y2="468" stroke="#222222" stroke-width="2"/>
    <line x1="74" y1="78" x2="74" y2="468" stroke="#222222" stroke-width="2"/>
    <g stroke="#e5e5e5" stroke-width="1"><line x1="74" y1="370" x2="884" y2="370"/><line x1="74" y1="272" x2="884" y2="272"/><line x1="74" y1="174" x2="884" y2="174"/></g>
    <polyline points="${points}" fill="none" stroke="#246fce" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/>
    <g fill="#ffffff" stroke="#246fce" stroke-width="3">${points.split(' ').map((point) => {
      const [x, y] = point.split(',')
      return `<circle cx="${x}" cy="${y}" r="7"/>`
    }).join('')}</g>
    <text x="480" y="526" text-anchor="middle" fill="#333333" font-family="Arial, sans-serif" font-size="16">X</text>
    <text x="24" y="274" text-anchor="middle" transform="rotate(-90 24 274)" fill="#333333" font-family="Arial, sans-serif" font-size="16">Y</text>
  </svg>`
}

function figurePreviewSvg(version: number): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="960" height="560" viewBox="0 0 960 560">
    <rect width="960" height="560" fill="#ffffff"/>
    <text x="52" y="42" fill="#171717" font-family="Arial, sans-serif" font-size="18" font-weight="600">1×2 组合图</text>
    <text x="908" y="42" text-anchor="end" fill="#777777" font-family="Arial, sans-serif" font-size="13">界面预览 · v${version}</text>
    <g transform="translate(52 78)"><rect width="402" height="410" fill="#fff" stroke="#d6d6d6"/><line x1="48" y1="348" x2="362" y2="348" stroke="#222"/><line x1="48" y1="38" x2="48" y2="348" stroke="#222"/><polyline points="58,310 112,252 166,276 220,174 274,206 332,102" fill="none" stroke="#246fce" stroke-width="4"/><text x="18" y="28" font-family="Arial" font-size="16" font-weight="600">A</text></g>
    <g transform="translate(506 78)"><rect width="402" height="410" fill="#fff" stroke="#d6d6d6"/><line x1="48" y1="348" x2="362" y2="348" stroke="#222"/><line x1="48" y1="38" x2="48" y2="348" stroke="#222"/><rect x="76" y="202" width="56" height="146" fill="#246fce"/><rect x="174" y="132" width="56" height="216" fill="#df594e"/><rect x="272" y="82" width="56" height="266" fill="#5b9a67"/><text x="18" y="28" font-family="Arial" font-size="16" font-weight="600">B</text></g>
  </svg>`
}

function createBrowserPreviewApi(): PlotAgentDesktopApi {
  const projects = new Map<string, PreviewProject>()
  const plots = new Map<string, JsonRecord>()
  const batches = new Map<string, PreviewBatch>()
  const figures = new Map<string, { projectId: string; version: number }>()
  let projectSequence = 0
  let importSequence = 0
  let plotSequence = 0
  let batchSequence = 0
  let figureSequence = 0

  const projectSummary = (project: PreviewProject): JsonRecord => ({
    project_id: project.projectId,
    display_name: project.name,
    project_version: project.projectVersion,
    is_open: project.isOpen,
    last_opened_at: project.lastOpenedAt,
  })

  const createProject = (name: string, datasets: JsonRecord[] = []): PreviewProject => {
    projectSequence += 1
    const project: PreviewProject = {
      projectId: `project:preview-${projectSequence}`,
      name,
      projectVersion: datasets.length > 0 ? 1 : 0,
      isOpen: false,
      lastOpenedAt: new Date().toISOString(),
      datasets,
    }
    projects.set(project.projectId, project)
    return project
  }

  const plotKey = (projectId: string, plotId: string): string => `${projectId}:${plotId}`

  const api: PlotAgentDesktopApi = {
    apiVersion: DESKTOP_API_VERSION,
    getBootstrap: async () => ({
      apiVersion: DESKTOP_API_VERSION,
      platform: 'win32',
      core: { phase: 'ready', restartAttempt: 0 },
      tasks: { tasks: [], activeTaskCount: 0, hasCommittingTask: false },
    }),
    getTasks: async () => ({ tasks: [], activeTaskCount: 0, hasCommittingTask: false }),
    cancelTask: actionOk,
    retryCore: actionOk,
    getProviderStatus: async () => ok({ configured: true, mode: 'browser_preview' }),
    configureCustomProvider: async () => ok({ configured: true, mode: 'browser_preview' }),
    clearProvider: async () => ok({ configured: true, mode: 'browser_preview' }),
    listProjects: async () => ok({ projects: [...projects.values()].map(projectSummary) }),
    createProject: async ({ name }) => ok(projectSummary(createProject(name))),
    renameProject: async ({ projectId, name }) => {
      const project = projects.get(projectId)
      if (!project) return missing('界面预览中没有找到该项目。')
      project.name = name
      return ok(projectSummary(project))
    },
    deleteProject: async ({ projectId }) => {
      if (!projects.delete(projectId)) return missing('界面预览中没有找到该项目。')
      return ok({ project_id: projectId, status: 'deleted', cleanup_pending: false })
    },
    activateProject: async ({ projectId }) => {
      const project = projects.get(projectId)
      if (!project) return missing('界面预览中没有找到该项目。')
      project.isOpen = true
      project.lastOpenedAt = new Date().toISOString()
      return ok({ ...projectSummary(project), status: 'open' })
    },
    openProject: async () => {
      const project = createProject('已打开的示例项目', previewDatasets('opened'))
      project.isOpen = true
      return ok({ ...projectSummary(project), datasets: project.datasets, status: 'open' })
    },
    openProjectResource: async () => {
      const project = createProject('资源示例项目', previewDatasets('resource'))
      project.isOpen = true
      return ok({ ...projectSummary(project), datasets: project.datasets, status: 'open' })
    },
    openSampleProject: async () => {
      const project = createProject('温度响应示例', previewDatasets('sample'))
      project.isOpen = true
      return ok({
        project: projectSummary(project),
        opened: { ...projectSummary(project), status: 'open' },
        imported: { kind: 'committed', project_version: project.projectVersion, datasets: project.datasets },
      })
    },
    closeProject: async ({ projectId }) => {
      const project = projects.get(projectId)
      if (!project) return missing('界面预览中没有找到该项目。')
      project.isOpen = false
      return ok({ ...projectSummary(project), status: 'closed' })
    },
    importDatasets: async ({ projectId }) => {
      const project = projects.get(projectId)
      if (!project) return missing('界面预览中没有找到该项目。')
      importSequence += 1
      const imported = previewDatasets(`import-${importSequence}`)
      project.datasets = [...project.datasets, ...imported]
      project.projectVersion += 1
      return ok({ kind: 'committed', project_version: project.projectVersion, datasets: imported })
    },
    listDatasets: async ({ projectId }) => {
      const project = projects.get(projectId)
      return project ? ok({ ...projectSummary(project), datasets: project.datasets }) : missing('界面预览中没有找到该项目。')
    },
    describeDataset: async ({ projectId, datasetId }) => {
      const dataset = projects.get(projectId)?.datasets.find((item) => item.source_dataset_id === datasetId)
      return dataset ? ok({ dataset }) : missing('界面预览中没有找到该数据集。')
    },
    createPlot: async (input) => {
      const project = projects.get(input.projectId)
      if (!project) return missing('界面预览中没有找到该项目。')
      project.projectVersion += 1
      plotSequence += 1
      const plotId = `plot:preview-${plotSequence}`
      const record: JsonRecord = {
        project_id: project.projectId,
        project_version: project.projectVersion,
        plot_id: plotId,
        plot_version: 1,
        chart_type_id: input.chartId,
        title: richText(`${input.chartId} 科研图预览`),
        series: [{ series_id: 'series:preview-1', style: { color: { value: '#246fce' }, line_width: { value: 1.2 }, marker_size: { value: 5 } } }],
        axes: [
          { axis_id: 'axis:x', orientation: 'x', position: 'bottom', scale_id: 'scale:x', label: richText('X') },
          { axis_id: 'axis:y', orientation: 'y', position: 'left', scale_id: 'scale:y', label: richText('Y') },
        ],
        scales: [
          { scale_id: 'scale:x', kind: 'linear', axis_range: {}, ticks: { number_format: 'auto', decimal_places: 2 } },
          { scale_id: 'scale:y', kind: 'linear', axis_range: {}, ticks: { number_format: 'auto', decimal_places: 2 } },
        ],
        legend: { visible: true, position: 'best' },
        publication_profile: { physical_size: { width: { value: 183, unit: 'mm' }, height: { value: 120, unit: 'mm' } } },
        resolved_style: { font_size: { value: 9, unit: 'pt' } },
      }
      plots.set(plotKey(project.projectId, plotId), record)
      return ok(record)
    },
    patchPlot: async (input) => {
      const current = plots.get(plotKey(input.projectId, input.plotId))
      const project = projects.get(input.projectId)
      if (!current || !project) return missing('界面预览中没有找到该图形。')
      project.projectVersion += 1
      const updated = {
        ...current,
        project_version: project.projectVersion,
        plot_version: input.plotVersion + 1,
      } satisfies JsonRecord
      plots.set(plotKey(input.projectId, input.plotId), updated)
      return ok(updated)
    },
    getPlot: async ({ projectId, plotId }) => {
      const plot = plots.get(plotKey(projectId, plotId))
      return plot ? ok(plot) : missing('界面预览中没有找到该图形。')
    },
    renderPlot: async ({ projectId, plotId, plotVersion }) => {
      const plot = plots.get(plotKey(projectId, plotId))
      if (!plot) return missing('界面预览中没有找到该图形。')
      const chartId = typeof plot.chart_type_id === 'string' ? plot.chart_type_id : 'K01'
      return ok({
        plot_id: plotId,
        plot_version: plotVersion,
        artifact: { resource: { resourceId: `resource:preview-${plotId}-${plotVersion}`, kind: 'preview', url: svgDataUrl(plotPreviewSvg(chartId, plotVersion)), mimeType: 'image/svg+xml' } },
      })
    },
    createBatch: async (input) => {
      const project = projects.get(input.projectId)
      if (!project) return missing('界面预览中没有找到该项目。')
      project.projectVersion += 1
      batchSequence += 1
      const batch: PreviewBatch = {
        taskId: `task:preview-${batchSequence}`,
        batchId: `batch:preview-${batchSequence}`,
        version: 1,
        projectId: input.projectId,
        itemIds: input.datasets.map((_, index) => `item:${index + 1}`),
      }
      batches.set(batch.batchId, batch)
      return ok({ task_id: batch.taskId, batch_id: batch.batchId, state: 'queued', project_version: project.projectVersion, batch: { batch_version: batch.version } })
    },
    runBatch: async ({ projectId, taskId }) => {
      const batch = [...batches.values()].find((item) => item.projectId === projectId && item.taskId === taskId)
      const project = projects.get(projectId)
      if (!batch || !project) return missing('界面预览中没有找到该批次。')
      project.projectVersion += 1
      return ok({ task_id: batch.taskId, batch_id: batch.batchId, state: 'succeeded', project_version: project.projectVersion, batch: { batch_version: batch.version }, items: batch.itemIds.map((itemId) => ({ item_id: itemId, state: 'succeeded' })) })
    },
    getBatch: async ({ projectId, batchId }) => {
      const batch = batches.get(batchId)
      return batch && batch.projectId === projectId
        ? ok({ task_id: batch.taskId, batch_id: batch.batchId, state: 'succeeded', batch: { batch_version: batch.version }, items: batch.itemIds.map((itemId) => ({ item_id: itemId, state: 'succeeded' })) })
        : missing('界面预览中没有找到该批次。')
    },
    createFigure: async ({ projectId }) => {
      const project = projects.get(projectId)
      if (!project) return missing('界面预览中没有找到该项目。')
      project.projectVersion += 1
      figureSequence += 1
      const figureId = `figure:preview-${figureSequence}`
      figures.set(figureId, { projectId, version: 1 })
      return ok({ project_version: project.projectVersion, figure: { figure_id: figureId, figure_version: 1 } })
    },
    getFigure: async ({ projectId, figureId }) => {
      const figure = figures.get(figureId)
      return figure && figure.projectId === projectId
        ? ok({ figure: { figure_id: figureId, figure_version: figure.version } })
        : missing('界面预览中没有找到该组合图。')
    },
    renderFigure: async ({ projectId, figureId }) => {
      const figure = figures.get(figureId)
      if (!figure || figure.projectId !== projectId) return missing('界面预览中没有找到该组合图。')
      return ok({ figure: { figure_id: figureId, figure_version: figure.version }, artifact: { resource: { resourceId: `resource:${figureId}`, kind: 'preview', url: svgDataUrl(figurePreviewSvg(figure.version)), mimeType: 'image/svg+xml' } } })
    },
    decideAgent: async (input) => {
      const project = projects.get(input.projectId)
      if (!project) return missing('界面预览中没有找到该项目。')
      project.projectVersion += 1
      if (input.target.kind === 'plot') {
        const current = plots.get(plotKey(input.projectId, input.target.id))
        if (!current) return missing('界面预览中没有找到该图形。')
        const updated = { ...current, project_version: project.projectVersion, plot_version: (typeof current.plot_version === 'number' ? current.plot_version : 1) + 1 } satisfies JsonRecord
        plots.set(plotKey(input.projectId, input.target.id), updated)
        return ok({ accepted: true, project_version: project.projectVersion, decision: { decision_type: 'action_plan', plan_id: 'plan:preview', actions: [] }, execution: updated })
      }
      const nextVersion = input.target.kind === 'batch'
        ? (batches.get(input.target.id)?.version ?? 1) + 1
        : (figures.get(input.target.id)?.version ?? 1) + 1
      return ok({
        accepted: true,
        project_version: project.projectVersion,
        decision: { decision_type: 'action_plan', plan_id: 'plan:preview', actions: [] },
        scope_execution: { target_kind: input.target.kind, target_id: input.target.id, target_version: nextVersion, project_version: project.projectVersion, updated_plot_count: 1 },
      })
    },
    exportPngSvg: async ({ format }) => ok({ export_id: `export:preview-${format}`, preview_only: true }),
    exportOrigin: async () => ok({ export_id: 'export:preview-opju', preview_only: true }),
    respondToCloseRequest: actionOk,
    onCoreStatus: () => () => undefined,
    onTaskEvent: () => () => undefined,
    onOpenResourceRequested: () => () => undefined,
    onCloseRequested: () => () => undefined,
  }
  return api
}

let browserPreviewApi: PlotAgentDesktopApi | undefined

export function resolveDesktopRuntime(): { api?: PlotAgentDesktopApi; previewMode: boolean } {
  if (window.plotAgentDesktop) return { api: window.plotAgentDesktop, previewMode: false }
  if (!import.meta.env.DEV) return { previewMode: false }
  browserPreviewApi ??= createBrowserPreviewApi()
  return { api: browserPreviewApi, previewMode: true }
}
