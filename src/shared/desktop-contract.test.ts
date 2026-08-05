import { describe, expect, it } from 'vitest'

import {
  CORE_PROTOCOL_VERSION,
  parseAgentDecideInput,
  parseCloseResponse,
  parseCoreProtocolMessage,
  parseCustomProviderConfigureInput,
  parsePlotPatchInput,
  parseProjectResourceInput,
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

  it('accepts only narrow product inputs without paths or credentials', () => {
    expect(parseProjectResourceInput({ resourceId: 'resource:one' })).toEqual({
      resourceId: 'resource:one',
    })
    expect(parseProjectResourceInput({ resourceId: 'resource:one', path: 'C:\\private.plotproj' }))
      .toBeNull()

    expect(parsePlotPatchInput({
      projectId: 'project:one',
      plotId: 'plot:one',
      plotVersion: 1,
      patch: { kind: 'set_axis_scale', scale: 'log10' },
    })).not.toBeNull()
    expect(parsePlotPatchInput({
      projectId: 'project:one',
      plotId: 'plot:one',
      plotVersion: 1,
      patch: { outputPath: 'C:\\private.svg' },
    })).toBeNull()
    expect(parsePlotPatchInput({
      projectId: 'project:one',
      plotId: 'plot:one',
      plotVersion: 1,
      patch: { apiToken: 'secret' },
    })).toBeNull()

    expect(parseAgentDecideInput({
      projectId: 'project:one',
      sourceDatasetId: 'source:one',
      sourceVersion: 1,
      expectedVersion: 2,
      target: { kind: 'plot', id: 'plot:one' },
      scope: 'current',
      utterance: 'Y axis 改成 log10，图例放到左上角',
    })).not.toBeNull()
  })

  it('accepts HTTPS and loopback HTTP custom-provider configuration', () => {
    expect(parseCustomProviderConfigureInput({
      baseUrl: 'https://provider.example/v1',
      modelId: 'research-model',
      apiKey: 'secret-value',
      retentionAcknowledged: true,
    })).toMatchObject({ baseUrl: 'https://provider.example/v1', modelId: 'research-model' })
    expect(parseCustomProviderConfigureInput({
      baseUrl: 'http://localhost:11434/v1',
      modelId: 'local-model',
      retentionAcknowledged: true,
    })).toMatchObject({ baseUrl: 'http://localhost:11434/v1', modelId: 'local-model' })
    expect(parseCustomProviderConfigureInput({
      baseUrl: 'http://127.0.0.1:8000/v1',
      modelId: 'local-model',
      retentionAcknowledged: true,
    })).toMatchObject({ baseUrl: 'http://127.0.0.1:8000/v1', modelId: 'local-model' })
    expect(parseCustomProviderConfigureInput({
      baseUrl: 'http://[::1]:8000/v1',
      modelId: 'local-model',
      retentionAcknowledged: true,
    })).toMatchObject({ baseUrl: 'http://[::1]:8000/v1', modelId: 'local-model' })
    expect(parseCustomProviderConfigureInput({
      baseUrl: 'http://provider.example/v1',
      modelId: 'research-model',
      retentionAcknowledged: true,
    })).toBeNull()
    expect(parseCustomProviderConfigureInput({
      baseUrl: 'https://user:secret@provider.example/v1',
      modelId: 'research-model',
      retentionAcknowledged: true,
    })).toBeNull()
  })
})
