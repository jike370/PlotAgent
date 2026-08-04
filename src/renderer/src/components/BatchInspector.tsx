import { useMemo, useState } from 'react'
import {
  ArrowLeft,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  Columns3,
  Combine,
  Eye,
  EyeOff,
  FilePlus2,
  Flag,
  Grid2X2,
  List,
  Maximize2,
  RotateCcw,
  Search,
  Settings2,
  TriangleAlert,
  X,
} from 'lucide-react'

import {
  batchInspectionItems,
  filterBatchItems,
  sortBatchItems,
  type BatchInspectionItem,
  type BatchIssueFilter,
  type BatchSortMode,
  type BatchStatusFilter,
  type BatchViewMode,
} from '../data/batchInspection'
import { BatchPlot } from './PlotVisuals'
import '../batchInspector.css'

interface BatchInspectorProps {
  onClose: () => void
}

const statusLabels = {
  success: '检查通过',
  warning: '科研警告',
  failed: '失败',
}

export function BatchInspector({ onClose }: BatchInspectorProps): React.JSX.Element {
  const [items, setItems] = useState<BatchInspectionItem[]>(() => structuredClone(batchInspectionItems))
  const [view, setView] = useState<BatchViewMode>('grid')
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<BatchStatusFilter>('all')
  const [issueFilter, setIssueFilter] = useState<BatchIssueFilter>('all')
  const [sortMode, setSortMode] = useState<BatchSortMode>('source-asc')
  const [selectedIds, setSelectedIds] = useState<string[]>(['A-25', 'B-37'])
  const [uniformRange, setUniformRange] = useState(false)
  const [overlayMode, setOverlayMode] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [carouselIndex, setCarouselIndex] = useState(0)
  const [savedObject, setSavedObject] = useState('')
  const [announcement, setAnnouncement] = useState('')
  const [alignment, setAlignment] = useState('time')
  const [normalization, setNormalization] = useState('raw')
  const [referenceId, setReferenceId] = useState('A-25')
  const [showConfidence, setShowConfidence] = useState(true)
  const [showDifference, setShowDifference] = useState(false)

  const visibleItems = useMemo(
    () => sortBatchItems(filterBatchItems(items, query, statusFilter, issueFilter), sortMode),
    [issueFilter, items, query, sortMode, statusFilter],
  )
  const selectedItems = items.filter((item) => selectedIds.includes(item.id))
  const comparableItems = selectedItems.filter((item) => item.status !== 'failed')
  const currentCarouselItem = visibleItems[carouselIndex] ?? visibleItems[0]
  const temporaryState = uniformRange || overlayMode

  const applySelection = (nextIds: string[]): void => {
    setSelectedIds(nextIds)
    const comparableCount = items.filter((item) => nextIds.includes(item.id) && item.status !== 'failed').length
    if (nextIds.length < 2) setUniformRange(false)
    if (comparableCount < 2) {
      setOverlayMode(false)
      setAdvancedOpen(false)
    }
  }

  const toggleSelection = (id: string): void => {
    const nextIds = selectedIds.includes(id) ? selectedIds.filter((selectedId) => selectedId !== id) : [...selectedIds, id]
    applySelection(nextIds)
  }

  const toggleAnomaly = (id: string): void => {
    setItems((current) => current.map((item) => item.id === id
      ? { ...item, anomalies: item.anomalies.length > 0 ? [] : ['人工标记：曲线形态需要复核'] }
      : item))
    const item = items.find((candidate) => candidate.id === id)
    setAnnouncement(item?.anomalies.length ? `已移除 ${item.sourceName} 的异常标记` : `已标记 ${item?.sourceName} 为异常`)
  }

  const toggleExcluded = (id: string): void => {
    setItems((current) => current.map((item) => item.id === id ? { ...item, excluded: !item.excluded } : item))
    const item = items.find((candidate) => candidate.id === id)
    setAnnouncement(item?.excluded ? `${item.sourceName} 已恢复到当前导出` : `${item?.sourceName} 已排除当前导出`)
  }

  const toggleUniformRange = (): void => {
    setUniformRange((current) => !current)
    setAnnouncement(uniformRange ? '已恢复各图独立坐标范围' : `已临时统一 ${selectedIds.length} 张图的坐标范围`)
  }

  const toggleOverlay = (): void => {
    setOverlayMode((current) => !current)
    setSavedObject('')
    setAnnouncement(overlayMode ? '已返回批次图集' : `正在临时叠加 ${comparableItems.length} 条同构曲线`)
  }

  const saveAsNewChart = (): void => {
    setSavedObject('CHART-003')
    setAnnouncement('已创建正式图表 CHART-003，原批次图表版本未改变')
  }

  return (
    <main className="batch-inspector">
      <header className="batch-inspector__header">
        <button className="back-button" type="button" onClick={onClose}><ArrowLeft size={16} />返回对话</button>
        <div className="batch-inspector__title">
          <span>温度响应实验 · B-024</span>
          <h1>基础批次检查</h1>
        </div>
        <div className="batch-inspector__summary" aria-label="批次状态摘要">
          <span><strong>4</strong> 来源</span>
          <span className="is-success"><strong>2</strong> 通过</span>
          <span className="is-warning"><strong>1</strong> 科研警告</span>
          <span className="is-danger"><strong>1</strong> 失败</span>
        </div>
        {overlayMode && (
          <button className="primary-button" type="button" onClick={saveAsNewChart} disabled={Boolean(savedObject)}>
            {savedObject ? <Check size={15} /> : <FilePlus2 size={15} />}{savedObject ? '已保存为新图' : '保存为新图'}
          </button>
        )}
      </header>

      <div className="batch-inspector__filters">
        <label className="batch-search">
          <Search size={15} />
          <span className="sr-only">搜索来源名或元数据</span>
          <input value={query} onChange={(event) => { setQuery(event.target.value); setCarouselIndex(0) }} placeholder="搜索来源名、温度、条件或重复编号" />
          {query && <button type="button" onClick={() => setQuery('')} aria-label="清空批次搜索"><X size={14} /></button>}
        </label>

        <div className="batch-view-switch" role="group" aria-label="图集视图">
          <button type="button" aria-label="网格视图" aria-pressed={view === 'grid'} onClick={() => setView('grid')}><Grid2X2 size={15} /></button>
          <button type="button" aria-label="列表视图" aria-pressed={view === 'list'} onClick={() => setView('list')}><List size={15} /></button>
          <button type="button" aria-label="大图轮播视图" aria-pressed={view === 'carousel'} onClick={() => setView('carousel')}><Columns3 size={15} /></button>
        </div>

        <label className="batch-filter-select"><span>状态</span><select aria-label="按状态筛选" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as BatchStatusFilter); setCarouselIndex(0) }}>
          <option value="all">全部状态</option><option value="success">检查通过</option><option value="warning">科研警告</option><option value="failed">失败</option>
        </select></label>
        <label className="batch-filter-select"><span>标记</span><select aria-label="按检查标记筛选" value={issueFilter} onChange={(event) => { setIssueFilter(event.target.value as BatchIssueFilter); setCarouselIndex(0) }}>
          <option value="all">全部标记</option><option value="anomaly">异常标记</option><option value="scientific-warning">科研警告</option><option value="excluded">已排除导出</option>
        </select></label>
        <label className="batch-filter-select"><span>排序</span><select aria-label="批次排序" value={sortMode} onChange={(event) => { setSortMode(event.target.value as BatchSortMode); setCarouselIndex(0) }}>
          <option value="source-asc">来源名 A–Z</option><option value="updated-desc">最近更新</option><option value="temperature-asc">温度升序</option><option value="status">状态优先</option>
        </select></label>
      </div>

      <div className="batch-selection-bar">
        <div className="batch-scope">
          <span>作用范围</span>
          <strong>{selectedIds.length > 0 ? `当前选择 · ${selectedIds.length} 张` : '当前图'}</strong>
          <small>所有临时检查操作跟随当前选择</small>
        </div>
        <button type="button" onClick={() => applySelection(visibleItems.map((item) => item.id))}>选择筛选结果</button>
        <button type="button" onClick={() => applySelection([])} disabled={selectedIds.length === 0}>清除选择</button>
        <span className="selection-divider" />
        <button className={uniformRange ? 'is-active' : ''} type="button" aria-pressed={uniformRange} onClick={toggleUniformRange} disabled={selectedIds.length < 2}><Maximize2 size={15} />统一坐标范围</button>
        <button className={overlayMode ? 'is-active' : ''} type="button" aria-pressed={overlayMode} onClick={toggleOverlay} disabled={comparableItems.length < 2}><Combine size={15} />叠加比较</button>
        {temporaryState && <span className="temporary-state"><RotateCcw size={14} />临时检查状态，不会生成图表版本</span>}
        <span className="visible-count">显示 {visibleItems.length} / {items.length}</span>
      </div>

      <div className={`batch-inspector__body${advancedOpen ? ' has-advanced-panel' : ''}`}>
        {savedObject && (
          <div className="batch-save-result" role="status"><CircleCheck size={17} /><span><strong>已创建正式图表 {savedObject}</strong>叠加状态作为新对象保存，批次内原图与版本均未改变。</span></div>
        )}

        {overlayMode ? (
          <OverlayComparison
            items={comparableItems}
            uniformRange={uniformRange}
            showConfidence={showConfidence}
            showDifference={showDifference}
            alignment={alignment}
            normalization={normalization}
            onToggleAdvanced={() => setAdvancedOpen((open) => !open)}
            advancedOpen={advancedOpen}
          />
        ) : visibleItems.length === 0 ? (
          <div className="batch-empty-results"><Search size={24} /><h2>没有匹配的批次结果</h2><p>调整状态、检查标记或搜索关键词。</p><button type="button" onClick={() => { setQuery(''); setStatusFilter('all'); setIssueFilter('all') }}>清除筛选</button></div>
        ) : view === 'grid' ? (
          <GridView items={visibleItems} selectedIds={selectedIds} uniformRange={uniformRange} onToggleSelection={toggleSelection} onToggleAnomaly={toggleAnomaly} onToggleExcluded={toggleExcluded} />
        ) : view === 'list' ? (
          <ListView items={visibleItems} selectedIds={selectedIds} uniformRange={uniformRange} onToggleSelection={toggleSelection} onToggleAnomaly={toggleAnomaly} onToggleExcluded={toggleExcluded} />
        ) : (
          <CarouselView items={visibleItems} current={currentCarouselItem} index={visibleItems.indexOf(currentCarouselItem)} selectedIds={selectedIds} uniformRange={uniformRange} onIndexChange={setCarouselIndex} onToggleSelection={toggleSelection} onToggleAnomaly={toggleAnomaly} onToggleExcluded={toggleExcluded} />
        )}

        {overlayMode && advancedOpen && (
          <aside className="advanced-comparison" aria-label="高级比较参数">
            <header><div><strong>高级比较</strong><span>仅影响当前临时视图</span></div><button className="icon-button" type="button" onClick={() => setAdvancedOpen(false)} aria-label="关闭高级比较"><X size={17} /></button></header>
            <label><span>时间对齐</span><select value={alignment} onChange={(event) => setAlignment(event.target.value)}><option value="time">按 time 原值</option><option value="start">首个观测对齐</option><option value="peak">峰值位置对齐</option></select></label>
            <label><span>数值处理</span><select value={normalization} onChange={(event) => setNormalization(event.target.value)}><option value="raw">原始值</option><option value="baseline">起点归一化</option><option value="zscore">组内 Z-score</option></select></label>
            <label><span>参考曲线</span><select value={referenceId} onChange={(event) => setReferenceId(event.target.value)}>{comparableItems.map((item) => <option value={item.id} key={item.id}>{item.sourceName}</option>)}</select></label>
            <label className="advanced-check"><input type="checkbox" checked={showConfidence} onChange={(event) => setShowConfidence(event.target.checked)} /><span>显示置信区间</span></label>
            <label className="advanced-check"><input type="checkbox" checked={showDifference} onChange={(event) => setShowDifference(event.target.checked)} /><span>显示与参考曲线的差值</span></label>
            <section><strong>比较约束</strong><p>仅叠加 K02 线点图，X/Y 字段、单位与时间采样点一致。失败项不会进入比较。</p></section>
          </aside>
        )}
      </div>

      <div className="sr-only" role="status" aria-live="polite">{announcement}</div>
    </main>
  )
}

interface ViewProps {
  items: BatchInspectionItem[]
  selectedIds: string[]
  uniformRange: boolean
  onToggleSelection: (id: string) => void
  onToggleAnomaly: (id: string) => void
  onToggleExcluded: (id: string) => void
}

function GridView(props: ViewProps): React.JSX.Element {
  return (
    <section className={`batch-check-grid${props.uniformRange ? ' has-uniform-range' : ''}`} aria-label="批次网格视图">
      {props.items.map((item) => <BatchGridCard item={item} key={item.id} {...props} />)}
    </section>
  )
}

function BatchGridCard({ item, selectedIds, uniformRange, onToggleSelection, onToggleAnomaly, onToggleExcluded }: ViewProps & { item: BatchInspectionItem }): React.JSX.Element {
  const selected = selectedIds.includes(item.id)
  return (
    <article className={`batch-check-card${selected ? ' is-selected' : ''}${item.status === 'failed' ? ' is-failed' : ''}`}>
      <header>
        <label><input type="checkbox" checked={selected} onChange={() => onToggleSelection(item.id)} aria-label={`选择 ${item.sourceName}`} /><span>{item.sourceName}</span></label>
        <span className={`batch-check-status batch-check-status--${item.status}`}>{item.status === 'warning' && <TriangleAlert size={12} />}{statusLabels[item.status]}</span>
      </header>
      <div className="batch-card-plot">
        {item.status === 'failed' ? <FailedBatchPlot item={item} /> : <BatchPlot title={item.title} series={item.series} />}
        {uniformRange && item.status !== 'failed' && <span className="range-badge">统一 X/Y</span>}
      </div>
      <div className="batch-card-metadata"><span>{item.temperature} °C</span><span>{item.condition}</span><span>{item.replicate}</span><time>{item.updatedAt}</time></div>
      {(item.anomalies.length > 0 || item.scientificWarnings.length > 0) && <div className="batch-card-issues">{item.anomalies.map((issue) => <span className="is-anomaly" key={issue}><Flag size={11} />{issue}</span>)}{item.scientificWarnings.map((issue) => <span className="is-warning" key={issue}><TriangleAlert size={11} />{issue}</span>)}</div>}
      <footer><span>{item.version}</span><button type="button" className={item.anomalies.length ? 'is-active' : ''} onClick={() => onToggleAnomaly(item.id)} aria-label={`${item.anomalies.length ? '移除异常标记' : '标记异常'} ${item.sourceName}`}><Flag size={14} />异常</button><button type="button" className={item.excluded ? 'is-active' : ''} onClick={() => onToggleExcluded(item.id)} aria-label={`${item.excluded ? '恢复当前导出' : '排除当前导出'} ${item.sourceName}`}>{item.excluded ? <EyeOff size={14} /> : <Eye size={14} />}{item.excluded ? '已排除' : '参与导出'}</button></footer>
    </article>
  )
}

function ListView(props: ViewProps): React.JSX.Element {
  return (
    <div className="batch-check-list" role="table" aria-label="批次列表视图">
      <div className="batch-list-heading" role="row"><span role="columnheader">选择</span><span role="columnheader">预览</span><span role="columnheader">来源与元数据</span><span role="columnheader">状态</span><span role="columnheader">更新时间</span><span role="columnheader">检查操作</span></div>
      {props.items.map((item) => (
        <div className={`batch-list-row${props.selectedIds.includes(item.id) ? ' is-selected' : ''}`} role="row" key={item.id}>
          <span role="cell"><input type="checkbox" checked={props.selectedIds.includes(item.id)} onChange={() => props.onToggleSelection(item.id)} aria-label={`选择 ${item.sourceName}`} /></span>
          <span className="batch-list-preview" role="cell">{item.status === 'failed' ? <TriangleAlert size={21} /> : <BatchPlot title={item.title} series={item.series} compact />}</span>
          <span className="batch-list-source" role="cell"><strong>{item.sourceName}</strong><small>{item.temperature} °C · {item.condition} · {item.replicate}{props.uniformRange ? ' · 统一 X/Y' : ''}</small></span>
          <span role="cell"><span className={`batch-check-status batch-check-status--${item.status}`}>{statusLabels[item.status]}</span>{item.anomalies.length > 0 && <small className="list-issue"><Flag size={10} />异常</small>}{item.excluded && <small className="list-issue"><EyeOff size={10} />已排除</small>}</span>
          <time role="cell">{item.updatedAt}</time>
          <span className="batch-list-actions" role="cell"><button type="button" onClick={() => props.onToggleAnomaly(item.id)} aria-label={`${item.anomalies.length ? '移除异常标记' : '标记异常'} ${item.sourceName}`}><Flag size={14} /></button><button type="button" onClick={() => props.onToggleExcluded(item.id)} aria-label={`${item.excluded ? '恢复当前导出' : '排除当前导出'} ${item.sourceName}`}>{item.excluded ? <EyeOff size={14} /> : <Eye size={14} />}</button></span>
        </div>
      ))}
    </div>
  )
}

interface CarouselViewProps extends ViewProps {
  current: BatchInspectionItem
  index: number
  onIndexChange: (index: number) => void
}

function CarouselView({ items, current, index, selectedIds, uniformRange, onIndexChange, onToggleSelection, onToggleAnomaly, onToggleExcluded }: CarouselViewProps): React.JSX.Element {
  const previous = (): void => onIndexChange(index <= 0 ? items.length - 1 : index - 1)
  const next = (): void => onIndexChange(index >= items.length - 1 ? 0 : index + 1)
  return (
    <section className="batch-carousel" aria-label="批次大图轮播视图">
      <div className="batch-carousel__stage">
        <button className="carousel-arrow carousel-arrow--left" type="button" onClick={previous} aria-label="上一张图"><ChevronLeft size={22} /></button>
        <article className="carousel-paper">
          {current.status === 'failed' ? <FailedBatchPlot item={current} /> : <BatchPlot title={current.title} series={current.series} />}
          {uniformRange && current.status !== 'failed' && <span className="range-badge">统一 X/Y</span>}
        </article>
        <button className="carousel-arrow carousel-arrow--right" type="button" onClick={next} aria-label="下一张图"><ChevronRight size={22} /></button>
        <aside className="carousel-detail">
          <span>{index + 1} / {items.length}</span><h2>{current.sourceName}</h2><p>{current.temperature} °C · {current.condition} · {current.replicate}</p>
          <span className={`batch-check-status batch-check-status--${current.status}`}>{statusLabels[current.status]}</span>
          {current.failureReason && <p className="is-danger">{current.failureReason}</p>}
          {current.anomalies.map((issue) => <p className="is-danger" key={issue}><Flag size={12} />{issue}</p>)}
          {current.scientificWarnings.map((issue) => <p className="is-warning" key={issue}><TriangleAlert size={12} />{issue}</p>)}
          <label><input type="checkbox" checked={selectedIds.includes(current.id)} onChange={() => onToggleSelection(current.id)} />纳入当前选择</label>
          <button type="button" onClick={() => onToggleAnomaly(current.id)}><Flag size={14} />{current.anomalies.length ? '移除异常标记' : '标记异常'}</button>
          <button type="button" onClick={() => onToggleExcluded(current.id)}>{current.excluded ? <Eye size={14} /> : <EyeOff size={14} />}{current.excluded ? '恢复当前导出' : '排除当前导出'}</button>
        </aside>
      </div>
      <div className="batch-carousel__strip">{items.map((item, itemIndex) => <button type="button" className={item.id === current.id ? 'is-active' : ''} key={item.id} onClick={() => onIndexChange(itemIndex)} aria-label={`查看 ${item.sourceName}`}><span>{item.status === 'failed' ? <TriangleAlert size={18} /> : <BatchPlot title={item.title} series={item.series} compact />}</span><small>{item.sourceName}</small></button>)}</div>
    </section>
  )
}

function FailedBatchPlot({ item }: { item: BatchInspectionItem }): React.JSX.Element {
  return <div className="batch-failed-plot" role="status"><TriangleAlert size={26} /><strong>未生成图表</strong><span>{item.failureReason}</span><button type="button"><RotateCcw size={13} />修复后重试</button></div>
}

interface OverlayComparisonProps {
  items: BatchInspectionItem[]
  uniformRange: boolean
  showConfidence: boolean
  showDifference: boolean
  alignment: string
  normalization: string
  advancedOpen: boolean
  onToggleAdvanced: () => void
}

function OverlayComparison({ items, uniformRange, showConfidence, showDifference, alignment, normalization, advancedOpen, onToggleAdvanced }: OverlayComparisonProps): React.JSX.Element {
  const paths = [
    'M74 286C130 274 153 232 201 237S276 171 331 190S430 111 526 126S615 82 665 88',
    'M74 279C123 262 165 199 205 214S279 140 336 158S431 86 527 104S617 62 665 75',
    'M74 289C139 281 168 245 215 249S294 188 349 200S446 135 539 146S620 105 665 111',
  ]
  return (
    <section className="overlay-comparison" aria-labelledby="overlay-comparison-title">
      <header><div><span>同构曲线 · {items.length} 项</span><h2 id="overlay-comparison-title">临时叠加比较</h2></div><p><RotateCcw size={14} />未保存，不生成版本或正式对象</p><button type="button" className={advancedOpen ? 'is-active' : ''} aria-pressed={advancedOpen} onClick={onToggleAdvanced}><Settings2 size={15} />高级比较</button></header>
      <div className="overlay-chart-wrap">
        <svg className="overlay-chart" viewBox="0 0 720 370" role="img" aria-label={`${items.length} 条温度响应曲线叠加比较`}>
          <rect width="720" height="370" className="overlay-paper" />
          <g className="overlay-grid"><path d="M74 42V310H680M74 256H680M74 202H680M74 148H680M74 94H680" /></g>
          {showConfidence && items.map((item, index) => <path className={`overlay-band overlay-band--${index}`} key={`band-${item.id}`} d={`${paths[index]}L665 ${105 + index * 13}C615 ${95 + index * 10} 530 ${140 + index * 16} 526 ${143 + index * 16}S430 ${130 + index * 21} 331 ${207 + index * 17}S201 ${255 + index * 9} 74 ${300 + index * 2}Z`} />)}
          {items.map((item, index) => <path className={`overlay-line overlay-line--${index}`} key={item.id} d={paths[index]} />)}
          <text x="330" y="350">Time (min)</text><text transform="translate(20 240) rotate(-90)">Fluorescence (a.u.)</text>
        </svg>
        <div className="overlay-legend">{items.map((item, index) => <span key={item.id}><i className={`overlay-key overlay-key--${index}`} />{item.sourceName}{item.scientificWarnings.length > 0 && <TriangleAlert size={11} />}</span>)}</div>
        <div className="overlay-mode-summary"><span>{uniformRange ? '坐标范围：已统一' : '坐标范围：按共同数据域'}</span><span>对齐：{alignment === 'time' ? 'time 原值' : alignment === 'start' ? '首个观测' : '峰值位置'}</span><span>数值：{normalization === 'raw' ? '原始值' : normalization === 'baseline' ? '起点归一化' : '组内 Z-score'}</span>{showDifference && <span>显示参考差值</span>}</div>
      </div>
      <div className="comparison-metrics" role="table" aria-label="曲线比较指标">
        <div role="row"><span role="columnheader">来源</span><span role="columnheader">末端值</span><span role="columnheader">最大斜率</span><span role="columnheader">AUC</span><span role="columnheader">检查</span></div>
        {items.map((item, index) => <div role="row" key={item.id}><span role="cell"><i className={`overlay-key overlay-key--${index}`} />{item.sourceName}</span><span role="cell">{[0.842, 0.917, 0.796][index]?.toFixed(3)}</span><span role="cell">{[0.031, 0.044, 0.027][index]?.toFixed(3)} /min</span><span role="cell">{[31.8, 35.4, 29.7][index]?.toFixed(1)}</span><span role="cell">{item.scientificWarnings.length ? '科研警告' : '通过'}</span></div>)}
      </div>
    </section>
  )
}
