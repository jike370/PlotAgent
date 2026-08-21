import { useRef, useState } from 'react'
import {
  ArrowLeft,
  Check,
  ChevronDown,
  Columns2,
  Download,
  Eye,
  FileImage,
  FileType2,
  Image,
  Layers3,
  Link2,
  Maximize2,
  Move,
  Redo2,
  RotateCcw,
  SlidersHorizontal,
  Undo2,
  X,
} from 'lucide-react'

import type { ScopeMode } from './ConversationWorkspace'
import { BatchPlot } from './PlotVisuals'
import type { JsonValue } from '../../../shared/desktop-contract'
import type { ProductPlot } from '../data/productState'
import { symbolCatalog } from '../data/chartCatalog'

interface FocusEditorProps {
  initialIndex: number
  initialPanelOpen?: boolean
  simplePanel?: boolean
  plot?: ProductPlot & { title: string }
  previousPlot?: ProductPlot
  onPatch?: (patch: JsonValue) => Promise<void>
  canUndo?: boolean
  canRedo?: boolean
  onUndo?: () => void
  onRedo?: () => void
  onExport?: (format: 'png' | 'svg' | 'opju') => void
  initialParameterTab?: ParameterTab
  onParameterTabChange?: (tab: ParameterTab) => void
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

export type ParameterTab =
  | 'general' | 'style' | 'specialist' | 'axis' | 'legend'
  | 'colormap' | 'uncertainty' | 'labels'
type EditState = 'idle' | 'saving' | 'saved' | 'error'

const symbolNames: Record<string, string> = {
  square: '方形', circle: '圆形', triangle_up: '上三角', triangle_down: '下三角',
  diamond: '菱形', plus: '加号', cross: '叉号', triangle_left: '左三角',
  triangle_right: '右三角', hexagon: '六边形', star: '星形', pentagon: '五边形',
}

type ChartParameterValue = string | number | boolean

const chartParameterLabels: Record<string, string> = {
  triangle: '矩阵显示区域',
  levels: '等高线级数',
  pareto_reference_percent: '帕累托参考百分比',
  facet_columns: '分面列数',
  panel_columns: '面板列数',
  show_risk_table: '显示风险表',
  null_effect: '零效应参考值',
  equal_axes: '坐标轴等比例',
  show_counts: '显示计数',
}

function defaultChartParameter(parameter: string): ChartParameterValue {
  if (parameter === 'triangle') return 'full'
  if (parameter === 'levels') return 12
  if (parameter === 'pareto_reference_percent') return 80
  if (parameter === 'facet_columns' || parameter === 'panel_columns') return 2
  if (parameter === 'null_effect') return 0
  if (parameter.startsWith('show_') || parameter === 'equal_axes') return true
  return 0
}

function ChartParameterEditor({
  parameters,
  values,
  disabled,
  onApply,
}: {
  parameters: readonly string[]
  values: Readonly<Record<string, ChartParameterValue>>
  disabled: boolean
  onApply: (parameter: string, value: ChartParameterValue) => Promise<void>
}): React.JSX.Element {
  const [drafts, setDrafts] = useState<Record<string, ChartParameterValue>>(() => (
    Object.fromEntries(parameters.map((parameter) => [
      parameter,
      values[parameter] ?? defaultChartParameter(parameter),
    ]))
  ))

  return <>
    {parameters.map((parameter) => {
      const value = drafts[parameter] ?? defaultChartParameter(parameter)
      const label = chartParameterLabels[parameter] ?? parameter
      return <form
        className="parameter-section"
        key={parameter}
        onSubmit={(event) => {
          event.preventDefault()
          void onApply(parameter, value)
        }}
      >
        <h3>{label}</h3>
        {parameter === 'triangle'
          ? <label><span>范围</span><select aria-label={label} value={String(value)} onChange={(event) => setDrafts((current) => ({ ...current, [parameter]: event.target.value }))}><option value="full">完整</option><option value="lower">下三角</option><option value="upper">上三角</option></select></label>
          : typeof value === 'boolean'
            ? <label className="parameter-check"><input aria-label={label} type="checkbox" checked={value} onChange={(event) => setDrafts((current) => ({ ...current, [parameter]: event.target.checked }))} /><span>{value ? '启用' : '停用'}</span></label>
            : <label><span>值</span><input aria-label={label} type="number" value={Number(value)} onChange={(event) => setDrafts((current) => ({ ...current, [parameter]: event.target.valueAsNumber }))} /></label>}
        <button className="parameter-apply" type="submit" disabled={disabled}>应用参数</button>
      </form>
    })}
  </>
}

export function FocusEditor({ initialIndex, initialPanelOpen = false, simplePanel = false, plot, previousPlot, onPatch, canUndo = false, canRedo = false, onUndo, onRedo, onExport, initialParameterTab = 'general', onParameterTabChange, onClose }: FocusEditorProps): React.JSX.Element {
  const initialSeriesStyle = plot?.seriesStyles[0]?.style ?? plot?.style
  const initialAxisState = plot?.axisStates.y ?? plot?.axisStates.x
  const [activeIndex, setActiveIndex] = useState(Math.min(initialIndex, 2))
  const [selected, setSelected] = useState<number[]>([Math.min(initialIndex, 2)])
  const [scope, setScope] = useState<ScopeMode>('current')
  const [panelOpen, setPanelOpen] = useState(initialPanelOpen)
  const [parameterTab, setParameterTab] = useState<ParameterTab>(initialParameterTab)
  const [compareOpen, setCompareOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [editState, setEditState] = useState<EditState>('idle')
  const [editMessage, setEditMessage] = useState('')
  const [seriesTargetIndex, setSeriesTargetIndex] = useState(0)
  const [seriesVisible, setSeriesVisible] = useState(initialSeriesStyle?.visible ?? true)
  const [lineColor, setLineColor] = useState(
    initialSeriesStyle?.lineStrokeColor ?? '#2A6FDB',
  )
  const [lineWidth, setLineWidth] = useState(initialSeriesStyle?.lineWidthPt ?? 0.8)
  const [lineStyle, setLineStyle] = useState(initialSeriesStyle?.lineStyle ?? 'solid')
  const [lineOpacity, setLineOpacity] = useState(initialSeriesStyle?.lineOpacity ?? 1)
  const [markerSize, setMarkerSize] = useState(initialSeriesStyle?.markerSizePt ?? 4.5)
  const [markerShape, setMarkerShape] = useState(initialSeriesStyle?.markerShape ?? 'circle')
  const [markerInterior, setMarkerInterior] = useState(
    initialSeriesStyle?.markerInterior ?? 'solid',
  )
  const [markerFillColor, setMarkerFillColor] = useState(
    initialSeriesStyle?.markerFillColor ?? '#2A6FDB',
  )
  const [markerStrokeColor, setMarkerStrokeColor] = useState(
    initialSeriesStyle?.markerStrokeColor ?? '#2A6FDB',
  )
  const [markerStrokeWidth, setMarkerStrokeWidth] = useState(
    initialSeriesStyle?.markerStrokeWidthPt ?? 0.8,
  )
  const [markerOpacity, setMarkerOpacity] = useState(initialSeriesStyle?.markerOpacity ?? 1)
  const [fillColor, setFillColor] = useState(initialSeriesStyle?.fillColor ?? '#2A6FDB')
  const [fillOpacity, setFillOpacity] = useState(initialSeriesStyle?.fillOpacity ?? 0.8)
  const [fillStrokeColor, setFillStrokeColor] = useState(
    initialSeriesStyle?.fillStrokeColor ?? '#1F4F99',
  )
  const [fillStrokeWidth, setFillStrokeWidth] = useState(
    initialSeriesStyle?.fillStrokeWidthPt ?? 0.8,
  )
  const [axisTarget, setAxisTarget] = useState<'x' | 'y' | 'yRight'>('y')
  const [axisScale, setAxisScale] = useState(initialAxisState?.scale ?? 'linear')
  const [axisLabel, setAxisLabel] = useState(initialAxisState?.label ?? '')
  const [axisMinimum, setAxisMinimum] = useState(initialAxisState?.minimum?.toString() ?? '')
  const [axisMaximum, setAxisMaximum] = useState(initialAxisState?.maximum?.toString() ?? '')
  const [axisReverse, setAxisReverse] = useState(initialAxisState?.reverse ?? false)
  const [tickLabelsVisible, setTickLabelsVisible] = useState(
    initialAxisState?.tickLabelsVisible ?? true,
  )
  const [majorTicksVisible, setMajorTicksVisible] = useState(
    initialAxisState?.majorTicksVisible ?? true,
  )
  const [minorTicksVisible, setMinorTicksVisible] = useState(
    initialAxisState?.minorTicksVisible ?? true,
  )
  const [tickDirection, setTickDirection] = useState(
    initialAxisState?.tickDirection ?? 'out',
  )
  const [axisLineVisible, setAxisLineVisible] = useState(
    initialAxisState?.axisLineVisible ?? true,
  )
  const [axisTitleVisible, setAxisTitleVisible] = useState(
    initialAxisState?.axisTitleVisible ?? true,
  )
  const [axisTitleColor, setAxisTitleColor] = useState('#111827')
  const [axisTitleSize, setAxisTitleSize] = useState(10)
  const [axisTickFormat, setAxisTickFormat] = useState('auto')
  const [axisTickRotation, setAxisTickRotation] = useState(0)
  const [axisTickSize, setAxisTickSize] = useState(9)
  const [axisLineColor, setAxisLineColor] = useState('#111827')
  const [axisLineWidth, setAxisLineWidth] = useState(0.8)
  const [majorGridVisible, setMajorGridVisible] = useState(false)
  const [minorGridVisible, setMinorGridVisible] = useState(false)
  const [gridColor, setGridColor] = useState('#D1D5DB')
  const [gridLineWidth, setGridLineWidth] = useState(0.5)
  const [plotTitle, setPlotTitle] = useState(plot?.plotTitle ?? '')
  const [titleFontFamily, setTitleFontFamily] = useState('auto')
  const [titleFontSize, setTitleFontSize] = useState(plot?.fontSizePt ?? 11)
  const [titleFontWeight, setTitleFontWeight] = useState('normal')
  const [titleItalic, setTitleItalic] = useState(false)
  const [titleColor, setTitleColor] = useState('#111827')
  const [legendVisible, setLegendVisible] = useState(plot?.style.legendVisible ?? true)
  const [legendPlacement, setLegendPlacement] = useState(() => {
    const placement = plot?.style.legendPlacement ?? 'inside'
    return placement === 'right' ? 'outside_right' : placement === 'bottom' ? 'outside_bottom' : placement
  })
  const [legendColumns, setLegendColumns] = useState(1)
  const [legendTitle, setLegendTitle] = useState('')
  const [legendFontSize, setLegendFontSize] = useState(9)
  const [legendFontColor, setLegendFontColor] = useState('#111827')
  const [legendFrameVisible, setLegendFrameVisible] = useState(false)
  const [legendFrameColor, setLegendFrameColor] = useState('#9CA3AF')
  const initialColorMap = plot?.colorMaps[0]
  const [palette, setPalette] = useState(initialColorMap?.palette ?? 'viridis')
  const [paletteReverse, setPaletteReverse] = useState(initialColorMap?.reverse ?? false)
  const [colorMapMode, setColorMapMode] = useState(initialColorMap?.mode ?? 'continuous')
  const [colorMapMinimum, setColorMapMinimum] = useState(
    initialColorMap?.minimum?.toString() ?? '',
  )
  const [colorMapMaximum, setColorMapMaximum] = useState(
    initialColorMap?.maximum?.toString() ?? '',
  )
  const [colorMapMidpoint, setColorMapMidpoint] = useState(
    initialColorMap?.midpoint?.toString() ?? '',
  )
  const [colorMapLevels, setColorMapLevels] = useState(initialColorMap?.levels ?? 8)
  const [colorbarVisible, setColorbarVisible] = useState(
    initialColorMap?.colorbarVisible ?? true,
  )
  const [colorbarTitle, setColorbarTitle] = useState(initialColorMap?.colorbarTitle ?? '')
  const [colorbarAnchor, setColorbarAnchor] = useState(
    initialColorMap?.colorbarAnchor ?? 'right',
  )
  const [colorbarTickFormat, setColorbarTickFormat] = useState(
    initialColorMap?.colorbarTickFormat ?? 'auto',
  )
  const [missingColor, setMissingColor] = useState(initialColorMap?.missingColor ?? '#BDBDBD')
  const [errorColor, setErrorColor] = useState(plot?.errorStyles[0]?.barColor ?? '#1F2937')
  const [errorWidth, setErrorWidth] = useState(plot?.errorStyles[0]?.barWidthPt ?? 0.8)
  const [errorCapSize, setErrorCapSize] = useState(plot?.errorStyles[0]?.capSizePt ?? 6)
  const [errorOpacity, setErrorOpacity] = useState(plot?.errorStyles[0]?.barOpacity ?? 1)
  const [bandFillColor, setBandFillColor] = useState(
    plot?.errorStyles[0]?.bandFillColor ?? '#93C5FD',
  )
  const [bandFillOpacity, setBandFillOpacity] = useState(
    plot?.errorStyles[0]?.bandFillOpacity ?? 0.25,
  )
  const [bandStrokeColor, setBandStrokeColor] = useState(
    plot?.errorStyles[0]?.bandStrokeColor ?? '#2A6FDB',
  )
  const [bandStrokeWidth, setBandStrokeWidth] = useState(
    plot?.errorStyles[0]?.bandStrokeWidthPt ?? 0.8,
  )
  const [labelsVisible, setLabelsVisible] = useState(plot?.dataLabelStyles[0]?.visible ?? false)
  const [labelFormat, setLabelFormat] = useState(
    plot?.dataLabelStyles[0]?.valueFormat ?? 'auto',
  )
  const [labelPosition, setLabelPosition] = useState(
    plot?.dataLabelStyles[0]?.position ?? 'auto',
  )
  const [labelFontSize, setLabelFontSize] = useState(
    plot?.dataLabelStyles[0]?.fontSizePt ?? 9,
  )
  const [labelPrefix, setLabelPrefix] = useState(plot?.dataLabelStyles[0]?.prefix ?? '')
  const [labelSuffix, setLabelSuffix] = useState(plot?.dataLabelStyles[0]?.suffix ?? '')
  const [labelRotation, setLabelRotation] = useState(
    plot?.dataLabelStyles[0]?.rotationDeg ?? 0,
  )
  const [labelFontWeight, setLabelFontWeight] = useState(
    plot?.dataLabelStyles[0]?.fontWeight ?? 'normal',
  )
  const [labelFontColor, setLabelFontColor] = useState(
    plot?.dataLabelStyles[0]?.fontColor ?? '#111827',
  )
  const [legendPosition, setLegendPosition] = useState<Position>({ x: 68, y: 17 })
  const dragStart = useRef<{ pointerX: number; pointerY: number; position: Position } | null>(null)

  const selectSeries = (index: number): void => {
    if (!plot) return
    const validIndex = Math.min(index, Math.max(0, plot.seriesIds.length - 1))
    const seriesStyle = plot.seriesStyles[validIndex]?.style ?? plot.style
    setSeriesTargetIndex(validIndex)
    setSeriesVisible(seriesStyle.visible ?? true)
    setLineColor(seriesStyle.lineStrokeColor ?? '#2A6FDB')
    setLineWidth(seriesStyle.lineWidthPt ?? 0.8)
    setLineStyle(seriesStyle.lineStyle ?? 'solid')
    setLineOpacity(seriesStyle.lineOpacity ?? 1)
    setMarkerSize(seriesStyle.markerSizePt ?? 4.5)
    setMarkerShape(seriesStyle.markerShape ?? 'circle')
    setMarkerInterior(seriesStyle.markerInterior ?? 'solid')
    setMarkerFillColor(seriesStyle.markerFillColor ?? '#2A6FDB')
    setMarkerStrokeColor(seriesStyle.markerStrokeColor ?? '#2A6FDB')
    setMarkerStrokeWidth(seriesStyle.markerStrokeWidthPt ?? 0.8)
    setMarkerOpacity(seriesStyle.markerOpacity ?? 1)
    setFillColor(seriesStyle.fillColor ?? '#2A6FDB')
    setFillOpacity(seriesStyle.fillOpacity ?? 0.8)
    setFillStrokeColor(seriesStyle.fillStrokeColor ?? '#1F4F99')
    setFillStrokeWidth(seriesStyle.fillStrokeWidthPt ?? 0.8)
    const colorMap = plot.colorMaps[validIndex]
    setPalette(colorMap?.palette ?? 'viridis')
    setPaletteReverse(colorMap?.reverse ?? false)
    setColorMapMode(colorMap?.mode ?? 'continuous')
    setColorMapMinimum(colorMap?.minimum?.toString() ?? '')
    setColorMapMaximum(colorMap?.maximum?.toString() ?? '')
    setColorMapMidpoint(colorMap?.midpoint?.toString() ?? '')
    setColorMapLevels(colorMap?.levels ?? 8)
    setColorbarVisible(colorMap?.colorbarVisible ?? true)
    setColorbarTitle(colorMap?.colorbarTitle ?? '')
    setColorbarAnchor(colorMap?.colorbarAnchor ?? 'right')
    setColorbarTickFormat(colorMap?.colorbarTickFormat ?? 'auto')
    setMissingColor(colorMap?.missingColor ?? '#BDBDBD')
    const errorStyle = plot.errorStyles[validIndex]
    setErrorColor(errorStyle?.barColor ?? '#1F2937')
    setErrorWidth(errorStyle?.barWidthPt ?? 0.8)
    setErrorCapSize(errorStyle?.capSizePt ?? 6)
    setErrorOpacity(errorStyle?.barOpacity ?? 1)
    setBandFillColor(errorStyle?.bandFillColor ?? '#93C5FD')
    setBandFillOpacity(errorStyle?.bandFillOpacity ?? 0.25)
    setBandStrokeColor(errorStyle?.bandStrokeColor ?? '#2A6FDB')
    setBandStrokeWidth(errorStyle?.bandStrokeWidthPt ?? 0.8)
    const labelStyle = plot.dataLabelStyles[validIndex]
    setLabelsVisible(labelStyle?.visible ?? false)
    setLabelFormat(labelStyle?.valueFormat ?? 'auto')
    setLabelPosition(labelStyle?.position ?? 'auto')
    setLabelFontSize(labelStyle?.fontSizePt ?? 9)
    setLabelPrefix(labelStyle?.prefix ?? '')
    setLabelSuffix(labelStyle?.suffix ?? '')
    setLabelRotation(labelStyle?.rotationDeg ?? 0)
    setLabelFontWeight(labelStyle?.fontWeight ?? 'normal')
    setLabelFontColor(labelStyle?.fontColor ?? '#111827')
  }

  const selectAxis = (target: 'x' | 'y' | 'yRight'): void => {
    const axisState = plot?.axisStates[target]
    setAxisTarget(target)
    setAxisScale(axisState?.scale ?? 'linear')
    setAxisLabel(axisState?.label ?? '')
    setAxisMinimum(axisState?.minimum?.toString() ?? '')
    setAxisMaximum(axisState?.maximum?.toString() ?? '')
    setAxisReverse(axisState?.reverse ?? false)
    setTickLabelsVisible(axisState?.tickLabelsVisible ?? true)
    setMajorTicksVisible(axisState?.majorTicksVisible ?? true)
    setMinorTicksVisible(axisState?.minorTicksVisible ?? true)
    setTickDirection(axisState?.tickDirection ?? 'out')
    setAxisLineVisible(axisState?.axisLineVisible ?? true)
    setAxisTitleVisible(axisState?.axisTitleVisible ?? true)
  }

  const startDrag = (event: React.PointerEvent<HTMLButtonElement>): void => {
    event.currentTarget.setPointerCapture(event.pointerId)
    dragStart.current = {
      pointerX: event.clientX,
      pointerY: event.clientY,
      position: legendPosition,
    }
  }

  const moveDrag = (event: React.PointerEvent<HTMLButtonElement>): void => {
    if (!dragStart.current) return
    const next = {
      x: Math.max(4, Math.min(86, dragStart.current.position.x + (event.clientX - dragStart.current.pointerX) / 8)),
      y: Math.max(5, Math.min(78, dragStart.current.position.y + (event.clientY - dragStart.current.pointerY) / 6)),
    }
    setLegendPosition(next)
  }

  const keyboardMove = (event: React.KeyboardEvent<HTMLButtonElement>): void => {
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
    setLegendPosition(update)
  }

  const availableItems = plot ? [{ title: plot.title, file: plot.plotId, series: 'control' as const }] : focusItems
  const active = availableItems[Math.min(activeIndex, availableItems.length - 1)]
  const engineCapabilities = plot?.engineCapabilities ?? {}
  const seriesParameters = new Set(engineCapabilities.set_series_style ?? [])
  const axisParameters = new Set(engineCapabilities.set_axis ?? [])
  const legendParameters = new Set(engineCapabilities.set_legend ?? [])
  const colorMapParameters = new Set(engineCapabilities.set_colormap ?? [])
  const errorParameters = new Set(engineCapabilities.set_error_style ?? [])
  const dataLabelParameters = new Set(engineCapabilities.set_data_labels ?? [])
  const chartParameterNames = engineCapabilities.set_chart_parameter ?? []
  const editCapabilities = new Set([
    ...(engineCapabilities.set_title ? ['plot_title'] : []),
    ...(seriesParameters.has('visible') ? ['series_visibility'] : []),
    ...(seriesParameters.has('line_stroke_color') ? ['line_color'] : []),
    ...(seriesParameters.has('line_width_pt') ? ['line_width'] : []),
    ...(seriesParameters.has('line_style') ? ['line_style'] : []),
    ...(seriesParameters.has('line_opacity') ? ['line_opacity'] : []),
    ...(seriesParameters.has('marker_shape') ? ['marker_shape'] : []),
    ...(seriesParameters.has('marker_size_pt') ? ['marker_size'] : []),
    ...(seriesParameters.has('marker_interior') ? ['marker_interior'] : []),
    ...(seriesParameters.has('marker_fill_color') ? ['marker_fill_color'] : []),
    ...(seriesParameters.has('marker_stroke_color') ? ['marker_stroke_color'] : []),
    ...(seriesParameters.has('marker_stroke_width_pt') ? ['marker_stroke_width'] : []),
    ...(seriesParameters.has('marker_opacity') ? ['marker_opacity'] : []),
    ...(seriesParameters.has('fill_color') ? ['fill_color'] : []),
    ...(seriesParameters.has('fill_opacity') ? ['fill_opacity'] : []),
    ...(seriesParameters.has('fill_stroke_color') ? ['fill_stroke_color'] : []),
    ...(seriesParameters.has('fill_stroke_width_pt') ? ['fill_stroke_width'] : []),
    ...(axisParameters.has('label') ? ['axis_label'] : []),
    ...(axisParameters.has('scale') ? ['axis_scale'] : []),
    ...(axisParameters.has('bounds') ? ['axis_range'] : []),
    ...(axisParameters.has('reverse') ? ['axis_reverse'] : []),
    ...(axisParameters.has('tick_labels_visible') ? ['tick_labels_visibility'] : []),
    ...(axisParameters.has('major_ticks_visible') ? ['major_ticks_visibility'] : []),
    ...(axisParameters.has('minor_ticks_visible') ? ['minor_ticks_visibility'] : []),
    ...(axisParameters.has('tick_direction') ? ['tick_direction'] : []),
    ...(axisParameters.has('axis_line_visible') ? ['axis_line_visibility'] : []),
    ...(axisParameters.has('axis_title_visible') ? ['axis_title_visibility'] : []),
    ...(legendParameters.has('visible') ? ['legend_visibility'] : []),
    ...(legendParameters.has('anchor') ? ['legend_position'] : []),
    ...(colorMapParameters.size > 0 ? ['colormap'] : []),
    ...(errorParameters.size > 0 ? ['error_style'] : []),
    ...(dataLabelParameters.size > 0 ? ['data_labels'] : []),
  ])
  const hasSpecialistEdits = chartParameterNames.length > 0
  const selectedSeriesId = plot?.seriesIds[seriesTargetIndex]
  const selectedAxisId = plot?.axisIds[axisTarget]
  const legendTargetId = plot?.legendId
    ?? (plot ? `legend:${plot.plotId.replace('plot:', '')}.main` : undefined)
  const axisBoundsInvalid = editCapabilities.has('axis_range') && (
    (axisMinimum === '') !== (axisMaximum === '')
    || (axisMinimum !== '' && axisMaximum !== '' && Number(axisMinimum) >= Number(axisMaximum))
  )

  const legendAnchor = (placement: string): string => placement === 'outside_right'
    ? 'right'
    : placement === 'outside_bottom' ? 'bottom' : placement

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
    if (Object.keys(values).length === 0) {
      setEditState('saved')
      setEditMessage('当前设置没有变化。')
      return
    }
    setEditState('saving')
    setEditMessage('正在创建新版本…')
    try {
      await onPatch({
        operation,
        target: targetId,
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
    const current = plot?.seriesStyles[seriesTargetIndex]?.style ?? plot?.style ?? {}
    if (editCapabilities.has('series_visibility') && seriesVisible !== (current.visible ?? true)) values.visible = seriesVisible
    if (editCapabilities.has('line_color') && lineColor !== (current.lineStrokeColor ?? '#2A6FDB')) values.line_stroke_color = lineColor
    if (editCapabilities.has('line_width') && lineWidth !== (current.lineWidthPt ?? 0.8)) values.line_width_pt = lineWidth
    if (editCapabilities.has('line_style') && lineStyle !== (current.lineStyle ?? 'solid')) values.line_style = lineStyle
    if (editCapabilities.has('line_opacity') && lineOpacity !== (current.lineOpacity ?? 1)) values.line_opacity = lineOpacity
    if (editCapabilities.has('marker_size') && markerSize !== (current.markerSizePt ?? 4.5)) values.marker_size_pt = markerSize
    if (editCapabilities.has('marker_shape') && markerShape !== (current.markerShape ?? 'circle')) values.marker_shape = markerShape
    if (editCapabilities.has('marker_interior') && markerInterior !== (current.markerInterior ?? 'solid')) values.marker_interior = markerInterior
    if (editCapabilities.has('marker_fill_color') && markerFillColor !== (current.markerFillColor ?? '#2A6FDB')) values.marker_fill_color = markerFillColor
    if (editCapabilities.has('marker_stroke_color') && markerStrokeColor !== (current.markerStrokeColor ?? '#2A6FDB')) {
      values.marker_stroke_color = markerStrokeColor
    }
    if (editCapabilities.has('marker_stroke_width') && markerStrokeWidth !== (current.markerStrokeWidthPt ?? 0.8)) {
      values.marker_stroke_width_pt = markerStrokeWidth
    }
    if (editCapabilities.has('marker_opacity') && markerOpacity !== (current.markerOpacity ?? 1)) values.marker_opacity = markerOpacity
    if (editCapabilities.has('fill_color') && fillColor !== (current.fillColor ?? '#2A6FDB')) values.fill_color = fillColor
    if (editCapabilities.has('fill_opacity') && fillOpacity !== (current.fillOpacity ?? 0.8)) values.fill_opacity = fillOpacity
    if (editCapabilities.has('fill_stroke_color') && fillStrokeColor !== (current.fillStrokeColor ?? '#1F4F99')) {
      values.fill_stroke_color = fillStrokeColor
    }
    if (editCapabilities.has('fill_stroke_width') && fillStrokeWidth !== (current.fillStrokeWidthPt ?? 0.8)) {
      values.fill_stroke_width_pt = fillStrokeWidth
    }
    await applyPatch('set_series_style', selectedSeriesId, values)
  }

  const applyTitleSettings = async (): Promise<void> => {
    const values: Record<string, JsonValue> = {}
    const text = plotTitle.trim()
    if (text !== (plot?.plotTitle ?? '')) values.text = text
    if (titleFontFamily !== 'auto') values.font_family = titleFontFamily
    if (titleFontSize !== (plot?.fontSizePt ?? 11)) values.font_size_pt = titleFontSize
    if (titleFontWeight !== 'normal') values.font_weight = titleFontWeight
    if (titleItalic) values.italic = true
    if (titleColor !== '#111827') values.color = titleColor
    await applyPatch('set_title', plot?.plotId, values)
  }

  const applyAxisSettings = async (): Promise<void> => {
    const values: Record<string, JsonValue> = {}
    const current = plot?.axisStates[axisTarget]
    if (editCapabilities.has('axis_label') && axisLabel.trim() !== (current?.label ?? '')) values.label = axisLabel.trim()
    if (editCapabilities.has('axis_scale') && axisScale !== (current?.scale ?? 'linear')) values.scale = axisScale
    if (editCapabilities.has('axis_range') && axisMinimum !== '' && axisMaximum !== '') {
      const minimum = Number(axisMinimum)
      const maximum = Number(axisMaximum)
      if (minimum !== current?.minimum || maximum !== current?.maximum) {
        values.minimum = minimum
        values.maximum = maximum
      }
    }
    if (editCapabilities.has('axis_reverse') && axisReverse !== (current?.reverse ?? false)) values.reverse = axisReverse
    if (editCapabilities.has('tick_labels_visibility') && tickLabelsVisible !== (current?.tickLabelsVisible ?? true)) values.tick_labels_visible = tickLabelsVisible
    if (editCapabilities.has('major_ticks_visibility') && majorTicksVisible !== (current?.majorTicksVisible ?? true)) values.major_ticks_visible = majorTicksVisible
    if (editCapabilities.has('minor_ticks_visibility') && minorTicksVisible !== (current?.minorTicksVisible ?? true)) values.minor_ticks_visible = minorTicksVisible
    if (editCapabilities.has('tick_direction') && tickDirection !== (current?.tickDirection ?? 'out')) values.tick_direction = tickDirection
    if (editCapabilities.has('axis_line_visibility') && axisLineVisible !== (current?.axisLineVisible ?? true)) values.axis_line_visible = axisLineVisible
    if (editCapabilities.has('axis_title_visibility') && axisTitleVisible !== (current?.axisTitleVisible ?? true)) values.axis_title_visible = axisTitleVisible
    if (axisParameters.has('title_font_size_pt') && axisTitleSize !== 10) values.title_font_size_pt = axisTitleSize
    if (axisParameters.has('title_color') && axisTitleColor !== '#111827') values.title_color = axisTitleColor
    if (axisParameters.has('tick_format') && axisTickFormat !== 'auto') values.tick_format = axisTickFormat
    if (axisParameters.has('tick_rotation_deg') && axisTickRotation !== 0) values.tick_rotation_deg = axisTickRotation
    if (axisParameters.has('tick_font_size_pt') && axisTickSize !== 9) values.tick_font_size_pt = axisTickSize
    if (axisParameters.has('axis_line_color') && axisLineColor !== '#111827') values.axis_line_color = axisLineColor
    if (axisParameters.has('axis_line_width_pt') && axisLineWidth !== 0.8) values.axis_line_width_pt = axisLineWidth
    if (axisParameters.has('major_grid_visible') && majorGridVisible) values.major_grid_visible = true
    if (axisParameters.has('minor_grid_visible') && minorGridVisible) values.minor_grid_visible = true
    if (axisParameters.has('grid_color') && gridColor !== '#D1D5DB') values.grid_color = gridColor
    if (axisParameters.has('grid_line_width_pt') && gridLineWidth !== 0.5) values.grid_line_width_pt = gridLineWidth
    await applyPatch('set_axis', selectedAxisId, values)
  }

  const applyLegendSettings = async (): Promise<void> => {
    const values: Record<string, JsonValue> = {}
    if (editCapabilities.has('legend_visibility') && legendVisible !== (plot?.style.legendVisible ?? true)) values.visible = legendVisible
    if (editCapabilities.has('legend_position')) {
      const anchor = legendAnchor(legendPlacement)
      if (anchor !== (plot?.style.legendPlacement ?? 'inside')) values.anchor = anchor
    }
    if (legendParameters.has('columns') && legendColumns !== 1) values.columns = legendColumns
    if (legendParameters.has('title') && legendTitle !== '') values.title = legendTitle
    if (legendParameters.has('font_size_pt') && legendFontSize !== 9) values.font_size_pt = legendFontSize
    if (legendParameters.has('font_color') && legendFontColor !== '#111827') values.font_color = legendFontColor
    if (legendParameters.has('frame_visible') && legendFrameVisible) values.frame_visible = true
    if (legendParameters.has('frame_color') && legendFrameColor !== '#9CA3AF') values.frame_color = legendFrameColor
    await applyPatch('set_legend', legendTargetId, values)
  }

  const applyColorMap = async (): Promise<void> => {
    const values: Record<string, JsonValue> = {
      palette,
      reverse: paletteReverse,
      mode: colorMapMode,
      levels: colorMapLevels,
      missing_color: missingColor,
      colorbar_visible: colorbarVisible,
      colorbar_anchor: colorbarAnchor,
      colorbar_title: colorbarTitle,
      colorbar_tick_format: colorbarTickFormat,
    }
    if (colorMapMinimum !== '' && colorMapMaximum !== '') {
      values.minimum = Number(colorMapMinimum)
      values.maximum = Number(colorMapMaximum)
      if (colorMapMidpoint !== '') values.midpoint = Number(colorMapMidpoint)
    }
    await applyPatch('set_colormap', selectedSeriesId, values)
  }

  const applyErrorStyle = async (): Promise<void> => {
    const values: Record<string, JsonValue> = {}
    if (errorParameters.has('bar_color')) values.bar_color = errorColor
    if (errorParameters.has('bar_width_pt')) values.bar_width_pt = errorWidth
    if (errorParameters.has('cap_size_pt')) values.cap_size_pt = errorCapSize
    if (errorParameters.has('bar_opacity')) values.bar_opacity = errorOpacity
    if (errorParameters.has('band_fill_color')) values.band_fill_color = bandFillColor
    if (errorParameters.has('band_fill_opacity')) values.band_fill_opacity = bandFillOpacity
    if (errorParameters.has('band_stroke_color')) values.band_stroke_color = bandStrokeColor
    if (errorParameters.has('band_stroke_width_pt')) {
      values.band_stroke_width_pt = bandStrokeWidth
    }
    await applyPatch('set_error_style', selectedSeriesId, values)
  }

  const applyDataLabels = async (): Promise<void> => {
    await applyPatch('set_data_labels', selectedSeriesId, {
      visible: labelsVisible,
      value_format: labelFormat,
      prefix: labelPrefix,
      suffix: labelSuffix,
      position: labelPosition,
      rotation_deg: labelRotation,
      font_size_pt: labelFontSize,
      font_weight: labelFontWeight,
      font_color: labelFontColor,
    })
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
          <button type="button" aria-label="撤销" disabled={!canUndo} onClick={onUndo}><Undo2 size={17} /></button>
          <button type="button" aria-label="重做" disabled={!canRedo} onClick={onRedo}><Redo2 size={17} /></button>
          <span className="toolbar-divider" />
          <button className={compareOpen ? 'is-active' : ''} type="button" disabled={!previousPlot} onClick={() => setCompareOpen((open) => !open)}><Columns2 size={16} />比较上一版本</button>
          <span className="focus-version-label">版本 v{plot?.plotVersion ?? 1}</span>
        </div>
        <div className="focus-header-actions">
          <button className={panelOpen ? 'is-active' : ''} type="button" onClick={() => setPanelOpen((open) => !open)}><SlidersHorizontal size={16} />编辑面板</button>
          <div className="export-anchor">
            <button className="primary-button" type="button" onClick={() => setExportOpen((open) => !open)} aria-expanded={exportOpen}><Download size={16} />导出<ChevronDown size={14} /></button>
            {exportOpen && (
              <div className="export-menu" role="menu">
                <button role="menuitem" type="button" onClick={() => { setExportOpen(false); onExport?.('png') }}><FileImage size={16} /><span><strong>导出 PNG</strong><small>位图文件</small></span></button>
                <button role="menuitem" type="button" onClick={() => { setExportOpen(false); onExport?.('svg') }}><FileType2 size={16} /><span><strong>导出 SVG</strong><small>保留矢量对象</small></span></button>
                <button role="menuitem" type="button" onClick={() => { setExportOpen(false); onExport?.('opju') }}><Layers3 size={16} /><span><strong>导出 OPJU</strong><small>Origin 原生可编辑项目</small></span></button>
              </div>
            )}
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭聚焦编辑"><X size={19} /></button>
        </div>
      </header>

      <div className={`focus-body${panelOpen ? ' has-panel' : ''}${simplePanel ? ' is-simple' : ''}`}>
        <main className="focus-stage">
          <div className="stage-toolbar">
            <div className="scope-control" aria-label="编辑作用范围">
              <span>作用范围</span>
              {simplePanel ? <button type="button" className="is-active">当前图</button> : ([
                ['current', '当前图'],
                ['selected', `选中图 ${selected.length}`],
                ['batch', '整个批次'],
              ] as [ScopeMode, string][]).map(([value, label]) => <button key={value} type="button" className={scope === value ? 'is-active' : ''} disabled={Boolean(plot) && value !== 'current'} title={Boolean(plot) && value !== 'current' ? '批量样式应用将在批次审阅中开放' : undefined} onClick={() => setScope(value)}>{label}</button>)}
            </div>
            <div className="stage-meta">
              <span><Eye size={13} />{simplePanel ? '当前渲染预览' : '预览 2,406 / 2,406 点'}</span>
              <button type="button"><Maximize2 size={14} />适合窗口</button>
            </div>
          </div>

          <div className={`plot-stage${compareOpen ? ' is-comparing' : ''}`}>
            {compareOpen && previousPlot && (
              <div className="compare-label compare-label--left"><span>v{previousPlot.plotVersion}</span>修改前</div>
            )}
            <div className="canvas-paper canvas-paper--previous" aria-hidden={!compareOpen}>
              {compareOpen && previousPlot && (previousPlot.preview?.url ? <img className="focus-real-preview" src={previousPlot.preview.url} alt={`${plot?.title ?? active.title} v${previousPlot.plotVersion} 预览`} /> : <BatchPlot title={active.title} series={active.series} />)}
            </div>
            <div className="canvas-paper canvas-paper--current">
              {plot?.preview?.url ? <img className="focus-real-preview" src={plot.preview.url} alt={`${plot.title} Core 预览`} /> : <BatchPlot title={active.title} series={active.series} />}
              {!plot?.preview?.url && <button
                className="draggable-legend"
                type="button"
                style={{ left: `${legendPosition.x}%`, top: `${legendPosition.y}%` }}
                onPointerDown={startDrag}
                onPointerMove={moveDrag}
                onPointerUp={() => { dragStart.current = null }}
                onKeyDown={keyboardMove}
                aria-label="图例，可拖动或用方向键移动"
              >
                <Move size={12} aria-hidden="true" />
                <span><i className="legend-line legend-line--blue" />Control</span>
                <span><i className="legend-line legend-line--amber" />Treated</span>
              </button>}
            </div>
            {compareOpen && plot && (
              <div className="compare-label compare-label--right"><span>v{plot.plotVersion}</span>当前版本</div>
            )}
          </div>
          <div className="canvas-status" aria-label="画布缩放"><span className="zoom-status">100%</span></div>
        </main>

        {panelOpen && (
          <aside className="parameter-panel" aria-label="图形参数">
            <header><div><strong>调整图形</strong><span>{scope === 'current' ? `${active.title} · v${plot?.plotVersion ?? 1}` : scope === 'selected' ? `${selected.length} 张选中图` : '批次 B-024'}</span></div><button type="button" onClick={() => setPanelOpen(false)} aria-label="关闭参数面板"><X size={17} /></button></header>
            <div className="parameter-tabs" role="tablist" aria-label="编辑类别">
              {([
                ['general', '常规'],
                ['style', '系列'],
                ...(!simplePanel && editCapabilities.has('colormap') ? [['colormap', '色阶']] : []),
                ...(!simplePanel && editCapabilities.has('error_style') ? [['uncertainty', '误差']] : []),
                ...(!simplePanel && editCapabilities.has('data_labels') ? [['labels', '标签']] : []),
                ...(!simplePanel && hasSpecialistEdits ? [['specialist', '专属']] : []),
                ['axis', '坐标轴'],
                ['legend', '图例'],
              ] as [ParameterTab, string][]).map(([value, label]) => (
                <button key={value} className={parameterTab === value ? 'is-active' : ''} type="button" role="tab" aria-selected={parameterTab === value} onClick={() => { setParameterTab(value); onParameterTabChange?.(value) }}>{label}</button>
              ))}
            </div>

            {parameterTab === 'general' && (
              <>
                {editCapabilities.has('plot_title') && <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyTitleSettings() }}><h3>图标题</h3><label><span>标题</span><input aria-label="图标题" value={plotTitle} maxLength={256} placeholder="留空即隐藏" onChange={(event) => setPlotTitle(event.target.value)} /></label><details className="parameter-subsection"><summary>字体与颜色</summary><label><span>字体</span><select aria-label="标题字体" value={titleFontFamily} onChange={(event) => setTitleFontFamily(event.target.value)}><option value="auto">自动</option><option value="Arial">Arial</option><option value="Times New Roman">Times New Roman</option><option value="Microsoft YaHei">微软雅黑</option><option value="SimSun">宋体</option></select></label><label><span>字号</span><div className="unit-input"><input aria-label="标题字号" type="number" min="5" max="72" step="0.5" value={titleFontSize} onChange={(event) => setTitleFontSize(event.target.valueAsNumber)} /><span>pt</span></div></label><label><span>字重</span><select aria-label="标题字重" value={titleFontWeight} onChange={(event) => setTitleFontWeight(event.target.value)}><option value="normal">常规</option><option value="bold">粗体</option></select></label><label className="parameter-check"><input aria-label="标题斜体" type="checkbox" checked={titleItalic} onChange={(event) => setTitleItalic(event.target.checked)} /><span>斜体</span></label><label><span>颜色</span><input aria-label="标题颜色" type="color" value={titleColor} onChange={(event) => setTitleColor(event.target.value)} /></label></details><button className="parameter-apply" type="submit" disabled={editState === 'saving'}>应用图标题</button></form>}
              </>
            )}

            {parameterTab === 'style' && (
              <>
                <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applySeriesStyle() }}>
                  <h3>系列样式</h3>
                  {plot && plot.seriesIds.length > 1 && <label><span>作用系列</span><select aria-label="作用系列" value={seriesTargetIndex} onChange={(event) => selectSeries(Number(event.target.value))}>{plot.seriesIds.map((seriesId, index) => <option key={seriesId} value={index}>系列 {index + 1}</option>)}</select></label>}
                  {editCapabilities.has('series_visibility') && <label className="parameter-check"><input aria-label="显示整个数据系列" type="checkbox" checked={seriesVisible} onChange={(event) => setSeriesVisible(event.target.checked)} /><span>显示整个数据系列</span></label>}
                  {[...editCapabilities].some((item) => item.startsWith('line_')) && <details className="parameter-subsection" open><summary>线条</summary>
                    {editCapabilities.has('line_color') && <label><span>描边颜色</span><input aria-label="线条描边颜色" type="color" value={lineColor} onChange={(event) => setLineColor(event.target.value)} /></label>}
                    {editCapabilities.has('line_width') && <label><span>线宽</span><div className="unit-input"><input aria-label="线宽" type="number" min="0.1" max="20" value={lineWidth} step="0.1" onChange={(event) => setLineWidth(event.target.valueAsNumber)} /><span>pt</span></div></label>}
                    {editCapabilities.has('line_style') && <label><span>线型</span><select aria-label="线型" value={lineStyle} onChange={(event) => setLineStyle(event.target.value)}><option value="solid">实线</option><option value="dash">虚线</option><option value="dot">点线</option><option value="dash_dot">点划线</option><option value="none">无线</option></select></label>}
                    {editCapabilities.has('line_opacity') && <label><span>不透明度</span><div className="unit-input"><input aria-label="线条不透明度" type="range" min="0" max="1" value={lineOpacity} step="0.05" onChange={(event) => setLineOpacity(event.target.valueAsNumber)} /><span>{Math.round(lineOpacity * 100)}%</span></div></label>}
                  </details>}
                  {[...editCapabilities].some((item) => item.startsWith('marker_')) && <details className="parameter-subsection" open><summary>符号</summary>
                    {editCapabilities.has('marker_shape') && <label><span>形状</span><select aria-label="符号形状" value={markerShape} onChange={(event) => setMarkerShape(event.target.value)}>{symbolCatalog.map((item) => <option key={item.shape} value={item.shape}>{symbolNames[item.shape] ?? item.shape}</option>)}</select></label>}
                    {editCapabilities.has('marker_size') && <label><span>大小</span><div className="unit-input"><input aria-label="符号大小" type="number" min="0.5" max="72" value={markerSize} step="0.5" onChange={(event) => setMarkerSize(event.target.valueAsNumber)} /><span>pt</span></div></label>}
                    {editCapabilities.has('marker_interior') && <label><span>内部</span><select aria-label="符号内部" value={markerInterior} onChange={(event) => setMarkerInterior(event.target.value)}><option value="solid">实心</option><option value="open">空心</option></select></label>}
                    {editCapabilities.has('marker_fill_color') && <label><span>填充颜色</span><input aria-label="符号填充颜色" type="color" value={markerFillColor} onChange={(event) => setMarkerFillColor(event.target.value)} /></label>}
                    {editCapabilities.has('marker_stroke_color') && <label><span>边缘颜色</span><input aria-label="符号边缘颜色" type="color" value={markerStrokeColor} onChange={(event) => setMarkerStrokeColor(event.target.value)} /></label>}
                    {editCapabilities.has('marker_stroke_width') && <label><span>边缘宽度</span><div className="unit-input"><input aria-label="符号边缘宽度" type="number" min="0" max="10" value={markerStrokeWidth} step="0.1" onChange={(event) => setMarkerStrokeWidth(event.target.valueAsNumber)} /><span>pt</span></div></label>}
                    {editCapabilities.has('marker_opacity') && <label><span>不透明度</span><div className="unit-input"><input aria-label="符号不透明度" type="range" min="0" max="1" value={markerOpacity} step="0.05" onChange={(event) => setMarkerOpacity(event.target.valueAsNumber)} /><span>{Math.round(markerOpacity * 100)}%</span></div></label>}
                  </details>}
                  {[...editCapabilities].some((item) => item.startsWith('fill_')) && <details className="parameter-subsection" open><summary>填充</summary>
                    {editCapabilities.has('fill_color') && <label><span>填充颜色</span><input aria-label="填充颜色" type="color" value={fillColor} onChange={(event) => setFillColor(event.target.value)} /></label>}
                    {editCapabilities.has('fill_opacity') && <label><span>不透明度</span><div className="unit-input"><input aria-label="填充不透明度" type="range" min="0" max="1" value={fillOpacity} step="0.05" onChange={(event) => setFillOpacity(event.target.valueAsNumber)} /><span>{Math.round(fillOpacity * 100)}%</span></div></label>}
                    {editCapabilities.has('fill_stroke_color') && <label><span>边框颜色</span><input aria-label="填充边框颜色" type="color" value={fillStrokeColor} onChange={(event) => setFillStrokeColor(event.target.value)} /></label>}
                    {editCapabilities.has('fill_stroke_width') && <label><span>边框宽度</span><div className="unit-input"><input aria-label="填充边框宽度" type="number" min="0" max="20" value={fillStrokeWidth} step="0.1" onChange={(event) => setFillStrokeWidth(event.target.valueAsNumber)} /><span>pt</span></div></label>}
                  </details>}
                  {[...editCapabilities].some((item) => item === 'series_visibility' || item.startsWith('line_') || item.startsWith('marker_') || item.startsWith('fill_'))
                    ? <button className="parameter-apply" type="submit" disabled={editState === 'saving' || !selectedSeriesId}>应用系列样式</button>
                    : <p className="parameter-empty">该图没有可移植的系列样式项。</p>}
                </form>

              </>
            )}

            {parameterTab === 'colormap' && (
              <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyColorMap() }}>
                <h3>颜色映射与色标</h3>
                {plot && plot.seriesIds.length > 1 && <label><span>作用系列</span><select aria-label="色阶作用系列" value={seriesTargetIndex} onChange={(event) => selectSeries(Number(event.target.value))}>{plot.seriesIds.map((seriesId, index) => <option key={seriesId} value={index}>系列 {index + 1}</option>)}</select></label>}
                <label><span>色板</span><select aria-label="色板" value={palette} onChange={(event) => setPalette(event.target.value)}><option value="viridis">Viridis</option><option value="cividis">Cividis</option><option value="plasma">Plasma</option><option value="blue_white_red">蓝—白—红</option><option value="gray_scale">灰阶</option><option value="fire">Fire</option><option value="rainbow_modified">Modified Rainbow</option></select></label>
                <label className="parameter-check"><input aria-label="反转色板" type="checkbox" checked={paletteReverse} onChange={(event) => setPaletteReverse(event.target.checked)} /><span>反转色板</span></label>
                <label><span>模式</span><select aria-label="色阶模式" value={colorMapMode} onChange={(event) => setColorMapMode(event.target.value)}><option value="continuous">连续</option><option value="discrete">离散</option></select></label>
                <label><span>等级数</span><input aria-label="色阶等级数" type="number" min="2" max="256" value={colorMapLevels} onChange={(event) => setColorMapLevels(event.target.valueAsNumber)} /></label>
                <label><span>缺失值颜色</span><input aria-label="缺失值颜色" type="color" value={missingColor} onChange={(event) => setMissingColor(event.target.value)} /></label>
                <details className="parameter-subsection"><summary>固定范围与中点</summary><label><span>最小值</span><input aria-label="色阶最小值" type="number" value={colorMapMinimum} onChange={(event) => setColorMapMinimum(event.target.value)} /></label><label><span>最大值</span><input aria-label="色阶最大值" type="number" value={colorMapMaximum} onChange={(event) => setColorMapMaximum(event.target.value)} /></label><label><span>中点</span><input aria-label="色阶中点" type="number" value={colorMapMidpoint} onChange={(event) => setColorMapMidpoint(event.target.value)} /></label></details>
                <label className="parameter-check"><input aria-label="显示色标" type="checkbox" checked={colorbarVisible} onChange={(event) => setColorbarVisible(event.target.checked)} /><span>显示色标</span></label>
                <label><span>色标标题</span><input aria-label="色标标题" value={colorbarTitle} onChange={(event) => setColorbarTitle(event.target.value)} /></label>
                <label><span>色标位置</span><select aria-label="色标位置" value={colorbarAnchor} onChange={(event) => setColorbarAnchor(event.target.value)}><option value="right">右侧</option><option value="bottom">底部</option></select></label>
                <label><span>色标格式</span><select aria-label="色标数值格式" value={colorbarTickFormat} onChange={(event) => setColorbarTickFormat(event.target.value)}><option value="auto">自动</option><option value="decimal">小数</option><option value="scientific">科学计数</option><option value="percent">百分比</option></select></label>
                <button className="parameter-apply" type="submit" disabled={editState === 'saving' || !selectedSeriesId || ((colorMapMinimum === '') !== (colorMapMaximum === '')) || (colorMapMidpoint !== '' && (colorMapMinimum === '' || Number(colorMapMidpoint) <= Number(colorMapMinimum) || Number(colorMapMidpoint) >= Number(colorMapMaximum)))}>应用色阶</button>
              </form>
            )}

            {parameterTab === 'uncertainty' && (
              <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyErrorStyle() }}>
                {errorParameters.has('bar_color') && <h3>误差棒</h3>}
                {errorParameters.has('bar_color') && <label><span>颜色</span><input aria-label="误差棒颜色" type="color" value={errorColor} onChange={(event) => setErrorColor(event.target.value)} /></label>}
                {errorParameters.has('bar_width_pt') && <label><span>线宽</span><div className="unit-input"><input aria-label="误差棒线宽" type="number" min="0.1" max="20" step="0.1" value={errorWidth} onChange={(event) => setErrorWidth(event.target.valueAsNumber)} /><span>pt</span></div></label>}
                {errorParameters.has('cap_size_pt') && <label><span>端帽大小</span><div className="unit-input"><input aria-label="误差棒端帽大小" type="number" min="0" max="72" step="0.5" value={errorCapSize} onChange={(event) => setErrorCapSize(event.target.valueAsNumber)} /><span>pt</span></div></label>}
                {errorParameters.has('bar_opacity') && <label><span>不透明度</span><div className="unit-input"><input aria-label="误差棒不透明度" type="range" min="0" max="1" step="0.05" value={errorOpacity} onChange={(event) => setErrorOpacity(event.target.valueAsNumber)} /><span>{Math.round(errorOpacity * 100)}%</span></div></label>}
                {[...errorParameters].some((parameter) => parameter.startsWith('band_')) && <h3>误差带</h3>}
                {errorParameters.has('band_fill_color') && <label><span>填充颜色</span><input aria-label="误差带填充颜色" type="color" value={bandFillColor} onChange={(event) => setBandFillColor(event.target.value)} /></label>}
                {errorParameters.has('band_fill_opacity') && <label><span>填充不透明度</span><div className="unit-input"><input aria-label="误差带不透明度" type="range" min="0" max="1" step="0.05" value={bandFillOpacity} onChange={(event) => setBandFillOpacity(event.target.valueAsNumber)} /><span>{Math.round(bandFillOpacity * 100)}%</span></div></label>}
                {errorParameters.has('band_stroke_color') && <label><span>边缘颜色</span><input aria-label="误差带边缘颜色" type="color" value={bandStrokeColor} onChange={(event) => setBandStrokeColor(event.target.value)} /></label>}
                {errorParameters.has('band_stroke_width_pt') && <label><span>边缘宽度</span><div className="unit-input"><input aria-label="误差带边缘宽度" type="number" min="0" max="20" step="0.1" value={bandStrokeWidth} onChange={(event) => setBandStrokeWidth(event.target.valueAsNumber)} /><span>pt</span></div></label>}
                <button className="parameter-apply" type="submit" disabled={editState === 'saving' || !selectedSeriesId}>应用误差样式</button>
              </form>
            )}

            {parameterTab === 'labels' && (
              <form className="parameter-section" onSubmit={(event) => { event.preventDefault(); void applyDataLabels() }}>
                <h3>数据标签</h3>
                <label className="parameter-check"><input aria-label="显示数据标签" type="checkbox" checked={labelsVisible} onChange={(event) => setLabelsVisible(event.target.checked)} /><span>显示数据标签</span></label>
                <label><span>数值格式</span><select aria-label="标签数值格式" value={labelFormat} onChange={(event) => setLabelFormat(event.target.value)}><option value="auto">自动</option><option value="decimal">小数</option><option value="scientific">科学计数</option><option value="percent">百分比</option></select></label>
                <label><span>位置</span><select aria-label="数据标签位置" value={labelPosition} onChange={(event) => setLabelPosition(event.target.value)}><option value="auto">自动</option><option value="above">上方</option><option value="below">下方</option><option value="left">左侧</option><option value="right">右侧</option><option value="center">居中</option></select></label>
                <label><span>前缀</span><input aria-label="数据标签前缀" value={labelPrefix} maxLength={32} onChange={(event) => setLabelPrefix(event.target.value)} /></label><label><span>后缀</span><input aria-label="数据标签后缀" value={labelSuffix} maxLength={32} onChange={(event) => setLabelSuffix(event.target.value)} /></label>
                <label><span>旋转</span><div className="unit-input"><input aria-label="数据标签旋转" type="number" min="-180" max="180" value={labelRotation} onChange={(event) => setLabelRotation(event.target.valueAsNumber)} /><span>°</span></div></label>
                <label><span>字号</span><div className="unit-input"><input aria-label="数据标签字号" type="number" min="5" max="72" step="0.5" value={labelFontSize} onChange={(event) => setLabelFontSize(event.target.valueAsNumber)} /><span>pt</span></div></label>
                <label><span>字重</span><select aria-label="数据标签字重" value={labelFontWeight} onChange={(event) => setLabelFontWeight(event.target.value)}><option value="normal">常规</option><option value="bold">粗体</option></select></label><label><span>颜色</span><input aria-label="数据标签颜色" type="color" value={labelFontColor} onChange={(event) => setLabelFontColor(event.target.value)} /></label>
                <button className="parameter-apply" type="submit" disabled={editState === 'saving' || !selectedSeriesId}>应用数据标签</button>
              </form>
            )}

            {parameterTab === 'specialist' && plot && (
              <ChartParameterEditor
                parameters={chartParameterNames}
                values={plot.chartParameters ?? {}}
                disabled={editState === 'saving'}
                onApply={(parameter, value) => applyPatch(
                  'set_chart_parameter',
                  plot.plotId,
                  { parameter, value },
                )}
              />
            )}

            {parameterTab === 'axis' && (
              <form className="parameter-operation-form" onSubmit={(event) => { event.preventDefault(); void applyAxisSettings() }}>
                <section className="parameter-section parameter-section--target">
                  <h3>作用坐标轴</h3>
                  <label><span>坐标轴</span><select aria-label="作用坐标轴" value={axisTarget} onChange={(event) => selectAxis(event.target.value as 'x' | 'y' | 'yRight')}><option value="x">X 轴</option><option value="y">左 Y 轴</option>{plot?.axisIds.yRight && <option value="yRight">右 Y 轴</option>}</select></label>
                </section>
                {(editCapabilities.has('axis_label') || editCapabilities.has('axis_scale') || editCapabilities.has('axis_range') || editCapabilities.has('axis_reverse')) && <section className="parameter-section">
                  <h3>标题与范围</h3>
                  {editCapabilities.has('axis_label') && <label><span>标题</span><input aria-label="轴标题" value={axisLabel} onChange={(event) => setAxisLabel(event.target.value)} /></label>}
                  {editCapabilities.has('axis_scale') && <label><span>尺度</span><select aria-label="轴尺度" value={axisScale} onChange={(event) => setAxisScale(event.target.value)}><option value="linear">线性</option><option value="log10">Log10</option></select></label>}
                  {editCapabilities.has('axis_range') && <details className="parameter-subsection" open><summary>显示范围</summary><label><span>最小值</span><input aria-label="轴最小值" type="number" value={axisMinimum} placeholder="自动" onChange={(event) => setAxisMinimum(event.target.value)} /></label><label><span>最大值</span><input aria-label="轴最大值" type="number" value={axisMaximum} placeholder="自动" onChange={(event) => setAxisMaximum(event.target.value)} /></label></details>}
                  {editCapabilities.has('axis_reverse') && <label className="parameter-check"><input aria-label="反向坐标轴" type="checkbox" checked={axisReverse} onChange={(event) => setAxisReverse(event.target.checked)} /><span>反向显示</span></label>}
                </section>}
                {[...editCapabilities].some((item) => item.endsWith('_visibility') || item === 'tick_direction') && <section className="parameter-section">
                  <h3>可见性与刻度</h3>
                  {editCapabilities.has('axis_title_visibility') && <label className="parameter-check"><input aria-label="显示轴标题" type="checkbox" checked={axisTitleVisible} onChange={(event) => setAxisTitleVisible(event.target.checked)} /><span>显示轴标题</span></label>}
                  {editCapabilities.has('tick_labels_visibility') && <label className="parameter-check"><input aria-label="显示刻度标签" type="checkbox" checked={tickLabelsVisible} onChange={(event) => setTickLabelsVisible(event.target.checked)} /><span>显示刻度标签</span></label>}
                  {editCapabilities.has('major_ticks_visibility') && <label className="parameter-check"><input aria-label="显示主刻度线" type="checkbox" checked={majorTicksVisible} onChange={(event) => setMajorTicksVisible(event.target.checked)} /><span>显示主刻度线</span></label>}
                  {editCapabilities.has('minor_ticks_visibility') && <label className="parameter-check"><input aria-label="显示次刻度线" type="checkbox" checked={minorTicksVisible} onChange={(event) => setMinorTicksVisible(event.target.checked)} /><span>显示次刻度线</span></label>}
                  {editCapabilities.has('axis_line_visibility') && <label className="parameter-check"><input aria-label="显示轴线" type="checkbox" checked={axisLineVisible} onChange={(event) => setAxisLineVisible(event.target.checked)} /><span>显示轴线</span></label>}
                  {editCapabilities.has('tick_direction') && <label><span>刻度线方向</span><select aria-label="刻度线方向" value={tickDirection} onChange={(event) => setTickDirection(event.target.value)}><option value="in">向内</option><option value="out">向外</option><option value="inout">内外两侧</option></select></label>}
                </section>}
                {axisParameters.has('title_font_size_pt') && <section className="parameter-section"><h3>视觉样式</h3><details className="parameter-subsection" open><summary>轴标题</summary><label><span>字号</span><div className="unit-input"><input aria-label="轴标题字号" type="number" min="5" max="72" step="0.5" value={axisTitleSize} onChange={(event) => setAxisTitleSize(event.target.valueAsNumber)} /><span>pt</span></div></label><label><span>颜色</span><input aria-label="轴标题颜色" type="color" value={axisTitleColor} onChange={(event) => setAxisTitleColor(event.target.value)} /></label></details><details className="parameter-subsection"><summary>刻度标签</summary><label><span>数值格式</span><select aria-label="刻度数值格式" value={axisTickFormat} onChange={(event) => setAxisTickFormat(event.target.value)}><option value="auto">自动</option><option value="decimal">小数</option><option value="scientific">科学计数</option><option value="percent">百分比</option><option value="date">日期</option><option value="time">时间</option></select></label><label><span>旋转</span><div className="unit-input"><input aria-label="刻度旋转" type="number" min="-180" max="180" value={axisTickRotation} onChange={(event) => setAxisTickRotation(event.target.valueAsNumber)} /><span>°</span></div></label><label><span>字号</span><div className="unit-input"><input aria-label="刻度字号" type="number" min="5" max="72" step="0.5" value={axisTickSize} onChange={(event) => setAxisTickSize(event.target.valueAsNumber)} /><span>pt</span></div></label></details><details className="parameter-subsection"><summary>轴线与网格</summary><label><span>轴线颜色</span><input aria-label="轴线颜色" type="color" value={axisLineColor} onChange={(event) => setAxisLineColor(event.target.value)} /></label><label><span>轴线宽度</span><div className="unit-input"><input aria-label="轴线宽度" type="number" min="0.1" max="20" step="0.1" value={axisLineWidth} onChange={(event) => setAxisLineWidth(event.target.valueAsNumber)} /><span>pt</span></div></label><label className="parameter-check"><input aria-label="主网格" type="checkbox" checked={majorGridVisible} onChange={(event) => setMajorGridVisible(event.target.checked)} /><span>主网格</span></label><label className="parameter-check"><input aria-label="次网格" type="checkbox" checked={minorGridVisible} onChange={(event) => setMinorGridVisible(event.target.checked)} /><span>次网格</span></label><label><span>网格颜色</span><input aria-label="网格颜色" type="color" value={gridColor} onChange={(event) => setGridColor(event.target.value)} /></label><label><span>网格线宽</span><div className="unit-input"><input aria-label="网格线宽" type="number" min="0.1" max="20" step="0.1" value={gridLineWidth} onChange={(event) => setGridLineWidth(event.target.valueAsNumber)} /><span>pt</span></div></label></details></section>}
                <div className="parameter-form-actions">{axisBoundsInvalid && <span>请填写完整且有效的范围。</span>}<button className="parameter-apply" type="submit" disabled={editState === 'saving' || !selectedAxisId || axisBoundsInvalid}>应用坐标轴设置</button></div>
              </form>
            )}

            {parameterTab === 'legend' && (
              <form className="parameter-operation-form" onSubmit={(event) => { event.preventDefault(); void applyLegendSettings() }}>
                <section className="parameter-section parameter-section--target"><h3>图例</h3></section>
                {(editCapabilities.has('legend_visibility') || editCapabilities.has('legend_position')) && <section className="parameter-section"><h3>显示与位置</h3>{editCapabilities.has('legend_visibility') && <label className="parameter-check"><input aria-label="显示图例" type="checkbox" checked={legendVisible} onChange={(event) => setLegendVisible(event.target.checked)} /><span>显示图例</span></label>}{editCapabilities.has('legend_position') && <label><span>位置</span><select aria-label="图例位置" value={legendPlacement} onChange={(event) => setLegendPlacement(event.target.value)}><option value="inside">图内</option><option value="outside_right">图外右侧</option><option value="outside_bottom">图外下方</option></select></label>}</section>}
                {legendParameters.has('columns') && <section className="parameter-section"><h3>排版与边框</h3>{legendParameters.has('title') && <label><span>标题</span><input aria-label="图例标题" value={legendTitle} onChange={(event) => setLegendTitle(event.target.value)} /></label>}<label><span>列数</span><input aria-label="图例列数" type="number" min="1" max="8" value={legendColumns} onChange={(event) => setLegendColumns(event.target.valueAsNumber)} /></label>{legendParameters.has('font_size_pt') && <label><span>字号</span><div className="unit-input"><input aria-label="图例字号" type="number" min="5" max="72" step="0.5" value={legendFontSize} onChange={(event) => setLegendFontSize(event.target.valueAsNumber)} /><span>pt</span></div></label>}{legendParameters.has('font_color') && <label><span>文字颜色</span><input aria-label="图例文字颜色" type="color" value={legendFontColor} onChange={(event) => setLegendFontColor(event.target.value)} /></label>}{legendParameters.has('frame_visible') && <label className="parameter-check"><input aria-label="图例边框" type="checkbox" checked={legendFrameVisible} onChange={(event) => setLegendFrameVisible(event.target.checked)} /><span>显示边框</span></label>}{legendFrameVisible && legendParameters.has('frame_color') && <label><span>边框颜色</span><input aria-label="图例边框颜色" type="color" value={legendFrameColor} onChange={(event) => setLegendFrameColor(event.target.value)} /></label>}</section>}
                <div className="parameter-form-actions"><button className="parameter-apply" type="submit" disabled={editState === 'saving' || !legendTargetId}>应用图例设置</button></div>
              </form>
            )}

            {editState !== 'idle' && <section className={`parameter-feedback parameter-feedback--${editState}`} aria-live="polite">
              {editState === 'saving' ? <span>正在保存…</span> : editState === 'saved' ? <span><Check size={14} />{editMessage}</span> : <span>{editMessage}</span>}
            </section>}
          </aside>
        )}
      </div>

      {!simplePanel && <footer className="thumbnail-dock">
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
      </footer>}
    </div>
  )
}
