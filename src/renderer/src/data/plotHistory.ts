import type { JsonValue } from '../../../shared/desktop-contract'
import { isJsonRecord, type ProductPlot } from './productState'

export interface PlotHistoryEntry {
  plotId: string
  label: string
  undoActions: JsonValue[]
  redoActions: JsonValue[]
}

const actionLabels: Record<string, string> = {
  bind_fields: '数据更新',
  set_title: '标题修改',
  set_axis: '坐标轴修改',
  set_series_style: '系列样式修改',
  set_legend: '图例修改',
  set_colormap: '色阶修改',
  set_error_style: '误差样式修改',
  set_data_labels: '数据标签修改',
  set_chart_parameter: '图形参数修改',
}

// These are the renderer-neutral defaults shown by FocusEditor before an explicit
// style action exists. Keeping the inverse snapshot on the same product defaults
// makes the first edit just as reversible as later edits.
const defaultSeriesStyle = {
  visible: true,
  line_stroke_color: '#2A6FDB',
  line_width_pt: 0.8,
  line_style: 'solid',
  line_opacity: 1,
  marker_shape: 'circle',
  marker_size_pt: 4.5,
  marker_interior: 'solid',
  marker_fill_color: '#2A6FDB',
  marker_stroke_color: '#2A6FDB',
  marker_stroke_width_pt: 0.8,
  marker_opacity: 1,
  fill_color: '#2A6FDB',
  fill_opacity: 0.8,
  fill_stroke_color: '#1F4F99',
  fill_stroke_width_pt: 0.8,
  fill_stroke_style: 'solid',
} as const

const historyMetadataKeys = new Set([
  'operation',
  'action_id',
  'expected_plot_version',
  'target',
  'target_alias',
])

const preciselyReversibleParameters: Readonly<Record<string, ReadonlySet<string>>> = {
  bind_fields: new Set(['data', 'bindings']),
  set_title: new Set(['text']),
  set_axis: new Set([
    'label',
    'scale',
    'reverse',
    'bounds_mode',
    'minimum',
    'maximum',
    'tick_labels_visible',
    'major_ticks_visible',
    'minor_ticks_visible',
    'tick_direction',
    'axis_line_visible',
    'axis_title_visible',
  ]),
  set_series_style: new Set([
    'visible',
    'line_stroke_color',
    'line_width_pt',
    'line_style',
    'line_opacity',
    'marker_shape',
    'marker_size_pt',
    'marker_interior',
    'marker_fill_color',
    'marker_stroke_color',
    'marker_stroke_width_pt',
    'marker_opacity',
    'fill_color',
    'fill_opacity',
    'fill_stroke_color',
    'fill_stroke_width_pt',
    'fill_stroke_style',
  ]),
  set_colormap: new Set([
    'palette',
    'reverse',
    'minimum',
    'maximum',
    'midpoint',
    'mode',
    'levels',
    'missing_color',
    'colorbar_visible',
    'colorbar_anchor',
    'colorbar_title',
    'colorbar_tick_format',
  ]),
  set_error_style: new Set([
    'bar_color',
    'bar_width_pt',
    'cap_size_pt',
    'bar_opacity',
    'band_fill_color',
    'band_fill_opacity',
    'band_stroke_color',
    'band_stroke_width_pt',
  ]),
  set_data_labels: new Set([
    'visible',
    'value_format',
    'prefix',
    'suffix',
    'position',
    'rotation_deg',
    'font_family',
    'font_size_pt',
    'font_weight',
    'font_color',
  ]),
  set_legend: new Set(['visible', 'anchor']),
  set_chart_parameter: new Set(['parameter', 'value']),
}

function hasOnlyPreciselyReversibleParameters(value: Record<string, JsonValue>, operation: string): boolean {
  const allowed = preciselyReversibleParameters[operation]
  if (allowed === undefined) return false
  return Object.entries(value).every(([key, fieldValue]) => (
    fieldValue === null || historyMetadataKeys.has(key) || allowed.has(key)
  ))
}

function reversibleAction(plot: ProductPlot, value: JsonValue): { undo: JsonValue; redo: JsonValue } | undefined {
  if (!isJsonRecord(value) || typeof value.operation !== 'string') return undefined
  if (!hasOnlyPreciselyReversibleParameters(value, value.operation)) return undefined
  const target = typeof value.target === 'string'
    ? value.target
    : typeof value.target_alias === 'string'
      ? targetFromAlias(plot, value.target_alias)
      : undefined
  if (target === undefined) return undefined
  const redo = {
    ...Object.fromEntries(Object.entries(value).filter(([key, fieldValue]) => (
      !['action_id', 'expected_plot_version', 'target_alias'].includes(key) && fieldValue !== null
    ))),
    target,
  }
  if (
    value.operation === 'bind_fields'
    && isJsonRecord(value.data)
    && Array.isArray(value.bindings)
    && value.bindings.length > 0
    && value.bindings.every(isJsonRecord)
  ) {
    return {
      undo: {
        operation: 'bind_fields',
        target,
        data: plot.engineData,
        bindings: plot.engineBindings,
      },
      redo,
    }
  }
  if (value.operation === 'set_title' && typeof value.text === 'string') {
    return { undo: { operation: 'set_title', target, text: plot.plotTitle }, redo }
  }
  if (value.operation === 'set_axis') {
    const axis = Object.values(plot.axisStates).find((candidate) => candidate?.axisId === target)
    if (!axis) return undefined
    const undo: Record<string, JsonValue> = { operation: 'set_axis', target }
    if (typeof value.label === 'string') undo.label = axis.label
    if (typeof value.scale === 'string') undo.scale = axis.scale
    if (typeof value.reverse === 'boolean') undo.reverse = axis.reverse
    const visibilityMappings = {
      tick_labels_visible: axis.tickLabelsVisible,
      major_ticks_visible: axis.majorTicksVisible,
      minor_ticks_visible: axis.minorTicksVisible,
      tick_direction: axis.tickDirection,
      axis_line_visible: axis.axisLineVisible,
      axis_title_visible: axis.axisTitleVisible,
    } as const
    for (const [key, previous] of Object.entries(visibilityMappings)) {
      if (Object.hasOwn(value, key) && value[key] !== null) undo[key] = previous
    }
    if (typeof value.minimum === 'number' || typeof value.maximum === 'number') {
      if (axis.minimum === undefined || axis.maximum === undefined) {
        undo.bounds_mode = 'automatic'
      } else {
        undo.bounds_mode = 'fixed'
        undo.minimum = axis.minimum
        undo.maximum = axis.maximum
      }
    } else if (value.bounds_mode === 'automatic' || value.bounds_mode === 'fixed') {
      if (axis.minimum === undefined || axis.maximum === undefined) {
        undo.bounds_mode = 'automatic'
      } else {
        undo.bounds_mode = 'fixed'
        undo.minimum = axis.minimum
        undo.maximum = axis.maximum
      }
    }
    return Object.keys(undo).length > 2 ? { undo, redo } : undefined
  }
  if (value.operation === 'set_series_style') {
    const style = plot.seriesStyles.find((candidate) => candidate.seriesId === target)?.style
    if (!style) return undefined
    const mappings = {
      visible: style.visible ?? defaultSeriesStyle.visible,
      line_stroke_color: style.lineStrokeColor ?? defaultSeriesStyle.line_stroke_color,
      line_width_pt: style.lineWidthPt ?? defaultSeriesStyle.line_width_pt,
      line_style: style.lineStyle ?? defaultSeriesStyle.line_style,
      line_opacity: style.lineOpacity ?? defaultSeriesStyle.line_opacity,
      marker_shape: style.markerShape ?? defaultSeriesStyle.marker_shape,
      marker_size_pt: style.markerSizePt ?? defaultSeriesStyle.marker_size_pt,
      marker_interior: style.markerInterior ?? defaultSeriesStyle.marker_interior,
      marker_fill_color: style.markerFillColor ?? defaultSeriesStyle.marker_fill_color,
      marker_stroke_color: style.markerStrokeColor ?? defaultSeriesStyle.marker_stroke_color,
      marker_stroke_width_pt: style.markerStrokeWidthPt ?? defaultSeriesStyle.marker_stroke_width_pt,
      marker_opacity: style.markerOpacity ?? defaultSeriesStyle.marker_opacity,
      fill_color: style.fillColor ?? defaultSeriesStyle.fill_color,
      fill_opacity: style.fillOpacity ?? defaultSeriesStyle.fill_opacity,
      fill_stroke_color: style.fillStrokeColor ?? defaultSeriesStyle.fill_stroke_color,
      fill_stroke_width_pt: style.fillStrokeWidthPt ?? defaultSeriesStyle.fill_stroke_width_pt,
      fill_stroke_style: style.fillStrokeStyle ?? defaultSeriesStyle.fill_stroke_style,
    } as const
    const undo: Record<string, JsonValue> = { operation: 'set_series_style', target }
    for (const [key, previous] of Object.entries(mappings)) {
      if (!Object.hasOwn(value, key) || value[key] === null) continue
      if (previous === undefined) return undefined
      undo[key] = previous
    }
    return Object.keys(undo).length > 2 ? { undo, redo } : undefined
  }
  if (value.operation === 'set_colormap') {
    const state = plot.colorMaps.find((candidate) => candidate.seriesId === target)
    if (!state) return undefined
    const mappings = {
      palette: state.palette,
      reverse: state.reverse,
      minimum: state.minimum,
      maximum: state.maximum,
      midpoint: state.midpoint,
      mode: state.mode,
      levels: state.levels,
      missing_color: state.missingColor,
      colorbar_visible: state.colorbarVisible,
      colorbar_anchor: state.colorbarAnchor,
      colorbar_title: state.colorbarTitle,
      colorbar_tick_format: state.colorbarTickFormat,
    } as const
    const undo: Record<string, JsonValue> = { operation: 'set_colormap', target }
    for (const [key, previous] of Object.entries(mappings)) {
      if (!Object.hasOwn(value, key) || value[key] === null) continue
      if (previous === undefined) return undefined
      undo[key] = previous
    }
    return Object.keys(undo).length > 2 ? { undo, redo } : undefined
  }
  if (value.operation === 'set_error_style') {
    const state = plot.errorStyles.find((candidate) => candidate.seriesId === target)
    if (!state) return undefined
    const mappings = {
      bar_color: state.barColor,
      bar_width_pt: state.barWidthPt,
      cap_size_pt: state.capSizePt,
      bar_opacity: state.barOpacity,
      band_fill_color: state.bandFillColor,
      band_fill_opacity: state.bandFillOpacity,
      band_stroke_color: state.bandStrokeColor,
      band_stroke_width_pt: state.bandStrokeWidthPt,
    } as const
    const undo: Record<string, JsonValue> = { operation: 'set_error_style', target }
    for (const [key, previous] of Object.entries(mappings)) {
      if (!Object.hasOwn(value, key) || value[key] === null) continue
      if (previous === undefined) return undefined
      undo[key] = previous
    }
    return Object.keys(undo).length > 2 ? { undo, redo } : undefined
  }
  if (value.operation === 'set_data_labels') {
    const state = plot.dataLabelStyles.find((candidate) => candidate.seriesId === target)
    if (!state) return undefined
    const mappings = {
      visible: state.visible,
      value_format: state.valueFormat,
      prefix: state.prefix,
      suffix: state.suffix,
      position: state.position,
      rotation_deg: state.rotationDeg,
      font_family: state.fontFamily,
      font_size_pt: state.fontSizePt,
      font_weight: state.fontWeight,
      font_color: state.fontColor,
    } as const
    const undo: Record<string, JsonValue> = { operation: 'set_data_labels', target }
    for (const [key, previous] of Object.entries(mappings)) {
      if (!Object.hasOwn(value, key) || value[key] === null) continue
      if (previous === undefined) return undefined
      undo[key] = previous
    }
    return Object.keys(undo).length > 2 ? { undo, redo } : undefined
  }
  if (value.operation === 'set_legend') {
    const undo: Record<string, JsonValue> = { operation: 'set_legend', target }
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
      undo: { operation: 'set_chart_parameter', target, parameter: value.parameter, value: previous },
      redo,
    }
  }
  return undefined
}

function targetFromAlias(plot: ProductPlot, alias: string): string | undefined {
  if (alias === 'plot') return plot.plotId
  if (alias === 'x_axis') return plot.axisIds.x
  if (alias === 'y_axis') return plot.axisIds.y
  if (alias === 'right_y_axis') return plot.axisIds.yRight
  if (alias === 'legend') return plot.legendId
  const seriesMatch = /^series_(\d+)$/.exec(alias)
  if (seriesMatch === null) return undefined
  const position = Number.parseInt(seriesMatch[1], 10) - 1
  return position < 0 ? undefined : plot.seriesIds[position]
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
    label: operations.length === 1
      ? actionLabels[operations[0]] ?? '图形修改'
      : operations.includes('bind_fields')
        ? '数据与图形修改'
        : `${operations.length} 项图形修改`,
    undoActions: reversible.flatMap((item) => item ? [item.undo] : []).reverse(),
    redoActions: reversible.flatMap((item) => item ? [item.redo] : []),
  }
}
