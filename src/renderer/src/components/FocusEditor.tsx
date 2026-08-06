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
import { SpecialistEditor } from './SpecialistEditor'
import type { JsonValue } from '../../../shared/desktop-contract'
import type { ProductPlot } from '../data/productState'
import {
  chartProductMetadata,
  paletteCatalog,
  symbolCatalog,
} from '../data/chartCatalog'

interface FocusEditorProps {
  initialIndex: number
  plot?: ProductPlot & { title: string }
  onPatch?: (patch: JsonValue) => Promise<void>
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

type ParameterTab = 'general' | 'style' | 'specialist' | 'axis' | 'legend' | 'annotation'
type AnnotationKind = 'text' | 'reference_line' | 'reference_band'
type AnnotationAxis = 'x' | 'y'
type EditState = 'idle' | 'saving' | 'saved' | 'error'

const symbolNames: Record<string, string> = {
  square: '方形', circle: '圆形', triangle_up: '上三角', triangle_down: '下三角',
  diamond: '菱形', plus: '加号', cross: '叉号', triangle_left: '左三角',
  triangle_right: '右三角', hexagon: '六边形', star: '星形', pentagon: '五边形',
}

export function FocusEditor({ initialIndex, plot, onPatch, onClose }: FocusEditorProps): React.JSX.Element {
  const initialSeriesStyle = plot?.seriesStyles[0]?.style ?? plot?.style
  const initialAxisState = plot?.axisStates.y ?? plot?.axisStates.x
  const [activeIndex, setActiveIndex] = useState(Math.min(initialIndex, 2))
  const [selected, setSelected] = useState<number[]>([Math.min(initialIndex, 2)])
  const [scope, setScope] = useState<ScopeMode>('current')
  const [panelOpen, setPanelOpen] = useState(false)
  const [parameterTab, setParameterTab] = useState<ParameterTab>('style')
  const [compareOpen, setCompareOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [editState, setEditState] = useState<EditState>('idle')
  const [editMessage, setEditMessage] = useState('')
  const [seriesTargetIndex, setSeriesTargetIndex] = useState(0)
  const [color, setColor] = useState(initialSeriesStyle?.color ?? '#2A6FDB')
  const [lineWidth, setLineWidth] = useState(initialSeriesStyle?.lineWidthPt ?? 0.8)
  const [lineStyle, setLineStyle] = useState(initialSeriesStyle?.lineStyle ?? 'solid')
  const [markerSize, setMarkerSize] = useState(initialSeriesStyle?.markerSizePt ?? 4.5)
  const [symbolShape, setSymbolShape] = useState(initialSeriesStyle?.symbolShape ?? 'circle')
  const [symbolInterior, setSymbolInterior] = useState(initialSeriesStyle?.symbolInterior ?? 'solid')
  const [paletteId, setPaletteId] = useState(initialSeriesStyle?.paletteId ?? 'Viridis')
  const [paletteReverse, setPaletteReverse] = useState(initialSeriesStyle?.paletteReverse ?? false)
  const [categoryName, setCategoryName] = useState('')
  const [categoryColor, setCategoryColor] = useState('#2A6FDB')
  const [axisTarget, setAxisTarget] = useState<'x' | 'y' | 'yRight'>('y')
  const [axisScale, setAxisScale] = useState(initialAxisState?.scale ?? 'linear')
  const [axisLabel, setAxisLabel] = useState(initialAxisState?.label ?? '')
  const [axisMinimum, setAxisMinimum] = useState(initialAxisState?.minimum?.toString() ?? '')
  const [axisMaximum, setAxisMaximum] = useState(initialAxisState?.maximum?.toString() ?? '')
  const [axisReverse, setAxisReverse] = useState(initialAxisState?.reverse ?? false)
  const [axisMajorInterval, setAxisMajorInterval] = useState(initialAxisState?.majorInterval?.toString() ?? '')
  const [axisNumberFormat, setAxisNumberFormat] = useState(initialAxisState?.numberFormat ?? 'auto')
  const [axisDecimalPlaces, setAxisDecimalPlaces] = useState(initialAxisState?.decimalPlaces ?? 2)
  const [plotTitle, setPlotTitle] = useState(plot?.plotTitle ?? '')
  const [fontSizePt, setFontSizePt] = useState(plot?.fontSizePt ?? 9)
  const [annotationKind, setAnnotationKind] = useState<AnnotationKind>('text')
  const [annotationAxis, setAnnotationAxis] = useState<AnnotationAxis>('y')
  const [annotationText, setAnnotationText] = useState('')
  const [annotationStart, setAnnotationStart] = useState('')
  const [annotationEnd, setAnnotationEnd] = useState('')
  const [legendVisible, setLegendVisible] = useState(plot?.style.legendVisible ?? true)
  const [legendPlacement, setLegendPlacement] = useState(plot?.style.legendPlacement ?? 'inside')
  const [canvasWidth, setCanvasWidth] = useState(plot?.canvasSizeMm.width ?? 183)
  const [canvasHeight, setCanvasHeight] = useState(plot?.canvasSizeMm.height ?? 120)
  const [legendPosition, setLegendPosition] = useState<Position>({ x: 68, y: 17 })
  const [annotationPosition, setAnnotationPosition] = useState<Position>({ x: 53, y: 37 })
  const dragStart = useRef<{ pointerX: number; pointerY: number; position: Position; type: 'legend' | 'annotation' } | null>(null)

  const selectSeries = (index: number): void => {
    if (!plot) return
    const validIndex = Math.min(index, Math.max(0, plot.seriesIds.length - 1))
    const seriesStyle = plot.seriesStyles[validIndex]?.style ?? plot.style
    setSeriesTargetIndex(validIndex)
    setColor(seriesStyle.color ?? '#2A6FDB')
    setLineWidth(seriesStyle.lineWidthPt ?? 0.8)
    setLineStyle(seriesStyle.lineStyle ?? 'solid')
    setMarkerSize(seriesStyle.markerSizePt ?? 4.5)
    setSymbolShape(seriesStyle.symbolShape ?? 'circle')
    setSymbolInterior(seriesStyle.symbolInterior ?? 'solid')
    setPaletteId(seriesStyle.paletteId ?? 'Viridis')
    setPaletteReverse(seriesStyle.paletteReverse ?? false)
  }

  const selectAxis = (target: 'x' | 'y' | 'yRight'): void => {
    const axisState = plot?.axisStates[target]
    setAxisTarget(target)
    setAxisScale(axisState?.scale ?? 'linear')
    setAxisLabel(axisState?.label ?? '')
    setAxisMinimum(axisState?.minimum?.toString() ?? '')
    setAxisMaximum(axisState?.maximum?.toString() ?? '')
    setAxisReverse(axisState?.reverse ?? false)
    setAxisMajorInterval(axisState?.majorInterval?.toString() ?? '')
    setAxisNumberFormat(axisState?.numberFormat ?? 'auto')
    setAxisDecimalPlaces(axisState?.decimalPlaces ?? 2)
  }

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
  const editCapabilities = new Set(
    plot ? chartProductMetadata[plot.chartId]?.editCapabilities ?? [] : [],
  )
  const hasSpecialistEdits = [...editCapabilities].some((item) => [
    'bar_fill', 'bar_edge', 'bar_width', 'bar_gap', 'error_style', 'band_style',
    'colorbar', 'dual_y_style', 'panel_style', 'y_offset', 'chart_parameters',
  ].includes(item))
  const selectedSeriesId = plot?.seriesIds[seriesTargetIndex]
  const selectedAxisId = plot?.axisIds[axisTarget]
  const selectedSymbol = symbolCatalog.find((item) => item.shape === symbolShape)
  const selectedPaletteColors = paletteCatalog.find((palette) => palette.palette_id === paletteId)?.colors ?? []
  const palettePreviewColors = paletteReverse ? [...selectedPaletteColors].reverse() : selectedPaletteColors

  const applyPatch = async (
    operation: string,
    targetId: string | undefined,
    values: Record<string, JsonValue>,
  ): Promise<void> => {
    if (!plot || !onPatch || !targetId) {
      setEditState('error')
      setEditMessage('当前图形没有可用的编辑目标。')
      return
    }
    setEditState('saving')
    setEditMessage('正在创建新版本…')
    try {
      await onPatch({
        operation,
        target_id: targetId,
        expected_plot_version: plot.plotVersion,
        ...values,
      })
      setEditState('saved')
      setEditMessage('修改已保存为新版本。')
    } catch (error) {
      setEditState('error')
      setEditMessage(error instanceof Error ? error.message : '修改未能应用。')
    }
  }

  const applySeriesStyle = async (): Promise<void> => {
    const values: Record<string, JsonValue> = {}
    if (editCapabilities.has('series_color')) values.color = { value: color }
    if (editCapabilities.has('line_width')) values.line_width = { value: lineWidth, unit: 'pt' }
    if (editCapabilities.has('line_style')) values.line_style = lineStyle
    if (editCapabilities.has('marker_size')) values.marker_size = { value: markerSize, unit: 'pt' }
    if (editCapabilities.has('symbol_shape') || editCapabilities.has('symbol_interior')) {
      values.symbol = { shape: symbolShape, interior: symbolInterior }
    }
    await applyPatch('set_series_style', selectedSeriesId, values)
  }

  const applyPalette = async (): Promise<void> => {
    await applyPatch('set_palette', selectedSeriesId, {
      palette_id: paletteId,
      reverse: paletteReverse,
    })
  }

  const openAnnotationEditor = (kind: AnnotationKind): void => {
    setPanelOpen(true)
    setParameterTab('annotation')
    setAnnotationKind(kind)
  }

  const applyAnnotation = async (): Promise<void> => {
    if (!plot) return
    const coordinate = Number(annotationStart)
    const end = Number(annotationEnd)
    const annotation: Record<string, JsonValue> = {
      annotation_id: `annotation:ui.${plot.plotId.replace('plot:', '')}.v${plot.plotVersion + 1}`,
      kind: annotationKind,
      text: annotationKind === 'text' ? { nodes: [{ kind: 'plain', text: annotationText.trim() }] } : null,
      x: null,
      y: null,
      x2: null,
      y2: null,
      affect_range: false,
    }
    if (annotationKind === 'text') {
      annotation.x = coordinate
      annotation.y = end
    } else {
      annotation[annotationAxis] = coordinate
      if (annotationKind === 'reference_band') annotation[`${annotationAxis}2`] = end
    }
    await applyPatch('add_annotation', plot.plotId, { annotation })
  }

  return (
    <div className="focus-editor" role="dialog" aria-modal="true" aria-label="聚焦编辑">
      <header className="focus-header">
        <button className="back-button" type="button" onClick={onClose}><ArrowLeft size={18} />返回对话</button>
        <div className="focus-title">
          <h2>{active.title}</h2>
          <span>{plot ? `${plot.plotId} · v${plot.plotVersion}` : '线点图 · v3'}</span>
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
          <button type="button" aria-label="文本标注" disabled={!editCapabilities.has('safe_annotation')} onClick={() => openAnnotationEditor('text')}><Type size={17} /></button>
          <button type="button" aria-label="箭头标注" disabled title="首版不提供箭头标注"><ArrowUpRight size={17} /></button>
          <button type="button" aria-label="参考带" disabled={!editCapabilities.has('safe_annotation')} onClick={() => openAnnotationEditor('reference_band')}><RectangleHorizontal size={17} /></button>
          <button type="button" aria-label="参考线" disabled={!editCapabilities.has('safe_annotation')} onClick={() => openAnnotationEditor('reference_line')}><Baseline size={17} /></button>
          <button type="button" aria-label="圆形标注" disabled title="首版不提供任意形状"><Circle size={17} /></button>
          <span />
          <button type="button" aria-label="显示网格" disabled title="网格编辑尚未进入资格范围"><Grid2X2 size={17} /></button>
          <button type="button" aria-label="对齐" disabled title="任意对象对齐尚未进入资格范围"><AlignCenter size={17} /></button>
        </aside>

        <main className="focus-stage">
          <div className="stage-toolbar">
            <div className="scope-control" aria-label="编辑作用范围">
              <span>作用范围</span>
              {([
                ['current', '当前图'],
                ['selected', `选中图 ${selected.length}`],
                ['batch', '整个批次'],
              ] as [ScopeMode, string][]).map(([value, label]) => <button key={value} type="button" className={scope === value ? 'is-active' : ''} disabled={Boolean(plot) && value !== 'current'} title={Boolean(plot) && value !== 'current' ? '批量样式应用将在批次审阅中开放' : undefined} onClick={() => setScope(value)}>{label}</button>)}
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
              {compareOpen && (plot?.preview?.url ? <img className="focus-real-preview" src={plot.preview.url} alt={`${plot.title} 上一版本预览`} /> : <BatchPlot title={active.title} series={active.series} />)}
            </div>
            <div className="canvas-paper canvas-paper--current">
              {plot?.preview?.url ? <img className="focus-real-preview" src={plot.preview.url} alt={`${plot.title} Core 预览`} /> : <BatchPlot title={active.title} series={active.series} />}
              {!plot?.preview?.url && <button
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
              </button>}
              {!plot?.preview?.url && <button
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
              </button>}
            </div>
            {compareOpen && (
              <div className="compare-label compare-label--right"><span>v3</span>当前版本</div>
            )}
          </div>
          <div className="canvas-status"><Sparkles size={13} /><span>参数应用后创建新版本，原始数据保持只读</span><span className="zoom-status">100%</span></div>
        </main>

        {panelOpen && (
          <aside className="parameter-panel" aria-label="图形参数">
            <header><div><strong>图形参数</strong><span>{scope === 'current' ? active.title : scope === 'selected' ? `${selected.length} 张选中图` : '批次 B-024'}</span></div><button type="button" onClick={() => setPanelOpen(false)} aria-label="关闭参数面板"><X size={17} /></button></header>
            <div className="parameter-tabs" role="tablist" aria-label="编辑类别">
              {([['general', '常规'], ['style', '样式'], ...(hasSpecialistEdits ? [['specialist', '专属']] : []), ['axis', '坐标轴'], ['legend', '图例'], ['annotation', '标注']] as [ParameterTab, string][]).map(([value, label]) => (
                <button key={value} className={parameterTab === value ? 'is-active' : ''} type="button" role="tab" aria-selected={parameterTab === value} onClick={() => setParameterTab(value)}>{label}</button>
              ))}
            </div>

            {parameterTab === 'general' && (
              <>
                {editCapabilities.has('plot_title') && <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyPatch('set_plot_title', plot?.plotId, { title: plotTitle.trim() === '' ? null : { nodes: [{ kind: 'plain', text: plotTitle.trim() }] } }) }}><h3>图标题</h3><label><span>标题</span><input aria-label="图标题" value={plotTitle} maxLength={256} placeholder="留空即隐藏" onChange={(event) => setPlotTitle(event.target.value)} /></label><button className="parameter-apply" type="submit" disabled={editState === 'saving'}>应用图标题</button></form>}
                {editCapabilities.has('font') && <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyPatch('set_font_size', plot?.plotId, { size: { value: fontSizePt, unit: 'pt' } }) }}><h3>全局字号</h3><label><span>字号</span><div className="unit-input"><input aria-label="全局字号" type="number" min="5" max="72" step="0.5" value={fontSizePt} onChange={(event) => setFontSizePt(event.target.valueAsNumber)} /><span>pt</span></div></label><p className="parameter-note">字体族固定为资格测试字体栈，避免换机后字形漂移。</p><button className="parameter-apply" type="submit" disabled={editState === 'saving' || !Number.isFinite(fontSizePt) || fontSizePt < 5 || fontSizePt > 72}>应用字号</button></form>}
              </>
            )}

            {parameterTab === 'style' && (
              <>
                <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applySeriesStyle() }}>
                  <h3>系列样式</h3>
                  {plot && plot.seriesIds.length > 1 && <label><span>作用系列</span><select aria-label="作用系列" value={seriesTargetIndex} onChange={(event) => selectSeries(Number(event.target.value))}>{plot.seriesIds.map((seriesId, index) => <option key={seriesId} value={index}>系列 {index + 1}</option>)}</select></label>}
                  {editCapabilities.has('series_color') && <label><span>颜色</span><input aria-label="系列颜色" type="color" value={color} onChange={(event) => setColor(event.target.value)} /></label>}
                  {editCapabilities.has('line_width') && <label><span>线宽</span><div className="unit-input"><input aria-label="线宽" type="number" min="0.1" max="20" value={lineWidth} step="0.1" onChange={(event) => setLineWidth(event.target.valueAsNumber)} /><span>pt</span></div></label>}
                  {editCapabilities.has('line_style') && <label><span>线型</span><select aria-label="线型" value={lineStyle} onChange={(event) => setLineStyle(event.target.value)}><option value="solid">实线</option><option value="dashed">虚线</option><option value="dotted">点线</option><option value="dash_dot">点划线</option></select></label>}
                  {editCapabilities.has('marker_size') && <label><span>符号大小</span><div className="unit-input"><input aria-label="符号大小" type="number" min="0.5" max="72" value={markerSize} step="0.5" onChange={(event) => setMarkerSize(event.target.valueAsNumber)} /><span>pt</span></div></label>}
                  {editCapabilities.has('symbol_shape') && <label><span>Origin 符号</span><select aria-label="Origin 符号" value={symbolShape} onChange={(event) => { const next = event.target.value; setSymbolShape(next); const entry = symbolCatalog.find((item) => item.shape === next); if (!entry?.allowed_interiors.includes(symbolInterior)) setSymbolInterior('solid') }}>{symbolCatalog.map((item) => <option key={item.shape} value={item.shape}>{symbolNames[item.shape] ?? item.shape}</option>)}</select></label>}
                  {editCapabilities.has('symbol_interior') && <label><span>符号内部</span><select aria-label="符号内部" value={symbolInterior} onChange={(event) => setSymbolInterior(event.target.value)}>{(selectedSymbol?.allowed_interiors ?? ['solid']).map((value) => <option key={value} value={value}>{value === 'solid' ? '实心' : value === 'open' ? '开放（遮挡下层线）' : '空心（透出下层线）'}</option>)}</select></label>}
                  {[...editCapabilities].some((item) => ['series_color', 'line_width', 'line_style', 'marker_size', 'symbol_shape', 'symbol_interior'].includes(item))
                    ? <button className="parameter-apply" type="submit" disabled={editState === 'saving' || !selectedSeriesId}>应用系列样式</button>
                    : <p className="parameter-empty">该图没有可移植的系列样式项。</p>}
                </form>

                {editCapabilities.has('series_color') && (
                  <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyPatch('set_category_color', selectedSeriesId, { category: categoryName.trim(), color: { value: categoryColor } }) }}>
                    <h3>分类颜色</h3>
                    <label><span>分类名称</span><input aria-label="分类名称" type="text" value={categoryName} maxLength={256} placeholder="与图例名称完全一致" onChange={(event) => setCategoryName(event.target.value)} /></label>
                    <label><span>颜色</span><input aria-label="分类颜色" type="color" value={categoryColor} onChange={(event) => setCategoryColor(event.target.value)} /></label>
                    <button className="parameter-apply" type="submit" disabled={editState === 'saving' || !selectedSeriesId || categoryName.trim() === ''}>应用分类颜色</button>
                  </form>
                )}

                {editCapabilities.has('palette') && (
                  <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyPalette() }}>
                    <h3>Origin 对照色板</h3>
                    <label><span>色板</span><select aria-label="Origin 色板" value={paletteId} onChange={(event) => setPaletteId(event.target.value)}>{paletteCatalog.map((palette) => <option key={palette.palette_id} value={palette.palette_id}>{palette.palette_id}</option>)}</select></label>
                    <div className="palette-preview" aria-label={`${paletteId} 色板预览`}>{palettePreviewColors.map((entry, index) => <i key={`${entry.value}:${index}`} style={{ background: entry.value }} />)}</div>
                    <label className="parameter-check"><input type="checkbox" checked={paletteReverse} onChange={(event) => setPaletteReverse(event.target.checked)} /><span>反向使用色板</span></label>
                    <button className="parameter-apply" type="submit" disabled={editState === 'saving' || !selectedSeriesId}>应用色板</button>
                  </form>
                )}

                {editCapabilities.has('canvas_size') && (
                  <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyPatch('set_canvas_size', plot?.plotId, { physical_size: { width: { value: canvasWidth, unit: 'mm' }, height: { value: canvasHeight, unit: 'mm' } } }) }}>
                    <h3>画布尺寸</h3>
                    <label><span>宽度</span><div className="unit-input"><input aria-label="画布宽度" type="number" min="20" max="1000" value={canvasWidth} onChange={(event) => setCanvasWidth(event.target.valueAsNumber)} /><span>mm</span></div></label>
                    <label><span>高度</span><div className="unit-input"><input aria-label="画布高度" type="number" min="20" max="1000" value={canvasHeight} onChange={(event) => setCanvasHeight(event.target.valueAsNumber)} /><span>mm</span></div></label>
                    <button className="parameter-apply" type="submit" disabled={editState === 'saving'}>应用画布尺寸</button>
                  </form>
                )}
              </>
            )}

            {parameterTab === 'specialist' && plot && (
              <SpecialistEditor
                capabilities={editCapabilities}
                plot={plot}
                disabled={editState === 'saving'}
                onApply={(operation, values) => applyPatch(operation, plot.plotId, values)}
              />
            )}

            {parameterTab === 'axis' && (
              <>
                <section className="parameter-section">
                  <h3>作用坐标轴</h3>
                  <label><span>坐标轴</span><select aria-label="作用坐标轴" value={axisTarget} onChange={(event) => selectAxis(event.target.value as 'x' | 'y' | 'yRight')}><option value="x">X 轴</option><option value="y">左 Y 轴</option>{plot?.axisIds.yRight && <option value="yRight">右 Y 轴</option>}</select></label>
                </section>
                {editCapabilities.has('axis_label') && <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyPatch('set_axis_label', selectedAxisId, { label: { nodes: [{ kind: 'plain', text: axisLabel }] } }) }}><h3>轴标题</h3><label><span>标题</span><input aria-label="轴标题" required value={axisLabel} onChange={(event) => setAxisLabel(event.target.value)} /></label><button className="parameter-apply" type="submit" disabled={editState === 'saving' || !selectedAxisId || axisLabel.trim().length === 0}>应用轴标题</button></form>}
                {editCapabilities.has('axis_scale') && <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyPatch('set_axis_scale', selectedAxisId, { scale: axisScale }) }}><h3>轴尺度</h3><label><span>尺度</span><select aria-label="轴尺度" value={axisScale} onChange={(event) => setAxisScale(event.target.value)}><option value="linear">线性</option><option value="log10">Log10</option></select></label><button className="parameter-apply" type="submit" disabled={editState === 'saving' || !selectedAxisId}>应用轴尺度</button></form>}
                {editCapabilities.has('axis_range') && <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyPatch('set_axis_range', selectedAxisId, { minimum: Number(axisMinimum), maximum: Number(axisMaximum) }) }}><h3>固定范围</h3><label><span>最小值</span><input aria-label="轴最小值" type="number" required value={axisMinimum} onChange={(event) => setAxisMinimum(event.target.value)} /></label><label><span>最大值</span><input aria-label="轴最大值" type="number" required value={axisMaximum} onChange={(event) => setAxisMaximum(event.target.value)} /></label><button className="parameter-apply" type="submit" disabled={editState === 'saving' || !selectedAxisId || axisMinimum === '' || axisMaximum === '' || Number(axisMinimum) >= Number(axisMaximum)}>应用固定范围</button></form>}
                {editCapabilities.has('axis_range') && <section className="parameter-section"><h3>自动范围</h3><p className="parameter-note">清除固定上下限，按当前数据重新缩放。</p><button className="parameter-apply" type="button" disabled={editState === 'saving' || !selectedAxisId} onClick={() => { setAxisMinimum(''); setAxisMaximum(''); void applyPatch('set_axis_range', selectedAxisId, { minimum: null, maximum: null }) }}>恢复自动范围</button></section>}
                {editCapabilities.has('axis_range') && <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyPatch('set_axis_reverse', selectedAxisId, { reverse: axisReverse }) }}><h3>轴方向</h3><label className="parameter-check"><input aria-label="反向坐标轴" type="checkbox" checked={axisReverse} onChange={(event) => setAxisReverse(event.target.checked)} /><span>反向显示</span></label><button className="parameter-apply" type="submit" disabled={editState === 'saving' || !selectedAxisId}>应用轴方向</button></form>}
                {editCapabilities.has('axis_ticks') && <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyPatch('set_axis_ticks', selectedAxisId, { ticks: { major_interval: axisMajorInterval === '' ? null : Number(axisMajorInterval), number_format: axisNumberFormat, decimal_places: axisDecimalPlaces } }) }}><h3>刻度与数字</h3><label><span>主刻度间隔</span><input aria-label="主刻度间隔" type="number" min="0" step="any" value={axisMajorInterval} placeholder="自动" onChange={(event) => setAxisMajorInterval(event.target.value)} /></label><label><span>数字格式</span><select aria-label="刻度数字格式" value={axisNumberFormat} onChange={(event) => setAxisNumberFormat(event.target.value)}><option value="auto">自动</option><option value="fixed">定点小数</option><option value="scientific">科学计数法</option></select></label><label><span>小数位数</span><input aria-label="刻度小数位数" type="number" min="0" max="12" value={axisDecimalPlaces} onChange={(event) => setAxisDecimalPlaces(event.target.valueAsNumber)} /></label><button className="parameter-apply" type="submit" disabled={editState === 'saving' || !selectedAxisId || (axisMajorInterval !== '' && Number(axisMajorInterval) <= 0) || !Number.isInteger(axisDecimalPlaces) || axisDecimalPlaces < 0 || axisDecimalPlaces > 12}>应用刻度</button></form>}
              </>
            )}

            {parameterTab === 'legend' && (
              <>
                {editCapabilities.has('legend_visibility') && <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyPatch('set_legend_visibility', 'legend:main', { visible: legendVisible }) }}><h3>显示</h3><label className="parameter-check"><input type="checkbox" checked={legendVisible} onChange={(event) => setLegendVisible(event.target.checked)} /><span>显示图例</span></label><button className="parameter-apply" type="submit" disabled={editState === 'saving'}>应用显示状态</button></form>}
                {editCapabilities.has('legend_position') && <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyPatch('move_legend', 'legend:main', { placement: legendPlacement, anchor_x: legendPosition.x / 100, anchor_y: legendPosition.y / 100 }) }}><h3>位置</h3><label><span>布局</span><select aria-label="图例位置" value={legendPlacement} onChange={(event) => setLegendPlacement(event.target.value)}><option value="inside">图内</option><option value="outside_right">图外右侧</option><option value="outside_bottom">图外下方</option></select></label><button className="parameter-apply" type="submit" disabled={editState === 'saving'}>应用图例位置</button></form>}
              </>
            )}

            {parameterTab === 'annotation' && (
              editCapabilities.has('safe_annotation') ? <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyAnnotation() }}>
                <h3>安全标注</h3>
                <label><span>类型</span><select aria-label="标注类型" value={annotationKind} onChange={(event) => setAnnotationKind(event.target.value as AnnotationKind)}><option value="text">文本</option><option value="reference_line">参考线</option><option value="reference_band">参考带</option></select></label>
                {annotationKind === 'text' ? <><label><span>文本</span><input aria-label="标注文本" maxLength={256} value={annotationText} onChange={(event) => setAnnotationText(event.target.value)} /></label><label><span>X 坐标</span><input aria-label="标注 X 坐标" type="number" required value={annotationStart} onChange={(event) => setAnnotationStart(event.target.value)} /></label><label><span>Y 坐标</span><input aria-label="标注 Y 坐标" type="number" required value={annotationEnd} onChange={(event) => setAnnotationEnd(event.target.value)} /></label></> : <><label><span>方向</span><select aria-label="参考对象方向" value={annotationAxis} onChange={(event) => setAnnotationAxis(event.target.value as AnnotationAxis)}><option value="x">垂直（X 值）</option><option value="y">水平（Y 值）</option></select></label><label><span>{annotationKind === 'reference_band' ? '起点' : '位置'}</span><input aria-label="参考对象起点" type="number" required value={annotationStart} onChange={(event) => setAnnotationStart(event.target.value)} /></label>{annotationKind === 'reference_band' && <label><span>终点</span><input aria-label="参考对象终点" type="number" required value={annotationEnd} onChange={(event) => setAnnotationEnd(event.target.value)} /></label>}</>}
                <p className="parameter-note">标注不改变自动坐标范围；仅开放可稳定映射到 Origin 的文本、参考线和参考带。</p>
                <button className="parameter-apply" type="submit" disabled={editState === 'saving' || annotationStart === '' || (annotationKind !== 'reference_line' && annotationEnd === '') || (annotationKind === 'text' && annotationText.trim() === '') || (annotationKind === 'reference_band' && Number(annotationStart) >= Number(annotationEnd))}>添加标注</button>
              </form> : <section className="parameter-section"><p className="parameter-empty">该图尚未通过标注资格测试。</p></section>
            )}

            <section className={`parameter-feedback parameter-feedback--${editState}`} aria-live="polite">
              {editState === 'saving' ? <span>正在保存…</span> : editState === 'saved' ? <span><Check size={14} />{editMessage}</span> : editState === 'error' ? <span>{editMessage}</span> : <span>每次应用都会创建可撤销的新版本。</span>}
            </section>
          </aside>
        )}
      </div>

      <footer className="thumbnail-dock">
        <div className="thumbnail-dock__label"><Image size={15} /><span>批次 B-024</span><strong>{selected.length} 张已选</strong></div>
        <div className="thumbnail-strip">
          {availableItems.map((item, index) => (
            <article className={`${activeIndex === index ? 'is-active' : ''}${selected.includes(index) ? ' is-selected' : ''}`} key={item.file}>
              <button className="thumb-open" type="button" onClick={() => setActiveIndex(index)} aria-label={`打开 ${item.title}`}>{plot?.preview?.url ? <img className="focus-real-thumb" src={plot.preview.url} alt="" /> : <BatchPlot compact title={item.title} series={item.series} />}</button>
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
