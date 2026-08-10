import { useMemo, useState } from 'react'
import {
  Activity,
  ArrowRight,
  Check,
  CheckCircle2,
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
  PanelTop,
  Play,
  SendHorizontal,
  Settings2,
  TableProperties,
  TriangleAlert,
} from 'lucide-react'

import type { CoreStatus, FieldMappingInput } from '../../../shared/desktop-contract'
import type { ChartType } from '../data/chartCatalog'
import type {
  AgentOutcome,
  AgentPlanView,
  ProductDataset,
  ProductPlot,
  ProductProject,
} from '../data/productState'

export type ScopeMode = 'current' | 'selected' | 'batch' | 'figure'

export interface ProductNotice {
  kind: 'info' | 'success' | 'warning' | 'error'
  title: string
  message: string
  actionLabel?: string
  onAction?: () => void
}

export interface BatchView {
  batchId: string
  taskId: string
  version: number
  state: string
  items: { id: string; state: string }[]
}

export interface FigureView {
  figureId: string
  version: number
  previewUrl?: string
}

export interface ExportRecordView {
  exportId: string
  format: 'png' | 'svg' | 'opju'
  targetKind: 'plot' | 'batch' | 'figure'
  targetId: string
  artifactHash?: string
  artifactSize?: number
}

export interface AgentChangeSetView {
  planId: string
  state: string
  items: {
    taskItemId: string
    actionType: string
    state: string
    attemptCount: number
    beforeCount: number
    afterCount: number
    failure?: string
  }[]
}

interface ConversationWorkspaceProps {
  core: CoreStatus
  project?: ProductProject
  datasets: ProductDataset[]
  activeDataset?: ProductDataset
  selectedChart?: ChartType
  plot?: ProductPlot
  batch?: BatchView
  figure?: FigureView
  figureCandidateCount: number
  plotIsFigureCandidate: boolean
  exportRecord?: ExportRecordView
  changeSet?: AgentChangeSetView
  notice?: ProductNotice
  busyAction?: string
  agentOutcome?: AgentOutcome
  agentPlan?: AgentPlanView
  agentConfigured: boolean
  previewMode?: boolean
  onOpenSample: () => void
  onImportData: () => void
  onOpenProject: () => void
  onOpenLibrary: () => void
  onSelectDataset: (datasetId: string) => void
  onConfirmMapping: (mapping: FieldMappingInput) => void
  onAgentInstruction: (instruction: string, scope: ScopeMode) => void
  onConfirmAgentPlan: (planId: string) => void
  onRejectAgentPlan: (planId: string) => void
  onRunAgentPlan: (planId: string) => void
  onResumeAgentPlan: (planId: string) => void
  onConfigureAgent: () => void
  onExport: (format: 'png' | 'svg' | 'opju', target?: { kind: 'batch' | 'figure'; id: string; version: number }) => void
  onCreateBatch: () => void
  onCreateFigure: () => void
  onToggleFigureCandidate: () => void
  onOpenFocus: () => void
  onOpenBatchInspect: () => void
  onOpenCompose: () => void
  onOpenTasks: () => void
}

const numericKinds = new Set(['integer', 'float', 'number', 'numeric', 'decimal'])
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

interface MappingRole {
  role: string
  label: string
  numeric: boolean
  required: boolean
}

function mappingRoles(chartId: string): MappingRole[] {
  const registry: Record<string, { required: string[]; optional: string[] }> = {
    K01: { required: ['x', 'y'], optional: [] }, K02: { required: ['x', 'y'], optional: [] },
    K03: { required: ['x', 'y'], optional: ['group'] }, K04: { required: ['x', 'y'], optional: ['size', 'color', 'group'] },
    K06: { required: ['center'], optional: ['x', 'x_lower', 'x_upper', 'lower', 'upper', 'error', 'group'] },
    K07: { required: ['x', 'center'], optional: ['lower', 'upper', 'group'] }, K08: { required: ['category', 'value'], optional: [] },
    K09: { required: ['category', 'group', 'value'], optional: [] }, K10: { required: ['category', 'component', 'value'], optional: [] },
    K11: { required: ['category', 'component', 'value'], optional: [] }, K12: { required: ['value'], optional: ['group'] },
    K13: { required: ['value'], optional: ['group'] }, K14: { required: ['value'], optional: ['group'] },
    K15: { required: ['value'], optional: [] }, K16: { required: ['value'], optional: ['group'] },
    K18: { required: ['x', 'y'], optional: [] }, K19: { required: ['time', 'value'], optional: ['event'] },
    K20: { required: ['row', 'column', 'value'], optional: [] }, K21: { required: ['row_label', 'column_label', 'value'], optional: [] },
    K22: { required: ['x', 'y', 'z'], optional: [] }, K24: { required: ['facet', 'base_x', 'base_y'], optional: [] },
    K25: { required: ['panel'], optional: [] }, S01: { required: ['time', 'survival'], optional: ['lower', 'upper', 'risk_count', 'group'] },
    S21: { required: ['label', 'effect', 'lower', 'upper'], optional: ['weight'] },
    S34: { required: ['z_real', 'z_imaginary'], optional: ['frequency'] }, S61: { required: ['actual', 'predicted'], optional: ['count'] },
    X02: { required: ['x', 'y'], optional: [] },
    X03: { required: ['category', 'series_1', 'series_2'], optional: ['series_3'] }, X05: { required: ['value'], optional: ['group'] },
    X07: { required: ['value', 'group'], optional: [] }, X09: { required: ['category', 'start', 'end'], optional: ['middle'] },
    X11: { required: ['category', 'delta'], optional: [] }, X12: { required: ['item', 'actual_value', 'target'], optional: ['range1', 'range2', 'range3'] },
    X13: { required: ['category', 'left', 'right'], optional: [] }, X15: { required: ['x', 'y', 'z'], optional: [] },
    X16: { required: ['x', 'y'], optional: [] }, X17: { required: ['x', 'y'], optional: [] },
    X18: { required: ['value'], optional: [] }, X19: { required: ['method_a', 'method_b'], optional: [] },
    X23: { required: ['x', 'left', 'right'], optional: [] }, X24: { required: ['category', 'value'], optional: [] },
    X35: { required: ['category', 'left', 'right'], optional: [] }, X36: { required: ['category', 'left', 'right'], optional: [] },
    X37: { required: ['group', 'left', 'right'], optional: [] }, X38: { required: ['x', 'y', 'series'], optional: [] },
    X39: { required: ['series_1', 'series_2'], optional: ['series_3'] }, X40: { required: ['series_1', 'series_2'], optional: ['series_3'] },
  }
  const labels: Record<string, string> = {
    middle: '中间界限',
    x: 'X', y: 'Y', z: 'Z', category: '类别', group: '分组', component: '组成', value: '数值',
    center: '中心值', x_lower: 'X 下限', x_upper: 'X 上限', lower: '下限', upper: '上限', error: '误差', size: '大小', color: '颜色',
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
  const entry = registry[chartId] ?? registry.K01
  return [
    ...entry.required.map((role) => ({ role, label: labels[role] ?? role, numeric: !categorical.has(role), required: true })),
    ...entry.optional.map((role) => ({ role, label: labels[role] ?? role, numeric: !categorical.has(role), required: false })),
  ]
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

function DatasetObject({
  datasets,
  activeDataset,
  onSelectDataset,
}: Pick<ConversationWorkspaceProps, 'datasets' | 'activeDataset' | 'onSelectDataset'>): React.JSX.Element {
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
      <div className="schema-strip" role="table" aria-label="字段、类型与单位">
        <div role="row" className="schema-row schema-row--heading"><span role="columnheader">字段</span><span role="columnheader">逻辑类型</span><span role="columnheader">物理类型</span><span role="columnheader">单位</span></div>
        {activeDataset.fields.map((field) => (
          <div role="row" className="schema-row" key={field.fieldId}>
            <span role="cell" title={field.name}><strong>{displayFieldName(field.name)}</strong></span>
            <span role="cell">{displayLogicalType(field.logicalType)}</span><span role="cell">{displayPhysicalType(field.physicalType)}</span><span role="cell">{field.unit}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

function MappingObject({
  chart,
  dataset,
  busy,
  onConfirm,
}: {
  chart: ChartType
  dataset: ProductDataset
  busy: boolean
  onConfirm: (mapping: FieldMappingInput) => void
}): React.JSX.Element {
  const variadicSeries = ['X03', 'X39', 'X40'].includes(chart.id)
  const [seriesRoleCount, setSeriesRoleCount] = useState(2)
  const roles = useMemo(() => {
    const fixed = mappingRoles(chart.id).filter((role) => !role.role.startsWith('series_'))
    if (!variadicSeries) return fixed
    return [
      ...fixed,
      ...Array.from({ length: seriesRoleCount }, (_, index) => ({
        role: `series_${index + 1}`,
        label: `系列 ${index + 1}`,
        numeric: true,
        required: true,
      })),
    ]
  }, [chart.id, seriesRoleCount, variadicSeries])
  const [values, setValues] = useState<Record<string, string>>(() => {
    const numeric = dataset.fields.filter((field) => numericKinds.has(field.logicalType.toLocaleLowerCase('en-US')))
    const other = dataset.fields.filter((field) => !numeric.includes(field))
    const next: Record<string, string> = {}
    roles.forEach((role, index) => {
      if (!role.required) { next[role.role] = ''; return }
      const candidates = role.numeric ? numeric : other.length > 0 ? other : dataset.fields
      next[role.role] = candidates[index % Math.max(candidates.length, 1)]?.fieldId ?? dataset.fields[0]?.fieldId ?? ''
    })
    return next
  })
  const complete = roles.filter((role) => role.required).every((role) => values[role.role])
  return (
    <section className="object-block mapping-object" aria-labelledby="mapping-title">
      <header className="object-header">
        <span className="object-icon object-icon--mapping"><TableProperties size={17} /></span>
        <div><h3 id="mapping-title">确认字段映射</h3><p>{chart.name}</p></div>
      </header>
      <div className="mapping-form">
        {roles.map((role) => (
          <label key={role.role}><span>{role.label}{role.required ? '' : '（可选）'}</span>
            <select value={values[role.role] ?? ''} onChange={(event) => setValues((current) => ({ ...current, [role.role]: event.target.value }))}>
              <option value="">选择字段</option>
              {dataset.fields.map((field) => <option key={field.fieldId} value={field.fieldId}>{displayFieldName(field.name)} · {displayLogicalType(field.logicalType)} · {field.unit}</option>)}
            </select>
          </label>
        ))}
      </div>
      {variadicSeries && (
        <div className="mapping-series-actions">
          <button type="button" onClick={() => setSeriesRoleCount((count) => count + 1)}>添加系列</button>
          <button type="button" disabled={seriesRoleCount <= 2} onClick={() => {
            const role = `series_${seriesRoleCount}`
            setValues((current) => {
              const next = { ...current }
              delete next[role]
              return next
            })
            setSeriesRoleCount((count) => Math.max(2, count - 1))
          }}>移除末项</button>
        </div>
      )}
      <footer className="mapping-confirmation">
        <button className="primary-button" type="button" disabled={!complete || busy} onClick={() => onConfirm({ roles: Object.fromEntries(Object.entries(values).filter(([, field]) => field)) })}>
          {busy ? <LoaderCircle className="spin" size={15} /> : <CheckCircle2 size={15} />}确认映射并绘图
        </button>
      </footer>
    </section>
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
  figureCandidateCount,
  plotIsFigureCandidate,
  onToggleFigureCandidate,
}: Pick<ConversationWorkspaceProps, 'plot' | 'selectedChart' | 'busyAction' | 'previewMode' | 'onExport' | 'onOpenLibrary' | 'onOpenFocus' | 'onCreateBatch' | 'figureCandidateCount' | 'plotIsFigureCandidate' | 'onToggleFigureCandidate'> & { chart?: ChartType }): React.JSX.Element {
  if (!plot) return <div />
  return (
    <section className="object-block product-plot-object" aria-labelledby="plot-title">
      <header className="object-header">
        <span className="object-icon object-icon--batch"><FileChartColumn size={17} /></span>
        <div><h3 id="plot-title">{chart?.name ?? plot.chartId} · v{plot.plotVersion}</h3><p>{plot.plotId} · {plot.chartId} · ResolvedRenderPlan</p></div>
        <span className="status-label status-label--success"><Check size={13} />{previewMode ? '界面预览' : '已渲染'}</span>
      </header>
      <div className="product-preview">
        {plot.preview?.url ? <img src={plot.preview.url} alt={`${chart?.name ?? plot.chartId} ${previewMode ? '界面预览' : '真实渲染预览'}`} /> : <div className="preview-pending"><LoaderCircle className="spin" size={20} /><span>等待受控预览资源</span></div>}
      </div>
      <footer className="plot-actions">
        <button type="button" onClick={onOpenLibrary}><Library size={15} />选择其他图形</button>
        <button type="button" onClick={onOpenFocus}><Settings2 size={15} />聚焦编辑</button>
        <button type="button" onClick={onCreateBatch}><Images size={15} />创建批次</button>
        <button type="button" onClick={onToggleFigureCandidate} aria-pressed={plotIsFigureCandidate}>
          <PanelTop size={15} />{plotIsFigureCandidate ? '移出组合图' : `加入组合图 (${figureCandidateCount}/4)`}
        </button>
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
  outcome?: AgentOutcome
  notice?: ProductNotice
  onSubmit: (instruction: string, scope: ScopeMode) => void
  onConfigure: () => void
  onOpenLibrary: () => void
  onImportData: () => void
}): React.JSX.Element {
  const [scope, setScope] = useState<ScopeMode>('current')
  const [value, setValue] = useState('')
  const canSubmit = datasetCount > 0 && selectedChart !== undefined
  const submit = (): void => {
    const instruction = value.trim()
    if (!instruction || !canSubmit || busy) return
    if (!configured) { onConfigure(); return }
    onSubmit(instruction, scope)
    setValue('')
  }
  return (
    <div className="composer-wrap">
      {notice?.kind === 'success' && <div className="composer-success" role="status"><Check size={14} />{notice.title}</div>}
      {outcome && outcome.kind !== 'action_plan' && <div className={`agent-outcome agent-outcome--${outcome.kind}`} role={outcome.kind === 'rejected' ? 'alert' : 'status'}><div><strong>{outcome.title}</strong><p>{outcome.message}</p>{outcome.questions?.map((question) => <p className="agent-question" key={question.questionKey}>{question.prompt}</p>)}</div></div>}
      <div className="composer" aria-label="自然语言绘图指令">
        <div className="composer-context">
          <span className="target-chip"><Layers3 size={14} />{plot ? `${plot.plotId} · v${plot.plotVersion}` : selectedChart ? `${selectedChart.id} · ${selectedChart.name}` : '未选择图形'}</span>
          {plot &&
          <div className="scope-switch" aria-label="作用范围">
            {([['current', '当前图'], ['selected', '选中图'], ['batch', '整个批次'], ['figure', '组合图']] as const).map(([mode, label]) => (
              <button className={scope === mode ? 'is-active' : ''} key={mode} type="button" onClick={() => setScope(mode)} aria-pressed={scope === mode}>{label}</button>
            ))}
          </div>}
        </div>
        <textarea value={value} disabled={busy} onChange={(event) => setValue(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit() } }} placeholder={plot ? '描述你想怎样修改这张图' : '描述你想绘制的图'} aria-label="描述绘图要求" />
        <div className="composer-toolbar">
          <button type="button" className={selectedChart ? 'composer-tool is-selected' : 'composer-tool'} onClick={onOpenLibrary}><Library size={15} />{selectedChart ? selectedChart.name : '选择图形'}</button>
          <button type="button" className="composer-tool" onClick={onImportData} disabled={importing}>
            {importing ? <LoaderCircle className="spin" size={15} /> : <FileUp size={15} />}
            {importing ? '正在导入' : `上传数据${datasetCount > 0 ? ` (${datasetCount})` : ''}`}
          </button>
          <button className="send-button" type="button" onClick={submit} disabled={!canSubmit || !value.trim() || busy} aria-label="生成任务计划" title={!canSubmit ? '导入数据并选择图形后即可发送' : undefined}>{busy ? <LoaderCircle className="spin" size={17} /> : <SendHorizontal size={17} />}</button>
        </div>
      </div>
    </div>
  )
}

function AgentPlanObject({
  plan,
  busy,
  onConfirm,
  onReject,
  onRun,
  onResume,
}: {
  plan: AgentPlanView
  busy: boolean
  onConfirm: (planId: string) => void
  onReject: (planId: string) => void
  onRun: (planId: string) => void
  onResume: (planId: string) => void
}): React.JSX.Element {
  const stateLabels: Record<string, string> = {
    draft: '草稿',
    needs_confirmation: '等待确认',
    ready: '待执行',
    running: '执行中',
    partial_success: '部分完成',
    partially_failed: '部分完成',
    succeeded: '已完成',
    failed: '未完成',
    interrupted: '已中断',
    needs_input: '等待输入',
    stale: '计划已过期',
    cancelled: '已取消',
  }
  return (
    <section className={`agent-plan agent-plan--${plan.state}`} aria-labelledby={`plan-${plan.planId}`}>
      <header className="agent-plan__header">
        <ListChecks size={17} aria-hidden="true" />
        <div><h3 id={`plan-${plan.planId}`}>任务计划</h3><span>{plan.completedCount}/{plan.steps.length} 步完成</span></div>
        <span className="agent-plan__state">{plan.state === 'running' && <LoaderCircle className="spin" size={13} />}{stateLabels[plan.state] ?? plan.state}</span>
      </header>
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
              {step.outputPlot && <p className="agent-plan-step__output">{step.outputPlot.plotId} · v{step.outputPlot.plotVersion}</p>}
              {step.outputBatch && <p className="agent-plan-step__output">{step.outputBatch.batchId} · v{step.outputBatch.batchVersion}</p>}
              {step.failure && <p>{step.failure.message}</p>}
            </div>
            {step.attemptCount > 0 && <span className="agent-plan-step__attempt">{step.attemptCount} 次</span>}
          </li>
        ))}
      </ol>
      {plan.warnings.length > 0 && <div className="agent-plan__warnings">{plan.warnings.map((warning) => <p key={warning}><TriangleAlert size={14} />{warning}</p>)}</div>}
      {plan.state === 'stale' && <p className="agent-plan__stale">作用对象已变化，请重新描述任务生成新计划。</p>}
      <footer className="agent-plan__actions">
        {plan.state === 'needs_confirmation' && <><button type="button" onClick={() => onReject(plan.planId)} disabled={busy}>取消计划</button><button className="primary-button" type="button" onClick={() => onConfirm(plan.planId)} disabled={busy}>确认并执行</button></>}
        {plan.state === 'ready' && <button className="primary-button" type="button" onClick={() => onRun(plan.planId)} disabled={busy}>执行计划</button>}
        {plan.resumable && <button className="primary-button" type="button" onClick={() => onResume(plan.planId)} disabled={busy}>继续未完成步骤</button>}
        {plan.state === 'succeeded' && <span className="agent-plan__saved"><CircleCheck size={14} />更改已保存</span>}
      </footer>
    </section>
  )
}

export function ConversationWorkspace(props: ConversationWorkspaceProps): React.JSX.Element {
  const { project, datasets, activeDataset, selectedChart, plot, batch, figure, exportRecord, changeSet, notice, busyAction } = props
  const [manualMappingOpen, setManualMappingOpen] = useState(false)
  return (
    <main className="workspace-main" id="conversation-main">
      <header className="workspace-header">
        <div className="workspace-heading">
          <h1>{project ? project.name : '开始使用'}</h1>
        </div>
        {project && <div className="workspace-header__actions"><button type="button" onClick={props.onOpenTasks}><Activity size={15} />任务</button><span className="autosave-status"><CircleCheck size={14} />项目 v{project.projectVersion}</span></div>}
      </header>

      {!project ? <Startup {...props} /> : (
        <div className="conversation-scroll">
          <div className="conversation-feed product-conversation-feed">
            {notice && notice.kind !== 'success' && <InlineNotice notice={notice} />}
            {datasets.length === 0 ? (
              <div className="message message--agent conversation-prompt"><div className="agent-avatar" aria-label="PlotAgent"><span>PA</span></div><div className="agent-response"><p>上传数据文件，并告诉我你想画什么图。</p></div></div>
            ) : (
              <>
                <div className="message message--agent"><div className="agent-avatar" aria-label="PlotAgent"><span>PA</span></div><div className="agent-response"><p>已导入 {datasets.length} 个数据表。</p><DatasetObject datasets={datasets} activeDataset={activeDataset} onSelectDataset={props.onSelectDataset} /></div></div>
                {selectedChart && activeDataset && !plot && <section className="chart-selection-strip"><div><strong>{selectedChart.id} {selectedChart.name}</strong><span>已选择图形</span></div><button type="button" onClick={() => setManualMappingOpen((open) => !open)}>{manualMappingOpen ? '收起字段映射' : '手动映射'}</button></section>}
                {manualMappingOpen && selectedChart && activeDataset && !plot && <MappingObject key={`${selectedChart.id}:${activeDataset.datasetId}`} chart={selectedChart} dataset={activeDataset} busy={busyAction === 'plot'} onConfirm={props.onConfirmMapping} />}
                {plot && <PlotObject {...props} chart={selectedChart} />}
                {props.agentPlan && <AgentPlanObject plan={props.agentPlan} busy={busyAction === 'agent-plan'} onConfirm={props.onConfirmAgentPlan} onReject={props.onRejectAgentPlan} onRun={props.onRunAgentPlan} onResume={props.onResumeAgentPlan} />}
                {changeSet && <section className="object-block product-result-strip" aria-label="更改记录"><ListChecks size={17} /><div><strong>ChangeSet · {changeSet.state}</strong><p>{changeSet.planId} · {changeSet.items.filter((item) => item.state === 'succeeded').length}/{changeSet.items.length} 项已提交</p></div></section>}
                {batch && <section className="object-block product-result-strip"><Images size={17} /><div><strong>批次 {batch.batchId}</strong><p>{batch.items.length} 项 · 状态 {batch.state}</p></div><button type="button" onClick={props.onOpenBatchInspect}>检查批次</button><button type="button" onClick={() => props.onExport('opju', { kind: 'batch', id: batch.batchId, version: batch.version })}><Download size={14} />导出批次 OPJU</button></section>}
                {figure && <section className="object-block product-result-strip"><PanelTop size={17} /><div><strong>组合图 {figure.figureId}</strong><p>固定版本 v{figure.version}</p></div><button type="button" onClick={props.onOpenCompose}>打开组合图</button><button type="button" onClick={() => props.onExport('opju', { kind: 'figure', id: figure.figureId, version: figure.version })}><Download size={14} />导出组合图 OPJU</button></section>}
                {exportRecord && <section className="object-block product-result-strip" aria-label="导出记录"><Download size={17} /><div><strong>{exportRecord.format.toLocaleUpperCase('en-US')} 导出记录</strong><p>{exportRecord.exportId} · {exportRecord.targetKind} {exportRecord.targetId}{exportRecord.artifactSize === undefined ? '' : ` · ${exportRecord.artifactSize} B`}</p>{exportRecord.artifactHash && <code title={exportRecord.artifactHash}>{exportRecord.artifactHash.slice(0, 12)}…</code>}</div></section>}
              </>
            )}
          </div>
        </div>
      )}

      {project && <ConversationComposer plot={plot} selectedChart={selectedChart} datasetCount={datasets.length} configured={props.agentConfigured} busy={busyAction === 'agent'} importing={busyAction === 'import'} outcome={props.agentOutcome} notice={notice} onSubmit={props.onAgentInstruction} onConfigure={props.onConfigureAgent} onOpenLibrary={props.onOpenLibrary} onImportData={props.onImportData} />}
      {!project && <div className="startup-footer"><span>{props.previewMode ? '界面预览使用内存示例，不写入本机' : '所有项目、数据与图表默认保存在这台电脑上'}</span><span>{props.previewMode ? 'PlotAgent · 开发预览' : 'PlotAgent 0.1.0 · 无需账号'}</span></div>}
    </main>
  )
}
