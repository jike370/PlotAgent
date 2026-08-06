import { describe, expect, it } from 'vitest'

import {
  allChartCatalog,
  chartCatalog,
  chartProductMetadata,
  filterCharts,
  paletteCatalog,
  symbolCatalog,
} from './chartCatalog'

const baseFilters = {
  query: '',
  layer: 'all' as const,
  category: '全部',
  capability: 'all' as const,
  collection: 'all' as const,
}

describe('chart catalog', () => {
  it('exposes 43 qualified charts while retaining all internal adapters', () => {
    expect(chartCatalog).toHaveLength(43)
    expect(allChartCatalog).toHaveLength(52)
    expect(chartCatalog.some((chart) => chart.id === 'S61')).toBe(true)
    expect(chartCatalog.some((chart) => chart.id === 'X24' || chart.id === 'S07')).toBe(true)
    expect(chartCatalog.some((chart) => chart.id === 'X07' || chart.id === 'X37')).toBe(false)
    expect(chartCatalog.some((chart) => chart.id === 'K23' || chart.id === 'S45')).toBe(false)
    expect(chartCatalog.every((chart) => chart.export.svg === 'vector')).toBe(true)
    expect(chartProductMetadata.X07?.admission).toBe('internal_only')
    expect(chartProductMetadata.X24?.visualEvidence).toBe('synthetic_visual')
  })

  it('searches aliases and stable IDs', () => {
    expect(filterCharts(chartCatalog, { ...baseFilters, query: 'EIS' })[0]?.id).toBe('S34')
    expect(filterCharts(chartCatalog, { ...baseFilters, query: 'K21' })[0]?.name).toBe('相关矩阵图')
    expect(filterCharts(chartCatalog, { ...baseFilters, query: '分类性能' })[0]?.id).toBe('S61')
  })

  it('filters user-owned collections without adding recommendations', () => {
    const favorites = filterCharts(chartCatalog, { ...baseFilters, collection: 'favorites' })

    expect(favorites.length).toBeGreaterThan(0)
    expect(favorites.every((chart) => chart.favorite)).toBe(true)
  })

  it('loads the closed Origin style catalog from generated runtime metadata', () => {
    expect(paletteCatalog).toHaveLength(16)
    expect(symbolCatalog).toHaveLength(12)
    expect(paletteCatalog.find((palette) => palette.palette_id === 'GrayScale')?.source_hash)
      .toBe('9bafc5fca3adfdc8270b9f132e09c66ef9d7df6d6c42109009e11aa6208d05fc')
    expect(symbolCatalog.find((symbol) => symbol.shape === 'diamond')?.allowed_interiors)
      .toEqual(['solid', 'open', 'hollow'])
    expect(symbolCatalog.find((symbol) => symbol.shape === 'plus')?.allowed_interiors)
      .toEqual(['solid'])
  })
})
