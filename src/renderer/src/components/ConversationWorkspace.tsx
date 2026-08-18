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

import type { CoreStatus, FieldMappingInput, TaskEvent } from '../../../shared/desktop-contract'
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
  readConversationMessages,
  writeConversationMessages,
  type ConversationMessage,
} from '../data/conversationPersistence'
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
  format: 'png' | 'svg' | 'opju'
  targetKind: 'plot'
  targetId: string
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
  plot?: ProductPlot
  exportRecord?: ExportRecordView
  notice?: ProductNotice
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
  onAgentInstruction: (instruction: string, scope: ScopeMode) => void
  onConfirmWorkflowPlan: (planId: string) => void
  onRejectWorkflowPlan: (planId: string) => void
  onRunWorkflowPlan: (planId: string) => void
  onResumeWorkflowPlan: (planId: string) => void
  onConfigureAgent: () => void
  onExport: (format: 'png' | 'svg' | 'opju') => void
  onCreateBatch: () => void
  onOpenFocus: () => void
  onOpenTasks: () => void
  onCancelTask: (taskId: string) => void
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

interface MappingRole extends MappingSuggestionRole {
  label: string
}

function mappingRoles(chart: ChartType): MappingRole[] {
  const labels: Record<string, string> = {
    middle: '中间界限',
    x: 'X', y: 'Y', z: 'Z', category: '类别', group: '分组', component: '组成', value: '数值',
    center: '中心值', x_err_minus: 'X 负误差', x_err_plus: 'X 正误差', y_err_minus: 'Y 负误差', y_err_plus: 'Y 正误差', lower: '下限', upper: '上限', error: '误差', size: '大小', color: '颜色',
    time: '时间', event: '事件', row: '行', column: '列', row_label: '行标签', column_label: '列标签',
    facet: '分面', base_x: '基础 X', base_y: '基础 Y', panel: '面板图', survival: '生存率', risk_count: '风险人数',
    dose: '剂量', response: '响应', parameter: '预计算参数', label: '标签', effect: '效应值', weight: '权重',
    spectral_axis: '谱轴', intensity: '强度', angle: '角度', peak_label: '峰标签', z_real: "Z'", z_imaginary: "-Z''",
    frequency: '频率', actual: '真实类别', predicted: '预测类别', count: '已聚合计数',
    baseline: '基线', start: '起点', end: '终点', series_1: '系列 1', series_2: '系列 2', series_3: '系列 3（可选）', delta: '变化量', item: '项目', actual_value: '实际值', target: '目标',
    range1: '区间 1', range2: '区间 2', range3: '区间 3', left: '左轴数值', right: '右轴数值',
    method_a: '方法 A', method_b: '方法 B', series: '系列', feature: '特征', log2fc: 'log2FC', pvalue: 'P 值', qvalue: 'Q 值',
  }
  const categorical = new Set(['category', 'group', 'component', 'event', 'row', 'column', 'row_label', 'column_label', 'facet', 'panel', 'parameter', 'label', 'peak_label', 'actual', 'predicted', 'item', 'series', 'feature'])
  return [
    ...chart.requiredFields.map((role) => ({ role, label: labels[role] ?? role, numeric: role !== 'time' && !categorical.has(role), datetime: role === 'time', required: true })),
    ...chart.optionalFields.map((role) => ({ role, label: labels[role] ?? role, numeric: role !== 'time' && !categorical.has(role), datetime: role === 'time', required: false })),
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
        <div className="startup-dialog" role="status">
          <span className="startup-dialog__avatar" aria-hidden="true"><FileChartColumn size={18} /></span>
          <span>请先导入数据</span>
        </div>

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
  return <div className="message message--agent conversation-history-message">
    <div className="agent-avatar" aria-label="PlotAgent"><span>PA</span></div>
    <div className="agent-response"><InlineNotice notice={notice} /></div>
  </div>
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
        <div><h3 id="dataset-title">{activeDataset.displayName}</h3><p>数据表 v{activeDataset.sourceVersion} · 原始数据只读</p></div>
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
        <span><strong>{activeDataset.missingCount}</strong> 缺失</span>
        <span><strong>{activeDataset.nonFiniteCount}</strong> 非有限值</span>
        <span><strong>{activeDataset.coordinateKinds.length || 1}</strong> 来源坐标类型</span>
      </div>
      {Object.keys(activeDataset.instrumentMetadata).length > 0 && <dl className="dataset-instrument-metadata" aria-label="仪器信息">
        <dt>仪器信息</dt>
        {Object.entries(activeDataset.instrumentMetadata).slice(0, 6).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}
      </dl>}
      <div className="schema-strip" role="table" aria-label="字段、类型与单位">
        <div role="row" className="schema-row schema-row--heading"><span role="columnheader">字段</span><span role="columnheader">逻辑类型</span><span role="columnheader">物理类型</span><span role="columnheader">单位</span></div>
        {activeDataset.fields.map((field) => (
          <div role="row" className="schema-row" key={field.fieldId}>
            <span role="cell" title={field.name}><strong>{displayFieldName(field.name)}</strong></span>
            <span role="cell">{displayLogicalType(field.logicalType)}</span><span role="cell">{displayPhysicalType(field.physicalType)}</span><span role="cell">{field.unit}</span>
          </div>
        ))}
      </div>
      {datasets.length > 1 && <details className="agent-dataset-context">
        <summary>提供给 Agent 的数据表 <span>{selectedWorkflowSourceIds.length}/8</span></summary>
        <div>
          {datasets.map((dataset) => {
            const active = dataset.datasetId === activeDataset.datasetId
            const selected = selectedWorkflowSourceIds.includes(dataset.datasetId)
            return <label key={dataset.datasetId}>
              <input
                type="checkbox"
                checked={selected}
                disabled={active || (!selected && selectedWorkflowSourceIds.length >= 8)}
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
        <div><h3 id="mapping-title">数据预览与字段绑定</h3><p>{dataset.displayName} · 原始数据只读</p></div>
      </header>
      <div className="mapping-review__toolbar">
        <span>
          <strong>{dataset.sampleRows === undefined
            ? dataset.samplePreviewUnavailable ? '样本预览不可用' : '正在读取样本'
            : `预览前 ${Math.min(dataset.sampleRows.length, 5)} 行`}</strong>
          ，共 {dataset.rowCount.toLocaleString('zh-CN')} 行
        </span>
        <span>字段角色位于原始列名上方</span>
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
                  <small>{displayLogicalType(field.logicalType)} · {field.unit}</small>
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
  chart,
  busyAction,
  previewMode,
  onExport,
  onOpenLibrary,
  onOpenFocus,
  onCreateBatch,
}: Pick<ConversationWorkspaceProps, 'plot' | 'selectedChart' | 'busyAction' | 'previewMode' | 'onExport' | 'onOpenLibrary' | 'onOpenFocus' | 'onCreateBatch'> & { chart?: ChartType }): React.JSX.Element {
  if (!plot) return <div />
  const plotChart = chart?.id === plot.chartId
    ? chart
    : chartCatalog.find((item) => item.id === plot.chartId)
  return (
    <section className="object-block product-plot-object" aria-labelledby="plot-title">
      <header className="object-header">
        <span className="object-icon object-icon--batch"><FileChartColumn size={17} /></span>
        <div><h3 id="plot-title">{plotChart?.name ?? plot.chartId} · v{plot.plotVersion}</h3><p>{plot.plotId} · {plot.chartId} · Agent Native</p></div>
        <span className="status-label status-label--success"><Check size={13} />{previewMode ? '界面预览' : '已渲染'}</span>
      </header>
      <div className="product-preview">
        {plot.preview?.url ? <img src={plot.preview.url} alt={`${plotChart?.name ?? plot.chartId} ${previewMode ? '界面预览' : '真实渲染预览'}`} /> : <div className="preview-pending"><LoaderCircle className="spin" size={20} /><span>等待受控预览资源</span></div>}
      </div>
      <footer className="plot-actions">
        <button type="button" onClick={onOpenLibrary}><Library size={15} />选择其他图形</button>
        <button type="button" onClick={onOpenFocus}><Settings2 size={15} />聚焦编辑</button>
        <button type="button" onClick={onCreateBatch}><Images size={15} />创建批次</button>
        <span />
        {(['png', 'svg', 'opju'] as const).map((format) => (
          <button key={format} type="button" onClick={() => onExport(format)} disabled={busyAction === `export-${format}`}>
            {busyAction === `export-${format}` ? <LoaderCircle className="spin" size={15} /> : <Download size={15} />}导出 {format.toLocaleUpperCase('en-US')}
          </button>
        ))}
      </footer>
    </section>
  )
}

function ConversationComposer({
  plot,
  selectedChart,
  datasetCount,
  configured,
  busy,
  importing,
  outcome,
  notice,
  onSubmit,
  onConfigure,
  onOpenLibrary,
  onImportData,
}: {
  plot?: ProductPlot
  selectedChart?: ChartType
  datasetCount: number
  configured: boolean
  busy: boolean
  importing: boolean
  outcome?: WorkflowOutcome
  notice?: ProductNotice
  onSubmit: (instruction: string, scope: ScopeMode) => void
  onConfigure: () => void
  onOpenLibrary: () => void
  onImportData: () => void
}): React.JSX.Element {
  const [scope, setScope] = useState<ScopeMode>('current')
  const [value, setValue] = useState('')
  const submit = (): void => {
    const instruction = value.trim()
    if (!instruction || busy) return
    onSubmit(instruction, scope)
    setValue('')
  }
  return (
    <div className="composer-wrap">
      {notice?.kind === 'success' && <div className="composer-success" role="status"><Check size={14} />{notice.title}</div>}
      {outcome && outcome.kind !== 'task_plan' && <div className={`agent-outcome agent-outcome--${outcome.kind}`} role={outcome.kind === 'rejected' ? 'alert' : 'status'}><div><strong>{outcome.title}</strong><p>{outcome.message}</p>{outcome.questions?.map((question) => <p className="agent-question" key={question.questionKey}>{question.prompt}</p>)}</div></div>}
      <div className="composer" aria-label="自然语言绘图指令">
        <div className="composer-context">
          <span className="target-chip"><Layers3 size={14} />{plot ? `${plot.plotId} · v${plot.plotVersion}` : selectedChart ? `${selectedChart.id} · ${selectedChart.name}` : '未选择图形'}</span>
          {plot &&
          <div className="scope-switch" aria-label="作用范围">
            {([['current', '当前图'], ['selected', '选中图']] as const).map(([mode, label]) => (
              <button className={scope === mode ? 'is-active' : ''} key={mode} type="button" onClick={() => setScope(mode)} aria-pressed={scope === mode}>{label}</button>
            ))}
          </div>}
        </div>
        <textarea value={value} disabled={busy} onChange={(event) => setValue(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit() } }} placeholder={plot ? '描述你想怎样修改这张图' : '描述绘图要求；缺少数据或图类时，我会告诉你下一步'} aria-label="描述绘图要求" />
        <div className="composer-toolbar">
          <button type="button" className={selectedChart ? 'composer-tool is-selected' : 'composer-tool'} onClick={onOpenLibrary}><Library size={15} />{selectedChart ? selectedChart.name : '选择图形'}</button>
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
}): React.JSX.Element {
  const stateLabels: Record<string, string> = {
    awaiting_confirmation: '等待确认',
    ready: '待执行',
    running: '执行中',
    partially_succeeded: '部分完成',
    succeeded: '已完成',
    failed: '未完成',
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
    return binding.fieldId
  }
  const objectLabel = plan.steps.length > 1
    ? `${plan.steps.length} 个任务`
    : plan.steps[0]?.taskKind === 'create'
      ? `${plan.steps[0].profileId || selectedChart?.id || '待定'} · 新图`
      : plot
        ? `${plot.plotId} · v${plot.plotVersion}`
        : `${selectedChart?.id ?? '待定'} · 新图`
  const previewStep = plan.steps[0]
  const previewDataset = datasets.find((dataset) => (
    previewStep?.sourceDatasetIds.includes(dataset.datasetId)
  ))
  const previewRoles = new Map(
    (previewStep?.bindings ?? []).map((binding) => [binding.fieldId, binding.role]),
  )
  return (
    <section className={`agent-plan agent-plan--${plan.state}`} aria-labelledby={`plan-${plan.planId}`}>
      <header className="agent-plan__header">
        <ListChecks size={17} aria-hidden="true" />
        <div><h3 id={`plan-${plan.planId}`}>任务计划</h3><span>{plan.completedCount}/{plan.steps.length} 步完成</span></div>
        <span className="agent-plan__state">{plan.state === 'running' && <LoaderCircle className="spin" size={13} />}{stateLabels[plan.state] ?? plan.state}</span>
      </header>
      <div className="agent-plan__context">
        <span><strong>对象</strong>{objectLabel}</span>
        <span><strong>输出</strong>Matplotlib 预览 · 可导出 Origin 原生项目</span>
      </div>
      {previewDataset && <section className="agent-plan__data-preview" aria-label="计划字段绑定与数据样本">
        <header><strong>{previewDataset.displayName}</strong><span>原始数据只读 · {plan.steps.length > 1 ? '首项示例' : '前 3 行'}</span></header>
        <div className="mapping-preview-scroll" tabIndex={0} aria-label="计划字段绑定和数据预览，可横向滚动">
          <table className="mapping-preview-table mapping-preview-table--readonly" style={{ minWidth: `${Math.max(620, previewDataset.fields.length * 138)}px` }}>
            <thead><tr>{previewDataset.fields.map((field) => <th key={field.fieldId} scope="col">
              <div className="mapping-column-head">
                <span className="mapping-role-badge" data-empty={!previewRoles.has(field.fieldId)}>{previewRoles.get(field.fieldId) ?? '未使用'}</span>
                <strong title={field.name}>{displayFieldName(field.name)}</strong>
                <small>{displayLogicalType(field.logicalType)} · {field.unit}</small>
              </div>
            </th>)}</tr></thead>
            <tbody>{previewDataset.sampleRows?.slice(0, 3).map((row, rowIndex) => <tr key={`plan-preview-${rowIndex}`}>{previewDataset.fields.map((field, columnIndex) => {
              const value = previewValue(row[columnIndex])
              return <td key={field.fieldId} title={value}>{value}</td>
            })}</tr>) ?? <tr><td className="mapping-preview-empty" colSpan={previewDataset.fields.length}>样本预览暂不可用，字段绑定仍来自同一份 Core 计划。</td></tr>}</tbody>
          </table>
        </div>
      </section>}
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
              <strong>{step.title}</strong>
              {step.detail && <p className="agent-plan-step__detail">{step.detail}</p>}
              {step.bindings.length > 0 && <dl className="agent-plan-step__bindings" aria-label={`${step.title} 字段绑定`}>
                <div className="agent-plan-step__section-label"><dt>字段绑定</dt><dd /></div>
                {step.bindings.map((binding) => <div key={`${binding.role}:${binding.fieldId}`}><dt>{binding.role}</dt><dd>{fieldLabel(binding)}</dd></div>)}
              </dl>}
              {step.changes.length > 0 && <ul className="agent-plan-step__changes" aria-label={`${step.title} 视觉修改`}>
                {step.changes.map((change) => <li key={change}>{change}</li>)}
              </ul>}
              {step.outputPlot && <p className="agent-plan-step__output">{step.outputPlot.plotId} · v{step.outputPlot.plotVersion}</p>}
              {step.failure && <p>{step.failure.message}</p>}
            </div>
            {step.attemptCount > 0 && <span className="agent-plan-step__attempt">{step.attemptCount} 次</span>}
          </li>
        ))}
      </ol>
      {plan.warnings.length > 0 && <div className="agent-plan__warnings">{plan.warnings.map((warning) => <p key={warning}><TriangleAlert size={14} />{warning}</p>)}</div>}
      <footer className="agent-plan__actions">
        {plan.state === 'awaiting_confirmation' && <><button type="button" onClick={() => onReject(plan.planId)} disabled={busy}>取消</button><button type="button" onClick={() => onEdit(plan.planId)} disabled={busy}>修改绑定</button><button className="primary-button" type="button" onClick={() => onConfirm(plan.planId)} disabled={busy}>确认并执行</button></>}
        {plan.state === 'ready' && <button className="primary-button" type="button" onClick={() => onRun(plan.planId)} disabled={busy}>执行计划</button>}
        {plan.resumable && <button className="primary-button" type="button" onClick={() => onResume(plan.planId)} disabled={busy}>继续未完成步骤</button>}
        {plan.state === 'succeeded' && <><span className="agent-plan__saved"><CircleCheck size={14} />更改已保存</span>{canUndo && <button type="button" onClick={onUndo} disabled={busy}><Undo2 size={14} />撤销本轮</button>}</>}
      </footer>
    </section>
  )
}

const terminalTaskStates = new Set(['succeeded', 'failed', 'cancelled', 'partially_succeeded', 'interrupted'])

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
  return <div className="message message--agent conversation-activity" role="status" aria-live="polite">
    <div className="agent-avatar" aria-hidden="true"><span>PA</span></div>
    <div className="activity-message"><span className="activity-pulse" aria-hidden="true" />{label}
      {(task?.state !== 'committing' && (task?.taskId ?? agentRuntimeTaskId)) && <button type="button" onClick={() => onCancel((task?.taskId ?? agentRuntimeTaskId) as string)}><StopCircle size={14} />停止</button>}
    </div>
  </div>
}

function ConversationHistory({ messages }: { messages: ConversationMessage[] }): React.JSX.Element {
  return <>{messages.map((message) => message.role === 'user'
    ? <div className="message message--user" key={message.id}><div className="message-content">{message.text}</div><time className="message-time">{new Date(message.createdAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</time></div>
    : <div className={`message message--agent conversation-history-message conversation-history-message--${message.kind ?? 'info'}`} key={message.id}>
        <div className="agent-avatar" aria-label="PlotAgent"><span>PA</span></div><div className="agent-response">{message.title && <strong>{message.title}</strong>}<p>{message.text}</p></div>
      </div>)}</>
}

export function ConversationWorkspace(props: ConversationWorkspaceProps): React.JSX.Element {
  const { project, datasets, activeDataset, selectedChart, plot, exportRecord, notice, busyAction } = props
  const [manualMappingOpen, setManualMappingOpen] = useState(false)
  const [messages, setMessages] = useState<ConversationMessage[]>(() => (
    project ? readConversationMessages(window.localStorage, project.projectId) : []
  ))
  const activeTurnRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const outcome = props.workflowOutcome
    if (!project || !outcome || outcome.kind === 'task_plan') return
    queueMicrotask(() => setMessages((current) => {
      const last = current.at(-1)
      if (last?.role === 'agent' && last.title === outcome.title && last.text === outcome.message) return current
      const updated = [...current, {
        id: `message:agent:${crypto.randomUUID()}`,
        role: 'agent' as const,
        title: outcome.title,
        text: outcome.message,
        createdAt: new Date().toISOString(),
        kind: outcome.kind === 'rejected' ? 'error' as const : outcome.kind === 'needs_input' ? 'warning' as const : 'info' as const,
      }]
      writeConversationMessages(window.localStorage, project.projectId, updated)
      return updated
    }))
  }, [project, props.workflowOutcome])

  const visibleMessages = useMemo(() => {
    const outcome = props.workflowOutcome
    if (!outcome || outcome.kind === 'task_plan') return messages
    return messages.filter((message, index) => !(
      index === messages.length - 1
      && message.role === 'agent'
      && message.title === outcome.title
      && message.text === outcome.message
    ))
  }, [messages, props.workflowOutcome])

  useEffect(() => {
    if (messages.length === 0 && busyAction === undefined && props.workflowOutcome === undefined && props.workflowPlan === undefined && exportRecord === undefined) return
    queueMicrotask(() => activeTurnRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'center' }))
  }, [busyAction, exportRecord, messages.length, props.workflowOutcome, props.workflowPlan])

  const submitInstruction = (instruction: string, scope: ScopeMode): void => {
    if (!project) return
    const message: ConversationMessage = {
      id: `message:user:${crypto.randomUUID()}`,
      role: 'user',
      text: instruction,
      createdAt: new Date().toISOString(),
    }
    setMessages((current) => {
      const updated = [...current, message]
      writeConversationMessages(window.localStorage, project.projectId, updated)
      return updated
    })
    props.onAgentInstruction(instruction, scope)
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
            {notice && notice.kind !== 'success' && <NoticeMessage notice={notice} />}
            {datasets.length === 0 ? (
              <div className="message message--agent conversation-prompt"><div className="agent-avatar" aria-label="PlotAgent"><span>PA</span></div><div className="agent-response"><p>上传数据文件，并告诉我你想画什么图。</p></div></div>
            ) : (
              <div className="message message--agent"><div className="agent-avatar" aria-label="PlotAgent"><span>PA</span></div><div className="agent-response"><p>已导入 {datasets.length} 个数据表。</p><DatasetObject datasets={datasets} activeDataset={activeDataset} onSelectDataset={props.onSelectDataset} selectedWorkflowSourceIds={props.selectedWorkflowSourceIds} onToggleWorkflowSource={props.onToggleWorkflowSource} /></div></div>
            )}
            <ConversationHistory messages={visibleMessages} />
            <ActivityMessage busyAction={busyAction} agentRuntimeLabel={props.agentRuntimeLabel} agentRuntimeTaskId={props.agentRuntimeTaskId} tasks={props.taskEvents} onCancel={props.onCancelTask} />
            {props.workflowOutcome && props.workflowOutcome.kind !== 'task_plan' && <div className={`message message--agent conversation-history-message conversation-history-message--${props.workflowOutcome.kind === 'rejected' ? 'error' : props.workflowOutcome.kind === 'needs_input' ? 'warning' : 'info'}`} role={props.workflowOutcome.kind === 'rejected' ? 'alert' : 'status'}>
              <div className="agent-avatar" aria-label="PlotAgent"><span>PA</span></div><div className="agent-response"><strong>{props.workflowOutcome.title}</strong><p>{props.workflowOutcome.message}</p>{props.workflowOutcome.questions?.map((question) => <p className="agent-question" key={question.questionKey}>{question.prompt}</p>)}</div>
            </div>}
            {props.workflowPlan && <div className="message message--agent"><div className="agent-avatar" aria-label="PlotAgent"><span>PA</span></div><div className="agent-response"><p>我已整理好可执行计划，请确认字段和改动。</p><WorkflowPlanObject plan={props.workflowPlan} datasets={datasets} selectedChart={selectedChart} plot={plot} busy={busyAction === 'agent-plan'} onConfirm={props.onConfirmWorkflowPlan} onReject={props.onRejectWorkflowPlan} onEdit={(planId) => { props.onRejectWorkflowPlan(planId); setManualMappingOpen(true) }} canUndo={props.canUndo} onUndo={props.onUndo} onRun={props.onRunWorkflowPlan} onResume={props.onResumeWorkflowPlan} /></div></div>}
            {exportRecord && <section className="object-block product-result-strip product-result-strip--success" aria-label="导出记录" role="status" aria-live="polite"><CircleCheck size={17} /><div><strong>{exportRecord.format.toLocaleUpperCase('en-US')} 导出完成</strong><p>{exportRecord.exportId} · {exportRecord.targetKind} {exportRecord.targetId}{exportRecord.artifactSize === undefined ? '' : ` · ${exportRecord.artifactSize.toLocaleString('zh-CN')} B`}</p>{exportRecord.artifactHash && <code title={exportRecord.artifactHash}>{exportRecord.artifactHash.slice(0, 12)}…</code>}</div></section>}
            <div ref={activeTurnRef} className="conversation-turn-anchor" aria-hidden="true" />
            {selectedChart && activeDataset && !plot && <section className="chart-selection-strip"><div><strong>{selectedChart.id} {selectedChart.name}</strong><span>已选择图形</span></div><button type="button" onClick={() => setManualMappingOpen((open) => !open)}>{manualMappingOpen ? '收起字段映射' : '手动映射'}</button></section>}
            {manualMappingOpen && selectedChart && activeDataset && !plot && <div className="message message--agent"><div className="agent-avatar" aria-label="PlotAgent"><span>PA</span></div><div className="agent-response"><p>我建议按以下方式绑定字段。先检查数据，再确认是否创建图形。</p><MappingObject key={`${selectedChart.id}:${activeDataset.datasetId}:${activeDataset.sourceVersion}`} chart={selectedChart} dataset={activeDataset} busy={busyAction === 'plot'} selectedDataCount={props.selectedWorkflowSourceIds.length} onConfirm={props.onConfirmMapping} onConfirmMultiSource={props.onConfirmMultiSourceMapping} onCancel={() => setManualMappingOpen(false)} /></div></div>}
            {plot && <PlotObject {...props} chart={selectedChart} />}
          </div>
        </div>
      )}

      {project && <ConversationComposer plot={plot} selectedChart={selectedChart} datasetCount={datasets.length} configured={props.agentConfigured} busy={busyAction === 'agent'} importing={busyAction === 'import'} notice={notice} onSubmit={submitInstruction} onConfigure={props.onConfigureAgent} onOpenLibrary={props.onOpenLibrary} onImportData={props.onImportData} />}
      {!project && <div className="startup-footer"><span>{props.previewMode ? '界面预览使用内存示例，不写入本机' : '所有项目、数据与图表默认保存在这台电脑上'}</span><span>{props.previewMode ? 'PlotAgent · 开发预览' : 'PlotAgent 0.1.0 · 无需账号'}</span></div>}
    </main>
  )
}
