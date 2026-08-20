import { describe, expect, it } from 'vitest'

import { parsePlotMentions, registerPlotReferences } from './plotReferences'

describe('plot references', () => {
  it('assigns stable monotonic project-local numbers without reusing removed entries', () => {
    let stored: string | null = null
    const storage = { getItem: () => stored, setItem: (_key: string, value: string) => { stored = value } }
    expect(registerPlotReferences(storage, 'project:one', ['plot:a', 'plot:b'])).toEqual([
      { plotId: 'plot:a', number: 1 }, { plotId: 'plot:b', number: 2 },
    ])
    expect(registerPlotReferences(storage, 'project:one', ['plot:b', 'plot:c'])).toEqual([
      { plotId: 'plot:a', number: 1 }, { plotId: 'plot:b', number: 2 }, { plotId: 'plot:c', number: 3 },
    ])
  })

  it('parses unique explicit mentions in user order', () => {
    expect(parsePlotMentions('@图2 和 @图5，别再改 @图2')).toEqual([2, 5])
    expect(parsePlotMentions('上一张图和图2')).toEqual([])
  })
})
