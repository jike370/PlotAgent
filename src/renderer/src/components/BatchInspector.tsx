import { useMemo, useState } from 'react'
import {
  ArrowLeft,
  CircleCheck,
  Clock3,
  ListFilter,
  LoaderCircle,
  Search,
  TriangleAlert,
  XCircle,
} from 'lucide-react'

import type { BatchView } from './ConversationWorkspace'
import '../batchInspector.css'

interface BatchInspectorProps {
  batch: BatchView
  onClose: () => void
}

type BatchStateGroup = 'all' | 'succeeded' | 'running' | 'failed'

function stateGroup(state: string): Exclude<BatchStateGroup, 'all'> {
  const normalized = state.toLocaleLowerCase('en-US')
  if (['succeeded', 'success', 'completed', 'complete'].includes(normalized)) return 'succeeded'
  if (['failed', 'failure', 'rejected', 'cancelled', 'canceled'].includes(normalized)) return 'failed'
  return 'running'
}

const stateCopy: Record<Exclude<BatchStateGroup, 'all'>, string> = {
  succeeded: '已完成',
  running: '处理中',
  failed: '失败',
}

function StateIcon({ state }: { state: Exclude<BatchStateGroup, 'all'> }): React.JSX.Element {
  if (state === 'succeeded') return <CircleCheck size={16} />
  if (state === 'failed') return <XCircle size={16} />
  return <LoaderCircle className="spin" size={16} />
}

export function BatchInspector({ batch, onClose }: BatchInspectorProps): React.JSX.Element {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<BatchStateGroup>('all')
  const counts = useMemo(() => batch.items.reduce((current, item) => {
    current[stateGroup(item.state)] += 1
    return current
  }, { succeeded: 0, running: 0, failed: 0 }), [batch.items])
  const visibleItems = useMemo(() => batch.items.filter((item) => {
    const group = stateGroup(item.state)
    return (filter === 'all' || filter === group)
      && (query.trim() === '' || item.id.toLocaleLowerCase('en-US').includes(query.trim().toLocaleLowerCase('en-US')))
  }), [batch.items, filter, query])

  return (
    <main className="batch-inspector" aria-labelledby="batch-inspector-title">
      <header className="batch-inspector__header">
        <button className="back-button" type="button" onClick={onClose}><ArrowLeft size={16} />返回对话</button>
        <div className="batch-inspector__title">
          <span>批次 {batch.batchId} · 版本 {batch.version}</span>
          <h1 id="batch-inspector-title">批次执行检查</h1>
        </div>
        <div className="batch-inspector__summary" aria-label="批次状态摘要">
          <span><strong>{batch.items.length}</strong> 项</span>
          <span className="is-success"><strong>{counts.succeeded}</strong> 完成</span>
          <span className="is-warning"><strong>{counts.running}</strong> 处理中</span>
          <span className="is-danger"><strong>{counts.failed}</strong> 失败</span>
        </div>
      </header>

      <section className="batch-inspector__identity" aria-label="批次身份">
        <div><span>任务</span><strong>{batch.taskId}</strong></div>
        <div><span>批次状态</span><strong>{batch.state}</strong></div>
        <p>这里仅展示 Core 返回的真实执行结果。每项沿用创建批次时已确认的同一份字段映射。</p>
      </section>

      <div className="batch-inspector__filters">
        <label className="batch-search">
          <Search size={15} />
          <span className="sr-only">搜索批次项</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索批次项 ID" />
        </label>
        <label className="batch-filter-select">
          <ListFilter size={14} />
          <span>状态</span>
          <select aria-label="按状态筛选" value={filter} onChange={(event) => setFilter(event.target.value as BatchStateGroup)}>
            <option value="all">全部</option>
            <option value="succeeded">已完成</option>
            <option value="running">处理中</option>
            <option value="failed">失败</option>
          </select>
        </label>
        <span className="batch-inspector__visible-count">显示 {visibleItems.length} / {batch.items.length}</span>
      </div>

      {batch.items.length === 0 ? (
        <section className="batch-inspector__empty">
          <Clock3 size={24} />
          <h2>批次尚未返回执行项</h2>
          <p>任务状态为“{batch.state}”。进度事件会继续显示在任务中心。</p>
        </section>
      ) : visibleItems.length === 0 ? (
        <section className="batch-inspector__empty">
          <Search size={24} />
          <h2>没有匹配的批次项</h2>
          <p>清除搜索词或切换状态筛选。</p>
          <button type="button" onClick={() => { setQuery(''); setFilter('all') }}>清除筛选</button>
        </section>
      ) : (
        <section className="batch-result-list" aria-label="批次执行结果">
          {visibleItems.map((item, index) => {
            const group = stateGroup(item.state)
            return (
              <article className={`batch-result-item batch-result-item--${group}`} key={`${item.id}:${index}`}>
                <span className="batch-result-item__index">{String(index + 1).padStart(2, '0')}</span>
                <span className="batch-result-item__icon"><StateIcon state={group} /></span>
                <div><strong>{item.id}</strong><span>Core 状态：{item.state}</span></div>
                <span className={`batch-check-status batch-check-status--${group}`}>
                  {group === 'failed' && <TriangleAlert size={12} />}{stateCopy[group]}
                </span>
              </article>
            )
          })}
        </section>
      )}
    </main>
  )
}
