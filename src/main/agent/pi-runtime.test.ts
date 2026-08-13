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

function noDecisionStream(): ReturnType<StreamFn> {
  const stream = createAssistantMessageEventStream()
  const message: AssistantMessage = {
    role: 'assistant',
    content: [{ type: 'text', text: 'I did not call the required tool.' }],
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
    stopReason: 'stop',
    timestamp: Date.now(),
  }
  queueMicrotask(() => {
    stream.push({ type: 'start', partial: message })
    stream.push({ type: 'done', reason: 'stop', message })
  })
  return stream
}

function multipleDecisionStream(): ReturnType<StreamFn> {
  const stream = createAssistantMessageEventStream()
  const calls = [1, 2].map((index) => ({
    type: 'toolCall' as const,
    id: `call-${index}`,
    name: 'submit_plotagent_decision',
    arguments: decision,
  }))
  const message: AssistantMessage = {
    role: 'assistant',
    content: calls,
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
    calls.forEach((call, contentIndex) => {
      stream.push({ type: 'toolcall_start', contentIndex, partial: message })
      stream.push({ type: 'toolcall_end', contentIndex, toolCall: call, partial: message })
    })
    stream.push({ type: 'done', reason: 'toolUse', message })
  })
  return stream
}

function preparedHandoff(): JsonValue {
  return {
    accepted: true,
    prepared: true,
    context_envelope: { context_hash: 'a'.repeat(64) },
    decision_schema: decisionSchema,
    system_prompt: 'Return one valid PlotAgent decision.',
  }
}

function configuredProvider(): JsonValue {
  return { base_url: 'https://model.example/v1', model_id: 'model', api_key: 'secret-key' }
}

describe('PiAgentRuntime', () => {
  it('runs Pi with one decision tool and sends the decision back to Core authority', async () => {
    const calls: { method: string; params?: JsonValue }[] = []
    const core: PiCoreBridge = {
      request: async (method, params) => {
        calls.push({ method, params })
        if (method === 'provider.runtime.get') {
          return configuredProvider()
        }
        const request = params as Record<string, JsonValue>
        if (request.prepare_only === true) {
          return preparedHandoff()
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
    expect(events.map((item) => item.sequence)).toEqual(
      events.map((_, index) => index + 1),
    )
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

  it('emits a terminal failure when provider configuration is unavailable', async () => {
    const events: PiAgentRuntimeEvent[] = []
    const core: PiCoreBridge = {
      request: async (method) => method === 'agent.engine.decide' ? preparedHandoff() : {},
    }
    const runtime = new PiAgentRuntime({
      core,
      emit: (event) => events.push(event),
      streamFn: () => { throw new Error('model must not run') },
    })

    await expect(runtime.decide({
      project_id: 'project:test',
      client_model_run_id: 'model-run:provider-missing',
    })).rejects.toMatchObject({ code: 'PROVIDER_NOT_CONFIGURED' })
    expect(events.map((item) => item.stage)).toEqual(['preparing_context', 'failed'])
  })

  it('rejects a model response that does not submit the decision tool', async () => {
    const events: PiAgentRuntimeEvent[] = []
    const core: PiCoreBridge = {
      request: async (method) => method === 'provider.runtime.get'
        ? configuredProvider()
        : preparedHandoff(),
    }
    const runtime = new PiAgentRuntime({
      core,
      emit: (event) => events.push(event),
      streamFn: noDecisionStream as StreamFn,
    })

    await expect(runtime.decide({
      project_id: 'project:test',
      client_model_run_id: 'model-run:no-decision',
    })).rejects.toMatchObject({ code: 'PI_DECISION_MISSING' })
    expect(events.at(-1)?.stage).toBe('failed')
  })

  it('rejects multiple decision tool calls without saving either as an accepted plan', async () => {
    const calls: { method: string; params?: JsonValue }[] = []
    const core: PiCoreBridge = {
      request: async (method, params) => {
        calls.push({ method, params })
        return method === 'provider.runtime.get' ? configuredProvider() : preparedHandoff()
      },
    }
    const runtime = new PiAgentRuntime({
      core,
      emit: () => undefined,
      streamFn: multipleDecisionStream as StreamFn,
    })

    await expect(runtime.decide({
      project_id: 'project:test',
      client_model_run_id: 'model-run:multiple',
    })).rejects.toMatchObject({ code: 'PI_MULTIPLE_DECISIONS' })
    expect(calls.filter((item) => {
      const params = item.params as Record<string, JsonValue> | undefined
      return params?.external_decision !== undefined
    })).toHaveLength(0)
  })

  it('emits failure and never completion when Core rejects the submitted decision', async () => {
    const events: PiAgentRuntimeEvent[] = []
    const core: PiCoreBridge = {
      request: async (method, params) => {
        if (method === 'provider.runtime.get') return configuredProvider()
        const request = params as Record<string, JsonValue>
        if (request.prepare_only === true) return preparedHandoff()
        throw new Error('Core validation rejected the decision')
      },
    }
    const runtime = new PiAgentRuntime({
      core,
      emit: (event) => events.push(event),
      streamFn: toolCallStream as StreamFn,
    })

    await expect(runtime.decide({
      project_id: 'project:test',
      client_model_run_id: 'model-run:rejected',
    })).rejects.toThrow('Core validation rejected the decision')
    expect(events.at(-1)?.stage).toBe('failed')
    expect(events.filter((event) => event.stage === 'completed')).toHaveLength(0)
  })

  it('treats a structured Core rejection as a failed run', async () => {
    const events: PiAgentRuntimeEvent[] = []
    const core: PiCoreBridge = {
      request: async (method, params) => {
        if (method === 'provider.runtime.get') return configuredProvider()
        const request = params as Record<string, JsonValue>
        if (request.prepare_only === true) return preparedHandoff()
        return {
          accepted: false,
          error: { code: 'ENGINE_PLAN_INVALID' },
        }
      },
    }
    const runtime = new PiAgentRuntime({
      core,
      emit: (event) => events.push(event),
      streamFn: toolCallStream as StreamFn,
    })

    await expect(runtime.decide({
      project_id: 'project:test',
      client_model_run_id: 'model-run:structured-rejection',
    })).rejects.toMatchObject({ code: 'ENGINE_PLAN_INVALID' })
    expect(events.at(-1)?.stage).toBe('failed')
    expect(events.filter((event) => event.stage === 'completed')).toHaveLength(0)
  })

  it('prevents an older preparation request from saving after a newer run starts', async () => {
    let releaseFirst: ((value: JsonValue) => void) | undefined
    const firstPrepared = new Promise<JsonValue>((resolve) => { releaseFirst = resolve })
    const externalRuns: string[] = []
    const events: PiAgentRuntimeEvent[] = []
    const core: PiCoreBridge = {
      request: async (method, params) => {
        const request = params as Record<string, JsonValue>
        const runId = String(request.client_model_run_id ?? '')
        if (method === 'provider.runtime.get') return configuredProvider()
        if (request.prepare_only === true && runId === 'model-run:first') return firstPrepared
        if (request.prepare_only === true) return { accepted: true, decision }
        externalRuns.push(runId)
        return { accepted: true, decision }
      },
    }
    const runtime = new PiAgentRuntime({
      core,
      emit: (event) => events.push(event),
      streamFn: toolCallStream as StreamFn,
    })

    const first = runtime.decide({
      project_id: 'project:test',
      client_model_run_id: 'model-run:first',
    })
    await Promise.resolve()
    await expect(runtime.decide({
      project_id: 'project:test',
      client_model_run_id: 'model-run:second',
    })).resolves.toEqual({ accepted: true, decision })
    releaseFirst?.(preparedHandoff())

    await expect(first).rejects.toMatchObject({ code: 'PI_RUN_SUPERSEDED' })
    expect(externalRuns).toEqual([])
    expect(events.filter((event) => (
      event.runId === 'model-run:first' && ['completed', 'failed'].includes(event.stage)
    ))).toHaveLength(0)
  })
})
