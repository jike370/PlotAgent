import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { App } from './App'

describe('PlotAgent desktop prototype', () => {
  const openSampleProject = async (user: ReturnType<typeof userEvent.setup>): Promise<void> => {
    await user.click(screen.getByRole('button', { name: /用示例项目试用/ }))
  }

  it('starts with three clearly weighted first-use paths', () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: '从第一份数值数据开始' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /用示例项目试用/ })).toHaveClass('startup-action--primary')
    expect(screen.getByRole('button', { name: /导入自己的数据/ })).toHaveClass('startup-action--secondary')
    expect(screen.getByRole('button', { name: '打开已有 .plotproj' })).toHaveClass('startup-project-link')
    expect(screen.getByText('还没有本机项目')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '浏览图形库' })).not.toBeInTheDocument()
  })

  it('keeps import and existing-project entry points local and interactive', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: /导入自己的数据/ }))
    expect(screen.getByText(/已打开数值数据选择器/)).toHaveClass('toast')

    await user.click(screen.getByRole('button', { name: '打开已有 .plotproj' }))
    expect(screen.getByText('已打开 .plotproj 项目选择器')).toHaveClass('toast')
  })

  it('opens a modifiable local copy of the numeric sample project', async () => {
    const user = userEvent.setup()
    render(<App />)

    await openSampleProject(user)

    expect(screen.getByText('temperature_series.zip')).toBeInTheDocument()
    expect(screen.getByText('温度响应 · 批次 B-024')).toBeInTheDocument()
    expect(screen.getByText('.opju 未导出')).toBeInTheDocument()
    expect(screen.getByText(/已创建“温度响应实验”本地副本/)).toHaveClass('toast')
  })

  it('opens the first-use empty conversation', async () => {
    const user = userEvent.setup()
    render(<App />)

    await openSampleProject(user)
    await user.click(screen.getByRole('button', { name: /新建对话/ }))

    expect(screen.getByRole('heading', { name: '从一份真实数据开始' })).toBeInTheDocument()
    expect(screen.getByText('原始内容保持只读。', { exact: false })).toBeInTheDocument()
  })

  it('opens the explicit chart selection library', async () => {
    const user = userEvent.setup()
    render(<App />)

    await openSampleProject(user)
    await user.click(screen.getByRole('button', { name: '图形库' }))

    expect(screen.getByRole('heading', { name: '图形库' })).toBeInTheDocument()
    expect(screen.getByText('首轮正式目标 31 项 · 全部为数值数据图表 · 由你明确选择')).toBeInTheDocument()
  })

  it('shows S61 numeric compatibility without first-release image or map entries', async () => {
    const user = userEvent.setup()
    render(<App />)

    await openSampleProject(user)
    await user.click(screen.getByRole('button', { name: '图形库' }))
    await user.type(screen.getByPlaceholderText('搜索名称、缩写、学科、数据形状或稳定 ID'), 'S61')
    await user.click(screen.getByRole('button', { name: /S61.*混淆矩阵/ }))

    expect(screen.getByText('缺少真实类别与预测类别字段。不会自动替换为其他图形。')).toBeInTheDocument()
    expect(screen.queryByText('科学图像面板')).not.toBeInTheDocument()
    expect(screen.queryByText('专题地图')).not.toBeInTheDocument()
  })

  it('builds compositions from numeric charts only', async () => {
    const user = userEvent.setup()
    render(<App />)

    await openSampleProject(user)
    await user.click(screen.getByRole('button', { name: '创建组合图' }))
    expect(screen.getByLabelText('可用数值图表')).toBeInTheDocument()
    expect(screen.getByText('第一轮组合图只使用项目内数值数据图表，导出保持矢量结构。')).toBeInTheDocument()
    expect(screen.queryByText('导入图片面板')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '2 × 2' }))
    expect(screen.getByLabelText('面板 D 混淆矩阵')).toBeInTheDocument()
  })

  it('opens the project resource library from the project heading and blocks referenced raw data deletion', async () => {
    const user = userEvent.setup()
    render(<App />)

    await openSampleProject(user)
    await user.click(screen.getByRole('button', { name: '打开项目资源库：温度响应实验' }))

    expect(screen.getByRole('dialog', { name: '项目资源库' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /原始数据/ })).toHaveAttribute('aria-selected', 'true')

    await user.click(screen.getByRole('button', { name: '删除' }))

    const blocker = screen.getByRole('alert')
    expect(blocker).toHaveTextContent('无法直接删除原始数据')
    expect(blocker).toHaveTextContent('7 个下游对象仍依赖')
    expect(screen.getByRole('button', { name: '删除原始数据' })).toBeDisabled()
  })

  it('shows the upstream operation chain for derived data', async () => {
    const user = userEvent.setup()
    render(<App />)

    await openSampleProject(user)
    await user.click(screen.getByRole('button', { name: '打开项目资源库：温度响应实验' }))
    await user.click(screen.getByRole('tab', { name: /派生数据/ }))

    expect(screen.getByRole('heading', { name: '上游操作链' })).toBeInTheDocument()
    expect(screen.getByText('移除无效观测')).toBeInTheDocument()
    expect(screen.getByText('删除 7 个无法解析的 fluorescence 值')).toBeInTheDocument()
  })

  it('searches across all project resource categories', async () => {
    const user = userEvent.setup()
    render(<App />)

    await openSampleProject(user)
    await user.click(screen.getByRole('button', { name: '打开项目资源库：温度响应实验' }))
    await user.type(screen.getByRole('textbox', { name: '搜索项目资源' }), 'Figure 1')

    expect(screen.getByLabelText('项目资源搜索结果')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Figure 1 · 温度响应总览' })).toBeInTheDocument()
    expect(screen.getByText('组合图 · COMP-001')).toBeInTheDocument()
  })

  it('opens the resource library from the reference selector and treats exports as external location records', async () => {
    const user = userEvent.setup()
    render(<App />)

    await openSampleProject(user)
    await user.click(screen.getByRole('button', { name: '引用' }))
    await user.click(screen.getByRole('option', { name: /浏览项目资源库/ }))
    await user.click(screen.getByRole('tab', { name: /导出/ }))

    expect(screen.getByRole('heading', { name: '外部文件定位记录' })).toBeInTheDocument()
    expect(screen.getByText('D:\\exports\\temperature_series')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '在资源管理器中定位' })).toBeInTheDocument()
  })

  it('renames and archives a project resource with accessible controls', async () => {
    const user = userEvent.setup()
    render(<App />)

    await openSampleProject(user)
    await user.click(screen.getByRole('button', { name: '打开项目资源库：温度响应实验' }))
    await user.click(screen.getByRole('button', { name: '重命名' }))
    const nameInput = screen.getByRole('textbox', { name: '资源名称' })
    await user.clear(nameInput)
    await user.type(nameInput, 'temperature_series_original.zip')
    await user.click(screen.getByRole('button', { name: '保存名称' }))

    expect(screen.getByRole('heading', { name: 'temperature_series_original.zip' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '归档' }))
    expect(screen.getByText('已归档', { selector: '.status-label' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '恢复资源' })).toBeInTheDocument()
  })
})
