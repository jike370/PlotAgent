import { useState } from 'react'
import { CircleCheck, Clock3, LoaderCircle, TriangleAlert, X } from 'lucide-react'

import type { TaskEvent } from '../../../shared/desktop-contract'
import { useDialogFocus } from './useDialogFocus'

interface TaskDrawerProps {
  tasks: TaskEvent[]
  onCancel: (taskId: string) => void
  onClose: () => void
}

const terminalStates = new Set(['succeeded', 'failed', 'cancelled', 'partially_succeeded', 'interrupted'])

export function TaskDrawer({ tasks, onCancel, onClose }: TaskDrawerProps): React.JSX.Element {
  const [view, setView] = useState<'active' | 'all'>('active')
  const dialogRef = useDialogFocus<HTMLElement>()
  const activeCount = tasks.filter((task) => !terminalStates.has(task.state)).length
  const shownTasks = view === 'active' ? tasks.filter((task) => !terminalStates.has(task.state)) : tasks
  return (
    <div className="drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <aside ref={dialogRef} className="task-drawer" role="dialog" aria-modal="true" aria-labelledby="task-title" tabIndex={-1}>
        <header><h2 id="task-title">任务中心</h2><button className="icon-button" type="button" onClick={onClose} aria-label="关闭任务中心"><X size={18} /></button></header>
        <div className="task-tabs" aria-label="任务范围"><button data-autofocus className={view === 'active' ? 'is-active' : ''} type="button" aria-pressed={view === 'active'} onClick={() => setView('active')}>进行中 {activeCount}</button><button className={view === 'all' ? 'is-active' : ''} type="button" aria-pressed={view === 'all'} onClick={() => setView('all')}>全部 {tasks.length}</button></div>
        <div className="task-list">
          {shownTasks.length === 0 ? (
            <div className="task-empty"><Clock3 size={20} /><strong>{view === 'active' ? '当前没有进行中的任务' : '还没有任务记录'}</strong></div>
          ) : [...shownTasks].sort((a, b) => b.sequence - a.sequence).map((task) => {
            const terminal = terminalStates.has(task.state)
            const failed = ['failed', 'interrupted', 'partially_succeeded'].includes(task.state)
            const progress = task.progress?.total
              ? Math.round(task.progress.completed / task.progress.total * 100)
              : undefined
            const Icon = failed ? TriangleAlert : terminal ? CircleCheck : task.state === 'queued' ? Clock3 : LoaderCircle
            return (
              <article className={`task-item task-item--${failed ? 'warning' : terminal ? 'success' : task.state === 'queued' ? 'queued' : 'running'}`} key={task.taskId}>
                <div className="task-item__icon"><Icon className={!terminal && task.state !== 'queued' ? 'spin' : undefined} size={17} /></div>
                <div className="task-item__content">
                  <header><strong>{task.taskId}</strong><span>{progress === undefined ? task.state : `${progress}%`}</span></header>
                  <p>状态 {task.state} · 事件序号 {task.sequence}</p>
                  {progress !== undefined && <div className="task-progress" aria-label={`进度 ${progress}%`}><span style={{ width: `${progress}%` }} /></div>}
                </div>
                {!terminal && <button type="button" onClick={() => onCancel(task.taskId)} aria-label={`取消任务 ${task.taskId}`}><X size={15} /></button>}
              </article>
            )
          })}
        </div>
      </aside>
    </div>
  )
}
