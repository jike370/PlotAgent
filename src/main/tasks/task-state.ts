import type {
  TaskEvent,
  TaskSnapshot,
  TaskState,
  TaskSummary,
} from '../../shared/desktop-contract.js'

const TERMINAL_STATES = new Set<TaskState>([
  'succeeded',
  'cancelled',
  'failed',
  'partially_succeeded',
  'interrupted',
])

const CANCELLABLE_STATES = new Set<TaskState>(['queued', 'preparing', 'running'])

const ALLOWED_TRANSITIONS: Readonly<Record<TaskState, ReadonlySet<TaskState>>> = {
  queued: new Set(['preparing', 'cancelling', 'interrupted']),
  preparing: new Set(['running', 'cancelling', 'failed', 'interrupted']),
  running: new Set(['committing', 'cancelling', 'failed', 'interrupted']),
  committing: new Set(['succeeded', 'failed', 'partially_succeeded', 'interrupted']),
  cancelling: new Set(['cancelled', 'committing', 'interrupted']),
  succeeded: new Set(),
  cancelled: new Set(),
  failed: new Set(),
  partially_succeeded: new Set(),
  interrupted: new Set(),
}

export function isActiveTaskState(state: TaskState): boolean {
  return !TERMINAL_STATES.has(state)
}

export function isTaskCancellable(state: TaskState): boolean {
  return CANCELLABLE_STATES.has(state)
}

export function isLegalTaskTransition(previous: TaskState, next: TaskState): boolean {
  return previous === next || ALLOWED_TRANSITIONS[previous].has(next)
}

export function applyTaskEvent(
  previous: TaskSummary | undefined,
  event: TaskEvent,
): TaskSummary | null {
  if (previous === undefined) {
    if (event.state !== 'queued' && event.state !== 'interrupted') return null
  } else {
    if (event.sequence <= previous.sequence || !isLegalTaskTransition(previous.state, event.state)) {
      return null
    }
  }

  return {
    taskId: event.taskId,
    sequence: event.sequence,
    state: event.state,
    cancellable: isTaskCancellable(event.state),
    ...(event.taskKind === undefined
      ? previous?.taskKind === undefined ? {} : { taskKind: previous.taskKind }
      : { taskKind: event.taskKind }),
    ...(event.label === undefined
      ? previous?.label === undefined ? {} : { label: previous.label }
      : { label: event.label }),
    ...(event.progress === undefined ? {} : { progress: event.progress }),
    ...(event.error === undefined ? {} : { error: event.error }),
  }
}

export class TaskTracker {
  private readonly tasks = new Map<string, TaskSummary>()
  private readonly listeners = new Set<(snapshot: TaskSnapshot) => void>()

  apply(event: TaskEvent): boolean {
    const next = applyTaskEvent(this.tasks.get(event.taskId), event)
    if (next === null) return false
    this.tasks.set(event.taskId, next)
    this.emit()
    return true
  }

  get(taskId: string): TaskSummary | undefined {
    return this.tasks.get(taskId)
  }

  snapshot(): TaskSnapshot {
    const tasks = [...this.tasks.values()].sort((left, right) =>
      left.taskId.localeCompare(right.taskId),
    )
    return {
      tasks,
      activeTaskCount: tasks.filter((task) => isActiveTaskState(task.state)).length,
      hasCommittingTask: tasks.some((task) => task.state === 'committing'),
    }
  }

  subscribe(listener: (snapshot: TaskSnapshot) => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private emit(): void {
    const snapshot = this.snapshot()
    for (const listener of this.listeners) listener(snapshot)
  }
}
