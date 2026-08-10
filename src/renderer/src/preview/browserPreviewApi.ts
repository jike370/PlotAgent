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

interface PreviewBatch {
  taskId: string
  batchId: string
  version: number
  projectId: string
  itemIds: string[]
}

interface PreviewAgentPlan {
  projectId: string
  planId: string
  input?: Parameters<PlotAgentDesktopApi['decideAgent']>[0]
  batch?: PreviewBatch
  batchChartId?: string
  state: string
  confirmationState: string
  outputPlot?: { plotId: string; plotVersion: number }
  outputBatch?: { batchId: string; batchVersion: number }
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
  const batches = new Map<string, PreviewBatch>()
  const agentPlans = new Map<string, PreviewAgentPlan>()
  let projectSequence = 0
  let importSequence = 0
  let plotSequence = 0
  let batchSequence = 0
  let agentPlanSequence = 0

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

  const agentPlanRecord = (plan: PreviewAgentPlan): JsonRecord => {
    if (plan.batch !== undefined) {
      const plotActions: JsonRecord[] = plan.batch.itemIds.map((_, index) => ({
        action_type: 'create_plot',
        action_id: `action:item_${index + 1}`,
        target_alias: `plot_${index + 1}`,
        chart_type_id: plan.batchChartId ?? 'K01',
        field_selections: [
          { role: 'x', context_field_alias: `d${index + 1}_x` },
          { role: 'y', context_field_alias: `d${index + 1}_y` },
        ],
      }))
      const batchAction: JsonRecord = {
        action_type: 'create_batch',
        action_id: 'action:batch',
        depends_on: plotActions.map((action) => action.action_id as string),
        target_alias: 'batch_result',
        chart_type_id: plan.batchChartId ?? 'K01',
        field_selections: [
          { role: 'x', context_field_alias: 'd1_x' },
          { role: 'y', context_field_alias: 'd1_y' },
        ],
      }
      const actions = [...plotActions, batchAction]
      return {
        plan_id: plan.planId,
        conversation_id: 'conversation:main',
        context_snapshot_id: 'context:preview',
        context_hash: 'a'.repeat(64),
        project_revision: projects.get(plan.projectId)?.projectVersion ?? 0,
        source_plan_hash: 'b'.repeat(64),
        state: plan.state,
        confirmation_state: plan.confirmationState,
        source_plan: { decision_type: 'action_plan', plan_id: plan.planId, target_alias: 'batch_result', actions, warnings: [], confirmation: 'required' },
        items: actions.map((action, index) => ({
          task_item_id: `taskitem:${plan.planId.replace('plan:', '')}.${index + 1}`,
          action,
          state: plan.state === 'succeeded' ? 'succeeded' : plan.state === 'needs_confirmation' ? 'pending' : 'ready',
          depends_on: index === actions.length - 1
            ? plotActions.map((_, dependencyIndex) => `taskitem:${plan.planId.replace('plan:', '')}.${dependencyIndex + 1}`)
            : [],
          expected_objects: [],
          idempotency_key: `agent.${plan.planId}.${index + 1}`,
          output_slots: [index === actions.length - 1 ? 'batch' : 'primary'],
          attempt_count: plan.state === 'succeeded' ? 1 : 0,
          outputs: plan.state !== 'succeeded'
            ? []
            : index === actions.length - 1 && plan.outputBatch !== undefined
              ? [{ output_slot: 'batch', output_kind: 'object', object_ref: { object_alias: 'batch_result', object_id: plan.outputBatch.batchId, object_version: plan.outputBatch.batchVersion, object_type: 'batch', content_hash: 'd'.repeat(64) }, summary: '预览批次' }]
              : [{ output_slot: 'primary', output_kind: 'object', object_ref: { object_alias: `plot_${index + 1}`, object_id: `plot:preview-batch-${index + 1}`, object_version: 1, object_type: 'plot', content_hash: 'c'.repeat(64) }, summary: '预览图形' }],
        })),
      }
    }
    if (plan.batch === undefined) {
      const mutation = plan.input?.target?.kind === 'plot'
      const plotId = mutation ? plan.input?.target?.id ?? 'plot:preview' : 'plot:preview-agent'
      const proposalAction: JsonRecord = mutation
        ? {
          operation: 'set_title', action_id: 'action:preview', plot_alias: 'active_target',
          text: '预览修改',
        }
        : {
          operation: 'create_plot', action_id: 'action:preview', plot_alias: 'active_target',
          profile_id: plan.input?.selectedChartId ?? 'K01', source_alias: 'active_data',
          bindings: [
            { role: 'x', field_alias: 'x_field' },
            { role: 'y', field_alias: 'y_field' },
          ],
        }
      const boundAction: JsonRecord = mutation
        ? {
          operation: 'set_title', action_id: 'action:preview', target: plotId,
          expected_plot_version: plan.outputPlot?.plotVersion
            ? plan.outputPlot.plotVersion - 1 : 1,
          text: '预览修改',
        }
        : {
          operation: 'create_plot', action_id: 'action:preview', plot_id: plotId,
          profile_id: plan.input?.selectedChartId ?? 'K01',
        }
      return {
        plan_id: plan.planId,
        project_version: projects.get(plan.projectId)?.projectVersion ?? 0,
        state: plan.state,
        confirmation_state: plan.confirmationState,
        next_action_index: plan.state === 'succeeded' ? 1 : 0,
        current_project_revision: projects.get(plan.projectId)?.projectVersion ?? 0,
        error_code: null,
        proposal: {
          schema_version: 'engine-agent.v1', decision_type: 'action_plan',
          plan_id: plan.planId, target_alias: 'active_target', actions: [proposalAction],
        },
        bound_plan: {
          plan_id: plan.planId,
          expected_project_revision: projects.get(plan.projectId)?.projectVersion ?? 0,
          actions: [boundAction],
        },
      }
    }
    const actionType = plan.batch !== undefined
      ? 'create_batch'
      : plan.input?.target?.kind === 'plot' ? 'patch_plot' : 'create_plot'
    const action: JsonRecord = actionType === 'patch_plot'
      ? { action_type: actionType, action_id: 'action:preview', target_alias: 'active_target', patches: [{ operation: 'set_plot_title', target_alias: 'active_target', title: '预览修改' }] }
      : actionType === 'create_batch'
        ? { action_type: actionType, action_id: 'action:preview', target_alias: 'batch_result', chart_type_id: 'K01', field_selections: [{ role: 'x', context_field_alias: 'd1_x' }, { role: 'y', context_field_alias: 'd1_y' }] }
        : { action_type: actionType, action_id: 'action:preview', target_alias: 'active_target', chart_type_id: plan.input?.selectedChartId ?? 'K01', field_selections: [{ role: 'x', context_field_alias: 'x_field' }, { role: 'y', context_field_alias: 'y_field' }] }
    return {
      plan_id: plan.planId,
      conversation_id: 'conversation:main',
      context_snapshot_id: 'context:preview',
      context_hash: 'a'.repeat(64),
      project_revision: projects.get(plan.projectId)?.projectVersion ?? 0,
      source_plan_hash: 'b'.repeat(64),
      state: plan.state,
      confirmation_state: plan.confirmationState,
      source_plan: { decision_type: 'action_plan', plan_id: plan.planId, target_alias: plan.batch === undefined ? 'active_target' : 'batch_result', actions: [action], warnings: [], confirmation: plan.batch === undefined ? 'not_required' : 'required' },
      items: [{
        task_item_id: `taskitem:${plan.planId.replace('plan:', '')}.1`,
        action,
        state: plan.state === 'succeeded' ? 'succeeded' : plan.state === 'needs_confirmation' ? 'pending' : 'ready',
        depends_on: [],
        expected_objects: [],
        idempotency_key: `agent.${plan.planId}`,
        output_slots: [plan.batch === undefined ? 'primary' : 'batch'],
        attempt_count: plan.state === 'succeeded' ? 1 : 0,
        outputs: plan.outputBatch !== undefined
          ? [{ output_slot: 'batch', output_kind: 'object', object_ref: { object_alias: 'batch_result', object_id: plan.outputBatch.batchId, object_version: plan.outputBatch.batchVersion, object_type: 'batch', content_hash: 'd'.repeat(64) }, summary: '预览批次' }]
          : plan.outputPlot === undefined ? [] : [{ output_slot: 'primary', output_kind: 'object', object_ref: { object_alias: 'active_target', object_id: plan.outputPlot.plotId, object_version: plan.outputPlot.plotVersion, object_type: 'plot', content_hash: 'c'.repeat(64) }, summary: '预览图形' }],
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
            profile_id: profileId, data: input.action.data ?? null,
            bindings: input.action.bindings ?? [], components: input.action.components ?? [],
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
              { operation: 'set_series_style', parameters: ['color', 'line_width_pt', 'line_style', 'symbol', 'symbol_size_pt'] },
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
    createBatch: async (input) => {
      const project = projects.get(input.projectId)
      if (!project) return missing('界面预览中没有找到该项目。')
      batchSequence += 1
      const batch: PreviewBatch = {
        taskId: `task:preview-${batchSequence}`,
        batchId: `batch:preview-${batchSequence}`,
        version: 1,
        projectId: input.projectId,
        itemIds: input.datasets.map((_, index) => `item:${index + 1}`),
      }
      agentPlanSequence += 1
      const plan: PreviewAgentPlan = {
        projectId: input.projectId,
        planId: `plan:preview-${agentPlanSequence}`,
        batch,
        batchChartId: input.chartId,
        state: 'needs_confirmation',
        confirmationState: 'pending',
      }
      agentPlans.set(plan.planId, plan)
      return ok({ project_version: project.projectVersion, task_plan: agentPlanRecord(plan) })
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
    decideAgent: async (input) => {
      const project = projects.get(input.projectId)
      if (!project) return missing('界面预览中没有找到该项目。')
      agentPlanSequence += 1
      const plan: PreviewAgentPlan = {
        projectId: input.projectId,
        planId: `plan:preview-${agentPlanSequence}`,
        input,
        state: 'needs_confirmation',
        confirmationState: 'pending',
      }
      agentPlans.set(plan.planId, plan)
      const taskPlan = agentPlanRecord(plan)
      return ok({ accepted: true, conversation_id: 'conversation:main', decision: taskPlan.proposal, task_plan: taskPlan })
    },
    getAgentPlan: async ({ planId }) => {
      const plan = agentPlans.get(planId)
      return plan === undefined ? missing('未找到 Agent 计划。') : ok(agentPlanRecord(plan))
    },
    listAgentPlans: async ({ projectId }) => ok({
      plans: [...agentPlans.values()]
        .filter((plan) => plan.projectId === projectId)
        .map(agentPlanRecord),
    }),
    confirmAgentPlan: async ({ planId, accept }) => {
      const plan = agentPlans.get(planId)
      if (plan === undefined) return missing('未找到 Agent 计划。')
      if (!accept) {
        agentPlans.delete(planId)
        return ok({ plan_id: planId, state: 'cancelled' })
      }
      plan.state = 'ready'
      plan.confirmationState = 'confirmed'
      return ok(agentPlanRecord(plan))
    },
    runAgentPlan: async ({ projectId, planId }) => {
      const plan = agentPlans.get(planId)
      const project = projects.get(projectId)
      if (plan === undefined || project === undefined) return missing('未找到 Agent 计划。')
      if (plan.batch !== undefined) {
        project.projectVersion += 1
        batches.set(plan.batch.batchId, plan.batch)
        plan.outputBatch = { batchId: plan.batch.batchId, batchVersion: plan.batch.version }
        plan.state = 'succeeded'
        return ok({
          task_plan: agentPlanRecord(plan),
          change_set: {
            plan_id: planId,
            state: 'succeeded',
            items: agentPlanRecord(plan).items,
          },
          completed_item_count: plan.batch.itemIds.length + 1,
          total_item_count: plan.batch.itemIds.length + 1,
          resumable: false,
        })
      }
      if (plan.input === undefined) return missing('预览计划缺少输入。')
      let output: JsonRecord
      if (plan.input.target?.kind === 'plot') {
        const current = plots.get(plotKey(projectId, plan.input.target.id))
        if (current === undefined) return missing('未找到待修改图形。')
        project.projectVersion += 1
        output = {
          ...current,
          project_version: project.projectVersion,
          plot_version: (typeof current.plot_version === 'number' ? current.plot_version : 1) + 1,
        }
        plots.set(plotKey(projectId, plan.input.target.id), output)
      } else {
        const created = await api.executePlotAction({
          projectId,
          expectedProjectVersion: project.projectVersion,
          action: {
            operation: 'create_plot',
            action_id: `action:preview.${crypto.randomUUID()}`,
            plot_id: `plot:preview-agent-${plotSequence + 1}`,
            profile_id: plan.input.selectedChartId ?? 'K01',
            data: {
              kind: 'source', dataset_id: plan.input.sourceDatasetId,
              version: plan.input.sourceVersion, content_hash: 'a'.repeat(64),
            },
            bindings: [
              { role: 'x', field_id: `${plan.input.sourceDatasetId}:time` },
              { role: 'y', field_id: `${plan.input.sourceDatasetId}:signal` },
            ],
            components: [],
          },
        })
        if (!created.ok || typeof created.value !== 'object' || created.value === null || Array.isArray(created.value)) return created
        output = created.value
      }
      plan.outputPlot = {
        plotId: typeof output.plot_id === 'string' ? output.plot_id : 'plot:preview',
        plotVersion: typeof output.plot_version === 'number' ? output.plot_version : 1,
      }
      plan.state = 'succeeded'
      return ok({
        task_plan: agentPlanRecord(plan),
        change_set: {
          plan_id: planId,
          state: 'succeeded',
          items: agentPlanRecord(plan).items,
        },
        completed_item_count: 1,
        total_item_count: 1,
        resumable: false,
      })
    },
    resumeAgentPlan: async (input) => api.runAgentPlan(input),
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
