import { describe, expect, it } from 'vitest'

import {
  CORE_PROTOCOL_VERSION,
  parseCloseResponse,
  parseCoreProtocolMessage,
  parseTaskEvent,
  parseTaskId,
} from './desktop-contract.js'

describe('desktop contract validation', () => {
  it('accepts one strict Core response shape', () => {
    expect(parseCoreProtocolMessage({
      jsonrpc: '2.0',
      protocol_version: CORE_PROTOCOL_VERSION,
      id: 'req:one',
      result: { status: 'ok' },
    })).not.toBeNull()
  })

  it.each([
    null,
    {},
    { jsonrpc: '2.0', protocol_version: '2.0', method: 'system.ping' },
    { jsonrpc: '2.0', protocol_version: '1.0', id: 'req:one', result: {}, error: {} },
    { jsonrpc: '2.0', protocol_version: '1.0', method: 'system.ping', extra: true },
    { jsonrpc: '2.0', protocol_version: '1.0', method: 'invalid method' },
  ])('rejects invalid or extra-field Core messages', (value) => {
    expect(parseCoreProtocolMessage(value)).toBeNull()
  })

  it('rejects malformed task events and renderer IPC inputs', () => {
    expect(parseTaskEvent({
      schema_version: '1.0',
      event_type: 'task.state',
      task_id: 'task:one',
      sequence: 1,
      state: 'paused',
    })).toBeNull()
    expect(parseTaskEvent({
      schema_version: '1.0',
      event_type: 'task.state',
      task_id: 'task:one',
      sequence: 1,
      state: 'running',
      progress: { completed: 3, total: 2, unit: 'rows' },
    })).toBeNull()
    expect(parseTaskId({ taskId: 'task:one', rawPath: 'C:\\secret' })).toBeNull()
    expect(parseCloseResponse({ requestId: 'close:one', choice: 'force-quit' })).toBeNull()
  })
})
