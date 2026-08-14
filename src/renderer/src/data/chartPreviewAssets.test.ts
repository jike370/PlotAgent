import { describe, expect, it } from 'vitest'

import previewManifest from '../assets/chart-previews/manifest.json'
import { chartCatalog } from './chartCatalog'
import { chartPreviewAssets, chartPreviewSource } from './chartPreviewAssets'

describe('chart preview assets', () => {
  it('has one current renderer image for every public chart', () => {
    const catalogIds = chartCatalog.map((chart) => chart.id).sort()
    const assetIds = Object.keys(chartPreviewAssets).sort()
    const manifestIds = previewManifest.entries.map((entry) => entry.profile_id).sort()

    expect(assetIds).toEqual(catalogIds)
    expect(manifestIds).toEqual(catalogIds)
    expect(previewManifest.count).toBe(34)
    expect(previewManifest.source_policy).toContain('production Matplotlib default state')
  })

  it('fails closed instead of substituting a generic family image', () => {
    expect(chartPreviewSource('K01')).toMatch(/K01\.png/)
    expect(() => chartPreviewSource('REMOVED')).toThrow('Missing chart preview asset')
  })
})
