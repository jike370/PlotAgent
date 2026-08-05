import { describe, expect, it } from 'vitest'

import { InMemoryResourceRegistry } from '../single-instance-routing.js'
import { sanitizeCoreResult } from './desktop-ipc.js'

describe('desktop product IPC boundary', () => {
  it('replaces Core artifact paths with random registered resources', () => {
    const registry = new InMemoryResourceRegistry()
    const result = sanitizeCoreResult({
      plot_id: 'plot:one',
      artifact: {
        resource_id: 'resource:core-preview',
        path: 'C:\\private\\project\\preview.png',
        content_hash: 'abc',
        size: 123,
      },
    }, registry)
    const serialized = JSON.stringify(result)

    expect(serialized).not.toContain('C:\\\\private')
    expect(serialized).not.toContain('"path"')
    expect(serialized).toContain('plotagent-resource://local/')
    expect(serialized).toContain('"kind":"preview"')
  })

  it('drops secret-shaped fields and rejects an unregistered absolute path value', () => {
    const registry = new InMemoryResourceRegistry()
    expect(sanitizeCoreResult({ status: 'ok', api_token: 'do-not-expose' }, registry))
      .toEqual({ status: 'ok' })
    expect(() => sanitizeCoreResult({ detail: 'C:\\private\\raw.csv' }, registry))
      .toThrow('Unregistered path')
  })
})
