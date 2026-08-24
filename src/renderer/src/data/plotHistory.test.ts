import { describe, expect, it } from 'vitest'

import type { ProductPlot } from './productState'
import { plotHistoryEntry } from './plotHistory'

const before = {
  plotId: 'plot:one',
  plotVersion: 3,
  chartId: 'K03',
} as ProductPlot

const after = {
  ...before,
  plotVersion: 7,
} as ProductPlot

describe('plot history', () => {
  it('records exact source and result versions for a compound edit', () => {
    expect(plotHistoryEntry(before, after, [
      { operation: 'set_title', target: 'plot:one', text: '新标题' },
      { operation: 'set_axis', target: 'axis:one.x', bounds_mode: 'fixed', minimum: 9, maximum: 13 },
      { operation: 'set_axis', target: 'axis:one.y', label: '治疗后数值' },
      { operation: 'set_legend', target: 'legend:one.main', visible: false },
    ])).toEqual({
      plotId: 'plot:one',
      label: '4 项图形修改',
      undoPlotVersion: 3,
      redoPlotVersion: 7,
    })
  })

  it('keeps data-and-plot labeling while snapshotting data updates', () => {
    expect(plotHistoryEntry(before, after, [
      { operation: 'bind_fields', target: 'plot:one' },
      { operation: 'set_title', target: 'plot:one', text: '更新后' },
    ])).toMatchObject({
      label: '数据与图形修改',
      undoPlotVersion: 3,
      redoPlotVersion: 7,
    })
  })

  it('does not create history for no-op, cross-plot, or non-forward results', () => {
    expect(plotHistoryEntry(before, after, [])).toBeUndefined()
    expect(plotHistoryEntry(before, { ...after, plotId: 'plot:two' }, [
      { operation: 'set_title' },
    ])).toBeUndefined()
    expect(plotHistoryEntry(before, { ...after, plotVersion: 3 }, [
      { operation: 'set_title' },
    ])).toBeUndefined()
  })
})
