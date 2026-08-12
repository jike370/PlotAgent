import type { JsonValue } from '../../../shared/desktop-contract'
import { isJsonRecord, type ProductPlot } from './productState'

export interface PlotHistoryEntry {
  plotId: string
  label: string
  undoActions: JsonValue[]
  redoActions: JsonValue[]
}

const actionLabels: Record<string, string> = {
  set_title: '标题修改',
  set_axis: '坐标轴修改',
  set_series_style: '系列样式修改',
  set_legend: '图例修改',
  set_chart_parameter: '图形参数修改',
}

function reversibleAction(plot: ProductPlot, value: JsonValue): { undo: JsonValue; redo: JsonValue } | undefined {
  if (!isJsonRecord(value) || typeof value.operation !== 'string' || typeof value.target !== 'string') return undefined
  const redo = Object.fromEntries(Object.entries(value).filter(([key]) => !['action_id', 'expected_plot_version'].includes(key)))
  if (value.operation === 'set_title' && typeof value.text === 'string') {
    return { undo: { operation: 'set_title', target: value.target, text: plot.plotTitle }, redo }
  }
  if (value.operation === 'set_axis') {
    const axis = Object.values(plot.axisStates).find((candidate) => candidate?.axisId === value.target)
    if (!axis) return undefined
    const undo: Record<string, JsonValue> = { operation: 'set_axis', target: value.target }
    if (typeof value.label === 'string') undo.label = axis.label
    if (typeof value.scale === 'string') undo.scale = axis.scale
    if (typeof value.reverse === 'boolean') undo.reverse = axis.reverse
    if (typeof value.minimum === 'number' || typeof value.maximum === 'number') {
      if (axis.minimum === undefined || axis.maximum === undefined) return undefined
      undo.minimum = axis.minimum
      undo.maximum = axis.maximum
    }
    return Object.keys(undo).length > 2 ? { undo, redo } : undefined
  }
  if (value.operation === 'set_series_style') {
    const style = plot.seriesStyles.find((candidate) => candidate.seriesId === value.target)?.style
    if (!style) return undefined
    const mappings = {
      color: style.color,
      line_width_pt: style.lineWidthPt,
      symbol_size_pt: style.markerSizePt,
      line_style: style.lineStyle,
      symbol: style.symbolShape,
      symbol_interior: style.symbolInterior,
      palette_id: style.paletteId,
      palette_reverse: style.paletteReverse,
    } as const
    const undo: Record<string, JsonValue> = { operation: 'set_series_style', target: value.target }
    for (const [key, previous] of Object.entries(mappings)) {
      if (!Object.hasOwn(value, key)) continue
      if (previous === undefined) return undefined
      undo[key] = previous
    }
    return Object.keys(undo).length > 2 ? { undo, redo } : undefined
  }
  if (value.operation === 'set_legend') {
    const undo: Record<string, JsonValue> = { operation: 'set_legend', target: value.target }
    if (typeof value.visible === 'boolean') {
      if (plot.style.legendVisible === undefined) return undefined
      undo.visible = plot.style.legendVisible
    }
    if (typeof value.anchor === 'string') {
      if (plot.style.legendPlacement === undefined) return undefined
      undo.anchor = plot.style.legendPlacement
    }
    return Object.keys(undo).length > 2 ? { undo, redo } : undefined
  }
  if (value.operation === 'set_chart_parameter' && typeof value.parameter === 'string') {
    const previous = plot.chartParameters?.[value.parameter]
    if (previous === undefined) return undefined
    return {
      undo: { operation: 'set_chart_parameter', target: value.target, parameter: value.parameter, value: previous },
      redo,
    }
  }
  return undefined
}

export function plotHistoryEntry(
  plot: ProductPlot,
  actions: readonly JsonValue[],
): PlotHistoryEntry | undefined {
  if (actions.length === 0) return undefined
  const reversible = actions.map((action) => reversibleAction(plot, action))
  if (reversible.some((item) => item === undefined)) return undefined
  const operations = actions.flatMap((action) => isJsonRecord(action) && typeof action.operation === 'string' ? [action.operation] : [])
  return {
    plotId: plot.plotId,
    label: operations.length === 1 ? actionLabels[operations[0]] ?? '图形修改' : `${operations.length} 项图形修改`,
    undoActions: reversible.flatMap((item) => item ? [item.undo] : []).reverse(),
    redoActions: reversible.flatMap((item) => item ? [item.redo] : []),
  }
}
