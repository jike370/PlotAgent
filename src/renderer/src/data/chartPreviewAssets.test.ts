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
    expect(previewManifest.schema_version).toBe('plotagent.chart-library-previews.v4')
    expect(previewManifest.source_policy).toContain('production Matplotlib default state')
    expect(previewManifest.simplification_policy).toContain('remove titles, axes')
    expect(previewManifest.preview_palette).toEqual({
      line_and_point: '#d95555',
      bar_primary: '#1676d2',
      bar_secondary: '#62a6e3',
      bar_tertiary: '#a6ccee',
    })
    expect(previewManifest.entries.every((entry) => entry.asset_format === 'svg')).toBe(true)
    expect(previewManifest.entries.every((entry) => entry.width === 1024 && entry.height === 768)).toBe(true)
    const emphasisById = Object.fromEntries(
      previewManifest.entries.map((entry) => [entry.profile_id, entry.preview_emphasis]),
    )
    expect(emphasisById.K02).toContain('markers enlarged')
    expect(emphasisById.K03).toContain('markers enlarged')
    expect(emphasisById.K04).toContain('bubble radii progressively enlarged')
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

  it('uses element semantics instead of one categorical palette', () => {
    const markupFor = (profileId: string): string => {
      const entry = Object.entries(previewMarkup).find(([path]) => path.endsWith(`/${profileId}.svg`))
      expect(entry, `missing raw preview for ${profileId}`).toBeDefined()
      return entry![1].toLowerCase()
    }

    for (const profileId of ['K01', 'K02', 'K03', 'K06', 'K07']) {
      expect(markupFor(profileId)).toContain('#d95555')
    }
    const groupedBars = markupFor('K09')
    expect(groupedBars).toContain('#1676d2')
    expect(groupedBars).toContain('#62a6e3')
    expect(groupedBars).toContain('#a6ccee')
    for (const markup of Object.values(previewMarkup)) {
      expect(markup).not.toMatch(/#(?:7478a8|4f8c84)/i)
    }
  })
})
