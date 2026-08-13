import { describe, expect, it } from 'vitest'

import type { ProductPlot } from './productState'
import { plotHistoryEntry } from './plotHistory'

const plot = {
  plotId: 'plot:one',
  plotVersion: 3,
  chartId: 'K01',
  plotTitle: '旧标题',
  fontSizePt: 9,
  projectVersion: 4,
  seriesIds: ['series:one'],
  seriesStyles: [{ seriesId: 'series:one', style: { color: '#112233', lineWidthPt: 1 } }],
  axisIds: { y: 'axis:y' },
  axisStates: { y: { axisId: 'axis:y', label: 'Value', scale: 'linear', reverse: false, numberFormat: 'auto', decimalPlaces: 2 } },
  canvasSizeMm: { width: 183, height: 120 },
  annotations: [],
  specialist: {},
  style: { legendVisible: true, legendPlacement: 'inside' },
} as unknown as ProductPlot

describe('plot history', () => {
  it('builds inverse actions for declarative edits', () => {
    expect(plotHistoryEntry(plot, [
      { operation: 'set_title', target: 'plot:one', text: '新标题' },
      { operation: 'set_axis', target: 'axis:y', scale: 'log10' },
    ])).toMatchObject({
      plotId: 'plot:one',
      undoActions: [
        { operation: 'set_axis', target: 'axis:y', scale: 'linear' },
        { operation: 'set_title', target: 'plot:one', text: '旧标题' },
      ],
    })
  })

  it('does not claim undo when the previous native default is unknown', () => {
    expect(plotHistoryEntry(plot, [{ operation: 'set_series_style', target: 'series:one', symbol: 'circle' }]))
      .toBeUndefined()
    expect(plotHistoryEntry(plot, [{ operation: 'add_annotation', target: 'plot:one', text: 'x' }]))
      .toBeUndefined()
  })
})
