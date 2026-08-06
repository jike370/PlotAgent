import { describe, expect, it } from 'vitest'

import { chartCatalog, filterCharts } from './chartCatalog'

const baseFilters = {
  query: '',
  layer: 'all' as const,
  category: '全部',
  capability: 'all' as const,
  collection: 'all' as const,
}

describe('chart catalog', () => {
  it('contains the 52 confirmed numeric first-release chart types', () => {
    expect(chartCatalog).toHaveLength(52)
    expect(chartCatalog.filter((chart) => chart.layer === 'core')).toHaveLength(44)
    expect(chartCatalog.filter((chart) => chart.layer === 'validation')).toHaveLength(8)
    expect(chartCatalog.some((chart) => chart.id === 'S61')).toBe(true)
    expect(chartCatalog.some((chart) => chart.id === 'K23' || chart.id === 'S45')).toBe(false)
    expect(chartCatalog.every((chart) => chart.export.svg === 'vector')).toBe(true)
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
})
