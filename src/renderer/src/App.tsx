import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FlaskConical, LoaderCircle, X } from 'lucide-react'

import type {
  AgentRuntimeEvent,
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
  type AgentOutcome,
  type AgentPlanView,
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
  const [agentDatasetIds, setAgentDatasetIds] = useState<string[]>([])
  const [selectedChart, setSelectedChart] = useState<ChartType>()
  const [confirmedMapping, setConfirmedMapping] = useState<FieldMappingInput>()
  const [plot, setPlot] = useState<ProductPlot>()
  const [previousPlot, setPreviousPlot] = useState<ProductPlot>()
  const [exportRecord, setExportRecord] = useState<ExportRecordView>()
  const [notice, setNotice] = useState<ProductNotice>()
  const [agentOutcome, setAgentOutcome] = useState<AgentOutcome>()
  const [agentPlan, setAgentPlan] = useState<AgentPlanView>()
  const [agentConfigured, setAgentConfigured] = useState(false)
  const [undoStack, setUndoStack] = useState<PlotHistoryEntry[]>([])
  const [redoStack, setRedoStack] = useState<PlotHistoryEntry[]>([])
  const [providerOpen, setProviderOpen] = useState(false)
  const [providerNotice, setProviderNotice] = useState<ProductNotice>()

  const [libraryOpen, setLibraryOpen] = useState(false)
  const [tasksOpen, setTasksOpen] = useState(false)
  const [busyAction, setBusyAction] = useState<string>()
  const [taskEvents, setTaskEvents] = useState<Record<string, TaskEvent>>({})
  const [agentRuntimeEvent, setAgentRuntimeEvent] = useState<AgentRuntimeEvent>()
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
    agentDatasetIds?: string[]
    chartId?: string
    mapping?: FieldMappingInput | null
  }): void => {
    if (!project) return
    const datasetId = selection.datasetId ?? activeDatasetId
    const chartId = selection.chartId ?? selectedChart?.id
    const mapping = selection.mapping === null ? undefined : selection.mapping ?? confirmedMapping
    writeWorkspaceSelection(window.localStorage, project.projectId, {
      ...(datasetId === undefined ? {} : { datasetId }),
      ...((selection.agentDatasetIds ?? agentDatasetIds).length === 0 ? {} : { agentDatasetIds: selection.agentDatasetIds ?? agentDatasetIds }),
      ...(chartId === undefined ? {} : { chartId }),
      ...(mapping === undefined ? {} : { mapping }),
    })
  }, [activeDatasetId, agentDatasetIds, confirmedMapping, project, selectedChart?.id])

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
      setAgentDatasetIds([])
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
    setAgentDatasetIds([])
    setSelectedChart(undefined)
    setConfirmedMapping(undefined)
    setPlot(undefined)
    setPreviousPlot(undefined)
    setExportRecord(undefined)
    setAgentOutcome(undefined)
    setAgentPlan(undefined)
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
    const unsubAgentRuntime = api.onAgentRuntimeEvent((event) => setAgentRuntimeEvent(event))
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
    if (imported.length === 0 && (summary.attentionCount > 0 || importKind === 'clarification' || importKind === 'needs_input')) {
      setNotice({
        kind: 'warning',
        title: '导入需要确认',
        message: summary.attentionDetails.join('\n') || resultMessage(value) || '无法唯一确定表头、分隔符或小数格式。',
        actionLabel: '重新选择文件',
        onAction: () => { retryImportIntoProject(targetProject) },
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
    if (datasets.length === 0 && imported[0]) {
      setActiveDatasetId(imported[0].datasetId)
      setAgentDatasetIds([])
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
      actionLabel: summary.attentionCount > 0 ? '继续处理' : '重新选择文件',
      onAction: () => { retryImportIntoProject(targetProject) },
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
      setDatasets([]); setActiveDatasetId(undefined); setAgentDatasetIds([])
      setPlot(undefined); setPreviousPlot(undefined); setSelectedChart(undefined); setConfirmedMapping(undefined)
      setAgentPlan(undefined); setAgentOutcome(undefined); setExportRecord(undefined)

      let datasetNotice: ProductNotice | undefined
      try {
        const listed = valueOrThrow(await api.listDatasets({ projectId }))
        const nextDatasets = readDatasets(listed)
      const persisted = readWorkspaceSelection(window.localStorage, projectId)
      const nextDataset = nextDatasets.find((item) => item.datasetId === persisted?.datasetId) ?? nextDatasets[0]
      const availableDatasetIds = new Set(nextDatasets.map((item) => item.datasetId))
      const nextAgentDatasetIds = (persisted?.agentDatasetIds ?? [])
        .filter((datasetId) => availableDatasetIds.has(datasetId) && datasetId !== nextDataset?.datasetId)
        .slice(0, 7)
      const persistedChart = chartCatalog.find((item) => item.id === persisted?.chartId)
      const availableFields = new Set(nextDataset?.fields.map((field) => field.fieldId) ?? [])
      const persistedMapping = persisted?.mapping !== undefined &&
        Object.values(persisted.mapping.roles).every((fieldId) => availableFields.has(fieldId))
        ? persisted.mapping
        : undefined
        setDatasets(nextDatasets); setActiveDatasetId(nextDataset?.datasetId); setAgentDatasetIds(nextAgentDatasetIds)
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

  const confirmCombinedMapping = async (mapping: FieldMappingInput): Promise<void> => {
    if (!api || !project || !activeDataset || !selectedChart) return
    const selectedIds = [activeDataset.datasetId, ...agentDatasetIds.filter((id) => id !== activeDataset.datasetId)].slice(0, 8)
    const combinedSources = selectedIds.flatMap((id) => {
      const dataset = datasets.find((candidate) => candidate.datasetId === id)
      return dataset ? [dataset] : []
    })
    if (combinedSources.length < 2) {
      setNotice({ kind: 'warning', title: '还需选择数据表', message: '请在“提供给 Agent 的数据表”中至少勾选两个数据表。' })
      return
    }
    setBusyAction('plot'); setNotice(undefined)
    try {
      const activeFields = new Map(activeDataset.fields.map((field) => [field.fieldId, field.name]))
      const roles = Object.entries(mapping.roles)
        .filter(([role]) => role !== 'group')
        .map(([role, fieldId]) => {
          const name = activeFields.get(fieldId)
          if (name === undefined) throw new Error(`当前映射字段已不存在：${fieldId}`)
          return { role, name }
        })
      const requests = combinedSources.map((dataset) => {
        if (!dataset.contentHash) throw new Error(`${dataset.displayName} 缺少不可变内容标识。`)
        const byName = new Map<string, string[]>()
        for (const field of dataset.fields) {
          const key = field.name.trim().toLocaleLowerCase('en-US')
          byName.set(key, [...(byName.get(key) ?? []), field.fieldId])
        }
        const bindings = Object.fromEntries(roles.map(({ role, name }) => {
          const matches = byName.get(name.trim().toLocaleLowerCase('en-US')) ?? []
          if (matches.length !== 1) {
            throw new Error(`${dataset.displayName} 无法唯一匹配字段“${name}”，未执行同图绘制。`)
          }
          return [role, matches[0]]
        }))
        return {
          datasetId: dataset.datasetId,
          sourceVersion: dataset.sourceVersion,
          contentHash: dataset.contentHash,
          bindings,
        }
      })
      const created = valueOrThrow(await api.createCombinedPlot({
        projectId: project.projectId,
        datasets: requests,
        profileId: selectedChart.id,
        expectedProjectVersion: project.projectVersion,
      }))
      const nextPlot = readPlot(created)
      if (!nextPlot) throw new Error('Core 未返回多数据同图的 PlotDocument。')
      setConfirmedMapping(mapping)
      setPlot(nextPlot)
      setPreviousPlot(undefined)
      setUndoStack([])
      setRedoStack([])
      setProject(projectWithVersion(project, projectVersionFrom(created, project.projectVersion + 1)))
      setNotice({
        kind: 'success',
        title: '多数据同图绘制完成',
        message: `${combinedSources.length} 个同构数据表已合并，数据来源作为原生分组字段保留。`,
      })
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const runAgent = async (instruction: string, scope: ScopeMode): Promise<void> => {
    if (!project) return
    if (!activeDataset) {
      setAgentOutcome({ kind: 'needs_input', title: '请先上传数据', message: '收到你的要求了。上传数据后，我会继续声明字段绑定。' })
      return
    }
    if (!agentConfigured) {
      setAgentOutcome({ kind: 'needs_input', title: '请配置模型服务', message: '数据已经就绪，配置模型服务后即可生成绘图任务计划。' })
      setProviderOpen(true)
      return
    }
    if (!api) return
    const requestGeneration = agentRequestGeneration.current + 1
    agentRequestGeneration.current = requestGeneration
    setBusyAction('agent'); setAgentOutcome(undefined); setNotice(undefined)
    try {
      const target = plot ? { kind: 'plot' as const, id: plot.plotId } : undefined
      const selectedDatasets = datasets
        .filter((dataset) => agentDatasetIds.includes(dataset.datasetId) || dataset.datasetId === activeDataset.datasetId)
        .slice(0, 8)
        .map((dataset) => ({ datasetId: dataset.datasetId, sourceVersion: dataset.sourceVersion }))
      const value = valueOrThrow(await api.decideAgent({
        projectId: project.projectId,
        sourceDatasetId: activeDataset.datasetId,
        sourceVersion: activeDataset.sourceVersion,
        selectedDatasets,
        expectedVersion: project.projectVersion,
        ...(selectedChart === undefined ? {} : { selectedChartId: selectedChart.id }),
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

  const syncPlanOutput = async (plan: AgentPlanView): Promise<ProductPlot | undefined> => {
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

  const executeAgentPlan = async (planId: string, resume = false): Promise<void> => {
    if (!api || !project || busyAction !== undefined) return
    const historyEntry = plot && agentPlan?.planId === planId
      ? plotHistoryEntry(plot, agentPlan.boundActions) : undefined
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
      await syncPlanOutput(plan)
      if (plan.state === 'succeeded' && historyEntry) {
        setUndoStack((current) => [...current, historyEntry].slice(-50))
        setRedoStack([])
      }
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
      if (!isJsonRecord(value) || value.state !== 'cancelled') {
        throw new Error('Core did not confirm plan cancellation.')
      }
      setAgentPlan(undefined)
      setAgentOutcome({ kind: 'no_change', title: '计划已取消', message: '未修改任何项目对象。' })
    } catch (error) {
      setAgentOutcome({ kind: 'rejected', title: '计划未取消', message: errorNotice(error).message })
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

  const createBatch = async (): Promise<void> => {
    if (!api || !project || !selectedChart || datasets.length === 0 || !activeDataset) return
    setBusyAction('batch'); setNotice(undefined)
    if (!confirmedMapping) { setNotice({ kind: 'warning', title: '批次尚不能创建', message: '请先确认当前图形的字段映射。' }); setBusyAction(undefined); return }
    try {
      const activeFields = new Map(activeDataset.fields.map((field) => [field.fieldId, field.name]))
      const roles = Object.entries(confirmedMapping.roles).map(([role, fieldId]) => {
        const name = activeFields.get(fieldId)
        if (name === undefined) throw new Error(`当前映射字段已不存在：${fieldId}`)
        return { role, name }
      })
      const batchDatasets = datasets.map((dataset) => {
        if (!dataset.contentHash) throw new Error(`${dataset.displayName} 缺少不可变内容标识。`)
        const byName = new Map<string, string[]>()
        for (const field of dataset.fields) {
          const key = field.name.trim().toLocaleLowerCase('en-US')
          byName.set(key, [...(byName.get(key) ?? []), field.fieldId])
        }
        const bindings = Object.fromEntries(roles.map(({ role, name }) => {
          const matches = byName.get(name.trim().toLocaleLowerCase('en-US')) ?? []
          if (matches.length !== 1) {
            throw new Error(`${dataset.displayName} 无法唯一匹配字段“${name}”，批量计划尚未创建。`)
          }
          return [role, matches[0]]
        }))
        return {
          datasetId: dataset.datasetId,
          sourceVersion: dataset.sourceVersion,
          contentHash: dataset.contentHash,
          bindings,
        }
      })
      const created = valueOrThrow(await api.createPlotBatchPlan({
        projectId: project.projectId,
        datasets: batchDatasets,
        profileId: selectedChart.id,
        expectedProjectVersion: project.projectVersion,
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
  const canUndo = undoStack.at(-1)?.plotId === plot?.plotId
  const canRedo = redoStack.at(-1)?.plotId === plot?.plotId
  const modalOpen = libraryOpen || tasksOpen || providerOpen
  const selectDataset = (datasetId: string): void => {
    invalidateAgentRequest()
    setActiveDatasetId(datasetId)
    const nextAgentDatasetIds = agentDatasetIds.filter((id) => id !== datasetId).slice(0, 7)
    setAgentDatasetIds(nextAgentDatasetIds)
    setConfirmedMapping(undefined)
    setPlot(undefined)
    setPreviousPlot(undefined)
    setAgentPlan(undefined)
    setUndoStack([])
    setRedoStack([])
    rememberWorkspace({ datasetId, agentDatasetIds: nextAgentDatasetIds, mapping: null })
  }
  const toggleAgentDataset = (datasetId: string): void => {
    if (datasetId === activeDataset?.datasetId) return
    const next = agentDatasetIds.includes(datasetId)
      ? agentDatasetIds.filter((id) => id !== datasetId)
      : [...agentDatasetIds, datasetId].slice(0, 7)
    setAgentDatasetIds(next)
    rememberWorkspace({ agentDatasetIds: next })
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
          <ConversationWorkspace key={project?.projectId ?? 'no-project'} core={core} project={project} datasets={datasets} activeDataset={activeDataset} selectedAgentDatasetIds={activeDataset === undefined ? [] : [activeDataset.datasetId, ...agentDatasetIds.filter((id) => id !== activeDataset.datasetId)].slice(0, 8)} selectedChart={selectedChart} plot={plot} exportRecord={exportRecord} notice={notice} busyAction={busyAction} agentRuntimeLabel={agentRuntimeEvent?.projectId === project?.projectId ? agentRuntimeEvent?.label : undefined} agentOutcome={agentOutcome} agentPlan={agentPlan} agentConfigured={agentConfigured} taskEvents={Object.values(taskEvents)} previewMode={previewMode} canUndo={canUndo} canRedo={canRedo} onUndo={() => void undoPlotChange()} onRedo={() => void redoPlotChange()} onOpenSample={() => void openSample()} onImportData={() => void importData()} onOpenProject={() => void openProject()} onOpenLibrary={() => setLibraryOpen(true)} onSelectDataset={selectDataset} onToggleAgentDataset={toggleAgentDataset} onConfirmMapping={(mapping) => void confirmMapping(mapping)} onConfirmCombinedMapping={(mapping) => void confirmCombinedMapping(mapping)} onAgentInstruction={(instruction, scope) => void runAgent(instruction, scope)} onConfirmAgentPlan={(planId) => void confirmAgentPlan(planId)} onRejectAgentPlan={(planId) => void rejectAgentPlan(planId)} onRunAgentPlan={(planId) => void executeAgentPlan(planId)} onResumeAgentPlan={(planId) => void executeAgentPlan(planId, true)} onConfigureAgent={() => setProviderOpen(true)} onExport={(format) => void exportArtifact(format)} onCreateBatch={() => void createBatch()} onOpenFocus={() => void openFocusEditor()} onOpenTasks={() => setTasksOpen(true)} onCancelTask={(taskId) => { if (api) void api.cancelTask(taskId) }} />
        </>}
        {screen === 'focus' && plot && <FocusEditor key={`${plot.plotId}:${plot.plotVersion}`} initialIndex={0} plot={{ ...plot, title: selectedChart?.name ?? plot.chartId }} previousPlot={previousPlot} onPatch={applyPlotPatch} canUndo={canUndo} canRedo={canRedo} onUndo={() => void undoPlotChange()} onRedo={() => void redoPlotChange()} onClose={() => setScreen('workspace')} />}
      </div>
      {libraryOpen && <ChartLibrary currentChartId={selectedChart?.id} datasetCompatibility={chartCompatibility} onClose={() => setLibraryOpen(false)} onSelect={(chart) => {
        setLibraryOpen(false)
        invalidateAgentRequest()
        setSelectedChart(chart); setConfirmedMapping(undefined); setPlot(undefined); setPreviousPlot(undefined); setAgentOutcome(undefined); rememberWorkspace({ chartId: chart.id, mapping: null })
        setUndoStack([]); setRedoStack([])
        setNotice(activeDataset ? undefined : { kind: 'info', title: `已选择 ${chart.name} ${chart.id}`, message: '可以继续上传数据。' })
      }} />}
      {tasksOpen && <TaskDrawer tasks={Object.values(taskEvents)} onCancel={(taskId) => { if (api) void api.cancelTask(taskId) }} onClose={() => setTasksOpen(false)} />}
      {providerOpen && <ProviderSettings busy={busyAction === 'provider'} notice={providerNotice} onClose={() => setProviderOpen(false)} onConfigure={(input) => void configureProvider(input)} />}
    </div>
  )
}
