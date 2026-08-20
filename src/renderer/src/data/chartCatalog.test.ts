import { describe, expect, it } from 'vitest'

import engineProfileCatalog from '../../../shared/generated/engine-profile-catalog.json'
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
  it('exposes exactly the 34 Agent Native engine profiles', () => {
    expect(chartCatalog).toHaveLength(34)
    expect(allChartCatalog).toHaveLength(34)
    expect(chartCatalog.some((chart) => chart.id === 'S61')).toBe(true)
    expect(chartCatalog.some((chart) => chart.id === 'X24')).toBe(true)
    expect(chartCatalog.some((chart) => chart.id === 'S07' || chart.id === 'K05')).toBe(false)
    expect(chartCatalog.some((chart) => chart.id === 'X07' || chart.id === 'X37')).toBe(false)
    expect(chartCatalog.some((chart) => chart.id === 'K23' || chart.id === 'S45')).toBe(false)
    expect(chartCatalog.some((chart) => ['K16', 'K25', 'S01', 'S21'].includes(chart.id))).toBe(false)
    expect(chartCatalog.every((chart) => chart.export.svg === 'vector')).toBe(true)
    expect(chartProductMetadata.X07).toBeUndefined()
    expect(chartProductMetadata.S07).toBeUndefined()
    expect(chartProductMetadata.X24?.visualEvidence).toBe('engine_acceptance')
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

  it('keeps only common Matplotlib and Origin style choices', () => {
    expect(paletteCatalog).toHaveLength(1)
    expect(symbolCatalog).toHaveLength(7)
    expect(symbolCatalog.find((symbol) => symbol.shape === 'diamond')?.allowed_interiors)
      .toEqual(['solid'])
    expect(symbolCatalog.find((symbol) => symbol.shape === 'plus')?.allowed_interiors)
      .toEqual(['solid'])
  })

  it('projects mapping roles from the generated engine profile catalog', () => {
    const bubble = chartCatalog.find((chart) => chart.id === 'K04')
    const area = chartCatalog.find((chart) => chart.id === 'K18')
    const beforeAfter = chartCatalog.find((chart) => chart.id === 'X40')

    expect(bubble).toMatchObject({
      requiredFields: ['x', 'y'],
      optionalFields: ['size', 'color'],
      repeatableRolePrefixes: [],
    })
    expect(area).toMatchObject({
      requiredFields: ['x', 'series_1'],
      optionalFields: ['group'],
      repeatableRolePrefixes: ['series'],
    })
    expect(beforeAfter).toMatchObject({
      requiredFields: ['label', 'series_1', 'series_2'],
      optionalFields: ['group'],
      repeatableRolePrefixes: [],
    })
  })

  it('projects the corrected public editing surface', () => {
    const pointError = engineProfileCatalog.profiles.find((profile) => profile.profile_id === 'K06')
    const errorBand = engineProfileCatalog.profiles.find((profile) => profile.profile_id === 'K07')
    const pointErrorStyle = pointError?.capabilities.find(
      (capability) => capability.operation === 'set_error_style',
    )
    const errorBandStyle = errorBand?.capabilities.find(
      (capability) => capability.operation === 'set_error_style',
    )

    expect(chartProductMetadata.X38?.editCapabilities).toContain('axis_range')
    expect(pointErrorStyle?.parameters).toEqual([
      'bar_color', 'bar_width_pt', 'cap_size_pt', 'bar_opacity',
    ])
    expect(errorBandStyle?.parameters).toEqual([
      'band_fill_color', 'band_fill_opacity', 'band_stroke_color', 'band_stroke_width_pt',
    ])
    expect(engineProfileCatalog.profiles.every((profile) => (
      profile.capabilities.every((capability) => capability.operation !== 'add_annotation')
    ))).toBe(true)
  })
})
