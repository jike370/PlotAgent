import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Archive,
  ArchiveRestore,
  Check,
  ChevronRight,
  Clock3,
  Columns3,
  Database,
  ExternalLink,
  FileChartColumn,
  FileOutput,
  Files,
  GitBranch,
  History,
  Images,
  LayoutTemplate,
  Link2,
  MessageSquarePlus,
  Pencil,
  Search,
  ShieldAlert,
  Table2,
  Trash2,
  X,
  type LucideIcon,
} from 'lucide-react'

import {
  getResourceById,
  projectResources,
  resourceKindLabels,
  type ProjectResource,
  type ResourceKind,
} from '../data/projectResources'

interface ProjectResourceLibraryProps {
  onClose: () => void
}

type DetailTab = 'overview' | 'versions' | 'lineage'

const resourceKinds = Object.keys(resourceKindLabels) as ResourceKind[]

const resourceKindIcons: Record<ResourceKind, LucideIcon> = {
  'raw-data': Database,
  'derived-data': Table2,
  'plot-batch': Images,
  chart: FileChartColumn,
  composition: Columns3,
  template: LayoutTemplate,
  export: FileOutput,
}

function collectAffectedResources(resource: ProjectResource, resources: ProjectResource[]): ProjectResource[] {
  const affected = new Set<string>()
  const queue = [...resource.referencedBy]

  while (queue.length > 0) {
    const id = queue.shift()
    if (!id || affected.has(id)) continue
    affected.add(id)
    const downstream = getResourceById(resources, id)
    if (downstream) queue.push(...downstream.referencedBy)
  }

  return [...affected]
    .map((id) => getResourceById(resources, id))
    .filter((item): item is ProjectResource => Boolean(item))
}

function ResourceIcon({ kind, size = 17 }: { kind: ResourceKind; size?: number }): React.JSX.Element {
  const Icon = resourceKindIcons[kind]
  return <Icon size={size} aria-hidden="true" />
}

export function ProjectResourceLibrary({ onClose }: ProjectResourceLibraryProps): React.JSX.Element {
  const [resources, setResources] = useState<ProjectResource[]>(() => structuredClone(projectResources))
  const [activeKind, setActiveKind] = useState<ResourceKind>('raw-data')
  const [selectedId, setSelectedId] = useState('RAW-001')
  const [query, setQuery] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [detailTab, setDetailTab] = useState<DetailTab>('overview')
  const [renaming, setRenaming] = useState(false)
  const [draftName, setDraftName] = useState('')
  const [deleteBlocked, setDeleteBlocked] = useState(false)
  const [announcement, setAnnouncement] = useState('')
  const drawerRef = useRef<HTMLElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    searchRef.current?.focus()
    return () => previouslyFocused?.focus()
  }, [])

  useEffect(() => {
    if (!announcement) return undefined
    const timeoutId = window.setTimeout(() => setAnnouncement(''), 3200)
    return () => window.clearTimeout(timeoutId)
  }, [announcement])

  const normalizedQuery = query.trim().toLocaleLowerCase('zh-CN')
  const visibleResources = useMemo(
    () => resources.filter((resource) => {
      const matchesKind = normalizedQuery ? true : resource.kind === activeKind
      const matchesArchive = showArchived || !resource.archived
      const matchesQuery = !normalizedQuery
        || `${resource.name} ${resource.summary} ${resource.id}`.toLocaleLowerCase('zh-CN').includes(normalizedQuery)
      return matchesKind && matchesArchive && matchesQuery
    }),
    [activeKind, normalizedQuery, resources, showArchived],
  )

  const selectedResource = visibleResources.find((resource) => resource.id === selectedId) ?? visibleResources[0]
  const affectedResources = selectedResource ? collectAffectedResources(selectedResource, resources) : []

  const selectKind = (kind: ResourceKind): void => {
    setActiveKind(kind)
    setDetailTab('overview')
    setRenaming(false)
    setDeleteBlocked(false)
    const firstResource = resources.find((resource) => resource.kind === kind && (showArchived || !resource.archived))
    if (firstResource) setSelectedId(firstResource.id)
  }

  const selectResource = (resource: ProjectResource): void => {
    setSelectedId(resource.id)
    setDetailTab('overview')
    setRenaming(false)
    setDeleteBlocked(false)
  }

  const beginRename = (): void => {
    if (!selectedResource) return
    setDraftName(selectedResource.name)
    setRenaming(true)
  }

  const saveRename = (): void => {
    if (!selectedResource || !draftName.trim()) return
    const nextName = draftName.trim()
    setResources((current) => current.map((resource) => resource.id === selectedResource.id ? { ...resource, name: nextName } : resource))
    setRenaming(false)
    setAnnouncement(`已将资源重命名为 ${nextName}`)
  }

  const toggleArchive = (): void => {
    if (!selectedResource) return
    const archived = !selectedResource.archived
    setResources((current) => current.map((resource) => resource.id === selectedResource.id ? { ...resource, archived } : resource))
    if (archived) setShowArchived(true)
    setAnnouncement(archived ? `已归档 ${selectedResource.name}` : `已恢复 ${selectedResource.name}`)
  }

  const requestDelete = (): void => {
    if (!selectedResource) return
    if (affectedResources.length > 0) {
      setDeleteBlocked(true)
      setAnnouncement(`无法删除，${affectedResources.length} 个对象仍引用这份原始数据`)
      return
    }
    setResources((current) => current.filter((resource) => resource.id !== selectedResource.id))
    setAnnouncement(`已删除未被引用的原始数据 ${selectedResource.name}`)
  }

  const onDrawerKeyDown = (event: React.KeyboardEvent<HTMLElement>): void => {
    if (event.key !== 'Tab' || !drawerRef.current) return
    const focusable = [...drawerRef.current.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), [tabindex="0"]')]
    const first = focusable[0]
    const last = focusable.at(-1)
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last?.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first?.focus()
    }
  }

  return (
    <div
      className="drawer-backdrop resource-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <section
        className="resource-library"
        role="dialog"
        aria-modal="true"
        aria-labelledby="resource-library-title"
        ref={drawerRef}
        onKeyDown={onDrawerKeyDown}
      >
        <header className="resource-library__header">
          <div>
            <span>温度响应实验</span>
            <h2 id="resource-library-title">项目资源库</h2>
          </div>
          <p>{resources.length} 个资源，关系与版本保存在本机项目中</p>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭项目资源库"><X size={19} /></button>
        </header>

        <div className="resource-toolbar">
          <label className="resource-search">
            <Search size={16} aria-hidden="true" />
            <span className="sr-only">搜索项目资源</span>
            <input
              ref={searchRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索名称、说明或资源编号"
            />
          </label>
          <label className="resource-archive-filter">
            <input type="checkbox" checked={showArchived} onChange={(event) => setShowArchived(event.target.checked)} />
            显示已归档
          </label>
        </div>

        <div className="resource-kind-tabs" role="tablist" aria-label="资源分类">
          {resourceKinds.map((kind) => {
            const count = resources.filter((resource) => resource.kind === kind && !resource.archived).length
            return (
              <button
                type="button"
                role="tab"
                key={kind}
                className={activeKind === kind ? 'is-active' : ''}
                aria-selected={activeKind === kind}
                onClick={() => selectKind(kind)}
              >
                <ResourceIcon kind={kind} size={15} />
                <span>{resourceKindLabels[kind]}</span>
                <small>{count}</small>
              </button>
            )
          })}
        </div>

        <div className="resource-library__body">
          <aside className="resource-list-pane" aria-label={normalizedQuery ? '项目资源搜索结果' : `${resourceKindLabels[activeKind]}列表`}>
            <header>
              <strong>{normalizedQuery ? '搜索结果' : resourceKindLabels[activeKind]}</strong>
              <span>{visibleResources.length} 项</span>
            </header>
            <div className="resource-list">
              {visibleResources.length === 0 ? (
                <div className="resource-list-empty">
                  <Search size={19} />
                  <strong>没有匹配的资源</strong>
                  <span>尝试缩短关键词或显示已归档资源。</span>
                </div>
              ) : visibleResources.map((resource) => (
                <button
                  type="button"
                  key={resource.id}
                  className={`resource-list-row${selectedResource?.id === resource.id ? ' is-active' : ''}${resource.archived ? ' is-archived' : ''}`}
                  aria-current={selectedResource?.id === resource.id ? 'true' : undefined}
                  onClick={() => selectResource(resource)}
                >
                  <span className={`resource-list-icon resource-list-icon--${resource.kind}`}><ResourceIcon kind={resource.kind} /></span>
                  <span className="resource-list-copy">
                    <strong>{resource.name}</strong>
                    <small>{resource.summary}</small>
                    <span>{resource.id} · {resource.updatedAt}{resource.archived ? ' · 已归档' : ''}</span>
                  </span>
                  <ChevronRight size={15} aria-hidden="true" />
                </button>
              ))}
            </div>
          </aside>

          <section className="resource-detail-pane" aria-label="资源详情面板">
            {selectedResource ? (
              <>
                <header className="resource-detail-header">
                  <span className={`resource-detail-icon resource-list-icon--${selectedResource.kind}`}><ResourceIcon kind={selectedResource.kind} size={20} /></span>
                  <div>
                    <span>{resourceKindLabels[selectedResource.kind]} · {selectedResource.id}</span>
                    {renaming ? (
                      <form className="resource-rename" onSubmit={(event) => { event.preventDefault(); saveRename() }}>
                        <label>
                          <span className="sr-only">资源名称</span>
                          <input value={draftName} onChange={(event) => setDraftName(event.target.value)} autoFocus />
                        </label>
                        <button type="submit" disabled={!draftName.trim()}>保存名称</button>
                        <button type="button" onClick={() => setRenaming(false)}>取消</button>
                      </form>
                    ) : <h3>{selectedResource.name}</h3>}
                    <p>{selectedResource.summary}</p>
                  </div>
                  {selectedResource.archived && <span className="status-label status-label--neutral">已归档</span>}
                </header>

                <nav className="resource-detail-tabs" aria-label="资源详情">
                  {([
                    ['overview', '概览'],
                    ['versions', `版本 ${selectedResource.versions.length}`],
                    ['lineage', '来源关系'],
                  ] as const).map(([tab, label]) => (
                    <button type="button" key={tab} className={detailTab === tab ? 'is-active' : ''} aria-current={detailTab === tab ? 'page' : undefined} onClick={() => { setDetailTab(tab); setDeleteBlocked(false) }}>{label}</button>
                  ))}
                </nav>

                <div className="resource-detail-scroll">
                  {detailTab === 'overview' && (
                    <ResourceOverview resource={selectedResource} resources={resources} />
                  )}
                  {detailTab === 'versions' && <ResourceVersions resource={selectedResource} />}
                  {detailTab === 'lineage' && <ResourceLineage resource={selectedResource} resources={resources} />}

                  {deleteBlocked && (
                    <section className="resource-delete-blocker" role="alert" aria-labelledby="delete-blocker-title">
                      <div className="resource-delete-blocker__heading">
                        <ShieldAlert size={20} />
                        <div>
                          <h4 id="delete-blocker-title">无法直接删除原始数据</h4>
                          <p>{affectedResources.length} 个下游对象仍依赖 {selectedResource.name}。请先移除引用或归档原始数据。</p>
                        </div>
                        <button className="icon-button" type="button" onClick={() => setDeleteBlocked(false)} aria-label="关闭删除阻断说明"><X size={17} /></button>
                      </div>
                      <ul>
                        {affectedResources.map((resource) => (
                          <li key={resource.id}>
                            <ResourceIcon kind={resource.kind} size={14} />
                            <span><strong>{resource.name}</strong><small>{resourceKindLabels[resource.kind]} · {resource.id}</small></span>
                          </li>
                        ))}
                      </ul>
                      <div>
                        <button type="button" onClick={() => { setDetailTab('lineage'); setDeleteBlocked(false) }}><GitBranch size={15} />查看来源关系</button>
                        <button type="button" disabled>删除原始数据</button>
                      </div>
                    </section>
                  )}
                </div>

                <footer className="resource-actions">
                  {selectedResource.kind === 'export' ? (
                    <button className="resource-primary-action" type="button" onClick={() => setAnnouncement(`已定位外部目录 ${selectedResource.externalPath}`)}><ExternalLink size={15} />在资源管理器中定位</button>
                  ) : (
                    <button className="resource-primary-action" type="button" onClick={() => setAnnouncement(`已引用 ${selectedResource.name} 到“温度响应批量绘图”`)}><MessageSquarePlus size={15} />引用到当前对话</button>
                  )}
                  <button type="button" onClick={beginRename}><Pencil size={15} />重命名</button>
                  <button type="button" onClick={() => setDetailTab('versions')}><History size={15} />查看版本</button>
                  <button type="button" onClick={() => setDetailTab('lineage')}><GitBranch size={15} />来源关系</button>
                  <button type="button" onClick={toggleArchive}>{selectedResource.archived ? <ArchiveRestore size={15} /> : <Archive size={15} />}{selectedResource.archived ? '恢复资源' : '归档'}</button>
                  {selectedResource.kind === 'raw-data' && <button className="resource-delete-action" type="button" onClick={requestDelete}><Trash2 size={15} />删除</button>}
                </footer>
              </>
            ) : (
              <div className="resource-detail-empty"><Files size={25} /><strong>选择一个资源查看详情</strong></div>
            )}
          </section>
        </div>
        <div className="sr-only" role="status" aria-live="polite">{announcement}</div>
        {announcement && <div className="resource-announcement" role="status"><Check size={14} />{announcement}</div>}
      </section>
    </div>
  )
}

function ResourceOverview({ resource, resources }: { resource: ProjectResource; resources: ProjectResource[] }): React.JSX.Element {
  return (
    <div className="resource-overview">
      <dl className="resource-metadata">
        <div><dt>更新时间</dt><dd>{resource.updatedAt}</dd></div>
        <div><dt>格式</dt><dd>{resource.format ?? '项目对象'}</dd></div>
        <div><dt>大小</dt><dd>{resource.size ?? '由项目管理'}</dd></div>
        <div><dt>当前版本</dt><dd>{resource.versions[0]?.label ?? '无版本'}</dd></div>
      </dl>

      {resource.kind === 'export' && (
        <section className="external-record-note">
          <ExternalLink size={18} />
          <div><h4>外部文件定位记录</h4><p>项目不保存导出文件副本。此记录只用于定位外部文件，不会在资源库内打开或编辑文件。</p><code>{resource.externalPath}</code></div>
        </section>
      )}

      {resource.operationChain && <OperationChain resource={resource} />}

      <section className="resource-conversations">
        <header><h4>引用对话</h4><span>{resource.conversations.length} 个</span></header>
        {resource.conversations.map((conversation) => <span key={conversation}><Link2 size={13} />{conversation}</span>)}
      </section>

      <section className="resource-impact-summary">
        <header><h4>关系摘要</h4><span>{resource.parentIds.length} 个上游 · {collectAffectedResources(resource, resources).length} 个下游对象</span></header>
        <p>来源与下游引用共同用于版本追溯、删除保护和对话定位。</p>
      </section>
    </div>
  )
}

function OperationChain({ resource }: { resource: ProjectResource }): React.JSX.Element {
  return (
    <section className="operation-chain" aria-labelledby="operation-chain-title">
      <header><h4 id="operation-chain-title">上游操作链</h4><span>{resource.operationChain?.length ?? 0} 步，可追溯</span></header>
      <ol>
        {resource.operationChain?.map((step, index) => (
          <li key={step.label}>
            <span>{index + 1}</span>
            <div><strong>{step.label}</strong><small>{step.detail}</small></div>
          </li>
        ))}
      </ol>
    </section>
  )
}

function ResourceVersions({ resource }: { resource: ProjectResource }): React.JSX.Element {
  return (
    <section className="resource-versions" aria-labelledby="resource-versions-title">
      <header><h4 id="resource-versions-title">版本记录</h4><p>资源内容和操作记录保存在项目中，可按版本追溯。</p></header>
      <ol>
        {resource.versions.map((version, index) => (
          <li key={version.id}>
            <span className="version-node"><Clock3 size={14} /></span>
            <div><strong>{version.label}</strong><p>{version.detail}</p><small>{version.createdAt} · {version.author}</small></div>
            {index === 0 ? <span className="status-label status-label--success">当前</span> : <button type="button">查看此版本</button>}
          </li>
        ))}
      </ol>
    </section>
  )
}

function ResourceLineage({ resource, resources }: { resource: ProjectResource; resources: ProjectResource[] }): React.JSX.Element {
  const upstream = resource.parentIds.map((id) => getResourceById(resources, id)).filter((item): item is ProjectResource => Boolean(item))
  const downstream = resource.referencedBy.map((id) => getResourceById(resources, id)).filter((item): item is ProjectResource => Boolean(item))

  return (
    <div className="resource-lineage">
      <section>
        <header><h4>直接上游</h4><span>{upstream.length} 项</span></header>
        {upstream.length === 0 ? <p className="lineage-empty">这是来源对象，没有项目内上游。</p> : upstream.map((item) => <LineageRow key={item.id} resource={item} />)}
      </section>
      <div className="lineage-current"><ResourceIcon kind={resource.kind} /><span><strong>{resource.name}</strong><small>当前资源</small></span></div>
      <section>
        <header><h4>直接下游引用</h4><span>{downstream.length} 项</span></header>
        {downstream.length === 0 ? <p className="lineage-empty">暂无下游对象引用此资源。</p> : downstream.map((item) => <LineageRow key={item.id} resource={item} />)}
      </section>
      {resource.operationChain && <OperationChain resource={resource} />}
    </div>
  )
}

function LineageRow({ resource }: { resource: ProjectResource }): React.JSX.Element {
  return (
    <div className="lineage-row">
      <span className={`resource-list-icon resource-list-icon--${resource.kind}`}><ResourceIcon kind={resource.kind} size={14} /></span>
      <span><strong>{resource.name}</strong><small>{resourceKindLabels[resource.kind]} · {resource.id}</small></span>
    </div>
  )
}
