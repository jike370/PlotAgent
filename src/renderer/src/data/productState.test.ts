import { describe, expect, it } from 'vitest'

import { projectVersionFrom, readAgentOutcome, readProjects } from './productState'

describe('product state normalization', () => {
  it('merges create and open summaries without losing the project name', () => {
    expect(readProjects({
      project: { project_id: 'project:one', display_name: '温度响应示例', is_open: false },
      opened: { project_id: 'project:one', project_version: 2, status: 'open' },
    })).toEqual([{
      projectId: 'project:one',
      name: '温度响应示例',
      projectVersion: 2,
      isOpen: true,
    }])
  })

  it('only exposes an explicit single Agent execution as the current plot', () => {
    const single = readAgentOutcome({
      accepted: true,
      decision: { decision_type: 'action_plan' },
      executions: [{ plot_id: 'plot:one', plot_version: 2 }],
      execution: { plot_id: 'plot:one', plot_version: 2 },
    })
    expect(single.execution).toEqual(expect.objectContaining({ plotId: 'plot:one', plotVersion: 2 }))
    expect(single.executionCount).toBe(1)

    const multiple = readAgentOutcome({
      accepted: true,
      decision: { decision_type: 'action_plan' },
      executions: [
        { plot_id: 'plot:one', plot_version: 2 },
        { plot_id: 'plot:two', plot_version: 4 },
      ],
      scope_execution: {
        target_kind: 'batch',
        target_id: 'batch:one',
        target_version: 2,
        project_version: 7,
        updated_plot_count: 2,
        batch: {
          item_states: [
            { item_id: 'item:one', state: 'succeeded' },
            { item_id: 'item:two', state: 'failed' },
          ],
        },
      },
    })
    expect(multiple.execution).toBeUndefined()
    expect(multiple.executionCount).toBe(2)
    expect(multiple.message).toContain('当前作用对象保持不变')
    expect(multiple.scopeExecution).toEqual({
      kind: 'batch',
      id: 'batch:one',
      version: 2,
      projectVersion: 7,
      updatedPlotCount: 2,
      batchItems: [
        { id: 'item:one', state: 'succeeded' },
        { id: 'item:two', state: 'failed' },
      ],
    })
  })

  it('prefers the root project revision over nested plot revisions', () => {
    expect(projectVersionFrom({
      project_version: 8,
      executions: [
        { project_version: 6, plot_id: 'plot:one', plot_version: 2 },
        { project_version: 7, plot_id: 'plot:two', plot_version: 2 },
      ],
    }, 1)).toBe(8)
  })
})
