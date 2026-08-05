import { describe, expect, it } from 'vitest'

import {
  assertSecureWebPreferences,
  PRODUCTION_CONTENT_SECURITY_POLICY,
} from './window-security.js'

describe('BrowserWindow security assertions', () => {
  it('accepts the hardened preference set', () => {
    expect(() => assertSecureWebPreferences({
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      webviewTag: false,
    })).not.toThrow()
  })

  it.each([
    { contextIsolation: false, nodeIntegration: false, sandbox: true },
    { contextIsolation: true, nodeIntegration: true, sandbox: true },
    { contextIsolation: true, nodeIntegration: false, sandbox: false },
    { contextIsolation: true, nodeIntegration: false, sandbox: true, webviewTag: true },
    { contextIsolation: true, nodeIntegration: false, sandbox: true, webSecurity: false },
  ])('rejects an unsafe preference override', (preferences) => {
    expect(() => assertSecureWebPreferences(preferences)).toThrow('security invariants')
  })

  it('blocks production renderer network and embedded content in CSP', () => {
    expect(PRODUCTION_CONTENT_SECURITY_POLICY).toContain("connect-src 'none'")
    expect(PRODUCTION_CONTENT_SECURITY_POLICY).toContain('img-src \'self\' data: plotagent-resource:')
    expect(PRODUCTION_CONTENT_SECURITY_POLICY).toContain("object-src 'none'")
    expect(PRODUCTION_CONTENT_SECURITY_POLICY).toContain("frame-ancestors 'none'")
  })
})
