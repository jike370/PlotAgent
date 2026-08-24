/// <reference types="node" />

import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const styles = readFileSync(resolve(process.cwd(), 'src/renderer/src/styles.css'), 'utf8')
const conversationWorkspace = readFileSync(resolve(process.cwd(), 'src/renderer/src/components/ConversationWorkspace.tsx'), 'utf8')

describe('renderer typography', () => {
  it('uses a CJK glyph-capable fallback for full-width punctuation', () => {
    expect(styles).toContain('font-family: "PlotAgent CJK"')
    expect(styles).toContain('local("Microsoft YaHei UI")')
    expect(styles).toContain('U+FF00-FFEF')
    expect(styles).toContain('"PlotAgent CJK", "Segoe UI Variable Text"')
  })
})

describe('renderer motion system', () => {
  it('uses shared exact timing and easing tokens', () => {
    expect(styles).toContain('--motion-state: 120ms')
    expect(styles).toContain('--motion-drawer: 220ms')
    expect(styles).toContain('--ease-out: cubic-bezier(0.23, 1, 0.32, 1)')
    expect(styles).toContain('--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1)')
  })

  it('keeps functional charts and keyboard submission free from decorative motion', () => {
    expect(styles).not.toContain('.plot-open:hover .batch-plot')
    expect(conversationWorkspace).toContain("behavior: 'auto'")
    expect(conversationWorkspace).not.toContain("behavior: 'smooth'")
  })

  it('ships entry, exit, and reduced-motion treatments together', () => {
    expect(styles).toContain('@starting-style')
    expect(styles).toContain(".product-toast[data-motion-state='exiting']")
    expect(styles).toContain(".drawer-backdrop[data-motion-state='exiting']")
    expect(styles).toContain('@media (prefers-reduced-motion: reduce)')
    expect(styles).not.toContain('transition-duration: 0.01ms !important')
  })
})
