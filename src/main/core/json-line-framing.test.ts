import { describe, expect, it } from 'vitest'

import {
  CORE_PROTOCOL_VERSION,
  createCoreRequest,
} from '../../shared/desktop-contract.js'
import { encodeJsonLine, JsonLineDecoder } from './json-line-framing.js'

describe('JSON line framing', () => {
  it('reassembles a message split across chunks', () => {
    const decoder = new JsonLineDecoder()
    const encoded = encodeJsonLine(createCoreRequest('req:one', 'system.ping'))

    expect(decoder.push(encoded.subarray(0, 7))).toEqual([])
    expect(decoder.push(encoded.subarray(7))).toEqual([
      {
        kind: 'message',
        message: createCoreRequest('req:one', 'system.ping'),
      },
    ])
  })

  it('decodes multiple newline-delimited messages in one chunk', () => {
    const decoder = new JsonLineDecoder()
    const first = encodeJsonLine(createCoreRequest('req:one', 'system.ping'))
    const second = encodeJsonLine(createCoreRequest('req:two', 'tasks.snapshot'))

    const frames = decoder.push(Buffer.concat([first, second]))

    expect(frames).toHaveLength(2)
    expect(frames.every((frame) => frame.kind === 'message')).toBe(true)
  })

  it('rejects malformed, oversized, and truncated frames without returning their content', () => {
    const decoder = new JsonLineDecoder(128)
    expect(decoder.push('{not-json}\n')).toEqual([
      { kind: 'error', code: 'CORE_PROTOCOL_INVALID_FRAME' },
    ])
    expect(decoder.push(`${'x'.repeat(129)}\n`)).toEqual([
      { kind: 'error', code: 'CORE_PROTOCOL_FRAME_TOO_LARGE' },
    ])
    decoder.push(JSON.stringify({
      jsonrpc: '2.0',
      protocol_version: CORE_PROTOCOL_VERSION,
      method: 'health.heartbeat',
    }))
    expect(decoder.end()).toEqual([
      { kind: 'error', code: 'CORE_PROTOCOL_TRUNCATED_FRAME' },
    ])
  })
})
