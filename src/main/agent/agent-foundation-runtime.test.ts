import { describe, expect, it } from 'vitest'

import type { AgentActivation, AgentYieldContract } from '../../shared/generated/contracts.js'
import {
  AgentFoundationRuntime,
  AgentFoundationRuntimeError,
  publicAgentFoundationError,
  type AgentFoundationRuntimeEvent,
} from './agent-foundation-runtime.js'

class FakeCore {
  readonly calls: { method: string; params: unknown }[] = []
  private pumpCalls = 0
  private state = 'awaiting_confirmation'
  private taskVersion = 2

  async request(method: string, params?: unknown): Promise<unknown> {
    this.calls.push({ method, params })
    if (method === 'datasets.describe') {
      return {
        source_dataset_id: 'source:test',
        source_version: 1,
        content_hash: 'a'.repeat(64),
      }
    }
    if (method === 'engine.plots.get') {
      return {
        document: {
          plot_id: 'plot:existing',
          plot_version: 3,
          profile_id: 'K01',
        },
      }
    }
    if (method === 'agent.tasks.create') return { state: 'created' }
    if (method === 'agent.tasks.list') {
      return {
        tasks: [{ task_id: 'task:fixed', state: 'awaiting_confirmation', intent: { intent_id: 'intent:fixed' } }],
      }
    }
    if (method === 'agent.tasks.pump.next') {
      this.pumpCalls += 1
      if (this.pumpCalls === 1) {
        return {
          kind: 'run_activation',
          activation: {
            activation_id: 'activation:test',
            task_id: 'task:fixed',
            task_version: 1,
            task_state: 'created',
            permission_phase: 'p0_read',
            allowed_tools: ['inspect_source'],
          },
        }
      }
      return { kind: 'wait', reason: 'awaiting_confirmation', task_state: this.state }
    }
    if (method === 'agent.tasks.activation.running') return { state: 'created' }
    if (method === 'agent.tasks.yield.accept') return { state: 'intent_staged' }
    if (method === 'agent.tasks.plan.get') return this.view()
    if (method === 'agent.tasks.get') return this.viewTask()
    if (method === 'agent.tasks.cancel') {
      this.state = 'cancelled'
      this.taskVersion += 2
      return { state: this.state }
    }
    if (method === 'agent.tasks.plan.confirm') {
      this.state = 'executing'
      this.taskVersion += 1
      return { state: this.state }
    }
    if (method === 'agent.tasks.plan.reject') {
      this.state = 'rejected'
      this.taskVersion += 1
      return { state: this.state }
    }
    if (method === 'agent.tasks.execute') {
      this.state = 'completed_verified'
      this.taskVersion += 5
      return { task: { state: this.state } }
    }
    throw new Error(`Unexpected method ${method}`)
  }

  private view(): unknown {
    return {
      task: this.viewTask(),
      plan: {
        plan_id: 'plan:fixed',
        items: [{
          item_id: 'item:fixed.1',
          task_kind: 'create',
          profile_id: 'K01',
          sources: [{ source_alias: 'data_1', source_dataset_id: 'source:test' }],
          bindings: [],
          visual_actions: [],
        }],
      },
      plan_hash: 'b'.repeat(64),
      confirmation_state: this.state === 'awaiting_confirmation' ? 'pending' : 'confirmed',
    }
  }

  private viewTask(): unknown {
    return {
      task_id: 'task:fixed',
      task_version: this.taskVersion,
      state: this.state,
      items: [{
        item_id: 'item:fixed.1',
        state: this.state === 'completed_verified' ? 'succeeded' : 'staged',
        attempt_count: this.state === 'completed_verified' ? 1 : 0,
        ...(this.state === 'completed_verified'
          ? { output_plot_id: 'plot:fixed.1', output_plot_version: 1 }
          : {}),
      }],
    }
  }
}

describe('AgentFoundationRuntime', () => {
  it('marks recoverable provider failures as retryable without exposing an internal error type', () => {
    expect(publicAgentFoundationError(new AgentFoundationRuntimeError(
      'AGENT_V2_PROVIDER_BALANCE',
      '模型服务余额不足。',
    ))).toEqual({
      code: 'IPC_INVALID_ARGUMENT',
      message: '模型服务余额不足。',
      retryable: true,
    })
  })

  it('does not present an exhausted task budget as retryable in place', () => {
    expect(publicAgentFoundationError(new AgentFoundationRuntimeError(
      'AGENT_V2_BUDGET_EXHAUSTED',
      '任务预算已耗尽；请修改要求后创建新任务。',
    ))).toEqual({
      code: 'IPC_INVALID_ARGUMENT',
      message: '任务预算已耗尽；请修改要求后创建新任务。',
      retryable: false,
    })
  })

  it('returns a verified read-only answer without requiring a confirmation plan', async () => {
    let nextCalls = 0
    const calls: { method: string; params: unknown }[] = []
    const events: AgentFoundationRuntimeEvent[] = []
    const core = {
      request: async (method: string, params?: unknown): Promise<unknown> => {
        calls.push({ method, params })
        if (method === 'datasets.describe') return {
          source_dataset_id: 'source:test', source_version: 1, content_hash: 'a'.repeat(64),
        }
        if (method === 'agent.tasks.create') return { state: 'created' }
        if (method === 'agent.tasks.pump.next') {
          nextCalls += 1
          return nextCalls === 1
            ? {
                kind: 'run_activation',
                activation: {
                  activation_id: 'activation:inspection',
                  task_id: 'task:fixed',
                  task_version: 1,
                  task_state: 'created',
                  permission_phase: 'p0_read',
                  allowed_tools: ['inspect_source'],
                },
              }
            : { kind: 'wait', reason: 'terminal', task_state: 'completed_verified' }
        }
        if (method === 'agent.tasks.activation.running') return {}
        if (method === 'agent.tasks.yield.accept') return { state: 'completed_verified' }
        throw new Error(`Unexpected method ${method}`)
      },
    }
    const runtime = new AgentFoundationRuntime({
      core,
      emit: (event) => events.push(event),
      id: () => 'fixed',
      createRuntime: () => ({
        abort: () => false,
        run: async (activation: AgentActivation): Promise<AgentYieldContract> => ({
          outcome: 'information_ready',
          activation_id: activation.activation_id,
          task_id: activation.task_id,
          task_version: activation.task_version,
          message: '共有 4 列，其中 1 个值缺失。',
        }),
      }),
    })

    await expect(runtime.run({
      projectId: 'project:test',
      selectedSources: [{ datasetId: 'source:test', sourceVersion: 1 }],
      selectedProfileIds: [],
      expectedProjectVersion: 0,
      instruction: '只读检查列类型和缺失值。',
    })).resolves.toEqual({
      outcome: 'information_ready',
      workflow_run_id: 'task:fixed',
      message: '共有 4 列，其中 1 个值缺失。',
    })
    expect(calls.some((call) => call.method === 'agent.tasks.plan.get')).toBe(false)
    expect(events).toContainEqual(expect.objectContaining({
      stage: 'completed', label: '只读检查已完成',
    }))
  })

  it('returns a typed question and continues the same durable task after the reply', async () => {
    let phase: 'initial' | 'waiting' | 'continued' = 'initial'
    let nextCalls = 0
    const calls: { method: string; params: unknown }[] = []
    const core = {
      request: async (method: string, params?: unknown): Promise<unknown> => {
        calls.push({ method, params })
        if (method === 'datasets.describe') return {
          source_dataset_id: 'source:test', source_version: 1, content_hash: 'a'.repeat(64),
        }
        if (method === 'agent.tasks.create') return { state: 'created' }
        if (method === 'agent.tasks.get') return {
          task_id: 'task:fixed', task_version: 2, state: 'awaiting_input', items: [],
        }
        if (method === 'agent.tasks.user_event') {
          phase = 'continued'
          nextCalls = 0
          return { state: 'investigating' }
        }
        if (method === 'agent.tasks.pump.next') {
          nextCalls += 1
          if (nextCalls === 1) return {
            kind: 'run_activation',
            activation: {
              activation_id: phase === 'continued' ? 'activation:answer' : 'activation:question',
              task_id: 'task:fixed',
              task_version: phase === 'continued' ? 3 : 1,
              task_state: phase === 'continued' ? 'investigating' : 'created',
              permission_phase: 'p0_read',
              allowed_tools: ['inspect_source'],
            },
          }
          if (phase === 'continued') return {
            kind: 'wait', reason: 'awaiting_confirmation', task_state: 'awaiting_confirmation',
          }
          phase = 'waiting'
          return { kind: 'wait', reason: 'awaiting_input', task_state: 'awaiting_input' }
        }
        if (method === 'agent.tasks.activation.running') return {}
        if (method === 'agent.tasks.yield.accept') return {}
        if (method === 'agent.tasks.plan.get') return {
          task: { task_id: 'task:fixed', task_version: 5, state: 'awaiting_confirmation', items: [] },
          plan: { plan_id: 'plan:fixed', items: [] },
          plan_hash: 'b'.repeat(64),
          confirmation_state: 'pending',
        }
        throw new Error(`Unexpected method ${method}`)
      },
    }
    const runtime = new AgentFoundationRuntime({
      core,
      emit: () => undefined,
      id: () => 'fixed',
      createRuntime: () => ({
        abort: () => false,
        run: async (activation: AgentActivation): Promise<AgentYieldContract> => (
          activation.activation_id === 'activation:question'
            ? {
                outcome: 'needs_input',
                activation_id: activation.activation_id,
                task_id: activation.task_id,
                task_version: activation.task_version,
                questions: [{
                  question_key: 'x_field',
                  prompt: '哪一列作为 X？',
                  answer_kind: 'field',
                  required: true,
                }],
              }
            : {
                outcome: 'cancelled',
                activation_id: activation.activation_id,
                task_id: activation.task_id,
                task_version: activation.task_version,
                message: 'Synthetic terminal yield.',
              }
        ),
      }),
    })

    const question = await runtime.run({
      projectId: 'project:test',
      selectedSources: [{ datasetId: 'source:test', sourceVersion: 1 }],
      selectedProfileIds: ['K01'],
      expectedProjectVersion: 0,
      instruction: '画折线图。',
    })
    expect(question).toMatchObject({
      outcome: 'needs_input', workflow_run_id: 'task:fixed',
    })
    const continued = await runtime.run({
      projectId: 'project:test',
      selectedSources: [],
      expectedProjectVersion: 0,
      continuationWorkflowRunId: 'task:fixed',
      instruction: '第一列。',
    })
    expect(continued).toMatchObject({ plan: { plan_id: 'plan:fixed' } })
    expect(calls.find((call) => call.method === 'agent.tasks.user_event')).toMatchObject({
      params: { task_id: 'task:fixed', action: 'answered', message: '第一列。' },
    })
  })

  it('returns a revised confirmation plan after a repair clarification', async () => {
    let nextCalls = 0
    const events: AgentFoundationRuntimeEvent[] = []
    const core = {
      request: async (method: string): Promise<unknown> => {
        if (method === 'agent.tasks.get') return {
          task_id: 'task:repair', task_version: 8, state: 'awaiting_input', items: [
            { item_id: 'item:repair.1', state: 'succeeded', attempt_count: 1 },
            { item_id: 'item:repair.2', state: 'repairable_failed', attempt_count: 1 },
          ],
        }
        if (method === 'agent.tasks.user_event') return { state: 'investigating' }
        if (method === 'agent.tasks.pump.next') {
          nextCalls += 1
          return nextCalls === 1
            ? {
                kind: 'run_activation',
                activation: {
                  activation_id: 'activation:repair-answer',
                  task_id: 'task:repair',
                  task_version: 9,
                  task_state: 'investigating',
                  permission_phase: 'p0_read',
                  allowed_tools: ['inspect_source'],
                },
              }
            : {
                kind: 'wait',
                reason: 'awaiting_reconfirmation',
                task_state: 'awaiting_reconfirmation',
              }
        }
        if (method === 'agent.tasks.activation.running') return {}
        if (method === 'agent.tasks.yield.accept') return { state: 'intent_staged' }
        if (method === 'agent.tasks.plan.get') return {
          task: {
            task_id: 'task:repair', task_version: 11, state: 'awaiting_reconfirmation', items: [],
          },
          plan: { plan_id: 'plan:repair.v2', items: [] },
          plan_hash: 'b'.repeat(64),
          confirmation_state: 'pending',
        }
        throw new Error(`Unexpected method ${method}`)
      },
    }
    const runtime = new AgentFoundationRuntime({
      core,
      emit: (event) => events.push(event),
      id: () => 'fixed',
      createRuntime: () => ({
        abort: () => false,
        run: async (activation: AgentActivation): Promise<AgentYieldContract> => ({
          outcome: 'cancelled',
          activation_id: activation.activation_id,
          task_id: activation.task_id,
          task_version: activation.task_version,
          message: 'Synthetic revised intent accepted by the fake Core.',
        }),
      }),
    })

    await expect(runtime.run({
      projectId: 'project:test',
      selectedSources: [],
      expectedProjectVersion: 1,
      continuationWorkflowRunId: 'task:repair',
      instruction: '只修改失败项。',
    })).resolves.toMatchObject({
      task: { state: 'awaiting_reconfirmation' },
      plan: { plan_id: 'plan:repair.v2' },
      confirmation_state: 'pending',
    })
    expect(events).toContainEqual(expect.objectContaining({
      stage: 'completed', label: '修订计划已生成，等待重新确认',
    }))
  })

  it('continues a partial task as a correction instead of creating a replacement task', async () => {
    let nextCalls = 0
    const calls: { method: string; params: unknown }[] = []
    const core = {
      request: async (method: string, params?: unknown): Promise<unknown> => {
        calls.push({ method, params })
        if (method === 'agent.tasks.get') return {
          task_id: 'task:partial-correction', task_version: 8, state: 'partial', items: [
            { item_id: 'item:partial-correction.1', state: 'succeeded', attempt_count: 1 },
            { item_id: 'item:partial-correction.2', state: 'repairable_failed', attempt_count: 1 },
          ],
        }
        if (method === 'agent.tasks.user_event') return { state: 'investigating' }
        if (method === 'agent.tasks.pump.next') {
          nextCalls += 1
          return nextCalls === 1
            ? {
                kind: 'run_activation',
                activation: {
                  activation_id: 'activation:partial-correction',
                  task_id: 'task:partial-correction',
                  task_version: 9,
                  task_state: 'investigating',
                  permission_phase: 'p0_read',
                  allowed_tools: ['inspect_source'],
                },
              }
            : {
                kind: 'wait',
                reason: 'awaiting_reconfirmation',
                task_state: 'awaiting_reconfirmation',
              }
        }
        if (method === 'agent.tasks.activation.running') return {}
        if (method === 'agent.tasks.yield.accept') return { state: 'intent_staged' }
        if (method === 'agent.tasks.plan.get') return {
          task: {
            task_id: 'task:partial-correction',
            task_version: 11,
            state: 'awaiting_reconfirmation',
            items: [],
          },
          plan: { plan_id: 'plan:partial-correction.v2', items: [] },
          plan_hash: 'b'.repeat(64),
          confirmation_state: 'pending',
        }
        throw new Error(`Unexpected method ${method}`)
      },
    }
    const runtime = new AgentFoundationRuntime({
      core,
      emit: () => undefined,
      id: () => 'partial-correction',
      createRuntime: () => ({
        abort: () => false,
        run: async (activation: AgentActivation): Promise<AgentYieldContract> => ({
          outcome: 'cancelled',
          activation_id: activation.activation_id,
          task_id: activation.task_id,
          task_version: activation.task_version,
          message: 'Synthetic revised intent accepted by the fake Core.',
        }),
      }),
    })

    await expect(runtime.run({
      projectId: 'project:test',
      selectedSources: [],
      expectedProjectVersion: 1,
      continuationWorkflowRunId: 'task:partial-correction',
      instruction: '第二项改用另一列，然后再执行。',
    })).resolves.toMatchObject({
      task: { state: 'awaiting_reconfirmation' },
      plan: { plan_id: 'plan:partial-correction.v2' },
    })
    expect(calls.filter((call) => call.method === 'agent.tasks.create')).toHaveLength(0)
    expect(calls.find((call) => call.method === 'agent.tasks.user_event')).toMatchObject({
      params: {
        task_id: 'task:partial-correction',
        action: 'corrected',
        message: '第二项改用另一列，然后再执行。',
      },
    })
  })

  it('resumes an interrupted planning checkpoint without creating a replacement task', async () => {
    let nextCalls = 0
    const calls: { method: string; params: unknown }[] = []
    const core = {
      request: async (method: string, params?: unknown): Promise<unknown> => {
        calls.push({ method, params })
        if (method === 'agent.tasks.list') return { tasks: [{
          task_id: 'task:restart-planning',
          task_version: 4,
          state: 'investigating',
          intent: null,
          items: [],
        }] }
        if (method === 'agent.tasks.get') return {
          task_id: 'task:restart-planning',
          task_version: 4,
          state: 'investigating',
          items: [],
        }
        if (method === 'agent.tasks.pump.next') {
          nextCalls += 1
          return nextCalls === 1
            ? {
                kind: 'run_activation',
                activation: {
                  activation_id: 'activation:restart-planning',
                  task_id: 'task:restart-planning',
                  task_version: 4,
                  task_state: 'investigating',
                  permission_phase: 'p0_read',
                  allowed_tools: ['inspect_source'],
                },
              }
            : {
                kind: 'wait',
                reason: 'awaiting_confirmation',
                task_state: 'awaiting_confirmation',
              }
        }
        if (method === 'agent.tasks.activation.running') return {}
        if (method === 'agent.tasks.yield.accept') return { state: 'intent_staged' }
        if (method === 'agent.tasks.plan.get') return {
          task: {
            task_id: 'task:restart-planning',
            task_version: 6,
            state: 'awaiting_confirmation',
            items: [],
          },
          plan: { plan_id: 'plan:restart-planning.v1', items: [] },
          plan_hash: 'c'.repeat(64),
          confirmation_state: 'pending',
        }
        throw new Error(`Unexpected method ${method}`)
      },
    }
    const runtime = new AgentFoundationRuntime({
      core,
      emit: () => undefined,
      id: () => 'restart-planning',
      createRuntime: () => ({
        abort: () => false,
        run: async (activation: AgentActivation): Promise<AgentYieldContract> => ({
          outcome: 'cancelled',
          activation_id: activation.activation_id,
          task_id: activation.task_id,
          task_version: activation.task_version,
          message: 'Synthetic recovered intent accepted by the fake Core.',
        }),
      }),
    })
    await runtime.list('project:test')

    await expect(runtime.resumeTask('task:restart-planning')).resolves.toMatchObject({
      task: { state: 'awaiting_confirmation' },
      plan: { plan_id: 'plan:restart-planning.v1' },
    })
    expect(calls.filter((call) => call.method === 'agent.tasks.create')).toHaveLength(0)
    expect(calls.filter((call) => call.method === 'agent.tasks.user_event')).toHaveLength(0)
  })

  it('rejects duplicate continuation while the durable activation is still running', async () => {
    const core = {
      request: async (method: string): Promise<unknown> => {
        if (method === 'agent.tasks.list') return { tasks: [{
          task_id: 'task:active-planning',
          task_version: 4,
          state: 'investigating',
          active_activation_id: 'activation:active-planning',
          intent: null,
          items: [],
        }] }
        if (method === 'agent.tasks.get') return {
          task_id: 'task:active-planning',
          task_version: 4,
          state: 'investigating',
          active_activation_id: 'activation:active-planning',
          items: [],
        }
        throw new Error(`Unexpected method ${method}`)
      },
    }
    const runtime = new AgentFoundationRuntime({ core, emit: () => undefined })
    await runtime.list('project:test')

    await expect(runtime.resumeTask('task:active-planning')).rejects.toMatchObject({
      code: 'AGENT_V2_TASK_ALREADY_RUNNING',
      message: '这项任务正在运行，无需再次继续。',
    })
  })

  it('resumes a blocked task only through the typed external-condition event', async () => {
    let nextCalls = 0
    const calls: { method: string; params: unknown }[] = []
    const core = {
      request: async (method: string, params?: unknown): Promise<unknown> => {
        calls.push({ method, params })
        if (method === 'agent.tasks.list') return { tasks: [{
          task_id: 'task:blocked', task_version: 3, state: 'blocked', intent: null, items: [],
        }] }
        if (method === 'agent.tasks.get') return {
          task_id: 'task:blocked', task_version: 3, state: 'blocked', items: [],
        }
        if (method === 'agent.tasks.user_event') return {
          task_id: 'task:blocked', task_version: 4, state: 'investigating', items: [],
        }
        if (method === 'agent.tasks.pump.next') {
          nextCalls += 1
          return nextCalls === 1
            ? {
                kind: 'run_activation',
                activation: {
                  activation_id: 'activation:blocked',
                  task_id: 'task:blocked',
                  task_version: 4,
                  task_state: 'investigating',
                  permission_phase: 'p0_read',
                  allowed_tools: ['inspect_source'],
                },
              }
            : { kind: 'wait', reason: 'awaiting_input', task_state: 'awaiting_input' }
        }
        if (method === 'agent.tasks.activation.running') return {}
        if (method === 'agent.tasks.yield.accept') return { state: 'awaiting_input' }
        throw new Error(`Unexpected method ${method}`)
      },
    }
    const runtime = new AgentFoundationRuntime({
      core,
      emit: () => undefined,
      id: () => 'blocked',
      createRuntime: () => ({
        abort: () => false,
        run: async (activation: AgentActivation): Promise<AgentYieldContract> => ({
          outcome: 'needs_input',
          activation_id: activation.activation_id,
          task_id: activation.task_id,
          task_version: activation.task_version,
          questions: [{
            question_key: 'external_condition',
            prompt: '外部条件已经恢复，是否继续？',
            answer_kind: 'single_choice',
            required: true,
            choices: ['继续', '暂不继续'],
          }],
        }),
      }),
    })
    await runtime.list('project:test')

    await expect(runtime.resumeTask('task:blocked')).resolves.toMatchObject({
      outcome: 'needs_input',
      workflow_run_id: 'task:blocked',
    })
    expect(calls.find((call) => call.method === 'agent.tasks.user_event')).toMatchObject({
      params: { task_id: 'task:blocked', expected_task_version: 3, action: 'resumed' },
    })
  })

  it('runs one selected source to confirmation and executes only after approval', async () => {
    const core = new FakeCore()
    const events: AgentFoundationRuntimeEvent[] = []
    const runtime = new AgentFoundationRuntime({
      core,
      emit: (event) => events.push(event),
      id: () => 'fixed',
      clock: () => new Date('2026-08-18T10:00:00Z'),
      createRuntime: () => ({
        abort: () => false,
        run: async (activation: AgentActivation): Promise<AgentYieldContract> => ({
          outcome: 'cancelled',
          activation_id: activation.activation_id,
          task_id: activation.task_id,
          task_version: activation.task_version,
          message: 'Fake typed yield.',
        }),
      }),
    })

    const created = await runtime.run({
      projectId: 'project:test',
      selectedSources: [{ datasetId: 'source:test', sourceVersion: 1 }],
      selectedProfileIds: ['K01'],
      expectedProjectVersion: 4,
      instruction: '绘制折线图。',
    })
    expect(created).toMatchObject({
      task: { state: 'awaiting_confirmation' },
      plan: { plan_id: 'plan:fixed' },
    })
    expect(core.calls.find((call) => call.method === 'agent.tasks.create')).toMatchObject({
      params: {
        envelope: {
          budget: { max_estimated_cost: 10 },
        },
      },
    })
    expect(core.calls.some((call) => call.method === 'agent.tasks.execute')).toBe(false)

    const confirmed = await runtime.confirm({ projectId: 'project:test', planId: 'plan:fixed' })
    expect(confirmed).toMatchObject({ task: { state: 'executing' } })
    const completed = await runtime.execute({ projectId: 'project:test', planId: 'plan:fixed' })
    expect(completed).toMatchObject({
      task: { state: 'completed_verified' },
      plan: { plan_id: 'plan:fixed' },
    })
    expect(events).toContainEqual(expect.objectContaining({ stage: 'completed', label: '计划已生成，等待确认' }))
    expect(events).toContainEqual(expect.objectContaining({ taskId: 'task:fixed', stage: 'planning' }))
    expect(events.at(-1)).toMatchObject({ stage: 'completed', label: '任务结果已验证' })
  })

  it('returns to the Core control channel between atomic batch items', async () => {
    let state = 'executing'
    let executionCalls = 0
    const calls: { method: string; params: unknown }[] = []
    const core = {
      request: async (method: string, params?: unknown): Promise<unknown> => {
        calls.push({ method, params })
        if (method === 'agent.tasks.list') {
          return { tasks: [{ task_id: 'task:stepped', state, intent: { intent_id: 'intent:stepped' } }] }
        }
        if (method === 'agent.tasks.plan.get') {
          return {
            task: { task_id: 'task:stepped', task_version: 4 + executionCalls, state, items: [] },
            plan: { plan_id: 'plan:stepped', items: [] },
            plan_hash: 'a'.repeat(64),
            confirmation_state: 'confirmed',
          }
        }
        if (method === 'agent.tasks.execute') {
          executionCalls += 1
          state = executionCalls === 1 ? 'executing' : 'completed_verified'
          return { task: { task_id: 'task:stepped', task_version: 4 + executionCalls, state } }
        }
        throw new Error(`Unexpected method ${method}`)
      },
    }
    const runtime = new AgentFoundationRuntime({ core, emit: () => undefined })
    await runtime.list('project:test')

    await expect(runtime.execute({ projectId: 'project:test', planId: 'plan:stepped' }))
      .resolves.toMatchObject({ task: { state: 'completed_verified' } })

    const executions = calls.filter((call) => call.method === 'agent.tasks.execute')
    expect(executions).toHaveLength(2)
    expect(executions.every((call) => (
      call.params as Record<string, unknown>
    ).step === true)).toBe(true)
  })

  it('does not enqueue the next atomic item after the user requests cancellation', async () => {
    let state = 'executing'
    let executionCalls = 0
    let releaseFirstStep: (() => void) | undefined
    let markFirstStepStarted: (() => void) | undefined
    const firstStepStarted = new Promise<void>((resolve) => {
      markFirstStepStarted = resolve
    })
    const firstStepRelease = new Promise<void>((resolve) => {
      releaseFirstStep = resolve
    })
    const cancelControlTimeouts: number[] = []
    const core = {
      request: async (method: string, _params?: unknown, timeoutMs?: number): Promise<unknown> => {
        if (method === 'agent.tasks.list') {
          return { tasks: [{ task_id: 'task:cancel-race', state, intent: { intent_id: 'intent:cancel-race' } }] }
        }
        if (method === 'agent.tasks.plan.get') {
          return {
            task: { task_id: 'task:cancel-race', task_version: 6, state, items: [] },
            plan: { plan_id: 'plan:cancel-race', items: [] },
            plan_hash: 'a'.repeat(64),
            confirmation_state: 'confirmed',
          }
        }
        if (method === 'agent.tasks.get') {
          cancelControlTimeouts.push(timeoutMs ?? 0)
          return { task_id: 'task:cancel-race', task_version: 6, state, items: [] }
        }
        if (method === 'agent.tasks.execute') {
          executionCalls += 1
          markFirstStepStarted?.()
          await firstStepRelease
          return { task: { task_id: 'task:cancel-race', task_version: 6, state: 'executing' } }
        }
        if (method === 'agent.tasks.cancel') {
          state = 'cancelled'
          return { task_id: 'task:cancel-race', task_version: 8, state }
        }
        throw new Error(`Unexpected method ${method}`)
      },
    }
    const events: AgentFoundationRuntimeEvent[] = []
    const runtime = new AgentFoundationRuntime({ core, emit: (event) => events.push(event) })
    await runtime.list('project:test')

    const execution = runtime.execute({ projectId: 'project:test', planId: 'plan:cancel-race' })
    await firstStepStarted
    await runtime.cancel('task:cancel-race')
    releaseFirstStep?.()

    await expect(execution).resolves.toMatchObject({ task: { state: 'cancelled' } })
    expect(executionCalls).toBe(1)
    expect(cancelControlTimeouts).toContain(900_000)
    expect(events.at(-1)).toMatchObject({ stage: 'cancelled' })
  })

  it('reports a terminal execution failure as failed instead of verified completion', async () => {
    let state = 'executing'
    const events: AgentFoundationRuntimeEvent[] = []
    const core = {
      request: async (method: string): Promise<unknown> => {
        if (method === 'agent.tasks.list') {
          return { tasks: [{ task_id: 'task:terminal-failure', state, intent: { intent_id: 'intent:terminal-failure' } }] }
        }
        if (method === 'agent.tasks.plan.get') {
          return {
            task: { task_id: 'task:terminal-failure', task_version: 5, state, items: [] },
            plan: { plan_id: 'plan:terminal-failure', items: [] },
            plan_hash: 'a'.repeat(64),
            confirmation_state: 'confirmed',
          }
        }
        if (method === 'agent.tasks.execute') {
          state = 'failed'
          return { task: { task_id: 'task:terminal-failure', task_version: 5, state } }
        }
        throw new Error(`Unexpected method ${method}`)
      },
    }
    const runtime = new AgentFoundationRuntime({ core, emit: (event) => events.push(event) })
    await runtime.list('project:test')

    await expect(runtime.execute({ projectId: 'project:test', planId: 'plan:terminal-failure' }))
      .resolves.toMatchObject({ task: { state: 'failed' } })
    expect(events.at(-1)).toMatchObject({ stage: 'failed', label: '任务执行失败，请查看失败项诊断' })
  })

  it.each([
    { terminalState: 'failed', expectedStage: 'failed' },
    { terminalState: 'cancelled', expectedStage: 'cancelled' },
  ] as const)(
    'projects $terminalState when a partial-repair pump stops terminally',
    async ({ terminalState, expectedStage }) => {
      let state = 'partial'
      const events: AgentFoundationRuntimeEvent[] = []
      const core = {
        request: async (method: string): Promise<unknown> => {
          if (method === 'agent.tasks.list') {
            return {
              tasks: [{
                task_id: 'task:repair-terminal',
                state,
                intent: { intent_id: 'intent:repair-terminal' },
              }],
            }
          }
          if (method === 'agent.tasks.plan.get') {
            return {
              task: {
                task_id: 'task:repair-terminal',
                task_version: 8,
                state,
                items: [{
                  item_id: 'item:repair-terminal.1',
                  state: 'repairable_failed',
                  attempt_count: 1,
                }],
              },
              plan: { plan_id: 'plan:repair-terminal', items: [] },
              plan_hash: 'a'.repeat(64),
              confirmation_state: 'confirmed',
            }
          }
          if (method === 'agent.tasks.pump.next') {
            state = terminalState
            return { kind: 'wait', reason: 'terminal', task_state: terminalState }
          }
          throw new Error(`Unexpected method ${method}`)
        },
      }
      const runtime = new AgentFoundationRuntime({ core, emit: (event) => events.push(event) })
      await runtime.list('project:test')

      await expect(runtime.execute({
        projectId: 'project:test',
        planId: 'plan:repair-terminal',
      })).resolves.toMatchObject({ task: { state: terminalState } })
      expect(events.at(-1)).toMatchObject({ stage: expectedStage })
      expect(events.at(-1)?.label).not.toBe('任务结果已验证')
    },
  )

  it('recovers durable plan authority after a desktop restart', async () => {
    const core = new FakeCore()
    const runtime = new AgentFoundationRuntime({
      core,
      emit: () => undefined,
    })

    await expect(runtime.list('project:test')).resolves.toMatchObject({
      task_plans: [{
        task: { task_id: 'task:fixed', state: 'awaiting_confirmation' },
        plan: { plan_id: 'plan:fixed' },
      }],
    })
    expect(runtime.ownsPlan('plan:fixed')).toBe(true)
    expect(runtime.ownsTask('task:fixed')).toBe(true)
    await expect(runtime.confirm({ projectId: 'project:test', planId: 'plan:fixed' }))
      .resolves.toMatchObject({ task: { state: 'executing' } })
  })

  it.each(['intent_staged', 'investigating', 'awaiting_input', 'repairing', 'blocked'])(
    'restores a %s checkpoint without reading a missing or stale confirmation plan',
    async (state) => {
      const calls: string[] = []
      const core = {
        request: async (method: string): Promise<unknown> => {
          calls.push(method)
          if (method === 'agent.tasks.list') return {
            tasks: [{
              task_id: `task:${state}`,
              task_version: 4,
              state,
              intent: { intent_id: `intent:${state}` },
              items: [],
            }],
          }
          if (method === 'agent.tasks.latest_yield' && state === 'awaiting_input') return {
            outcome: 'needs_input',
            questions: [{ question_key: 'field_y', prompt: '请选择 Y。' }],
          }
          throw new Error(`A non-present current plan must not be read: ${method}`)
        },
      }
      const runtime = new AgentFoundationRuntime({ core, emit: () => undefined })

      await expect(runtime.list('project:test')).resolves.toMatchObject({
        task_plans: [],
        durable_tasks: [{ task_id: `task:${state}`, state }],
      })
      expect(runtime.ownsTask(`task:${state}`)).toBe(true)
      expect(calls).toEqual(state === 'awaiting_input'
        ? ['agent.tasks.list', 'agent.tasks.latest_yield']
        : ['agent.tasks.list'])
    },
  )

  it('cancels a recovered durable task through its Core-owned checkpoint', async () => {
    const core = new FakeCore()
    const runtime = new AgentFoundationRuntime({ core, emit: () => undefined, id: () => 'cancel' })
    await runtime.list('project:test')

    await expect(runtime.cancel('task:fixed')).resolves.toBeUndefined()
    expect(core.calls.find((call) => call.method === 'agent.tasks.cancel')).toMatchObject({
      params: {
        project_id: 'project:test',
        task_id: 'task:fixed',
        expected_task_version: 2,
        user_event_id: 'user-event:cancel',
      },
    })
    await expect(runtime.cancel('task:fixed')).resolves.toBeUndefined()
    expect(core.calls.filter((call) => call.method === 'agent.tasks.cancel')).toHaveLength(1)
  })

  it('accepts a recovered partial result through the typed durable user event', async () => {
    class PartialCore extends FakeCore {
      override async request(method: string, params?: unknown): Promise<unknown> {
        this.calls.push({ method, params })
        if (method === 'agent.tasks.list') {
          return { tasks: [{ task_id: 'task:fixed', state: 'partial', intent: { intent_id: 'intent:fixed' } }] }
        }
        if (method === 'agent.tasks.get') {
          return { task_id: 'task:fixed', task_version: 7, state: 'partial' }
        }
        if (method === 'agent.tasks.user_event') {
          return {
            task_id: 'task:fixed',
            task_version: 8,
            state: 'completed_verified',
            completion: { outcome: 'completed_with_skips' },
          }
        }
        return super.request(method, params)
      }
    }

    const core = new PartialCore()
    const runtime = new AgentFoundationRuntime({ core, emit: () => undefined, id: () => 'skip' })
    await runtime.list('project:test')

    await expect(runtime.acceptPartial('task:fixed')).resolves.toBeUndefined()
    expect(core.calls.find((call) => call.method === 'agent.tasks.user_event')).toMatchObject({
      params: {
        project_id: 'project:test',
        task_id: 'task:fixed',
        expected_task_version: 7,
        action: 'partial_accepted',
        user_event_id: 'user-event:skip',
      },
    })
  })

  it('offers and performs a side-effect-free retry without starting the Agent runtime', async () => {
    class SafeRetryCore extends FakeCore {
      private retryState = 'partial'

      private retryTask(): Record<string, unknown> {
        return {
          task_id: 'task:fixed',
          task_version: this.retryState === 'partial' ? 7 : 8,
          state: this.retryState,
          items: this.retryState === 'partial' ? [{
            item_id: 'item:fixed.1',
            state: 'repairable_failed',
            last_error: {
              category: 'deterministic_technical',
              retryable: true,
              requires_user: false,
              side_effect_state: 'known_none',
            },
          }] : [],
        }
      }

      override async request(method: string, params?: unknown): Promise<unknown> {
        this.calls.push({ method, params })
        if (method === 'agent.tasks.list') {
          return { tasks: [{ task_id: 'task:fixed', state: this.retryState, intent: { intent_id: 'intent:fixed' } }] }
        }
        if (method === 'agent.tasks.plan.get') {
          return {
            task: this.retryTask(),
            plan: { plan_id: 'plan:fixed', items: [] },
            plan_hash: 'a'.repeat(64),
          }
        }
        if (method === 'agent.tasks.retry_safe') {
          this.retryState = 'executing'
          return this.retryTask()
        }
        if (method === 'agent.tasks.execute') {
          this.retryState = 'completed_verified'
          return { task: this.retryTask() }
        }
        return super.request(method, params)
      }
    }

    const core = new SafeRetryCore()
    const runtime = new AgentFoundationRuntime({ core, emit: () => undefined, id: () => 'retry' })
    await runtime.list('project:test')

    await expect(runtime.execute({ projectId: 'project:test', planId: 'plan:fixed' }))
      .resolves.toMatchObject({ task: { state: 'partial' } })
    expect(core.calls.filter((call) => call.method === 'agent.tasks.pump.next')).toHaveLength(0)
    expect(core.calls.filter((call) => call.method === 'agent.tasks.execute')).toHaveLength(0)

    await expect(runtime.resume({ projectId: 'project:test', planId: 'plan:fixed' }))
      .resolves.toMatchObject({ task: { state: 'completed_verified' } })
    expect(core.calls.find((call) => call.method === 'agent.tasks.retry_safe')).toMatchObject({
      params: {
        project_id: 'project:test',
        task_id: 'task:fixed',
        expected_task_version: 7,
      },
    })
    expect(core.calls.filter((call) => call.method === 'agent.tasks.execute')).toHaveLength(1)
  })

  it('returns the refreshed durable checkpoint when a safe retry still fails', async () => {
    let state = 'partial'
    let version = 7
    let attempts = 1
    const task = (): Record<string, unknown> => ({
      task_id: 'task:retry-again',
      task_version: version,
      state,
      items: [{
        item_id: 'item:retry-again.1',
        state: 'repairable_failed',
        attempt_count: attempts,
        last_error: {
          category: 'deterministic_technical',
          retryable: true,
          requires_user: false,
          side_effect_state: 'known_none',
        },
      }],
    })
    const calls: string[] = []
    const core = {
      request: async (method: string): Promise<unknown> => {
        calls.push(method)
        if (method === 'agent.tasks.list') {
          return { tasks: [{ task_id: 'task:retry-again', state, intent: { intent_id: 'intent:retry-again' } }] }
        }
        if (method === 'agent.tasks.plan.get') {
          return { task: task(), plan: { plan_id: 'plan:retry-again', items: [] }, plan_hash: 'a'.repeat(64) }
        }
        if (method === 'agent.tasks.retry_safe') {
          state = 'executing'
          version = 8
          return task()
        }
        if (method === 'agent.tasks.execute') {
          state = 'partial'
          version = 9
          attempts = 2
          return { task: task() }
        }
        throw new Error(`Unexpected method ${method}`)
      },
    }
    const runtime = new AgentFoundationRuntime({ core, emit: () => undefined, id: () => 'retry-again' })
    await runtime.list('project:test')

    await expect(runtime.resume({ projectId: 'project:test', planId: 'plan:retry-again' }))
      .resolves.toMatchObject({
        task: {
          state: 'partial',
          task_version: 9,
          items: [{ attempt_count: 2 }],
        },
      })
    expect(calls).not.toContain('agent.tasks.pump.next')
  })

  it('creates a bounded multi-source and multi-profile durable batch envelope', async () => {
    class MultiSourceCore extends FakeCore {
      override async request(method: string, params?: unknown): Promise<unknown> {
        if (method === 'datasets.describe') {
          const source = params as { source_dataset_id: string; source_version: number }
          return {
            source_dataset_id: source.source_dataset_id,
            source_version: source.source_version,
            content_hash: source.source_dataset_id === 'source:first'
              ? 'a'.repeat(64)
              : 'b'.repeat(64),
          }
        }
        return super.request(method, params)
      }
    }
    const core = new MultiSourceCore()
    const runtime = new AgentFoundationRuntime({
      core,
      emit: () => undefined,
      id: () => 'fixed',
      createRuntime: () => ({
        abort: () => false,
        run: async (activation: AgentActivation): Promise<AgentYieldContract> => ({
          outcome: 'cancelled',
          activation_id: activation.activation_id,
          task_id: activation.task_id,
          task_version: activation.task_version,
          message: 'Fake typed yield.',
        }),
      }),
    })

    expect(runtime.canRun({
      projectId: 'project:test',
      selectedSources: [
        { datasetId: 'source:first', sourceVersion: 1 },
        { datasetId: 'source:second', sourceVersion: 2 },
      ],
      selectedProfileIds: ['K01', 'K02'],
      expectedProjectVersion: 4,
      instruction: '数据一画折线图，数据二画线点图。',
      parentTaskId: 'task:previous',
    })).toBe(true)
    await runtime.run({
      projectId: 'project:test',
      selectedSources: [
        { datasetId: 'source:first', sourceVersion: 1 },
        { datasetId: 'source:second', sourceVersion: 2 },
      ],
      selectedProfileIds: ['K01', 'K02'],
      expectedProjectVersion: 4,
      instruction: '数据一画折线图，数据二画线点图。',
      parentTaskId: 'task:previous',
    })

    expect(core.calls.find((call) => call.method === 'agent.tasks.create')).toMatchObject({
      params: {
        envelope: {
          selected_sources: [
            {
              source_dataset_id: 'source:first',
              source_version: 1,
              content_hash: 'a'.repeat(64),
            },
            {
              source_dataset_id: 'source:second',
              source_version: 2,
              content_hash: 'b'.repeat(64),
            },
          ],
          selected_profile_ids: ['K01', 'K02'],
          parent_task_id: 'task:previous',
          relationship: 'follow_up',
        },
      },
    })
  })

  it('accepts an existing plot without a source or explicit chart selection', async () => {
    const core = new FakeCore()
    const runtime = new AgentFoundationRuntime({
      core,
      emit: () => undefined,
      id: () => 'fixed',
      createRuntime: () => ({
        abort: () => false,
        run: async (activation: AgentActivation): Promise<AgentYieldContract> => ({
          outcome: 'cancelled',
          activation_id: activation.activation_id,
          task_id: activation.task_id,
          task_version: activation.task_version,
          message: 'Fake typed yield.',
        }),
      }),
    })

    const input = {
      projectId: 'project:test',
      selectedSources: [],
      selectedPlotIds: ['plot:existing'],
      expectedProjectVersion: 4,
      instruction: '把标题改成温度响应。',
    }
    expect(runtime.canRun(input)).toBe(true)
    await runtime.run(input)

    expect(core.calls.find((call) => call.method === 'engine.plots.get')).toMatchObject({
      params: { project_id: 'project:test', plot_id: 'plot:existing' },
    })
    expect(core.calls.find((call) => call.method === 'agent.tasks.create')).toMatchObject({
      params: {
        envelope: {
          selected_sources: [],
          selected_plots: [{
            plot_id: 'plot:existing',
            plot_version: 3,
            profile_id: 'K01',
          }],
          selected_profile_ids: [],
        },
      },
    })
  })

  it('re-enters the durable repair pump and retries only after a typed repair yield', async () => {
    class PartialCore {
      readonly calls: string[] = []
      private state = 'partial'
      private pumpCalls = 0

      async request(method: string): Promise<unknown> {
        this.calls.push(method)
        if (method === 'agent.tasks.list') {
          return { tasks: [{ task_id: 'task:partial', state: this.state, intent: { intent_id: 'intent:partial' } }] }
        }
        if (method === 'agent.tasks.plan.get') {
          return {
            task: {
              task_id: 'task:partial',
              task_version: this.state === 'partial' ? 8 : 10,
              state: this.state,
              items: [
                { item_id: 'item:partial.1', state: 'succeeded', attempt_count: 1 },
                {
                  item_id: 'item:partial.2',
                  state: this.state === 'completed_verified' ? 'succeeded' : 'repairable_failed',
                  attempt_count: this.state === 'completed_verified' ? 2 : 1,
                },
              ],
            },
            plan: { plan_id: 'plan:partial', items: [] },
            plan_hash: 'b'.repeat(64),
            confirmation_state: 'confirmed',
          }
        }
        if (method === 'agent.tasks.pump.next') {
          this.pumpCalls += 1
          if (this.pumpCalls === 1) {
            return {
              kind: 'run_activation',
              activation: {
                activation_id: 'activation:repair',
                task_id: 'task:partial',
                task_version: 9,
                reason: 'verification_failed',
                task_state: 'repairing',
                permission_phase: 'p0_read',
                allowed_tools: ['inspect_source'],
                verification_report_ids: ['verification:partial.2.attempt-1'],
              },
            }
          }
          return { kind: 'wait', reason: 'execution_pending', task_state: 'executing' }
        }
        if (method === 'agent.tasks.activation.running') return { state: 'repairing' }
        if (method === 'agent.tasks.yield.accept') {
          this.state = 'executing'
          return { state: 'executing' }
        }
        if (method === 'agent.tasks.execute') {
          this.state = 'completed_verified'
          return { task: { state: this.state } }
        }
        throw new Error(`Unexpected method ${method}`)
      }
    }
    const core = new PartialCore()
    const runtime = new AgentFoundationRuntime({
      core,
      emit: () => undefined,
      createRuntime: () => ({
        abort: () => false,
        run: async (activation: AgentActivation): Promise<AgentYieldContract> => ({
          outcome: 'technical_repair_ready',
          activation_id: activation.activation_id,
          task_id: activation.task_id,
          task_version: activation.task_version,
          proposal: {
            failed_report_ids: ['verification:partial.2.attempt-1'],
            affected_item_ids: ['item:partial.2'],
            repair_operations: ['retry_execution'],
            preserves_confirmed_semantics: true,
            proposal_hash: 'c'.repeat(64),
          },
        }),
      }),
    })

    await runtime.list('project:test')
    await expect(runtime.execute({ projectId: 'project:test', planId: 'plan:partial' }))
      .resolves.toMatchObject({ task: { state: 'completed_verified' } })
    expect(core.calls.filter((method) => method === 'agent.tasks.execute')).toHaveLength(1)
    expect(core.calls).toContain('agent.tasks.yield.accept')
  })

  it('returns a typed repair question instead of hiding it behind the partial task view', async () => {
    let pumpCalls = 0
    const core = {
      request: async (method: string): Promise<unknown> => {
        if (method === 'agent.tasks.list') {
          return { tasks: [{ task_id: 'task:repair-question', state: 'partial', intent: { intent_id: 'intent:repair-question' } }] }
        }
        if (method === 'agent.tasks.plan.get') return {
          task: {
            task_id: 'task:repair-question', task_version: 8, state: 'partial',
            items: [
              { item_id: 'item:repair-question.1', state: 'succeeded', attempt_count: 1 },
              { item_id: 'item:repair-question.2', state: 'repairable_failed', attempt_count: 1 },
            ],
          },
          plan: { plan_id: 'plan:repair-question', items: [] },
          plan_hash: 'b'.repeat(64),
          confirmation_state: 'confirmed',
        }
        if (method === 'agent.tasks.pump.next') {
          pumpCalls += 1
          return pumpCalls === 1
            ? {
                kind: 'run_activation',
                activation: {
                  activation_id: 'activation:repair-question',
                  task_id: 'task:repair-question',
                  task_version: 9,
                  task_state: 'repairing',
                  permission_phase: 'p0_read',
                  allowed_tools: ['inspect_source'],
                },
              }
            : { kind: 'wait', reason: 'awaiting_input', task_state: 'awaiting_input' }
        }
        if (method === 'agent.tasks.activation.running') return { state: 'repairing' }
        if (method === 'agent.tasks.yield.accept') return { state: 'awaiting_input' }
        throw new Error(`Unexpected method ${method}`)
      },
    }
    const runtime = new AgentFoundationRuntime({
      core,
      emit: () => undefined,
      createRuntime: () => ({
        abort: () => false,
        run: async (activation: AgentActivation): Promise<AgentYieldContract> => ({
          outcome: 'needs_input',
          activation_id: activation.activation_id,
          task_id: activation.task_id,
          task_version: activation.task_version,
          questions: [{
            question_key: 'repair_choice',
            prompt: '失败项应取消，还是提供替代数据后重试？',
            answer_kind: 'text',
            required: true,
          }],
        }),
      }),
    })

    await runtime.list('project:test')
    await expect(runtime.execute({ projectId: 'project:test', planId: 'plan:repair-question' }))
      .resolves.toEqual({
        outcome: 'needs_input',
        workflow_run_id: 'task:repair-question',
        questions: [{
          question_key: 'repair_choice',
          prompt: '失败项应取消，还是提供替代数据后重试？',
          answer_kind: 'text',
          required: true,
        }],
      })
  })

  it('treats an already verified revised plan as an idempotent execution success', async () => {
    const calls: string[] = []
    const view = {
      task: {
        task_id: 'task:already-complete', task_version: 12, state: 'completed_verified',
        items: [{ item_id: 'item:already-complete.1', state: 'succeeded', attempt_count: 1 }],
      },
      plan: { plan_id: 'plan:already-complete', items: [] },
      plan_hash: 'd'.repeat(64),
      confirmation_state: 'confirmed',
    }
    const runtime = new AgentFoundationRuntime({
      core: {
        request: async (method: string): Promise<unknown> => {
          calls.push(method)
          if (method === 'agent.tasks.list') {
            return { tasks: [{ task_id: 'task:already-complete', state: 'completed_verified', intent: { intent_id: 'intent:already-complete' } }] }
          }
          if (method === 'agent.tasks.plan.get') return view
          throw new Error(`Unexpected method ${method}`)
        },
      },
      emit: () => undefined,
    })

    await runtime.list('project:test')
    await expect(runtime.execute({ projectId: 'project:test', planId: 'plan:already-complete' }))
      .resolves.toEqual(view)
    expect(calls).not.toContain('agent.tasks.execute')
  })

  it.each([
    {
      yielded: {
        outcome: 'runtime_failed',
        error: {
          code: 'PI_V2_PROVIDER_FAILED',
          category: 'runtime',
          message: '402 Insufficient Balance',
          retryable: true,
          requires_user: false,
          side_effect_state: 'known_none',
        },
      },
      wait: { reason: 'terminal', task_state: 'failed' },
      code: 'AGENT_V2_PROVIDER_BALANCE',
      message: /余额不足.*未修改项目/,
    },
    {
      yielded: {
        outcome: 'runtime_failed',
        error: {
          code: 'PI_V2_PROVIDER_FAILED',
          category: 'runtime',
          message: 'fetch failed',
          retryable: true,
          requires_user: false,
          side_effect_state: 'known_none',
        },
      },
      wait: { reason: 'terminal', task_state: 'failed' },
      code: 'AGENT_V2_PROVIDER_UNAVAILABLE',
      message: /模型服务不可用.*未修改项目/,
    },
    {
      yielded: {
        outcome: 'budget_exhausted',
        exhausted_budget: 'wall_time',
        message: 'wall-time budget exhausted',
      },
      wait: { reason: 'terminal', task_state: 'failed' },
      code: 'AGENT_V2_DECISION_TIMEOUT',
      message: /响应超时.*未修改项目/,
    },
    {
      yielded: {
        outcome: 'budget_exhausted',
        exhausted_budget: 'model_turns',
        message: 'model-turn budget exhausted',
      },
      wait: { reason: 'terminal', task_state: 'failed' },
      code: 'AGENT_V2_BUDGET_EXHAUSTED',
      message: /model_turns 限额.*创建新任务/,
    },
  ])('reports an actionable failure when planning stops before confirmation', async (example) => {
    class FailureCore extends FakeCore {
      private failurePumpCalls = 0

      override async request(method: string, params?: unknown): Promise<unknown> {
        if (method === 'agent.tasks.pump.next') {
          this.failurePumpCalls += 1
          if (this.failurePumpCalls > 1) return { kind: 'wait', ...example.wait }
        }
        return super.request(method, params)
      }
    }
    const core = new FailureCore()
    const runtime = new AgentFoundationRuntime({
      core,
      emit: () => undefined,
      id: () => 'fixed',
      createRuntime: () => ({
        abort: () => false,
        run: async (active: AgentActivation): Promise<AgentYieldContract> => ({
          ...example.yielded,
          activation_id: active.activation_id,
          task_id: active.task_id,
          task_version: active.task_version,
        } as AgentYieldContract),
      }),
    })

    await expect(runtime.run({
      projectId: 'project:test',
      selectedSources: [{ datasetId: 'source:test', sourceVersion: 1 }],
      selectedProfileIds: ['K01'],
      expectedProjectVersion: 1,
      instruction: '绘制折线图。',
    })).rejects.toMatchObject({ code: example.code, message: example.message })
  })
})
