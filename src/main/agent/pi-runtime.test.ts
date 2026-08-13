import { createAssistantMessageEventStream, type AssistantMessage, type JsonValue } from '@earendil-works/pi-ai'
import type { StreamFn } from '@earendil-works/pi-agent-core'
import { describe, expect, it } from 'vitest'

import { PiAgentRuntime, type PiAgentRuntimeEvent, type PiCoreBridge } from './pi-runtime.js'

const decision = {
  decision_type: 'no_change',
  target_alias: 'active_target',
  reason: 'No change requested.',
}

const decisionSchema = {
  type: 'object',
  properties: {
    decision_type: { const: 'no_change' },
    target_alias: { type: 'string' },
    reason: { type: 'string' },
  },
  required: ['decision_type', 'target_alias', 'reason'],
  additionalProperties: false,
}

function toolCallStream(): ReturnType<StreamFn> {
  const stream = createAssistantMessageEventStream()
  const message: AssistantMessage = {
    role: 'assistant',
    content: [{
      type: 'toolCall',
      id: 'call-1',
      name: 'submit_plotagent_decision',
      arguments: decision,
    }],
    api: 'openai-completions',
    provider: 'test',
    model: 'test-model',
    usage: {
      input: 1,
      output: 1,
      cacheRead: 0,
      cacheWrite: 0,
      totalTokens: 2,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
    },
    stopReason: 'toolUse',
    timestamp: Date.now(),
  }
  queueMicrotask(() => {
    stream.push({ type: 'start', partial: message })
    stream.push({ type: 'toolcall_start', contentIndex: 0, partial: message })
    stream.push({ type: 'toolcall_end', contentIndex: 0, toolCall: message.content[0] as never, partial: message })
    stream.push({ type: 'done', reason: 'toolUse', message })
  })
  return stream
}

describe('PiAgentRuntime', () => {
  it('runs Pi with one decision tool and sends the decision back to Core authority', async () => {
    const calls: { method: string; params?: JsonValue }[] = []
    const core: PiCoreBridge = {
      request: async (method, params) => {
        calls.push({ method, params })
        if (method === 'provider.runtime.get') {
          return { base_url: 'https://model.example/v1', model_id: 'model', api_key: 'secret-key' } as JsonValue
        }
        const request = params as Record<string, JsonValue>
        if (request.prepare_only === true) {
          return {
            accepted: true,
            prepared: true,
            context_envelope: { context_hash: 'a'.repeat(64) },
            decision_schema: decisionSchema,
            system_prompt: 'Return one valid PlotAgent decision.',
          } as JsonValue
        }
        expect(request.external_decision).toEqual(decision)
        return { accepted: true, decision } as JsonValue
      },
    }
    const events: PiAgentRuntimeEvent[] = []
    const runtime = new PiAgentRuntime({
      core,
      emit: (event) => events.push(event),
      streamFn: toolCallStream as StreamFn,
    })

    const result = await runtime.decide({
      project_id: 'project:test',
      client_model_run_id: 'model-run:test',
    })

    expect(result).toEqual({ accepted: true, decision })
    expect(calls.map((item) => item.method)).toEqual([
      'agent.engine.decide',
      'provider.runtime.get',
      'agent.engine.decide',
    ])
    expect(events.map((item) => item.stage)).toContain('validating_decision')
    expect(events.at(-1)?.stage).toBe('completed')
  })

  it('returns deterministic Core preflight without calling the model provider', async () => {
    const core: PiCoreBridge = {
      request: async () => ({ accepted: true, decision }),
    }
    const runtime = new PiAgentRuntime({
      core,
      emit: () => undefined,
      streamFn: () => { throw new Error('model must not run') },
    })
    await expect(runtime.decide({
      project_id: 'project:test',
      client_model_run_id: 'model-run:test',
    })).resolves.toEqual({ accepted: true, decision })
  })
})
