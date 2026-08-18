import { describe, expect, it, vi } from 'vitest'

import type { AgentActivation, AgentYieldContract } from '../../shared/generated/contracts.js'
import { AgentTaskPump, type DurableTaskCoreBridge } from './task-pump.js'

const activation: AgentActivation = {
  activation_id: 'activation:test',
  task_id: 'task:test',
  task_version: 1,
  reason: 'new_task',
  task_state: 'created',
  original_instruction: 'Create a line chart.',
  allowed_tools: ['inspect_source'],
  permission_phase: 'p0_read',
  activation_budget: { max_model_turns: 4, timeout_ms: 30_000 },
  task_budget: { limits: { max_model_calls: 8 }, usage: {} },
  deadline: '2099-08-18T10:00:00Z',
  created_at: '2026-08-18T10:00:00Z',
}

const yielded: AgentYieldContract = {
  outcome: 'needs_input',
  activation_id: activation.activation_id,
  task_id: activation.task_id,
  task_version: activation.task_version,
  questions: [{
    question_key: 'x_field',
    prompt: 'Which field is X?',
    answer_kind: 'field',
  }],
}

describe('AgentTaskPump', () => {
  it('accepts a fully specified activation with no ordinary tools', async () => {
    const toolFreeActivation = { ...activation, allowed_tools: [] }
    let nextCalls = 0
    const pump = new AgentTaskPump({
      core: {
        request: async (method) => {
          if (method === 'agent.tasks.pump.next') {
            nextCalls += 1
            return nextCalls === 1
              ? { kind: 'run_activation', activation: toolFreeActivation }
              : { kind: 'wait', reason: 'awaiting_input', task_state: 'awaiting_input' }
          }
          return { state: 'investigating' }
        },
      },
      runtime: { run: async () => yielded, abort: () => true },
      emit: () => undefined,
    })

    await expect(pump.drain('project:test', 'task:test')).resolves.toMatchObject({
      reason: 'awaiting_input',
      activationsRun: 1,
    })
  })

  it('runs only the Core-requested activation and stops at confirmation', async () => {
    const methods: string[] = []
    let nextCalls = 0
    const core: DurableTaskCoreBridge = {
      request: async (method, params) => {
        methods.push(method)
        if (method === 'agent.tasks.pump.next') {
          nextCalls += 1
          return nextCalls === 1
            ? { kind: 'run_activation', activation }
            : { kind: 'wait', reason: 'awaiting_confirmation', task_state: 'awaiting_confirmation' }
        }
        if (method === 'agent.tasks.activation.running') {
          expect(params).toEqual({
            project_id: 'project:test',
            activation_id: activation.activation_id,
          })
          return { state: 'investigating' }
        }
        if (method === 'agent.tasks.yield.accept') {
          expect(params).toEqual({ project_id: 'project:test', yield: yielded })
          return { state: 'awaiting_confirmation' }
        }
        throw new Error(`unexpected method ${method}`)
      },
    }
    const runtime = { run: vi.fn(async () => yielded), abort: vi.fn(() => true) }
    const events: string[] = []
    const pump = new AgentTaskPump({
      core,
      runtime,
      emit: (event) => events.push(event.stage),
    })

    await expect(pump.drain('project:test', 'task:test')).resolves.toEqual({
      projectId: 'project:test',
      taskId: 'task:test',
      reason: 'awaiting_confirmation',
      taskState: 'awaiting_confirmation',
      activationsRun: 1,
    })
    expect(runtime.run).toHaveBeenCalledWith(activation)
    expect(methods).toEqual([
      'agent.tasks.pump.next',
      'agent.tasks.activation.running',
      'agent.tasks.yield.accept',
      'agent.tasks.pump.next',
    ])
    expect(events).toEqual([
      'checking_next_action',
      'activation_started',
      'activation_yielded',
      'checking_next_action',
      'waiting',
    ])
  })

  it('rejects a stale runtime yield before sending it to Core', async () => {
    const methods: string[] = []
    const core: DurableTaskCoreBridge = {
      request: async (method) => {
        methods.push(method)
        if (method === 'agent.tasks.pump.next') return { kind: 'run_activation', activation }
        return { state: 'investigating' }
      },
    }
    const runtime = {
      run: async () => ({ ...yielded, activation_id: 'activation:late' }),
      abort: () => true,
    }
    const pump = new AgentTaskPump({ core, runtime, emit: () => undefined })

    await expect(pump.drain('project:test', 'task:test')).rejects.toMatchObject({
      code: 'TASK_PUMP_YIELD_IDENTITY_MISMATCH',
    })
    expect(methods).not.toContain('agent.tasks.yield.accept')
  })

  it('returns the typed terminal yield that caused a non-confirmation wait', async () => {
    let nextCalls = 0
    const failure: AgentYieldContract = {
      outcome: 'runtime_failed',
      activation_id: activation.activation_id,
      task_id: activation.task_id,
      task_version: activation.task_version,
      error: {
        code: 'PI_V2_PROVIDER_FAILED',
        category: 'runtime',
        message: 'fetch failed',
        retryable: true,
        requires_user: false,
        side_effect_state: 'known_none',
      },
    }
    const pump = new AgentTaskPump({
      core: {
        request: async (method) => {
          if (method === 'agent.tasks.pump.next') {
            nextCalls += 1
            return nextCalls === 1
              ? { kind: 'run_activation', activation }
              : { kind: 'wait', reason: 'terminal', task_state: 'failed' }
          }
          return { state: 'failed' }
        },
      },
      runtime: { run: async () => failure, abort: () => true },
      emit: () => undefined,
    })

    await expect(pump.drain('project:test', 'task:test')).resolves.toMatchObject({
      reason: 'terminal',
      taskState: 'failed',
      terminalYield: failure,
    })
  })

  it('cancels the active activation without asking Main to transition task state', async () => {
    let release: (() => void) | undefined
    let started: (() => void) | undefined
    const runtimeStarted = new Promise<void>((resolve) => { started = resolve })
    const core: DurableTaskCoreBridge = {
      request: async (method) => {
        if (method === 'agent.tasks.pump.next') return { kind: 'run_activation', activation }
        return { state: 'investigating' }
      },
    }
    const runtime = {
      run: async () => {
        started?.()
        await new Promise<void>((resolve) => { release = resolve })
        return yielded
      },
      abort: vi.fn(() => true),
    }
    const pump = new AgentTaskPump({ core, runtime, emit: () => undefined })

    const pending = pump.drain('project:test', 'task:test')
    await runtimeStarted
    expect(pump.cancel('project:test', 'task:test')).toBe(true)
    release?.()
    await expect(pending).resolves.toMatchObject({
      reason: 'terminal',
      taskState: 'cancelled',
    })
    expect(runtime.abort).toHaveBeenCalledWith(activation.activation_id)
  })

  it('fails closed on unknown Core directives and immediate activation loops', async () => {
    const invalid = new AgentTaskPump({
      core: { request: async () => ({ kind: 'execute_anything' }) },
      runtime: { run: async () => yielded, abort: () => true },
      emit: () => undefined,
    })
    await expect(invalid.drain('project:test', 'task:test')).rejects.toMatchObject({
      code: 'TASK_PUMP_PROTOCOL_INVALID',
    })

    const looping = new AgentTaskPump({
      core: { request: async () => ({ kind: 'run_activation', activation }) },
      runtime: { run: async () => yielded, abort: () => true },
      emit: () => undefined,
      maxImmediateActivations: 1,
    })
    await expect(looping.drain('project:test', 'task:test')).rejects.toMatchObject({
      code: 'TASK_PUMP_IMMEDIATE_LIMIT',
    })
  })
})
