import type { DesktopResource, JsonValue } from '../../../shared/desktop-contract'

export interface ProductProject {
  projectId: string
  name: string
  projectVersion: number
  isOpen: boolean
  lastOpenedAt?: string
}

export interface ProductField {
  fieldId: string
  name: string
  logicalType: string
  physicalType: string
  unit: string
}

export type ProductPreviewValue = string | number | boolean | null

export interface ProductDataset {
  datasetId: string
  contentHash?: string
  displayName: string
  sourceFileName?: string
  sourceSheetName?: string
  sourceVersion: number
  rowCount: number
  fieldCount: number
  fields: ProductField[]
  missingCount: number
  nonFiniteCount: number
  coordinateKinds: string[]
  sampleRows?: ProductPreviewValue[][]
  samplePreviewUnavailable?: boolean
}

export type ProductOriginAvailability =
  | {
    available: true
    displayName: string
    displayVersion: string
    discoverySource: string
  }
  | {
    available: false
    code: string
    message: string
    retryable: boolean
  }

export interface ProductSeriesStyle {
  color?: string
  lineWidthPt?: number
  markerSizePt?: number
  lineStyle?: string
  symbolShape?: string
  symbolInterior?: string
  paletteId?: string
  paletteReverse?: boolean
}

export interface ProductAxisState {
  axisId: string
  label: string
  scale: string
  minimum?: number
  maximum?: number
  reverse: boolean
  majorInterval?: number
  numberFormat: string
  decimalPlaces: number
}

export interface ProductAnnotation {
  annotationId: string
  kind: string
  text: string
  x?: number
  y?: number
  x2?: number
  y2?: number
}

export interface ProductSpecialistState {
  barArea: {
    fillColor?: string
    edgeColor?: string
    edgeWidthPt: number
    widthRatio: number
    alpha: number
  }
  uncertainty: {
    color?: string
    lineWidthPt: number
    capSizePt: number
    bandAlpha: number
  }
  colorbar: {
    visible: boolean
    title: string
    minimum?: number
    maximum?: number
    levels: number
  }
  dualY: {
    leftColor?: string
    rightColor?: string
    axisWidthPt: number
  }
  facet: {
    order: string[]
    labels: { value: string; label: string }[]
    gapMm: number
    sharedX: boolean
    sharedY: boolean
    commonLegend: boolean
  }
  yOffset: { distance?: number; order: string[] }
  chartParameters: {
    stepWhere: 'pre' | 'mid' | 'post'
    volcanoAbsoluteLog2FoldChange: number
    volcanoPvalue: number
    paretoReferencePercent: number
  }
}

export interface ProductPlot {
  plotId: string
  plotVersion: number
  contentHash?: string
  chartId: string
  plotTitle: string
  fontSizePt: number
  projectVersion: number
  seriesIds: string[]
  seriesStyles: { seriesId: string; style: ProductSeriesStyle }[]
  axisIds: { x?: string; y?: string; yRight?: string }
  axisStates: { x?: ProductAxisState; y?: ProductAxisState; yRight?: ProductAxisState }
  canvasSizeMm: { width: number; height: number }
  annotations: ProductAnnotation[]
  specialist: ProductSpecialistState
  style: ProductSeriesStyle & {
    legendVisible?: boolean
    legendPlacement?: string
  }
  chartParameters?: Readonly<Record<string, string | number | boolean>>
  engineCapabilities?: Readonly<Record<string, readonly string[]>>
  preview?: DesktopResource
}

export type AgentOutcomeKind = 'action_plan' | 'needs_input' | 'unsupported' | 'no_change' | 'rejected'

export interface AgentQuestion {
  questionKey: string
  prompt: string
  choices: { value: string; label: string }[]
}

export interface AgentPlanStep {
  taskItemId: string
  actionType: string
  title: string
  detail?: string
  state: string
  attemptCount: number
  failure?: { code: string; message: string; retryable: boolean }
  outputPlot?: { plotId: string; plotVersion: number }
}

export interface AgentBindingView {
  role: string
  fieldId: string
}

export interface AgentPlanView {
  planId: string
  state: string
  confirmationState: string
  warnings: string[]
  steps: AgentPlanStep[]
  completedCount: number
  resumable: boolean
  bindings: AgentBindingView[]
  boundActions: JsonValue[]
}

export interface AgentOutcome {
  kind: AgentOutcomeKind
  title: string
  message: string
  questions?: AgentQuestion[]
  plan?: AgentPlanView
  execution?: ProductPlot
  executionCount?: number
  scopeExecution?: AgentScopeExecution
}

export interface AgentScopeExecution {
  kind: 'batch' | 'figure'
  id: string
  version: number
  projectVersion: number
  updatedPlotCount: number
  batchItems: { id: string; state: string }[]
}

type JsonRecord = Record<string, JsonValue>

export function isJsonRecord(value: JsonValue | undefined): value is JsonRecord {
  return value !== null && value !== undefined && typeof value === 'object' && !Array.isArray(value)
}

function stringValue(record: JsonRecord, ...keys: string[]): string | undefined {
  for (const key of keys) if (typeof record[key] === 'string') return record[key]
  return undefined
}

function numberValue(record: JsonRecord, ...keys: string[]): number | undefined {
  for (const key of keys) if (typeof record[key] === 'number') return record[key]
  return undefined
}

function records(value: JsonValue, predicate: (record: JsonRecord) => boolean): JsonRecord[] {
  if (Array.isArray(value)) return value.flatMap((item) => records(item, predicate))
  if (!isJsonRecord(value)) return []
  const current = predicate(value) ? [value] : []
  return [...current, ...Object.values(value).flatMap((item) => records(item, predicate))]
}

function unitLabel(value: JsonValue | undefined): string {
  if (typeof value === 'string') return value
  if (!isJsonRecord(value)) return '未声明'
  return stringValue(value, 'symbol', 'canonical', 'display_name', 'value') ?? '未声明'
}

export function readProjects(value: JsonValue): ProductProject[] {
  const candidates = records(value, (record) => typeof record.project_id === 'string' && (
    Object.hasOwn(record, 'display_name') || Object.hasOwn(record, 'is_open') || Object.hasOwn(record, 'status')
  ))
  const projects = new Map<string, ProductProject>()
  for (const record of candidates) {
    const projectId = stringValue(record, 'project_id')!
    const existing = projects.get(projectId)
    projects.set(projectId, {
      projectId,
      name: stringValue(record, 'display_name') ?? existing?.name ?? '未命名项目',
      projectVersion: numberValue(record, 'project_version') ?? existing?.projectVersion ?? 0,
      isOpen: existing?.isOpen === true || record.is_open === true || record.status === 'open',
      lastOpenedAt: stringValue(record, 'last_opened_at') ?? existing?.lastOpenedAt,
    })
  }
  return [...projects.values()]
}

export function readProject(value: JsonValue): ProductProject | undefined {
  return readProjects(value).at(-1)
}

function countQuality(value: JsonValue | undefined, keys: string[]): number {
  if (!isJsonRecord(value)) return 0
  return keys.reduce((total, key) => total + (typeof value[key] === 'number' ? value[key] : 0), 0)
}

function readSampleRows(value: JsonValue | undefined): ProductPreviewValue[][] | undefined {
  if (value === undefined) return undefined
  if (!Array.isArray(value)) return []
  return value.slice(0, 5).flatMap((row): ProductPreviewValue[][] => {
    if (!Array.isArray(row)) return []
    const values = row.flatMap((item): ProductPreviewValue[] => (
      item === null || typeof item === 'string' || typeof item === 'number' || typeof item === 'boolean'
        ? [item]
        : []
    ))
    return values.length === row.length ? [values] : []
  })
}

export function readDatasets(value: JsonValue): ProductDataset[] {
  const candidates = records(value, (record) => typeof record.source_dataset_id === 'string' && Array.isArray(record.fields))
  return [...new Map(candidates.map((record) => {
    const datasetId = stringValue(record, 'source_dataset_id')!
    const fields = (Array.isArray(record.fields) ? record.fields : []).flatMap((field): ProductField[] => {
      if (!isJsonRecord(field)) return []
      const fieldId = stringValue(field, 'field_id')
      if (fieldId === undefined) return []
      return [{
        fieldId,
        name: stringValue(field, 'name') ?? fieldId,
        logicalType: stringValue(field, 'logical_type') ?? 'unknown',
        physicalType: stringValue(field, 'physical_type') ?? 'unknown',
        unit: unitLabel(field.unit),
      }]
    })
    const quality = isJsonRecord(record.quality) ? record.quality : undefined
    const sourceFileName = stringValue(record, 'source_file_name', 'file_name', 'workbook_name')
    const sourceSheetName = stringValue(record, 'source_sheet_name', 'sheet_name')
    const sourceTableIndex = numberValue(record, 'source_table_index')
    const sampleRows = readSampleRows(record.sample_rows)
    const displayName = sourceFileName === undefined
      ? stringValue(record, 'display_name') ?? datasetId
      : sourceSheetName !== undefined
        ? `${sourceFileName} > ${sourceSheetName}`
        : Array.isArray(record.source_coordinate_kinds) && record.source_coordinate_kinds.includes('excel')
          ? `${sourceFileName} > 工作表 ${sourceTableIndex ?? 1}`
          : sourceFileName
    return [`${datasetId}@${numberValue(record, 'source_version') ?? 1}`, {
      datasetId,
      ...(stringValue(record, 'content_hash') === undefined
        ? {} : { contentHash: stringValue(record, 'content_hash') }),
      displayName,
      ...(sourceFileName === undefined ? {} : { sourceFileName }),
      ...(sourceSheetName === undefined ? {} : { sourceSheetName }),
      sourceVersion: numberValue(record, 'source_version') ?? 1,
      rowCount: numberValue(record, 'row_count') ?? 0,
      fieldCount: numberValue(record, 'field_count') ?? fields.length,
      fields,
      missingCount: countQuality(quality, ['missing_count', 'null_count', 'missing_values']),
      nonFiniteCount: countQuality(quality, ['nonfinite_count', 'non_finite_count']),
      coordinateKinds: Array.isArray(record.source_coordinate_kinds)
        ? record.source_coordinate_kinds.filter((item): item is string => typeof item === 'string')
        : [],
      ...(sampleRows === undefined ? {} : { sampleRows }),
    } satisfies ProductDataset]
  })).values()]
}

function readResource(value: JsonValue): DesktopResource | undefined {
  const candidate = records(value, (record) => (
    typeof record.resourceId === 'string' && record.kind === 'preview' && typeof record.url === 'string'
  )).at(0)
  if (candidate === undefined) return undefined
  return {
    resourceId: candidate.resourceId as string,
    kind: 'preview',
    url: candidate.url as string,
    ...(typeof candidate.mimeType === 'string' ? { mimeType: candidate.mimeType as DesktopResource['mimeType'] } : {}),
    ...(typeof candidate.fileName === 'string' ? { fileName: candidate.fileName } : {}),
  }
}

function richTextValue(value: JsonValue | undefined): string {
  if (!isJsonRecord(value) || !Array.isArray(value.nodes)) return ''
  return value.nodes.flatMap((node) => {
    if (!isJsonRecord(node)) return []
    if (node.kind === 'newline') return ['\n']
    if (node.kind === 'fraction' && typeof node.text === 'string' && typeof node.denominator === 'string') {
      return [`${node.text}/${node.denominator}`]
    }
    return typeof node.text === 'string' ? [node.text] : []
  }).join('')
}

function physicalLengthMm(value: JsonValue | undefined, fallback: number): number {
  if (!isJsonRecord(value) || typeof value.value !== 'number') return fallback
  return value.unit === 'pt' ? value.value * 25.4 / 72 : value.value
}

function physicalLengthPt(value: JsonValue | undefined, fallback: number): number {
  if (!isJsonRecord(value) || typeof value.value !== 'number') return fallback
  return value.unit === 'mm' ? value.value * 72 / 25.4 : value.value
}

function colorString(value: JsonValue | undefined): string | undefined {
  return isJsonRecord(value) && typeof value.value === 'string' ? value.value : undefined
}

function stringArray(value: JsonValue | undefined): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function readSpecialist(value: JsonValue | undefined): ProductSpecialistState {
  const specialist = isJsonRecord(value) ? value : {}
  const barArea = isJsonRecord(specialist.bar_area) ? specialist.bar_area : {}
  const uncertainty = isJsonRecord(specialist.uncertainty) ? specialist.uncertainty : {}
  const colorbar = isJsonRecord(specialist.colorbar) ? specialist.colorbar : {}
  const dualY = isJsonRecord(specialist.dual_y) ? specialist.dual_y : {}
  const facet = isJsonRecord(specialist.facet) ? specialist.facet : {}
  const yOffset = isJsonRecord(specialist.y_offset) ? specialist.y_offset : {}
  const parameters = isJsonRecord(specialist.chart_parameters)
    ? specialist.chart_parameters : {}
  const labels = Array.isArray(facet.labels) ? facet.labels.filter(isJsonRecord) : []
  return {
    barArea: {
      ...(colorString(barArea.fill_color) ? { fillColor: colorString(barArea.fill_color) } : {}),
      ...(colorString(barArea.edge_color) ? { edgeColor: colorString(barArea.edge_color) } : {}),
      edgeWidthPt: physicalLengthPt(barArea.edge_width, 0.5),
      widthRatio: numberValue(barArea, 'width_ratio') ?? 0.8,
      alpha: numberValue(barArea, 'alpha') ?? 1,
    },
    uncertainty: {
      ...(colorString(uncertainty.color) ? { color: colorString(uncertainty.color) } : {}),
      lineWidthPt: physicalLengthPt(uncertainty.line_width, 0.8),
      capSizePt: physicalLengthPt(uncertainty.cap_size, 4),
      bandAlpha: numberValue(uncertainty, 'band_alpha') ?? 0.25,
    },
    colorbar: {
      visible: colorbar.visible !== false,
      title: richTextValue(colorbar.title),
      ...(typeof colorbar.minimum === 'number' ? { minimum: colorbar.minimum } : {}),
      ...(typeof colorbar.maximum === 'number' ? { maximum: colorbar.maximum } : {}),
      levels: numberValue(colorbar, 'levels') ?? 7,
    },
    dualY: {
      ...(colorString(dualY.left_color) ? { leftColor: colorString(dualY.left_color) } : {}),
      ...(colorString(dualY.right_color) ? { rightColor: colorString(dualY.right_color) } : {}),
      axisWidthPt: physicalLengthPt(dualY.axis_width, 0.8),
    },
    facet: {
      order: stringArray(facet.order),
      labels: labels.flatMap((item) => (
        typeof item.value === 'string' && typeof item.label === 'string'
          ? [{ value: item.value, label: item.label }] : []
      )),
      gapMm: physicalLengthMm(facet.gap, 4),
      sharedX: facet.shared_x !== false,
      sharedY: facet.shared_y !== false,
      commonLegend: facet.common_legend !== false,
    },
    yOffset: {
      ...(typeof yOffset.distance === 'number' ? { distance: yOffset.distance } : {}),
      order: stringArray(yOffset.order),
    },
    chartParameters: {
      stepWhere: parameters.step_where === 'pre' || parameters.step_where === 'mid'
        ? parameters.step_where : 'post',
      volcanoAbsoluteLog2FoldChange:
        numberValue(parameters, 'volcano_absolute_log2_fold_change') ?? 1,
      volcanoPvalue: numberValue(parameters, 'volcano_pvalue') ?? 0.05,
      paretoReferencePercent: numberValue(parameters, 'pareto_reference_percent') ?? 80,
    },
  }
}

function semanticObjectId(plotId: string, object: JsonRecord): string | undefined {
  const kind = stringValue(object, 'object_kind')
  const key = stringValue(object, 'object_key')
  if (kind === undefined || key === undefined) return undefined
  return `${kind}:${plotId.replace(/^plot:/, '')}.${key}`
}

function engineSeriesStyle(action: JsonRecord): ProductSeriesStyle {
  return {
    ...(typeof action.color === 'string' ? { color: action.color } : {}),
    ...(typeof action.line_width_pt === 'number' ? { lineWidthPt: action.line_width_pt } : {}),
    ...(typeof action.line_style === 'string' ? { lineStyle: action.line_style } : {}),
    ...(typeof action.symbol === 'string' ? { symbolShape: action.symbol } : {}),
    ...(typeof action.symbol_size_pt === 'number' ? { markerSizePt: action.symbol_size_pt } : {}),
  }
}

export function readPlot(value: JsonValue): ProductPlot | undefined {
  const root = records(value, (record) => isJsonRecord(record.document)).at(0)
  if (root === undefined || !isJsonRecord(root.document)) return undefined
  const document = root.document
  const plotRef = isJsonRecord(root.plot_ref) ? root.plot_ref : undefined
  const plotId = stringValue(document, 'plot_id')
  const plotVersion = numberValue(document, 'plot_version')
  const profileId = stringValue(document, 'profile_id')
  if (plotId === undefined || plotVersion === undefined || profileId === undefined) return undefined
  const actions = Array.isArray(root.actions) ? root.actions.filter(isJsonRecord) : []
  const profile = isJsonRecord(root.profile) ? root.profile : {}
  const objects = Array.isArray(profile.objects) ? profile.objects.filter(isJsonRecord) : []
  const readback = isJsonRecord(root.readback) ? root.readback : {}
  const nativeObjects = Array.isArray(readback.objects) ? readback.objects.filter(isJsonRecord) : []
  const objectId = (alias: string): string | undefined => {
    const object = objects.find((item) => item.object_alias === alias)
    return object === undefined ? undefined : semanticObjectId(plotId, object)
  }
  const actionTarget = (operation: string, target: string): JsonRecord[] => actions.filter(
    (action) => action.operation === operation && action.target === target,
  )
  const seriesIds = [...new Set([
    ...objects.flatMap((object) => object.object_kind === 'series'
      ? [semanticObjectId(plotId, object)].filter((item): item is string => item !== undefined) : []),
    ...nativeObjects.flatMap((object) => typeof object.semantic_id === 'string'
      && object.semantic_id.startsWith('series:') ? [object.semantic_id] : []),
  ])]
  const axisIds = {
    ...(objectId('x_axis') ? { x: objectId('x_axis') } : {}),
    ...(objectId('y_axis') ? { y: objectId('y_axis') } : {}),
    ...(objectId('right_y_axis') ? { yRight: objectId('right_y_axis') } : {}),
  }
  const axisState = (axisId: string | undefined): ProductAxisState | undefined => {
    if (axisId === undefined) return undefined
    const edits = actionTarget('set_axis', axisId)
    const current = edits.at(-1)
    return {
      axisId,
      label: current && typeof current.label === 'string' ? current.label : '',
      scale: current && typeof current.scale === 'string' ? current.scale : 'linear',
      ...(current && typeof current.minimum === 'number' ? { minimum: current.minimum } : {}),
      ...(current && typeof current.maximum === 'number' ? { maximum: current.maximum } : {}),
      reverse: current?.reverse === true,
      numberFormat: 'auto',
      decimalPlaces: 2,
    }
  }
  const title = actions.filter((action) => action.operation === 'set_title').at(-1)
  const legendId = objectId('legend')
  const legend = legendId === undefined ? undefined : actionTarget('set_legend', legendId).at(-1)
  const capabilities = (Array.isArray(profile.capabilities) ? profile.capabilities : [])
    .filter(isJsonRecord)
    .reduce<Record<string, readonly string[]>>((result, capability) => {
      if (typeof capability.operation === 'string') {
        result[capability.operation] = Array.isArray(capability.parameters)
          ? capability.parameters.filter((item): item is string => typeof item === 'string') : []
      }
      return result
    }, {})
  const chartParameters = actions
    .filter((action) => action.operation === 'set_chart_parameter')
    .reduce<Record<string, string | number | boolean>>((result, action) => {
      if (typeof action.parameter === 'string'
          && (typeof action.value === 'string'
            || typeof action.value === 'number'
            || typeof action.value === 'boolean')) {
        result[action.parameter] = action.value
      }
      return result
    }, {})
  return {
    plotId,
    plotVersion,
    ...(plotRef && typeof plotRef.content_hash === 'string'
      ? { contentHash: plotRef.content_hash } : {}),
    chartId: profileId,
    plotTitle: title && typeof title.text === 'string' ? title.text : '',
    fontSizePt: 9,
    projectVersion: projectVersionFrom(value, 0),
    seriesIds,
    seriesStyles: seriesIds.map((seriesId) => ({
      seriesId,
      style: engineSeriesStyle(actionTarget('set_series_style', seriesId).at(-1) ?? {}),
    })),
    axisIds,
    axisStates: {
      ...(axisState(axisIds.x) ? { x: axisState(axisIds.x) } : {}),
      ...(axisState(axisIds.y) ? { y: axisState(axisIds.y) } : {}),
      ...(axisState(axisIds.yRight) ? { yRight: axisState(axisIds.yRight) } : {}),
    },
    canvasSizeMm: { width: 183, height: 120 },
    annotations: actions.flatMap((action): ProductAnnotation[] => (
      action.operation === 'add_annotation'
      && typeof action.annotation_id === 'string'
      && typeof action.text === 'string'
        ? [{
          annotationId: action.annotation_id,
          kind: 'text',
          text: action.text,
          ...(typeof action.x === 'number' ? { x: action.x } : {}),
          ...(typeof action.y === 'number' ? { y: action.y } : {}),
        }]
        : []
    )),
    specialist: readSpecialist(undefined),
    style: {
      ...(seriesIds[0] ? engineSeriesStyle(actionTarget('set_series_style', seriesIds[0]).at(-1) ?? {}) : {}),
      ...(legend && typeof legend.visible === 'boolean' ? { legendVisible: legend.visible } : {}),
      ...(legend && typeof legend.anchor === 'string' ? { legendPlacement: legend.anchor } : {}),
    },
    chartParameters,
    engineCapabilities: capabilities,
    preview: readResource(value),
  }
}

export function readPlots(value: JsonValue): ProductPlot[] {
  const container = records(value, (record) => Array.isArray(record.plots)).at(0)
  if (container === undefined || !Array.isArray(container.plots)) return []
  return container.plots.flatMap((item) => {
    const plot = readPlot(item)
    return plot === undefined ? [] : [plot]
  })
}

export function withPreview(plot: ProductPlot, value: JsonValue): ProductPlot {
  return { ...plot, preview: readResource(value) ?? plot.preview }
}

function decisionMessage(decision: JsonRecord): string {
  const questions = Array.isArray(decision.questions) ? decision.questions : []
  const prompts = questions.flatMap((question) => (
    isJsonRecord(question) && typeof question.prompt === 'string' ? [question.prompt] : []
  ))
  if (prompts.length > 0) return prompts.join('；')
  return stringValue(decision, 'message', 'reason', 'explanation') ?? 'Agent 已返回结构化结果。'
}

function readScopeExecution(value: JsonValue): AgentScopeExecution | undefined {
  if (!isJsonRecord(value) || !isJsonRecord(value.scope_execution)) return undefined
  const scope = value.scope_execution
  if ((scope.target_kind !== 'batch' && scope.target_kind !== 'figure')
    || typeof scope.target_id !== 'string'
    || typeof scope.target_version !== 'number') return undefined
  const batch = isJsonRecord(scope.batch) ? scope.batch : undefined
  const rawItems = batch !== undefined && Array.isArray(batch.item_states) ? batch.item_states : []
  return {
    kind: scope.target_kind,
    id: scope.target_id,
    version: scope.target_version,
    projectVersion: numberValue(scope, 'project_version') ?? 0,
    updatedPlotCount: numberValue(scope, 'updated_plot_count') ?? 0,
    batchItems: rawItems.flatMap((item) => isJsonRecord(item) && typeof item.item_id === 'string'
      ? [{ id: item.item_id, state: typeof item.state === 'string' ? item.state : 'queued' }]
      : []),
  }
}

export function readAgentOutcome(value: JsonValue): AgentOutcome {
  if (isJsonRecord(value) && value.accepted === false) {
    const error = isJsonRecord(value.error) ? value.error : undefined
    return {
      kind: 'rejected',
      title: '指令未执行',
      message: error === undefined ? 'Agent 结果未通过本地校验。' : stringValue(error, 'message') ?? 'Agent 结果未通过本地校验。',
    }
  }
  const decision = records(value, (record) => typeof record.decision_type === 'string').at(0)
  if (decision === undefined) return { kind: 'rejected', title: '无法识别结果', message: 'Core 未返回受支持的四类 Agent 决策。' }
  const decisionType = decision.decision_type
  if (decisionType === 'action_plan') {
    const root = isJsonRecord(value) ? value : undefined
    const executions = root !== undefined && Array.isArray(root.executions) ? root.executions : []
    const explicitExecution = root !== undefined && isJsonRecord(root.execution) ? readPlot(root.execution) : undefined
    const executionCount = executions.length > 0 ? executions.length : explicitExecution === undefined ? 0 : 1
    const scopeExecution = readScopeExecution(value)
    const plan = readAgentPlan(value)
    return {
      kind: 'action_plan',
      title: executionCount > 0 ? '任务已执行' : '计划已生成',
      message: executionCount > 1
        ? `已完成 ${executionCount} 个可追溯图形版本。`
        : executionCount === 1
          ? '已创建可追溯图形版本。'
          : '检查任务与作用对象后执行。',
      ...(plan === undefined ? {} : { plan }),
      ...(explicitExecution === undefined ? {} : { execution: explicitExecution }),
      ...(scopeExecution === undefined ? {} : { scopeExecution }),
      executionCount,
    }
  }
  if (decisionType === 'needs_input') {
    const questions = Array.isArray(decision.questions)
      ? decision.questions.flatMap((question): AgentQuestion[] => {
        if (!isJsonRecord(question) || typeof question.question_key !== 'string' || typeof question.prompt !== 'string') return []
        const choices = Array.isArray(question.choices)
          ? question.choices.flatMap((choice) => isJsonRecord(choice) && typeof choice.value === 'string' && typeof choice.label === 'string'
            ? [{ value: choice.value, label: choice.label }]
            : [])
          : []
        return [{ questionKey: question.question_key, prompt: question.prompt, choices }]
      })
      : []
    return { kind: 'needs_input', title: '需要补充信息', message: decisionMessage(decision), questions }
  }
  if (decisionType === 'unsupported') return { kind: 'unsupported', title: '当前不支持', message: decisionMessage(decision) }
  if (decisionType === 'no_change') return { kind: 'no_change', title: '无需修改', message: decisionMessage(decision) }
  return { kind: 'rejected', title: '结果已拒绝', message: decisionMessage(decision) }
}

function engineActionTitle(action: JsonRecord): string {
  const operation = stringValue(action, 'operation') ?? 'unknown'
  const labels: Record<string, string> = {
    create_plot: '创建图形',
    bind_fields: '更新字段绑定',
    set_title: '修改标题',
    set_axis: '修改坐标轴',
    set_series_style: '修改系列样式',
    set_legend: '修改图例',
    set_chart_parameter: '修改图形参数',
    add_annotation: '添加标注',
    export_plot: '导出图形',
  }
  return labels[operation] ?? operation
}

function engineActionDetail(action: JsonRecord): string | undefined {
  const operation = stringValue(action, 'operation')
  const target = stringValue(action, 'target')
  if (operation === 'create_plot') return `图形 ${stringValue(action, 'profile_id') ?? '待定'} · ${stringValue(action, 'plot_id') ?? '新对象'}`
  if (operation === 'set_title' && typeof action.text === 'string') return `标题 → “${action.text}”`
  if (operation === 'set_axis') {
    const changes = [
      typeof action.label === 'string' ? `标题“${action.label}”` : undefined,
      typeof action.scale === 'string' ? `尺度 ${action.scale}` : undefined,
      typeof action.minimum === 'number' && typeof action.maximum === 'number' ? `范围 ${action.minimum}–${action.maximum}` : undefined,
      typeof action.reverse === 'boolean' ? action.reverse ? '反向' : '正向' : undefined,
    ].filter((item): item is string => item !== undefined)
    return `${target ?? '坐标轴'}${changes.length > 0 ? ` · ${changes.join(' · ')}` : ''}`
  }
  if (operation === 'set_series_style') {
    const changes = Object.entries(action)
      .filter(([key]) => ['color', 'line_width_pt', 'line_style', 'symbol', 'symbol_size_pt'].includes(key))
      .map(([key, value]) => `${key}=${String(value)}`)
    return `${target ?? '系列'}${changes.length > 0 ? ` · ${changes.join(' · ')}` : ''}`
  }
  if (operation === 'set_legend') {
    const changes = [
      typeof action.visible === 'boolean' ? action.visible ? '显示' : '隐藏' : undefined,
      typeof action.anchor === 'string' ? `位置 ${action.anchor}` : undefined,
    ].filter((item): item is string => item !== undefined)
    return `${target ?? '图例'}${changes.length > 0 ? ` · ${changes.join(' · ')}` : ''}`
  }
  if (operation === 'set_chart_parameter' && typeof action.parameter === 'string') return `${action.parameter} → ${String(action.value)}`
  if (operation === 'add_annotation' && typeof action.text === 'string') return `文本“${action.text}”`
  if (operation === 'bind_fields') return '按下方角色→字段映射更新绑定'
  if (operation === 'export_plot') return `导出 ${stringValue(action, 'format') ?? '产物'}`
  return target
}

function readEngineAgentPlan(value: JsonValue): AgentPlanView | undefined {
  const plan = records(value, (record) => (
    typeof record.plan_id === 'string'
    && isJsonRecord(record.proposal)
    && isJsonRecord(record.bound_plan)
  )).at(0)
  if (plan === undefined) return undefined
  const proposal = plan.proposal as JsonRecord
  const boundPlan = plan.bound_plan as JsonRecord
  const proposedActions = Array.isArray(proposal.actions)
    ? proposal.actions.filter(isJsonRecord) : []
  const boundActions = Array.isArray(boundPlan.actions)
    ? boundPlan.actions.filter(isJsonRecord) : []
  const bindings = boundActions.flatMap((action): AgentBindingView[] => {
    if (!Array.isArray(action.bindings)) return []
    return action.bindings.flatMap((binding) => {
      if (!isJsonRecord(binding)) return []
      const role = stringValue(binding, 'role')
      const fieldId = stringValue(binding, 'field_id')
      return role === undefined || fieldId === undefined ? [] : [{ role, fieldId }]
    })
  })
  const state = stringValue(plan, 'state') ?? 'needs_confirmation'
  const nextActionIndex = numberValue(plan, 'next_action_index') ?? 0
  const errorCode = stringValue(plan, 'error_code')
  const steps = proposedActions.map((action, index): AgentPlanStep => {
    const bound = boundActions[index] ?? {}
    const succeeded = index < nextActionIndex || state === 'succeeded'
    const failed = state === 'partially_failed' && index === nextActionIndex
    const running = state === 'running' && index === nextActionIndex
    const target = stringValue(bound, 'target')
    const plotId = stringValue(bound, 'plot_id') ?? plotIdFromSemanticTarget(target)
    const outputVersion = bound.operation === 'create_plot'
      ? 1
      : typeof bound.expected_plot_version === 'number'
        ? bound.expected_plot_version + (bound.operation === 'export_plot' ? 0 : 1)
        : undefined
    return {
      taskItemId: stringValue(action, 'action_id') ?? `action:${index + 1}`,
      actionType: stringValue(action, 'operation') ?? 'unknown',
      title: engineActionTitle(action),
      ...(engineActionDetail(bound) ? { detail: engineActionDetail(bound) } : {}),
      state: succeeded ? 'succeeded' : failed ? 'failed' : running ? 'running' : 'pending',
      attemptCount: succeeded || failed ? 1 : 0,
      ...(failed ? {
        failure: {
          code: errorCode ?? 'ENGINE_ACTION_FAILED',
          message: '该动作未完成，可以从这里继续执行。',
          retryable: true,
        },
      } : {}),
      ...(plotId !== undefined && outputVersion !== undefined
        ? { outputPlot: { plotId, plotVersion: outputVersion } } : {}),
    }
  })
  return {
    planId: plan.plan_id as string,
    state,
    confirmationState: stringValue(plan, 'confirmation_state') ?? 'pending',
    warnings: [],
    steps,
    completedCount: steps.filter((step) => step.state === 'succeeded').length,
    resumable: state === 'partially_failed',
    bindings,
    boundActions,
  }
}

function plotIdFromSemanticTarget(target: string | undefined): string | undefined {
  if (target === undefined) return undefined
  if (target.startsWith('plot:')) return target
  const separator = target.indexOf(':')
  const lastDot = target.lastIndexOf('.')
  if (separator <= 0 || lastDot <= separator + 1) return undefined
  return `plot:${target.slice(separator + 1, lastDot)}`
}

export function readAgentPlan(value: JsonValue): AgentPlanView | undefined {
  return readEngineAgentPlan(value)
}

export function readAgentPlans(value: JsonValue): AgentPlanView[] {
  if (isJsonRecord(value) && Array.isArray(value.plans)) {
    return value.plans.flatMap((plan) => {
      const parsed = readAgentPlan(plan)
      return parsed === undefined ? [] : [parsed]
    })
  }
  const plan = readAgentPlan(value)
  return plan === undefined ? [] : [plan]
}

export function projectVersionFrom(value: JsonValue, fallback: number): number {
  if (isJsonRecord(value) && typeof value.project_version === 'number') return value.project_version
  const candidates = records(value, (record) => typeof record.project_version === 'number')
    .map((record) => record.project_version as number)
  return candidates.length === 0 ? fallback : Math.max(...candidates)
}

export function resultKind(value: JsonValue): string | undefined {
  const candidate = records(value, (record) => typeof record.kind === 'string').at(0)
  return candidate?.kind as string | undefined
}

export function readOriginAvailability(value: JsonValue): ProductOriginAvailability | undefined {
  if (!isJsonRecord(value)) return undefined
  if (value.status === 'ready') {
    return {
      available: true,
      displayName: stringValue(value, 'display_name') ?? 'Origin',
      displayVersion: stringValue(value, 'display_version') ?? '',
      discoverySource: stringValue(value, 'discovery_source') ?? 'registry',
    }
  }
  if (value.status !== 'error' || !isJsonRecord(value.error)) return undefined
  return {
    available: false,
    code: stringValue(value.error, 'code') ?? 'UNKNOWN',
    message: stringValue(value.error, 'message') ?? 'Origin 环境未通过检测。',
    retryable: value.error.retryable !== false,
  }
}

export interface ImportSummary {
  fileCount: number
  committedCount: number
  attentionCount: number
  failedCount: number
  committedFiles: string[]
  attentionFiles: string[]
  failedFiles: string[]
  attentionDetails: string[]
  failedDetails: string[]
}

export function readImportSummary(value: JsonValue): ImportSummary {
  const entries = records(value, (record) => typeof record.kind === 'string' && (
    ['committed', 'imported', 'clarification', 'needs_input', 'rejection', 'rejected', 'failed']
      .includes(record.kind as string)
  ))
  const committedCount = entries.filter((entry) => entry.kind === 'committed' || entry.kind === 'imported').length
  const committed = entries.filter((entry) => entry.kind === 'committed' || entry.kind === 'imported')
  const attention = entries.filter((entry) => entry.kind === 'clarification' || entry.kind === 'needs_input')
  const failed = entries.filter((entry) => ['rejection', 'rejected', 'failed'].includes(entry.kind as string))
  const selectedContainer = records(value, (record) => Array.isArray(record.selected_files)).at(0)
  const selectedFiles = selectedContainer !== undefined && Array.isArray(selectedContainer.selected_files)
    ? selectedContainer.selected_files.flatMap((item) => typeof item === 'string' ? [item] : [])
    : []
  const fileName = (entry: JsonRecord): string | undefined => (
    typeof entry.source_file_name === 'string' ? entry.source_file_name : undefined
  )
  const issueMessage = (entry: JsonRecord): string => {
    const candidate = records(entry, (record) => ['question', 'message', 'reason', 'remediation'].some((key) => typeof record[key] === 'string')).at(0)
    return candidate === undefined
      ? '未返回可显示的处理原因。'
      : stringValue(candidate, 'question', 'message', 'reason', 'remediation') ?? '未返回可显示的处理原因。'
  }
  const reportedFiles = new Set(entries.flatMap((entry) => fileName(entry) ?? []))
  const unreportedFiles = selectedFiles.filter((name) => !reportedFiles.has(name))
  const committedFiles = committed.flatMap((entry) => fileName(entry) ?? [])
  const attentionFiles = attention.flatMap((entry) => fileName(entry) ?? [])
  const rejectedFiles = failed.flatMap((entry) => fileName(entry) ?? [])
  return {
    fileCount: selectedFiles.length || entries.length,
    committedCount,
    attentionCount: attention.length,
    failedCount: failed.length + unreportedFiles.length,
    committedFiles,
    attentionFiles,
    failedFiles: [...rejectedFiles, ...unreportedFiles],
    attentionDetails: attention.map((entry) => `${fileName(entry) ?? '所选文件'}：${issueMessage(entry)}`),
    failedDetails: [
      ...failed.map((entry) => `${fileName(entry) ?? '所选文件'}：${issueMessage(entry)}`),
      ...unreportedFiles.map((name) => `${name}：未返回处理结果，请重试。`),
    ],
  }
}

export function resultMessage(value: JsonValue): string | undefined {
  const candidate = records(value, (record) => ['prompt', 'question', 'message', 'reason', 'remediation'].some((key) => typeof record[key] === 'string')).at(0)
  return candidate === undefined ? undefined : stringValue(candidate, 'prompt', 'question', 'message', 'reason', 'remediation')
}
