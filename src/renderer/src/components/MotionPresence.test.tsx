import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { MotionPresence } from './MotionPresence'

afterEach(() => {
  vi.useRealTimers()
})

describe('MotionPresence', () => {
  it('keeps exiting content mounted until its transition budget expires', () => {
    vi.useFakeTimers()
    const { rerender } = render(
      <MotionPresence present exitMs={140}>
        {(phase) => <div data-testid="surface" data-motion-state={phase} />}
      </MotionPresence>,
    )

    expect(screen.getByTestId('surface')).toHaveAttribute('data-motion-state', 'entered')
    rerender(
      <MotionPresence present={false} exitMs={140}>
        {(phase) => <div data-testid="surface" data-motion-state={phase} />}
      </MotionPresence>,
    )
    expect(screen.getByTestId('surface')).toHaveAttribute('data-motion-state', 'exiting')

    act(() => vi.advanceTimersByTime(139))
    expect(screen.getByTestId('surface')).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1))
    expect(screen.queryByTestId('surface')).not.toBeInTheDocument()
  })

  it('interrupts an exit when the surface is reopened', () => {
    vi.useFakeTimers()
    const renderSurface = (present: boolean) => (
      <MotionPresence present={present} exitMs={160}>
        {(phase) => <div data-testid="surface" data-motion-state={phase} />}
      </MotionPresence>
    )
    const { rerender } = render(renderSurface(true))

    rerender(renderSurface(false))
    expect(screen.getByTestId('surface')).toHaveAttribute('data-motion-state', 'exiting')
    rerender(renderSurface(true))
    expect(screen.getByTestId('surface')).toHaveAttribute('data-motion-state', 'entered')

    act(() => vi.advanceTimersByTime(200))
    expect(screen.getByTestId('surface')).toBeInTheDocument()
  })
})
