import { useMemo, useState } from 'react'
import {
  Activity,
  CircleCheck,
  FileChartColumn,
  FlaskConical,
  FolderKanban,
  MessageSquare,
  Plus,
  Search,
  SlidersHorizontal,
  TriangleAlert,
  X,
} from 'lucide-react'

import type { CoreStatus } from '../../../shared/desktop-contract'
import type { ProductProject } from '../data/productState'

interface SidebarProps {
  projects: ProductProject[]
  activeProjectId?: string
  core: CoreStatus
  taskCount: number
  originStatus: 'unknown' | 'available' | 'unavailable' | 'exporting'
  onProjectChange: (projectId: string) => void
  onNewProject: () => void
  onTaskCenter: () => void
  onConfigureAgent: () => void
}

const originLabels = {
  unknown: ['Origin 尚未检测', '导出 OPJU 时检测'],
  available: ['Origin 可用', '支持 OPJU'],
  unavailable: ['Origin 不可用', '仅影响 OPJU'],
  exporting: ['正在调用 Origin', '请勿关闭应用'],
} as const

export function Sidebar({
  projects,
  activeProjectId,
  core,
  taskCount,
  originStatus,
  onProjectChange,
  onNewProject,
  onTaskCenter,
  onConfigureAgent,
}: SidebarProps): React.JSX.Element {
  const [query, setQuery] = useState('')
  const origin = originLabels[originStatus]
  const visibleProjects = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('zh-CN')
    if (!normalizedQuery) return projects
    return projects.filter((project) => `${project.name} ${project.projectId}`.toLocaleLowerCase('zh-CN').includes(normalizedQuery))
  }, [projects, query])
  const OriginIcon = originStatus === 'available' ? CircleCheck : originStatus === 'exporting' ? FileChartColumn : TriangleAlert

  return (
    <aside className="sidebar" aria-label="项目与对话">
      <div className="sidebar__brand">
        <span className="brand-mark" aria-hidden="true"><FlaskConical size={17} strokeWidth={1.9} /></span>
        <span>PlotAgent</span>
        <span className="prototype-badge">内测</span>
      </div>

      <div className="sidebar__actions">
        <button className="new-conversation" type="button" onClick={onNewProject}>
          <Plus size={16} aria-hidden="true" />新建项目<kbd>Ctrl N</kbd>
        </button>
        <label className="sidebar-search">
          <Search size={15} aria-hidden="true" />
          <span className="sr-only">搜索本机项目</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索本机项目" />
          {query && <button type="button" onClick={() => setQuery('')} aria-label="清除项目搜索"><X size={14} /></button>}
        </label>
      </div>

      <nav className="project-nav" aria-label="本机项目">
        <div className="section-label">本机项目</div>
        {projects.length === 0 ? (
          <div className="sidebar-startup-empty">
            <FolderKanban size={20} aria-hidden="true" />
            <strong>还没有本机项目</strong>
          </div>
        ) : visibleProjects.length === 0 ? (
          <div className="sidebar-search-empty" role="status">
            <Search size={18} aria-hidden="true" />
            <span>没有匹配的本机项目</span>
          </div>
        ) : visibleProjects.map((project) => (
          <section className={`project-group${project.projectId === activeProjectId ? ' project-group--active' : ''}`} key={project.projectId}>
            <button
              className="project-row"
              type="button"
              onClick={() => onProjectChange(project.projectId)}
              aria-current={project.projectId === activeProjectId ? 'page' : undefined}
            >
              <FolderKanban size={16} aria-hidden="true" />
              <span>{project.name}</span>
              {project.isOpen && <span className="project-count" aria-label="已打开">●</span>}
            </button>
            {project.projectId === activeProjectId && (
              <div className="conversation-list">
                <div className="conversation-row is-active" aria-current="page">
                  <MessageSquare size={14} aria-hidden="true" />
                  <span>绘图对话</span><time>当前</time>
                </div>
              </div>
            )}
          </section>
        ))}
      </nav>

      <div className="sidebar__footer">
        <button type="button" onClick={onTaskCenter}>
          <Activity size={16} aria-hidden="true" />
          <span>任务中心</span><span className="task-count">{taskCount}</span>
        </button>
        <button type="button" onClick={onConfigureAgent}>
          <SlidersHorizontal size={16} aria-hidden="true" />
          <span>Agent 服务</span>
          <span className={`status-dot status-dot--${core.phase === 'ready' ? 'online' : 'offline'}`} aria-label={core.phase === 'ready' ? 'Core 已连接' : 'Core 未连接'} />
        </button>
        <div className={`origin-row origin-row--${originStatus}`} role="status">
          <OriginIcon className={originStatus === 'exporting' ? 'spin' : undefined} size={16} aria-hidden="true" />
          <span>{origin[0]}</span><span className="footer-meta">{origin[1]}</span>
        </div>
        <div className="build-row"><span>本地单实例</span><span className="footer-meta">0.1.0 内测</span></div>
      </div>
    </aside>
  )
}
