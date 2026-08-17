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
      return { state: this.state }
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
})
