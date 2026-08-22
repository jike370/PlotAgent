import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { JsonValue } from '../../../shared/desktop-contract'
import type { ProductPlot } from '../data/productState'
import { FocusEditor } from './FocusEditor'

function plot(
  chartId: string,
  capabilities: Readonly<Record<string, readonly string[]>> = {},
): ProductPlot & { title: string } {
  return {
    title: '测试图',
    plotId: 'plot:test',
    plotVersion: 3,
    chartId,
    engineData: {
      kind: 'source', dataset_id: 'source:test', version: 1,
      content_hash: 'a'.repeat(64),
    },
    engineBindings: [
      { role: 'x', field_id: 'field:x' },
      { role: 'y', field_id: 'field:y' },
    ],
    plotTitle: '已保存标题',
    fontSizePt: 10,
    projectVersion: 4,
    seriesIds: ['series:test.primary'],
    seriesStyles: [{ seriesId: 'series:test.primary', style: {} }],
    colorMaps: [{ seriesId: 'series:test.primary' }],
    errorStyles: [{ seriesId: 'series:test.primary' }],
    dataLabelStyles: [{ seriesId: 'series:test.primary' }],
    axisIds: { x: 'axis:test.x', y: 'axis:test.y' },
    axisStates: {
      x: { axisId: 'axis:test.x', label: 'Time', scale: 'linear', reverse: false, tickLabelsVisible: true, majorTicksVisible: true, minorTicksVisible: true, tickDirection: 'out', axisLineVisible: true, axisTitleVisible: true, numberFormat: 'auto', decimalPlaces: 2 },
      y: { axisId: 'axis:test.y', label: 'Signal', scale: 'log10', minimum: 0.1, maximum: 100, reverse: false, tickLabelsVisible: true, majorTicksVisible: true, minorTicksVisible: true, tickDirection: 'out', axisLineVisible: true, axisTitleVisible: true, numberFormat: 'auto', decimalPlaces: 2 },
    },
    canvasSizeMm: { width: 183, height: 120 },
    annotations: [],
    specialist: {
      barArea: { edgeWidthPt: 0.5, widthRatio: 0.8, alpha: 1 },
      uncertainty: { lineWidthPt: 0.8, capSizePt: 4, bandAlpha: 0.25 },
      colorbar: { visible: true, title: '', levels: 7 },
      dualY: { axisWidthPt: 0.8 },
      facet: { order: [], labels: [], gapMm: 4, sharedX: true, sharedY: true, commonLegend: true },
      yOffset: { order: [] },
      chartParameters: {
        stepWhere: 'post',
        volcanoAbsoluteLog2FoldChange: 1,
        volcanoPvalue: 0.05,
        paretoReferencePercent: 80,
      },
    },
    style: { legendVisible: true, legendPlacement: 'inside' },
    engineCapabilities: capabilities,
  }
}

const commonCapabilities = {
  set_title: ['text'],
  set_series_style: [
    'visible', 'line_stroke_color', 'line_width_pt', 'line_style', 'marker_shape', 'marker_size_pt',
  ],
  set_axis: ['label', 'scale', 'bounds', 'reverse', 'tick_labels_visible', 'major_ticks_visible', 'minor_ticks_visible', 'tick_direction', 'axis_line_visible', 'axis_title_visible'],
  set_legend: ['visible', 'anchor'],
} as const

describe('FocusEditor Agent Native actions', () => {
  it('compares the current plot with a real adjacent version', async () => {
    const user = userEvent.setup()
    const current = plot('K01', commonCapabilities)
    current.preview = { resourceId: 'resource:current', kind: 'preview', url: 'plotagent-resource://local/current', mimeType: 'image/png' }
    const previous = plot('K01', commonCapabilities)
    previous.plotVersion = 2
    previous.preview = { resourceId: 'resource:previous', kind: 'preview', url: 'plotagent-resource://local/previous', mimeType: 'image/png' }
    const { rerender } = render(<FocusEditor initialIndex={0} plot={current} onClose={() => undefined} />)

    expect(screen.getByRole('button', { name: '比较上一版本' })).toBeDisabled()
    rerender(<FocusEditor initialIndex={0} plot={current} previousPlot={previous} onClose={() => undefined} />)
    await user.click(screen.getByRole('button', { name: '比较上一版本' }))

    expect(screen.getByText('v2')).toBeInTheDocument()
    expect(screen.getByText('v3')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /v2 预览/ })).toHaveAttribute('src', 'plotagent-resource://local/previous')
    expect(screen.getByRole('img', { name: /Core 预览/ })).toHaveAttribute('src', 'plotagent-resource://local/current')
  })

  it('exposes only history operations backed by the parent version controller', async () => {
    const user = userEvent.setup()
    const onUndo = vi.fn()
    const onRedo = vi.fn()
    render(<FocusEditor initialIndex={0} plot={plot('K01', commonCapabilities)} canUndo onUndo={onUndo} canRedo={false} onRedo={onRedo} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '撤销' }))
    expect(onUndo).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: '重做' })).toBeDisabled()
    expect(onRedo).not.toHaveBeenCalled()
  })

  it('submits one public series-style action to the selected semantic object', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn<(patch: JsonValue) => Promise<void>>(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K03', commonCapabilities)} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '编辑面板' }))
    await user.click(screen.getByRole('tab', { name: '系列' }))
    await user.selectOptions(screen.getByRole('combobox', { name: '符号形状' }), 'diamond')
    await user.selectOptions(screen.getByRole('combobox', { name: '线型' }), 'dash')
    await user.click(screen.getByRole('button', { name: '应用系列样式' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledTimes(1))
    expect(onPatch).toHaveBeenCalledWith({
      operation: 'set_series_style',
      target: 'series:test.primary',
      marker_shape: 'diamond',
      line_style: 'dash',
    })
  })

  it('exposes qualified colormap, error, and data-label actions as frontend controls', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn<(patch: JsonValue) => Promise<void>>(async () => undefined)
    const value = plot('K04', {
      ...commonCapabilities,
      set_colormap: ['palette', 'reverse', 'mode', 'levels', 'colorbar_visible'],
      set_error_style: ['bar_color', 'bar_width_pt', 'cap_size_pt', 'bar_opacity'],
      set_data_labels: ['visible', 'value_format', 'position', 'font_size_pt'],
    })
    render(<FocusEditor
      initialIndex={0}
      plot={value}
      onPatch={onPatch}
      onClose={() => undefined}
    />)

    await user.click(screen.getByRole('button', { name: '编辑面板' }))
    await user.click(screen.getByRole('tab', { name: '色阶' }))
    await user.selectOptions(screen.getByRole('combobox', { name: '色板' }), 'plasma')
    await user.click(screen.getByRole('button', { name: '应用色阶' }))
    await user.click(screen.getByRole('tab', { name: '误差' }))
    await user.click(screen.getByRole('button', { name: '应用误差样式' }))
    await user.click(screen.getByRole('tab', { name: '标签' }))
    await user.click(screen.getByRole('checkbox', { name: '显示数据标签' }))
    await user.click(screen.getByRole('button', { name: '应用数据标签' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledTimes(3))
    expect(onPatch.mock.calls.map(([action]) => (
      typeof action === 'object' && action !== null && 'operation' in action
        ? action.operation : undefined
    ))).toEqual(['set_colormap', 'set_error_style', 'set_data_labels'])
  })

  it('keeps error-bar and error-band controls within their profile contracts', async () => {
    const user = userEvent.setup()
    const onBarPatch = vi.fn<(patch: JsonValue) => Promise<void>>(async () => undefined)
    const barView = render(<FocusEditor
      initialIndex={0}
      plot={plot('K06', {
        ...commonCapabilities,
        set_error_style: ['bar_color', 'bar_width_pt', 'cap_size_pt', 'bar_opacity'],
      })}
      onPatch={onBarPatch}
      onClose={() => undefined}
    />)

    await user.click(screen.getByRole('button', { name: '编辑面板' }))
    await user.click(screen.getByRole('tab', { name: '误差' }))
    expect(screen.getByRole('heading', { name: '误差棒' })).toBeInTheDocument()
    expect(screen.queryByLabelText('误差带填充颜色')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '应用误差样式' }))
    await waitFor(() => expect(onBarPatch).toHaveBeenCalledOnce())
    expect(onBarPatch).toHaveBeenCalledWith(expect.objectContaining({
      operation: 'set_error_style',
      bar_color: expect.any(String),
      bar_width_pt: expect.any(Number),
      cap_size_pt: expect.any(Number),
      bar_opacity: expect.any(Number),
    }))
    expect(onBarPatch.mock.calls[0]?.[0]).not.toHaveProperty('band_fill_color')
    barView.unmount()

    const onBandPatch = vi.fn<(patch: JsonValue) => Promise<void>>(async () => undefined)
    render(<FocusEditor
      initialIndex={0}
      plot={plot('K07', {
        ...commonCapabilities,
        set_error_style: [
          'band_fill_color', 'band_fill_opacity',
          'band_stroke_color', 'band_stroke_width_pt',
        ],
      })}
      onPatch={onBandPatch}
      onClose={() => undefined}
    />)

    await user.click(screen.getByRole('button', { name: '编辑面板' }))
    await user.click(screen.getByRole('tab', { name: '误差' }))
    expect(screen.getByRole('heading', { name: '误差带' })).toBeInTheDocument()
    expect(screen.queryByLabelText('误差棒端帽大小')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '应用误差样式' }))
    await waitFor(() => expect(onBandPatch).toHaveBeenCalledOnce())
    expect(onBandPatch).toHaveBeenCalledWith(expect.objectContaining({
      operation: 'set_error_style',
      band_fill_color: expect.any(String),
      band_fill_opacity: expect.any(Number),
      band_stroke_color: expect.any(String),
      band_stroke_width_pt: expect.any(Number),
    }))
    expect(onBandPatch.mock.calls[0]?.[0]).not.toHaveProperty('bar_color')
  })

  it('does not expose edits omitted by the profile capability contract', async () => {
    const user = userEvent.setup()
    render(<FocusEditor
      initialIndex={0}
      plot={plot('K01', {
        set_series_style: ['line_stroke_color', 'line_width_pt', 'line_style'],
      })}
      onPatch={async () => undefined}
      onClose={() => undefined}
    />)

    await user.click(screen.getByRole('button', { name: '编辑面板' }))
    await user.click(screen.getByRole('tab', { name: '系列' }))
    expect(screen.queryByRole('combobox', { name: '符号形状' })).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '线型' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: '专属' })).not.toBeInTheDocument()
  })

  it('targets the series explicitly selected by the user', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    const value = plot('K02', commonCapabilities)
    value.seriesIds = ['series:test.one', 'series:test.two']
    value.seriesStyles = [
      { seriesId: 'series:test.one', style: {} },
      { seriesId: 'series:test.two', style: { markerShape: 'diamond' } },
    ]
    value.colorMaps = [
      { seriesId: 'series:test.one' }, { seriesId: 'series:test.two' },
    ]
    value.errorStyles = [
      { seriesId: 'series:test.one' }, { seriesId: 'series:test.two' },
    ]
    value.dataLabelStyles = [
      { seriesId: 'series:test.one' }, { seriesId: 'series:test.two' },
    ]
    render(<FocusEditor initialIndex={0} plot={value} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '编辑面板' }))
    await user.click(screen.getByRole('tab', { name: '系列' }))
    await user.selectOptions(screen.getByRole('combobox', { name: '作用系列' }), '1')
    await user.selectOptions(screen.getByRole('combobox', { name: '符号形状' }), 'square')
    await user.click(screen.getByRole('button', { name: '应用系列样式' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledTimes(1))
    expect(onPatch).toHaveBeenCalledWith({
      operation: 'set_series_style', target: 'series:test.two', marker_shape: 'square',
    })
  })

  it('emits one set_title action without old PlotSpec patch fields', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K01', commonCapabilities)} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '编辑面板' }))
    await user.click(screen.getByRole('tab', { name: '常规' }))
    await user.clear(screen.getByRole('textbox', { name: '图标题' }))
    await user.type(screen.getByRole('textbox', { name: '图标题' }), '新标题')
    await user.click(screen.getByRole('button', { name: '应用图标题' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledWith({
      operation: 'set_title', target: 'plot:test', text: '新标题',
    }))
  })

  it('emits a typed axis edit against the semantic Y axis', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K01', commonCapabilities)} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '编辑面板' }))
    await user.click(screen.getByRole('tab', { name: '坐标轴' }))
    expect(screen.getByRole('combobox', { name: '轴尺度' })).toHaveValue('log10')
    await user.clear(screen.getByRole('textbox', { name: '轴标题' }))
    await user.type(screen.getByRole('textbox', { name: '轴标题' }), 'Response')
    await user.click(screen.getByRole('button', { name: '应用坐标轴设置' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledWith({
      operation: 'set_axis', target: 'axis:test.y', label: 'Response',
    }))
  })

  it('exposes and submits X38 numeric axis bounds', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    render(<FocusEditor
      initialIndex={0}
      plot={plot('X38', commonCapabilities)}
      onPatch={onPatch}
      onClose={() => undefined}
    />)

    await user.click(screen.getByRole('button', { name: '编辑面板' }))
    await user.click(screen.getByRole('tab', { name: '坐标轴' }))
    await user.selectOptions(screen.getByRole('combobox', { name: '作用坐标轴' }), 'x')
    await user.clear(screen.getByRole('spinbutton', { name: '轴最小值' }))
    await user.type(screen.getByRole('spinbutton', { name: '轴最小值' }), '30')
    await user.clear(screen.getByRole('spinbutton', { name: '轴最大值' }))
    await user.type(screen.getByRole('spinbutton', { name: '轴最大值' }), '90')
    await user.click(screen.getByRole('button', { name: '应用坐标轴设置' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledWith({
      operation: 'set_axis',
      target: 'axis:test.x',
      minimum: 30,
      maximum: 90,
    }))
  })

  it('edits series visibility and axis visibility without phrase routing', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K01', commonCapabilities)} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '编辑面板' }))
    await user.click(screen.getByRole('tab', { name: '系列' }))
    await user.click(screen.getByRole('checkbox', { name: '显示整个数据系列' }))
    await user.click(screen.getByRole('button', { name: '应用系列样式' }))
    await user.click(screen.getByRole('tab', { name: '坐标轴' }))
    await user.click(screen.getByRole('checkbox', { name: '显示刻度标签' }))
    await user.click(screen.getByRole('checkbox', { name: '显示次刻度线' }))
    await user.selectOptions(screen.getByRole('combobox', { name: '刻度线方向' }), 'inout')
    await user.click(screen.getByRole('button', { name: '应用坐标轴设置' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledTimes(2))
    expect(onPatch).toHaveBeenNthCalledWith(1, {
      operation: 'set_series_style', target: 'series:test.primary', visible: false,
    })
    expect(onPatch).toHaveBeenNthCalledWith(2, {
      operation: 'set_axis',
      target: 'axis:test.y',
      tick_labels_visible: false,
      minor_ticks_visible: false,
      tick_direction: 'inout',
    })
  })

  it('maps the visible legend placement to a public anchor', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K02', commonCapabilities)} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '编辑面板' }))
    await user.click(screen.getByRole('tab', { name: '图例' }))
    await user.selectOptions(screen.getByRole('combobox', { name: '图例位置' }), 'outside_right')
    await user.click(screen.getByRole('button', { name: '应用图例设置' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledWith({
      operation: 'set_legend', target: 'legend:test.main', anchor: 'right',
    }))
  })

  it('normalizes a persisted right legend anchor and does not create a no-op version', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    const value = plot('K02', commonCapabilities)
    value.style.legendPlacement = 'right'
    render(<FocusEditor initialIndex={0} plot={value} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '编辑面板' }))
    await user.click(screen.getByRole('tab', { name: '图例' }))
    expect(screen.getByRole('combobox', { name: '图例位置' })).toHaveValue('outside_right')
    await user.click(screen.getByRole('button', { name: '应用图例设置' }))

    expect(onPatch).not.toHaveBeenCalled()
    expect(screen.getByText('当前设置没有变化。')).toBeInTheDocument()
  })

  it('renders and submits profile-declared chart parameters generically', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    const value = plot('X24', { ...commonCapabilities, set_chart_parameter: ['pareto_reference_percent'] })
    value.chartParameters = { pareto_reference_percent: 80 }
    render(<FocusEditor initialIndex={0} plot={value} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '编辑面板' }))
    await user.click(screen.getByRole('tab', { name: '专属' }))
    await user.clear(screen.getByRole('spinbutton', { name: '帕累托参考百分比' }))
    await user.type(screen.getByRole('spinbutton', { name: '帕累托参考百分比' }), '75')
    await user.click(screen.getByRole('button', { name: '应用参数' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledWith({
      operation: 'set_chart_parameter',
      target: 'plot:test',
      parameter: 'pareto_reference_percent',
      value: 75,
    }))
  })
})
