import {
  Activity,
  Beaker,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  FileChartColumn,
  FlaskConical,
  FolderKanban,
  MessageSquare,
  Plus,
  Search,
  Settings,
  SlidersHorizontal,
  TriangleAlert,
} from 'lucide-react'

export type ConversationId = 'batch' | 'dose' | 'empty'

interface SidebarProps {
  activeConversation: ConversationId
  onConversationChange: (id: ConversationId) => void
  onNewConversation: () => void
  onTaskCenter: () => void
  onOpenResources: () => void
}

const conversations = [
  { id: 'batch' as const, label: '温度响应批量绘图', meta: '刚刚' },
  { id: 'dose' as const, label: '剂量反应曲线', meta: '昨天' },
]

export function Sidebar({
  activeConversation,
  onConversationChange,
  onNewConversation,
  onTaskCenter,
  onOpenResources,
}: SidebarProps): React.JSX.Element {
  return (
    <aside className="sidebar" aria-label="项目与对话">
      <div className="sidebar__brand">
        <span className="brand-mark" aria-hidden="true"><FlaskConical size={17} strokeWidth={1.9} /></span>
        <span>PlotAgent</span>
        <span className="prototype-badge">原型</span>
      </div>

      <div className="sidebar__actions">
        <button className="new-conversation" type="button" onClick={onNewConversation}>
          <Plus size={16} aria-hidden="true" />
          新建对话
          <kbd>Ctrl N</kbd>
        </button>
        <label className="sidebar-search">
          <Search size={15} aria-hidden="true" />
          <span className="sr-only">搜索项目与对话</span>
          <input placeholder="搜索项目与对话" />
        </label>
      </div>

      <nav className="project-nav" aria-label="项目列表">
        <div className="section-label">本机项目</div>
        <section className="project-group project-group--active">
          <button className="project-row" type="button" aria-expanded="true" onClick={onOpenResources} aria-label="打开温度响应实验项目资源库">
            <ChevronDown size={15} aria-hidden="true" />
            <FolderKanban size={16} aria-hidden="true" />
            <span>温度响应实验</span>
            <span className="project-count">2</span>
          </button>
          <div className="conversation-list">
            {conversations.map((conversation) => (
              <button
                className={`conversation-row${activeConversation === conversation.id ? ' is-active' : ''}`}
                key={conversation.id}
                type="button"
                onClick={() => onConversationChange(conversation.id)}
                aria-current={activeConversation === conversation.id ? 'page' : undefined}
              >
                <MessageSquare size={14} aria-hidden="true" />
                <span>{conversation.label}</span>
                <time>{conversation.meta}</time>
              </button>
            ))}
          </div>
        </section>

        <section className="project-group">
          <button className="project-row" type="button" aria-expanded="false">
            <ChevronRight size={15} aria-hidden="true" />
            <Beaker size={16} aria-hidden="true" />
            <span>细胞活性筛选</span>
            <span className="project-count">3</span>
          </button>
        </section>
        <section className="project-group">
          <button className="project-row" type="button" aria-expanded="false">
            <ChevronRight size={15} aria-hidden="true" />
            <FileChartColumn size={16} aria-hidden="true" />
            <span>电化学循环测试</span>
            <span className="project-count">1</span>
          </button>
        </section>
      </nav>

      <div className="sidebar__footer">
        <button type="button" onClick={onTaskCenter}>
          <Activity size={16} aria-hidden="true" />
          <span>任务中心</span>
          <span className="task-count">2</span>
        </button>
        <button type="button">
          <SlidersHorizontal size={16} aria-hidden="true" />
          <span>模型设置</span>
          <span className="status-dot status-dot--online" aria-label="已连接" />
        </button>
        <button className="origin-row" type="button">
          <TriangleAlert size={16} aria-hidden="true" />
          <span>Origin 不可用</span>
          <span className="footer-meta">仅禁用 .opju</span>
        </button>
        <button type="button">
          <Settings size={16} aria-hidden="true" />
          <span>应用设置</span>
        </button>
        <button type="button">
          <CircleHelp size={16} aria-hidden="true" />
          <span>帮助与反馈</span>
          <span className="footer-meta">0.1.0</span>
        </button>
      </div>
    </aside>
  )
}
