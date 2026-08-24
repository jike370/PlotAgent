import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  Activity,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  Download,
  FileChartColumn,
  FileSpreadsheet,
  FileUp,
  FolderOpen,
  Images,
  Layers3,
  Library,
  ListChecks,
  LoaderCircle,
  Play,
  Redo2,
  SendHorizontal,
  Settings2,
  StopCircle,
  TableProperties,
  TriangleAlert,
  Undo2,
} from 'lucide-react'

import type {
  CoreStatus,
  FieldMappingInput,
  TaskEvent,
  WorkflowPlotSelection,
} from '../../../shared/desktop-contract'
import { MAX_WORKFLOW_SOURCES } from '../../../shared/desktop-contract'
import { chartCatalog, type ChartType } from '../data/chartCatalog'
import type {
  WorkflowBindingView,
  WorkflowOutcome,
  WorkflowPlanView,
  ProductDataset,
  ProductPlot,
  ProductProject,
} from '../data/productState'
import {
  readConversationTimeline,
  writeConversationTimeline,
  type ConversationExportRecord,
  type ConversationTextItem,
  type ConversationTimelineItem,
} from '../data/conversationPersistence'
import { parsePlotMentions, registerPlotReferences, type PlotReference } from '../data/plotReferences'
import { AgentMessage } from './ConversationPrimitives'
import {
  fieldMatchesRole,
  suggestedFieldMapping,
  type MappingSuggestionRole,
} from './mappingSuggestions'

export type ScopeMode = 'current' | 'selected'

export interface ProductNotice {
  kind: 'info' | 'success' | 'warning' | 'error'
  title: string
  message: string
  actionLabel?: string
  onAction?: () => void
}

export interface ExportRecordView {
  exportId: string
  resourceId: string
  fileName: string
  format: 'png' | 'svg' | 'opju'
  targetKind: 'plot'
  targetId: string
  plotVersion: number
  artifactHash?: string
  artifactSize?: number
}

interface ConversationWorkspaceProps {
  core: CoreStatus
  project?: ProductProject
  datasets: ProductDataset[]
  activeDataset?: ProductDataset
  selectedWorkflowSourceIds: string[]
  selectedChart?: ChartType
  multiChartTask?: boolean
  plot?: ProductPlot
  projectPlots: ProductPlot[]
  exportRecord?: ExportRecordView
  notice?: ProductNotice
  importNotice?: ProductNotice
  busyAction?: string
  agentRuntimeLabel?: string
  agentRuntimeTaskId?: string
  workflowOutcome?: WorkflowOutcome
  workflowPlan?: WorkflowPlanView
  agentConfigured: boolean
  taskEvents: TaskEvent[]
  previewMode?: boolean
  onOpenSample: () => void
  onImportData: () => void
  onOpenProject: () => void
  onOpenLibrary: () => void
  onSelectDataset: (datasetId: string) => void
  onToggleWorkflowSource: (datasetId: string) => void
  onConfirmMapping: (mapping: FieldMappingInput) => void
  onConfirmMultiSourceMapping: (mapping: FieldMappingInput) => void
  onAgentInstruction: (instruction: string, selectedPlots: WorkflowPlotSelection[]) => void
  onConfirmWorkflowPlan: (planId: string) => void
  onRejectWorkflowPlan: (planId: string) => void
  onRunWorkflowPlan: (planId: string) => void
  onResumeWorkflowPlan: (planId: string) => void
  onConfigureAgent: () => void
  onExport: (format: 'png' | 'svg' | 'opju') => void
  onOpenExport: (resourceId: string) => void
  onRevealExport: (resourceId: string) => void
  onCreateBatch: () => void
  onOpenFocus: () => void
  onOpenTasks: () => void
  onCancelTask: (taskId: string) => void
  onAcceptPartialTask: (taskId: string) => void
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void
}

const fieldNames: Record<string, string> = {
  time_min: '时间',
  signal_au: '信号',
  signal: '信号',
  fluorescence_au: '荧光强度',
  fluorescence: '荧光强度',
  intensity: '强度',
  temperature_c: '温度',
  temperature: '温度',
  condition: '条件',
  value: '数值',
  error: '误差',
  p_value: 'P 值',
  pvalue: 'P 值',
  group: '分组',
  category: '类别',
  label: '标签',
  sheet1: '标签',
  'sheet 1': '标签',
}
const logicalTypes: Record<string, string> = {
  numeric: '数值', number: '数值', integer: '整数', float: '数值', decimal: '数值', categorical: '分类', string: '文本', datetime: '日期时间', boolean: '布尔值',
}
const physicalTypes: Record<string, string> = {
  float64: '浮点数', float32: '浮点数', int64: '整数', int32: '整数', string: '文本', object: '文本', bool: '布尔值', boolean: '布尔值', datetime64: '日期时间',
}
function displayFieldName(name: string): string {
  return fieldNames[name.toLocaleLowerCase('en-US')] ?? name
}

function displayLogicalType(type: string): string {
  return logicalTypes[type.toLocaleLowerCase('en-US')] ?? type
}

function displayPhysicalType(type: string): string {
  return physicalTypes[type.toLocaleLowerCase('en-US')] ?? type
}

function isExpectedPhysicalType(logicalType: string, physicalType: string): boolean {
  const logical = logicalType.toLocaleLowerCase('en-US')
  const physical = physicalType.toLocaleLowerCase('en-US')
  const expected: Record<string, Set<string>> = {
    numeric: new Set(['float64', 'float32', 'int64', 'int32']),
    number: new Set(['float64', 'float32', 'int64', 'int32']),
    integer: new Set(['int64', 'int32']),
    float: new Set(['float64', 'float32', 'int64', 'int32']),
    decimal: new Set(['float64', 'float32', 'int64', 'int32']),
    categorical: new Set(['string', 'object']),
    string: new Set(['string', 'object']),
    datetime: new Set(['datetime64']),
    boolean: new Set(['bool', 'boolean']),
  }
  return expected[logical]?.has(physical) === true
}

function FieldMeta({ field }: { field: ProductDataset['fields'][number] }): React.JSX.Element {
  const unit = field.unit.trim()
  const declaredUnit = unit.length > 0 && !['未声明', 'unknown', 'none'].includes(unit.toLocaleLowerCase('en-US'))
  const physicalType = displayPhysicalType(field.physicalType)
  const showPhysicalType = !isExpectedPhysicalType(field.logicalType, field.physicalType)
  return (
    <small className="field-meta" title={`${displayLogicalType(field.logicalType)} · ${physicalType}${declaredUnit ? ` · ${unit}` : ''}`}>
      <span>{displayLogicalType(field.logicalType)}</span>
      {showPhysicalType && <span>{physicalType}</span>}
      {declaredUnit && <span>{unit}</span>}
    </small>
  )
}

interface MappingRole extends MappingSuggestionRole {
  label: string
}

const mappingRoleLabels: Record<string, string> = {
  middle: '中间界限',
  x: 'X', y: 'Y', z: 'Z', category: '类别', group: '分组', component: '组成', value: '数值',
  center: '中心值', x_err_minus: 'X 负误差', x_err_plus: 'X 正误差', y_err_minus: 'Y 负误差', y_err_plus: 'Y 正误差', lower: '下限', upper: '上限', error: '误差', size: '大小', color: '颜色',
  time: '时间', event: '事件', row: '行', column: '列', row_label: '行标签', column_label: '列标签',
  facet: '分面', base_x: '基础 X', base_y: '基础 Y', panel: '面板图', survival: '生存率', risk_count: '风险人数',
  dose: '剂量', response: '响应', parameter: '预计算参数', label: '标签', effect: '效应值', weight: '权重',
  spectral_axis: '谱轴', intensity: '强度', angle: '角度', peak_label: '峰标签', z_real: "Z'", z_imaginary: "-Z''",
  frequency: '频率', actual: '真实类别', predicted: '预测类别', count: '已聚合计数',
  baseline: '基线', start: '起点', end: '终点', series_1: '系列 1', series_2: '系列 2', series_3: '系列 3', delta: '变化量', item: '项目', actual_value: '实际值', target: '目标',
  range1: '区间 1', range2: '区间 2', range3: '区间 3', left: '左轴数值', right: '右轴数值',
  method_a: '方法 A', method_b: '方法 B', series: '系列', feature: '特征', log2fc: 'log2FC', pvalue: 'P 值', qvalue: 'Q 值',
}

function displayWorkflowRole(role: string): string {
  if (role.startsWith('series_')) return `系列 ${role.slice('series_'.length)}`
  return mappingRoleLabels[role] ?? role
}

function displayDataOperation(operation: string): string {
  const operationLabels: Array<[string, string]> = [
    ['align_sources_on_x', '按 X 列对齐多个数据来源'],
    ['concatenate_sources', '合并多个数据来源'],
    ['convert_text_to_numeric', '将文本数值转换为数值列'],
    ['convert_units', '换算数据单位'],
    ['drop_invalid_rows', '移除无法绘图的数据行'],
    ['filter_rows', '筛选数据行'],
    ['sort_rows', '按指定字段排序'],
    ['pivot_long_to_wide', '将长表整理为多系列表'],
  ]
  return operationLabels.find(([key]) => operation.startsWith(key))?.[1] ?? operation.replaceAll('_', ' ')
}

function mappingRoles(chart: ChartType): MappingRole[] {
  const categorical = new Set(['category', 'group', 'component', 'event', 'row', 'column', 'row_label', 'column_label', 'facet', 'panel', 'parameter', 'label', 'peak_label', 'actual', 'predicted', 'item', 'series', 'feature'])
  return [
    ...chart.requiredFields.map((role) => ({ role, label: mappingRoleLabels[role] ?? role, numeric: role !== 'time' && !categorical.has(role), datetime: role === 'time', required: true })),
    ...chart.optionalFields.map((role) => ({ role, label: mappingRoleLabels[role] ?? role, numeric: role !== 'time' && !categorical.has(role), datetime: role === 'time', required: false })),
  ]
}

function previewValue(value: string | number | boolean | null | undefined): string {
  if (value === null) return '空值'
  if (value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

function Startup({
  core,
  busyAction,
  notice,
  onOpenSample,
  onImportData,
  onOpenProject,
}: Pick<ConversationWorkspaceProps, 'core' | 'busyAction' | 'notice' | 'onOpenSample' | 'onImportData' | 'onOpenProject'>): React.JSX.Element {
  const offline = core.phase !== 'ready'
  return (
    <div className="conversation-scroll conversation-scroll--empty">
      <section className="startup-empty" aria-label="开始使用 PlotAgent">
        {offline && (
          <div className="startup-core-alert" role="status">
            {core.phase === 'starting' || core.phase === 'restarting'
              ? <LoaderCircle className="spin" size={17} />
              : <TriangleAlert size={17} />}
            <div><strong>{core.phase === 'failed' ? '本地 Core 启动失败' : '正在准备本地 Core'}</strong><span>{core.error?.message ?? '就绪后可创建项目和导入数据。'}</span></div>
          </div>
        )}

        <div className="startup-actions">
          <button className="startup-action startup-action--primary" type="button" onClick={onOpenSample} disabled={offline || busyAction !== undefined}>
            <span className="startup-action__icon">{busyAction === 'sample' ? <LoaderCircle className="spin" size={18} /> : <Play size={18} />}</span>
            <span><strong>示例</strong></span><ArrowRight size={17} />
          </button>
          <button className="startup-action startup-action--secondary" type="button" onClick={onImportData} disabled={offline || busyAction !== undefined}>
            <span className="startup-action__icon">{busyAction === 'import' ? <LoaderCircle className="spin" size={18} /> : <FileSpreadsheet size={18} />}</span>
            <span><strong>导入</strong><small>CSV、TSV、TXT、DAT、XLS、XLSX、XLSM</small></span><ArrowRight size={17} />
          </button>
        </div>
        <button className="startup-project-link" type="button" onClick={onOpenProject} disabled={offline || busyAction !== undefined}>
          <FolderOpen size={15} />打开已有 .plotproj
        </button>
        {notice && <InlineNotice notice={notice} />}
      </section>
    </div>
  )
}

function InlineNotice({ notice }: { notice: ProductNotice }): React.JSX.Element {
  const Icon = notice.kind === 'success' ? CircleCheck : notice.kind === 'error' ? TriangleAlert : CircleAlert
  return (
    <div className={`product-notice product-notice--${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}>
      <Icon size={17} />
      <div><strong>{notice.title}</strong><p>{notice.message}</p></div>
      {notice.actionLabel && notice.onAction && <button type="button" onClick={notice.onAction}>{notice.actionLabel}</button>}
    </div>
  )
}

function NoticeMessage({ notice }: { notice: ProductNotice }): React.JSX.Element {
  return <AgentMessage className="conversation-history-message"><InlineNotice notice={notice} /></AgentMessage>
}

function DatasetObject({
  datasets,
  activeDataset,
  onSelectDataset,
  selectedWorkflowSourceIds,
  onToggleWorkflowSource,
}: Pick<ConversationWorkspaceProps, 'datasets' | 'activeDataset' | 'onSelectDataset' | 'selectedWorkflowSourceIds' | 'onToggleWorkflowSource'>): React.JSX.Element {
  if (!activeDataset) return <div />
  return (
    <section className="object-block dataset-object" aria-labelledby="dataset-title">
      <header className="object-header">
        <span className="object-icon object-icon--data" aria-hidden="true"><FileSpreadsheet size={17} /></span>
        <div><h3 id="dataset-title">{activeDataset.displayName}</h3><p>版本 {activeDataset.sourceVersion}</p></div>
        <span className="status-label status-label--success"><Check size={13} />已解析</span>
        {datasets.length > 1 && (
          <label className="dataset-switcher">数据表
            <select value={activeDataset.datasetId} onChange={(event) => onSelectDataset(event.target.value)}>
              {datasets.map((dataset) => <option key={`${dataset.datasetId}:${dataset.sourceVersion}`} value={dataset.datasetId}>{dataset.displayName}</option>)}
            </select>
          </label>
        )}
      </header>
      <div className="dataset-stats" aria-label="数据质量摘要">
        <span><strong>{activeDataset.rowCount.toLocaleString('zh-CN')}</strong> 行</span>
        <span><strong>{activeDataset.fieldCount}</strong> 字段</span>
        {activeDataset.missingCount > 0 && <span><strong>{activeDataset.missingCount}</strong> 缺失</span>}
        {activeDataset.nonFiniteCount > 0 && <span><strong>{activeDataset.nonFiniteCount}</strong> 非有限值</span>}
        {activeDataset.coordinateKinds.length > 1 && <span><strong>{activeDataset.coordinateKinds.length}</strong> 种来源坐标</span>}
      </div>
      {Object.keys(activeDataset.instrumentMetadata).length > 0 && <dl className="dataset-instrument-metadata" aria-label="仪器信息">
        <dt>仪器信息</dt>
        {Object.entries(activeDataset.instrumentMetadata).slice(0, 6).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}
      </dl>}
      <section className="dataset-preview" aria-labelledby="dataset-preview-title">
        <header className="dataset-preview__heading">
          <div><strong id="dataset-preview-title">提供给 Agent 的数据表</strong></div>
          <span>{activeDataset.sampleRows === undefined
            ? activeDataset.samplePreviewUnavailable ? '样本暂不可用' : '正在读取样本'
            : `前 ${Math.min(activeDataset.sampleRows.length, 5)} 行 · ${activeDataset.fieldCount} 列`}</span>
        </header>
        <div className="dataset-preview__scroll" tabIndex={0} aria-label="整理后的数据表，可横向滚动">
          <table className="dataset-preview__table" style={{ minWidth: `${Math.max(680, activeDataset.fields.length * 136)}px` }}>
            <thead><tr>{activeDataset.fields.map((field) => <th key={field.fieldId} scope="col">
              <strong title={field.name}>{displayFieldName(field.name)}</strong>
              <FieldMeta field={field} />
            </th>)}</tr></thead>
            <tbody>{activeDataset.sampleRows === undefined
              ? <tr><td className="dataset-preview__empty" colSpan={activeDataset.fields.length}>{activeDataset.samplePreviewUnavailable ? '样本预览暂不可用，字段结构仍已保留。' : '正在读取整理后的数据样本…'}</td></tr>
              : activeDataset.sampleRows.length === 0
                ? <tr><td className="dataset-preview__empty" colSpan={activeDataset.fields.length}>整理后的数据表没有可预览行。</td></tr>
                : activeDataset.sampleRows.slice(0, 5).map((row, rowIndex) => <tr key={`dataset-preview-${rowIndex}`}>{activeDataset.fields.map((field, columnIndex) => {
                  const value = previewValue(row[columnIndex])
                  return <td key={field.fieldId} title={value}>{value}</td>
                })}</tr>)}</tbody>
          </table>
        </div>
      </section>
      {datasets.length > 1 && <details className="agent-dataset-context">
        <summary>本次任务数据 <span>{selectedWorkflowSourceIds.length}/{MAX_WORKFLOW_SOURCES}</span></summary>
        <div>
          {datasets.map((dataset) => {
            const active = dataset.datasetId === activeDataset.datasetId
            const selected = selectedWorkflowSourceIds.includes(dataset.datasetId)
            return <label key={dataset.datasetId}>
              <input
                type="checkbox"
                checked={selected}
                disabled={active || (!selected && selectedWorkflowSourceIds.length >= MAX_WORKFLOW_SOURCES)}
                onChange={() => onToggleWorkflowSource(dataset.datasetId)}
              />
              <span><strong>{dataset.displayName}</strong><small>{active ? '当前数据表，始终提供' : `${dataset.rowCount} 行 · ${dataset.fieldCount} 字段`}</small></span>
            </label>
          })}
        </div>
      </details>}
    </section>
  )
}

function MappingObject({
  chart,
  dataset,
  busy,
  onConfirm,
  onConfirmMultiSource,
  onCancel,
  selectedDataCount,
}: {
  chart: ChartType
  dataset: ProductDataset
  busy: boolean
  onConfirm: (mapping: FieldMappingInput) => void
  onConfirmMultiSource: (mapping: FieldMappingInput) => void
  onCancel: () => void
  selectedDataCount: number
}): React.JSX.Element {
  const multiSourceProfiles = new Set(['K03', 'K12', 'K13', 'K14', 'K18', 'K19', 'X05'])
  const canUseMultipleSources = selectedDataCount >= 2 && multiSourceProfiles.has(chart.id)
  const variadicSeries = chart.repeatableRolePrefixes.includes('series')
  const minimumSeriesRoleCount = Math.max(
    1,
    chart.requiredFields.filter((role) => role.startsWith('series_')).length,
  )
  const [seriesRoleCount, setSeriesRoleCount] = useState(minimumSeriesRoleCount)
  const roles = useMemo(() => {
    const configured = mappingRoles(chart)
    if (!variadicSeries) return configured
    const fixed = configured.filter((role) => !role.role.startsWith('series_'))
    return [
      ...fixed,
      ...Array.from({ length: seriesRoleCount }, (_, index) => ({
        role: `series_${index + 1}`,
        label: `系列 ${index + 1}`,
        numeric: true,
        datetime: false,
        required: true,
      })),
    ]
  }, [chart, seriesRoleCount, variadicSeries])
  const suggestions = useMemo(() => suggestedFieldMapping(roles, dataset), [dataset, roles])
  const [values, setValues] = useState<Record<string, string>>(() => suggestions)
  const [picker, setPicker] = useState<{ fieldId: string; left: number; top: number }>()
  const pickerRef = useRef<HTMLDivElement>(null)
  const triggerRefs = useRef(new Map<string, HTMLButtonElement>())
  const missingRoles = roles.filter((role) => role.required && !values[role.role])
  const complete = missingRoles.length === 0
  const assignedRole = (fieldId: string): MappingRole | undefined => roles.find((role) => values[role.role] === fieldId)
  const closePicker = useCallback((restoreFocus = false): void => {
    const trigger = picker ? triggerRefs.current.get(picker.fieldId) : undefined
    if (restoreFocus) trigger?.focus()
    setPicker(undefined)
  }, [picker])
  const openPicker = (fieldId: string): void => {
    const trigger = triggerRefs.current.get(fieldId)
    if (!trigger) return
    if (picker?.fieldId === fieldId) { closePicker(true); return }
    const rect = trigger.getBoundingClientRect()
    const menuWidth = 224
    const menuHeight = 44 + Math.ceil((roles.length + 1) / 2) * 38
    const left = Math.min(rect.left, window.innerWidth - menuWidth - 12)
    const top = rect.bottom + 6 + menuHeight <= window.innerHeight
      ? rect.bottom + 6
      : Math.max(12, rect.top - menuHeight - 6)
    setPicker({ fieldId, left: Math.max(12, left), top })
  }
  const setFieldRole = (fieldId: string, roleName: string): void => {
    setValues((current) => {
      const next = Object.fromEntries(Object.entries(current).filter(([, assignedField]) => assignedField !== fieldId))
      if (roleName) next[roleName] = fieldId
      return next
    })
    closePicker(false)
    window.requestAnimationFrame(() => triggerRefs.current.get(fieldId)?.focus())
  }
  const movePickerFocus = (event: React.KeyboardEvent<HTMLDivElement>): void => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
    const items = [...(pickerRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]:not(:disabled)') ?? [])]
    if (items.length === 0) return
    event.preventDefault()
    const currentIndex = items.indexOf(document.activeElement as HTMLButtonElement)
    const nextIndex = event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? items.length - 1
        : event.key === 'ArrowDown'
          ? (currentIndex + 1 + items.length) % items.length
          : (currentIndex - 1 + items.length) % items.length
    items[nextIndex]?.focus()
  }

  useEffect(() => {
    if (!picker) return
    const onPointerDown = (event: PointerEvent): void => {
      const target = event.target as Node
      if (pickerRef.current?.contains(target) || triggerRefs.current.get(picker.fieldId)?.contains(target)) return
      closePicker(false)
    }
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      closePicker(true)
    }
    const onViewportChange = (): void => closePicker(false)
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    window.addEventListener('resize', onViewportChange)
    window.addEventListener('scroll', onViewportChange, true)
    const frame = window.requestAnimationFrame(() => {
      const selected = pickerRef.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]')
      const first = pickerRef.current?.querySelector<HTMLButtonElement>('[role="menuitemradio"]')
      ;(selected ?? first)?.focus()
    })
    return () => {
      window.cancelAnimationFrame(frame)
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('resize', onViewportChange)
      window.removeEventListener('scroll', onViewportChange, true)
    }
  }, [closePicker, picker])

  return (
    <div className="mapping-review" role="group" aria-labelledby="mapping-title">
      <header className="mapping-data-context">
        <span className="object-icon object-icon--mapping" aria-hidden="true"><TableProperties size={17} /></span>
        <div><h3 id="mapping-title">数据预览与字段绑定</h3><p>{dataset.displayName}</p></div>
      </header>
      <div className="mapping-review__toolbar">
        <span>
          <strong>{dataset.sampleRows === undefined
            ? dataset.samplePreviewUnavailable ? '样本预览不可用' : '正在读取样本'
            : `预览前 ${Math.min(dataset.sampleRows.length, 5)} 行`}</strong>
          ，共 {dataset.rowCount.toLocaleString('zh-CN')} 行
        </span>
        <span>点击角色可修改</span>
      </div>
      <section className="mapping-preview-object">
        <div className="mapping-preview-scroll" tabIndex={0} aria-label="字段映射和数据预览，可横向滚动">
          <table className="mapping-preview-table" style={{ minWidth: `${Math.max(680, dataset.fields.length * 148)}px` }}>
            <thead><tr>{dataset.fields.map((field) => {
              const role = assignedRole(field.fieldId)
              return <th key={field.fieldId} scope="col">
                <div className="mapping-column-head">
                  <button
                    className="mapping-role-trigger"
                    type="button"
                    ref={(node) => { if (node) triggerRefs.current.set(field.fieldId, node); else triggerRefs.current.delete(field.fieldId) }}
                    aria-label={`${displayFieldName(field.name)} 的绘图角色：${role?.label ?? '未使用'}`}
                    aria-haspopup="menu"
                    aria-expanded={picker?.fieldId === field.fieldId}
                    data-empty={role === undefined}
                    disabled={busy}
                    onClick={() => openPicker(field.fieldId)}
                  >
                    <span>{role?.label ?? '未使用'}</span><ChevronDown size={12} aria-hidden="true" />
                  </button>
                  <strong title={field.name}>{displayFieldName(field.name)}</strong>
                  <FieldMeta field={field} />
                </div>
              </th>
            })}</tr></thead>
            <tbody>{dataset.sampleRows === undefined
              ? <tr><td className="mapping-preview-empty" colSpan={dataset.fields.length}>{dataset.samplePreviewUnavailable ? '样本预览暂不可用，仍可按字段名称与类型完成映射。' : '正在读取样本…'}</td></tr>
              : dataset.sampleRows.length === 0
                ? <tr><td className="mapping-preview-empty" colSpan={dataset.fields.length}>没有可预览的数据行。</td></tr>
                : dataset.sampleRows.map((row, rowIndex) => <tr key={`preview-row-${rowIndex}`}>{dataset.fields.map((field, columnIndex) => {
                  const value = previewValue(row[columnIndex])
                  return <td key={field.fieldId} title={value}>{value}</td>
                })}</tr>)}</tbody>
          </table>
        </div>
      </section>
      {variadicSeries && (
        <div className="mapping-series-actions">
          <button type="button" onClick={() => setSeriesRoleCount((count) => count + 1)}>添加系列</button>
          <button type="button" disabled={seriesRoleCount <= minimumSeriesRoleCount} onClick={() => {
            const role = `series_${seriesRoleCount}`
            setValues((current) => {
              const next = { ...current }
              delete next[role]
              return next
            })
            setSeriesRoleCount((count) => Math.max(minimumSeriesRoleCount, count - 1))
          }}>移除末项</button>
        </div>
      )}
      <section className="mapping-decision" data-state={complete ? 'valid' : 'invalid'} aria-labelledby="mapping-decision-title">
        <div className="mapping-decision__copy">
          <span>是否确认创建</span>
          <strong id="mapping-decision-title">{chart.id} {chart.name}</strong>
          <div className="mapping-validation" data-state={complete ? 'valid' : 'invalid'} role="status">
            <span aria-hidden="true" />
            {complete
              ? `必填字段已完成：${roles.filter((role) => role.required).map((role) => role.label).join('、')}`
              : `还需绑定：${missingRoles.map((role) => role.label).join('、')}`}
          </div>
        </div>
        <div className="mapping-decision__actions">
          <button type="button" disabled={busy} onClick={() => { closePicker(false); onCancel() }}>取消</button>
          <button type="button" disabled={busy} onClick={() => { closePicker(false); setValues(suggestions) }}>恢复 Agent 建议</button>
          {canUseMultipleSources && <button type="button" disabled={!complete || busy} onClick={() => onConfirmMultiSource({ roles: Object.fromEntries(Object.entries(values).filter(([role, field]) => role !== 'group' && field)) })}>
            {busy ? <LoaderCircle className="spin" size={15} /> : <Layers3 size={15} />}{busy ? '正在合并绘图' : `${selectedDataCount} 个数据表同图绘制`}
          </button>}
          <button className="primary-button" type="button" disabled={!complete || busy} onClick={() => onConfirm({ roles: Object.fromEntries(Object.entries(values).filter(([, field]) => field)) })}>
            {busy ? <LoaderCircle className="spin" size={15} /> : <CheckCircle2 size={15} />}{busy ? '正在绘图' : '确认并绘图'}
          </button>
        </div>
      </section>
      {picker && createPortal(
        <div className="mapping-role-menu" ref={pickerRef} role="menu" aria-label={`${displayFieldName(dataset.fields.find((field) => field.fieldId === picker.fieldId)?.name ?? picker.fieldId)} 的绘图角色`} style={{ left: picker.left, top: picker.top }} onKeyDown={movePickerFocus}>
          <span>选择字段角色</span>
          <div>
            {[{ role: '', label: '未使用', numeric: false, required: false }, ...roles].map((role) => {
              const selected = (assignedRole(picker.fieldId)?.role ?? '') === role.role
              const field = dataset.fields.find((candidate) => candidate.fieldId === picker.fieldId)
              const incompatible = Boolean(role.role && field && !fieldMatchesRole(role, field))
              return <button key={role.role || 'unused'} type="button" role="menuitemradio" aria-checked={selected} disabled={incompatible} title={incompatible ? '该字段类型不适用于此角色' : undefined} onClick={() => setFieldRole(picker.fieldId, role.role)}>
                <span aria-hidden="true">{selected ? '✓' : ''}</span>{role.label}{role.required ? '' : role.role ? '（可选）' : ''}
              </button>
            })}
          </div>
        </div>,
        document.body,
      )}
    </div>
  )
}

function PlotObject({
  plot,
  plotNumber,
  interactive,
  className,
  busyAction,
  previewMode,
  onExport,
  onOpenLibrary,
  onOpenFocus,
  onCreateBatch,
}: Pick<ConversationWorkspaceProps, 'plot' | 'busyAction' | 'previewMode' | 'onExport' | 'onOpenLibrary' | 'onOpenFocus' | 'onCreateBatch'> & {
  plotNumber: number
  interactive: boolean
  className?: string
}): React.JSX.Element {
  if (!plot) return <div />
  const plotChart = chartCatalog.find((item) => item.id === plot.chartId)
  return (
    <section className={`object-block product-plot-object${className ? ` ${className}` : ''}`} aria-label={`@图${plotNumber} ${plotChart?.name ?? plot.chartId} v${plot.plotVersion}`}>
      <header className="object-header">
        <span className="object-icon object-icon--batch"><FileChartColumn size={17} /></span>
        <div><h3>@图{plotNumber} · {plotChart?.name ?? plot.chartId} · v{plot.plotVersion}</h3></div>
        <span className={interactive ? 'status-label status-label--success' : 'status-label'}><Check size={13} />{interactive ? (previewMode ? '界面预览' : '已渲染') : '历史版本'}</span>
      </header>
      <div className="product-preview">
        {plot.preview?.url ? <img key={`${plot.plotId}:${plot.plotVersion}:${plot.preview.resourceId}`} src={plot.preview.url} alt={`${plotChart?.name ?? plot.chartId} ${previewMode ? '界面预览' : '真实渲染预览'}`} /> : <div className="preview-pending"><LoaderCircle className="spin" size={20} /><span>等待受控预览资源</span></div>}
      </div>
      {interactive && <footer className="plot-actions">
        <button type="button" onClick={onOpenLibrary}><Library size={15} />选择其他图形</button>
        <button type="button" onClick={onOpenFocus}><Settings2 size={15} />编辑图形</button>
        <button type="button" onClick={onCreateBatch}><Images size={15} />创建批次</button>
        <span />
        {(['png', 'svg', 'opju'] as const).map((format) => (
          <button key={format} type="button" onClick={() => onExport(format)} disabled={busyAction === `export-${format}`}>
            {busyAction === `export-${format}` ? <LoaderCircle className="spin" size={15} /> : <Download size={15} />}导出 {format.toLocaleUpperCase('en-US')}
          </button>
        ))}
      </footer>}
    </section>
  )
}

function ConversationComposer({
  plotReferences,
  selectedChart,
  multiChartTask,
  datasetCount,
  configured,
  busy,
  importing,
  notice,
  mappingOpen,
  canInspectMapping,
  onSubmit,
  onConfigure,
  onOpenLibrary,
  onImportData,
  onToggleMapping,
}: {
  plotReferences: { reference: PlotReference; plot: ProductPlot }[]
  selectedChart?: ChartType
  multiChartTask?: boolean
  datasetCount: number
  configured: boolean
  busy: boolean
  importing: boolean
  notice?: ProductNotice
  mappingOpen: boolean
  canInspectMapping: boolean
  onSubmit: (instruction: string, selectedPlots: WorkflowPlotSelection[]) => void
  onConfigure: () => void
  onOpenLibrary: () => void
  onImportData: () => void
  onToggleMapping: () => void
}): React.JSX.Element {
  const [value, setValue] = useState('')
  const [mentionOpen, setMentionOpen] = useState(false)
  const [mentionError, setMentionError] = useState<string>()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const mentionedNumbers = parsePlotMentions(value)
  const mentionedTargets = mentionedNumbers.flatMap((number) => {
    const match = plotReferences.find((item) => item.reference.number === number)
    return match === undefined ? [] : [`@图${number} · v${match.plot.plotVersion}`]
  })
  const submit = (): void => {
    const instruction = value.trim()
    if (!instruction || busy) return
    const numbers = parsePlotMentions(instruction)
    const byNumber = new Map(plotReferences.map((item) => [item.reference.number, item.plot]))
    const missing = numbers.filter((number) => !byNumber.has(number))
    if (missing.length > 0) {
      setMentionError(`项目中不存在 ${missing.map((number) => `@图${number}`).join('、')}。`)
      return
    }
    onSubmit(instruction, numbers.flatMap((number) => {
      const selected = byNumber.get(number)
      return selected === undefined ? [] : [{
        plotId: selected.plotId,
        plotVersion: selected.plotVersion,
      }]
    }))
    setValue('')
    setMentionOpen(false)
    setMentionError(undefined)
  }
  const insertMention = (reference: PlotReference): void => {
    const textarea = textareaRef.current
    const caret = textarea?.selectionStart ?? value.length
    const trigger = value.lastIndexOf('@', Math.max(0, caret - 1))
    const before = trigger >= 0 ? value.slice(0, trigger) : `${value}${value && !value.endsWith(' ') ? ' ' : ''}`
    const after = trigger >= 0 ? value.slice(caret) : ''
    const next = `${before}@图${reference.number} ${after}`
    setValue(next)
    setMentionOpen(false)
    setMentionError(undefined)
    window.requestAnimationFrame(() => {
      const nextCaret = before.length + `@图${reference.number} `.length
      textarea?.focus()
      textarea?.setSelectionRange(nextCaret, nextCaret)
    })
  }
  return (
    <div className="composer-wrap">
      {notice?.kind === 'success' && <div className="composer-success" role="status"><Check size={14} />{notice.title}</div>}
      <div className="composer" aria-label="自然语言绘图指令">
        <div className="composer-context">
          <span className="target-chip"><Layers3 size={14} />{
            mentionedTargets.length > 0
              ? mentionedTargets.join('、')
              : multiChartTask
                ? '多图任务'
              : selectedChart
                ? `${selectedChart.id} · ${selectedChart.name}`
                : '未选择图形'
          }</span>
          {mentionedTargets.length === 0 && canInspectMapping && <button className="composer-context__action" type="button" onClick={onToggleMapping} disabled={busy || importing}>{mappingOpen ? '收起字段绑定' : '字段绑定'}</button>}
        </div>
        <textarea ref={textareaRef} value={value} disabled={busy} onChange={(event) => {
          const next = event.target.value
          setValue(next)
          setMentionError(undefined)
          const caret = event.target.selectionStart ?? next.length
          setMentionOpen(plotReferences.length > 0 && /(?:^|\s)@[^\s]*$/u.test(next.slice(0, caret)))
        }} onKeyDown={(event) => {
          if (event.key === 'Escape' && mentionOpen) { event.preventDefault(); setMentionOpen(false); return }
          if (event.key === 'Enter' && !event.shiftKey && !mentionOpen) { event.preventDefault(); submit() }
        }} placeholder={plotReferences.length > 0 ? '通过 @ 指定需编辑的对象' : '描述绘图要求'} aria-label="描述绘图要求" aria-describedby={mentionError ? 'composer-mention-error' : undefined} />
        {mentionOpen && <div className="plot-mention-menu" role="listbox" aria-label="选择作用图形">
          {plotReferences.map(({ reference, plot: candidate }) => {
            const chart = chartCatalog.find((item) => item.id === candidate.chartId)
            return <button key={reference.plotId} type="button" role="option" aria-selected="false" onMouseDown={(event) => event.preventDefault()} onClick={() => insertMention(reference)}>
              <strong>@图{reference.number}</strong><span>{chart?.name ?? candidate.chartId} · v{candidate.plotVersion}</span>
            </button>
          })}
        </div>}
        {mentionError && <p id="composer-mention-error" className="composer-mention-error" role="alert">{mentionError}</p>}
        <div className="composer-toolbar">
          <button type="button" className={selectedChart || multiChartTask ? 'composer-tool is-selected' : 'composer-tool'} onClick={onOpenLibrary}><Library size={15} />{multiChartTask ? '多图任务' : selectedChart ? selectedChart.name : '选择图形'}</button>
          <button type="button" className="composer-tool" onClick={onImportData} disabled={importing}>
            {importing ? <LoaderCircle className="spin" size={15} /> : <FileUp size={15} />}
            {importing ? '正在导入' : `上传数据${datasetCount > 0 ? ` (${datasetCount})` : ''}`}
          </button>
          {!configured && <button type="button" className="composer-tool" onClick={onConfigure}>配置模型</button>}
          <button className="send-button" type="button" onClick={submit} disabled={!value.trim() || busy} aria-label="生成任务计划">{busy ? <LoaderCircle className="spin" size={17} /> : <SendHorizontal size={17} />}</button>
        </div>
      </div>
    </div>
  )
}

function WorkflowPlanObject({
  plan,
  datasets,
  selectedChart,
  plot,
  busy,
  onConfirm,
  onReject,
  onEdit,
  canUndo,
  onUndo,
  onRun,
  onResume,
  onAcceptPartial,
}: {
  plan: WorkflowPlanView
  datasets: ProductDataset[]
  selectedChart?: ChartType
  plot?: ProductPlot
  busy: boolean
  onConfirm: (planId: string) => void
  onReject: (planId: string) => void
  onEdit: (planId: string) => void
  canUndo: boolean
  onUndo: () => void
  onRun: (planId: string) => void
  onResume: (planId: string) => void
  onAcceptPartial: (taskId: string) => void
}): React.JSX.Element {
  const stateLabels: Record<string, string> = {
    awaiting_confirmation: '等待确认',
    awaiting_reconfirmation: '等待重新确认',
    ready: '待执行',
    running: '执行中',
    partially_succeeded: '部分完成',
    completed_with_skips: '已完成（含跳过项）',
    succeeded: '已完成',
    failed: '失败',
    cancelled: '已取消',
    rejected: '已拒绝',
  }
  const fieldLabel = (binding: WorkflowBindingView): string => {
    const candidates = binding.sourceDatasetId === undefined
      ? datasets
      : datasets.filter((dataset) => dataset.datasetId === binding.sourceDatasetId)
    for (const dataset of candidates) {
      const field = dataset.fields.find((candidate) => candidate.fieldId === binding.fieldId)
      if (field) return datasets.length > 1
        ? `${dataset.displayName} · ${displayFieldName(field.name)}`
        : displayFieldName(field.name)
    }
    if (binding.fieldName !== undefined) return displayFieldName(binding.fieldName)
    return binding.fieldId
  }
  const objectLabel = plan.steps.length > 1
    ? `${plan.steps.length} 个任务`
    : plan.steps[0]?.taskKind === 'create'
      ? `${plan.steps[0].profileId || selectedChart?.id || '待定'} · 新图`
      : plot
        ? `${plot.plotId} · v${plot.plotVersion}`
        : `${selectedChart?.id ?? '待定'} · 新图`
  const sourceCount = new Set(plan.steps.flatMap((step) => step.sourceDatasetIds)).size
  const bindingCount = plan.steps.reduce((total, step) => total + step.bindings.length, 0)
  const bindingSummary = bindingCount > 0 ? `${bindingCount} 个字段角色` : '字段绑定待补充'
  const objectChartNames = [...new Set(plan.steps.flatMap((step) => {
    const chart = chartCatalog.find((candidate) => candidate.id === step.profileId)
    return chart ? [`${chart.id} ${chart.name}`] : []
  }))]
  const visibleObjectLabel = plan.steps.length === 1 && plan.steps[0]?.taskKind === 'create'
    ? `${objectChartNames[0] ?? plan.steps[0].profileId ?? '待定图形'} · 新图`
    : objectLabel
  const previewSources = plan.steps.reduce<Array<{
    dataset: ProductDataset
    roles: Map<string, string>
  }>>((sources, step) => {
    for (const sourceDatasetId of step.sourceDatasetIds) {
      const existing = sources.find((source) => source.dataset.datasetId === sourceDatasetId)
      const dataset = datasets.find((candidate) => candidate.datasetId === sourceDatasetId)
      if (!dataset) continue
      const roles = existing?.roles ?? new Map<string, string>()
      for (const evidence of step.sourceFieldRoles ?? []) {
        if (evidence.sourceDatasetId === sourceDatasetId) {
          roles.set(evidence.fieldId, evidence.role)
        }
      }
      if (!existing) sources.push({ dataset, roles })
    }
    return sources
  }, [])
  return (
    <section className={`agent-plan agent-plan--${plan.state}`} aria-labelledby={`plan-${plan.planId}`}>
      <header className="agent-plan__header">
        <ListChecks size={17} aria-hidden="true" />
        <div><h3 id={`plan-${plan.planId}`}>任务计划</h3></div>
        <span className="agent-plan__state">{plan.state === 'running' && <LoaderCircle className="spin" size={13} />}{stateLabels[plan.state] ?? plan.state}</span>
      </header>
      <div className="agent-context-cards" role="list" aria-label="任务上下文">
        <article className="agent-context-card" role="listitem">
          <FileChartColumn size={16} aria-hidden="true" />
          <strong>{visibleObjectLabel}</strong>
        </article>
        <article className="agent-context-card" role="listitem">
          <TableProperties size={16} aria-hidden="true" />
          <strong>{sourceCount} 个来源 · {bindingSummary}</strong>
        </article>
        <article className="agent-context-card" role="listitem">
          <Images size={16} aria-hidden="true" />
          <strong>{plan.steps.length} 张可预览、可导出的图</strong>
        </article>
      </div>
      {previewSources.map(({ dataset: previewDataset, roles: previewRoles }) => <section key={previewDataset.datasetId} className="agent-plan__data-preview" aria-label="计划字段绑定与数据样本">
        <header><strong>{previewDataset.displayName}</strong><span>原始数据 · 前 3 行</span></header>
        <div className="mapping-preview-scroll" tabIndex={0} aria-label="计划字段绑定和数据预览，可横向滚动">
          <table className="mapping-preview-table mapping-preview-table--readonly" style={{ minWidth: `${Math.max(620, previewDataset.fields.length * 138)}px` }}>
            <thead><tr>{previewDataset.fields.map((field) => <th key={field.fieldId} scope="col">
              <div className="mapping-column-head">
                <span className="mapping-role-badge" data-empty={!previewRoles.has(field.fieldId)}>
                  {previewRoles.has(field.fieldId) ? displayWorkflowRole(previewRoles.get(field.fieldId)!) : <span aria-label="未使用">—</span>}
                </span>
                <strong title={field.name}>{displayFieldName(field.name)}</strong>
                <FieldMeta field={field} />
              </div>
            </th>)}</tr></thead>
            <tbody>{previewDataset.sampleRows?.slice(0, 3).map((row, rowIndex) => <tr key={`plan-preview-${rowIndex}`}>{previewDataset.fields.map((field, columnIndex) => {
              const value = previewValue(row[columnIndex])
              return <td key={field.fieldId} title={value}>{value}</td>
            })}</tr>) ?? <tr><td className="mapping-preview-empty" colSpan={previewDataset.fields.length}>样本预览暂不可用，字段绑定仍来自同一份 Core 计划。</td></tr>}</tbody>
          </table>
        </div>
      </section>)}
      <ol className="agent-plan__steps">
        {plan.steps.map((step) => (
          <li className={`agent-plan-step agent-plan-step--${step.state}`} key={step.taskItemId}>
            <span className="agent-plan-step__mark" aria-hidden="true">
              {step.state === 'succeeded'
                ? <Check size={13} />
                : step.state === 'running' || step.state === 'committing'
                  ? <LoaderCircle className="spin" size={13} />
                  : step.state === 'failed' || step.state === 'stale'
                    ? <TriangleAlert size={13} />
                    : null}
            </span>
            <div>
              <div className="agent-plan-step__title"><strong>{step.title}</strong>{chartCatalog.find((candidate) => candidate.id === step.profileId)?.name && <span>{chartCatalog.find((candidate) => candidate.id === step.profileId)?.name}</span>}</div>
              {step.detail && <p className="agent-plan-step__detail">{step.detail}</p>}
              {step.bindings.length > 0 && <dl className="agent-plan-step__bindings" aria-label={`${step.title} 字段绑定`}>
                <div className="agent-plan-step__section-label"><dt>字段绑定</dt><dd /></div>
                {step.bindings.map((binding) => <div key={`${binding.role}:${binding.fieldId}`}><dt>{displayWorkflowRole(binding.role)}</dt><dd>{fieldLabel(binding)}</dd></div>)}
              </dl>}
              {step.dataOperations.length > 0 && <div className="agent-plan-step__operations" aria-label={`${step.title} 数据处理`}>
                <strong>数据处理</strong>
                <ul className="tool-chip-list">{step.dataOperations.map((operation, index) => <li key={`${index}:${operation}`}><TableProperties size={12} aria-hidden="true" />{displayDataOperation(operation)}</li>)}</ul>
              </div>}
              {step.changes.length > 0 && <ul className="agent-plan-step__changes" aria-label={`${step.title} 视觉修改`}>
                {step.changes.map((change) => <li key={change}><Settings2 size={12} aria-hidden="true" />{change}</li>)}
              </ul>}
              {step.outputPlot && <p className="agent-plan-step__output">{step.outputPlot.plotId} · v{step.outputPlot.plotVersion}</p>}
              {step.failure && <div className="agent-plan-step__failure" role="alert">
                <p>{step.failure.message}</p>
                <small>阶段：绘图引擎执行与验证 · {step.failure.sideEffectState === 'known_applied' ? '已保留已提交更改' : step.failure.sideEffectState === 'known_none' ? '项目未发生更改' : '项目变化待核验'}</small>
                <small>下一步：{plan.state === 'failed'
                  ? '修改要求后创建新任务'
                  : step.failure.retryable
                    ? '仅重试此失败项'
                    : step.failure.requiresUser ? '修改要求或字段绑定' : '修改后重试，或跳过此项'}</small>
                {step.failure.diagnosticId && <small>诊断 ID：{step.failure.diagnosticId}</small>}
              </div>}
            </div>
            {step.attemptCount > 0 && <span className="agent-plan-step__attempt">{step.attemptCount} 次</span>}
          </li>
        ))}
      </ol>
      {plan.warnings.length > 0 && <div className="agent-plan__warnings">{plan.warnings.map((warning) => <p key={warning}><TriangleAlert size={14} />{warning}</p>)}</div>}
      <footer className="agent-plan__actions">
        {plan.state === 'awaiting_confirmation' && <><button type="button" onClick={() => onReject(plan.planId)} disabled={busy}>取消</button><button type="button" onClick={() => onEdit(plan.planId)} disabled={busy}>修改绑定</button><button className="primary-button" type="button" onClick={() => onConfirm(plan.planId)} disabled={busy}>确认并执行</button></>}
        {plan.state === 'awaiting_reconfirmation' && <><button type="button" onClick={() => onReject(plan.planId)} disabled={busy}>拒绝修订计划</button><button className="primary-button" type="button" onClick={() => onConfirm(plan.planId)} disabled={busy}>确认修订计划</button></>}
        {plan.state === 'ready' && <button className="primary-button" type="button" onClick={() => onRun(plan.planId)} disabled={busy}>执行计划</button>}
        {plan.resumable && <button className="primary-button" type="button" onClick={() => onResume(plan.planId)} disabled={busy}>继续未完成步骤</button>}
        {plan.state === 'partially_succeeded' && plan.completedCount > 0 && plan.taskId && <button type="button" onClick={() => onAcceptPartial(plan.taskId as string)} disabled={busy}>保留成功项并结束</button>}
        {(plan.state === 'succeeded' || plan.state === 'completed_with_skips') && <><span className="agent-plan__saved"><CircleCheck size={14} />{plan.state === 'completed_with_skips' ? '成功项已保存，其余已跳过' : '更改已保存'}</span>{canUndo && <button type="button" onClick={onUndo} disabled={busy}><Undo2 size={14} />撤销本轮</button>}</>}
      </footer>
    </section>
  )
}

const terminalTaskStates = new Set(['succeeded', 'completed_with_skips', 'failed', 'cancelled', 'partially_succeeded', 'interrupted'])

function ActivityMessage({
  busyAction,
  agentRuntimeLabel,
  agentRuntimeTaskId,
  tasks,
  onCancel,
}: {
  busyAction?: string
  agentRuntimeLabel?: string
  agentRuntimeTaskId?: string
  tasks: TaskEvent[]
  onCancel: (taskId: string) => void
}): React.JSX.Element | null {
  if (busyAction === undefined) return null
  const task = [...tasks]
    .filter((event) => !terminalTaskStates.has(event.state))
    .sort((left, right) => right.sequence - left.sequence)[0]
  let label = '正在处理…'
  if (busyAction === 'agent') label = agentRuntimeLabel ?? '正在理解你的要求…'
  else if (busyAction === 'import') label = '正在读取并校验数据…'
  else if (busyAction === 'plot') label = task?.state === 'committing' ? '正在保存图形版本…' : '正在调用 Matplotlib 渲染器…'
  else if (busyAction === 'agent-plan') label = agentRuntimeLabel
    ?? (task?.state === 'committing' ? '正在保存图形版本…' : '正在执行已确认的绘图动作…')
  else if (busyAction === 'plot-patch') label = task?.state === 'committing' ? '正在保存新版本…' : '正在验证图形修改…'
  else if (busyAction === 'undo') label = '正在创建撤销版本…'
  else if (busyAction === 'redo') label = '正在创建重做版本…'
  else if (busyAction === 'export-opju') label = task?.state === 'committing'
    ? 'OPJU 已生成，正在完成保存…'
    : '正在生成并验证 OPJU…'
  else if (busyAction.startsWith('export-')) label = '正在生成导出文件…'
  const progressLabel = task?.progress?.total
    ? `${task.progress.completed}/${task.progress.total} ${task.progress.unit}`
    : undefined
  return <AgentMessage className="conversation-activity" live>
    <div className="activity-message"><span className="activity-pulse" aria-hidden="true"><i /><i /><i /></span><div className="activity-message__copy"><strong><span className="activity-message__stage" key={label}>{label}</span>{progressLabel ? ` · ${progressLabel}` : ''}</strong></div>
      {(task?.state !== 'committing' && (task?.taskId ?? agentRuntimeTaskId)) && <button type="button" onClick={() => onCancel((task?.taskId ?? agentRuntimeTaskId) as string)}><StopCircle size={14} />停止</button>}
    </div>
  </AgentMessage>
}

function ConversationTextMessage({ message, animate = false }: { message: ConversationTextItem; animate?: boolean }): React.JSX.Element {
  const paragraphs = [message.text, ...(message.questions ?? [])]
    .filter((text, index, values) => text.trim().length > 0 && values.indexOf(text) === index)
  return message.role === 'user'
    ? <div className="message message--user"><div className="message-content">{message.text}</div><time className="message-time">{new Date(message.createdAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</time></div>
    : <AgentMessage className={`conversation-history-message conversation-history-message--${message.kind ?? 'info'}${animate ? ' motion-timeline-enter' : ''}`}>
        {paragraphs.map((paragraph, index) => <p className={index === 0 ? undefined : 'agent-question'} key={paragraph}>{paragraph}</p>)}
      </AgentMessage>
}

function ExportResult({
  record,
  className,
  onOpen,
  onReveal,
}: {
  record: ConversationExportRecord
  className?: string
  onOpen: (resourceId: string) => void
  onReveal: (resourceId: string) => void
}): React.JSX.Element {
  return <section className={`object-block product-result-strip product-result-strip--success${className ? ` ${className}` : ''}`} role="status" aria-live="polite" aria-label="导出记录">
    <CircleCheck size={17} />
    <div><strong>{record.format.toLocaleUpperCase('en-US')} 导出完成</strong><p>{record.fileName}{record.plotVersion === undefined ? '' : ` · v${record.plotVersion}`}{record.artifactSize === undefined ? '' : ` · ${record.artifactSize.toLocaleString('zh-CN')} B`}</p>{record.artifactHash && <code title={record.artifactHash}>{record.artifactHash.slice(0, 12)}…</code>}</div>
    <div className="product-result-strip__actions"><button type="button" onClick={() => onOpen(record.resourceId)}>打开文件</button><button type="button" onClick={() => onReveal(record.resourceId)}>打开所在文件夹</button></div>
  </section>
}

function ProductToast({
  notice,
  record,
  onOpen,
  onReveal,
}: {
  notice: ProductNotice
  record: ExportRecordView
  onOpen: (resourceId: string) => void
  onReveal: (resourceId: string) => void
}): React.JSX.Element {
  const [exiting, setExiting] = useState(false)
  useEffect(() => {
    const timer = window.setTimeout(() => setExiting(true), 7_800)
    return () => window.clearTimeout(timer)
  }, [record.exportId])

  return <aside className="product-toast product-toast--success" data-motion-state={exiting ? 'exiting' : 'entered'} role="status" aria-live="polite">
    <CircleCheck size={19} />
    <div><strong>{notice.title}</strong><p>{notice.message}</p><span>{record.fileName}</span></div>
    <div className="product-toast__actions"><button type="button" onClick={() => onOpen(record.resourceId)}>打开文件</button><button type="button" onClick={() => onReveal(record.resourceId)}><FolderOpen size={14} />打开文件夹</button></div>
  </aside>
}

export function ConversationWorkspace(props: ConversationWorkspaceProps): React.JSX.Element {
  const { project, datasets, activeDataset, selectedChart, plot, exportRecord, notice, busyAction } = props
  const [manualMappingOpen, setManualMappingOpen] = useState(false)
  const [planRevisionOpen, setPlanRevisionOpen] = useState(false)
  const [timeline, setTimeline] = useState<ConversationTimelineItem[]>(() => (
    project ? readConversationTimeline(window.localStorage, project.projectId) : []
  ))
  const [hydratedTimelineIds] = useState(() => new Set(timeline.map((item) => item.id)))
  const initialPlotIds = [...new Set([...props.projectPlots.map((item) => item.plotId), ...(plot ? [plot.plotId] : [])])]
  const [plotReferences, setPlotReferences] = useState<PlotReference[]>(() => (
    project ? registerPlotReferences(window.localStorage, project.projectId, initialPlotIds) : []
  ))
  const activeTurnIdRef = useRef(timeline.at(-1)?.turnId)
  const scrollAnchorRef = useRef<HTMLDivElement>(null)
  const availablePlots = useMemo(() => {
    const latestById = new Map(props.projectPlots.map((item) => [item.plotId, item]))
    if (plot) latestById.set(plot.plotId, plot)
    return plotReferences.flatMap((reference) => {
      const candidate = latestById.get(reference.plotId)
      return candidate ? [{ reference, plot: candidate }] : []
    })
  }, [plot, plotReferences, props.projectPlots])

  const updateTimeline = useCallback((update: (current: ConversationTimelineItem[]) => ConversationTimelineItem[]): void => {
    if (!project) return
    setTimeline((current) => {
      const updated = update(current)
      if (updated === current) return current
      writeConversationTimeline(window.localStorage, project.projectId, updated)
      return updated
    })
  }, [project])

  useEffect(() => {
    if (!project) return
    const plotIds = [...new Set([...props.projectPlots.map((item) => item.plotId), ...(plot ? [plot.plotId] : [])])]
    queueMicrotask(() => setPlotReferences(registerPlotReferences(window.localStorage, project.projectId, plotIds)))
  }, [plot, project, props.projectPlots])

  useEffect(() => {
    const outcome = props.workflowOutcome
    if (!project || !outcome || outcome.kind === 'task_plan') return
    const questions = outcome.questions?.map((question) => question.prompt) ?? []
    queueMicrotask(() => updateTimeline((current) => {
      const last = current.at(-1)
      if (last?.type === 'text' && last.role === 'agent' && last.title === outcome.title && last.text === outcome.message
        && JSON.stringify(last.questions ?? []) === JSON.stringify(questions)) return current
      return [...current, {
        type: 'text', id: `message:agent:${crypto.randomUUID()}`, turnId: activeTurnIdRef.current,
        role: 'agent', title: outcome.title, text: outcome.message, questions, createdAt: new Date().toISOString(),
        kind: outcome.kind === 'rejected' ? 'error' : outcome.kind === 'needs_input' ? 'warning' : 'info',
      }]
    }))
  }, [project, props.workflowOutcome, updateTimeline])

  useEffect(() => {
    const plan = props.workflowPlan
    if (!project || !plan) return
    queueMicrotask(() => updateTimeline((current) => {
      const index = current.findIndex((item) => item.type === 'plan' && item.plan.planId === plan.planId)
      if (index < 0) return [...current, {
        type: 'plan', id: `timeline:plan:${plan.planId}`, turnId: activeTurnIdRef.current,
        createdAt: new Date().toISOString(), plan,
      }]
      const existing = current[index]
      if (existing.type !== 'plan') return current
      const updated = [...current]
      updated[index] = { ...existing, plan }
      return updated
    }))
  }, [project, props.workflowPlan, updateTimeline])

  useEffect(() => {
    if (!project || !plot) return
    const references = registerPlotReferences(window.localStorage, project.projectId, [plot.plotId])
    const plotNumber = references.find((item) => item.plotId === plot.plotId)?.number
    if (plotNumber === undefined) return
    queueMicrotask(() => updateTimeline((current) => {
      const itemId = `timeline:plot:${plot.plotId}:v${plot.plotVersion}`
      const index = current.findIndex((item) => item.id === itemId)
      if (index < 0) return [...current, {
        type: 'plot', id: itemId, turnId: activeTurnIdRef.current,
        createdAt: new Date().toISOString(), plotNumber, plot,
      }]
      const existing = current[index]
      if (existing.type !== 'plot') return current
      const updated = [...current]
      updated[index] = { ...existing, plotNumber, plot }
      return updated
    }))
  }, [plot, project, updateTimeline])

  useEffect(() => {
    if (!project || !exportRecord) return
    queueMicrotask(() => updateTimeline((current) => {
      const itemId = `timeline:export:${exportRecord.exportId}`
      if (current.some((item) => item.id === itemId)) return current
      return [...current, {
        type: 'export', id: itemId, turnId: activeTurnIdRef.current, createdAt: new Date().toISOString(),
        record: {
          exportId: exportRecord.exportId, resourceId: exportRecord.resourceId, fileName: exportRecord.fileName,
          format: exportRecord.format, targetId: exportRecord.targetId, plotVersion: exportRecord.plotVersion,
          ...(exportRecord.artifactHash ? { artifactHash: exportRecord.artifactHash } : {}),
          ...(exportRecord.artifactSize === undefined ? {} : { artifactSize: exportRecord.artifactSize }),
        },
      }]
    }))
  }, [exportRecord, project, updateTimeline])

  useEffect(() => {
    if (timeline.length === 0 && busyAction === undefined) return
    queueMicrotask(() => scrollAnchorRef.current?.scrollIntoView?.({ behavior: 'auto', block: 'center' }))
  }, [busyAction, planRevisionOpen, timeline.length])

  const submitInstruction = (instruction: string, selectedPlots: WorkflowPlotSelection[]): void => {
    if (!project) return
    setPlanRevisionOpen(false)
    const turnId = `turn:${crypto.randomUUID()}`
    activeTurnIdRef.current = turnId
    updateTimeline((current) => [...current, {
      type: 'text', id: `message:user:${crypto.randomUUID()}`, turnId, role: 'user',
      text: instruction, createdAt: new Date().toISOString(),
    }])
    props.onAgentInstruction(instruction, selectedPlots)
  }
  return (
    <main className="workspace-main" id="conversation-main">
      <header className="workspace-header">
        <div className="workspace-heading">
          <h1>{project ? project.name : '开始使用'}</h1>
        </div>
        {project && <div className="workspace-header__actions"><button type="button" onClick={props.onUndo} disabled={!props.canUndo || busyAction !== undefined} aria-label="撤销本轮修改"><Undo2 size={15} />撤销</button><button type="button" onClick={props.onRedo} disabled={!props.canRedo || busyAction !== undefined} aria-label="重做本轮修改"><Redo2 size={15} />重做</button><button type="button" onClick={props.onOpenTasks}><Activity size={15} />任务</button><span className="autosave-status"><CircleCheck size={14} />项目 v{project.projectVersion}</span></div>}
      </header>

      {!project ? <Startup {...props} /> : (
        <div className="conversation-scroll">
          <div className="conversation-feed product-conversation-feed">
            {datasets.length === 0 ? (
              <AgentMessage className="conversation-prompt"><p>上传数据文件，并告诉我你想画什么图。</p></AgentMessage>
            ) : (
              <AgentMessage><p>已导入 {datasets.length} 个数据表。</p>{props.importNotice && <InlineNotice notice={props.importNotice} />}<DatasetObject datasets={datasets} activeDataset={activeDataset} onSelectDataset={props.onSelectDataset} selectedWorkflowSourceIds={props.selectedWorkflowSourceIds} onToggleWorkflowSource={props.onToggleWorkflowSource} /></AgentMessage>
            )}
            {timeline.map((item) => {
              const motionClass = hydratedTimelineIds.has(item.id) ? undefined : 'motion-timeline-enter'
              if (item.type === 'text') return <ConversationTextMessage key={item.id} message={item} animate={item.role === 'agent' && motionClass !== undefined} />
              if (item.type === 'plan') return <AgentMessage className={motionClass} key={item.id}><WorkflowPlanObject plan={item.plan} datasets={datasets} selectedChart={selectedChart} plot={plot} busy={busyAction === 'agent-plan' && props.workflowPlan?.planId === item.plan.planId} onConfirm={props.onConfirmWorkflowPlan} onReject={props.onRejectWorkflowPlan} onEdit={() => setPlanRevisionOpen(true)} canUndo={props.canUndo} onUndo={props.onUndo} onRun={props.onRunWorkflowPlan} onResume={props.onResumeWorkflowPlan} onAcceptPartial={props.onAcceptPartialTask} /></AgentMessage>
              if (item.type === 'plot') return <PlotObject className={motionClass} key={item.id} {...props} plot={item.plot} plotNumber={item.plotNumber} interactive={plot?.plotId === item.plot.plotId && plot.plotVersion === item.plot.plotVersion} />
              return <ExportResult className={motionClass} key={item.id} record={item.record} onOpen={props.onOpenExport} onReveal={props.onRevealExport} />
            })}
            {notice && notice.kind !== 'success' && <NoticeMessage notice={notice} />}
            <ActivityMessage busyAction={busyAction} agentRuntimeLabel={props.agentRuntimeLabel} agentRuntimeTaskId={props.agentRuntimeTaskId} tasks={props.taskEvents} onCancel={props.onCancelTask} />
            <div ref={scrollAnchorRef} className="conversation-turn-anchor" aria-hidden="true" />
            {planRevisionOpen && <AgentMessage><p>请在输入框说明要修改的字段绑定，例如“X 改为 Time”。我会基于当前计划生成修订版，再请你确认。</p></AgentMessage>}
            {manualMappingOpen && selectedChart && activeDataset && !plot && <AgentMessage><p>我建议按以下方式绑定字段。先检查数据，再确认是否创建图形。</p><MappingObject key={`${selectedChart.id}:${activeDataset.datasetId}:${activeDataset.sourceVersion}`} chart={selectedChart} dataset={activeDataset} busy={busyAction === 'plot'} selectedDataCount={props.selectedWorkflowSourceIds.length} onConfirm={props.onConfirmMapping} onConfirmMultiSource={props.onConfirmMultiSourceMapping} onCancel={() => setManualMappingOpen(false)} /></AgentMessage>}
          </div>
        </div>
      )}

      {project && notice?.kind === 'success' && exportRecord && <ProductToast key={exportRecord.exportId} notice={notice} record={exportRecord} onOpen={props.onOpenExport} onReveal={props.onRevealExport} />}

      {project && <ConversationComposer plotReferences={availablePlots} selectedChart={selectedChart} multiChartTask={props.multiChartTask} datasetCount={datasets.length} configured={props.agentConfigured} busy={busyAction === 'agent'} importing={busyAction === 'import'} notice={notice} mappingOpen={manualMappingOpen} canInspectMapping={Boolean(selectedChart && !props.multiChartTask && activeDataset && !plot)} onSubmit={submitInstruction} onConfigure={props.onConfigureAgent} onOpenLibrary={props.onOpenLibrary} onImportData={props.onImportData} onToggleMapping={() => setManualMappingOpen((open) => !open)} />}
      {!project && <div className="startup-footer"><span>{props.previewMode ? '界面预览使用内存示例，不写入本机' : '所有项目、数据与图表默认保存在这台电脑上'}</span><span>{props.previewMode ? 'PlotAgent · 开发预览' : 'PlotAgent 0.1.0 · 无需账号'}</span></div>}
    </main>
  )
}
