import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { App } from './App'

describe('App', () => {
  it('renders the desktop scaffold', () => {
    render(<App />)

    expect(screen.getByText('PlotAgent 桌面端骨架已就绪')).toBeInTheDocument()
  })
})
