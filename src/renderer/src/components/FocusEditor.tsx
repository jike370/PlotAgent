import { useRef, useState } from 'react'
import {
  AlignCenter,
  ArrowLeft,
  ArrowUpRight,
  Baseline,
  Check,
  ChevronDown,
  Circle,
  Columns2,
  Download,
  Eye,
  FileImage,
  FileType2,
  Grid2X2,
  History,
  Image,
  Layers3,
  Link2,
  Lock,
  Maximize2,
  MousePointer2,
  Move,
  Redo2,
  RectangleHorizontal,
  RotateCcw,
  SlidersHorizontal,
  Sparkles,
  Type,
  Undo2,
  X,
} from 'lucide-react'

import type { ScopeMode } from './ConversationWorkspace'
import { BatchPlot } from './PlotVisuals'

interface FocusEditorProps {
  initialIndex: number
  plot?: { title: string; plotId: string; version: number; previewUrl?: string }
  onClose: () => void
}

const focusItems = [
  { title: 'Sample A · 25 °C', file: 'sample_A_25C.csv', series: 'control' as const },
  { title: 'Sample B · 37 °C', file: 'sample_B_37C.csv', series: 'treated' as const },
  { title: 'Sample C · 42 °C', file: 'sample_C_42C.csv', series: 'recovery' as const },
]

interface Position {
  x: number
  y: number
}

export function FocusEditor({ initialIndex, plot, onClose }: FocusEditorProps): React.JSX.Element {
  const [activeIndex, setActiveIndex] = useState(Math.min(initialIndex, 2))
  const [selected, setSelected] = useState<number[]>([Math.min(initialIndex, 2)])
  const [scope, setScope] = useState<ScopeMode>('current')
  const [panelOpen, setPanelOpen] = useState(false)
  const [compareOpen, setCompareOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [legendPosition, setLegendPosition] = useState<Position>({ x: 68, y: 17 })
  const [annotationPosition, setAnnotationPosition] = useState<Position>({ x: 53, y: 37 })
  const dragStart = useRef<{ pointerX: number; pointerY: number; position: Position; type: 'legend' | 'annotation' } | null>(null)

  const startDrag = (event: React.PointerEvent<HTMLButtonElement>, type: 'legend' | 'annotation'): void => {
    event.currentTarget.setPointerCapture(event.pointerId)
    dragStart.current = {
      pointerX: event.clientX,
      pointerY: event.clientY,
      position: type === 'legend' ? legendPosition : annotationPosition,
      type,
    }
  }

  const moveDrag = (event: React.PointerEvent<HTMLButtonElement>): void => {
    if (!dragStart.current) return
    const next = {
      x: Math.max(4, Math.min(86, dragStart.current.position.x + (event.clientX - dragStart.current.pointerX) / 8)),
      y: Math.max(5, Math.min(78, dragStart.current.position.y + (event.clientY - dragStart.current.pointerY) / 6)),
    }
    if (dragStart.current.type === 'legend') setLegendPosition(next)
    else setAnnotationPosition(next)
  }

  const keyboardMove = (event: React.KeyboardEvent<HTMLButtonElement>, type: 'legend' | 'annotation'): void => {
    const delta = event.shiftKey ? 3 : 1
    const movement = {
      ArrowLeft: { x: -delta, y: 0 },
      ArrowRight: { x: delta, y: 0 },
      ArrowUp: { x: 0, y: -delta },
      ArrowDown: { x: 0, y: delta },
    }[event.key]
    if (!movement) return
    event.preventDefault()
    const update = (current: Position): Position => ({ x: current.x + movement.x, y: current.y + movement.y })
    if (type === 'legend') setLegendPosition(update)
    else setAnnotationPosition(update)
  }

  const availableItems = plot ? [{ title: plot.title, file: plot.plotId, series: 'control' as const }] : focusItems
  const active = availableItems[Math.min(activeIndex, availableItems.length - 1)]

  return (
    <div className="focus-editor" role="dialog" aria-modal="true" aria-label="聚焦编辑">
      <header className="focus-header">
        <button className="back-button" type="button" onClick={onClose}><ArrowLeft size={18} />返回对话</button>
        <div className="focus-title">
          <h2>{active.title}</h2>
          <span>{plot ? `${plot.plotId} · v${plot.version}` : '线点图 · v3'}</span>
        </div>
        <div className="focus-history-tools">
          <button type="button" aria-label="撤销"><Undo2 size={17} /></button>
          <button type="button" aria-label="重做" disabled><Redo2 size={17} /></button>
          <span className="toolbar-divider" />
          <button className={compareOpen ? 'is-active' : ''} type="button" onClick={() => setCompareOpen((open) => !open)}><Columns2 size={16} />比较版本</button>
          <button type="button"><History size={16} />版本 v3<ChevronDown size={14} /></button>
        </div>
        <div className="focus-header-actions">
          <button className={panelOpen ? 'is-active' : ''} type="button" onClick={() => setPanelOpen((open) => !open)}><SlidersHorizontal size={16} />参数</button>
          <div className="export-anchor">
            <button className="primary-button" type="button" onClick={() => setExportOpen((open) => !open)} aria-expanded={exportOpen}><Download size={16} />导出<ChevronDown size={14} /></button>
            {exportOpen && (
              <div className="export-menu" role="menu">
                <button role="menuitem" type="button"><FileImage size={16} /><span><strong>导出 PNG</strong><small>183 mm · 300 DPI</small></span></button>
                <button role="menuitem" type="button"><FileType2 size={16} /><span><strong>导出 SVG</strong><small>保留矢量对象</small></span></button>
                <button role="menuitem" type="button" disabled><Layers3 size={16} /><span><strong>导出 .opju</strong><small>Origin 当前不可用</small></span></button>
              </div>
            )}
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭聚焦编辑"><X size={19} /></button>
        </div>
      </header>

      <div className={`focus-body${panelOpen ? ' has-panel' : ''}`}>
        <aside className="annotation-toolbar" aria-label="标注工具">
          <button className="is-active" type="button" aria-label="选择工具"><MousePointer2 size={17} /></button>
          <button type="button" aria-label="文本标注"><Type size={17} /></button>
          <button type="button" aria-label="箭头标注"><ArrowUpRight size={17} /></button>
          <button type="button" aria-label="矩形标注"><RectangleHorizontal size={17} /></button>
          <button type="button" aria-label="参考线"><Baseline size={17} /></button>
          <button type="button" aria-label="圆形标注"><Circle size={17} /></button>
          <span />
          <button type="button" aria-label="显示网格"><Grid2X2 size={17} /></button>
          <button type="button" aria-label="对齐"><AlignCenter size={17} /></button>
        </aside>

        <main className="focus-stage">
          <div className="stage-toolbar">
            <div className="scope-control" aria-label="编辑作用范围">
              <span>作用范围</span>
              {([
                ['current', '当前图'],
                ['selected', `选中图 ${selected.length}`],
                ['batch', '整个批次'],
              ] as [ScopeMode, string][]).map(([value, label]) => <button key={value} type="button" className={scope === value ? 'is-active' : ''} onClick={() => setScope(value)}>{label}</button>)}
            </div>
            <div className="stage-meta">
              <span><Lock size={13} />原始数据只读</span>
              <span><Eye size={13} />预览 2,406 / 2,406 点</span>
              <button type="button"><Maximize2 size={14} />适合窗口</button>
            </div>
          </div>

          <div className={`plot-stage${compareOpen ? ' is-comparing' : ''}`}>
            {compareOpen && (
              <div className="compare-label compare-label--left"><span>v2</span>修改前</div>
            )}
            <div className="canvas-paper canvas-paper--previous" aria-hidden={!compareOpen}>
              {compareOpen && (plot?.previewUrl ? <img className="focus-real-preview" src={plot.previewUrl} alt={`${plot.title} 上一版本预览`} /> : <BatchPlot title={active.title} series={active.series} />)}
            </div>
            <div className="canvas-paper canvas-paper--current">
              {plot?.previewUrl ? <img className="focus-real-preview" src={plot.previewUrl} alt={`${plot.title} Core 预览`} /> : <BatchPlot title={active.title} series={active.series} />}
              <button
                className="draggable-legend"
                type="button"
                style={{ left: `${legendPosition.x}%`, top: `${legendPosition.y}%` }}
                onPointerDown={(event) => startDrag(event, 'legend')}
                onPointerMove={moveDrag}
                onPointerUp={() => { dragStart.current = null }}
                onKeyDown={(event) => keyboardMove(event, 'legend')}
                aria-label="图例，可拖动或用方向键移动"
              >
                <Move size={12} aria-hidden="true" />
                <span><i className="legend-line legend-line--blue" />Control</span>
                <span><i className="legend-line legend-line--amber" />Treated</span>
              </button>
              <button
                className="draggable-annotation"
                type="button"
                style={{ left: `${annotationPosition.x}%`, top: `${annotationPosition.y}%` }}
                onPointerDown={(event) => startDrag(event, 'annotation')}
                onPointerMove={moveDrag}
                onPointerUp={() => { dragStart.current = null }}
                onKeyDown={(event) => keyboardMove(event, 'annotation')}
                aria-label="峰值标注，可拖动或用方向键移动"
              >
                <span>峰值区</span><ArrowUpRight size={14} />
              </button>
            </div>
            {compareOpen && (
              <div className="compare-label compare-label--right"><span>v3</span>当前版本</div>
            )}
          </div>
          <div className="canvas-status"><Sparkles size={13} /><span>拖动图例或标注可立即创建可撤销版本</span><span className="zoom-status">100%</span></div>
        </main>

        {panelOpen && (
          <aside className="parameter-panel" aria-label="图形参数">
            <header><div><strong>图形参数</strong><span>{scope === 'current' ? active.title : scope === 'selected' ? `${selected.length} 张选中图` : '批次 B-024'}</span></div><button type="button" onClick={() => setPanelOpen(false)} aria-label="关闭参数面板"><X size={17} /></button></header>
            <div className="parameter-tabs"><button className="is-active" type="button">样式</button><button type="button">坐标轴</button><button type="button">图例</button><button type="button">数据</button></div>
            <section className="parameter-section">
              <h3>线与标记</h3>
              <label><span>线宽</span><div className="unit-input"><input type="number" defaultValue="0.8" step="0.1" /><span>pt</span></div></label>
              <label><span>标记大小</span><div className="unit-input"><input type="number" defaultValue="4.5" step="0.5" /><span>pt</span></div></label>
              <label><span>连接方式</span><select defaultValue="straight"><option value="straight">直线</option><option value="spline">样条</option><option value="step">阶梯</option></select></label>
            </section>
            <section className="parameter-section">
              <h3>画布与发表规格</h3>
              <label><span>规格</span><select defaultValue="nature"><option value="nature">Nature · 双栏</option><option value="general">通用双栏</option></select></label>
              <label><span>宽度</span><div className="unit-input"><input type="number" defaultValue="183" /><span>mm</span></div></label>
              <label><span>DPI</span><div className="unit-input"><input type="number" defaultValue="300" /><span>dpi</span></div></label>
            </section>
            <section className="parameter-section parameter-section--status">
              <h3>校验</h3>
              <p><Check size={14} />最小线宽符合规格</p>
              <p><Check size={14} />字体已嵌入</p>
              <p><Check size={14} />色彩不只依赖颜色区分</p>
            </section>
            <footer><button type="button"><RotateCcw size={14} />恢复批次样式</button></footer>
          </aside>
        )}
      </div>

      <footer className="thumbnail-dock">
        <div className="thumbnail-dock__label"><Image size={15} /><span>批次 B-024</span><strong>{selected.length} 张已选</strong></div>
        <div className="thumbnail-strip">
          {availableItems.map((item, index) => (
            <article className={`${activeIndex === index ? 'is-active' : ''}${selected.includes(index) ? ' is-selected' : ''}`} key={item.file}>
              <button className="thumb-open" type="button" onClick={() => setActiveIndex(index)} aria-label={`打开 ${item.title}`}>{plot?.previewUrl ? <img className="focus-real-thumb" src={plot.previewUrl} alt="" /> : <BatchPlot compact title={item.title} series={item.series} />}</button>
              <label><input type="checkbox" checked={selected.includes(index)} onChange={() => setSelected((current) => current.includes(index) ? current.filter((value) => value !== index) : [...current, index])} /><span>{index + 1}</span></label>
              <small>{item.file.replace('sample_', '').replace('.csv', '')}</small>
            </article>
          ))}
          <article className="is-failed"><div><RotateCcw size={18} /><span>待重试</span></div><small>D_50C</small></article>
        </div>
        <button className="dock-link" type="button"><Link2 size={15} />应用到选中图</button>
      </footer>
    </div>
  )
}
