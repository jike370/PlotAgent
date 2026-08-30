import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { chartCatalog } from '../data/chartCatalog'
import { chartCompatibility } from '../data/chartCompatibility'
import { ChartLibrary } from './ChartLibrary'

describe('chart library dataset compatibility', () => {
  it('admits grouped and stacked bars with one numeric and two category fields', () => {
    const summary = {
      numericFieldCount: 1,
      categoricalFieldCount: 2,
      totalFieldCount: 3,
    }

    for (const chartId of ['K09', 'K10', 'K11']) {
      const chart = chartCatalog.find((item) => item.id === chartId)
      expect(chart).toBeDefined()
      expect(chartCompatibility(chart!, summary)).toEqual({ compatible: true })
    }
  })

  it('does not lower the numeric requirement for a two-axis scatter chart', () => {
    const chart = chartCatalog.find((item) => item.id === 'K03')
    expect(chart).toBeDefined()
    expect(chartCompatibility(chart!, {
      numericFieldCount: 1,
      categoricalFieldCount: 2,
      totalFieldCount: 3,
    })).toEqual({ compatible: false })
  })

  it('admits K01 and K02 when discrete text supplies x and one numeric field supplies y', () => {
    const summary = {
      numericFieldCount: 1,
      categoricalFieldCount: 2,
      totalFieldCount: 3,
    }

    for (const chartId of ['K01', 'K02']) {
      const chart = chartCatalog.find((item) => item.id === chartId)
      expect(chart).toBeDefined()
      expect(chartCompatibility(chart!, summary)).toEqual({ compatible: true })
    }
  })

  it('uses the generated role contract for mixed and datetime inputs', () => {
    const column = chartCatalog.find((item) => item.id === 'K08')
    const timeSeries = chartCatalog.find((item) => item.id === 'K19')
    expect(column).toBeDefined()
    expect(timeSeries).toBeDefined()

    expect(chartCompatibility(column!, {
      numericFieldCount: 1,
      categoricalFieldCount: 1,
      totalFieldCount: 2,
    })).toEqual({ compatible: true })
    expect(chartCompatibility(timeSeries!, {
      numericFieldCount: 1,
      categoricalFieldCount: 0,
      datetimeFieldCount: 1,
      totalFieldCount: 2,
    })).toEqual({ compatible: true })
  })
})

describe('chart library presentation', () => {
  it('keeps cards compact and moves supporting copy into the detail panel', () => {
    const chart = chartCatalog.find((item) => item.id === 'K02')!

    render(<ChartLibrary onClose={vi.fn()} onSelect={vi.fn()} />)

    const card = screen.getByRole('button', { name: `${chart.id} ${chart.name}` })
    const detail = screen.getByLabelText(`${chart.name}详情`)

    expect(within(card).getByText(chart.id)).toBeInTheDocument()
    expect(within(card).getByText(chart.name)).toBeInTheDocument()
    expect(within(card).queryByText(chart.englishName)).not.toBeInTheDocument()
    expect(within(card).queryByText(chart.purpose)).not.toBeInTheDocument()
    for (const shape of chart.dataShape) {
      expect(within(card).queryByText(shape)).not.toBeInTheDocument()
    }

    expect(within(detail).getByText(chart.englishName)).toBeInTheDocument()
    expect(within(detail).getByText(chart.purpose)).toBeInTheDocument()
    expect(within(detail).getByText(chart.dataShape.join(' / '))).toBeInTheDocument()
  })
})
