import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { BatchInspector } from './BatchInspector'

describe('BatchInspector', () => {
  it('switches between grid, list and large carousel views', async () => {
    const user = userEvent.setup()
    render(<BatchInspector onClose={vi.fn()} />)

    expect(screen.getByLabelText('批次网格视图')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '列表视图' }))
    expect(screen.getByRole('table', { name: '批次列表视图' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '大图轮播视图' }))
    expect(screen.getByLabelText('批次大图轮播视图')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '下一张图' })).toBeInTheDocument()
  })

  it('keeps coordinate and overlay comparisons temporary until explicitly saved as a new chart', async () => {
    const user = userEvent.setup()
    render(<BatchInspector onClose={vi.fn()} />)

    expect(screen.getByText('当前选择 · 2 张')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /统一坐标范围/ }))
    expect(screen.getByText('临时检查状态，不会生成图表版本')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /叠加比较/ }))
    expect(screen.getByRole('heading', { name: '临时叠加比较' })).toBeInTheDocument()
    expect(screen.getByText('未保存，不生成版本或正式对象')).toBeInTheDocument()
    expect(screen.queryByText(/CHART-003/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '保存为新图' }))
    expect(screen.getByText('已创建正式图表 CHART-003')).toBeInTheDocument()
    expect(screen.getByText('批次内原图与版本均未改变。', { exact: false })).toBeInTheDocument()
  })

  it('filters by failure and scientific warnings, then sorts by metadata and update time', async () => {
    const user = userEvent.setup()
    render(<BatchInspector onClose={vi.fn()} />)

    await user.selectOptions(screen.getByRole('combobox', { name: '按状态筛选' }), 'failed')
    const grid = screen.getByLabelText('批次网格视图')
    expect(within(grid).getByText('sample_D_50C.csv')).toBeInTheDocument()
    expect(within(grid).queryByText('sample_A_25C.csv')).not.toBeInTheDocument()

    await user.selectOptions(screen.getByRole('combobox', { name: '按状态筛选' }), 'all')
    await user.selectOptions(screen.getByRole('combobox', { name: '按检查标记筛选' }), 'scientific-warning')
    expect(within(grid).getByText('sample_B_37C.csv')).toBeInTheDocument()
    expect(within(grid).queryByText('sample_C_42C.csv')).not.toBeInTheDocument()

    await user.selectOptions(screen.getByRole('combobox', { name: '批次排序' }), 'temperature-asc')
    await user.selectOptions(screen.getByRole('combobox', { name: '批次排序' }), 'updated-desc')
    expect(screen.getByText('显示 1 / 4')).toBeInTheDocument()
  })

  it('marks anomalies, excludes an item from export and keeps scope synchronized with selection', async () => {
    const user = userEvent.setup()
    render(<BatchInspector onClose={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: '标记异常 sample_A_25C.csv' }))
    expect(screen.getByRole('button', { name: '移除异常标记 sample_A_25C.csv' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '排除当前导出 sample_A_25C.csv' }))
    expect(screen.getByRole('button', { name: '恢复当前导出 sample_A_25C.csv' })).toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: '选择 sample_B_37C.csv' }))
    expect(screen.getByText('当前选择 · 1 张')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /叠加比较/ })).toBeDisabled()
  })
})
