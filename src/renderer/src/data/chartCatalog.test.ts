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
  it('contains the 32 confirmed first-release chart types', () => {
    expect(chartCatalog).toHaveLength(32)
    expect(chartCatalog.filter((chart) => chart.layer === 'core')).toHaveLength(25)
    expect(chartCatalog.filter((chart) => chart.layer === 'validation')).toHaveLength(7)
  })

  it('searches aliases and stable IDs', () => {
    expect(filterCharts(chartCatalog, { ...baseFilters, query: 'EIS' })[0]?.id).toBe('S34')
    expect(filterCharts(chartCatalog, { ...baseFilters, query: 'K21' })[0]?.name).toBe('相关矩阵图')
  })

  it('filters user-owned collections without adding recommendations', () => {
    const favorites = filterCharts(chartCatalog, { ...baseFilters, collection: 'favorites' })

    expect(favorites.length).toBeGreaterThan(0)
    expect(favorites.every((chart) => chart.favorite)).toBe(true)
  })
})
