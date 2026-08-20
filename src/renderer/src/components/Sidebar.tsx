import { createPortal } from 'react-dom'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  CircleCheck,
  FileChartColumn,
  FlaskConical,
  FolderKanban,
  LoaderCircle,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
  SlidersHorizontal,
  Trash2,
  TriangleAlert,
  X,
} from 'lucide-react'

import type { CoreStatus } from '../../../shared/desktop-contract'
import type { ProductProject } from '../data/productState'

interface SidebarProps {
  projects: ProductProject[]
  activeProjectId?: string
  core: CoreStatus
  agentConfigured: boolean
  taskCount: number
  originStatus: 'unknown' | 'checking' | 'available' | 'unavailable' | 'exporting'
  busyAction?: string
  previewMode?: boolean
  onProjectChange: (projectId: string) => void
  onNewProject: () => void
  onRenameProject: (projectId: string, name: string) => Promise<boolean>
  onDeleteProject: (projectId: string) => Promise<boolean>
  onTaskCenter: () => void
  onConfigureAgent: () => void
  onRefreshOrigin: () => void
}

interface ProjectOverlay {
  projectId: string
  top: number
  left: number
}

const PINNED_PROJECTS_KEY = 'plotagent.sidebar.pinned-projects'

function initialPinnedProjects(): string[] {
  try {
    const value = JSON.parse(window.localStorage.getItem(PINNED_PROJECTS_KEY) ?? '[]')
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

function lastOpenedLabel(value: string | undefined): string {
  if (!value) return '本机项目'
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) return '本机项目'
  return `最近使用 ${new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(date)}`
}

const originLabels = {
  unknown: ['Origin 尚未检测', '重新检测'],
  checking: ['正在检测 Origin', '请稍候'],
  available: ['Origin 可用', '重新检测'],
  unavailable: ['Origin 不可用', '重新检测'],
  exporting: ['正在调用 Origin', '请勿关闭应用'],
} as const

export function Sidebar({
  projects,
  activeProjectId,
  core,
  agentConfigured,
  taskCount,
  originStatus,
  busyAction,
  previewMode = false,
  onProjectChange,
  onNewProject,
  onRenameProject,
  onDeleteProject,
  onTaskCenter,
  onConfigureAgent,
  onRefreshOrigin,
}: SidebarProps): React.JSX.Element {
  const [query, setQuery] = useState('')
  const [pinnedProjectIds, setPinnedProjectIds] = useState(initialPinnedProjects)
  const [menu, setMenu] = useState<ProjectOverlay>()
  const [hoverInfo, setHoverInfo] = useState<ProjectOverlay>()
  const [renaming, setRenaming] = useState<{ projectId: string; name: string }>()
  const hoverTimer = useRef<number | undefined>(undefined)
  const origin = originLabels[originStatus]
  const visibleProjects = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('zh-CN')
    const filtered = normalizedQuery
      ? projects.filter((project) => project.name.toLocaleLowerCase('zh-CN').includes(normalizedQuery))
      : projects
    const pinned = new Set(pinnedProjectIds)
    return [...filtered].sort((left, right) => Number(pinned.has(right.projectId)) - Number(pinned.has(left.projectId)))
  }, [pinnedProjectIds, projects, query])
  const OriginIcon = originStatus === 'available'
    ? CircleCheck
    : originStatus === 'checking' || originStatus === 'exporting' ? LoaderCircle : TriangleAlert
  const originActionLabel = originStatus === 'checking' || originStatus === 'exporting'
    ? origin[0]
    : `${origin[0]}，重新检测`
  const menuProject = menu ? projects.find((item) => item.projectId === menu.projectId) : undefined
  const hoverProject = hoverInfo ? projects.find((item) => item.projectId === hoverInfo.projectId) : undefined

  useEffect(() => {
    try {
      window.localStorage.setItem(PINNED_PROJECTS_KEY, JSON.stringify(pinnedProjectIds))
    } catch {
      // A blocked preference store must not block project navigation.
    }
  }, [pinnedProjectIds])

  useEffect(() => {
    if (!menu) return
    const closeOnOutsidePointer = (event: PointerEvent): void => {
      const target = event.target instanceof Element ? event.target : undefined
      if (!target?.closest('[data-project-menu], [data-project-menu-trigger]')) setMenu(undefined)
    }
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') setMenu(undefined)
    }
    window.addEventListener('pointerdown', closeOnOutsidePointer)
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      window.removeEventListener('pointerdown', closeOnOutsidePointer)
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [menu])

  const clearHover = (): void => {
    if (hoverTimer.current !== undefined) window.clearTimeout(hoverTimer.current)
    hoverTimer.current = undefined
    setHoverInfo(undefined)
  }

  const beginHover = (projectId: string, element: HTMLElement): void => {
    clearHover()
    const bounds = element.getBoundingClientRect()
    hoverTimer.current = window.setTimeout(() => {
      setHoverInfo({
        projectId,
        top: Math.max(8, Math.min(bounds.top, window.innerHeight - 68)),
        left: Math.max(8, Math.min(bounds.right + 8, window.innerWidth - 246)),
      })
    }, 350)
  }

  const togglePinned = (projectId: string): void => {
    setPinnedProjectIds((current) => current.includes(projectId)
      ? current.filter((item) => item !== projectId)
      : [projectId, ...current])
    setMenu(undefined)
  }

  const commitRename = async (): Promise<void> => {
    if (!renaming) return
    const nextName = renaming.name.trim()
    const current = projects.find((item) => item.projectId === renaming.projectId)
    if (!nextName || nextName === current?.name) {
      setRenaming(undefined)
      return
    }
    if (await onRenameProject(renaming.projectId, nextName)) setRenaming(undefined)
  }

  const confirmDelete = async (project: ProductProject): Promise<void> => {
    setMenu(undefined)
    const confirmed = window.confirm(`删除“${project.name}”？\n\n项目及其本机数据将被永久删除，此操作无法撤销。`)
    if (!confirmed) return
    if (await onDeleteProject(project.projectId)) {
      setPinnedProjectIds((current) => current.filter((item) => item !== project.projectId))
    }
  }

  return (
    <aside className="sidebar" aria-label="项目与对话">
      <div className="sidebar__brand">
        <span className="brand-mark" aria-hidden="true"><FlaskConical size={17} strokeWidth={1.9} /></span>
        <span className="brand-wordmark"><strong>PlotAgent</strong><small>AI 绘图引擎</small></span>
        <span className="prototype-badge">内测</span>
      </div>

      <div className="sidebar__actions">
        <button className="new-conversation" type="button" onClick={onNewProject} disabled={core.phase !== 'ready' || busyAction !== undefined}>
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
          <div
            className={`project-group${project.projectId === activeProjectId ? ' project-group--active' : ''}`}
            key={project.projectId}
            onMouseEnter={(event) => beginHover(project.projectId, event.currentTarget)}
            onMouseLeave={clearHover}
          >
            {renaming?.projectId === project.projectId ? (
              <form className="project-rename" onSubmit={(event) => { event.preventDefault(); void commitRename() }}>
                <FolderKanban size={16} aria-hidden="true" />
                <input
                  autoFocus
                  aria-label={`重命名项目 ${project.name}`}
                  value={renaming.name}
                  maxLength={120}
                  onChange={(event) => setRenaming({ ...renaming, name: event.target.value })}
                  onBlur={() => void commitRename()}
                  onKeyDown={(event) => { if (event.key === 'Escape') { event.preventDefault(); setRenaming(undefined) } }}
                />
              </form>
            ) : (
              <>
                <button
                  className="project-row"
                  type="button"
                  onClick={() => onProjectChange(project.projectId)}
                  aria-current={project.projectId === activeProjectId ? 'page' : undefined}
                  aria-describedby={hoverInfo?.projectId === project.projectId ? `project-info-${project.projectId}` : undefined}
                >
                  <FolderKanban size={16} aria-hidden="true" />
                  <span>{project.name}</span>
                </button>
                <button
                  className="project-more"
                  type="button"
                  data-project-menu-trigger
                  disabled={busyAction !== undefined}
                  aria-label={`项目“${project.name}”操作`}
                  aria-expanded={menu?.projectId === project.projectId}
                  onClick={(event) => {
                    clearHover()
                    const bounds = event.currentTarget.getBoundingClientRect()
                    setMenu({
                      projectId: project.projectId,
                      top: Math.max(8, Math.min(bounds.bottom + 4, window.innerHeight - 142)),
                      left: Math.max(8, Math.min(bounds.left, window.innerWidth - 204)),
                    })
                  }}
                >
                  <MoreHorizontal size={16} aria-hidden="true" />
                </button>
              </>
            )}
          </div>
        ))}
      </nav>

      {hoverProject && hoverInfo && createPortal(
        <div className="project-info-popover" id={`project-info-${hoverProject.projectId}`} role="tooltip" style={{ top: hoverInfo.top, left: hoverInfo.left }}>
          <strong>{hoverProject.name}</strong>
          <span>{`${hoverProject.projectId === activeProjectId ? '当前项目 · ' : ''}v${hoverProject.projectVersion} · ${lastOpenedLabel(hoverProject.lastOpenedAt)}`}</span>
        </div>,
        document.body,
      )}

      {menuProject && menu && createPortal(
        <div className="project-menu" data-project-menu role="menu" aria-label={`${menuProject.name}项目菜单`} style={{ top: menu.top, left: menu.left }}>
          <div className="project-menu__title"><FolderKanban size={15} aria-hidden="true" /><strong>{menuProject.name}</strong></div>
          <button type="button" role="menuitem" onClick={() => togglePinned(menuProject.projectId)}>
            {pinnedProjectIds.includes(menuProject.projectId) ? <PinOff size={15} /> : <Pin size={15} />}
            {pinnedProjectIds.includes(menuProject.projectId) ? '取消置顶' : '置顶项目'}
          </button>
          <button type="button" role="menuitem" onClick={() => { setRenaming({ projectId: menuProject.projectId, name: menuProject.name }); setMenu(undefined) }}>
            <Pencil size={15} />重命名
          </button>
          <button className="project-menu__danger" type="button" role="menuitem" onClick={() => void confirmDelete(menuProject)}>
            <Trash2 size={15} />删除项目
          </button>
        </div>,
        document.body,
      )}

      <div className="sidebar__footer">
        <button type="button" onClick={onTaskCenter}>
          <Activity size={16} aria-hidden="true" />
          <span>任务中心</span><span className="task-count">{taskCount}</span>
        </button>
        <div className="core-row" role="status">
          <FileChartColumn size={16} aria-hidden="true" />
          <span>本地 Core</span>
          <span className="footer-meta">{core.phase === 'ready' ? '已连接' : '未连接'}</span>
        </div>
        <button type="button" onClick={onConfigureAgent} aria-label={`模型服务 ${agentConfigured ? '已配置' : '未配置'}`}>
          <SlidersHorizontal size={16} aria-hidden="true" />
          <span>模型服务</span>
          <span className="footer-meta">{agentConfigured ? '已配置' : '未配置'}</span>
        </button>
        <button className={`origin-row origin-row--${originStatus}`} type="button" onClick={onRefreshOrigin} disabled={originStatus === 'checking' || originStatus === 'exporting'} aria-label={originActionLabel}>
          <OriginIcon className={originStatus === 'checking' || originStatus === 'exporting' ? 'spin' : undefined} size={16} aria-hidden="true" />
          <span>{origin[0]}</span><span className="footer-meta">{origin[1]}</span>
        </button>
        <div className="build-row"><span>{previewMode ? '界面预览' : '本地单实例'}</span><span className="footer-meta">{previewMode ? '内存示例' : '0.1.0 内测'}</span></div>
      </div>
    </aside>
  )
}
