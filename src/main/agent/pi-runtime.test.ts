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
  route: 'agent',
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

function toolCallStream(name: string, args: Record<string, JsonValue>): ReturnType<StreamFn> {
  const stream = createAssistantMessageEventStream()
  const message: AssistantMessage = {
    role: 'assistant',
    content: [{
      type: 'toolCall', id: 'call-1', name,
      arguments: args,
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

function submitDraftStream(): ReturnType<StreamFn> {
  return toolCallStream('submit_task_draft', { task_draft: draft })
}

const request = {
  project_id: 'project:test', client_run_id: 'workflow-client:test',
  expected_project_version: 0, instruction: '画折线图',
  selected_sources: [{ dataset_id: 'source:test', source_version: 1 }],
}

describe('PiAgentRuntime workflow orchestration', () => {
  it('uses bounded raw evidence to propose parser options without plotting semantics', async () => {
    const calls: string[] = []
    const core: PiCoreBridge = {
      request: async (method): Promise<JsonValue> => {
        calls.push(method)
        if (method === 'data_preparation.sources.inspect') return {
          source_format: 'txt', generic_parser_code: 'IMPORT_DELIMITER_AMBIGUOUS',
          text_previews: [{ encoding: 'utf-8-sig', lines: ['time;value', '0;1'] }],
        }
        return { base_url: 'https://model.example/v1', model_id: 'model', api_key: 'secret' }
      },
    }
    const runtime = new PiAgentRuntime({
      core,
      emit: () => undefined,
      streamFn: (() => toolCallStream('submit_parser_options', {
        options: { encoding: 'utf-8-sig', delimiter: ';', header_row: 1 },
        rationale: '预览稳定显示分号分隔且首行为列名。',
      })) as StreamFn,
    })

    await expect(runtime.prepareData({
      project_id: 'project:test',
      client_run_id: 'data-client:test',
      preparation_run_id: 'data-run:test',
      source_path: 'D:\\authorized.txt',
      import_outcome: { kind: 'clarification' },
    })).resolves.toMatchObject({
      outcome: 'proposal',
      options: { encoding: 'utf-8-sig', delimiter: ';', header_row: 1 },
      model_turn_count: 1,
      tool_call_count: 1,
      input_token_count: 1,
      output_token_count: 1,
    })
    expect(calls).toEqual(['data_preparation.sources.inspect', 'provider.runtime.get'])
  })

  it('fails closed when raw evidence does not support parser parameters', async () => {
    const core: PiCoreBridge = {
      request: async (method): Promise<JsonValue> => method === 'data_preparation.sources.inspect'
        ? { source_format: 'xls', raw_preview_unavailable: true }
        : { base_url: 'https://model.example/v1', model_id: 'model', api_key: 'secret' },
    }
    const runtime = new PiAgentRuntime({
      core,
      emit: () => undefined,
      streamFn: (() => toolCallStream('report_preparation_unresolved', {
        reason: '没有可核验的原始预览，不能安全猜测。',
      })) as StreamFn,
    })

    await expect(runtime.prepareData({
      project_id: 'project:test', client_run_id: 'data-client:test',
      preparation_run_id: 'data-run:test', source_path: 'D:\\authorized.xls',
    })).resolves.toMatchObject({ outcome: 'unresolved' })
  })

  it('returns a Core-owned structured result without invoking the model', async () => {
    const calls: string[] = []
    const params: JsonValue[] = []
    const core: PiCoreBridge = {
      request: async (method, value) => {
        calls.push(method)
        params.push(value ?? null)
        return { outcome: 'draft_ready', task_plan: { state: 'awaiting_confirmation' } }
      },
    }
    const runtime = new PiAgentRuntime({ core, emit: () => undefined })

    await expect(runtime.run(request)).resolves.toMatchObject({ outcome: 'draft_ready' })
    expect(calls).toEqual(['workflow.prepare'])
    expect(params[0]).toEqual({
      project_id: 'project:test',
      expected_project_version: 0,
      instruction: '画折线图',
      selected_sources: [{ dataset_id: 'source:test', source_version: 1 }],
    })
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

  it('does not preinspect or rewrite a multi-source instruction before Agent planning', async () => {
    const calls: string[] = []
    const core: PiCoreBridge = {
      request: async (method): Promise<JsonValue> => {
        calls.push(method)
        if (method === 'workflow.prepare') return {
          outcome: 'agent_required', workflow_run_id: 'workflow:test',
          workflow_context: {
            workflow_run_id: 'workflow:test',
            instruction: '比较两张表的结构，同构后分别绘图',
            selected_source_aliases: ['data_1', 'data_2'],
            fields: [],
          },
          task_draft_schema: { type: 'object' }, system_prompt: 'Submit a TaskDraft.',
        }
        if (method === 'provider.runtime.get') return {
          base_url: 'https://model.example/v1', model_id: 'model', api_key: 'secret',
        }
        if (method === 'workflow.inspect') return {
          result: { source_aliases: ['data_1', 'data_2'], isomorphic: true },
          audit: { tool_name: 'compare_schemas' },
        }
        return { outcome: 'draft_ready', task_plan: { state: 'awaiting_confirmation' } }
      },
    }
    const runtime = new PiAgentRuntime({
      core, emit: () => undefined, streamFn: submitDraftStream as StreamFn,
    })

    await runtime.run({
      ...request,
      selected_sources: [
        { dataset_id: 'source:one', source_version: 1 },
        { dataset_id: 'source:two', source_version: 1 },
      ],
    })
    expect(calls).toEqual([
      'workflow.prepare', 'provider.runtime.get', 'workflow.submit_draft',
    ])
  })

  it('lets Pi pause the same workflow with structured clarification questions', async () => {
    const calls: string[] = []
    const core: PiCoreBridge = {
      request: async (method, params): Promise<JsonValue> => {
        calls.push(method)
        if (method === 'workflow.prepare') return {
          outcome: 'agent_required', workflow_run_id: 'workflow:test',
          workflow_context: { workflow_run_id: 'workflow:test' },
          task_draft_schema: { type: 'object' }, system_prompt: 'Ask only if required.',
        }
        if (method === 'provider.runtime.get') return {
          base_url: 'https://model.example/v1', model_id: 'model', api_key: 'secret',
        }
        expect(params).toEqual({
          project_id: 'project:test',
          workflow_run_id: 'workflow:test',
          questions: [{
            question_key: 'chart_type',
            prompt: '请选择图类。',
            answer_kind: 'profile',
            choices: ['K01', 'K03'],
            required: true,
          }],
        })
        return {
          outcome: 'needs_input',
          workflow_run_id: 'workflow:test',
          questions: [],
        }
      },
    }
    const streamFn = (() => toolCallStream('ask_user', {
      questions: [{
        question_key: 'chart_type',
        prompt: '请选择图类。',
        answer_kind: 'profile',
        choices: ['K01', 'K03'],
        required: true,
      }],
    })) as StreamFn
    const runtime = new PiAgentRuntime({ core, emit: () => undefined, streamFn })

    await expect(runtime.run(request)).resolves.toMatchObject({
      outcome: 'needs_input', workflow_run_id: 'workflow:test',
    })
    expect(calls).toEqual(['workflow.prepare', 'provider.runtime.get', 'workflow.ask_user'])
  })

  it('stops after the Core-owned model-turn budget', async () => {
    let modelCalls = 0
    const core: PiCoreBridge = {
      request: async (method): Promise<JsonValue> => {
        if (method === 'workflow.prepare') return {
          outcome: 'agent_required', workflow_run_id: 'workflow:test',
          workflow_context: {
            workflow_run_id: 'workflow:test',
            budget: { max_agent_turns: 1 },
          },
          task_draft_schema: { type: 'object' }, system_prompt: 'Use bounded tools.',
        }
        if (method === 'provider.runtime.get') return {
          base_url: 'https://model.example/v1', model_id: 'model', api_key: 'secret',
        }
        return { result: { sources: [] }, audit: { tool_name: 'list_sources' } }
      },
    }
    const runtime = new PiAgentRuntime({
      core,
      emit: () => undefined,
      streamFn: (() => {
        modelCalls += 1
        return toolCallStream('list_sources', {})
      }) as StreamFn,
    })

    await expect(runtime.run(request)).rejects.toMatchObject({
      code: 'PI_TURN_BUDGET_EXCEEDED',
    })
    expect(modelCalls).toBe(1)
  })

  it('maps timeout and superseded runs to stable public errors', () => {
    expect(publicPiAgentError(new Error('other'))).toBeUndefined()
    expect(publicPiAgentError({})).toBeUndefined()
  })
})
