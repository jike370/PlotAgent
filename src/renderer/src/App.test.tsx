import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { App } from './App'

describe('PlotAgent desktop prototype', () => {
  it('renders structured scientific conversation objects', () => {
    render(<App />)

    expect(screen.getByText('temperature_series.zip')).toBeInTheDocument()
    expect(screen.getByText('温度响应 · 批次 B-024')).toBeInTheDocument()
    expect(screen.getByText('.opju 未导出')).toBeInTheDocument()
  })

  it('opens the first-use empty conversation', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: /新建对话/ }))

    expect(screen.getByRole('heading', { name: '从一份真实数据开始' })).toBeInTheDocument()
    expect(screen.getByText('原始内容保持只读。', { exact: false })).toBeInTheDocument()
  })

  it('opens the explicit chart selection library', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: '图形库' }))

    expect(screen.getByRole('heading', { name: '图形库' })).toBeInTheDocument()
    expect(screen.getByText('首轮正式目标 32 项 · 由你明确选择')).toBeInTheDocument()
  })
})
