import { createAssistantMessageEventStream, type AssistantMessage, type JsonValue } from '@earendil-works/pi-ai'
import type { StreamFn } from '@earendil-works/pi-agent-core'
import { describe, expect, it } from 'vitest'

import {
  PiAgentRuntime,
  publicPiAgentError,
  type PiAgentRuntimeEvent,
  type PiCoreBridge,
} from './pi-runtime.js'

const draft = {
  schema_version: 'task-draft.v1',
  draft_id: 'draft:test',
  workflow_run_id: 'workflow:test',
  route: 'agent_single_turn',
  summary: '创建折线图',
  items: [{
    task_kind: 'create',
    item_id: 'item:test.1', plot_alias: 'plot_1', profile_id: 'K01',
    source_aliases: ['data_1'], data_operations: [],
    bindings: [
      { role: 'x', source_alias: 'data_1', field_alias: 'data_1_field_1' },
      { role: 'y', source_alias: 'data_1', field_alias: 'data_1_field_2' },
    ],
    visual_actions: [],
  }],
  confidence: 0.95,
  hard_constraints: ['preserve_source_values'],
}

function submitDraftStream(): ReturnType<StreamFn> {
  const stream = createAssistantMessageEventStream()
  const message: AssistantMessage = {
    role: 'assistant',
    content: [{
      type: 'toolCall', id: 'call-1', name: 'submit_task_draft',
      arguments: { task_draft: draft },
    }],
    api: 'openai-completions', provider: 'test', model: 'test-model',
    usage: {
      input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
    },
    stopReason: 'toolUse', timestamp: Date.now(),
  }
  queueMicrotask(() => {
    stream.push({ type: 'start', partial: message })
    stream.push({ type: 'toolcall_start', contentIndex: 0, partial: message })
    stream.push({
      type: 'toolcall_end', contentIndex: 0,
      toolCall: message.content[0] as never, partial: message,
    })
    stream.push({ type: 'done', reason: 'toolUse', message })
  })
  return stream
}

const request = {
  project_id: 'project:test', client_run_id: 'workflow-client:test',
  expected_project_version: 0, instruction: '画折线图',
  selected_sources: [{ dataset_id: 'source:test', source_version: 1 }],
}

describe('PiAgentRuntime workflow orchestration', () => {
  it('bypasses the model when Core resolves a deterministic draft', async () => {
    const calls: string[] = []
    const core: PiCoreBridge = {
      request: async (method) => {
        calls.push(method)
        return { outcome: 'draft_ready', task_plan: { state: 'awaiting_confirmation' } }
      },
    }
    const runtime = new PiAgentRuntime({ core, emit: () => undefined })

    await expect(runtime.run(request)).resolves.toMatchObject({ outcome: 'draft_ready' })
    expect(calls).toEqual(['workflow.prepare'])
  })

  it('lets Pi submit a TaskDraft while Core remains the plan authority', async () => {
    const calls: string[] = []
    const events: PiAgentRuntimeEvent[] = []
    const core: PiCoreBridge = {
      request: async (method, params): Promise<JsonValue> => {
        calls.push(method)
        if (method === 'workflow.prepare') return {
          outcome: 'agent_required', workflow_run_id: 'workflow:test',
          workflow_context: { workflow_run_id: 'workflow:test' },
          task_draft_schema: { type: 'object' }, system_prompt: 'Submit a TaskDraft.',
        }
        if (method === 'provider.runtime.get') return {
          base_url: 'https://model.example/v1', model_id: 'model', api_key: 'secret',
        }
        expect(params).toMatchObject({ workflow_run_id: 'workflow:test', task_draft: draft })
        return { outcome: 'draft_ready', task_plan: { state: 'awaiting_confirmation' } }
      },
    }
    const runtime = new PiAgentRuntime({
      core, emit: (event) => events.push(event), streamFn: submitDraftStream as StreamFn,
    })

    await expect(runtime.run(request)).resolves.toMatchObject({ outcome: 'draft_ready' })
    expect(calls).toEqual([
      'workflow.prepare', 'provider.runtime.get', 'workflow.submit_draft',
    ])
    expect(events.map((event) => event.stage)).toContain('validating_draft')
    expect(events.at(-1)?.stage).toBe('completed')
  })

  it('maps timeout and superseded runs to stable public errors', () => {
    expect(publicPiAgentError(new Error('other'))).toBeUndefined()
    expect(publicPiAgentError({})).toBeUndefined()
  })
})
