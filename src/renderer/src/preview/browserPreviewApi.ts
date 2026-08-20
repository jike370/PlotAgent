import {
  DESKTOP_API_VERSION,
  type DesktopActionResult,
  type DesktopDataResult,
  type JsonValue,
  type PlotAgentDesktopApi,
} from '../../../shared/desktop-contract'

type JsonRecord = { [key: string]: JsonValue }

function isJsonRecord(value: JsonValue | undefined): value is JsonRecord {
  return value !== null && value !== undefined && typeof value === 'object' && !Array.isArray(value)
}

interface PreviewProject {
  projectId: string
  name: string
  projectVersion: number
  isOpen: boolean
  lastOpenedAt: string
  datasets: JsonRecord[]
}

interface PreviewWorkflowPlan {
  projectId: string
  planId: string
  input: Parameters<PlotAgentDesktopApi['runWorkflow']>[0]
  state: string
  outputPlot?: { plotId: string; plotVersion: number }
}

const ok = (value: JsonValue): DesktopDataResult => ({ ok: true, value })
const actionOk = async (): Promise<DesktopActionResult> => ({ ok: true })

function missing(message: string): DesktopDataResult {
  return {
    ok: false,
    error: { code: 'RESOURCE_INVALID', message, retryable: false },
  }
}

function previewDataset(datasetId: string, label: string, index: number): JsonRecord {
  return {
    source_dataset_id: datasetId,
    source_file_name: '示例数据.xlsx',
    source_sheet_name: label,
    source_version: 1,
    content_hash: `${index + 1}`.repeat(64),
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
    sample_rows: Array.from({ length: 5 }, (_, row) => [
      row + 1,
      Number((3.2 + index * 0.4 + row * 0.73).toFixed(3)),
      Number((12 + row * 2.5).toFixed(1)),
      Number((0.4 + row * 0.08).toFixed(2)),
      Number((0.05 / (row + 1)).toFixed(4)),
      row < 3 ? 'Control' : 'Treatment',
      `Category ${row + 1}`,
      `${label}-${row + 1}`,
    ]),
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

function createBrowserPreviewApi(): PlotAgentDesktopApi {
  const projects = new Map<string, PreviewProject>()
  const plots = new Map<string, JsonRecord>()
  const workflowPlans = new Map<string, PreviewWorkflowPlan>()
  let projectSequence = 0
  let importSequence = 0
  let plotSequence = 0
  let workflowPlanSequence = 0

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

  const workflowPlanRecord = (plan: PreviewWorkflowPlan): JsonRecord => {
    const projectVersion = projects.get(plan.projectId)?.projectVersion ?? 0
    const profileId = plan.input.selectedProfileIds?.[0] ?? 'K01'
    const source = plan.input.selectedSources[0]
    const token = plan.planId.startsWith('plan:') ? plan.planId.slice(5) : plan.planId
    const itemId = `item:${token}.1`
    return {
      state: plan.state,
      current_project_revision: projectVersion,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      plan: {
        schema_version: 'task-plan.v1',
        plan_id: plan.planId,
        workflow_run_id: `workflow:${token}`,
        draft_hash: 'a'.repeat(64),
        expected_project_revision: plan.input.expectedProjectVersion,
        items: [{
          item_id: itemId,
          plot_alias: 'plot_1',
          plot_id: plan.outputPlot?.plotId ?? `plot:workflow.${token}.1`,
          profile_id: profileId,
          sources: source === undefined ? [] : [{
            source_alias: 'data_1', source_dataset_id: source.datasetId,
            source_version: source.sourceVersion, content_hash: 'a'.repeat(64),
            display_name: source.datasetId, row_count: 5,
          }],
          resolved_fields: [], data_operations: [], bindings: [], visual_actions: [],
          exports: [], depends_on: [], idempotency_key: `preview.${itemId}`,
        }],
      },
      item_progress: [{
        item_id: itemId, state: plan.state === 'succeeded' ? 'succeeded' : 'pending',
        attempt_count: plan.state === 'succeeded' ? 1 : 0, error_code: null,
        output_plot_id: plan.outputPlot?.plotId ?? null,
        output_plot_version: plan.outputPlot?.plotVersion ?? null,
      }],
    }
  }

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
    acceptPartialTask: actionOk,
    resumeAgentTask: async () => missing('浏览器预览不运行真实 Agent 任务。'),
    retryCore: actionOk,
    getProviderStatus: async () => ok({ configured: true, mode: 'browser_preview' }),
    configureCustomProvider: async () => ok({ configured: true, mode: 'browser_preview' }),
    clearProvider: async () => ok({ configured: true, mode: 'browser_preview' }),
    getOriginStatus: async () => ok({
      status: 'ready',
      display_name: 'OriginPro',
      display_version: 'Preview',
      discovery_source: 'browser_preview',
    }),
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
    executePlotAction: async (input) => {
      const project = projects.get(input.projectId)
      if (!project) return missing('界面预览中没有找到该项目。')
      if (!isJsonRecord(input.action) || typeof input.action.operation !== 'string') {
        return missing('界面预览收到无效绘图动作。')
      }
      project.projectVersion += 1
      if (input.action.operation === 'create_plot') {
        plotSequence += 1
        const plotId = typeof input.action.plot_id === 'string'
          ? input.action.plot_id : `plot:preview-${plotSequence}`
        const profileId = typeof input.action.profile_id === 'string' ? input.action.profile_id : 'K01'
        const token = plotId.replace(/^plot:/, '')
        const record: JsonRecord = {
          project_id: project.projectId,
          project_version: project.projectVersion,
          plot_id: plotId,
          plot_version: 1,
          profile_id: profileId,
          plot_ref: {
            plot_id: plotId,
            plot_version: 1,
            content_hash: 'e'.repeat(64),
          },
          document: {
            schema_version: '2.0', plot_id: plotId, plot_version: 1, parent_version: null,
            profile_id: profileId, data: input.action.data,
            bindings: input.action.bindings ?? [],
            applied_action_ids: [input.action.action_id],
          },
          actions: [input.action],
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
                parameters: [
                  'line_stroke_color', 'line_width_pt', 'line_style',
                  'marker_shape', 'marker_size_pt',
                ],
              },
              { operation: 'set_legend', parameters: ['visible', 'anchor'] },
            ],
          },
          readback: { objects: [{ semantic_id: `series:${token}.primary` }] },
          preview: { resourceId: `resource:preview-${plotId}-1`, kind: 'preview', url: svgDataUrl(plotPreviewSvg(profileId, 1)), mimeType: 'image/svg+xml' },
        }
        plots.set(plotKey(project.projectId, plotId), record)
        return ok(record)
      }
      const target = typeof input.action.target === 'string' ? input.action.target : ''
      const current = [...plots.values()].find((candidate) => {
        const document = isJsonRecord(candidate.document) ? candidate.document : {}
        const plotId = typeof document.plot_id === 'string' ? document.plot_id : ''
        const token = plotId.replace(/^plot:/, '')
        return target === plotId || target.startsWith(`axis:${token}.`)
          || target.startsWith(`series:${token}.`) || target.startsWith(`legend:${token}.`)
      })
      if (!current || !isJsonRecord(current.document)) return missing('界面预览中没有找到该图形。')
      const nextVersion = (typeof current.document.plot_version === 'number'
        ? current.document.plot_version : 1) + 1
      const actions = Array.isArray(current.actions) ? [...current.actions, input.action] : [input.action]
      const updated: JsonRecord = {
        ...current,
        project_version: project.projectVersion,
        plot_version: nextVersion,
        document: {
          ...current.document,
          plot_version: nextVersion,
          parent_version: nextVersion - 1,
          applied_action_ids: actions.flatMap((action) => isJsonRecord(action)
            && typeof action.action_id === 'string' ? [action.action_id] : []),
        },
        actions,
        preview: { resourceId: `resource:preview-${current.document.plot_id}-${nextVersion}`, kind: 'preview', url: svgDataUrl(plotPreviewSvg(String(current.profile_id ?? 'K01'), nextVersion)), mimeType: 'image/svg+xml' },
      }
      plots.set(plotKey(input.projectId, String(current.document.plot_id)), updated)
      return ok(updated)
    },
    getPlot: async ({ projectId, plotId }) => {
      const plot = plots.get(plotKey(projectId, plotId))
      return plot ? ok(plot) : missing('界面预览中没有找到该图形。')
    },
    listPlots: async ({ projectId }) => ok({
      project_id: projectId,
      project_version: projects.get(projectId)?.projectVersion ?? 0,
      plots: [...plots.values()].filter((plot) => plot.project_id === projectId),
    }),
    runWorkflow: async (input) => {
      const project = projects.get(input.projectId)
      if (!project) return missing('界面预览中没有找到该项目。')
      workflowPlanSequence += 1
      const plan: PreviewWorkflowPlan = {
        projectId: input.projectId,
        planId: `plan:preview-${workflowPlanSequence}`,
        input,
        state: 'awaiting_confirmation',
      }
      workflowPlans.set(plan.planId, plan)
      return ok({ outcome: 'draft_ready', task_plan: workflowPlanRecord(plan) })
    },
    getTaskPlan: async ({ planId }) => {
      const plan = workflowPlans.get(planId)
      return plan === undefined ? missing('未找到任务计划。') : ok(workflowPlanRecord(plan))
    },
    listTaskPlans: async ({ projectId }) => ok({
      task_plans: [...workflowPlans.values()]
        .filter((plan) => plan.projectId === projectId)
        .map(workflowPlanRecord),
    }),
    confirmTaskPlan: async ({ planId, accept }) => {
      const plan = workflowPlans.get(planId)
      if (plan === undefined) return missing('未找到任务计划。')
      if (!accept) {
        plan.state = 'rejected'
        return ok(workflowPlanRecord(plan))
      }
      plan.state = 'ready'
      return ok(workflowPlanRecord(plan))
    },
    runTaskPlan: async ({ projectId, planId }) => {
      const plan = workflowPlans.get(planId)
      const project = projects.get(projectId)
      if (plan === undefined || project === undefined) return missing('未找到任务计划。')
      const source = plan.input.selectedSources[0]
      if (source === undefined) return missing('预览计划缺少数据来源。')
      const created = await api.executePlotAction({
        projectId,
        expectedProjectVersion: project.projectVersion,
        action: {
          operation: 'create_plot', action_id: `action:preview.${crypto.randomUUID()}`,
          plot_id: `plot:preview-agent-${plotSequence + 1}`,
          profile_id: plan.input.selectedProfileIds?.[0] ?? 'K01',
          data: { kind: 'source', dataset_id: source.datasetId, version: source.sourceVersion, content_hash: 'a'.repeat(64) },
          bindings: [
            { role: 'x', field_id: `${source.datasetId}:time` },
            { role: 'y', field_id: `${source.datasetId}:signal` },
          ],
        },
      })
      if (!created.ok || !isJsonRecord(created.value)) return created
      const output = created.value
      plan.outputPlot = {
        plotId: typeof output.plot_id === 'string' ? output.plot_id : 'plot:preview',
        plotVersion: typeof output.plot_version === 'number' ? output.plot_version : 1,
      }
      plan.state = 'succeeded'
      return ok(workflowPlanRecord(plan))
    },
    resumeTaskPlan: async (input) => api.runTaskPlan(input),
    exportPngSvg: async ({ format }) => ok({ export_id: `export:preview-${format}`, preview_only: true }),
    exportOrigin: async () => ok({ export_id: 'export:preview-opju', preview_only: true }),
    respondToCloseRequest: actionOk,
    onCoreStatus: () => () => undefined,
    onTaskEvent: () => () => undefined,
    onWorkflowRuntimeEvent: () => () => undefined,
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
