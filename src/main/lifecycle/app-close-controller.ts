import { randomUUID } from 'node:crypto'

import {
  DESKTOP_API_VERSION,
  type CloseRequest,
  type CloseResponse,
  type DesktopActionResult,
  type TaskSnapshot,
} from '../../shared/desktop-contract.js'

interface PreventableEvent {
  preventDefault(): void
}

export interface AppCloseControllerOptions {
  readonly getTasks: () => TaskSnapshot
  readonly cancelAllTasks: () => Promise<DesktopActionResult>
  readonly stopCore: () => Promise<void>
  readonly emitCloseRequest: (request: CloseRequest) => void
  readonly quit: () => void
}

export class AppCloseController {
  private closeRequest?: CloseRequest
  private cancelAndQuitPending = false
  private shutdownStarted = false
  private shutdownComplete = false

  constructor(private readonly options: AppCloseControllerOptions) {}

  handleWindowClose(event: PreventableEvent): void {
    if (this.shutdownComplete) return
    event.preventDefault()
    if (this.options.getTasks().activeTaskCount > 0) {
      this.requestChoice()
      return
    }
    this.beginShutdown()
  }

  handleBeforeQuit(event: PreventableEvent): void {
    if (this.shutdownComplete) return
    event.preventDefault()
    if (this.options.getTasks().activeTaskCount > 0 && !this.cancelAndQuitPending) {
      this.requestChoice()
      return
    }
    this.beginShutdown()
  }

  async respond(response: CloseResponse): Promise<DesktopActionResult> {
    if (this.closeRequest?.requestId !== response.requestId) {
      return {
        ok: false,
        error: {
          code: 'IPC_INVALID_ARGUMENT',
          message: 'The close request is no longer active.',
          retryable: false,
        },
      }
    }
    this.closeRequest = undefined

    if (response.choice !== 'cancel-and-quit') return { ok: true }

    this.cancelAndQuitPending = true
    const result = await this.options.cancelAllTasks()
    if (!result.ok) {
      this.cancelAndQuitPending = false
      return result
    }
    if (this.options.getTasks().activeTaskCount === 0) this.beginShutdown()
    return { ok: true }
  }

  handleTaskSnapshot(snapshot: TaskSnapshot): void {
    if (this.cancelAndQuitPending && snapshot.activeTaskCount === 0) this.beginShutdown()
  }

  private requestChoice(): void {
    if (this.closeRequest !== undefined) {
      this.options.emitCloseRequest(this.closeRequest)
      return
    }
    const tasks = this.options.getTasks()
    this.closeRequest = {
      schemaVersion: DESKTOP_API_VERSION,
      requestId: `close:${randomUUID()}`,
      activeTaskCount: tasks.activeTaskCount,
      hasCommittingTask: tasks.hasCommittingTask,
    }
    this.options.emitCloseRequest(this.closeRequest)
  }

  private beginShutdown(): void {
    if (this.shutdownStarted) return
    this.shutdownStarted = true
    void this.options.stopCore().finally(() => {
      this.shutdownComplete = true
      this.options.quit()
    })
  }
}
