import { describe, expect, it } from 'vitest'

import type { JsonValue } from '../../../shared/desktop-contract'
import { readDatasets, readImportSummary, readPlot, readPlots } from './productState'

describe('product plot state', () => {
  it('prefers file and worksheet identity and summarizes per-file import outcomes', () => {
    const value: JsonValue = {
      imports: [
        {
          kind: 'committed',
          source_file_name: '仪器记录.xlsx',
          datasets: [{
            source_dataset_id: 'source:opaque',
            source_file_name: '仪器记录.xlsx',
            source_sheet_name: '动力学',
            source_version: 1,
            row_count: 2,
            field_count: 1,
            fields: [{ field_id: 'field:x', name: 'Time_s', logical_type: 'numeric', physical_type: 'float64', unit: { symbol: 's' } }],
            sample_rows: [[1], [2]],
            quality: {},
            source_coordinate_kinds: ['excel'],
          }],
        },
        { kind: 'failed', source_file_name: '损坏.csv', error: { message: '无法解析' } },
      ],
    }

    expect(readDatasets(value)[0]).toMatchObject({
      datasetId: 'source:opaque',
      displayName: '仪器记录.xlsx > 动力学',
      sourceFileName: '仪器记录.xlsx',
      sourceSheetName: '动力学',
      sampleRows: [[1], [2]],
    })
    expect(readImportSummary(value)).toEqual({
      fileCount: 2,
      committedCount: 1,
      attentionCount: 0,
      failedCount: 1,
      failedFiles: ['损坏.csv'],
    })
  })

  it('reads semantic objects, public actions, and capabilities from PlotDocument', () => {
    const plot = readPlot({
      project_version: 7,
      preview: {
        resourceId: 'resource:preview',
        kind: 'preview',
        url: 'plotagent-resource://preview/plot-test.png',
      },
      document: {
        plot_id: 'plot:test',
        plot_version: 3,
        profile_id: 'K02',
      },
      profile: {
        profile_id: 'K02',
        objects: [
          { object_alias: 'x_axis', object_kind: 'axis', object_key: 'x' },
          { object_alias: 'y_axis', object_kind: 'axis', object_key: 'y' },
          { object_alias: 'series_1', object_kind: 'series', object_key: 'primary' },
          { object_alias: 'legend', object_kind: 'legend', object_key: 'main' },
        ],
        capabilities: [
          { operation: 'set_title', parameters: ['text'] },
          { operation: 'set_axis', parameters: ['label', 'scale', 'bounds', 'reverse'] },
          { operation: 'set_series_style', parameters: ['color', 'line_width_pt', 'line_style', 'symbol', 'symbol_size_pt'] },
          { operation: 'set_legend', parameters: ['visible', 'anchor'] },
          { operation: 'add_annotation', parameters: ['text'] },
        ],
      },
      actions: [
        { operation: 'set_title', target: 'plot:test', text: 'Persisted title' },
        { operation: 'set_axis', target: 'axis:test.x', label: 'Time' },
        { operation: 'set_axis', target: 'axis:test.y', label: 'Signal', scale: 'log10', minimum: 0.1, maximum: 100 },
        { operation: 'set_series_style', target: 'series:test.primary', color: '#123456', line_width_pt: 1.5, symbol_size_pt: 7, line_style: 'dash', symbol: 'diamond' },
        { operation: 'set_legend', target: 'legend:test.main', visible: false, anchor: 'right' },
        { operation: 'add_annotation', target: 'plot:test', annotation_id: 'annotation:test', text: 'Peak', x: 2, y: 5 },
      ],
    })

    expect(plot).toMatchObject({
      plotId: 'plot:test',
      plotVersion: 3,
      chartId: 'K02',
      plotTitle: 'Persisted title',
      fontSizePt: 9,
      projectVersion: 7,
      seriesIds: ['series:test.primary'],
      axisIds: { x: 'axis:test.x', y: 'axis:test.y' },
      axisStates: {
        x: { axisId: 'axis:test.x', label: 'Time', scale: 'linear', reverse: false },
        y: { axisId: 'axis:test.y', label: 'Signal', scale: 'log10', minimum: 0.1, maximum: 100, reverse: false },
      },
      canvasSizeMm: { width: 183, height: 120 },
      annotations: [{ annotationId: 'annotation:test', kind: 'text', text: 'Peak', x: 2, y: 5 }],
      style: { legendVisible: false, legendPlacement: 'right' },
    })
    expect(plot?.seriesStyles[0]?.style).toEqual({
      color: '#123456',
      lineWidthPt: 1.5,
      markerSizePt: 7,
      lineStyle: 'dash',
      symbolShape: 'diamond',
    })
    expect(plot?.engineCapabilities?.set_axis).toEqual(['label', 'scale', 'bounds', 'reverse'])
    expect(plot?.preview?.url).toBe('plotagent-resource://preview/plot-test.png')
  })

  it('preserves the Core commit order when reading the latest plot per object', () => {
    const plots = readPlots({
      project_version: 9,
      plots: [
        {
          document: { plot_id: 'plot:zeta', plot_version: 4, profile_id: 'K01' },
          profile: { profile_id: 'K01', objects: [], capabilities: [] },
          actions: [],
        },
        {
          document: { plot_id: 'plot:alpha', plot_version: 2, profile_id: 'K02' },
          profile: { profile_id: 'K02', objects: [], capabilities: [] },
          actions: [],
        },
      ],
    })

    expect(plots.map((plot) => `${plot.plotId}@${plot.plotVersion}`)).toEqual([
      'plot:zeta@4',
      'plot:alpha@2',
    ])
    expect(plots.at(-1)?.chartId).toBe('K02')
  })
})
