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
  it('has one Origin gallery replica for every public chart', () => {
    const catalogIds = chartCatalog.map((chart) => chart.id).sort()
    const assetIds = Object.keys(chartPreviewAssets).sort()
    const manifestIds = previewManifest.entries.map((entry) => entry.profile_id).sort()

    expect(assetIds).toEqual(catalogIds)
    expect(manifestIds).toEqual(catalogIds)
    expect(previewManifest.count).toBe(34)
    expect(previewManifest.schema_version).toBe('plotagent.chart-library-previews.v5')
    expect(previewManifest.source_policy).toContain('OriginPro 2024 graph-gallery previews')
    expect(previewManifest.reference_policy).toContain('OriginPro gallery screenshots')
    expect(previewManifest.preview_policy).toContain('canonical graph-type symbol')
    expect(previewManifest.entries.every((entry) => entry.backend === 'origin-gallery-replica')).toBe(true)
    expect(previewManifest.entries.every((entry) => entry.origin_preview_name.length > 0)).toBe(true)
    expect(previewManifest.entries.every((entry) => entry.origin_template.length > 0)).toBe(true)
    expect(previewManifest.entries.every((entry) => entry.asset_format === 'svg')).toBe(true)
    expect(previewManifest.entries.every((entry) => entry.width === 1024 && entry.height === 768)).toBe(true)
    const templateById = Object.fromEntries(
      previewManifest.entries.map((entry) => [entry.profile_id, entry.origin_template]),
    )
    expect(templateById.K01).toBe('LINE.OTP')
    expect(templateById.K13).toBe('BOX.OTP')
    expect(templateById.X40).toBe('BeforeAfter.otpu')
  })

  it('fails closed instead of substituting a generic family image', () => {
    expect(chartPreviewSource('K01')).toMatch(/^data:image\/svg\+xml/)
    expect(() => chartPreviewSource('REMOVED')).toThrow('Missing chart preview asset')
  })

  it('uses lightweight vector geometry without embedded renderer output', () => {
    expect(Object.keys(previewMarkup)).toHaveLength(34)
    for (const markup of Object.values(previewMarkup)) {
      expect(markup).toContain('viewBox="0 0 120 90"')
      expect(markup).not.toContain('matplotlib')
      expect(markup).not.toContain('data:image')
      expect(markup).toMatch(/<(?:path|polyline|line|circle|rect)\b/)
    }
  })

  it('preserves the distinguishing Origin gallery motif for representative families', () => {
    const markupFor = (profileId: string): string => {
      const entry = Object.entries(previewMarkup).find(([path]) => path.endsWith(`/${profileId}.svg`))
      expect(entry, `missing raw preview for ${profileId}`).toBeDefined()
      return entry![1].toLowerCase()
    }

    expect(markupFor('K03').match(/<circle\b/g)?.length).toBeGreaterThanOrEqual(8)
    expect(markupFor('K06').match(/<line\b/g)?.length).toBeGreaterThanOrEqual(12)
    expect(markupFor('K10').match(/<rect\b/g)?.length).toBeGreaterThanOrEqual(11)
    expect(markupFor('K20').match(/<rect\b/g)?.length).toBeGreaterThanOrEqual(11)
    expect(markupFor('K24').match(/<polyline\b/g)?.length).toBe(4)
    expect(markupFor('X40').match(/<line\b/g)?.length).toBe(4)
  })
})
