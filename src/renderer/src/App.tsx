import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FlaskConical, LoaderCircle, X } from 'lucide-react'

import type {
  CoreStatus,
  CustomProviderConfigureInput,
  DesktopDataResult,
  FieldMappingInput,
  JsonValue,
  TaskEvent,
} from '../../shared/desktop-contract'
import { chartCatalog, type ChartType } from './data/chartCatalog'
import {
  isJsonRecord,
  projectVersionFrom,
  readAgentOutcome,
  readAgentPlan,
  readAgentPlans,
  readDatasets,
  readImportSummary,
  readOriginAvailability,
  readPlot,
  readPlots,
  readProject,
  readProjects,
  resultKind,
  resultMessage,
  withPreview,
  type AgentOutcome,
  type AgentPlanView,
  type ProductDataset,
  type ProductPlot,
  type ProductProject,
} from './data/productState'
import { BatchInspector } from './components/BatchInspector'
import { ChartLibrary } from './components/ChartLibrary'
import { CompositionEditor } from './components/CompositionEditor'
import {
  ConversationWorkspace,
  type BatchView,
  type AgentChangeSetView,
  type ExportRecordView,
  type FigureView,
  type ProductNotice,
  type ScopeMode,
} from './components/ConversationWorkspace'
import { FocusEditor } from './components/FocusEditor'
import { Sidebar } from './components/Sidebar'
import { TaskDrawer } from './components/TaskDrawer'
import { useDialogFocus } from './components/useDialogFocus'
import { resolveDesktopRuntime } from './preview/browserPreviewApi'

type Screen = 'workspace' | 'focus' | 'composition' | 'batch-inspector'

const initialCore: CoreStatus = { phase: 'starting', restartAttempt: 0 }

function failureNotice(error: { code: string; message: string; retryable: boolean }): ProductNotice {
  return { kind: 'error', title: '操作未完成', message: error.message }
}

function valueOrThrow(result: DesktopDataResult): JsonValue {
  if (!result.ok) throw result.error
  return result.value
}

function errorNotice(error: unknown): ProductNotice {
  if (typeof error === 'object' && error !== null && 'message' in error && typeof error.message === 'string') {
    const code = 'code' in error && typeof error.code === 'string' ? error.code : 'DESKTOP_OPERATION_FAILED'
    return failureNotice({ code, message: error.message, retryable: false })
  }
  return { kind: 'error', title: '操作未完成', message: '发生了未分类的本地错误。' }
}

function projectWithVersion(project: ProductProject, version: number): ProductProject {
  return { ...project, projectVersion: version, isOpen: true }
}

function nextProjectName(projects: ProductProject[]): string {
  const names = new Set(projects.map((item) => item.name))
  let index = 1
  while (names.has(`新建项目 ${index}`)) index += 1
  return `新建项目 ${index}`
}

function readProviderConfigured(value: JsonValue): boolean {
  if (!isJsonRecord(value)) return false
  if (value.configured === true) return true
  return Object.values(value).some((item) => isJsonRecord(item) && item.configured === true)
}

function readBatch(value: JsonValue): BatchView | undefined {
  if (!isJsonRecord(value)) return undefined
  const batch = isJsonRecord(value.batch) ? value.batch : value
  const batchId = typeof value.batch_id === 'string'
    ? value.batch_id
    : typeof batch.batch_id === 'string' ? batch.batch_id : undefined
  if (!batchId) return undefined
  const taskId = typeof value.task_id === 'string' ? value.task_id : `task:${batchId.replace(/^batch:/, '')}`
  const rawItems = Array.isArray(value.items)
    ? value.items
    : Array.isArray(batch.item_states) ? batch.item_states : []
  return {
    batchId,
    taskId,
    version: typeof batch.batch_version === 'number' ? batch.batch_version : 1,
    state: typeof value.state === 'string' ? value.state : 'queued',
    items: rawItems.flatMap((item) => isJsonRecord(item) && typeof item.item_id === 'string'
      ? [{ id: item.item_id, state: typeof item.state === 'string' ? item.state : 'queued' }]
      : []),
  }
}

function readFigure(value: JsonValue): FigureView | undefined {
  if (!isJsonRecord(value)) return undefined
  const figure = isJsonRecord(value.figure) ? value.figure : value
  if (typeof figure.figure_id !== 'string') return undefined
  const resource = isJsonRecord(value.artifact) && isJsonRecord(value.artifact.resource)
    ? value.artifact.resource
    : undefined
  return {
    figureId: figure.figure_id,
    version: typeof figure.figure_version === 'number' ? figure.figure_version : 1,
    ...(resource && typeof resource.url === 'string' ? { previewUrl: resource.url } : {}),
  }
}

function readExportRecord(
  value: JsonValue,
  format: 'png' | 'svg' | 'opju',
  target: { kind: 'plot' | 'batch' | 'figure'; id: string },
): ExportRecordView | undefined {
  if (!isJsonRecord(value) || typeof value.export_id !== 'string') return undefined
  const artifact = isJsonRecord(value.artifact) ? value.artifact : undefined
  return {
    exportId: value.export_id,
    format,
    targetKind: typeof value.target_kind === 'string' && ['plot', 'batch', 'figure'].includes(value.target_kind)
      ? value.target_kind as ExportRecordView['targetKind']
      : target.kind,
    targetId: typeof value.target_id === 'string'
      ? value.target_id
      : typeof value.plot_id === 'string' ? value.plot_id : target.id,
    ...(artifact && typeof artifact.content_hash === 'string' ? { artifactHash: artifact.content_hash } : {}),
    ...(artifact && typeof artifact.size === 'number' ? { artifactSize: artifact.size } : {}),
  }
}

function readAgentChangeSet(value: JsonValue): AgentChangeSetView | undefined {
  if (!isJsonRecord(value) || typeof value.plan_id !== 'string' || typeof value.state !== 'string') return undefined
  return {
    planId: value.plan_id,
    state: value.state,
    items: (Array.isArray(value.items) ? value.items : []).flatMap((item) => {
      if (!isJsonRecord(item) || typeof item.task_item_id !== 'string' || typeof item.state !== 'string') return []
      const failure = isJsonRecord(item.failure) && typeof item.failure.message === 'string'
        ? item.failure.message : undefined
      return [{
        taskItemId: item.task_item_id,
        actionType: typeof item.action_type === 'string' ? item.action_type : 'unknown',
        state: item.state,
        attemptCount: typeof item.attempt_count === 'number' ? item.attempt_count : 0,
        beforeCount: Array.isArray(item.before) ? item.before.length : 0,
        afterCount: Array.isArray(item.after) ? item.after.length : 0,
        ...(failure === undefined ? {} : { failure }),
      }]
    }),
  }
}

interface ProviderSettingsProps {
  busy: boolean
  notice?: ProductNotice
  onClose: () => void
  onConfigure: (input: CustomProviderConfigureInput) => void
}

function ProviderSettings({ busy, notice, onClose, onConfigure }: ProviderSettingsProps): React.JSX.Element {
  const [baseUrl, setBaseUrl] = useState('')
  const [modelId, setModelId] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [acknowledged, setAcknowledged] = useState(false)
  const dialogRef = useDialogFocus<HTMLElement>()

  return (
    <div className="provider-settings-layer" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section ref={dialogRef} className="provider-settings" role="dialog" aria-modal="true" aria-labelledby="provider-settings-title" tabIndex={-1}>
        <header><div><h2 id="provider-settings-title">模型服务</h2></div><button className="icon-button" type="button" onClick={onClose} aria-label="关闭模型服务设置"><X size={18} /></button></header>
        <form onSubmit={(event) => {
          event.preventDefault()
          onConfigure({ baseUrl, modelId, ...(apiKey ? { apiKey } : {}), retentionAcknowledged: true })
          setApiKey('')
        }}>
          <label>Base URL<input data-autofocus type="url" required placeholder="https://provider.example/v1 或 http://127.0.0.1:8000/v1" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} /></label>
          <label>Model ID<input required placeholder="model-id" value={modelId} onChange={(event) => setModelId(event.target.value)} /></label>
          <label>API key（可选）<input type="password" autoComplete="off" value={apiKey} onChange={(event) => setApiKey(event.target.value)} /></label>
          <label className="provider-retention"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} /><span>我已了解：Agent 会向所选模型服务发送指令、字段元数据和受控样本，保留政策由该服务决定。</span></label>
          {notice && <div className={`provider-inline-status provider-inline-status--${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}><strong>{notice.title}</strong><span>{notice.message}</span></div>}
          <footer><button type="button" onClick={onClose}>稍后配置</button><button className="primary-button" type="submit" disabled={!acknowledged || !baseUrl || !modelId || busy}>{busy && <LoaderCircle className="spin" size={15} />}保存模型服务</button></footer>
        </form>
      </section>
    </div>
  )
}

export function App(): React.JSX.Element {
  const { api, previewMode } = resolveDesktopRuntime()
  const [screen, setScreen] = useState<Screen>('workspace')
  const [core, setCore] = useState<CoreStatus>(api ? initialCore : {
    phase: 'failed', restartAttempt: 0,
    error: { code: 'CORE_NOT_READY', message: '桌面桥接不可用，请从 PlotAgent 桌面应用启动。', retryable: false },
  })
  const [projects, setProjects] = useState<ProductProject[]>([])
  const [project, setProject] = useState<ProductProject>()
  const [datasets, setDatasets] = useState<ProductDataset[]>([])
  const [activeDatasetId, setActiveDatasetId] = useState<string>()
  const [selectedChart, setSelectedChart] = useState<ChartType>()
  const [confirmedMapping, setConfirmedMapping] = useState<FieldMappingInput>()
  const [plot, setPlot] = useState<ProductPlot>()
  const [figureCandidates, setFigureCandidates] = useState<ProductPlot[]>([])
  const [batch, setBatch] = useState<BatchView>()
  const [figure, setFigure] = useState<FigureView>()
  const [exportRecord, setExportRecord] = useState<ExportRecordView>()
  const [changeSet, setChangeSet] = useState<AgentChangeSetView>()
  const [notice, setNotice] = useState<ProductNotice>()
  const [agentOutcome, setAgentOutcome] = useState<AgentOutcome>()
  const [agentPlan, setAgentPlan] = useState<AgentPlanView>()
  const [agentConfigured, setAgentConfigured] = useState(false)
  const [providerOpen, setProviderOpen] = useState(false)
  const [providerNotice, setProviderNotice] = useState<ProductNotice>()

  const [libraryOpen, setLibraryOpen] = useState(false)
  const [tasksOpen, setTasksOpen] = useState(false)
  const [busyAction, setBusyAction] = useState<string>()
  const [taskEvents, setTaskEvents] = useState<Record<string, TaskEvent>>({})
  const [originStatus, setOriginStatus] = useState<'unknown' | 'checking' | 'available' | 'unavailable' | 'exporting'>('unknown')
  const [originDiagnostic, setOriginDiagnostic] = useState('Origin 环境未通过检测。请重新检测后再导出。')
  const importInFlight = useRef(false)
  const agentRequestGeneration = useRef(0)

  useEffect(() => {
    if (notice?.kind !== 'success') return
    const timer = window.setTimeout(() => setNotice(undefined), 4_000)
    return () => window.clearTimeout(timer)
  }, [notice])

  const activeDataset = datasets.find((dataset) => dataset.datasetId === activeDatasetId) ?? datasets[0]
  const taskCount = Object.values(taskEvents).filter((event) => !['succeeded', 'failed', 'cancelled', 'partially_succeeded', 'interrupted'].includes(event.state)).length
  const activeProjectId = project?.projectId

  const refreshOriginStatus = useCallback(async (reportResult = false): Promise<boolean> => {
    if (!api) return false
    setOriginStatus('checking')
    try {
      const result = await api.getOriginStatus()
      if (!result.ok) {
        setOriginStatus('unavailable')
        setOriginDiagnostic(result.error.message)
        if (reportResult) setNotice({ kind: 'error', title: 'Origin 不可用', message: result.error.message })
        return false
      }
      const availability = readOriginAvailability(result.value)
      if (!availability) {
        setOriginStatus('unavailable')
        setOriginDiagnostic('Core 返回了无法识别的 Origin 状态。请重新检测。')
        if (reportResult) setNotice({ kind: 'error', title: 'Origin 检测失败', message: 'Core 返回了无法识别的 Origin 状态。请重新检测。' })
        return false
      }
      if (!availability.available) {
        setOriginStatus('unavailable')
        setOriginDiagnostic(availability.message)
        if (reportResult) setNotice({ kind: 'error', title: 'Origin 不可用', message: availability.message })
        return false
      }
      setOriginStatus('available')
      setOriginDiagnostic('')
      if (reportResult) {
        const version = availability.displayVersion ? ` ${availability.displayVersion}` : ''
        setNotice({ kind: 'success', title: 'Origin 可用', message: `${availability.displayName}${version}` })
      }
      return true
    } catch (error) {
      setOriginStatus('unavailable')
      setOriginDiagnostic(errorNotice(error).message)
      if (reportResult) setNotice(errorNotice(error))
      return false
    }
  }, [api])

  const recoverLatestPlot = useCallback(async (projectId: string): Promise<{
    plot?: ProductPlot
    notice?: ProductNotice
  }> => {
    if (!api) return {}
    try {
      const listed = valueOrThrow(await api.listPlots({ projectId }))
      const latest = readPlots(listed).at(-1)
      if (!latest) return {}
      const stored = valueOrThrow(await api.getPlot({
        projectId,
        plotId: latest.plotId,
        plotVersion: latest.plotVersion,
      }))
      let recovered = readPlot(stored) ?? latest
      try {
        const rendered = valueOrThrow(await api.renderPlot({
          projectId,
          plotId: recovered.plotId,
          plotVersion: recovered.plotVersion,
          mode: 'preview',
        }))
        recovered = withPreview(recovered, rendered)
        return { plot: recovered }
      } catch (error) {
        return {
          plot: recovered,
          notice: { kind: 'warning', title: '图形已恢复，预览未完成', message: errorNotice(error).message },
        }
      }
    } catch (error) {
      return {
        notice: { kind: 'warning', title: '图形恢复未完成', message: errorNotice(error).message },
      }
    }
  }, [api])

  useEffect(() => {
    if (core.phase !== 'ready') return
    const timer = window.setTimeout(() => { void refreshOriginStatus(false) }, 0)
    return () => window.clearTimeout(timer)
  }, [core.phase, refreshOriginStatus])

  useEffect(() => {
    if (!api || !activeProjectId) return
    let active = true
    void api.listAgentPlans({ projectId: activeProjectId }).then((result) => {
      if (!active || !result.ok) return
      const plans = readAgentPlans(result.value)
      setAgentPlan(plans.at(-1))
    })
    return () => { active = false }
  }, [api, activeProjectId])

  const mergeProjects = useCallback((nextProjects: ProductProject[]) => {
    setProjects((current) => {
      const byId = new Map(current.map((item) => [item.projectId, item]))
      for (const item of nextProjects) byId.set(item.projectId, { ...byId.get(item.projectId), ...item })
      return [...byId.values()]
    })
  }, [])

  const refreshProjects = useCallback(async () => {
    if (!api) return
    const result = await api.listProjects()
    if (result.ok) mergeProjects(readProjects(result.value))
  }, [api, mergeProjects])

  useEffect(() => {
    if (!api || core.phase !== 'ready') return
    let active = true
    void api.listProjects().then((result) => {
      if (active && result.ok) setProjects(readProjects(result.value))
    })
    void api.getProviderStatus().then((result) => {
      if (active && result.ok) setAgentConfigured(readProviderConfigured(result.value))
    })
    return () => { active = false }
  }, [api, core.phase])

  const hydrateProject = useCallback((value: JsonValue, fallbackName = '未命名项目', fallbackProject?: ProductProject) => {
    const nextProject = readProject(value) ?? (fallbackProject ? projectWithVersion(fallbackProject, projectVersionFrom(value, fallbackProject.projectVersion)) : undefined)
    if (nextProject) {
      const hydrated = { ...nextProject, name: nextProject.name || fallbackName, projectVersion: projectVersionFrom(value, nextProject.projectVersion), isOpen: true }
      setProject(hydrated)
      mergeProjects([hydrated])
    }
    const nextDatasets = readDatasets(value)
    if (nextDatasets.length > 0) {
      setDatasets(nextDatasets)
      setActiveDatasetId(nextDatasets[0].datasetId)
    }
    return nextProject
  }, [mergeProjects])

  const invalidateAgentRequest = useCallback(() => {
    agentRequestGeneration.current += 1
    setBusyAction((current) => current === 'agent' ? undefined : current)
  }, [])

  const clearWorkspace = useCallback(() => {
    invalidateAgentRequest()
    setProject(undefined)
    setDatasets([])
    setActiveDatasetId(undefined)
    setSelectedChart(undefined)
    setConfirmedMapping(undefined)
    setPlot(undefined)
    setFigureCandidates([])
    setBatch(undefined)
    setFigure(undefined)
    setExportRecord(undefined)
    setChangeSet(undefined)
    setAgentOutcome(undefined)
    setAgentPlan(undefined)
    setScreen('workspace')
  }, [invalidateAgentRequest])

  const createNewProject = useCallback(async (): Promise<void> => {
    if (!api || busyAction !== undefined || core.phase !== 'ready') return
    setBusyAction('new-project')
    setNotice(undefined)
    try {
      const createdValue = valueOrThrow(await api.createProject({ name: nextProjectName(projects) }))
      const created = readProject(createdValue)
      if (!created) throw new Error('Core 未返回新项目 ID。')
      const openedValue = valueOrThrow(await api.activateProject({ projectId: created.projectId }))
      const opened = {
        ...created,
        projectVersion: projectVersionFrom(openedValue, created.projectVersion),
        isOpen: true,
      }
      clearWorkspace()
      setProject(opened)
      mergeProjects([opened])
      await refreshProjects()
    } catch (error) {
      setNotice(errorNotice(error))
    } finally {
      setBusyAction(undefined)
    }
  }, [api, busyAction, clearWorkspace, core.phase, mergeProjects, projects, refreshProjects])

  const renameProject = useCallback(async (projectId: string, name: string): Promise<boolean> => {
    if (!api || busyAction !== undefined) return false
    setBusyAction(`rename-project:${projectId}`)
    try {
      const value = valueOrThrow(await api.renameProject({ projectId, name }))
      const renamed = readProject(value)
      const nextName = renamed?.name ?? name.trim()
      setProjects((current) => current.map((item) => item.projectId === projectId ? { ...item, name: nextName } : item))
      setProject((current) => current?.projectId === projectId ? { ...current, name: nextName } : current)
      return true
    } catch (error) {
      setNotice(errorNotice(error))
      return false
    } finally {
      setBusyAction(undefined)
    }
  }, [api, busyAction])

  const deleteProject = useCallback(async (projectId: string): Promise<boolean> => {
    if (!api || busyAction !== undefined) return false
    setBusyAction(`delete-project:${projectId}`)
    try {
      valueOrThrow(await api.deleteProject({ projectId }))
      setProjects((current) => current.filter((item) => item.projectId !== projectId))
      if (project?.projectId === projectId) clearWorkspace()
      setNotice({ kind: 'success', title: '项目已删除', message: '项目及其本机工作目录已删除。' })
      return true
    } catch (error) {
      setNotice(errorNotice(error))
      return false
    } finally {
      setBusyAction(undefined)
    }
  }, [api, busyAction, clearWorkspace, project])

  useEffect(() => {
    if (!api) return
    let active = true
    void api.getBootstrap().then((bootstrap) => {
      if (!active) return
      setCore(bootstrap.core)
    }).catch((error: unknown) => { if (active) setNotice(errorNotice(error)) })
    const unsubCore = api.onCoreStatus((status) => setCore(status))
    const unsubTasks = api.onTaskEvent((event) => setTaskEvents((current) => ({ ...current, [event.taskId]: event })))
    const unsubOpen = api.onOpenResourceRequested((request) => {
      setBusyAction('open-project')
      void api.openProjectResource({ resourceId: request.resourceId }).then(async (result) => {
        const value = valueOrThrow(result)
        const nextProject = hydrateProject(value)
        if (!nextProject) throw new Error('Core 未返回项目 ID。')
        const listed = valueOrThrow(await api.listDatasets({ projectId: nextProject.projectId }))
        hydrateProject(listed, nextProject.name, nextProject)
        const recovery = await recoverLatestPlot(nextProject.projectId)
        setPlot(recovery.plot)
        setSelectedChart(recovery.plot ? chartCatalog.find((chart) => chart.id === recovery.plot?.chartId) : undefined)
        setNotice(recovery.notice ?? { kind: 'success', title: '项目已打开', message: '已从受控项目资源恢复本地会话。' })
      }).catch((error: unknown) => setNotice(errorNotice(error))).finally(() => setBusyAction(undefined))
    })
    return () => { active = false; unsubCore(); unsubTasks(); unsubOpen() }
  }, [api, hydrateProject, recoverLatestPlot])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.ctrlKey && event.key.toLocaleLowerCase('en-US') === 'n') {
        event.preventDefault()
        void createNewProject()
      }
      if (event.key === 'Escape') {
        if (providerOpen) setProviderOpen(false)
        else if (libraryOpen) setLibraryOpen(false)
        else if (tasksOpen) setTasksOpen(false)
        else if (screen !== 'workspace') setScreen('workspace')
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [createNewProject, libraryOpen, providerOpen, screen, tasksOpen])

  const importIntoProject = async (targetProject: ProductProject): Promise<void> => {
    if (!api) return
    const value = valueOrThrow(await api.importDatasets({ projectId: targetProject.projectId }))
    const summary = readImportSummary(value)
    const importKind = resultKind(value)
    const imported = readDatasets(value)
    if (imported.length === 0 && (summary.attentionCount > 0 || importKind === 'clarification' || importKind === 'needs_input')) {
      setNotice({ kind: 'warning', title: '导入需要确认', message: resultMessage(value) ?? 'Core 无法唯一确定表头、分隔符或小数格式，请按提示重新导入。' })
      return
    }
    if (imported.length === 0 && (summary.failedCount > 0 || importKind === 'rejection' || importKind === 'rejected' || importKind === 'failed')) {
      const failedNames = summary.failedFiles.length > 0 ? `：${summary.failedFiles.join('、')}` : ''
      setNotice({ kind: 'error', title: '数据未导入', message: resultMessage(value) ?? `所选文件均未导入${failedNames}。` })
      return
    }
    setDatasets((current) => [...new Map([...current, ...imported].map((item) => [`${item.datasetId}:${item.sourceVersion}`, item])).values()])
    if (datasets.length === 0 && imported[0]) setActiveDatasetId(imported[0].datasetId)
    const version = projectVersionFrom(value, targetProject.projectVersion)
    const nextProject = projectWithVersion(targetProject, version)
    setProject(nextProject); mergeProjects([nextProject])
    if (datasets.length === 0) { setConfirmedMapping(undefined); setPlot(undefined) }
    const partial = summary.failedCount > 0 || summary.attentionCount > 0
    const failedNames = summary.failedFiles.length > 0 ? `；未导入：${summary.failedFiles.join('、')}` : ''
    setNotice(partial ? {
      kind: 'warning',
      title: '部分文件未导入',
      message: `已导入 ${imported.length} 个数据表${failedNames}。`,
    } : {
      kind: 'success',
      title: '数据已导入',
      message: previewMode
        ? `已载入 ${imported.length} 个内存示例数据集，可继续检查字段与界面流程。`
        : `已导入 ${summary.committedCount || 1} 个文件，共 ${imported.length} 个工作表或数据块。`,
    })
  }

  const openSample = async (): Promise<void> => {
    if (!api) return
    setBusyAction('sample'); setNotice(undefined)
    try {
      const value = valueOrThrow(await api.openSampleProject())
      hydrateProject(value, '温度响应示例')
      setNotice({
        kind: 'success',
        title: previewMode ? '示例项目已载入' : '示例项目已创建',
        message: previewMode ? '使用内存示例数据预览完整交互，不写入本机项目。' : '内置 CSV 已通过真实导入路径复制到新的本地项目。',
      })
      await refreshProjects()
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const importData = async (): Promise<void> => {
    if (!api || importInFlight.current || busyAction !== undefined) return
    importInFlight.current = true
    setBusyAction('import'); setNotice(undefined)
    try {
      let target = project
      if (!target) {
        const createdValue = valueOrThrow(await api.createProject({ name: '新建科研绘图项目' }))
        target = readProject(createdValue)
        if (!target) throw new Error('Core 未返回新项目 ID。')
        const openedValue = valueOrThrow(await api.activateProject({ projectId: target.projectId }))
        target = { ...target, projectVersion: projectVersionFrom(openedValue, 0), isOpen: true }
        setProject(target); mergeProjects([target])
      }
      await importIntoProject(target)
      await refreshProjects()
    } catch (error) {
      if (typeof error === 'object' && error !== null && 'code' in error && error.code === 'DIALOG_CANCELLED') setNotice(undefined)
      else setNotice(errorNotice(error))
    } finally {
      importInFlight.current = false
      setBusyAction(undefined)
    }
  }

  const openProject = async (): Promise<void> => {
    if (!api) return
    setBusyAction('open-project'); setNotice(undefined)
    try {
      const value = valueOrThrow(await api.openProject())
      const nextProject = hydrateProject(value)
      let recoveryNotice: ProductNotice | undefined
      if (nextProject) {
        const listed = valueOrThrow(await api.listDatasets({ projectId: nextProject.projectId }))
        hydrateProject(listed, nextProject.name, nextProject)
        const recovery = await recoverLatestPlot(nextProject.projectId)
        setPlot(recovery.plot)
        setSelectedChart(recovery.plot ? chartCatalog.find((chart) => chart.id === recovery.plot?.chartId) : undefined)
        recoveryNotice = recovery.notice
      }
      setNotice(recoveryNotice ?? {
          kind: 'success',
          title: '项目已打开',
          message: previewMode ? '已载入内存项目，用于检查打开项目后的界面。' : '.plotproj 已由 Main 授权并交给本地 Core 校验。',
      })
      await refreshProjects()
    } catch (error) {
      if (typeof error === 'object' && error !== null && 'code' in error && error.code === 'DIALOG_CANCELLED') setNotice(undefined)
      else setNotice(errorNotice(error))
    } finally { setBusyAction(undefined) }
  }

  const activateProject = async (projectId: string): Promise<void> => {
    if (!api || project?.projectId === projectId) return
    invalidateAgentRequest()
    setBusyAction('activate-project'); setNotice(undefined)
    try {
      const known = projects.find((item) => item.projectId === projectId)
      const opened = valueOrThrow(await api.activateProject({ projectId }))
      const listed = valueOrThrow(await api.listDatasets({ projectId }))
      const next = { ...(known ?? { projectId, name: '本机项目', projectVersion: 0, isOpen: true }), projectVersion: projectVersionFrom(opened, 0), isOpen: true }
      setProject(next); setDatasets(readDatasets(listed)); setActiveDatasetId(readDatasets(listed)[0]?.datasetId)
      setPlot(undefined); setSelectedChart(undefined); setConfirmedMapping(undefined); setBatch(undefined); setFigure(undefined); setFigureCandidates([])
      setAgentPlan(undefined); setAgentOutcome(undefined); setChangeSet(undefined); setExportRecord(undefined)
      const recovery = await recoverLatestPlot(projectId)
      if (recovery.plot) {
        setPlot(recovery.plot)
        setSelectedChart(chartCatalog.find((chart) => chart.id === recovery.plot?.chartId))
      }
      if (recovery.notice) setNotice(recovery.notice)
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const confirmMapping = async (mapping: FieldMappingInput): Promise<void> => {
    if (!api || !project || !activeDataset || !selectedChart) return
    setConfirmedMapping(mapping)
    setBusyAction('plot'); setNotice(undefined)
    try {
      const created = valueOrThrow(await api.createPlot({
        projectId: project.projectId,
        datasetId: activeDataset.datasetId,
        sourceVersion: activeDataset.sourceVersion,
        chartId: selectedChart.id,
        fieldMapping: mapping,
        expectedVersion: project.projectVersion,
      }))
      let nextPlot = readPlot(created)
      if (!nextPlot) throw new Error('Core 未返回 PlotSpec 版本。')
      const rendered = valueOrThrow(await api.renderPlot({ projectId: project.projectId, plotId: nextPlot.plotId, plotVersion: nextPlot.plotVersion, mode: 'preview' }))
      nextPlot = withPreview(nextPlot, rendered)
      setPlot(nextPlot)
      setProject(projectWithVersion(project, projectVersionFrom(created, project.projectVersion + 1)))
      setNotice({
        kind: 'success',
        title: '绘图完成',
        message: previewMode
          ? `${selectedChart.name} ${selectedChart.id} 已按确认映射生成界面预览。`
          : `${selectedChart.name} ${selectedChart.id} 已按确认映射创建，预览来自本地 Core。`,
      })
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const runAgent = async (instruction: string, scope: ScopeMode): Promise<void> => {
    if (!api || !project || !activeDataset || !selectedChart) return
    const requestGeneration = agentRequestGeneration.current + 1
    agentRequestGeneration.current = requestGeneration
    setBusyAction('agent'); setAgentOutcome(undefined); setNotice(undefined)
    try {
      const target = scope === 'batch'
        ? batch ? { kind: 'batch' as const, id: batch.batchId } : undefined
        : scope === 'figure'
          ? figure ? { kind: 'figure' as const, id: figure.figureId } : undefined
          : plot ? { kind: 'plot' as const, id: plot.plotId } : undefined
      if ((scope === 'batch' || scope === 'figure') && !target) {
        setAgentOutcome({ kind: 'rejected', title: '作用对象不可用', message: scope === 'batch' ? '请先创建并运行一个批次。' : '请先创建组合图。' })
        return
      }
      const value = valueOrThrow(await api.decideAgent({
        projectId: project.projectId,
        sourceDatasetId: activeDataset.datasetId,
        sourceVersion: activeDataset.sourceVersion,
        expectedVersion: project.projectVersion,
        selectedChartId: selectedChart.id,
        executionMode: 'plan_only',
        ...(target === undefined ? {} : { target }),
        scope,
        utterance: instruction,
      }))
      if (agentRequestGeneration.current !== requestGeneration) return
      const outcome = readAgentOutcome(value)
      setAgentPlan(outcome.plan)
      setAgentOutcome(outcome)
    } catch (error) {
      if (agentRequestGeneration.current === requestGeneration) {
        setAgentOutcome({ kind: 'rejected', title: '指令未执行', message: errorNotice(error).message })
      }
    } finally {
      if (agentRequestGeneration.current === requestGeneration) setBusyAction(undefined)
    }
  }

  const syncPlanOutput = async (plan: AgentPlanView): Promise<void> => {
    if (!api || !project) return
    const batchOutput = plan.steps.flatMap((step) => step.outputBatch ? [step.outputBatch] : []).at(-1)
    if (batchOutput) {
      const stored = valueOrThrow(await api.getBatch({ projectId: project.projectId, batchId: batchOutput.batchId }))
      const nextBatch = readBatch(stored)
      if (nextBatch) setBatch(nextBatch)
      setProject(projectWithVersion(project, projectVersionFrom(stored, project.projectVersion)))
      return
    }
    const output = plan.steps.flatMap((step) => step.outputPlot ? [step.outputPlot] : []).at(-1)
    if (!output) return
    const stored = valueOrThrow(await api.getPlot({ projectId: project.projectId, plotId: output.plotId, plotVersion: output.plotVersion }))
    let nextPlot = readPlot(stored)
    if (!nextPlot) return
    const rendered = valueOrThrow(await api.renderPlot({ projectId: project.projectId, plotId: nextPlot.plotId, plotVersion: nextPlot.plotVersion, mode: 'preview' }))
    nextPlot = withPreview(nextPlot, rendered)
    setPlot(nextPlot)
    setProject(projectWithVersion(project, Math.max(project.projectVersion, nextPlot.projectVersion)))
  }

  const executeAgentPlan = async (planId: string, resume = false): Promise<void> => {
    if (!api || !project || busyAction !== undefined) return
    setBusyAction('agent-plan')
    setNotice(undefined)
    setAgentPlan((current) => current?.planId === planId ? { ...current, state: 'running' } : current)
    try {
      const value = valueOrThrow(resume
        ? await api.resumeAgentPlan({ projectId: project.projectId, planId })
        : await api.runAgentPlan({ projectId: project.projectId, planId }))
      const plan = readAgentPlan(value)
      if (!plan) throw new Error('Core 未返回任务计划状态。')
      setAgentPlan(plan)
      if (isJsonRecord(value) && value.change_set !== undefined) {
        setChangeSet(readAgentChangeSet(value.change_set))
      }
      await syncPlanOutput(plan)
      setAgentOutcome({
        kind: 'action_plan',
        title: plan.state === 'succeeded' ? '任务已完成' : plan.state === 'partial_success' ? '任务部分完成' : '任务未完成',
        message: plan.state === 'succeeded' ? '更改已保存为可追溯版本。' : '已保留完成项，可继续未完成步骤。',
        plan,
      })
      if (plan.state === 'succeeded') setNotice(undefined)
    } catch (error) {
      const stored = await api.getAgentPlan({ projectId: project.projectId, planId })
      if (stored.ok) setAgentPlan(readAgentPlan(stored.value))
      setAgentOutcome({ kind: 'rejected', title: '计划未执行', message: errorNotice(error).message })
    } finally {
      setBusyAction(undefined)
    }
  }

  const confirmAgentPlan = async (planId: string): Promise<void> => {
    if (!api || !project || busyAction !== undefined) return
    setBusyAction('agent-plan')
    try {
      const confirmed = valueOrThrow(await api.confirmAgentPlan({ projectId: project.projectId, planId, accept: true }))
      const plan = readAgentPlan(confirmed)
      if (plan) setAgentPlan(plan)
    } catch (error) {
      setAgentOutcome({ kind: 'rejected', title: '计划未确认', message: errorNotice(error).message })
      setBusyAction(undefined)
      return
    }
    setBusyAction(undefined)
    await executeAgentPlan(planId)
  }

  const rejectAgentPlan = async (planId: string): Promise<void> => {
    if (!api || !project || busyAction !== undefined) return
    setBusyAction('agent-plan')
    try {
      const value = valueOrThrow(await api.confirmAgentPlan({ projectId: project.projectId, planId, accept: false }))
      setAgentPlan(readAgentPlan(value))
      setAgentOutcome({ kind: 'no_change', title: '计划已取消', message: '未修改任何项目对象。' })
    } catch (error) {
      setAgentOutcome({ kind: 'rejected', title: '计划未取消', message: errorNotice(error).message })
    } finally {
      setBusyAction(undefined)
    }
  }

  const applyPlotPatch = async (patch: JsonValue): Promise<void> => {
    if (!api || !project || !plot) throw new Error('当前没有可编辑图形。')
    setBusyAction('plot-patch'); setNotice(undefined)
    try {
      const value = valueOrThrow(await api.patchPlot({
        projectId: project.projectId,
        plotId: plot.plotId,
        plotVersion: plot.plotVersion,
        patch,
      }))
      let nextPlot = readPlot(value)
      if (!nextPlot) throw new Error('Core 未返回新的 PlotSpec 版本。')
      const rendered = valueOrThrow(await api.renderPlot({
        projectId: project.projectId,
        plotId: nextPlot.plotId,
        plotVersion: nextPlot.plotVersion,
        mode: 'preview',
      }))
      nextPlot = withPreview(nextPlot, rendered)
      setPlot(nextPlot)
      setProject(projectWithVersion(project, projectVersionFrom(value, project.projectVersion + 1)))
      setNotice({ kind: 'success', title: '修改已应用', message: `已创建图形版本 v${nextPlot.plotVersion}。` })
    } catch (error) {
      setNotice(errorNotice(error))
      throw error
    } finally {
      setBusyAction(undefined)
    }
  }

  const exportArtifact = async (format: 'png' | 'svg' | 'opju', explicitTarget?: { kind: 'batch' | 'figure'; id: string; version: number }): Promise<void> => {
    if (!api || !project || (explicitTarget === undefined && plot === undefined)) return
    if (previewMode) {
      setNotice({ kind: 'info', title: `预览模式不写出 ${format.toLocaleUpperCase('en-US')}`, message: '请在 PlotAgent 桌面应用中验证真实文件导出。' })
      return
    }
    const target = explicitTarget ?? { kind: 'plot' as const, id: plot!.plotId, version: plot!.plotVersion }
    if (format === 'opju' && originStatus === 'unavailable') {
      setNotice({ kind: 'error', title: 'Origin 不可用', message: originDiagnostic })
      return
    }
    if (format === 'opju' && originStatus !== 'available' && !await refreshOriginStatus(true)) return
    setBusyAction(`export-${format}`); setNotice(undefined)
    if (format === 'opju') setOriginStatus('exporting')
    try {
      const result = format === 'opju'
        ? await api.exportOrigin({ projectId: project.projectId, target })
        : await api.exportPngSvg({ projectId: project.projectId, target, format })
      const exported = valueOrThrow(result)
      setExportRecord(readExportRecord(exported, format, target))
      if (format === 'opju') setOriginStatus('available')
      setNotice({ kind: 'success', title: `已导出 ${format.toLocaleUpperCase('en-US')}`, message: '文件已写入你在系统对话框中授权的位置。' })
    } catch (error) {
      const cancelled = typeof error === 'object' && error !== null && 'code' in error && error.code === 'DIALOG_CANCELLED'
      const originUnavailable = typeof error === 'object' && error !== null && 'code' in error && error.code === 'ORIGIN_UNAVAILABLE'
      if (format === 'opju') {
        setOriginStatus(originUnavailable ? 'unavailable' : 'available')
        if (originUnavailable) setOriginDiagnostic(errorNotice(error).message)
      }
      if (!cancelled) setNotice(errorNotice(error))
    } finally { setBusyAction(undefined) }
  }

  const createBatch = async (): Promise<void> => {
    if (!api || !project || !selectedChart || datasets.length === 0 || !activeDataset) return
    setBusyAction('batch'); setNotice(undefined)
    if (!confirmedMapping) { setNotice({ kind: 'warning', title: '批次尚不能创建', message: '请先确认当前图形的字段映射。' }); setBusyAction(undefined); return }
    try {
      const created = valueOrThrow(await api.createBatch({
        projectId: project.projectId,
        datasets: datasets.map((dataset) => ({ datasetId: dataset.datasetId, sourceVersion: dataset.sourceVersion })),
        chartId: selectedChart.id,
        fieldMapping: confirmedMapping,
        expectedVersion: project.projectVersion,
      }))
      const plan = readAgentPlan(created)
      if (!plan) throw new Error('Core 未返回批量任务计划。')
      setAgentPlan(plan)
      setAgentOutcome({
        kind: 'action_plan',
        title: '批量任务计划',
        message: `${datasets.length} 个数据集将使用同一字段映射。`,
        plan,
      })
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const toggleFigureCandidate = (): void => {
    if (!plot) {
      setNotice({ kind: 'warning', title: '无法加入组合图', message: '当前没有已渲染的图形。' })
      return
    }
    const exactMatch = figureCandidates.some((item) => (
      item.plotId === plot.plotId && item.plotVersion === plot.plotVersion
    ))
    if (exactMatch) {
      setFigureCandidates((current) => current.filter((item) => !(
        item.plotId === plot.plotId && item.plotVersion === plot.plotVersion
      )))
      setNotice({ kind: 'info', title: '已移出组合图', message: `${plot.plotId} · v${plot.plotVersion}` })
      return
    }
    const replacingVersion = figureCandidates.some((item) => item.plotId === plot.plotId)
    if (!replacingVersion && figureCandidates.length >= 4) {
      setNotice({ kind: 'warning', title: '组合图已满', message: '第一版组合图最多包含 4 张图。' })
      return
    }
    setFigureCandidates((current) => [
      ...current.filter((item) => item.plotId !== plot.plotId),
      plot,
    ])
    setNotice({
      kind: 'success',
      title: replacingVersion ? '已更新组合图候选' : '已加入组合图',
      message: `${plot.plotId} · v${plot.plotVersion}`,
    })
  }

  const createFigure = async (): Promise<void> => {
    if (!api || !project || busyAction !== undefined) return
    if (figureCandidates.length < 2) {
      setNotice({ kind: 'warning', title: '还需要候选图', message: `已加入 ${figureCandidates.length} 张，请先将至少 2 张已渲染图加入组合图。` })
      return
    }
    setBusyAction('figure'); setNotice(undefined)
    try {
      const created = valueOrThrow(await api.createFigure({
        projectId: project.projectId,
        plotRefs: figureCandidates.map((item) => ({ plotId: item.plotId, plotVersion: item.plotVersion })),
        layout: figureCandidates.length > 2 ? '2x2' : '1x2',
        expectedVersion: project.projectVersion,
      }))
      let nextFigure = readFigure(created)
      if (!nextFigure) throw new Error('Core 未返回 FigureSpec。')
      const nextProject = projectWithVersion(project, projectVersionFrom(created, project.projectVersion + 1))
      setFigure(nextFigure)
      setProject(nextProject)
      try {
        const rendered = valueOrThrow(await api.renderFigure({ projectId: project.projectId, figureId: nextFigure.figureId }))
        nextFigure = { ...nextFigure, ...readFigure(rendered) }
        setFigure(nextFigure)
        setFigureCandidates([])
        setNotice({ kind: 'success', title: '组合图已创建', message: `${nextFigure.figureId} · v${nextFigure.version}` })
      } catch (error) {
        setNotice({ kind: 'warning', title: '组合图已创建，预览未完成', message: `${nextFigure.figureId}：${errorNotice(error).message}` })
      }
    } catch (error) {
      setNotice({ kind: 'error', title: '组合图创建失败', message: errorNotice(error).message })
    } finally { setBusyAction(undefined) }
  }

  const configureProvider = async (input: CustomProviderConfigureInput): Promise<void> => {
    if (!api) return
    setBusyAction('provider'); setProviderNotice(undefined)
    try {
      const value = valueOrThrow(await api.configureCustomProvider(input))
      setAgentConfigured(readProviderConfigured(value))
      setProviderNotice({ kind: 'success', title: '模型服务已保存', message: 'API key 已从界面清除，后续只由本地 Core 从系统凭据库读取。' })
    } catch (error) { setProviderNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const chartCompatibility = useMemo(() => ({
    numericFieldCount: activeDataset?.fields.filter((field) => ['number', 'numeric', 'float', 'integer', 'decimal'].includes(field.logicalType.toLocaleLowerCase('en-US'))).length ?? 0,
    categoricalFieldCount: activeDataset?.fields.filter((field) => ['string', 'categorical', 'category', 'boolean'].includes(field.logicalType.toLocaleLowerCase('en-US'))).length ?? 0,
    totalFieldCount: activeDataset?.fields.length ?? 0,
  }), [activeDataset])
  const figureCandidateCount = figureCandidates.length
  const plotIsFigureCandidate = plot !== undefined && figureCandidates.some((item) => (
    item.plotId === plot.plotId && item.plotVersion === plot.plotVersion
  ))
  const modalOpen = libraryOpen || tasksOpen || providerOpen

  return (
    <div className="app-shell">
      <a className="skip-link" href="#conversation-main">跳到绘图对话</a>
      <div className="app-titlebar" aria-hidden="true"><FlaskConical size={13} /><span>PlotAgent</span></div>
      <div className="app-surface" inert={modalOpen ? true : undefined}>
        {screen === 'workspace' && <>
          <Sidebar projects={projects} activeProjectId={project?.projectId} core={core} agentConfigured={agentConfigured} taskCount={taskCount} originStatus={originStatus} busyAction={busyAction} previewMode={previewMode} onProjectChange={(id) => void activateProject(id)} onNewProject={() => void createNewProject()} onRenameProject={renameProject} onDeleteProject={deleteProject} onTaskCenter={() => setTasksOpen(true)} onConfigureAgent={() => setProviderOpen(true)} onRefreshOrigin={() => void refreshOriginStatus(true)} />
          <ConversationWorkspace core={core} project={project} datasets={datasets} activeDataset={activeDataset} selectedChart={selectedChart} plot={plot} batch={batch} figure={figure} figureCandidateCount={figureCandidateCount} plotIsFigureCandidate={plotIsFigureCandidate} exportRecord={exportRecord} changeSet={changeSet} notice={notice} busyAction={busyAction} agentOutcome={agentOutcome} agentPlan={agentPlan} agentConfigured={agentConfigured} previewMode={previewMode} onOpenSample={() => void openSample()} onImportData={() => void importData()} onOpenProject={() => void openProject()} onOpenLibrary={() => setLibraryOpen(true)} onSelectDataset={(id) => { invalidateAgentRequest(); setActiveDatasetId(id); setConfirmedMapping(undefined); setPlot(undefined); setAgentPlan(undefined) }} onConfirmMapping={(mapping) => void confirmMapping(mapping)} onAgentInstruction={(instruction, scope) => void runAgent(instruction, scope)} onConfirmAgentPlan={(planId) => void confirmAgentPlan(planId)} onRejectAgentPlan={(planId) => void rejectAgentPlan(planId)} onRunAgentPlan={(planId) => void executeAgentPlan(planId)} onResumeAgentPlan={(planId) => void executeAgentPlan(planId, true)} onConfigureAgent={() => setProviderOpen(true)} onExport={(format, target) => void exportArtifact(format, target)} onCreateBatch={() => void createBatch()} onCreateFigure={() => void createFigure()} onToggleFigureCandidate={toggleFigureCandidate} onOpenFocus={() => setScreen('focus')} onOpenBatchInspect={() => setScreen('batch-inspector')} onOpenCompose={() => setScreen('composition')} onOpenTasks={() => setTasksOpen(true)} />
        </>}
        {screen === 'focus' && plot && <FocusEditor key={`${plot.plotId}:${plot.plotVersion}`} initialIndex={0} plot={{ ...plot, title: selectedChart?.name ?? plot.chartId }} onPatch={applyPlotPatch} onClose={() => setScreen('workspace')} />}
        {screen === 'composition' && figure && <CompositionEditor figure={figure} onClose={() => setScreen('workspace')} />}
        {screen === 'batch-inspector' && batch && <BatchInspector batch={batch} onClose={() => setScreen('workspace')} />}
      </div>
      {libraryOpen && <ChartLibrary currentChartId={selectedChart?.id} availablePlotCount={figureCandidateCount} datasetCompatibility={chartCompatibility} onClose={() => setLibraryOpen(false)} onSelect={(chart) => {
        setLibraryOpen(false)
        if (chart.id === 'K25') { void createFigure(); return }
        invalidateAgentRequest()
        setSelectedChart(chart); setConfirmedMapping(undefined); setPlot(undefined); setAgentOutcome(undefined)
        setNotice(activeDataset ? undefined : { kind: 'info', title: `已选择 ${chart.name} ${chart.id}`, message: '可以继续上传数据。' })
      }} />}
      {tasksOpen && <TaskDrawer tasks={Object.values(taskEvents)} onCancel={(taskId) => { if (api) void api.cancelTask(taskId) }} onClose={() => setTasksOpen(false)} />}
      {providerOpen && <ProviderSettings busy={busyAction === 'provider'} notice={providerNotice} onClose={() => setProviderOpen(false)} onConfigure={(input) => void configureProvider(input)} />}
    </div>
  )
}
