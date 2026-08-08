import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { JsonValue } from '../../../shared/desktop-contract'
import type { ProductPlot } from '../data/productState'
import { FocusEditor } from './FocusEditor'

function plot(chartId: string): ProductPlot & { title: string } {
  return {
    title: '测试图',
    plotId: 'plot:test',
    plotVersion: 3,
    chartId,
    plotTitle: '已保存标题',
    fontSizePt: 10,
    projectVersion: 4,
    seriesIds: ['series:test.0'],
    seriesStyles: [{ seriesId: 'series:test.0', style: {} }],
    axisIds: { x: 'axis:x', y: 'axis:y' },
    axisStates: {
      x: { axisId: 'axis:x', label: 'Time', scale: 'linear', reverse: false, numberFormat: 'auto', decimalPlaces: 2 },
      y: { axisId: 'axis:y', label: 'Signal', scale: 'log10', minimum: 0.1, maximum: 100, reverse: false, majorInterval: 10, numberFormat: 'scientific', decimalPlaces: 1 },
    },
    canvasSizeMm: { width: 183, height: 120 },
    annotations: [],
    specialist: {
      barArea: { edgeWidthPt: 0.5, widthRatio: 0.8, alpha: 1 },
      uncertainty: { lineWidthPt: 0.8, capSizePt: 4, bandAlpha: 0.25 },
      colorbar: { visible: true, title: '', levels: 7 },
      dualY: { axisWidthPt: 0.8 },
      facet: {
        order: [], labels: [], gapMm: 4, sharedX: true, sharedY: true,
        commonLegend: true,
      },
      yOffset: { order: [] },
      chartParameters: {
        stepWhere: 'post',
        volcanoAbsoluteLog2FoldChange: 1, volcanoPvalue: 0.05,
        paretoReferencePercent: 80,
      },
    },
    style: { legendVisible: true, legendPlacement: 'inside' },
  }
}

describe('FocusEditor capability-driven patches', () => {
  it('submits one typed series patch with an Origin symbol', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn<(patch: JsonValue) => Promise<void>>(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K03')} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '参数' }))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Origin 符号' }), 'diamond')
    await user.selectOptions(screen.getByRole('combobox', { name: '符号内部' }), 'hollow')
    await user.click(screen.getByRole('button', { name: '应用系列样式' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledTimes(1))
    expect(onPatch).toHaveBeenCalledWith(expect.objectContaining({
      operation: 'set_series_style',
      target_id: 'series:test.0',
      expected_plot_version: 3,
      symbol: { shape: 'diamond', interior: 'hollow' },
    }))
  })

  it('submits a compact palette selection and reverse flag', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K20')} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '参数' }))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Origin 色板' }), 'Magma')
    await user.click(screen.getByRole('checkbox', { name: '反向使用色板' }))
    await user.click(screen.getByRole('button', { name: '应用色板' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledTimes(1))
    expect(onPatch).toHaveBeenCalledWith(expect.objectContaining({
      operation: 'set_palette',
      palette_id: 'Magma',
      reverse: true,
    }))
  })

  it('does not expose symbol controls for a line-only chart', async () => {
    const user = userEvent.setup()
    render(<FocusEditor initialIndex={0} plot={plot('K01')} onPatch={async () => undefined} onClose={() => undefined} />)
    await user.click(screen.getByRole('button', { name: '参数' }))
    expect(screen.queryByRole('combobox', { name: 'Origin 符号' })).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '线型' })).toBeInTheDocument()
  })

  it('targets the selected series instead of silently editing the first series', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    const multiSeries = plot('K02')
    multiSeries.seriesIds = ['series:test.0', 'series:test.1']
    multiSeries.seriesStyles = [
      { seriesId: 'series:test.0', style: { symbolShape: 'circle', symbolInterior: 'solid' } },
      { seriesId: 'series:test.1', style: { symbolShape: 'diamond', symbolInterior: 'hollow' } },
    ]
    render(
      <FocusEditor
        initialIndex={0}
        plot={multiSeries}
        onPatch={onPatch}
        onClose={() => undefined}
      />,
    )

    await user.click(screen.getByRole('button', { name: '参数' }))
    await user.selectOptions(screen.getByRole('combobox', { name: '作用系列' }), '1')
    expect(screen.getByRole('combobox', { name: 'Origin 符号' })).toHaveValue('diamond')
    expect(screen.getByRole('combobox', { name: '符号内部' })).toHaveValue('hollow')
    await user.click(screen.getByRole('button', { name: '应用系列样式' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledTimes(1))
    expect(onPatch).toHaveBeenCalledWith(expect.objectContaining({
      operation: 'set_series_style',
      target_id: 'series:test.1',
      symbol: { shape: 'diamond', interior: 'hollow' },
    }))
  })

  it('removes unsupported interiors when a line-only Origin symbol is selected', async () => {
    const user = userEvent.setup()
    render(<FocusEditor initialIndex={0} plot={plot('K03')} onPatch={async () => undefined} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '参数' }))
    await user.selectOptions(screen.getByRole('combobox', { name: '符号内部' }), 'hollow')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Origin 符号' }), 'plus')

    expect(screen.getByRole('combobox', { name: '符号内部' })).toHaveValue('solid')
    expect(screen.getByRole('combobox', { name: '符号内部' })).toHaveDisplayValue('实心')
  })

  it('submits an exact category identity color patch', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K09')} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '参数' }))
    await user.type(screen.getByRole('textbox', { name: '分类名称' }), 'Treated')
    await user.click(screen.getByRole('button', { name: '应用分类颜色' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledTimes(1))
    expect(onPatch).toHaveBeenCalledWith(expect.objectContaining({
      operation: 'set_category_color',
      target_id: 'series:test.0',
      category: 'Treated',
      color: { value: '#2A6FDB' },
    }))
  })

  it('shows the persisted axis state instead of resetting an existing log axis', async () => {
    const user = userEvent.setup()
    render(<FocusEditor initialIndex={0} plot={plot('K01')} onPatch={async () => undefined} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '参数' }))
    await user.click(screen.getByRole('tab', { name: '坐标轴' }))

    expect(screen.getByRole('combobox', { name: '轴尺度' })).toHaveValue('log10')
    expect(screen.getByRole('textbox', { name: '轴标题' })).toHaveValue('Signal')
    expect(screen.getByRole('spinbutton', { name: '轴最小值' })).toHaveValue(0.1)
    expect(screen.getByRole('spinbutton', { name: '轴最大值' })).toHaveValue(100)
    expect(screen.getByRole('spinbutton', { name: '主刻度间隔' })).toHaveValue(10)
    expect(screen.getByRole('combobox', { name: '刻度数字格式' })).toHaveValue('scientific')
    expect(screen.getByRole('spinbutton', { name: '刻度小数位数' })).toHaveValue(1)
  })

  it('submits persisted general title and font changes', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K01')} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '参数' }))
    await user.click(screen.getByRole('tab', { name: '常规' }))
    expect(screen.getByRole('textbox', { name: '图标题' })).toHaveValue('已保存标题')
    expect(screen.getByRole('spinbutton', { name: '全局字号' })).toHaveValue(10)
    await user.clear(screen.getByRole('textbox', { name: '图标题' }))
    await user.click(screen.getByRole('button', { name: '应用图标题' }))
    await waitFor(() => expect(onPatch).toHaveBeenCalledWith(expect.objectContaining({
      operation: 'set_plot_title', target_id: 'plot:test', title: null,
    })))
  })

  it('supports automatic range, reverse axes, and explicit ticks', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn<(patch: JsonValue) => Promise<void>>(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K01')} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '参数' }))
    await user.click(screen.getByRole('tab', { name: '坐标轴' }))
    await user.click(screen.getByRole('button', { name: '恢复自动范围' }))
    await user.click(screen.getByRole('checkbox', { name: '反向坐标轴' }))
    await user.click(screen.getByRole('button', { name: '应用轴方向' }))
    await user.clear(screen.getByRole('spinbutton', { name: '主刻度间隔' }))
    await user.selectOptions(screen.getByRole('combobox', { name: '刻度数字格式' }), 'fixed')
    await user.click(screen.getByRole('button', { name: '应用刻度' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledTimes(3))
    expect(onPatch.mock.calls.map(([patch]) => patch)).toEqual(expect.arrayContaining([
      expect.objectContaining({ operation: 'set_axis_range', minimum: null, maximum: null }),
      expect.objectContaining({ operation: 'set_axis_reverse', reverse: true }),
      expect.objectContaining({ operation: 'set_axis_ticks', ticks: { major_interval: null, number_format: 'fixed', decimal_places: 1 } }),
    ]))
  })

  it('opens the real reference-band editor from the toolbar and emits one safe annotation', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K01')} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '参考带' }))
    await user.type(screen.getByRole('spinbutton', { name: '参考对象起点' }), '2')
    await user.type(screen.getByRole('spinbutton', { name: '参考对象终点' }), '4')
    await user.click(screen.getByRole('button', { name: '添加标注' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledWith(expect.objectContaining({
      operation: 'add_annotation',
      target_id: 'plot:test',
      annotation: expect.objectContaining({
        annotation_id: 'annotation:ui.test.v4', kind: 'reference_band', y: 2, y2: 4,
      }),
    })))
  })

  it('submits dynamic grouped-bar parameters from the specialist tab', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('K09')} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '参数' }))
    await user.click(screen.getByRole('tab', { name: '专属' }))
    await user.clear(screen.getByRole('spinbutton', { name: '柱宽比例' }))
    await user.type(screen.getByRole('spinbutton', { name: '柱宽比例' }), '0.65')
    await user.click(screen.getByRole('button', { name: '应用柱与面积样式' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledWith(expect.objectContaining({
      operation: 'set_bar_area_style',
      target_id: 'plot:test',
      style: expect.objectContaining({ width_ratio: 0.65 }),
    })))
  })

  it('only exposes the fixed chart parameter relevant to the current chart', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
    render(<FocusEditor initialIndex={0} plot={plot('S07')} onPatch={onPatch} onClose={() => undefined} />)

    await user.click(screen.getByRole('button', { name: '参数' }))
    await user.click(screen.getByRole('tab', { name: '专属' }))
    expect(screen.getByRole('spinbutton', { name: '火山图倍数阈值' })).toBeInTheDocument()
    expect(screen.queryByRole('spinbutton', { name: '棒棒糖基线' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '应用图型参数' }))

    await waitFor(() => expect(onPatch).toHaveBeenCalledWith(expect.objectContaining({
      operation: 'set_chart_parameters',
      parameters: expect.objectContaining({
        volcano_absolute_log2_fold_change: 1,
        volcano_pvalue: 0.05,
      }),
    })))
  })
})
