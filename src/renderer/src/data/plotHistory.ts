import type { JsonValue } from '../../../shared/desktop-contract'
import { isJsonRecord, type ProductPlot } from './productState'

export interface PlotHistoryEntry {
  plotId: string
  label: string
  undoPlotVersion: number
  redoPlotVersion: number
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

/**
 * Record exact immutable plot snapshots instead of synthesizing inverse style
 * actions. Renderer defaults differ by profile and backend; only versioned
 * snapshot restore can preserve them without guessing.
 */
export function plotHistoryEntry(
  before: ProductPlot,
  after: ProductPlot,
  actions: readonly JsonValue[],
): PlotHistoryEntry | undefined {
  if (
    actions.length === 0
    || before.plotId !== after.plotId
    || after.plotVersion <= before.plotVersion
  ) return undefined
  const operations = actions.flatMap((action) => (
    isJsonRecord(action) && typeof action.operation === 'string' ? [action.operation] : []
  ))
  if (operations.length === 0) return undefined
  return {
    plotId: before.plotId,
    label: operations.length === 1
      ? actionLabels[operations[0]] ?? '图形修改'
      : operations.includes('bind_fields')
        ? '数据与图形修改'
        : `${operations.length} 项图形修改`,
    undoPlotVersion: before.plotVersion,
    redoPlotVersion: after.plotVersion,
  }
}
