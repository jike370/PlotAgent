import { describe, expect, it } from 'vitest'

import {
  CORE_PROTOCOL_VERSION,
  parseAgentContextInput,
  parseAgentDecideInput,
  parseAgentPlanConfirmInput,
  parseAgentPlanInput,
  parseCloseResponse,
  parseCoreProtocolMessage,
  parseCustomProviderConfigureInput,
  parseEngineActionInput,
  parseProjectRenameInput,
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
    expect(parseProjectRenameInput({ projectId: 'project:one', name: '  新名称  ' })).toEqual({
      projectId: 'project:one',
      name: '新名称',
    })
    expect(parseProjectRenameInput({ projectId: 'project:one', name: '', path: 'C:\\private' }))
      .toBeNull()

    expect(parseEngineActionInput({
      projectId: 'project:one',
      expectedProjectVersion: 1,
      action: {
        operation: 'set_axis',
        action_id: 'action:one',
        target: 'axis:one.x',
        expected_plot_version: 1,
        scale: 'log10',
      },
    })).not.toBeNull()
    expect(parseEngineActionInput({
      projectId: 'project:one',
      expectedProjectVersion: 1,
      action: { operation: 'export_plot', outputPath: 'C:\\private.svg' },
    })).toBeNull()
    expect(parseEngineActionInput({
      projectId: 'project:one',
      expectedProjectVersion: 1,
      action: { operation: 'set_title', apiToken: 'secret' },
    })).toBeNull()

    expect(parseAgentDecideInput({
      projectId: 'project:one',
      sourceDatasetId: 'source:one',
      sourceVersion: 1,
      expectedVersion: 2,
      executionMode: 'plan_only',
      target: { kind: 'plot', id: 'plot:one' },
      scope: 'current',
      utterance: 'Y axis 改成 log10，图例放到左上角',
    })).not.toBeNull()
    expect(parseAgentDecideInput({
      projectId: 'project:one',
      sourceDatasetId: 'source:one',
      sourceVersion: 1,
      expectedVersion: 2,
      selectedChartId: 'K02',
      executionMode: 'plan_only',
      scope: 'current',
      utterance: '以时间为 X、信号为 Y 绘制线点图',
    })).toMatchObject({ selectedChartId: 'K02', executionMode: 'plan_only' })
    expect(parseAgentDecideInput({
      projectId: 'project:one',
      sourceDatasetId: 'source:one',
      sourceVersion: 1,
      expectedVersion: 2,
      executionMode: 'plan_only',
      scope: 'batch',
      utterance: '修改上一批',
    })).toBeNull()
    expect(parseAgentContextInput({ projectId: 'project:one', conversationId: 'conversation:one' }))
      .toEqual({ projectId: 'project:one', conversationId: 'conversation:one' })
    expect(parseAgentPlanInput({ projectId: 'project:one', planId: 'plan:one' }))
      .toEqual({ projectId: 'project:one', planId: 'plan:one' })
    expect(parseAgentPlanConfirmInput({ projectId: 'project:one', planId: 'plan:one', accept: true }))
      .toEqual({ projectId: 'project:one', planId: 'plan:one', accept: true })
    expect(parseAgentPlanConfirmInput({ projectId: 'project:one', planId: 'plan:one', accept: 'yes' }))
      .toBeNull()
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
