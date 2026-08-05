import { describe, expect, it, vi } from 'vitest'

import type { CloseRequest, TaskSnapshot } from '../../shared/desktop-contract.js'
import { AppCloseController } from './app-close-controller.js'

const ACTIVE_TASKS: TaskSnapshot = {
  tasks: [{
    taskId: 'task:one',
    sequence: 2,
    state: 'running',
    cancellable: true,
  }],
  activeTaskCount: 1,
  hasCommittingTask: false,
}

const NO_TASKS: TaskSnapshot = {
  tasks: [],
  activeTaskCount: 0,
  hasCommittingTask: false,
}

describe('active-task close coordination', () => {
  it('exposes wait/return without exiting and cancel-and-quit with a safe task boundary', async () => {
    let snapshot = ACTIVE_TASKS
    const requests: CloseRequest[] = []
    const stopCore = vi.fn(async () => undefined)
    const quit = vi.fn()
    const preventDefault = vi.fn()
    const controller = new AppCloseController({
      getTasks: () => snapshot,
      cancelAllTasks: vi.fn(async () => ({ ok: true } as const)),
      stopCore,
      emitCloseRequest: (request) => requests.push(request),
      quit,
    })

    controller.handleWindowClose({ preventDefault })
    expect(preventDefault).toHaveBeenCalledOnce()
    expect(requests).toHaveLength(1)

    expect(await controller.respond({
      requestId: requests[0].requestId,
      choice: 'wait',
    })).toEqual({ ok: true })
    expect(stopCore).not.toHaveBeenCalled()

    controller.handleWindowClose({ preventDefault })
    const secondRequest = requests.at(-1)
    expect(secondRequest).toBeDefined()
    expect(await controller.respond({
      requestId: secondRequest?.requestId ?? '',
      choice: 'cancel-and-quit',
    })).toEqual({ ok: true })
    expect(stopCore).not.toHaveBeenCalled()

    snapshot = NO_TASKS
    controller.handleTaskSnapshot(snapshot)
    await vi.waitFor(() => expect(quit).toHaveBeenCalledOnce())
    expect(stopCore).toHaveBeenCalledOnce()
  })

  it('rejects stale close responses', async () => {
    const controller = new AppCloseController({
      getTasks: () => ACTIVE_TASKS,
      cancelAllTasks: vi.fn(async () => ({ ok: true } as const)),
      stopCore: vi.fn(async () => undefined),
      emitCloseRequest: vi.fn(),
      quit: vi.fn(),
    })

    await expect(controller.respond({ requestId: 'close:stale', choice: 'return' }))
      .resolves.toMatchObject({ ok: false, error: { code: 'IPC_INVALID_ARGUMENT' } })
  })
})
