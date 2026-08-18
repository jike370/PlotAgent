import { describe, expect, it } from 'vitest'

import { matchProviderPreset, providerPreset, providerPresets } from './providerPresets'

describe('provider presets', () => {
  it('pins safe OpenAI-compatible endpoints and non-empty model choices', () => {
    expect(providerPresets.map((item) => item.id)).toEqual(['zhipu', 'deepseek', 'aliyun'])
    for (const item of providerPresets) {
      expect(new URL(item.baseUrl).protocol).toBe('https:')
      expect(item.models.length).toBeGreaterThan(0)
      expect(new Set(item.models.map((model) => model.id)).size).toBe(item.models.length)
    }
    expect(providerPreset('zhipu')?.models[0]?.id).toBe('glm-4.7-flash')
  })

  it('recognizes saved presets but preserves an advanced custom endpoint', () => {
    expect(matchProviderPreset('https://api.deepseek.com/')).toBe('deepseek')
    expect(matchProviderPreset('https://provider.example/v1')).toBe('custom')
    expect(matchProviderPreset(undefined)).toBe('zhipu')
  })

  it('keeps current public model identifiers in the Aliyun preset', () => {
    expect(providerPreset('aliyun')?.models.map((model) => model.id)).toEqual([
      'qwen3.6-flash',
      'qwen3.7-plus',
      'qwen3.7-max',
    ])
  })
})
