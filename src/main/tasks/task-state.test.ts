import { describe, expect, it } from 'vitest'

import { DESKTOP_API_VERSION, type TaskEvent } from '../../shared/desktop-contract.js'
import { applyTaskEvent, isLegalTaskTransition, TaskTracker } from './task-state.js'

function event(state: TaskEvent['state'], sequence: number): TaskEvent {
  return {
    schemaVersion: DESKTOP_API_VERSION,
    eventType: 'task.state',
    taskId: 'task:one',
    state,
    sequence,
  }
}

describe('ExecutionTask state', () => {
  it('accepts the canonical lifecycle and derives close-app metadata', () => {
    const tracker = new TaskTracker()
    expect(tracker.apply(event('queued', 0))).toBe(true)
    expect(tracker.apply(event('preparing', 1))).toBe(true)
    expect(tracker.apply(event('running', 2))).toBe(true)
    expect(tracker.apply(event('committing', 3))).toBe(true)
    expect(tracker.snapshot()).toMatchObject({ activeTaskCount: 1, hasCommittingTask: true })
    expect(tracker.get('task:one')?.cancellable).toBe(false)
    expect(tracker.apply(event('succeeded', 4))).toBe(true)
    expect(tracker.snapshot()).toMatchObject({ activeTaskCount: 0, hasCommittingTask: false })
  })

  it('rejects illegal, stale, and post-terminal events', () => {
    const queued = applyTaskEvent(undefined, event('queued', 0))
    expect(queued).not.toBeNull()
    expect(applyTaskEvent(queued ?? undefined, event('committing', 1))).toBeNull()
    expect(applyTaskEvent(queued ?? undefined, event('preparing', 0))).toBeNull()
    expect(isLegalTaskTransition('succeeded', 'running')).toBe(false)
  })

  it('allows cancelling to finish at the commit boundary', () => {
    expect(isLegalTaskTransition('running', 'cancelling')).toBe(true)
    expect(isLegalTaskTransition('cancelling', 'committing')).toBe(true)
    expect(isLegalTaskTransition('committing', 'succeeded')).toBe(true)
  })

  it('keeps task context and exposes the terminal failure reason', () => {
    const tracker = new TaskTracker()
    expect(tracker.apply({
      ...event('queued', 0),
      taskKind: 'engine-action',
      label: '绘图任务',
    })).toBe(true)
    expect(tracker.apply(event('preparing', 1))).toBe(true)
    expect(tracker.apply({
      ...event('failed', 2),
      error: { code: 'ENGINE_ACTION_INVALID', message: '字段绑定不完整。' },
    })).toBe(true)
    expect(tracker.get('task:one')).toMatchObject({
      taskKind: 'engine-action',
      label: '绘图任务',
      error: { code: 'ENGINE_ACTION_INVALID', message: '字段绑定不完整。' },
    })
  })
})
