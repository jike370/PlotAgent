import { describe, expect, it } from 'vitest'

import engineProfileCatalog from '../../../shared/generated/engine-profile-catalog.json'
import type { JsonValue } from '../../../shared/desktop-contract'
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
  seriesStyles: [{
    seriesId: 'series:one',
    style: { lineStrokeColor: '#112233', lineWidthPt: 1 },
  }],
  colorMaps: [{ seriesId: 'series:one' }],
  errorStyles: [{ seriesId: 'series:one' }],
  dataLabelStyles: [{ seriesId: 'series:one' }],
  axisIds: { y: 'axis:y' },
  legendId: 'legend:one',
  axisStates: { y: { axisId: 'axis:y', label: 'Value', scale: 'linear', reverse: false, tickLabelsVisible: true, majorTicksVisible: true, minorTicksVisible: true, tickDirection: 'out', axisLineVisible: true, axisTitleVisible: true, numberFormat: 'auto', decimalPlaces: 2 } },
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

  it('uses the documented editor default when the first style edit has no prior action', () => {
    expect(plotHistoryEntry(plot, [{
      operation: 'set_series_style', target: 'series:one', marker_shape: 'circle',
    }])).toMatchObject({
      undoActions: [{
        operation: 'set_series_style', target: 'series:one', marker_shape: 'circle',
      }],
    })
    expect(plotHistoryEntry(plot, [{
      operation: 'set_series_style', target: 'series:one', marker_size_pt: 8,
    }])).toMatchObject({
      undoActions: [{
        operation: 'set_series_style', target: 'series:one', marker_size_pt: 4.5,
      }],
    })
    expect(plotHistoryEntry(plot, [{ operation: 'add_annotation', target: 'plot:one', text: 'x' }]))
      .toBeUndefined()
  })

  it('ignores nullable optional fields emitted by an Agent style action', () => {
    expect(plotHistoryEntry(plot, [{
      operation: 'set_series_style',
      target: 'series:one',
      line_stroke_color: '#ff0000',
      line_style: null,
      line_width_pt: null,
      marker_shape: null,
      marker_size_pt: null,
    }])).toMatchObject({
      undoActions: [{
        operation: 'set_series_style', target: 'series:one', line_stroke_color: '#112233',
      }],
      redoActions: [{
        operation: 'set_series_style', target: 'series:one', line_stroke_color: '#ff0000',
      }],
    })
  })

  it('reverses axis and series visibility edits', () => {
    expect(plotHistoryEntry(plot, [{
      operation: 'set_axis',
      target: 'axis:y',
      tick_labels_visible: false,
      tick_direction: 'inout',
      axis_line_visible: false,
    }])).toMatchObject({
      undoActions: [{
        operation: 'set_axis',
        target: 'axis:y',
        tick_labels_visible: true,
        tick_direction: 'out',
        axis_line_visible: true,
      }],
    })
    expect(plotHistoryEntry(plot, [{
      operation: 'set_series_style', target: 'series:one', visible: false,
    }])).toMatchObject({
      undoActions: [{
        operation: 'set_series_style', target: 'series:one', visible: true,
      }],
    })
  })

  it('refuses a partial undo when an action contains parameters without an exact inverse', () => {
    expect(plotHistoryEntry(plot, [{
      operation: 'set_title', target: 'plot:one', text: '新标题', font_size_pt: 14,
    }])).toBeUndefined()
    expect(plotHistoryEntry(plot, [{
      operation: 'set_axis', target: 'axis:y', label: 'Intensity', major_grid_visible: true,
    }])).toBeUndefined()
    expect(plotHistoryEntry(plot, [{
      operation: 'set_legend', target: 'legend:one', visible: false, columns: 2, title: 'Groups',
    }])).toBeUndefined()
  })

  it('constructs the basic reversible edit history for every formal chart profile', () => {
    expect(engineProfileCatalog.profiles).toHaveLength(34)
    for (const profile of engineProfileCatalog.profiles) {
      const profilePlot = {
        ...plot,
        chartId: profile.profile_id,
      } as ProductPlot
      const actions: JsonValue[] = [
        { operation: 'set_title', target: 'plot:one', text: `${profile.profile_id} title` },
        { operation: 'set_axis', target: 'axis:y', label: 'Signal' },
        { operation: 'set_series_style', target: 'series:one', visible: false },
        ...(profile.capabilities.some((capability) => capability.operation === 'set_legend')
          ? [{ operation: 'set_legend', target: 'legend:one', anchor: 'right' }]
          : []),
      ]
      const entry = plotHistoryEntry(profilePlot, actions)
      expect(entry, profile.profile_id).toBeDefined()
      expect(entry?.undoActions, profile.profile_id).toHaveLength(actions.length)
      expect(entry?.redoActions, profile.profile_id).toHaveLength(actions.length)
    }
  })
})
