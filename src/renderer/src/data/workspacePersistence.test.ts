import { describe, expect, it } from 'vitest'

import { readWorkspaceSelection, writeWorkspaceSelection } from './workspacePersistence'

describe('workspace persistence', () => {
  it('round-trips the active data, chart, and confirmed mapping', () => {
    let stored: string | null = null
    const storage = {
      getItem: () => stored,
      setItem: (_key: string, value: string) => { stored = value },
    }
    writeWorkspaceSelection(storage, 'project:one', {
      datasetId: 'source:one',
      chartId: 'K01',
      mapping: { roles: { x: 'field:x', y: 'field:y' } },
    })
    expect(readWorkspaceSelection(storage, 'project:one')).toEqual({
      datasetId: 'source:one',
      chartId: 'K01',
      mapping: { roles: { x: 'field:x', y: 'field:y' } },
    })
  })

  it('fails closed for malformed persisted values', () => {
    expect(readWorkspaceSelection({ getItem: () => '{"mapping":{"roles":{"x":"C:\\\\secret"}}}' }, 'project:one'))
      .toBeUndefined()
  })
})
