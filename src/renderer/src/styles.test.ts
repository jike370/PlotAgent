/// <reference types="node" />

import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const styles = readFileSync(resolve(process.cwd(), 'src/renderer/src/styles.css'), 'utf8')

describe('renderer typography', () => {
  it('uses a CJK glyph-capable fallback for full-width punctuation', () => {
    expect(styles).toContain('font-family: "PlotAgent CJK"')
    expect(styles).toContain('local("Microsoft YaHei UI")')
    expect(styles).toContain('U+FF00-FFEF')
    expect(styles).toContain('"PlotAgent CJK", "Segoe UI Variable Text"')
  })
})
