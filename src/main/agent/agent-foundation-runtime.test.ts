import { describe, expect, it } from 'vitest'

import type { AgentActivation, AgentYieldContract } from '../../shared/generated/contracts.js'
import {
  AgentFoundationRuntime,
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
    if (method === 'agent.tasks.create') return { state: 'created' }
    if (method === 'agent.tasks.list') {
      return {
        tasks: [{ task_id: 'task:fixed', intent: { intent_id: 'intent:fixed' } }],
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
      task: {
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
      },
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
}

describe('AgentFoundationRuntime', () => {
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
    expect(events.at(-1)).toMatchObject({ stage: 'completed', label: '计划已生成，等待确认' })
  })

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
    await expect(runtime.confirm({ projectId: 'project:test', planId: 'plan:fixed' }))
      .resolves.toMatchObject({ task: { state: 'executing' } })
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
          return { tasks: [{ task_id: 'task:partial', intent: { intent_id: 'intent:partial' } }] }
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

  it.each([
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
      wait: { reason: 'blocked', task_state: 'blocked' },
      code: 'AGENT_V2_DECISION_TIMEOUT',
      message: /响应超时.*未修改项目/,
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
