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
  FolderOpen,
  Images,
  Layers3,
  Library,
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

interface ConversationWorkspaceProps {
  core: CoreStatus
  project?: ProductProject
  datasets: ProductDataset[]
  activeDataset?: ProductDataset
  selectedChart?: ChartType
  plot?: ProductPlot
  batch?: BatchView
  figure?: FigureView
  notice?: ProductNotice
  busyAction?: string
  agentOutcome?: AgentOutcome
  agentConfigured: boolean
  onOpenSample: () => void
  onImportData: () => void
  onOpenProject: () => void
  onOpenLibrary: () => void
  onSelectDataset: (datasetId: string) => void
  onConfirmMapping: (mapping: FieldMappingInput) => void
  onAgentInstruction: (instruction: string, scope: ScopeMode) => void
  onConfigureAgent: () => void
  onExport: (format: 'png' | 'svg' | 'opju', target?: { kind: 'batch' | 'figure'; id: string; version: number }) => void
  onCreateBatch: () => void
  onCreateFigure: () => void
  onOpenFocus: () => void
  onOpenBatchInspect: () => void
  onOpenCompose: () => void
  onOpenTasks: () => void
}

const numericKinds = new Set(['integer', 'float', 'number', 'numeric', 'decimal'])

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
    K05: { required: ['x', 'y'], optional: ['lower', 'upper'] }, K06: { required: ['center'], optional: ['lower', 'upper', 'error', 'group'] },
    K07: { required: ['x', 'center'], optional: ['lower', 'upper', 'group'] }, K08: { required: ['category', 'value'], optional: [] },
    K09: { required: ['category', 'group', 'value'], optional: [] }, K10: { required: ['category', 'component', 'value'], optional: [] },
    K11: { required: ['category', 'component', 'value'], optional: [] }, K12: { required: ['value'], optional: ['group'] },
    K13: { required: ['value'], optional: ['group'] }, K14: { required: ['value'], optional: ['group'] },
    K15: { required: ['value'], optional: [] }, K16: { required: ['value'], optional: ['group'] }, K17: { required: ['value'], optional: [] },
    K18: { required: ['x', 'y'], optional: [] }, K19: { required: ['time', 'value'], optional: ['event'] },
    K20: { required: ['row', 'column', 'value'], optional: [] }, K21: { required: ['row_label', 'column_label', 'value'], optional: [] },
    K22: { required: ['x', 'y', 'z'], optional: [] }, K24: { required: ['facet', 'base_x', 'base_y'], optional: [] },
    K25: { required: ['panel'], optional: [] }, S01: { required: ['time', 'survival'], optional: ['lower', 'upper', 'risk_count', 'group'] },
    S05: { required: ['dose', 'response'], optional: ['lower', 'upper', 'parameter'] },
    S21: { required: ['label', 'effect', 'lower', 'upper'], optional: ['weight'] },
    S25: { required: ['spectral_axis', 'intensity'], optional: [] }, S31: { required: ['angle', 'intensity'], optional: ['peak_label'] },
    S34: { required: ['z_real', 'z_imaginary'], optional: ['frequency'] }, S61: { required: ['actual', 'predicted'], optional: [] },
    X01: { required: ['x', 'y'], optional: [] }, X02: { required: ['category', 'value'], optional: ['baseline', 'group'] },
    X03: { required: ['category', 'start', 'end'], optional: ['group'] }, X05: { required: ['value'], optional: ['group'] },
    X07: { required: ['value', 'group'], optional: [] }, X09: { required: ['category', 'start', 'end'], optional: ['middle'] },
    X11: { required: ['category', 'delta'], optional: [] }, X12: { required: ['item', 'actual_value', 'target'], optional: ['range1', 'range2', 'range3'] },
    X13: { required: ['category', 'left', 'right'], optional: [] }, X15: { required: ['x', 'y', 'z'], optional: [] },
    X16: { required: ['x', 'y'], optional: [] }, X17: { required: ['x', 'y'], optional: [] },
    X18: { required: ['value'], optional: [] }, X19: { required: ['method_a', 'method_b'], optional: [] },
    X23: { required: ['x', 'left', 'right'], optional: [] }, X24: { required: ['category', 'value'], optional: [] },
    X35: { required: ['category', 'left', 'right'], optional: [] }, X36: { required: ['category', 'left', 'right'], optional: [] },
    X37: { required: ['group', 'left', 'right'], optional: [] }, X38: { required: ['x', 'y', 'series'], optional: [] },
    S07: { required: ['feature', 'log2fc', 'pvalue'], optional: ['qvalue'] },
  }
  const labels: Record<string, string> = {
    middle: '中间界限',
    x: 'X', y: 'Y', z: 'Z', category: '类别', group: '分组', component: '组成', value: '数值',
    center: '中心值', lower: '下限', upper: '上限', error: '误差', size: '大小', color: '颜色',
    time: '时间', event: '事件', row: '行', column: '列', row_label: '行标签', column_label: '列标签',
    facet: '分面', base_x: '基础 X', base_y: '基础 Y', panel: '面板图', survival: '生存率', risk_count: '风险人数',
    dose: '剂量', response: '响应', parameter: '预计算参数', label: '标签', effect: '效应值', weight: '权重',
    spectral_axis: '谱轴', intensity: '强度', angle: '角度', peak_label: '峰标签', z_real: "Z'", z_imaginary: "-Z''",
    frequency: '频率', actual: '真实类别', predicted: '预测类别',
    baseline: '基线', start: '起点', end: '终点', delta: '变化量', item: '项目', actual_value: '实际值', target: '目标',
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
        <div><h3 id="dataset-title">{activeDataset.datasetId}</h3><p>SourceDataset v{activeDataset.sourceVersion} · 原始数据只读</p></div>
        <span className="status-label status-label--success"><Check size={13} />已解析</span>
        {datasets.length > 1 && (
          <label className="dataset-switcher">数据表
            <select value={activeDataset.datasetId} onChange={(event) => onSelectDataset(event.target.value)}>
              {datasets.map((dataset) => <option key={`${dataset.datasetId}:${dataset.sourceVersion}`} value={dataset.datasetId}>{dataset.datasetId}</option>)}
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
            <span role="cell"><strong>{field.name}</strong><small>{field.fieldId}</small></span>
            <span role="cell">{field.logicalType}</span><span role="cell">{field.physicalType}</span><span role="cell">{field.unit}</span>
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
  const roles = useMemo(() => mappingRoles(chart.id), [chart.id])
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
        <div><h3 id="mapping-title">确认字段映射</h3><p>{chart.name} {chart.id} · 一次确认后创建 PlotSpec</p></div>
        <span className="status-label status-label--neutral">用户明确选图</span>
      </header>
      <div className="mapping-form">
        {roles.map((role) => (
          <label key={role.role}><span>{role.label}{role.required ? '' : '（可选）'}</span>
            <select value={values[role.role] ?? ''} onChange={(event) => setValues((current) => ({ ...current, [role.role]: event.target.value }))}>
              <option value="">选择字段</option>
              {dataset.fields.map((field) => <option key={field.fieldId} value={field.fieldId}>{field.name} · {field.logicalType} · {field.unit}</option>)}
            </select>
          </label>
        ))}
      </div>
      <footer className="mapping-confirmation">
        <span><CircleAlert size={15} />此处只确认绘图语义，不修改原始单元格。</span>
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
  onExport,
  onOpenLibrary,
  onOpenFocus,
  onCreateBatch,
  onCreateFigure,
}: Pick<ConversationWorkspaceProps, 'plot' | 'selectedChart' | 'busyAction' | 'onExport' | 'onOpenLibrary' | 'onOpenFocus' | 'onCreateBatch' | 'onCreateFigure'> & { chart?: ChartType }): React.JSX.Element {
  if (!plot) return <div />
  return (
    <section className="object-block product-plot-object" aria-labelledby="plot-title">
      <header className="object-header">
        <span className="object-icon object-icon--batch"><FileChartColumn size={17} /></span>
        <div><h3 id="plot-title">{chart?.name ?? plot.chartId} · v{plot.plotVersion}</h3><p>{plot.plotId} · {plot.chartId} · ResolvedRenderPlan</p></div>
        <span className="status-label status-label--success"><Check size={13} />已渲染</span>
      </header>
      <div className="product-preview">
        {plot.preview?.url ? <img src={plot.preview.url} alt={`${chart?.name ?? plot.chartId} 真实渲染预览`} /> : <div className="preview-pending"><LoaderCircle className="spin" size={20} /><span>等待受控预览资源</span></div>}
      </div>
      <footer className="plot-actions">
        <button type="button" onClick={onOpenLibrary}><Library size={15} />选择其他图形</button>
        <button type="button" onClick={onOpenFocus}><Settings2 size={15} />聚焦编辑</button>
        <button type="button" onClick={onCreateBatch}><Images size={15} />创建批次</button>
        <button type="button" onClick={onCreateFigure}><PanelTop size={15} />加入组合图</button>
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

function AgentComposer({
  plot,
  configured,
  busy,
  outcome,
  onSubmit,
  onConfigure,
}: {
  plot: ProductPlot
  configured: boolean
  busy: boolean
  outcome?: AgentOutcome
  onSubmit: (instruction: string, scope: ScopeMode) => void
  onConfigure: () => void
}): React.JSX.Element {
  const [scope, setScope] = useState<ScopeMode>('current')
  const [value, setValue] = useState('')
  const submit = (): void => {
    const instruction = value.trim()
    if (!instruction || !configured || busy) return
    onSubmit(instruction, scope)
    setValue('')
  }
  return (
    <div className="composer-wrap">
      {outcome && <div className={`agent-outcome agent-outcome--${outcome.kind}`} role={outcome.kind === 'rejected' ? 'alert' : 'status'}><div><strong>{outcome.title}</strong><p>{outcome.message}</p></div></div>}
      {!configured && <div className="agent-setup"><CircleAlert size={16} /><span>尚未配置模型服务。绘图、批量与导出仍可完全本地使用。</span><button type="button" onClick={onConfigure}>配置模型服务</button></div>}
      <div className="composer" aria-label="自然语言绘图指令">
        <div className="composer-context">
          <span className="target-chip"><Layers3 size={14} />作用对象：{plot.plotId} · v{plot.plotVersion}</span>
          <div className="scope-switch" aria-label="作用范围">
            {([['current', '当前图'], ['selected', '选中图'], ['batch', '整个批次'], ['figure', '组合图']] as const).map(([mode, label]) => (
              <button className={scope === mode ? 'is-active' : ''} key={mode} type="button" onClick={() => setScope(mode)} aria-pressed={scope === mode}>{label}</button>
            ))}
          </div>
        </div>
        <textarea value={value} disabled={!configured || busy} onChange={(event) => setValue(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit() } }} placeholder="例如：Y axis 改成 log10，legend 放到图外右侧" aria-label="描述绘图修改要求" />
        <div className="composer-toolbar"><span className="agent-language">支持中文、English 与混合科研术语</span><button className="send-button" type="button" onClick={submit} disabled={!configured || !value.trim() || busy} aria-label="发送绘图指令">{busy ? <LoaderCircle className="spin" size={17} /> : <SendHorizontal size={17} />}</button></div>
      </div>
      <p className="composer-note">可用对数坐标、图形不可分割的固定计算和用户预计算字段；不提供通用分析或拟合。</p>
    </div>
  )
}

export function ConversationWorkspace(props: ConversationWorkspaceProps): React.JSX.Element {
  const { project, datasets, activeDataset, selectedChart, plot, batch, figure, notice, busyAction } = props
  return (
    <main className="workspace-main" id="conversation-main">
      <header className="workspace-header">
        <div className="workspace-heading">
          {project && <div className="project-context"><FolderOpen size={12} aria-hidden="true" /><span>{project.name}</span></div>}
          <h1>{project ? '绘图对话' : '开始使用'}</h1>
        </div>
        {project && <div className="workspace-header__actions"><button type="button" onClick={props.onOpenTasks}><Activity size={15} />任务</button><span className="autosave-status"><CircleCheck size={14} />项目 v{project.projectVersion}</span></div>}
      </header>

      {!project ? <Startup {...props} /> : (
        <div className="conversation-scroll">
          <div className="conversation-feed product-conversation-feed">
            {notice && <InlineNotice notice={notice} />}
            {datasets.length === 0 ? (
              <section className="project-empty-data"><FileSpreadsheet size={24} /><h2>导入数值数据</h2><p>支持多工作表 Excel 与包含仪器说明的 TXT。第一轮不处理科研图像。</p><button className="primary-button" type="button" onClick={props.onImportData} disabled={busyAction !== undefined}>{busyAction === 'import' ? <LoaderCircle className="spin" size={15} /> : <FolderOpen size={15} />}选择数据文件</button></section>
            ) : (
              <>
                <div className="message message--agent"><div className="agent-avatar" aria-label="PlotAgent"><span>PA</span></div><div className="agent-response"><p>数据已由本地 Core 解析。请先检查字段与质量摘要，再明确选择图形。</p><DatasetObject datasets={datasets} activeDataset={activeDataset} onSelectDataset={props.onSelectDataset} /></div></div>
                {!selectedChart && <div className="explicit-chart-choice"><Library size={19} /><div><strong>请选择要绘制的图形</strong><p>Agent 不会替你推荐、猜测或静默替换图形类型。</p></div><button className="primary-button" type="button" onClick={props.onOpenLibrary}>选择图形</button></div>}
                {selectedChart && activeDataset && !plot && <MappingObject key={`${selectedChart.id}:${activeDataset.datasetId}`} chart={selectedChart} dataset={activeDataset} busy={busyAction === 'plot'} onConfirm={props.onConfirmMapping} />}
                {plot && <PlotObject {...props} chart={selectedChart} />}
                {batch && <section className="object-block product-result-strip"><Images size={17} /><div><strong>批次 {batch.batchId}</strong><p>{batch.items.length} 项 · 状态 {batch.state}</p></div><button type="button" onClick={props.onOpenBatchInspect}>检查批次</button><button type="button" onClick={() => props.onExport('opju', { kind: 'batch', id: batch.batchId, version: batch.version })}><Download size={14} />导出批次 OPJU</button></section>}
                {figure && <section className="object-block product-result-strip"><PanelTop size={17} /><div><strong>组合图 {figure.figureId}</strong><p>固定版本 v{figure.version}</p></div><button type="button" onClick={props.onOpenCompose}>打开组合图</button><button type="button" onClick={() => props.onExport('opju', { kind: 'figure', id: figure.figureId, version: figure.version })}><Download size={14} />导出组合图 OPJU</button></section>}
              </>
            )}
          </div>
        </div>
      )}

      {project && plot && <AgentComposer plot={plot} configured={props.agentConfigured} busy={busyAction === 'agent'} outcome={props.agentOutcome} onSubmit={props.onAgentInstruction} onConfigure={props.onConfigureAgent} />}
      {!project && <div className="startup-footer"><span>所有项目、数据与图表默认保存在这台电脑上</span><span>PlotAgent 0.1.0 · 无需账号</span></div>}
    </main>
  )
}
