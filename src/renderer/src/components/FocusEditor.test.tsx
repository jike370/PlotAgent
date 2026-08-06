import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { ProductPlot } from '../data/productState'
import { FocusEditor } from './FocusEditor'

function plot(chartId: string): ProductPlot & { title: string } {
  return {
    title: '测试图',
    plotId: 'plot:test',
    plotVersion: 3,
    chartId,
    projectVersion: 4,
    seriesIds: ['series:test.0'],
    seriesStyles: [{ seriesId: 'series:test.0', style: {} }],
    axisIds: { x: 'axis:x', y: 'axis:y' },
    axisStates: {
      x: { axisId: 'axis:x', label: 'Time', scale: 'linear', reverse: false },
      y: { axisId: 'axis:y', label: 'Signal', scale: 'log10', minimum: 0.1, maximum: 100, reverse: false },
    },
    canvasSizeMm: { width: 183, height: 120 },
    style: { legendVisible: true, legendPlacement: 'inside' },
  }
}

describe('FocusEditor capability-driven patches', () => {
  it('submits one typed series patch with an Origin symbol', async () => {
    const user = userEvent.setup()
    const onPatch = vi.fn(async () => undefined)
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
  })
})
