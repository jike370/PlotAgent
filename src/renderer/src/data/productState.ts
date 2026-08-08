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

export interface ProductDataset {
  datasetId: string
  sourceVersion: number
  rowCount: number
  fieldCount: number
  fields: ProductField[]
  missingCount: number
  nonFiniteCount: number
  coordinateKinds: string[]
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
  state: string
  attemptCount: number
  failure?: { code: string; message: string; retryable: boolean }
  outputPlot?: { plotId: string; plotVersion: number }
  outputBatch?: { batchId: string; batchVersion: number }
}

export interface AgentPlanView {
  planId: string
  state: string
  confirmationState: string
  warnings: string[]
  steps: AgentPlanStep[]
  completedCount: number
  resumable: boolean
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
    return [`${datasetId}@${numberValue(record, 'source_version') ?? 1}`, {
      datasetId,
      sourceVersion: numberValue(record, 'source_version') ?? 1,
      rowCount: numberValue(record, 'row_count') ?? 0,
      fieldCount: numberValue(record, 'field_count') ?? fields.length,
      fields,
      missingCount: countQuality(quality, ['missing_count', 'null_count', 'missing_values']),
      nonFiniteCount: countQuality(quality, ['nonfinite_count', 'non_finite_count']),
      coordinateKinds: Array.isArray(record.source_coordinate_kinds)
        ? record.source_coordinate_kinds.filter((item): item is string => typeof item === 'string')
        : [],
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

function readSeriesStyle(value: JsonValue | undefined): ProductSeriesStyle {
  if (!isJsonRecord(value)) return {}
  const symbol = isJsonRecord(value.symbol) ? value.symbol : undefined
  const palette = isJsonRecord(value.palette) ? value.palette : undefined
  return {
    ...(isJsonRecord(value.color) && typeof value.color.value === 'string'
      ? { color: value.color.value } : {}),
    ...(isJsonRecord(value.line_width) && typeof value.line_width.value === 'number'
      ? { lineWidthPt: value.line_width.value } : {}),
    ...(isJsonRecord(value.marker_size) && typeof value.marker_size.value === 'number'
      ? { markerSizePt: value.marker_size.value } : {}),
    ...(typeof value.line_style === 'string' ? { lineStyle: value.line_style } : {}),
    ...(symbol && typeof symbol.shape === 'string' ? { symbolShape: symbol.shape } : {}),
    ...(symbol && typeof symbol.interior === 'string' ? { symbolInterior: symbol.interior } : {}),
    ...(palette && typeof palette.palette_id === 'string' ? { paletteId: palette.palette_id } : {}),
    ...(palette && typeof palette.reverse === 'boolean' ? { paletteReverse: palette.reverse } : {}),
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

export function readPlot(value: JsonValue): ProductPlot | undefined {
  const candidates = records(value, (record) => (
    typeof record.plot_id === 'string' && typeof record.plot_version === 'number'
  ))
  const fallback = candidates.at(-1)
  if (fallback === undefined) return undefined
  const record = candidates.find((candidate) => Array.isArray(candidate.series)) ?? fallback
  const series = Array.isArray(record.series) ? record.series.filter(isJsonRecord) : []
  const axes = Array.isArray(record.axes) ? record.axes.filter(isJsonRecord) : []
  const scales = Array.isArray(record.scales) ? record.scales.filter(isJsonRecord) : []
  const firstStyle = series.length > 0 && isJsonRecord(series[0].style) ? series[0].style : undefined
  const legend = isJsonRecord(record.legend) ? record.legend : undefined
  const xAxis = axes.find((axis) => axis.orientation === 'x')
  const leftYAxis = axes.find((axis) => axis.orientation === 'y' && axis.position !== 'right')
  const rightYAxis = axes.find((axis) => axis.orientation === 'y' && axis.position === 'right')
  const axisState = (axis: JsonRecord | undefined): ProductAxisState | undefined => {
    if (!axis || typeof axis.axis_id !== 'string') return undefined
    const scale = scales.find((candidate) => candidate.scale_id === axis.scale_id)
    const axisRange = scale && isJsonRecord(scale.axis_range) ? scale.axis_range : undefined
    const ticks = scale && isJsonRecord(scale.ticks) ? scale.ticks : undefined
    return {
      axisId: axis.axis_id,
      label: richTextValue(axis.label),
      scale: scale && typeof scale.kind === 'string' ? scale.kind : 'linear',
      ...(axisRange && typeof axisRange.minimum === 'number' ? { minimum: axisRange.minimum } : {}),
      ...(axisRange && typeof axisRange.maximum === 'number' ? { maximum: axisRange.maximum } : {}),
      reverse: axisRange?.reverse === true,
      ...(ticks && typeof ticks.major_interval === 'number' ? { majorInterval: ticks.major_interval } : {}),
      numberFormat: ticks && typeof ticks.number_format === 'string' ? ticks.number_format : 'auto',
      decimalPlaces: ticks && typeof ticks.decimal_places === 'number' ? ticks.decimal_places : 2,
    }
  }
  const publicationProfile = isJsonRecord(record.publication_profile) ? record.publication_profile : undefined
  const physicalSize = publicationProfile && isJsonRecord(publicationProfile.physical_size)
    ? publicationProfile.physical_size : undefined
  const resolvedStyle = isJsonRecord(record.resolved_style) ? record.resolved_style : undefined
  const annotations = Array.isArray(record.annotations) ? record.annotations.filter(isJsonRecord) : []
  return {
    plotId: record.plot_id as string,
    plotVersion: record.plot_version as number,
    chartId: stringValue(record, 'chart_type_id') ?? 'K01',
    plotTitle: richTextValue(record.title),
    fontSizePt: physicalLengthPt(resolvedStyle?.font_size, 9),
    projectVersion: projectVersionFrom(value, numberValue(record, 'project_version') ?? 0),
    seriesIds: series.flatMap((item) => typeof item.series_id === 'string' ? [item.series_id] : []),
    seriesStyles: series.flatMap((item) => typeof item.series_id === 'string'
      ? [{ seriesId: item.series_id, style: readSeriesStyle(item.style) }]
      : []),
    axisIds: {
      ...(xAxis && typeof xAxis.axis_id === 'string' ? { x: xAxis.axis_id } : {}),
      ...(leftYAxis && typeof leftYAxis.axis_id === 'string' ? { y: leftYAxis.axis_id } : {}),
      ...(rightYAxis && typeof rightYAxis.axis_id === 'string' ? { yRight: rightYAxis.axis_id } : {}),
    },
    axisStates: {
      ...(axisState(xAxis) ? { x: axisState(xAxis) } : {}),
      ...(axisState(leftYAxis) ? { y: axisState(leftYAxis) } : {}),
      ...(axisState(rightYAxis) ? { yRight: axisState(rightYAxis) } : {}),
    },
    canvasSizeMm: {
      width: physicalLengthMm(physicalSize?.width, 183),
      height: physicalLengthMm(physicalSize?.height, 120),
    },
    annotations: annotations.flatMap((annotation): ProductAnnotation[] => {
      if (typeof annotation.annotation_id !== 'string' || typeof annotation.kind !== 'string') return []
      return [{
        annotationId: annotation.annotation_id,
        kind: annotation.kind,
        text: richTextValue(annotation.text),
        ...(typeof annotation.x === 'number' ? { x: annotation.x } : {}),
        ...(typeof annotation.y === 'number' ? { y: annotation.y } : {}),
        ...(typeof annotation.x2 === 'number' ? { x2: annotation.x2 } : {}),
        ...(typeof annotation.y2 === 'number' ? { y2: annotation.y2 } : {}),
      }]
    }),
    specialist: readSpecialist(record.specialist),
    style: {
      ...readSeriesStyle(firstStyle),
      ...(legend && typeof legend.visible === 'boolean' ? { legendVisible: legend.visible } : {}),
      ...(legend && typeof legend.placement === 'string' ? { legendPlacement: legend.placement } : {}),
    },
    preview: readResource(value),
  }
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

function actionTitle(action: JsonRecord): string {
  const actionType = stringValue(action, 'action_type') ?? 'unknown'
  if (actionType === 'create_plot') {
    const chart = stringValue(action, 'chart_type_id')
    return chart === undefined ? '创建图形' : `绘制 ${chart}`
  }
  if (actionType === 'patch_plot') {
    const patches = Array.isArray(action.patches) ? action.patches.filter(isJsonRecord) : []
    const operations = patches.flatMap((patch) => typeof patch.operation === 'string' ? [patch.operation] : [])
    const labels: Record<string, string> = {
      set_plot_title: '修改标题', set_axis_range: '调整坐标范围', set_axis_scale: '修改坐标尺度',
      set_axis_label: '修改坐标标题', set_series_style: '修改系列样式', set_palette: '修改色板',
      set_legend_visibility: '修改图例', move_legend: '移动图例', add_annotation: '添加标注',
    }
    return operations.length === 0 ? '修改图形' : operations.map((item) => labels[item] ?? '修改图形').join('、')
  }
  const labels: Record<string, string> = {
    create_batch: '创建批量绘图', patch_batch: '修改绘图批次', create_figure: '创建组合图',
    patch_figure: '修改组合图', export_artifact: '导出结果',
  }
  return labels[actionType] ?? '执行任务'
}

export function readAgentPlan(value: JsonValue): AgentPlanView | undefined {
  const plan = records(value, (record) => (
    typeof record.plan_id === 'string' && Array.isArray(record.items) && isJsonRecord(record.source_plan)
  )).at(0)
  if (plan === undefined) return undefined
  const source = plan.source_plan as JsonRecord
  const warnings = Array.isArray(source.warnings)
    ? source.warnings.flatMap((warning) => isJsonRecord(warning) && typeof warning.message === 'string' ? [warning.message] : [])
    : []
  const steps = (plan.items as JsonValue[]).flatMap((item): AgentPlanStep[] => {
    if (!isJsonRecord(item) || typeof item.task_item_id !== 'string' || !isJsonRecord(item.action)) return []
    const failure = isJsonRecord(item.failure) && typeof item.failure.code === 'string' && typeof item.failure.message === 'string'
      ? {
        code: item.failure.code,
        message: item.failure.message,
        retryable: item.failure.retryable === true,
      }
      : undefined
    const objectOutputs = Array.isArray(item.outputs)
      ? item.outputs.flatMap((candidate) => {
        if (!isJsonRecord(candidate) || !isJsonRecord(candidate.object_ref)) return []
        return [candidate.object_ref]
      })
      : []
    const output = objectOutputs.flatMap((object) => (
      object.object_type === 'plot' && typeof object.object_id === 'string' && typeof object.object_version === 'number'
        ? [{ plotId: object.object_id, plotVersion: object.object_version }]
        : []
    )).at(-1)
    const outputBatch = objectOutputs.flatMap((object) => (
      object.object_type === 'batch' && typeof object.object_id === 'string' && typeof object.object_version === 'number'
        ? [{ batchId: object.object_id, batchVersion: object.object_version }]
        : []
    )).at(-1)
    return [{
      taskItemId: item.task_item_id,
      actionType: stringValue(item.action, 'action_type') ?? 'unknown',
      title: actionTitle(item.action),
      state: stringValue(item, 'state') ?? 'pending',
      attemptCount: numberValue(item, 'attempt_count') ?? 0,
      ...(failure === undefined ? {} : { failure }),
      ...(output === undefined ? {} : { outputPlot: output }),
      ...(outputBatch === undefined ? {} : { outputBatch }),
    }]
  })
  const state = stringValue(plan, 'state') ?? 'draft'
  return {
    planId: plan.plan_id as string,
    state,
    confirmationState: stringValue(plan, 'confirmation_state') ?? 'not_required',
    warnings,
    steps,
    completedCount: steps.filter((step) => ['succeeded', 'skipped'].includes(step.state)).length,
    resumable: ['partial_success', 'failed', 'interrupted'].includes(state),
  }
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

export function resultMessage(value: JsonValue): string | undefined {
  const candidate = records(value, (record) => ['prompt', 'message', 'reason'].some((key) => typeof record[key] === 'string')).at(0)
  return candidate === undefined ? undefined : stringValue(candidate, 'prompt', 'message', 'reason')
}
