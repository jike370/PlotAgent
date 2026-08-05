import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { BatchInspector } from './BatchInspector'

const batch = {
  batchId: 'batch:temperature',
  taskId: 'task:batch',
  version: 3,
  state: 'completed',
  items: [
    { id: 'item:25c', state: 'succeeded' },
    { id: 'item:37c', state: 'running' },
    { id: 'item:50c', state: 'failed' },
  ],
}

describe('BatchInspector', () => {
  it('shows only identities and execution states returned by Core', () => {
    render(<BatchInspector batch={batch} onClose={vi.fn()} />)

    expect(screen.getByRole('heading', { name: '批次执行检查' })).toBeInTheDocument()
    expect(screen.getByText('批次 batch:temperature · 版本 3')).toBeInTheDocument()
    expect(screen.getByText('task:batch')).toBeInTheDocument()
    expect(screen.getByLabelText('批次执行结果')).toBeInTheDocument()
    expect(screen.getByText('item:25c')).toBeInTheDocument()
    expect(screen.queryByText(/sample_A|CHART-003|叠加比较/)).not.toBeInTheDocument()
  })

  it('filters real result items by state and id', async () => {
    const user = userEvent.setup()
    render(<BatchInspector batch={batch} onClose={vi.fn()} />)

    await user.selectOptions(screen.getByRole('combobox', { name: '按状态筛选' }), 'failed')
    const results = screen.getByLabelText('批次执行结果')
    expect(within(results).getByText('item:50c')).toBeInTheDocument()
    expect(within(results).queryByText('item:25c')).not.toBeInTheDocument()

    await user.selectOptions(screen.getByRole('combobox', { name: '按状态筛选' }), 'all')
    await user.type(screen.getByRole('textbox', { name: '搜索批次项' }), '37c')
    expect(within(results).getByText('item:37c')).toBeInTheDocument()
    expect(within(results).queryByText('item:50c')).not.toBeInTheDocument()
    expect(screen.getByText('显示 1 / 3')).toBeInTheDocument()
  })

  it('shows a truthful empty state before Core returns result items', () => {
    render(<BatchInspector batch={{ ...batch, state: 'queued', items: [] }} onClose={vi.fn()} />)
    expect(screen.getByRole('heading', { name: '批次尚未返回执行项' })).toBeInTheDocument()
    expect(screen.getByText(/任务状态为“queued”/)).toBeInTheDocument()
  })
})
