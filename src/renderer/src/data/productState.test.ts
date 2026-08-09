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
    })
    expect(readImportSummary(value)).toEqual({
      fileCount: 2,
      committedCount: 1,
      attentionCount: 0,
      failedCount: 1,
      failedFiles: ['损坏.csv'],
    })
  })

  it('reads versioned style targets from the nested desktop PlotSpec response', () => {
    const plot = readPlot({
      project_version: 7,
      artifact: {
        resourceId: 'resource:preview',
        kind: 'preview',
        url: 'plotagent-resource://preview/plot-test.png',
      },
      spec: {
        plot_id: 'plot:test',
        plot_version: 3,
        chart_type_id: 'K02',
        series: [
          {
            series_id: 'series:test.0',
            style: {
              color: { value: '#123456' },
              line_width: { value: 1.5, unit: 'pt' },
              marker_size: { value: 7, unit: 'pt' },
              line_style: 'dashed',
              symbol: { shape: 'diamond', interior: 'hollow' },
              palette: null,
            },
          },
        ],
        scales: [
          { scale_id: 'scale:x', kind: 'linear', axis_range: { minimum: null, maximum: null, reverse: false }, ticks: { major_interval: null, number_format: 'auto', decimal_places: 2 } },
          { scale_id: 'scale:y', kind: 'log10', axis_range: { minimum: 0.1, maximum: 100, reverse: false }, ticks: { major_interval: 10, number_format: 'scientific', decimal_places: 1 } },
          { scale_id: 'scale:y_right', kind: 'linear', axis_range: { minimum: 4, maximum: 9, reverse: true } },
        ],
        axes: [
          { axis_id: 'axis:x', scale_id: 'scale:x', orientation: 'x', position: 'bottom', label: { nodes: [{ kind: 'plain', text: 'Time' }] } },
          { axis_id: 'axis:y', scale_id: 'scale:y', orientation: 'y', position: 'left', label: { nodes: [{ kind: 'plain', text: 'Signal' }] } },
          { axis_id: 'axis:y_right', scale_id: 'scale:y_right', orientation: 'y', position: 'right', label: { nodes: [{ kind: 'plain', text: 'Temperature' }] } },
        ],
        legend: { visible: false, placement: 'outside_right' },
        title: { nodes: [{ kind: 'plain', text: 'Persisted title' }] },
        resolved_style: { font_size: { value: 11, unit: 'pt' } },
        annotations: [{ annotation_id: 'annotation:test', kind: 'reference_line', text: null, x: null, y: 5, x2: null, y2: null }],
        publication_profile: {
          physical_size: { width: { value: 720, unit: 'pt' }, height: { value: 100, unit: 'mm' } },
        },
      },
    })

    expect(plot).toMatchObject({
      plotId: 'plot:test',
      plotVersion: 3,
      chartId: 'K02',
      plotTitle: 'Persisted title',
      fontSizePt: 11,
      projectVersion: 7,
      seriesIds: ['series:test.0'],
      axisIds: { x: 'axis:x', y: 'axis:y', yRight: 'axis:y_right' },
      axisStates: {
        x: { axisId: 'axis:x', label: 'Time', scale: 'linear', reverse: false, numberFormat: 'auto', decimalPlaces: 2 },
        y: { axisId: 'axis:y', label: 'Signal', scale: 'log10', minimum: 0.1, maximum: 100, reverse: false, majorInterval: 10, numberFormat: 'scientific', decimalPlaces: 1 },
        yRight: { axisId: 'axis:y_right', label: 'Temperature', scale: 'linear', minimum: 4, maximum: 9, reverse: true, numberFormat: 'auto', decimalPlaces: 2 },
      },
      canvasSizeMm: { width: 254, height: 100 },
      annotations: [{ annotationId: 'annotation:test', kind: 'reference_line', text: '', y: 5 }],
      style: { legendVisible: false, legendPlacement: 'outside_right' },
    })
    expect(plot?.seriesStyles[0]?.style).toEqual({
      color: '#123456',
      lineWidthPt: 1.5,
      markerSizePt: 7,
      lineStyle: 'dashed',
      symbolShape: 'diamond',
      symbolInterior: 'hollow',
    })
    expect(plot?.preview?.url).toBe('plotagent-resource://preview/plot-test.png')
  })

  it('preserves the Core commit order when reading the latest plot per object', () => {
    const plots = readPlots({
      project_version: 9,
      plots: [
        { plot_id: 'plot:zeta', plot_version: 4, chart_type_id: 'K01' },
        { plot_id: 'plot:alpha', plot_version: 2, chart_type_id: 'K02' },
      ],
    })

    expect(plots.map((plot) => `${plot.plotId}@${plot.plotVersion}`)).toEqual([
      'plot:zeta@4',
      'plot:alpha@2',
    ])
    expect(plots.at(-1)?.chartId).toBe('K02')
  })
})
