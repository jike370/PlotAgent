import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { TaskDrawer } from './TaskDrawer'

describe('TaskDrawer', () => {
  it('shows durable partial results, safe diagnostics, and retries failed items only', () => {
    const onRetryPlan = vi.fn()
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
          { taskItemId: 'item:kept', actionType: 'workflow_item', taskKind: 'create', profileId: 'K01', title: '创建 K01', detail: '', sourceDatasetIds: [], bindings: [], changes: [], state: 'succeeded', attemptCount: 1 },
          { taskItemId: 'item:failed', actionType: 'workflow_item', taskKind: 'create', profileId: 'K03', title: '创建 K03', detail: '', sourceDatasetIds: [], bindings: [], changes: [], state: 'failed', attemptCount: 2, failure: { code: 'ORIGIN_BUSY', message: 'Origin 暂时忙碌。', retryable: true } },
        ],
      }]}
      onCancel={onCancel}
      onRetryPlan={onRetryPlan}
      onClose={vi.fn()}
    />)

    const dialog = screen.getByRole('dialog', { name: '任务中心' })
    expect(within(dialog).getByText(/1\/2 项已完成/)).toBeInTheDocument()
    expect(within(dialog).getByText('plot:kept · v2')).toBeInTheDocument()
    expect(within(dialog).getByRole('alert')).toHaveTextContent('诊断 diag:safe-1')
    fireEvent.click(within(dialog).getByRole('button', { name: '仅重试失败项' }))
    expect(onRetryPlan).toHaveBeenCalledWith('plan:partial')
    expect(onCancel).not.toHaveBeenCalled()
  })
})
