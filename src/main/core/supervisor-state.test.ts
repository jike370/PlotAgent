import { describe, expect, it } from 'vitest'

import { INITIAL_CORE_STATUS, publicCoreError, reduceSupervisorState, RestartBudget } from './supervisor-state.js'

describe('Core supervisor state', () => {
  it('follows the start, ready, restart, and stop lifecycle', () => {
    const starting = reduceSupervisorState(INITIAL_CORE_STATUS, { type: 'start' })
    const ready = reduceSupervisorState(starting, { type: 'ready' })
    const restarting = reduceSupervisorState(ready, {
      type: 'restart-scheduled',
      attempt: 1,
      error: publicCoreError('CORE_PROCESS_EXITED'),
    })
    const startingAgain = reduceSupervisorState(restarting, { type: 'start' })
    const stopping = reduceSupervisorState(startingAgain, { type: 'stop' })

    expect(starting.phase).toBe('starting')
    expect(ready.phase).toBe('ready')
    expect(restarting).toMatchObject({ phase: 'restarting', restartAttempt: 1 })
    expect(startingAgain).toMatchObject({ phase: 'starting', restartAttempt: 1 })
    expect(reduceSupervisorState(stopping, { type: 'stopped' })).toEqual(INITIAL_CORE_STATUS)
  })

  it('rejects illegal transitions', () => {
    expect(() => reduceSupervisorState(INITIAL_CORE_STATUS, { type: 'ready' })).toThrow(
      'Illegal Core supervisor transition',
    )
  })

  it('caps automatic restarts inside the crash window', () => {
    const budget = new RestartBudget(3, 60_000, 100)

    expect(budget.recordFailure(0)).toEqual({ restart: true, attempt: 1, delayMs: 100 })
    expect(budget.recordFailure(1_000)).toEqual({ restart: true, attempt: 2, delayMs: 200 })
    expect(budget.recordFailure(2_000)).toEqual({ restart: true, attempt: 3, delayMs: 400 })
    expect(budget.recordFailure(3_000)).toEqual({ restart: false, attempt: 3, delayMs: 0 })
    expect(budget.recordFailure(70_000)).toEqual({ restart: true, attempt: 1, delayMs: 100 })
  })
})
