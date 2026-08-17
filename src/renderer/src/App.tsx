import { useCallback, useEffect, useEffectEvent, useMemo, useRef, useState } from 'react'
import { FlaskConical, LoaderCircle, X } from 'lucide-react'

import type {
  WorkflowRuntimeEvent,
  CoreStatus,
  CustomProviderConfigureInput,
  DesktopDataResult,
  FieldMappingInput,
  JsonValue,
  TaskEvent,
} from '../../shared/desktop-contract'
import { chartCatalog, type ChartType } from './data/chartCatalog'
import {
  disambiguateDatasetDisplayNames,
  isJsonRecord,
  projectVersionFrom,
  readWorkflowOutcome,
  readWorkflowPlan,
  readWorkflowPlans,
  readDataPreparationRecipes,
  readDataPreparationAttention,
  readDataPreparationRun,
  readEngineCompatibility,
  readDatasets,
  readImportSummary,
  readOriginAvailability,
  readPlot,
  readPlots,
  readProject,
  readProjects,
  resultKind,
  resultMessage,
  type WorkflowOutcome,
  type WorkflowPlanView,
  type DataPreparationRecipeView,
  type DataPreparationAttentionView,
  type DataPreparationRunView,
  type ProductDataset,
  type ProductPlot,
  type ProductProject,
} from './data/productState'
import { readWorkspaceSelection, writeWorkspaceSelection } from './data/workspacePersistence'
import { plotHistoryEntry, type PlotHistoryEntry } from './data/plotHistory'
import { ChartLibrary } from './components/ChartLibrary'
import {
  ConversationWorkspace,
  type ExportRecordView,
  type ProductNotice,
  type ScopeMode,
} from './components/ConversationWorkspace'
import { FocusEditor } from './components/FocusEditor'
import { Sidebar } from './components/Sidebar'
import { TaskDrawer } from './components/TaskDrawer'
import { useDialogFocus } from './components/useDialogFocus'
import { resolveDesktopRuntime } from './preview/browserPreviewApi'

type Screen = 'workspace' | 'focus'

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

function readExportRecord(
  value: JsonValue,
  format: 'png' | 'svg' | 'opju',
  target: { kind: 'plot'; id: string },
): ExportRecordView | undefined {
  if (!isJsonRecord(value) || typeof value.export_id !== 'string') return undefined
  const artifact = isJsonRecord(value.artifact) ? value.artifact : undefined
  return {
    exportId: value.export_id,
    format,
    targetKind: 'plot',
    targetId: typeof value.target_id === 'string'
      ? value.target_id
      : typeof value.plot_id === 'string' ? value.plot_id : target.id,
    ...(artifact && typeof artifact.content_hash === 'string' ? { artifactHash: artifact.content_hash } : {}),
    ...(artifact && typeof artifact.size === 'number' ? { artifactSize: artifact.size } : {}),
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
  const [workflowSourceIds, setWorkflowSourceIds] = useState<string[]>([])
  const [selectedChart, setSelectedChart] = useState<ChartType>()
  const [confirmedMapping, setConfirmedMapping] = useState<FieldMappingInput>()
  const [plot, setPlot] = useState<ProductPlot>()
  const [previousPlot, setPreviousPlot] = useState<ProductPlot>()
  const [exportRecord, setExportRecord] = useState<ExportRecordView>()
  const [notice, setNotice] = useState<ProductNotice>()
  const [workflowOutcome, setWorkflowOutcome] = useState<WorkflowOutcome>()
  const [workflowPlan, setWorkflowPlan] = useState<WorkflowPlanView>()
  const [, setDataPreparationRecipes] = useState<DataPreparationRecipeView[]>([])
  const [dataPreparationAttention, setDataPreparationAttention] = useState<DataPreparationAttentionView[]>([])
  const [latestPreparationRun, setLatestPreparationRun] = useState<DataPreparationRunView>()
  const [engineCompatibilityResult, setEngineCompatibilityResult] = useState<{
    datasetKey: string
    statuses: Readonly<Record<string, 'compatible' | 'incompatible'>>
  }>()
  const [agentConfigured, setAgentConfigured] = useState(false)
  const [undoStack, setUndoStack] = useState<PlotHistoryEntry[]>([])
  const [redoStack, setRedoStack] = useState<PlotHistoryEntry[]>([])
  const [providerOpen, setProviderOpen] = useState(false)
  const [providerNotice, setProviderNotice] = useState<ProductNotice>()

  const [libraryOpen, setLibraryOpen] = useState(false)
  const [tasksOpen, setTasksOpen] = useState(false)
  const [busyAction, setBusyAction] = useState<string>()
  const [taskEvents, setTaskEvents] = useState<Record<string, TaskEvent>>({})
  const [agentRuntimeEvent, setAgentRuntimeEvent] = useState<WorkflowRuntimeEvent>()
  const pendingAgentRequest = useRef<{ instruction: string; scope: ScopeMode } | undefined>(
    undefined,
  )
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

  useEffect(() => {
    if (!api || !project || !activeDataset || activeDataset.sampleRows !== undefined || activeDataset.samplePreviewUnavailable) return
    let active = true
    const markUnavailable = (): void => {
      if (!active) return
      setDatasets((current) => current.map((dataset) => (
        dataset.datasetId === activeDataset.datasetId && dataset.sourceVersion === activeDataset.sourceVersion
          ? { ...dataset, samplePreviewUnavailable: true }
          : dataset
      )))
    }
    void api.describeDataset({
      projectId: project.projectId,
      datasetId: activeDataset.datasetId,
      sourceVersion: activeDataset.sourceVersion,
    }).then((result) => {
      if (!active || !result.ok) { markUnavailable(); return }
      const described = readDatasets(result.value).find((dataset) => (
        dataset.datasetId === activeDataset.datasetId
        && dataset.sourceVersion === activeDataset.sourceVersion
      ))
      if (!described || described.sampleRows === undefined) { markUnavailable(); return }
      setDatasets((current) => current.map((dataset) => (
        dataset.datasetId === described.datasetId && dataset.sourceVersion === described.sourceVersion
          ? { ...dataset, ...described }
          : dataset
      )))
    }).catch(markUnavailable)
    return () => { active = false }
  }, [activeDataset, api, project])

  const rememberWorkspace = useCallback((selection: {
    datasetId?: string
    workflowSourceIds?: string[]
    chartId?: string
    mapping?: FieldMappingInput | null
  }): void => {
    if (!project) return
    const datasetId = selection.datasetId ?? activeDatasetId
    const chartId = selection.chartId ?? selectedChart?.id
    const mapping = selection.mapping === null ? undefined : selection.mapping ?? confirmedMapping
    writeWorkspaceSelection(window.localStorage, project.projectId, {
      ...(datasetId === undefined ? {} : { datasetId }),
      ...((selection.workflowSourceIds ?? workflowSourceIds).length === 0 ? {} : { workflowSourceIds: selection.workflowSourceIds ?? workflowSourceIds }),
      ...(chartId === undefined ? {} : { chartId }),
      ...(mapping === undefined ? {} : { mapping }),
    })
  }, [activeDatasetId, confirmedMapping, project, selectedChart?.id, workflowSourceIds])

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
      const plots = readPlots(listed)
      const supportedChartIds = new Set(chartCatalog.map((chart) => chart.id))
      const removedPlots = plots.filter((plot) => !supportedChartIds.has(plot.chartId))
      const latest = plots.filter((plot) => supportedChartIds.has(plot.chartId)).at(-1)
      const removedNotice = removedPlots.length > 0
        ? {
            kind: 'warning' as const,
            title: '图类已移除',
            message: `此项目包含已从当前版本移除的图类：${[...new Set(removedPlots.map((plot) => plot.chartId))].join('、')}。这些历史图形不会被替换或重新渲染。`,
          }
        : undefined
      if (!latest) return { notice: removedNotice }
      const stored = valueOrThrow(await api.getPlot({
        projectId,
        plotId: latest.plotId,
        plotVersion: latest.plotVersion,
      }))
      return { plot: readPlot(stored) ?? latest, notice: removedNotice }
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
    void api.listTaskPlans({ projectId: activeProjectId }).then((result) => {
      if (!active || !result.ok) return
      const plans = readWorkflowPlans(result.value)
      const latest = plans.at(-1)
      setWorkflowPlan(latest)
    })
    void api.listDataPreparationRecipes({ projectId: activeProjectId }).then((result) => {
      if (active && result.ok) setDataPreparationRecipes(readDataPreparationRecipes(result.value))
    })
    return () => { active = false }
  }, [api, activeProjectId])

  useEffect(() => {
    if (!api || !activeProjectId || !activeDataset) return
    let active = true
    const datasetKey = `${activeDataset.datasetId}:${activeDataset.sourceVersion}`
    void api.checkEngineCompatibility({
      projectId: activeProjectId,
      datasetId: activeDataset.datasetId,
      sourceVersion: activeDataset.sourceVersion,
      profileIds: chartCatalog.map((chart) => chart.id),
    }).then((result) => {
      if (active && result.ok) setEngineCompatibilityResult({
        datasetKey,
        statuses: readEngineCompatibility(result.value),
      })
    })
    return () => { active = false }
  }, [api, activeProjectId, activeDataset])

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
      setWorkflowSourceIds([])
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
    setWorkflowSourceIds([])
    setSelectedChart(undefined)
    setConfirmedMapping(undefined)
    setPlot(undefined)
    setPreviousPlot(undefined)
    setExportRecord(undefined)
    setWorkflowOutcome(undefined)
    setWorkflowPlan(undefined)
    setDataPreparationAttention([])
    setLatestPreparationRun(undefined)
    setUndoStack([])
    setRedoStack([])
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
    const unsubAgentRuntime = api.onWorkflowRuntimeEvent((event) => setAgentRuntimeEvent(event))
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
        setPreviousPlot(undefined)
        setSelectedChart(recovery.plot ? chartCatalog.find((chart) => chart.id === recovery.plot?.chartId) : undefined)
        setNotice(recovery.notice ?? { kind: 'success', title: '项目已打开', message: '已从受控项目资源恢复本地会话。' })
      }).catch((error: unknown) => setNotice(errorNotice(error))).finally(() => setBusyAction(undefined))
    })
    return () => { active = false; unsubCore(); unsubTasks(); unsubAgentRuntime(); unsubOpen() }
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

  async function importIntoProject(targetProject: ProductProject): Promise<void> {
    if (!api) return
    const value = valueOrThrow(await api.importDatasets({ projectId: targetProject.projectId }))
    const summary = readImportSummary(value)
    const importKind = resultKind(value)
    const imported = readDatasets(value)
    const attention = readDataPreparationAttention(value)
    if (attention.length > 0) {
      setDataPreparationAttention((current) => [
        ...current.filter((item) => !attention.some((next) => next.runId === item.runId)),
        ...attention,
      ])
    }
    if (imported.length === 0 && attention.length > 0) {
      setNotice({
        kind: 'warning',
        title: '数据整理需要确认',
        message: '请在对话中的整理卡片选择候选，或交给 Agent 判断。',
      })
      return
    }
    if (imported.length === 0 && (summary.failedCount > 0 || importKind === 'rejection' || importKind === 'rejected' || importKind === 'failed')) {
      setNotice({
        kind: 'error',
        title: '数据未导入',
        message: summary.failedDetails.join('\n') || resultMessage(value) || '所选文件均未导入。',
        actionLabel: '重新选择文件',
        onAction: () => { retryImportIntoProject(targetProject) },
      })
      return
    }
    setDatasets((current) => disambiguateDatasetDisplayNames(
      [...new Map([...current, ...imported].map((item) => [`${item.datasetId}:${item.sourceVersion}`, item])).values()],
    ))
    const preparationRunId = imported[0]?.dataPreparationRunId
    if (preparationRunId !== undefined) {
      const runResult = await api.getDataPreparationRun({
        projectId: targetProject.projectId,
        runId: preparationRunId,
      })
      if (runResult.ok) setLatestPreparationRun(readDataPreparationRun(runResult.value))
    }
    if (datasets.length === 0 && imported[0]) {
      setActiveDatasetId(imported[0].datasetId)
      setWorkflowSourceIds([])
    }
    const version = projectVersionFrom(value, targetProject.projectVersion)
    const nextProject = projectWithVersion(targetProject, version)
    setProject(nextProject); mergeProjects([nextProject])
    if (datasets.length === 0) { setConfirmedMapping(undefined); setPlot(undefined) }
    const partial = summary.failedCount > 0 || summary.attentionCount > 0
    const outcomeLines = [
      `已导入 ${summary.committedCount} 个文件，共 ${imported.length} 个工作表或数据块。`,
      ...summary.committedFiles.map((name) => `已导入：${name}`),
      ...summary.attentionDetails.map((detail) => `待确认：${detail}`),
      ...summary.failedDetails.map((detail) => `未导入：${detail}`),
    ]
    setNotice(partial ? {
      kind: 'warning',
      title: '部分文件未导入',
      message: outcomeLines.join('\n'),
      ...(attention.length > 0 ? {} : {
        actionLabel: '重新选择文件',
        onAction: () => { retryImportIntoProject(targetProject) },
      }),
    } : {
      kind: 'success',
      title: '数据已导入',
      message: previewMode
        ? `已载入 ${imported.length} 个内存示例数据集，可继续检查字段与界面流程。`
        : outcomeLines.join('\n'),
    })
  }

  function retryImportIntoProject(targetProject: ProductProject): void {
    if (!api || importInFlight.current) return
    importInFlight.current = true
    setBusyAction('import')
    setNotice(undefined)
    void importIntoProject(targetProject)
      .then(refreshProjects)
      .catch((error: unknown) => {
        if (typeof error === 'object' && error !== null && 'code' in error && error.code === 'DIALOG_CANCELLED') setNotice(undefined)
        else setNotice(errorNotice(error))
      })
      .finally(() => {
        importInFlight.current = false
        setBusyAction(undefined)
      })
  }

  async function applyDataPreparationResult(
    targetProject: ProductProject,
    value: JsonValue,
    previousRunId: string,
  ): Promise<void> {
    const nextAttention = readDataPreparationAttention(value)
    setDataPreparationAttention((current) => [
      ...current.filter((item) => item.runId !== previousRunId && !nextAttention.some((next) => next.runId === item.runId)),
      ...nextAttention,
    ])
    const imported = readDatasets(value)
    if (imported.length > 0) {
      setDatasets((current) => disambiguateDatasetDisplayNames(
        [...current.filter((item) => !imported.some((next) => next.datasetId === item.datasetId)), ...imported],
      ))
      if (datasets.length === 0 && imported[0]) {
        setActiveDatasetId(imported[0].datasetId)
        setWorkflowSourceIds([])
      }
      const runId = imported[0]?.dataPreparationRunId
      let nextRun: DataPreparationRunView | undefined
      if (runId !== undefined) {
        const runResult = await api?.getDataPreparationRun({ projectId: targetProject.projectId, runId })
        if (runResult?.ok) {
          nextRun = readDataPreparationRun(runResult.value)
          setLatestPreparationRun(nextRun)
        }
      }
      const version = projectVersionFrom(value, targetProject.projectVersion)
      const nextProject = projectWithVersion(targetProject, version)
      setProject(nextProject)
      mergeProjects([nextProject])
      setNotice(nextRun?.state === 'awaiting_confirmation' ? {
        kind: 'success',
        title: '数据整理完成，等待确认',
        message: `已生成 ${imported.length} 张规则数据表，请检查样本后确认采用或退回。`,
      } : {
        kind: 'success',
        title: '重新整理完成',
        message: `已生成 ${imported.length} 张新的规则数据表版本；已有图仍绑定原来的数据版本。`,
      })
      return
    }
    if (nextAttention.length > 0) {
      setNotice({ kind: 'warning', title: '仍需确认', message: nextAttention.map((item) => item.message).join('\n') })
      return
    }
    setNotice({
      kind: 'warning',
      title: 'Agent 未能确定整理方式',
      message: resultMessage(value) ?? '现有证据不足，原始数据没有被修改；可以重新选择文件或补充更明确的数据。',
    })
  }

  const retryDataPreparation = async (runId: string, optionValue: string): Promise<void> => {
    if (!api || !project || busyAction !== undefined) return
    setBusyAction('prepare-retry'); setNotice(undefined)
    try {
      const value = valueOrThrow(await api.retryDataPreparation({
        projectId: project.projectId,
        runId,
        optionValue,
      }))
      await applyDataPreparationResult(project, value, runId)
    } catch (error) {
      setNotice(errorNotice(error))
    } finally {
      setBusyAction(undefined)
    }
  }

  const assistDataPreparation = async (runId: string): Promise<void> => {
    if (!api || !project || busyAction !== undefined) return
    setBusyAction('prepare-agent'); setNotice(undefined)
    try {
      const value = valueOrThrow(await api.assistDataPreparation({ projectId: project.projectId, runId }))
      await applyDataPreparationResult(project, value, runId)
    } catch (error) {
      setNotice(errorNotice(error))
    } finally {
      setBusyAction(undefined)
    }
  }

  const reprocessDataPreparation = async (): Promise<void> => {
    if (!api || !project || !latestPreparationRun || busyAction !== undefined) return
    setBusyAction('prepare-reprocess'); setNotice(undefined)
    try {
      const value = valueOrThrow(await api.reprocessDataPreparation({
        projectId: project.projectId,
        runId: latestPreparationRun.runId,
      }))
      await applyDataPreparationResult(project, value, latestPreparationRun.runId)
    } catch (error) {
      setNotice(errorNotice(error))
    } finally {
      setBusyAction(undefined)
    }
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
        setPreviousPlot(undefined)
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
      const next = { ...(known ?? { projectId, name: '本机项目', projectVersion: 0, isOpen: true }), projectVersion: projectVersionFrom(opened, 0), isOpen: true }
      setProject(next); mergeProjects([next])
      setDatasets([]); setActiveDatasetId(undefined); setWorkflowSourceIds([])
      setPlot(undefined); setPreviousPlot(undefined); setSelectedChart(undefined); setConfirmedMapping(undefined)
      setWorkflowPlan(undefined); setWorkflowOutcome(undefined); setExportRecord(undefined)
      setDataPreparationAttention([]); setLatestPreparationRun(undefined)

      let datasetNotice: ProductNotice | undefined
      try {
        const listed = valueOrThrow(await api.listDatasets({ projectId }))
        const nextDatasets = readDatasets(listed)
      const persisted = readWorkspaceSelection(window.localStorage, projectId)
      const nextDataset = nextDatasets.find((item) => item.datasetId === persisted?.datasetId) ?? nextDatasets[0]
      const availableDatasetIds = new Set(nextDatasets.map((item) => item.datasetId))
      const nextWorkflowSourceIds = (persisted?.workflowSourceIds ?? [])
        .filter((datasetId) => availableDatasetIds.has(datasetId) && datasetId !== nextDataset?.datasetId)
        .slice(0, 7)
      const persistedChart = chartCatalog.find((item) => item.id === persisted?.chartId)
      const availableFields = new Set(nextDataset?.fields.map((field) => field.fieldId) ?? [])
      const persistedMapping = persisted?.mapping !== undefined &&
        Object.values(persisted.mapping.roles).every((fieldId) => availableFields.has(fieldId))
        ? persisted.mapping
        : undefined
        setDatasets(nextDatasets); setActiveDatasetId(nextDataset?.datasetId); setWorkflowSourceIds(nextWorkflowSourceIds)
        setSelectedChart(persistedChart); setConfirmedMapping(persistedMapping)
      } catch (error) {
        datasetNotice = {
          kind: 'warning',
          title: '项目数据暂不可用',
          message: errorNotice(error).message,
        }
      }
      const recovery = await recoverLatestPlot(projectId)
      if (recovery.plot) {
        setPlot(recovery.plot)
        setSelectedChart(chartCatalog.find((chart) => chart.id === recovery.plot?.chartId))
      }
      if (recovery.notice) setNotice(recovery.notice)
      else if (datasetNotice) setNotice(datasetNotice)
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const confirmMapping = async (mapping: FieldMappingInput): Promise<void> => {
    if (!api || !project || !activeDataset || !selectedChart) return
    setConfirmedMapping(mapping)
    rememberWorkspace({
      datasetId: activeDataset.datasetId,
      chartId: selectedChart.id,
      mapping,
    })
    setBusyAction('plot'); setNotice(undefined)
    try {
      if (!activeDataset.contentHash) throw new Error('当前数据缺少不可变内容标识。')
      const created = valueOrThrow(await api.executePlotAction({
        projectId: project.projectId,
        expectedProjectVersion: project.projectVersion,
        action: {
          operation: 'create_plot',
          action_id: `action:ui.create.${crypto.randomUUID()}`,
          plot_id: `plot:ui.${crypto.randomUUID()}`,
          profile_id: selectedChart.id,
          data: {
            kind: 'source',
            dataset_id: activeDataset.datasetId,
            version: activeDataset.sourceVersion,
            content_hash: activeDataset.contentHash,
          },
          bindings: Object.entries(mapping.roles).map(([role, field_id]) => ({ role, field_id })),
        },
      }))
      const nextPlot = readPlot(created)
      if (!nextPlot) throw new Error('Core 未返回 PlotDocument 版本。')
      setPlot(nextPlot)
      setPreviousPlot(undefined)
      setUndoStack([])
      setRedoStack([])
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

  const confirmMultiSourceMapping = async (mapping: FieldMappingInput): Promise<void> => {
    if (!api || !project || !activeDataset || !selectedChart) return
    const selectedIds = [activeDataset.datasetId, ...workflowSourceIds.filter((id) => id !== activeDataset.datasetId)].slice(0, 8)
    const multiSourceDatasets = selectedIds.flatMap((id) => {
      const dataset = datasets.find((candidate) => candidate.datasetId === id)
      return dataset ? [dataset] : []
    })
    if (multiSourceDatasets.length < 2) {
      setNotice({ kind: 'warning', title: '还需选择数据表', message: '请在“提供给 Agent 的数据表”中至少勾选两个数据表。' })
      return
    }
    setBusyAction('plot'); setNotice(undefined)
    try {
      const activeFields = new Map(activeDataset.fields.map((field) => [field.fieldId, field.name]))
      const roleDescription = Object.entries(mapping.roles)
        .filter(([role]) => role !== 'group')
        .map(([role, fieldId]) => {
          const name = activeFields.get(fieldId)
          if (name === undefined) throw new Error(`当前映射字段已不存在：${fieldId}`)
          return `${role}=${name}`
        })
      const created = valueOrThrow(await api.runWorkflow({
        projectId: project.projectId,
        selectedSources: multiSourceDatasets.map((dataset) => ({
          datasetId: dataset.datasetId,
          sourceVersion: dataset.sourceVersion,
        })),
        selectedProfileIds: [selectedChart.id],
        expectedProjectVersion: project.projectVersion,
        instruction: `将这些数据表合并绘制在同一张 ${selectedChart.id} ${selectedChart.name} 中；字段角色为 ${roleDescription.join('、')}；保留数据来源分组。`,
      }))
      setConfirmedMapping(mapping)
      const outcome = readWorkflowOutcome(created)
      setWorkflowPlan(outcome.plan)
      setWorkflowOutcome(outcome)
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const runAgent = async (instruction: string, scope: ScopeMode): Promise<void> => {
    if (!project) return
    if (!activeDataset) {
      pendingAgentRequest.current = { instruction, scope }
      setWorkflowOutcome({ kind: 'needs_input', title: '请先上传数据', message: '收到你的要求了。上传数据后，我会继续声明字段绑定。' })
      return
    }
    if (!api) return
    const continuationWorkflowRunId = workflowOutcome?.kind === 'needs_input'
      ? workflowOutcome.workflowRunId
      : undefined
    pendingAgentRequest.current = undefined
    const requestGeneration = agentRequestGeneration.current + 1
    agentRequestGeneration.current = requestGeneration
    setBusyAction('agent'); setWorkflowOutcome(undefined); setWorkflowPlan(undefined); setNotice(undefined)
    try {
      const selectedIds = [
        activeDataset.datasetId,
        ...workflowSourceIds.filter((id) => id !== activeDataset.datasetId),
      ].slice(0, 8)
      const selectedSources = selectedIds
        .flatMap((datasetId) => {
          const dataset = datasets.find((candidate) => candidate.datasetId === datasetId)
          return dataset === undefined ? [] : [dataset]
        })
        .map((dataset) => ({ datasetId: dataset.datasetId, sourceVersion: dataset.sourceVersion }))
      const value = valueOrThrow(await api.runWorkflow({
        projectId: project.projectId,
        selectedSources,
        expectedProjectVersion: project.projectVersion,
        ...(selectedChart === undefined ? {} : { selectedProfileIds: [selectedChart.id] }),
        ...(plot === undefined || scope !== 'current' ? {} : { selectedPlotIds: [plot.plotId] }),
        ...(continuationWorkflowRunId === undefined ? {} : { continuationWorkflowRunId }),
        instruction,
      }))
      if (agentRequestGeneration.current !== requestGeneration) return
      const outcome = readWorkflowOutcome(value)
      setWorkflowPlan(outcome.plan)
      setWorkflowOutcome(outcome)
    } catch (error) {
      if (agentRequestGeneration.current === requestGeneration) {
        setWorkflowOutcome({ kind: 'rejected', title: '指令未执行', message: errorNotice(error).message })
      }
    } finally {
      if (agentRequestGeneration.current === requestGeneration) setBusyAction(undefined)
    }
  }
  const resumePendingAgent = useEffectEvent(
    (pending: { instruction: string; scope: ScopeMode }) => {
      void runAgent(pending.instruction, pending.scope)
    },
  )

  useEffect(() => {
    const pending = pendingAgentRequest.current
    if (!pending || !activeDataset || busyAction !== undefined) return
    pendingAgentRequest.current = undefined
    const timer = window.setTimeout(() => resumePendingAgent(pending), 0)
    return () => window.clearTimeout(timer)
  }, [activeDataset, busyAction])

  const syncPlanOutput = async (plan: WorkflowPlanView): Promise<ProductPlot | undefined> => {
    if (!api || !project) return undefined
    const output = plan.steps.flatMap((step) => step.outputPlot ? [step.outputPlot] : []).at(-1)
    if (!output) return undefined
    const stored = valueOrThrow(await api.getPlot({ projectId: project.projectId, plotId: output.plotId, plotVersion: output.plotVersion }))
    const nextPlot = readPlot(stored)
    if (!nextPlot) return undefined
    setPlot(nextPlot)
    setPreviousPlot(plot)
    setProject(projectWithVersion(project, Math.max(project.projectVersion, nextPlot.projectVersion)))
    return nextPlot
  }

  const executeWorkflowPlan = async (planId: string, resume = false): Promise<void> => {
    if (!api || !project || busyAction !== undefined) return
    const historyEntry = plot && workflowPlan?.planId === planId
      ? plotHistoryEntry(plot, workflowPlan.boundActions) : undefined
    setBusyAction('agent-plan')
    setNotice(undefined)
    setWorkflowPlan((current) => current?.planId === planId ? { ...current, state: 'running' } : current)
    try {
      const value = valueOrThrow(resume
        ? await api.resumeTaskPlan({ projectId: project.projectId, planId })
        : await api.runTaskPlan({ projectId: project.projectId, planId }))
      const plan = readWorkflowPlan(value)
      if (!plan) throw new Error('Core 未返回任务计划状态。')
      setWorkflowPlan(plan)
      await syncPlanOutput(plan)
      if (plan.state === 'succeeded' && historyEntry) {
        setUndoStack((current) => [...current, historyEntry].slice(-50))
        setRedoStack([])
      }
      setWorkflowOutcome({
        kind: 'task_plan',
        title: plan.state === 'succeeded' ? '任务已完成' : plan.state === 'partially_succeeded' ? '任务部分完成' : '任务未完成',
        message: plan.state === 'succeeded' ? '更改已保存为可追溯版本。' : '已保留完成项，可继续未完成步骤。',
        plan,
      })
      if (plan.state === 'succeeded') setNotice(undefined)
    } catch (error) {
      const stored = await api.getTaskPlan({ projectId: project.projectId, planId })
      if (stored.ok) setWorkflowPlan(readWorkflowPlan(stored.value))
      setWorkflowOutcome({ kind: 'rejected', title: '计划未执行', message: errorNotice(error).message })
    } finally {
      setBusyAction(undefined)
    }
  }

  const confirmWorkflowPlan = async (planId: string): Promise<void> => {
    if (!api || !project || busyAction !== undefined) return
    setBusyAction('agent-plan')
    try {
      const confirmed = valueOrThrow(await api.confirmTaskPlan({ projectId: project.projectId, planId, accept: true }))
      const plan = readWorkflowPlan(confirmed)
      if (plan) setWorkflowPlan(plan)
    } catch (error) {
      setWorkflowOutcome({ kind: 'rejected', title: '计划未确认', message: errorNotice(error).message })
      setBusyAction(undefined)
      return
    }
    setBusyAction(undefined)
    await executeWorkflowPlan(planId)
  }

  const rejectWorkflowPlan = async (planId: string): Promise<void> => {
    if (!api || !project || busyAction !== undefined) return
    setBusyAction('agent-plan')
    try {
      const value = valueOrThrow(await api.confirmTaskPlan({ projectId: project.projectId, planId, accept: false }))
      if (!isJsonRecord(value) || value.state !== 'rejected') {
        throw new Error('Core did not confirm plan cancellation.')
      }
      setWorkflowPlan(undefined)
      setWorkflowOutcome({ kind: 'no_change', title: '计划已取消', message: '未修改任何项目对象。' })
    } catch (error) {
      setWorkflowOutcome({ kind: 'rejected', title: '计划未取消', message: errorNotice(error).message })
    } finally {
      setBusyAction(undefined)
    }
  }

  const applyPlotPatch = async (patch: JsonValue): Promise<void> => {
    if (!api || !project || !plot) throw new Error('当前没有可编辑图形。')
    if (!isJsonRecord(patch) || typeof patch.operation !== 'string') {
      throw new Error('绘图动作无效。')
    }
    const historyEntry = plotHistoryEntry(plot, [patch])
    setBusyAction('plot-patch'); setNotice(undefined)
    try {
      const value = valueOrThrow(await api.executePlotAction({
        projectId: project.projectId,
        expectedProjectVersion: project.projectVersion,
        action: {
          ...patch,
          action_id: `action:ui.edit.${crypto.randomUUID()}`,
          expected_plot_version: plot.plotVersion,
        },
      }))
      const nextPlot = readPlot(value)
      if (!nextPlot) throw new Error('Core 未返回新的 PlotDocument 版本。')
      setPlot(nextPlot)
      setPreviousPlot(plot)
      setProject(projectWithVersion(project, projectVersionFrom(value, project.projectVersion + 1)))
      if (historyEntry) {
        setUndoStack((current) => [...current, historyEntry].slice(-50))
        setRedoStack([])
      }
      setNotice({ kind: 'success', title: '修改已应用', message: `已创建图形版本 v${nextPlot.plotVersion}。` })
    } catch (error) {
      setNotice(errorNotice(error))
      throw error
    } finally {
      setBusyAction(undefined)
    }
  }

  const executeHistoryEntry = useCallback(async (
    entry: PlotHistoryEntry,
    direction: 'undo' | 'redo',
  ): Promise<boolean> => {
    if (!api || !project || !plot || plot.plotId !== entry.plotId || busyAction !== undefined) return false
    setBusyAction(direction)
    setNotice(undefined)
    let nextPlot = plot
    let nextProjectVersion = project.projectVersion
    try {
      for (const action of direction === 'undo' ? entry.undoActions : entry.redoActions) {
        if (!isJsonRecord(action)) throw new Error('历史动作无效。')
        const value = valueOrThrow(await api.executePlotAction({
          projectId: project.projectId,
          expectedProjectVersion: nextProjectVersion,
          action: {
            ...action,
            action_id: `action:ui.${direction}.${crypto.randomUUID()}`,
            expected_plot_version: nextPlot.plotVersion,
          },
        }))
        const restored = readPlot(value)
        if (!restored) throw new Error('Core 未返回恢复后的 PlotDocument。')
        nextPlot = restored
        nextProjectVersion = projectVersionFrom(value, nextProjectVersion + 1)
      }
      setPlot(nextPlot)
      setPreviousPlot(plot)
      setProject(projectWithVersion(project, nextProjectVersion))
      setNotice({
        kind: 'success',
        title: direction === 'undo' ? '已撤销本轮修改' : '已重做本轮修改',
        message: `${entry.label}已保存为新版本 v${nextPlot.plotVersion}。`,
      })
      return true
    } catch (error) {
      setNotice(errorNotice(error))
      return false
    } finally {
      setBusyAction(undefined)
    }
  }, [api, busyAction, plot, project])

  const undoPlotChange = useCallback(async (): Promise<void> => {
    const entry = undoStack.at(-1)
    if (!entry || await executeHistoryEntry(entry, 'undo') === false) return
    setUndoStack((current) => current.slice(0, -1))
    setRedoStack((current) => [...current, entry].slice(-50))
  }, [executeHistoryEntry, undoStack])

  const redoPlotChange = useCallback(async (): Promise<void> => {
    const entry = redoStack.at(-1)
    if (!entry || await executeHistoryEntry(entry, 'redo') === false) return
    setRedoStack((current) => current.slice(0, -1))
    setUndoStack((current) => [...current, entry].slice(-50))
  }, [executeHistoryEntry, redoStack])

  useEffect(() => {
    const onHistoryKeyDown = (event: KeyboardEvent): void => {
      const target = event.target
      if (target instanceof HTMLElement && (
        target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
      )) return
      if (!event.ctrlKey || event.altKey || event.key.toLocaleLowerCase('en-US') !== 'z') return
      event.preventDefault()
      if (event.shiftKey) void redoPlotChange()
      else void undoPlotChange()
    }
    window.addEventListener('keydown', onHistoryKeyDown)
    return () => window.removeEventListener('keydown', onHistoryKeyDown)
  }, [redoPlotChange, undoPlotChange])

  const exportArtifact = async (format: 'png' | 'svg' | 'opju'): Promise<void> => {
    if (!api || !project || plot === undefined) return
    if (previewMode) {
      setNotice({ kind: 'info', title: `预览模式不写出 ${format.toLocaleUpperCase('en-US')}`, message: '请在 PlotAgent 桌面应用中验证真实文件导出。' })
      return
    }
    const target = { kind: 'plot' as const, id: plot.plotId, version: plot.plotVersion }
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

  const saveDataPreparationRecipe = async (): Promise<void> => {
    if (!api || !project || !latestPreparationRun || busyAction !== undefined) return
    setBusyAction('save-recipe'); setNotice(undefined)
    try {
      const saved = valueOrThrow(await api.saveDataPreparationRecipe({
        projectId: project.projectId,
        runId: latestPreparationRun.runId,
        displayName: activeDataset === undefined
          ? '数据整理流程'
          : `${activeDataset.sourceFileName ?? activeDataset.displayName} 整理`,
      }))
      const listed = await api.listDataPreparationRecipes({ projectId: project.projectId })
      if (listed.ok) setDataPreparationRecipes(readDataPreparationRecipes(listed.value))
      setNotice({
        kind: 'success',
        title: '数据整理流程已保存',
        message: isJsonRecord(saved) && typeof saved.display_name === 'string'
          ? `${saved.display_name} 将在同构来源上自动进行结构匹配和校验；不会重放图类、字段绑定或视觉设置。`
          : '同构来源将优先尝试这条机械整理流程。',
      })
    } catch (error) {
      setNotice(errorNotice(error))
    } finally {
      setBusyAction(undefined)
    }
  }

  const confirmDataPreparationRun = async (accept: boolean): Promise<void> => {
    if (!api || !project || !latestPreparationRun || busyAction !== undefined) return
    setBusyAction('prepare-confirm'); setNotice(undefined)
    try {
      const value = valueOrThrow(await api.confirmDataPreparationRun({
        projectId: project.projectId,
        runId: latestPreparationRun.runId,
        accept,
      }))
      const runValue = isJsonRecord(value) && isJsonRecord(value.run) ? value.run : value
      const confirmedRun = readDataPreparationRun(runValue)
      const activeDatasets = readDatasets(value)
      setDataPreparationAttention((current) => current.filter((item) => item.runId !== latestPreparationRun.runId))
      if (accept) {
        setLatestPreparationRun(confirmedRun)
        setNotice({
          kind: 'success',
          title: '已采用整理结果',
          message: '数据表已确认。若经常处理同构数据，可以把这段非语义整理流程保存为 Recipe。',
        })
      } else {
        setLatestPreparationRun(undefined)
        setDatasets(disambiguateDatasetDisplayNames(activeDatasets))
        const nextActive = activeDatasets.some((item) => item.datasetId === activeDatasetId)
          ? activeDatasetId : activeDatasets[0]?.datasetId
        setActiveDatasetId(nextActive)
        setWorkflowSourceIds([])
        setConfirmedMapping(undefined)
        setPlot(undefined)
        setNotice({
          kind: 'warning',
          title: '已退回整理结果',
          message: '本次候选数据表已从当前工作区撤销，原始文件没有被修改；可以重新导入或重新处理。',
        })
      }
    } catch (error) {
      setNotice(errorNotice(error))
    } finally {
      setBusyAction(undefined)
    }
  }

  const createBatch = async (): Promise<void> => {
    if (!api || !project || !selectedChart || datasets.length === 0 || !activeDataset) return
    setBusyAction('batch'); setNotice(undefined)
    try {
      const created = valueOrThrow(await api.runWorkflow({
        projectId: project.projectId,
        selectedSources: datasets.slice(0, 8).map((dataset) => ({
          datasetId: dataset.datasetId,
          sourceVersion: dataset.sourceVersion,
        })),
        selectedProfileIds: [selectedChart.id],
        expectedProjectVersion: project.projectVersion,
        instruction: `分别为每个数据表创建 ${selectedChart.id} ${selectedChart.name}，保持原始数据不变。`,
      }))
      const plan = readWorkflowPlan(created)
      if (!plan) throw new Error('Core 未返回批量任务计划。')
      setWorkflowPlan(plan)
      setWorkflowOutcome({
        kind: 'task_plan',
        title: '批量任务计划',
        message: `${Math.min(datasets.length, 8)} 个数据表将分别生成一张图。`,
        plan,
      })
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
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
    totalFieldCount: activeDataset?.fields.length ?? 0,
    ...(activeDataset === undefined
      || engineCompatibilityResult?.datasetKey !== `${activeDataset.datasetId}:${activeDataset.sourceVersion}`
      ? {}
      : { statusByProfile: engineCompatibilityResult.statuses }),
  }), [activeDataset, engineCompatibilityResult])
  const canUndo = undoStack.at(-1)?.plotId === plot?.plotId
  const canRedo = redoStack.at(-1)?.plotId === plot?.plotId
  const modalOpen = libraryOpen || tasksOpen || providerOpen
  const selectDataset = (datasetId: string): void => {
    invalidateAgentRequest()
    setActiveDatasetId(datasetId)
    const nextWorkflowSourceIds = workflowSourceIds.filter((id) => id !== datasetId).slice(0, 7)
    setWorkflowSourceIds(nextWorkflowSourceIds)
    setConfirmedMapping(undefined)
    setPlot(undefined)
    setPreviousPlot(undefined)
    setWorkflowPlan(undefined)
    setUndoStack([])
    setRedoStack([])
    rememberWorkspace({ datasetId, workflowSourceIds: nextWorkflowSourceIds, mapping: null })
  }
  const toggleWorkflowSource = (datasetId: string): void => {
    if (datasetId === activeDataset?.datasetId) return
    const next = workflowSourceIds.includes(datasetId)
      ? workflowSourceIds.filter((id) => id !== datasetId)
      : [...workflowSourceIds, datasetId].slice(0, 7)
    setWorkflowSourceIds(next)
    rememberWorkspace({ workflowSourceIds: next })
  }

  const openFocusEditor = async (): Promise<void> => {
    if (!plot) return
    if (api && project && plot.plotVersion > 1) {
      try {
        const stored = valueOrThrow(await api.getPlot({
          projectId: project.projectId,
          plotId: plot.plotId,
          plotVersion: plot.plotVersion - 1,
        }))
        setPreviousPlot(readPlot(stored))
      } catch {
        setPreviousPlot(undefined)
      }
    } else {
      setPreviousPlot(undefined)
    }
    setScreen('focus')
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#conversation-main">跳到绘图对话</a>
      <div className="app-titlebar" aria-hidden="true"><FlaskConical size={13} /><span>PlotAgent</span></div>
      <div className="app-surface" inert={modalOpen ? true : undefined}>
        {screen === 'workspace' && <>
          <Sidebar projects={projects} activeProjectId={project?.projectId} core={core} agentConfigured={agentConfigured} taskCount={taskCount} originStatus={originStatus} busyAction={busyAction} previewMode={previewMode} onProjectChange={(id) => void activateProject(id)} onNewProject={() => void createNewProject()} onRenameProject={renameProject} onDeleteProject={deleteProject} onTaskCenter={() => setTasksOpen(true)} onConfigureAgent={() => setProviderOpen(true)} onRefreshOrigin={() => void refreshOriginStatus(true)} />
          <ConversationWorkspace key={project?.projectId ?? 'no-project'} core={core} project={project} datasets={datasets} activeDataset={activeDataset} selectedWorkflowSourceIds={activeDataset === undefined ? [] : [activeDataset.datasetId, ...workflowSourceIds.filter((id) => id !== activeDataset.datasetId)].slice(0, 8)} selectedChart={selectedChart} plot={plot} exportRecord={exportRecord} notice={notice} busyAction={busyAction} agentRuntimeLabel={agentRuntimeEvent?.projectId === project?.projectId ? agentRuntimeEvent?.label : undefined} workflowOutcome={workflowOutcome} workflowPlan={workflowPlan} dataPreparationAttention={dataPreparationAttention} latestPreparationRun={latestPreparationRun} agentConfigured={agentConfigured} taskEvents={Object.values(taskEvents)} previewMode={previewMode} canUndo={canUndo} canRedo={canRedo} onUndo={() => void undoPlotChange()} onRedo={() => void redoPlotChange()} onOpenSample={() => void openSample()} onImportData={() => void importData()} onOpenProject={() => void openProject()} onOpenLibrary={() => setLibraryOpen(true)} onSelectDataset={selectDataset} onToggleWorkflowSource={toggleWorkflowSource} onConfirmMapping={(mapping) => void confirmMapping(mapping)} onConfirmMultiSourceMapping={(mapping) => void confirmMultiSourceMapping(mapping)} onAgentInstruction={(instruction, scope) => void runAgent(instruction, scope)} onConfirmWorkflowPlan={(planId) => void confirmWorkflowPlan(planId)} onRejectWorkflowPlan={(planId) => void rejectWorkflowPlan(planId)} onRunWorkflowPlan={(planId) => void executeWorkflowPlan(planId)} onResumeWorkflowPlan={(planId) => void executeWorkflowPlan(planId, true)} onConfigureAgent={() => setProviderOpen(true)} onExport={(format) => void exportArtifact(format)} onSelectDataPreparationCandidate={(runId, optionValue) => void retryDataPreparation(runId, optionValue)} onAssistDataPreparation={(runId) => void assistDataPreparation(runId)} onConfirmDataPreparation={(accept) => void confirmDataPreparationRun(accept)} onReprocessDataPreparation={() => void reprocessDataPreparation()} onSaveDataPreparationRecipe={() => void saveDataPreparationRecipe()} onCreateBatch={() => void createBatch()} onOpenFocus={() => void openFocusEditor()} onOpenTasks={() => setTasksOpen(true)} onCancelTask={(taskId) => { if (api) void api.cancelTask(taskId) }} />
        </>}
        {screen === 'focus' && plot && <FocusEditor key={`${plot.plotId}:${plot.plotVersion}`} initialIndex={0} plot={{ ...plot, title: chartCatalog.find((chart) => chart.id === plot.chartId)?.name ?? plot.chartId }} previousPlot={previousPlot} onPatch={applyPlotPatch} canUndo={canUndo} canRedo={canRedo} onUndo={() => void undoPlotChange()} onRedo={() => void redoPlotChange()} onClose={() => setScreen('workspace')} />}
      </div>
      {libraryOpen && <ChartLibrary currentChartId={selectedChart?.id} datasetCompatibility={chartCompatibility} onClose={() => setLibraryOpen(false)} onSelect={(chart) => {
        setLibraryOpen(false)
        invalidateAgentRequest()
        setSelectedChart(chart); setConfirmedMapping(undefined); setPlot(undefined); setPreviousPlot(undefined); setWorkflowOutcome(undefined); rememberWorkspace({ chartId: chart.id, mapping: null })
        setUndoStack([]); setRedoStack([])
        setNotice(activeDataset ? undefined : { kind: 'info', title: `已选择 ${chart.name} ${chart.id}`, message: '可以继续上传数据。' })
      }} />}
      {tasksOpen && <TaskDrawer tasks={Object.values(taskEvents)} onCancel={(taskId) => { if (api) void api.cancelTask(taskId) }} onClose={() => setTasksOpen(false)} />}
      {providerOpen && <ProviderSettings busy={busyAction === 'provider'} notice={providerNotice} onClose={() => setProviderOpen(false)} onConfigure={(input) => void configureProvider(input)} />}
    </div>
  )
}
