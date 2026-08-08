import { describe, expect, it } from 'vitest'

import type { JsonValue } from '../../shared/desktop-contract.js'
import { PythonCoreSupervisor, resolveCoreLaunchSpec } from './python-supervisor.js'

const READY_WAIT_TIMEOUT_MS = 20_000
const STARTUP_TIMEOUT_MS = 15_000
const TEST_TIMEOUT_MS = 25_000

function waitUntilReady(supervisor: PythonCoreSupervisor): Promise<void> {
  const currentStatus = supervisor.getStatus()
  if (currentStatus.phase === 'ready') return Promise.resolve()
  if (currentStatus.phase === 'failed') {
    return Promise.reject(new Error(currentStatus.error?.message ?? 'Core startup failed'))
  }
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      unsubscribe()
      reject(new Error('Core did not become ready'))
    }, READY_WAIT_TIMEOUT_MS)
    const unsubscribe = supervisor.subscribeStatus((status) => {
      if (status.phase === 'failed') {
        clearTimeout(timer)
        unsubscribe()
        reject(new Error(status.error?.message ?? 'Core startup failed'))
        return
      }
      if (status.phase !== 'ready') return
      clearTimeout(timer)
      unsubscribe()
      resolve()
    })
  })
}

describe('Python Core supervisor integration', () => {
  it('performs the real initialize, heartbeat, request, and shutdown handshake', async () => {
    const supervisor = new PythonCoreSupervisor({
      launch: resolveCoreLaunchSpec({
        appPath: process.cwd(),
        isPackaged: false,
        platform: process.platform,
      }),
      // A full Vitest run can cold-start Python under heavy parallel load. Keep
      // the supervisor's own startup failure ahead of the outer readiness guard.
      startupTimeoutMs: STARTUP_TIMEOUT_MS,
      requestTimeoutMs: 2_000,
      heartbeatIntervalMs: 100,
      heartbeatTimeoutMs: 1_000,
      shutdownTimeoutMs: 2_000,
      maximumRestarts: 0,
    })

    try {
      supervisor.start()
      await waitUntilReady(supervisor)
      await expect(supervisor.request('health.get')).resolves.toMatchObject({
        status: 'ready',
        protocol_version: '1.0',
      } satisfies JsonValue)
      await expect(supervisor.request('task.get_snapshot')).resolves.toEqual({
        tasks: [],
        active_task_count: 0,
        has_committing_task: false,
      })
    } finally {
      await supervisor.stop()
    }

    expect(supervisor.getStatus().phase).toBe('stopped')
  }, TEST_TIMEOUT_MS)
})
