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
    plotTitle: '已保存标题',
    fontSizePt: 10,
    projectVersion: 4,
    seriesIds: ['series:test.primary'],
    seriesStyles: [{ seriesId: 'series:test.primary', style: {} }],
    axisIds: { x: 'axis:test.x', y: 'axis:test.y' },
    axisStates: {
      x: { axisId: 'axis:test.x', label: 'Time', scale: 'linear', reverse: false, numberFormat: 'auto', decimalPlaces: 2 },
      y: { axisId: 'axis:test.y', label: 'Signal', scale: 'log10', minimum: 0.1, maximum: 100, reverse: false, numberFormat: 'auto', decimalPlaces: 2 },
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
    components: [],
  }
}

const commonCapabilities = {
  set_title: ['text'],
  set_series_style: ['color', 'line_width_pt', 'line_style', 'symbol', 'symbol_size_pt'],
  set_axis: ['label', 'scale', 'bounds', 'reverse'],
  set_legend: ['visible', 'anchor'],
  add_annotation: ['text'],
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

    await user.click(screen.getByRole('button', { name: '参数' }))
    await user.selectOptions(screen.getByRole('combobox', { name: '符号' }), 'diamond')
    await user.selectOptions(screen.getByRole('combobox', { name: '线型' }), 'dash')
    await user.click(screen.getByRole('button', { name: '应用系列样式' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledTimes(1))
    expect(onPatch).toHaveBeenCalledWith(expect.objectContaining({
      operation: 'set_series_style',
      target: 'series:test.primary',
      symbol: 'diamond',
      line_style: 'dash',
    }))
  })

  it('does not expose edits omitted by the profile capability contract', async () => {
    const user = userEvent.setup()
    render(<FocusEditor
      initialIndex={0}
      plot={plot('K01', { set_series_style: ['color', 'line_width_pt', 'line_style'] })}
      onPatch={async () => undefined}
      onClose={() => undefined}
    />)

    await user.click(screen.getByRole('button', { name: '参数' }))
    expect(screen.queryByRole('combobox', { name: 'Origin 符号' })).not.toBeInTheDocument()
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
      { seriesId: 'series:test.two', style: { symbolShape: 'diamond' } },
    ]
    render(<FocusEditor initialIndex={0} plot={value} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '参数' }))
    await user.selectOptions(screen.getByRole('combobox', { name: '作用系列' }), '1')
    await user.click(screen.getByRole('button', { name: '应用系列样式' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledTimes(1))
    expect(onPatch).toHaveBeenCalledWith(expect.objectContaining({
      operation: 'set_series_style', target: 'series:test.two', symbol: 'diamond',
    }))
  })

  it('emits one set_title action without old PlotSpec patch fields', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K01', commonCapabilities)} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '参数' }))
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

    await user.click(screen.getByRole('button', { name: '参数' }))
    await user.click(screen.getByRole('tab', { name: '坐标轴' }))
    expect(screen.getByRole('combobox', { name: '轴尺度' })).toHaveValue('log10')
    await user.clear(screen.getByRole('textbox', { name: '轴标题' }))
    await user.type(screen.getByRole('textbox', { name: '轴标题' }), 'Response')
    await user.click(screen.getByRole('button', { name: '应用轴标题' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledWith({
      operation: 'set_axis', target: 'axis:test.y', label: 'Response',
    }))
  })

  it('maps the visible legend placement to a public anchor', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K02', commonCapabilities)} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '参数' }))
    await user.click(screen.getByRole('tab', { name: '图例' }))
    await user.selectOptions(screen.getByRole('combobox', { name: '图例位置' }), 'outside_right')
    await user.click(screen.getByRole('button', { name: '应用图例位置' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledWith({
      operation: 'set_legend', target: 'legend:test.main', anchor: 'right',
    }))
  })

  it('adds only the public text annotation shape', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K01', commonCapabilities)} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '文本标注' }))
    await user.type(screen.getByRole('textbox', { name: '标注文本' }), 'Peak')
    await user.type(screen.getByRole('spinbutton', { name: '标注 X 坐标' }), '2')
    await user.type(screen.getByRole('spinbutton', { name: '标注 Y 坐标' }), '4')
    await user.click(screen.getByRole('button', { name: '添加标注' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledWith(expect.objectContaining({
      operation: 'add_annotation',
      target: 'plot:test',
      text: 'Peak',
      x: 2,
      y: 4,
      coordinate_system: 'data',
    })))
    expect(screen.getByRole('button', { name: '参考带' })).toBeDisabled()
  })

  it('renders and submits profile-declared chart parameters generically', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    const value = plot('X24', { ...commonCapabilities, set_chart_parameter: ['pareto_reference_percent'] })
    value.chartParameters = { pareto_reference_percent: 80 }
    render(<FocusEditor initialIndex={0} plot={value} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '参数' }))
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
