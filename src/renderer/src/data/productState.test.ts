import { describe, expect, it } from 'vitest'

import { readPlot } from './productState'

describe('product plot state', () => {
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
          { scale_id: 'scale:x', kind: 'linear', axis_range: { minimum: null, maximum: null, reverse: false } },
          { scale_id: 'scale:y', kind: 'log10', axis_range: { minimum: 0.1, maximum: 100, reverse: false } },
          { scale_id: 'scale:y_right', kind: 'linear', axis_range: { minimum: 4, maximum: 9, reverse: true } },
        ],
        axes: [
          { axis_id: 'axis:x', scale_id: 'scale:x', orientation: 'x', position: 'bottom', label: { nodes: [{ kind: 'plain', text: 'Time' }] } },
          { axis_id: 'axis:y', scale_id: 'scale:y', orientation: 'y', position: 'left', label: { nodes: [{ kind: 'plain', text: 'Signal' }] } },
          { axis_id: 'axis:y_right', scale_id: 'scale:y_right', orientation: 'y', position: 'right', label: { nodes: [{ kind: 'plain', text: 'Temperature' }] } },
        ],
        legend: { visible: false, placement: 'outside_right' },
        publication_profile: {
          physical_size: { width: { value: 720, unit: 'pt' }, height: { value: 100, unit: 'mm' } },
        },
      },
    })

    expect(plot).toMatchObject({
      plotId: 'plot:test',
      plotVersion: 3,
      chartId: 'K02',
      projectVersion: 7,
      seriesIds: ['series:test.0'],
      axisIds: { x: 'axis:x', y: 'axis:y', yRight: 'axis:y_right' },
      axisStates: {
        x: { axisId: 'axis:x', label: 'Time', scale: 'linear', reverse: false },
        y: { axisId: 'axis:y', label: 'Signal', scale: 'log10', minimum: 0.1, maximum: 100, reverse: false },
        yRight: { axisId: 'axis:y_right', label: 'Temperature', scale: 'linear', minimum: 4, maximum: 9, reverse: true },
      },
      canvasSizeMm: { width: 254, height: 100 },
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
})
