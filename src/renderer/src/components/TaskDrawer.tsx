import { useState } from 'react'
import {
  CircleCheck,
  Clock3,
  LoaderCircle,
  RotateCcw,
  TriangleAlert,
  X,
} from 'lucide-react'

import type { TaskEvent, WorkflowRuntimeEvent } from '../../../shared/desktop-contract'
import type { DurableTaskView, WorkflowPlanView } from '../data/productState'
import { useDialogFocus } from './useDialogFocus'

interface TaskDrawerProps {
  tasks: TaskEvent[]
  durableTasks: DurableTaskView[]
  plans: WorkflowPlanView[]
  runtimeEvent?: WorkflowRuntimeEvent
  onCancel: (taskId: string) => void
  onAcceptPartial: (taskId: string) => void
  onResumeTask: (taskId: string) => void
  onRetryPlan: (planId: string) => void
  onClose: () => void
}

const legacyTerminalStates = new Set([
  'succeeded', 'failed', 'cancelled', 'partially_succeeded', 'interrupted',
])
const durableTerminalStates = new Set([
  'completed_verified', 'cancelled', 'rejected', 'failed', 'unsupported',
])
const durableActiveStates = new Set([
  'created', 'investigating', 'executing', 'verifying', 'repairing', 'delivering', 'cancelling',
])

const legacyStateLabels: Readonly<Record<TaskEvent['state'], string>> = {
  queued: '排队中',
  preparing: '准备中',
  running: '处理中',
  committing: '保存中',
  cancelling: '正在取消',
  succeeded: '已完成',
  cancelled: '已取消',
  failed: '失败',
  partially_succeeded: '部分完成',
  interrupted: '已中断',
}

const durableStateLabels: Readonly<Record<string, string>> = {
  created: '准备检查数据',
  investigating: '检查数据与字段',
  awaiting_input: '等待你的回复',
  intent_staged: '正在生成确认内容',
  awaiting_confirmation: '等待确认',
  awaiting_reconfirmation: '等待重新确认',
  executing: '调用绘图引擎',
  verifying: '验证图形结果',
  repairing: '修复失败项',
  delivering: '整理结果',
  partial: '部分完成',
  blocked: '等待外部条件',
  unsupported: '当前不支持',
  cancelling: '完成当前步骤后停止',
  cancelled: '已取消',
  rejected: '已拒绝',
  failed: '失败',
  completed_verified: '已完成并验证',
}

const failureCategoryLabels: Readonly<Record<string, string>> = {
  transient_external: '临时外部故障',
  deterministic_technical: '确定性技术错误',
  semantic_conflict: '语义冲突',
  stale_or_concurrent: '版本或并发冲突',
  unsupported: '能力不支持',
  safety_or_permission: '权限或安全限制',
  budget: '预算限制',
  runtime: 'Agent 运行错误',
}

function sideEffectLabel(value?: string): string {
  if (value === 'known_none') return '项目未发生更改'
  if (value === 'known_applied') return '项目已保留已提交更改'
  return '项目变化待核验'
}

function updateLabel(value?: string): string | undefined {
  if (!value) return undefined
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return undefined
  return `更新于 ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
}

export function TaskDrawer({
  tasks,
  durableTasks,
  plans,
  runtimeEvent,
  onCancel,
  onAcceptPartial,
  onResumeTask,
  onRetryPlan,
  onClose,
}: TaskDrawerProps): React.JSX.Element {
  const [view, setView] = useState<'active' | 'all'>('active')
  const dialogRef = useDialogFocus<HTMLElement>()
  const planByTask = new Map(plans.flatMap((plan) => (
    plan.taskId === undefined ? [] : [[plan.taskId, plan] as const]
  )))
  const shownDurable = durableTasks.filter((task) => (
    view === 'all' || !durableTerminalStates.has(task.state)
  ))
  const durableIds = new Set(durableTasks.map((task) => task.taskId))
  const shownLegacy = tasks.filter((task) => (
    !durableIds.has(task.taskId)
    && (view === 'all' || !legacyTerminalStates.has(task.state))
  ))
  const runtimeTerminal = runtimeEvent === undefined
    || ['completed', 'cancelled', 'failed'].includes(runtimeEvent.stage)
  const showRuntime = !runtimeTerminal
    && runtimeEvent.taskId !== undefined
    && !durableIds.has(runtimeEvent.taskId)
    && !tasks.some((task) => task.taskId === runtimeEvent.taskId)
  const activeCount = durableTasks.filter((task) => !durableTerminalStates.has(task.state)).length
    + tasks.filter((task) => !durableIds.has(task.taskId) && !legacyTerminalStates.has(task.state)).length
    + (showRuntime ? 1 : 0)
  const totalCount = durableTasks.length + tasks.filter((task) => !durableIds.has(task.taskId)).length
    + (showRuntime ? 1 : 0)

  return (
    <div className="drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <aside ref={dialogRef} className="task-drawer" role="dialog" aria-modal="true" aria-labelledby="task-title" tabIndex={-1}>
        <header>
          <div><h2 id="task-title">任务中心</h2></div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭任务中心"><X size={18} /></button>
        </header>
        <div className="task-tabs" aria-label="任务范围">
          <button data-autofocus className={view === 'active' ? 'is-active' : ''} type="button" aria-pressed={view === 'active'} onClick={() => setView('active')}>进行中 {activeCount}</button>
          <button className={view === 'all' ? 'is-active' : ''} type="button" aria-pressed={view === 'all'} onClick={() => setView('all')}>全部 {totalCount}</button>
        </div>
        <div className="task-list">
          {shownDurable.length === 0 && shownLegacy.length === 0 && !showRuntime ? (
            <div className="task-empty"><Clock3 size={20} /><strong>{view === 'active' ? '当前没有进行中的任务' : '还没有任务记录'}</strong></div>
          ) : null}
          {showRuntime && runtimeEvent.taskId && <article className="task-item task-item--running" key={runtimeEvent.taskId}>
            <div className="task-item__icon"><LoaderCircle className="spin" size={17} /></div>
            <div className="task-item__content">
              <header><strong>Agent 绘图任务</strong><span>{runtimeEvent.label}</span></header>
              <div className="task-item__actions"><button type="button" onClick={() => onCancel(runtimeEvent.taskId as string)}><X size={14} />停止任务</button></div>
            </div>
          </article>}
          {[...shownDurable].sort((a, b) => (b.updatedAt ?? '').localeCompare(a.updatedAt ?? '')).map((task) => {
            const terminal = durableTerminalStates.has(task.state)
            const warning = task.state === 'partial' || task.state === 'blocked' || task.state === 'failed'
            const completedSuccessfully = task.state === 'completed_verified'
            const plan = planByTask.get(task.taskId)
            const completed = task.items.filter((item) => item.state === 'succeeded').length
            const skipped = new Set(task.skippedItemIds ?? [])
            const retryable = plan?.resumable === true
            const recoverablePlanning = [
              'created', 'investigating', 'intent_staged', 'repairing', 'blocked',
            ].includes(task.state) && task.activeActivationId === undefined
            const Icon = warning
              ? TriangleAlert
              : completedSuccessfully
                ? CircleCheck
                : durableActiveStates.has(task.state)
                  ? LoaderCircle
                  : Clock3
            const updated = updateLabel(task.updatedAt)
            return (
              <article className={`task-item task-item--${warning ? 'warning' : completedSuccessfully ? 'success' : terminal ? 'neutral' : 'running'}`} key={task.taskId}>
                <div className="task-item__icon"><Icon className={durableActiveStates.has(task.state) ? 'spin' : undefined} size={17} /></div>
                <div className="task-item__content">
                  <header><strong>{plan?.steps.length === 1 ? plan.steps[0]?.title : `${task.items.length || 1} 项绘图任务`}</strong><span>{task.completionOutcome === 'completed_with_skips' ? '已完成（含跳过项）' : durableStateLabels[task.state] ?? task.state}</span></header>
                  <p>{task.items.length > 0
                    ? task.state === 'cancelled' && completed > 0
                      ? `已停止，保留 ${completed} 项成功结果`
                      : task.completionOutcome === 'completed_with_skips'
                        ? `${completed} 项已完成 · ${skipped.size} 项已跳过`
                        : `${completed}/${task.items.length} 项已完成`
                    : 'Agent 正在整理任务目标'}{updated ? ` · ${updated}` : ''}</p>
                  {task.items.map((item) => (
                    <div className={`task-subitem task-subitem--${item.state}`} key={item.itemId}>
                      <span>{plan?.steps.find((step) => step.taskItemId === item.itemId)?.title ?? item.itemId}</span>
                      <small>{item.outputPlot ? `${item.outputPlot.plotId} · v${item.outputPlot.plotVersion}` : skipped.has(item.itemId) ? '已跳过' : durableStateLabels[item.state] ?? item.state}</small>
                      {item.failure && <div role="alert" className="task-subitem__failure">
                        <p>{item.failure.message}</p>
                        <small>下一步：{item.failure.retryable ? '仅重试此失败项' : item.failure.requiresUser ? '修改要求或字段绑定' : '修改后重试，或跳过此项'}</small>
                        <details className="task-failure-details">
                          <summary>技术详情</summary>
                          <small>阶段：绘图引擎执行与验证 · 类别：{failureCategoryLabels[item.failure.category ?? ''] ?? item.failure.category ?? '技术错误'}</small>
                          <small>{sideEffectLabel(item.failure.sideEffectState)}</small>
                          {item.failure.diagnosticId && <small>诊断 {item.failure.diagnosticId}</small>}
                        </details>
                      </div>}
                    </div>
                  ))}
                  {(retryable || (!terminal && task.state !== 'cancelling')) && <div className="task-item__actions">
                    {retryable && plan && <button type="button" onClick={() => onRetryPlan(plan.planId)}><RotateCcw size={14} />仅重试失败项</button>}
                    {recoverablePlanning && <button type="button" onClick={() => onResumeTask(task.taskId)}><RotateCcw size={14} />{task.state === 'blocked' ? '重新检查条件' : '继续任务'}</button>}
                    {task.state === 'partial' && completed > 0 && <button type="button" onClick={() => onAcceptPartial(task.taskId)}><CircleCheck size={14} />保留成功项并结束</button>}
                    {!terminal && task.state !== 'cancelling' && <button type="button" onClick={() => onCancel(task.taskId)}><X size={14} />停止任务</button>}
                  </div>}
                </div>
              </article>
            )
          })}
          {[...shownLegacy].sort((a, b) => b.sequence - a.sequence).map((task) => {
            const terminal = legacyTerminalStates.has(task.state)
            const failed = ['failed', 'interrupted', 'partially_succeeded'].includes(task.state)
            const Icon = failed ? TriangleAlert : terminal ? CircleCheck : task.state === 'queued' ? Clock3 : LoaderCircle
            return (
              <article className={`task-item task-item--${failed ? 'warning' : terminal ? 'success' : task.state === 'queued' ? 'queued' : 'running'}`} key={task.taskId}>
                <div className="task-item__icon"><Icon className={!terminal && task.state !== 'queued' ? 'spin' : undefined} size={17} /></div>
                <div className="task-item__content">
                  <header><strong>{task.label ?? '本地后台任务'}</strong><span>{legacyStateLabels[task.state]}</span></header>
                  <p>{task.error?.message ?? (task.progress?.total ? `${task.progress.completed}/${task.progress.total} ${task.progress.unit}` : legacyStateLabels[task.state])}</p>
                  {task.error && <details className="task-failure-details"><summary>技术详情</summary><small>诊断 {task.error.code}</small></details>}
                </div>
                {!terminal && <button type="button" onClick={() => onCancel(task.taskId)} aria-label={`取消任务 ${task.label ?? task.taskId}`}><X size={15} /></button>}
              </article>
            )
          })}
        </div>
      </aside>
    </div>
  )
}
