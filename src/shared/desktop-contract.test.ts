import { describe, expect, it } from 'vitest'

import {
  CORE_PROTOCOL_VERSION,
  parseCloseResponse,
  parseCoreProtocolMessage,
  parseCustomProviderConfigureInput,
  parseEngineActionInput,
  parseProjectRenameInput,
  parseProjectResourceInput,
  parseTaskPlanConfirmInput,
  parseTaskPlanInput,
  parseTaskEvent,
  parseTaskId,
  parseWorkflowRunInput,
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

  it('preserves bounded task labels and failure details', () => {
    expect(parseTaskEvent({
      schema_version: '1.0',
      event_type: 'task.state',
      task_id: 'task:one',
      sequence: 2,
      state: 'failed',
      task_kind: 'import',
      label: '导入 measurements.csv',
      error: { code: 'IMPORT_HEADER_AMBIGUOUS', message: '无法确定表头，请指定表头行。' },
    })).toMatchObject({
      taskKind: 'import',
      label: '导入 measurements.csv',
      error: { code: 'IMPORT_HEADER_AMBIGUOUS', message: '无法确定表头，请指定表头行。' },
    })
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

    expect(parseWorkflowRunInput({
      projectId: 'project:one',
      selectedSources: [],
      selectedPlotIds: ['plot:one'],
      expectedProjectVersion: 2,
      instruction: 'Y axis 改成 log10，图例放到左上角',
    })).not.toBeNull()
    expect(parseWorkflowRunInput({
      projectId: 'project:one',
      selectedSources: [{ datasetId: 'source:one', sourceVersion: 1 }],
      selectedProfileIds: ['K02'],
      expectedProjectVersion: 2,
      instruction: '以时间为 X、信号为 Y 绘制线点图',
    })).toMatchObject({ selectedProfileIds: ['K02'] })
    expect(parseWorkflowRunInput({
      projectId: 'project:one',
      selectedSources: [],
      expectedProjectVersion: 2,
      instruction: '修改上一批',
    })).toBeNull()
    expect(parseTaskPlanInput({ projectId: 'project:one', planId: 'plan:one' }))
      .toEqual({ projectId: 'project:one', planId: 'plan:one' })
    expect(parseTaskPlanConfirmInput({ projectId: 'project:one', planId: 'plan:one', accept: true }))
      .toEqual({ projectId: 'project:one', planId: 'plan:one', accept: true })
    expect(parseTaskPlanConfirmInput({ projectId: 'project:one', planId: 'plan:one', accept: 'yes' }))
      .toBeNull()
  })

  it('accepts a bounded explicit multi-source workflow context', () => {
    expect(parseWorkflowRunInput({
      projectId: 'project:one',
      selectedSources: [
        { datasetId: 'source:one', sourceVersion: 1 },
        { datasetId: 'source:two', sourceVersion: 2 },
      ],
      expectedProjectVersion: 4,
      selectedProfileIds: ['K01'],
      instruction: '为选中的数据表分别绘图',
    })).toMatchObject({
      selectedSources: [
        { datasetId: 'source:one', sourceVersion: 1 },
        { datasetId: 'source:two', sourceVersion: 2 },
      ],
    })
    expect(parseWorkflowRunInput({
      projectId: 'project:one',
      selectedSources: [
        { datasetId: 'source:one', sourceVersion: 1 },
        { datasetId: 'source:one', sourceVersion: 1 },
      ],
      expectedProjectVersion: 4,
      instruction: '绘图',
    })).toBeNull()
  })

  it('rejects filesystem authority embedded in workflow requests', () => {
    expect(parseWorkflowRunInput({
      projectId: 'project:one',
      expectedProjectVersion: 2,
      selectedSources: [{ datasetId: 'source:a', sourceVersion: 1 }],
      instruction: '绘制散点图',
      outputPath: 'C:\\private.opju',
    })).toBeNull()
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
