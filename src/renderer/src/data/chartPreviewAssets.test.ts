import { describe, expect, it } from 'vitest'

import previewManifest from '../assets/chart-previews/manifest.json'
import { chartCatalog } from './chartCatalog'
import { chartPreviewAssets, chartPreviewSource } from './chartPreviewAssets'

const previewMarkup = import.meta.glob<string>('../assets/chart-previews/*.svg', {
  eager: true,
  import: 'default',
  query: '?raw',
})

describe('chart preview assets', () => {
  it('has one current renderer image for every public chart', () => {
    const catalogIds = chartCatalog.map((chart) => chart.id).sort()
    const assetIds = Object.keys(chartPreviewAssets).sort()
    const manifestIds = previewManifest.entries.map((entry) => entry.profile_id).sort()

    expect(assetIds).toEqual(catalogIds)
    expect(manifestIds).toEqual(catalogIds)
    expect(previewManifest.count).toBe(34)
    expect(previewManifest.source_policy).toContain('production Matplotlib default state')
    expect(previewManifest.simplification_policy).toContain('remove titles, axes')
    expect(previewManifest.entries.every((entry) => entry.asset_format === 'svg')).toBe(true)
  })

  it('fails closed instead of substituting a generic family image', () => {
    expect(chartPreviewSource('K01')).toMatch(/^data:image\/svg\+xml/)
    expect(() => chartPreviewSource('REMOVED')).toThrow('Missing chart preview asset')
  })

  it('keeps geometry while removing full-chart furniture', () => {
    expect(Object.keys(previewMarkup)).toHaveLength(34)
    for (const markup of Object.values(previewMarkup)) {
      expect(markup).toContain('viewBox=')
      expect(markup).not.toMatch(/id="(?:matplotlib\.axis_|legend_|text_)/)
      expect(markup).toMatch(/<(?:path|image|use|rect)\b/)
    }
  })
})
