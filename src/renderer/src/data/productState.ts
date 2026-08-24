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
  sourceBlock?: string
  instrumentMetadata: Readonly<Record<string, string>>
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

function canonicalDatasetDisplayName(dataset: ProductDataset): string {
  if (dataset.sourceFileName === undefined) return dataset.displayName
  if (dataset.sourceSheetName !== undefined) {
    return `${dataset.sourceFileName} > ${dataset.sourceSheetName}`
  }
  if (dataset.sourceBlock !== undefined) {
    return `${dataset.sourceFileName} > ${dataset.sourceBlock}`
  }
  return dataset.sourceFileName
}

export function disambiguateDatasetDisplayNames(datasets: ProductDataset[]): ProductDataset[] {
  const canonical = datasets.map((dataset) => ({
    ...dataset,
    displayName: canonicalDatasetDisplayName(dataset),
  }))
  const collisions = new Map<string, ProductDataset[]>()
  for (const dataset of canonical) {
    const key = dataset.displayName.trim().toLocaleLowerCase('en-US')
    collisions.set(key, [...(collisions.get(key) ?? []), dataset])
  }
  return canonical.map((dataset) => {
    const peers = collisions.get(dataset.displayName.trim().toLocaleLowerCase('en-US')) ?? []
    if (peers.length < 2) return dataset
    const stableSuffix = dataset.datasetId.replace(/^source:/, '').slice(-8)
    return { ...dataset, displayName: `${dataset.displayName} · ${stableSuffix}` }
  })
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
  visible?: boolean
  lineStrokeColor?: string
  lineWidthPt?: number
  lineStyle?: string
  lineOpacity?: number
  markerShape?: string
  markerSizePt?: number
  markerInterior?: string
  markerFillColor?: string
  markerStrokeColor?: string
  markerStrokeWidthPt?: number
  markerOpacity?: number
  fillColor?: string
  fillOpacity?: number
  fillStrokeColor?: string
  fillStrokeWidthPt?: number
  fillStrokeStyle?: string
}

export interface ProductColorMapState {
  seriesId: string
  palette?: string
  reverse?: boolean
  minimum?: number
  maximum?: number
  midpoint?: number
  mode?: string
  levels?: number
  missingColor?: string
  colorbarVisible?: boolean
  colorbarAnchor?: string
  colorbarTitle?: string
  colorbarTickFormat?: string
}

export interface ProductErrorStyle {
  seriesId: string
  barColor?: string
  barWidthPt?: number
  capSizePt?: number
  barOpacity?: number
  bandFillColor?: string
  bandFillOpacity?: number
  bandStrokeColor?: string
  bandStrokeWidthPt?: number
}

export interface ProductDataLabelStyle {
  seriesId: string
  visible?: boolean
  valueFormat?: string
  prefix?: string
  suffix?: string
  position?: string
  rotationDeg?: number
  fontFamily?: string
  fontSizePt?: number
  fontWeight?: string
  fontColor?: string
}

export interface ProductAxisState {
  axisId: string
  label: string
  scale: string
  minimum?: number
  maximum?: number
  reverse: boolean
  tickLabelsVisible: boolean
  majorTicksVisible: boolean
  minorTicksVisible: boolean
  tickDirection: string
  axisLineVisible: boolean
  axisTitleVisible: boolean
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
  engineData: JsonValue
  engineBindings: JsonValue[]
  plotTitle: string
  fontSizePt: number
  projectVersion: number
  seriesIds: string[]
  seriesStyles: { seriesId: string; style: ProductSeriesStyle }[]
  colorMaps: ProductColorMapState[]
  errorStyles: ProductErrorStyle[]
  dataLabelStyles: ProductDataLabelStyle[]
  axisIds: { x?: string; y?: string; yRight?: string }
  legendId?: string
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

export type WorkflowOutcomeKind = 'task_plan' | 'needs_input' | 'information' | 'unsupported' | 'no_change' | 'rejected'

export interface WorkflowQuestion {
  questionKey: string
  prompt: string
  choices: { value: string; label: string }[]
}

export interface WorkflowPlanStep {
  taskItemId: string
  actionType: string
  taskKind: 'create' | 'edit' | 'update_data'
  profileId: string
  title: string
  detail?: string
  sourceDatasetIds: string[]
  dataOperations: string[]
  bindings: WorkflowBindingView[]
  sourceFieldRoles: WorkflowSourceFieldRoleView[]
  preparedPreview?: WorkflowPreparedPreviewView
  preparedPreviewError?: WorkflowPreparedPreviewErrorView
  changes: string[]
  state: string
  attemptCount: number
  failure?: {
    code: string
    message: string
    retryable: boolean
    category?: string
    requiresUser?: boolean
    sideEffectState?: string
    diagnosticId?: string
  }
  outputPlot?: { plotId: string; plotVersion: number }
}

export interface WorkflowBindingView {
  role: string
  fieldId: string
  sourceDatasetId?: string
  fieldName?: string
}

export interface WorkflowPreparedFieldView {
  fieldId: string
  name: string
  logicalType: string
  unit?: string
}

export interface WorkflowPreparedSourceView {
  datasetId: string
  sourceVersion: number
  displayName: string
  rowCount: number
}

export interface WorkflowPreparedPreviewView {
  inputRowCount: number
  inputFieldCount: number
  outputRowCount: number
  outputFieldCount: number
  sources: WorkflowPreparedSourceView[]
  fields: WorkflowPreparedFieldView[]
  rows: JsonValue[][]
  contentHash: string
}

export interface WorkflowPreparedPreviewErrorView {
  code: string
  message: string
}

export interface WorkflowSourceFieldRoleView {
  role: string
  fieldId: string
  sourceDatasetId: string
}

export interface WorkflowPlanView {
  planId: string
  taskId?: string
  taskVersion?: number
  updatedAt?: string
  state: string
  confirmationState: string
  warnings: string[]
  steps: WorkflowPlanStep[]
  completedCount: number
  resumable: boolean
  bindings: WorkflowBindingView[]
  boundActions: JsonValue[]
}

export interface DurableTaskItemView {
  itemId: string
  state: string
  attemptCount: number
  outputPlot?: { plotId: string; plotVersion: number }
  failure?: {
    code: string
    message: string
    retryable: boolean
    category?: string
    requiresUser?: boolean
    sideEffectState?: string
    diagnosticId?: string
  }
}

export interface DurableTaskView {
  taskId: string
  taskVersion: number
  state: string
  projectRevision: number
  activeActivationId?: string
  updatedAt?: string
  completionOutcome?: 'all_succeeded' | 'completed_with_skips'
  skippedItemIds?: string[]
  items: DurableTaskItemView[]
}

export interface WorkflowOutcome {
  kind: WorkflowOutcomeKind
  title: string
  message: string
  questions?: WorkflowQuestion[]
  workflowRunId?: string
  plan?: WorkflowPlanView
  execution?: ProductPlot
  executionCount?: number
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
  const label = stringValue(value, 'canonical_unit', 'source_text')?.trim()
  return label || '未声明'
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
  const datasets = [...new Map(candidates.map((record) => {
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
    const sourceBlock = stringValue(record, 'source_block')
    const instrumentMetadata = isJsonRecord(record.instrument_metadata)
      ? Object.fromEntries(Object.entries(record.instrument_metadata).flatMap(([key, value]) => (
        typeof value === 'string' ? [[key, value]] : []
      )))
      : {}
    const sourceTableIndex = numberValue(record, 'source_table_index')
    const sampleRows = readSampleRows(record.sample_rows)
    const displayName = sourceFileName === undefined
      ? stringValue(record, 'display_name') ?? datasetId
      : sourceSheetName !== undefined
        ? `${sourceFileName} > ${sourceSheetName}`
        : sourceBlock !== undefined
          ? `${sourceFileName} > ${sourceBlock}`
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
      ...(sourceBlock === undefined ? {} : { sourceBlock }),
      instrumentMetadata,
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
  return disambiguateDatasetDisplayNames(datasets)
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
    ...(typeof action.visible === 'boolean' ? { visible: action.visible } : {}),
    ...(typeof action.line_stroke_color === 'string'
      ? { lineStrokeColor: action.line_stroke_color } : {}),
    ...(typeof action.line_width_pt === 'number' ? { lineWidthPt: action.line_width_pt } : {}),
    ...(typeof action.line_style === 'string' ? { lineStyle: action.line_style } : {}),
    ...(typeof action.line_opacity === 'number' ? { lineOpacity: action.line_opacity } : {}),
    ...(typeof action.marker_shape === 'string' ? { markerShape: action.marker_shape } : {}),
    ...(typeof action.marker_size_pt === 'number' ? { markerSizePt: action.marker_size_pt } : {}),
    ...(typeof action.marker_interior === 'string'
      ? { markerInterior: action.marker_interior } : {}),
    ...(typeof action.marker_fill_color === 'string'
      ? { markerFillColor: action.marker_fill_color } : {}),
    ...(typeof action.marker_stroke_color === 'string'
      ? { markerStrokeColor: action.marker_stroke_color } : {}),
    ...(typeof action.marker_stroke_width_pt === 'number'
      ? { markerStrokeWidthPt: action.marker_stroke_width_pt } : {}),
    ...(typeof action.marker_opacity === 'number'
      ? { markerOpacity: action.marker_opacity } : {}),
    ...(typeof action.fill_color === 'string' ? { fillColor: action.fill_color } : {}),
    ...(typeof action.fill_opacity === 'number' ? { fillOpacity: action.fill_opacity } : {}),
    ...(typeof action.fill_stroke_color === 'string'
      ? { fillStrokeColor: action.fill_stroke_color } : {}),
    ...(typeof action.fill_stroke_width_pt === 'number'
      ? { fillStrokeWidthPt: action.fill_stroke_width_pt } : {}),
    ...(typeof action.fill_stroke_style === 'string'
      ? { fillStrokeStyle: action.fill_stroke_style } : {}),
  }
}

function engineColorMap(seriesId: string, action: JsonRecord): ProductColorMapState {
  return {
    seriesId,
    ...(typeof action.palette === 'string' ? { palette: action.palette } : {}),
    ...(typeof action.reverse === 'boolean' ? { reverse: action.reverse } : {}),
    ...(typeof action.minimum === 'number' ? { minimum: action.minimum } : {}),
    ...(typeof action.maximum === 'number' ? { maximum: action.maximum } : {}),
    ...(typeof action.midpoint === 'number' ? { midpoint: action.midpoint } : {}),
    ...(typeof action.mode === 'string' ? { mode: action.mode } : {}),
    ...(typeof action.levels === 'number' ? { levels: action.levels } : {}),
    ...(typeof action.missing_color === 'string'
      ? { missingColor: action.missing_color } : {}),
    ...(typeof action.colorbar_visible === 'boolean'
      ? { colorbarVisible: action.colorbar_visible } : {}),
    ...(typeof action.colorbar_anchor === 'string'
      ? { colorbarAnchor: action.colorbar_anchor } : {}),
    ...(typeof action.colorbar_title === 'string'
      ? { colorbarTitle: action.colorbar_title } : {}),
    ...(typeof action.colorbar_tick_format === 'string'
      ? { colorbarTickFormat: action.colorbar_tick_format } : {}),
  }
}

function engineErrorStyle(seriesId: string, action: JsonRecord): ProductErrorStyle {
  return {
    seriesId,
    ...(typeof action.bar_color === 'string' ? { barColor: action.bar_color } : {}),
    ...(typeof action.bar_width_pt === 'number' ? { barWidthPt: action.bar_width_pt } : {}),
    ...(typeof action.cap_size_pt === 'number' ? { capSizePt: action.cap_size_pt } : {}),
    ...(typeof action.bar_opacity === 'number' ? { barOpacity: action.bar_opacity } : {}),
    ...(typeof action.band_fill_color === 'string'
      ? { bandFillColor: action.band_fill_color } : {}),
    ...(typeof action.band_fill_opacity === 'number'
      ? { bandFillOpacity: action.band_fill_opacity } : {}),
    ...(typeof action.band_stroke_color === 'string'
      ? { bandStrokeColor: action.band_stroke_color } : {}),
    ...(typeof action.band_stroke_width_pt === 'number'
      ? { bandStrokeWidthPt: action.band_stroke_width_pt } : {}),
  }
}

function engineDataLabelStyle(seriesId: string, action: JsonRecord): ProductDataLabelStyle {
  return {
    seriesId,
    ...(typeof action.visible === 'boolean' ? { visible: action.visible } : {}),
    ...(typeof action.value_format === 'string' ? { valueFormat: action.value_format } : {}),
    ...(typeof action.prefix === 'string' ? { prefix: action.prefix } : {}),
    ...(typeof action.suffix === 'string' ? { suffix: action.suffix } : {}),
    ...(typeof action.position === 'string' ? { position: action.position } : {}),
    ...(typeof action.rotation_deg === 'number' ? { rotationDeg: action.rotation_deg } : {}),
    ...(typeof action.font_family === 'string' ? { fontFamily: action.font_family } : {}),
    ...(typeof action.font_size_pt === 'number' ? { fontSizePt: action.font_size_pt } : {}),
    ...(typeof action.font_weight === 'string' ? { fontWeight: action.font_weight } : {}),
    ...(typeof action.font_color === 'string' ? { fontColor: action.font_color } : {}),
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
  const engineData = document.data
  const engineBindings = Array.isArray(document.bindings)
    ? document.bindings.filter(isJsonRecord)
    : []
  if (
    plotId === undefined
    || plotVersion === undefined
    || profileId === undefined
    || !isJsonRecord(engineData)
    || engineBindings.length === 0
  ) return undefined
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
  const mergedActionTarget = (operation: string, target: string): JsonRecord => (
    actionTarget(operation, target).reduce<JsonRecord>((result, action) => {
      if (operation === 'set_axis' && action.bounds_mode === 'automatic') {
        delete result.minimum
        delete result.maximum
      }
      for (const [key, value] of Object.entries(action)) {
        if (value !== null && value !== undefined) result[key] = value
      }
      return result
    }, {})
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
    const current = mergedActionTarget('set_axis', axisId)
    return {
      axisId,
      label: typeof current.label === 'string' ? current.label : '',
      scale: typeof current.scale === 'string' ? current.scale : 'linear',
      ...(typeof current.minimum === 'number' ? { minimum: current.minimum } : {}),
      ...(typeof current.maximum === 'number' ? { maximum: current.maximum } : {}),
      reverse: current.reverse === true,
      tickLabelsVisible: current.tick_labels_visible !== false,
      majorTicksVisible: current.major_ticks_visible !== false,
      minorTicksVisible: current.minor_ticks_visible !== false,
      tickDirection: typeof current.tick_direction === 'string' ? current.tick_direction : 'out',
      axisLineVisible: current.axis_line_visible !== false,
      axisTitleVisible: current.axis_title_visible !== false,
      numberFormat: 'auto',
      decimalPlaces: 2,
    }
  }
  const title = actions.filter((action) => action.operation === 'set_title').at(-1)
  const legendId = objectId('legend')
  const legend = legendId === undefined ? undefined : mergedActionTarget('set_legend', legendId)
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
    engineData,
    engineBindings,
    plotTitle: title && typeof title.text === 'string' ? title.text : '',
    fontSizePt: 9,
    projectVersion: projectVersionFrom(value, 0),
    seriesIds,
    seriesStyles: seriesIds.map((seriesId) => ({
      seriesId,
      style: engineSeriesStyle(mergedActionTarget('set_series_style', seriesId)),
    })),
    colorMaps: seriesIds.map((seriesId) => engineColorMap(
      seriesId,
      actionTarget('set_colormap', seriesId).at(-1) ?? {},
    )),
    errorStyles: seriesIds.map((seriesId) => engineErrorStyle(
      seriesId,
      actionTarget('set_error_style', seriesId).at(-1) ?? {},
    )),
    dataLabelStyles: seriesIds.map((seriesId) => engineDataLabelStyle(
      seriesId,
      actionTarget('set_data_labels', seriesId).at(-1) ?? {},
    )),
    axisIds,
    ...(legendId === undefined ? {} : { legendId }),
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

export function readWorkflowOutcome(value: JsonValue): WorkflowOutcome {
  const root = isJsonRecord(value) ? value : undefined
  if (root !== undefined && Array.isArray(root.pending_inputs)) {
    const pending = root.pending_inputs.find(isJsonRecord)
    if (pending !== undefined) return readWorkflowOutcome(pending)
  }
  const outcome = root === undefined ? undefined : stringValue(root, 'outcome')
  if (outcome === 'draft_ready' || readWorkflowPlan(value) !== undefined) {
    const plan = readWorkflowPlan(value)
    return {
      kind: 'task_plan',
      title: plan?.state === 'succeeded' ? '任务已完成' : '计划已生成',
      message: plan?.state === 'succeeded'
        ? `已完成 ${plan.completedCount} 个可追溯任务项。`
        : '检查数据、字段绑定、图形与视觉修改后确认执行。',
      ...(plan === undefined ? {} : { plan }),
      executionCount: plan?.completedCount ?? 0,
    }
  }
  if (outcome === 'needs_input' && root !== undefined) {
    const questions = Array.isArray(root.questions)
      ? root.questions.flatMap((question): WorkflowQuestion[] => {
        if (!isJsonRecord(question) || typeof question.question_key !== 'string' || typeof question.prompt !== 'string') return []
        const choices = Array.isArray(question.choices)
          ? question.choices.flatMap((choice) => typeof choice === 'string'
            ? [{ value: choice, label: choice }]
            : [])
          : []
        return [{ questionKey: question.question_key, prompt: question.prompt, choices }]
      })
      : []
    const workflowRunId = stringValue(root, 'workflow_run_id')
    return {
      kind: 'needs_input',
      title: '需要补充信息',
      message: decisionMessage(root),
      questions,
      ...(workflowRunId === undefined ? {} : { workflowRunId }),
    }
  }
  if (outcome === 'information_ready' && root !== undefined) {
    return { kind: 'information', title: '检查完成', message: decisionMessage(root) }
  }
  if (outcome === 'unsupported' && root !== undefined) return { kind: 'unsupported', title: '当前不支持', message: decisionMessage(root) }
  if (outcome === 'cancelled') return { kind: 'no_change', title: '任务已取消', message: '任务已停止，项目未发生更改。' }
  return { kind: 'rejected', title: '无法识别结果', message: 'Core 未返回受支持的工作流结果。' }
}

const planRevisionRequiredErrorCodes = new Set([
  'WORKFLOW_BINDING_OUTPUT_MISSING',
  'WORKFLOW_NON_ISOMORPHIC',
  'WORKFLOW_SOURCES_NOT_COMBINED',
  'WORKFLOW_SOURCE_UNUSED',
])

export function readWorkflowPlan(value: JsonValue): WorkflowPlanView | undefined {
  const root = isJsonRecord(value) ? value : undefined
  const durableTask = root !== undefined && isJsonRecord(root.task) ? root.task : undefined
  const durablePlan = root !== undefined && isJsonRecord(root.plan) ? root.plan : undefined
  const durableSnapshot: JsonRecord | undefined = durableTask !== undefined && durablePlan !== undefined
    && typeof durableTask.state === 'string' && Array.isArray(durableTask.items)
    ? {
      ...durableTask,
      state: durableTask.state,
      plan: durablePlan,
      item_progress: durableTask.items,
    }
    : undefined
  const snapshot = durableSnapshot ?? records(value, (record) => (
    isJsonRecord(record.plan)
    && typeof record.state === 'string'
    && Array.isArray(record.item_progress)
  )).at(0)
  if (snapshot === undefined || !isJsonRecord(snapshot.plan)) return undefined
  const presentation = root !== undefined && (
    Array.isArray(root.prepared_previews) || Array.isArray(root.prepared_preview_errors)
  ) ? root : snapshot
  const plan = snapshot.plan
  if (typeof plan.plan_id !== 'string' || !Array.isArray(plan.items)) return undefined
  const progressValues = snapshot.item_progress as JsonValue[]
  const progress = new Map(
    progressValues.flatMap((item): [string, JsonRecord][] => (
      isJsonRecord(item) && typeof item.item_id === 'string' ? [[item.item_id, item]] : []
    )),
  )
  const completion = isJsonRecord(snapshot.completion) ? snapshot.completion : undefined
  const completionOutcome = completion === undefined
    ? undefined
    : stringValue(completion, 'outcome')
  const skippedItemIds = new Set(
    completion !== undefined && Array.isArray(completion.skipped_item_ids)
      ? completion.skipped_item_ids.filter((item): item is string => typeof item === 'string')
      : [],
  )
  const bindings: WorkflowBindingView[] = []
  const boundActions: JsonValue[] = []
  const preparedPreviews = new Map<string, WorkflowPreparedPreviewView>()
  if (Array.isArray(presentation.prepared_previews)) {
    for (const preview of presentation.prepared_previews) {
      if (!isJsonRecord(preview) || typeof preview.item_id !== 'string') continue
      const sources = Array.isArray(preview.sources) ? preview.sources.flatMap((source): WorkflowPreparedSourceView[] => {
        if (!isJsonRecord(source)) return []
        const datasetId = stringValue(source, 'source_dataset_id')
        const sourceVersion = numberValue(source, 'source_version')
        const displayName = stringValue(source, 'display_name')
        const rowCount = numberValue(source, 'row_count')
        return datasetId === undefined || sourceVersion === undefined || displayName === undefined || rowCount === undefined
          ? []
          : [{ datasetId, sourceVersion, displayName, rowCount }]
      }) : []
      const fields = Array.isArray(preview.fields) ? preview.fields.flatMap((field): WorkflowPreparedFieldView[] => {
        if (!isJsonRecord(field)) return []
        const fieldId = stringValue(field, 'field_id')
        const name = stringValue(field, 'name')
        const logicalType = stringValue(field, 'logical_type')
        const unit = stringValue(field, 'unit_label')
        return fieldId === undefined || name === undefined || logicalType === undefined
          ? []
          : [{ fieldId, name, logicalType, ...(unit === undefined ? {} : { unit }) }]
      }) : []
      const rows = Array.isArray(preview.rows)
        ? preview.rows.flatMap((row): JsonValue[][] => Array.isArray(row) ? [[...row]] : [])
        : []
      const inputRowCount = numberValue(preview, 'input_row_count')
      const inputFieldCount = numberValue(preview, 'input_field_count')
      const outputRowCount = numberValue(preview, 'output_row_count')
      const outputFieldCount = numberValue(preview, 'output_field_count')
      const contentHash = stringValue(preview, 'content_hash')
      if (
        sources.length === 0
        || fields.length === 0
        || inputRowCount === undefined
        || inputFieldCount === undefined
        || outputRowCount === undefined
        || outputFieldCount === undefined
        || contentHash === undefined
        || fields.length !== outputFieldCount
        || rows.some((row) => row.length !== fields.length)
      ) continue
      preparedPreviews.set(preview.item_id, {
        inputRowCount,
        inputFieldCount,
        outputRowCount,
        outputFieldCount,
        sources,
        fields,
        rows,
        contentHash,
      })
    }
  }
  const preparedPreviewErrors = new Map<string, WorkflowPreparedPreviewErrorView>()
  if (Array.isArray(presentation.prepared_preview_errors)) {
    for (const failure of presentation.prepared_preview_errors) {
      if (!isJsonRecord(failure)) continue
      const itemId = stringValue(failure, 'item_id')
      const code = stringValue(failure, 'code')
      const message = stringValue(failure, 'message')
      if (itemId !== undefined && code !== undefined && message !== undefined) {
        preparedPreviewErrors.set(itemId, { code, message })
      }
    }
  }
  const steps = plan.items.flatMap((item): WorkflowPlanStep[] => {
    if (!isJsonRecord(item) || typeof item.item_id !== 'string') return []
    const itemProgress: JsonRecord = progress.get(item.item_id) ?? {}
    const stepBindings: WorkflowBindingView[] = []
    const sourceIds = new Map<string, string>()
    const fieldNamesById = new Map<string, string>()
    const fieldNamesByAlias = new Map<string, string>()
    if (Array.isArray(item.sources)) {
      for (const source of item.sources) {
        if (!isJsonRecord(source)) continue
        const sourceAlias = stringValue(source, 'source_alias')
        const sourceDatasetId = stringValue(source, 'source_dataset_id')
        if (sourceAlias !== undefined && sourceDatasetId !== undefined) {
          sourceIds.set(sourceAlias, sourceDatasetId)
        }
      }
    }
    if (Array.isArray(item.resolved_fields)) {
      for (const field of item.resolved_fields) {
        if (!isJsonRecord(field)) continue
        const fieldId = stringValue(field, 'field_id')
        const alias = stringValue(field, 'field_alias')
        const name = stringValue(field, 'name')
        if (fieldId !== undefined && name !== undefined) fieldNamesById.set(fieldId, name)
        if (alias !== undefined && name !== undefined) fieldNamesByAlias.set(alias, name)
      }
    }
    if (Array.isArray(item.bindings)) {
      for (const binding of item.bindings) {
        if (!isJsonRecord(binding)) continue
        const role = stringValue(binding, 'role')
        const fieldId = stringValue(binding, 'field_id')
        const sourceAlias = stringValue(binding, 'source_alias')
        if (role !== undefined && fieldId !== undefined) {
          const sourceDatasetId = sourceAlias === undefined ? undefined : sourceIds.get(sourceAlias)
          const fieldName = fieldNamesById.get(fieldId)
          const view = {
            role,
            fieldId,
            ...(sourceDatasetId === undefined ? {} : { sourceDatasetId }),
            ...(fieldName === undefined ? {} : { fieldName }),
          }
          bindings.push(view)
          stepBindings.push(view)
        }
      }
    }
    const sourceFieldRoles: WorkflowSourceFieldRoleView[] = []
    if (Array.isArray(item.binding_evidence)) {
      for (const evidence of item.binding_evidence) {
        if (!isJsonRecord(evidence)) continue
        const role = stringValue(evidence, 'role')
        const fieldId = stringValue(evidence, 'field_id')
        const sourceAlias = stringValue(evidence, 'source_alias')
        const sourceDatasetId = sourceAlias === undefined ? undefined : sourceIds.get(sourceAlias)
        if (role !== undefined && fieldId !== undefined && sourceDatasetId !== undefined) {
          sourceFieldRoles.push({ role, fieldId, sourceDatasetId })
        }
      }
    }
    if (sourceFieldRoles.length === 0) {
      for (const binding of stepBindings) {
        if (binding.sourceDatasetId !== undefined) {
          sourceFieldRoles.push({
            role: binding.role,
            fieldId: binding.fieldId,
            sourceDatasetId: binding.sourceDatasetId,
          })
        }
      }
    }
    const dataOperations = Array.isArray(item.data_operations)
      ? item.data_operations.flatMap((operation) => workflowDataOperationSummary(operation, fieldNamesByAlias))
      : []
    const visualActions = Array.isArray(item.visual_actions) ? item.visual_actions : []
    boundActions.push(...visualActions)
    const changes = visualActions.flatMap(workflowActionSummary)
    const rawItemState = stringValue(itemProgress, 'state') ?? 'pending'
    const state = skippedItemIds.has(item.item_id) ? 'cancelled'
      : rawItemState === 'staged' ? 'pending'
      : rawItemState === 'repairable_failed' ? 'failed'
        : rawItemState
    const rawTaskKind = stringValue(item, 'task_kind')
    const taskKind = rawTaskKind === 'edit'
      ? 'edit'
      : rawTaskKind === 'update_data'
        ? 'update_data'
        : 'create'
    const profileId = stringValue(item, 'profile_id') ?? '图形'
    const outputPlotId = stringValue(itemProgress, 'output_plot_id')
    const outputPlotVersion = numberValue(itemProgress, 'output_plot_version')
    const durableError = isJsonRecord(itemProgress.last_error) ? itemProgress.last_error : undefined
    const errorCode = stringValue(itemProgress, 'error_code')
      ?? (durableError === undefined ? undefined : stringValue(durableError, 'code'))
    const errorMessage = stringValue(itemProgress, 'error_message')
      ?? (durableError === undefined ? undefined : stringValue(durableError, 'message'))
    const errorRetryable = typeof itemProgress.error_retryable === 'boolean'
      ? itemProgress.error_retryable
      : typeof durableError?.retryable === 'boolean'
        ? durableError.retryable
      : undefined
    const errorCategory = durableError === undefined ? undefined : stringValue(durableError, 'category')
    const errorSideEffectState = durableError === undefined ? undefined : stringValue(durableError, 'side_effect_state')
    const errorRequiresUser = durableError?.requires_user === true
    const diagnosticId = durableError === undefined ? undefined : stringValue(durableError, 'diagnostic_id')
    const detailParts = [
      ...(stepBindings.length > 0 ? [`${stepBindings.length} 个字段角色`] : []),
      ...(dataOperations.length > 0 ? [`${dataOperations.length} 项数据处理`] : []),
      ...(taskKind === 'update_data' && changes.length > 0 ? [`${changes.length} 项视觉修改`] : []),
    ]
    const preparedPreview = preparedPreviews.get(item.item_id)
    const preparedPreviewError = preparedPreviewErrors.get(item.item_id)
    return [{
      taskItemId: item.item_id,
      actionType: 'workflow_item',
      taskKind,
      profileId,
      title: `${taskKind === 'edit' ? '修改' : taskKind === 'update_data' ? '更新数据' : '创建'} ${profileId}`,
      detail: taskKind === 'edit'
        ? changes.length > 0 ? `${changes.length} 项视觉修改` : undefined
        : detailParts.length > 0 ? detailParts.join(' · ') : undefined,
      sourceDatasetIds: [...sourceIds.values()],
      dataOperations,
      bindings: stepBindings,
      sourceFieldRoles,
      ...(preparedPreview === undefined ? {} : { preparedPreview }),
      ...(preparedPreviewError === undefined ? {} : { preparedPreviewError }),
      changes,
      state,
      attemptCount: numberValue(itemProgress, 'attempt_count') ?? 0,
      ...(errorCode === undefined || errorMessage === undefined || errorRetryable === undefined ? {} : {
        failure: {
          code: errorCode,
          message: errorMessage,
          retryable: errorRetryable,
          ...(errorCategory === undefined ? {} : { category: errorCategory }),
          ...(errorSideEffectState === undefined ? {} : { sideEffectState: errorSideEffectState }),
          ...(errorRequiresUser ? { requiresUser: true } : {}),
          ...(diagnosticId === undefined ? {} : { diagnosticId }),
        },
      }),
      ...(outputPlotId === undefined || outputPlotVersion === undefined ? {} : {
        outputPlot: { plotId: outputPlotId, plotVersion: outputPlotVersion },
      }),
    }]
  })
  const rawState = snapshot.state as string
  const state = rawState === 'completed_verified'
    ? completionOutcome === 'completed_with_skips' ? 'completed_with_skips' : 'succeeded'
    : rawState === 'executing' ? 'ready'
      : rawState === 'partial' ? 'partially_succeeded'
        : rawState
  const durableConfirmation = root === undefined
    ? undefined
    : stringValue(root, 'confirmation_state')
  return {
    planId: plan.plan_id,
    ...(typeof snapshot.task_id === 'string' ? { taskId: snapshot.task_id } : {}),
    ...(typeof snapshot.task_version === 'number' ? { taskVersion: snapshot.task_version } : {}),
    ...(typeof snapshot.updated_at === 'string' ? { updatedAt: snapshot.updated_at } : {}),
    state,
    confirmationState: durableConfirmation ?? (
      state === 'awaiting_confirmation' || state === 'awaiting_reconfirmation' ? 'pending'
        : state === 'rejected' ? 'rejected' : 'confirmed'
    ),
    warnings: [],
    steps,
    completedCount: steps.filter((step) => step.state === 'succeeded').length,
    resumable: state === 'partially_succeeded'
      && steps.some((step) => step.failure?.retryable === true
        && step.attemptCount < 2
        && !planRevisionRequiredErrorCodes.has(step.failure.code)
        && step.failure.category === 'deterministic_technical'
        && step.failure.requiresUser !== true
        && step.failure.sideEffectState === 'known_none'),
    bindings,
    boundActions,
  }
}

export function readDurableTasks(value: JsonValue): DurableTaskView[] {
  if (!isJsonRecord(value)) return []
  const candidates = Array.isArray(value.durable_tasks)
    ? value.durable_tasks
    : isJsonRecord(value.task)
      ? [value.task]
      : typeof value.task_id === 'string'
        ? [value]
        : []
  return candidates.flatMap((entry): DurableTaskView[] => {
    if (
      !isJsonRecord(entry)
      || typeof entry.task_id !== 'string'
      || typeof entry.task_version !== 'number'
      || typeof entry.state !== 'string'
      || typeof entry.project_revision !== 'number'
      || !Array.isArray(entry.items)
    ) return []
    const items = entry.items.flatMap((item): DurableTaskItemView[] => {
      if (!isJsonRecord(item) || typeof item.item_id !== 'string' || typeof item.state !== 'string') return []
      const error = isJsonRecord(item.last_error) ? item.last_error : undefined
      const outputPlotId = stringValue(item, 'output_plot_id')
      const outputPlotVersion = numberValue(item, 'output_plot_version')
      const code = error === undefined ? undefined : stringValue(error, 'code')
      const message = error === undefined ? undefined : stringValue(error, 'message')
      return [{
        itemId: item.item_id,
        state: item.state,
        attemptCount: numberValue(item, 'attempt_count') ?? 0,
        ...(outputPlotId === undefined || outputPlotVersion === undefined
          ? {}
          : { outputPlot: { plotId: outputPlotId, plotVersion: outputPlotVersion } }),
        ...(code === undefined || message === undefined
          ? {}
          : {
              failure: {
                code,
                message,
                retryable: error?.retryable === true,
                ...(typeof error?.category === 'string'
                  ? { category: error.category }
                  : {}),
                ...(error?.requires_user === true
                  ? { requiresUser: true }
                  : {}),
                ...(typeof error?.side_effect_state === 'string'
                  ? { sideEffectState: error.side_effect_state }
                  : {}),
                ...(typeof error?.diagnostic_id === 'string'
                  ? { diagnosticId: error.diagnostic_id }
                  : {}),
              },
            }),
      }]
    })
    const completion = isJsonRecord(entry.completion) ? entry.completion : undefined
    const completionOutcome = completion === undefined
      ? undefined
      : stringValue(completion, 'outcome')
    const skippedItemIds = completion !== undefined && Array.isArray(completion.skipped_item_ids)
      ? completion.skipped_item_ids.filter((item): item is string => typeof item === 'string')
      : []
    return [{
      taskId: entry.task_id,
      taskVersion: entry.task_version,
      state: entry.state,
      projectRevision: entry.project_revision,
      ...(typeof entry.active_activation_id === 'string'
        ? { activeActivationId: entry.active_activation_id }
        : {}),
      ...(typeof entry.updated_at === 'string' ? { updatedAt: entry.updated_at } : {}),
      ...(completionOutcome === 'all_succeeded' || completionOutcome === 'completed_with_skips'
        ? { completionOutcome }
        : {}),
      ...(skippedItemIds.length > 0 ? { skippedItemIds } : {}),
      items,
    }]
  })
}

function workflowActionSummary(value: JsonValue): string[] {
  if (!isJsonRecord(value)) return []
  const operation = stringValue(value, 'operation')
  const target = stringValue(value, 'target_alias')
  const values = Object.entries(value)
    .filter(([key, item]) => !['operation', 'target_alias'].includes(key) && item !== null)
    .map(([key, item]) => `${workflowParameterLabel(key)}=${String(item)}`)
  if (values.length === 0) return []
  const operationLabel: Record<string, string> = {
    set_title: '标题',
    set_axis: '坐标轴',
    set_series_style: '系列样式',
    set_legend: '图例',
    set_colormap: '颜色映射',
    set_error_style: '误差样式',
    set_data_labels: '数据标签',
    set_chart_parameter: '图形参数',
    add_annotation: '标注',
  }
  const prefix = operation === undefined ? '视觉修改' : (operationLabel[operation] ?? operation)
  return [`${prefix}${target === undefined || target === 'plot' ? '' : `（${target}）`}：${values.join('，')}`]
}

function workflowDataOperationSummary(value: JsonValue, fieldNames: ReadonlyMap<string, string>): string[] {
  if (!isJsonRecord(value)) return []
  const operation = stringValue(value, 'operation')
  const fieldLabel = (alias: string | undefined): string => alias === undefined
    ? '字段'
    : (fieldNames.get(alias) ?? alias)
  const scalar = (item: JsonValue | undefined): string => Array.isArray(item)
    ? item.map((entry) => String(entry)).join('、')
    : String(item ?? '')
  if (operation === 'filter_rows' && Array.isArray(value.predicates)) {
    const operatorLabels: Record<string, string> = {
      equal: '=',
      not_equal: '≠',
      less_than: '<',
      less_or_equal: '≤',
      greater_than: '>',
      greater_or_equal: '≥',
      is_missing: '为空',
      is_not_missing: '不为空',
      in_values: '属于',
    }
    const predicates = value.predicates.flatMap((predicate): string[] => {
      if (!isJsonRecord(predicate)) return []
      const alias = stringValue(predicate, 'field_alias')
      const operator = stringValue(predicate, 'operator')
      if (operator === undefined) return []
      const label = operatorLabels[operator] ?? operator
      return [`${fieldLabel(alias)} ${label}${operator.startsWith('is_') ? '' : ` ${scalar(predicate.value)}`}`]
    })
    return predicates.length === 0 ? ['筛选数据'] : [`筛选：${predicates.join(value.combine === 'any' ? ' 或 ' : ' 且 ')}`]
  }
  if (operation === 'sort_rows' && Array.isArray(value.keys)) {
    const keys = value.keys.flatMap((key): string[] => {
      if (!isJsonRecord(key)) return []
      const direction = stringValue(key, 'direction') === 'descending' ? '降序' : '升序'
      return [`${fieldLabel(stringValue(key, 'field_alias'))} ${direction}`]
    })
    return keys.length === 0 ? ['排序数据'] : [`排序：${keys.join('，')}`]
  }
  const labels: Record<string, string> = {
    select_fields: '选择字段',
    reshape_long_to_wide: '长表转宽表',
    reshape_wide_to_long: '宽表转长表',
    concatenate_sources: '合并数据表',
    rename_field: '重命名字段',
    derive_column: '计算派生列',
    convert_type: '转换字段类型',
    convert_unit: '单位换算',
    declare_unit: '声明缺失单位',
    bucketize_numeric: '数值分组',
  }
  return operation === undefined ? [] : [labels[operation] ?? operation]
}

function workflowParameterLabel(key: string): string {
  const labels: Record<string, string> = {
    text: '文本',
    label: '标题',
    scale: '刻度',
    reverse: '反向',
    line_stroke_color: '线色',
    line_width_pt: '线宽',
    line_style: '线型',
    marker_shape: '点形',
    marker_size_pt: '点大小',
    marker_fill_color: '点填充',
    marker_stroke_color: '点边框',
    fill_color: '填充色',
    visible: '显示',
    anchor: '位置',
  }
  return labels[key] ?? key
}

export function readWorkflowPlans(value: JsonValue): WorkflowPlanView[] {
  if (isJsonRecord(value) && Array.isArray(value.task_plans)) {
    return value.task_plans.flatMap((plan) => {
      const parsed = readWorkflowPlan(plan)
      return parsed === undefined ? [] : [parsed]
    })
  }
  const plan = readWorkflowPlan(value)
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
