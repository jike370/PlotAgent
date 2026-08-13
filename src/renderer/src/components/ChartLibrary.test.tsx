import { describe, expect, it } from 'vitest'

import { chartCatalog } from '../data/chartCatalog'
import { chartCompatibility } from '../data/chartCompatibility'

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
})
