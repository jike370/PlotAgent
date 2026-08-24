import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { TaskDrawer } from './TaskDrawer'

describe('TaskDrawer', () => {
  it('shows and cancels a durable Agent task while the model is still planning', () => {
    const onCancel = vi.fn()
    render(<TaskDrawer
      tasks={[]}
      durableTasks={[]}
      plans={[]}
      runtimeEvent={{
        schemaVersion: '1.0',
        runId: 'workflow:test',
        projectId: 'project:test',
        taskId: 'task:test',
        sequence: 3,
        startedAt: '2026-08-25T00:00:00.000Z',
        occurredAt: '2026-08-25T00:00:01.000Z',
        stage: 'planning',
        label: 'Agent 正在检查数据并规划…',
      }}
      onCancel={onCancel}
      onAcceptPartial={vi.fn()}
      onResumeTask={vi.fn()}
      onRetryPlan={vi.fn()}
      onClose={vi.fn()}
    />)

    const dialog = screen.getByRole('dialog', { name: '任务中心' })
    expect(within(dialog).getByRole('button', { name: '进行中 1' })).toBeInTheDocument()
    expect(within(dialog).getByText('Agent 正在检查数据并规划…')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: '停止任务' }))
    expect(onCancel).toHaveBeenCalledWith('task:test')
  })

  it('shows durable partial results, safe diagnostics, and retries failed items only', () => {
    const onRetryPlan = vi.fn()
    const onAcceptPartial = vi.fn()
    const onCancel = vi.fn()
    render(<TaskDrawer
      tasks={[]}
      durableTasks={[{
        taskId: 'task:partial',
        taskVersion: 6,
        state: 'partial',
        projectRevision: 14,
        updatedAt: '2026-08-18T07:00:00Z',
        items: [
          {
            itemId: 'item:kept',
            state: 'succeeded',
            attemptCount: 1,
            outputPlot: { plotId: 'plot:kept', plotVersion: 2 },
          },
          {
            itemId: 'item:failed',
            state: 'repairable_failed',
            attemptCount: 2,
            failure: {
              code: 'ORIGIN_BUSY',
              message: 'Origin 暂时忙碌。',
              retryable: true,
              diagnosticId: 'diag:safe-1',
            },
          },
        ],
      }]}
      plans={[{
        planId: 'plan:partial',
        taskId: 'task:partial',
        taskVersion: 6,
        state: 'partially_succeeded',
        confirmationState: 'confirmed',
        warnings: [],
        completedCount: 1,
        resumable: true,
        bindings: [],
        boundActions: [],
        steps: [
          { taskItemId: 'item:kept', actionType: 'workflow_item', taskKind: 'create', profileId: 'K01', title: '创建 K01', detail: '', sourceDatasetIds: [], dataOperations: [], bindings: [], sourceFieldRoles: [], changes: [], state: 'succeeded', attemptCount: 1 },
          { taskItemId: 'item:failed', actionType: 'workflow_item', taskKind: 'create', profileId: 'K03', title: '创建 K03', detail: '', sourceDatasetIds: [], dataOperations: [], bindings: [], sourceFieldRoles: [], changes: [], state: 'failed', attemptCount: 2, failure: { code: 'ORIGIN_BUSY', message: 'Origin 暂时忙碌。', retryable: true } },
        ],
      }]}
      onCancel={onCancel}
      onAcceptPartial={onAcceptPartial}
      onResumeTask={vi.fn()}
      onRetryPlan={onRetryPlan}
      onClose={vi.fn()}
    />)

    const dialog = screen.getByRole('dialog', { name: '任务中心' })
    expect(within(dialog).getByText(/1\/2 项已完成/)).toBeInTheDocument()
    expect(within(dialog).getByText('plot:kept · v2')).toBeInTheDocument()
    expect(within(dialog).getByRole('alert')).toHaveTextContent('诊断 diag:safe-1')
    expect(within(dialog).getByText('技术详情')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: '仅重试失败项' }))
    expect(onRetryPlan).toHaveBeenCalledWith('plan:partial')
    fireEvent.click(within(dialog).getByRole('button', { name: '保留成功项并结束' }))
    expect(onAcceptPartial).toHaveBeenCalledWith('task:partial')
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('offers an explicit restart continuation for an interrupted planning task', () => {
    const onResumeTask = vi.fn()
    render(<TaskDrawer
      tasks={[]}
      durableTasks={[{
        taskId: 'task:recovered-planning',
        taskVersion: 4,
        state: 'investigating',
        projectRevision: 2,
        items: [],
      }]}
      plans={[]}
      onCancel={vi.fn()}
      onAcceptPartial={vi.fn()}
      onResumeTask={onResumeTask}
      onRetryPlan={vi.fn()}
      onClose={vi.fn()}
    />)

    fireEvent.click(screen.getByRole('button', { name: '继续任务' }))
    expect(onResumeTask).toHaveBeenCalledWith('task:recovered-planning')
  })

  it('does not offer duplicate continuation while a durable activation is running', () => {
    render(<TaskDrawer
      tasks={[]}
      durableTasks={[{
        taskId: 'task:active-planning',
        taskVersion: 4,
        state: 'investigating',
        projectRevision: 2,
        activeActivationId: 'activation:active-planning',
        items: [],
      }]}
      plans={[]}
      onCancel={vi.fn()}
      onAcceptPartial={vi.fn()}
      onResumeTask={vi.fn()}
      onRetryPlan={vi.fn()}
      onClose={vi.fn()}
    />)

    expect(screen.queryByRole('button', { name: '继续任务' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '停止任务' })).toBeInTheDocument()
  })

  it('does not style cancelled, rejected, or unsupported terminal tasks as success', () => {
    const { container } = render(<TaskDrawer
      tasks={[]}
      durableTasks={[
        { taskId: 'task:cancelled', taskVersion: 2, state: 'cancelled', projectRevision: 2, items: [] },
        { taskId: 'task:rejected', taskVersion: 2, state: 'rejected', projectRevision: 2, items: [] },
        { taskId: 'task:unsupported', taskVersion: 2, state: 'unsupported', projectRevision: 2, items: [] },
        { taskId: 'task:completed', taskVersion: 2, state: 'completed_verified', projectRevision: 2, items: [] },
      ]}
      plans={[]}
      onCancel={vi.fn()}
      onAcceptPartial={vi.fn()}
      onResumeTask={vi.fn()}
      onRetryPlan={vi.fn()}
      onClose={vi.fn()}
    />)

    fireEvent.click(screen.getByRole('button', { name: '全部 4' }))
    expect(container.querySelectorAll('.task-item--neutral')).toHaveLength(3)
    expect(container.querySelectorAll('.task-item--success')).toHaveLength(1)
  })
})
