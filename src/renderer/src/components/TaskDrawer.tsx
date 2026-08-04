import {
  Check,
  CircleCheck,
  Clock3,
  LoaderCircle,
  Pause,
  Play,
  RotateCcw,
  TriangleAlert,
  X,
} from 'lucide-react'

interface TaskDrawerProps {
  onClose: () => void
}

export function TaskDrawer({ onClose }: TaskDrawerProps): React.JSX.Element {
  return (
    <div className="drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <aside className="task-drawer" role="dialog" aria-modal="true" aria-labelledby="task-title">
        <header><div><h2 id="task-title">任务中心</h2><p>跨项目后台任务</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="关闭任务中心"><X size={18} /></button></header>
        <div className="task-tabs"><button className="is-active" type="button">进行中 2</button><button type="button">已完成</button><button type="button">全部</button></div>
        <div className="task-list">
          <article className="task-item task-item--running">
            <div className="task-item__icon"><LoaderCircle className="spin" size={17} /></div>
            <div className="task-item__content">
              <header><strong>重新渲染 3 张图</strong><span>62%</span></header>
              <p>温度响应实验 · 批次 B-024</p>
              <div className="task-progress"><span style={{ width: '62%' }} /></div>
              <div className="task-stage"><span><Check size={12} />读取</span><span><Check size={12} />校验</span><span className="is-current"><LoaderCircle size={12} />绘制</span><span>导出验证</span></div>
            </div>
            <button type="button" aria-label="暂停任务"><Pause size={15} /></button>
          </article>
          <article className="task-item task-item--queued">
            <div className="task-item__icon"><Clock3 size={17} /></div>
            <div className="task-item__content"><header><strong>导出 3 个 SVG</strong><span>等待中</span></header><p>前序渲染完成后自动开始</p></div>
            <button type="button" aria-label="取消任务"><X size={15} /></button>
          </article>
        </div>
        <div className="task-section-label">最近结果</div>
        <div className="task-list">
          <article className="task-item task-item--warning">
            <div className="task-item__icon"><TriangleAlert size={17} /></div>
            <div className="task-item__content"><header><strong>批量绘图 B-024</strong><span>部分完成</span></header><p>3 张成功，1 张字段类型校验失败</p><button className="inline-task-action" type="button"><RotateCcw size={13} />重试失败项</button></div>
          </article>
          <article className="task-item task-item--success">
            <div className="task-item__icon"><CircleCheck size={17} /></div>
            <div className="task-item__content"><header><strong>导出图集</strong><span>已完成</span></header><p>6 个文件 · 今天 14:41</p><button className="inline-task-action" type="button"><Play size={13} />打开输出目录</button></div>
          </article>
        </div>
        <footer><span>普通绘图可并行，Origin 导出将顺序执行</span><button type="button">清理已完成任务</button></footer>
      </aside>
    </div>
  )
}
