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
  WorkflowPlotSelection,
} from '../../shared/desktop-contract'
import { MAX_WORKFLOW_SOURCES } from '../../shared/desktop-contract'
import { chartCatalog, type ChartType } from './data/chartCatalog'
import {
  disambiguateDatasetDisplayNames,
  isJsonRecord,
  projectVersionFrom,
  readWorkflowOutcome,
  readWorkflowPlan,
  readWorkflowPlans,
  readDurableTasks,
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
  type DurableTaskView,
  type ProductDataset,
  type ProductPlot,
  type ProductProject,
} from './data/productState'
import { readWorkspaceSelection, writeWorkspaceSelection } from './data/workspacePersistence'
import { plotHistoryEntry, type PlotHistoryEntry } from './data/plotHistory'
import {
  matchProviderPreset,
  providerPreset,
  providerPresets,
  type ProviderPresetId,
} from './data/providerPresets'
import { ChartLibrary } from './components/ChartLibrary'
import {
  ConversationWorkspace,
  type ExportRecordView,
  type ProductNotice,
} from './components/ConversationWorkspace'
import { FocusEditor, type ParameterTab } from './components/FocusEditor'
import { MotionPresence, type MotionPhase } from './components/MotionPresence'
import { Sidebar } from './components/Sidebar'
import { TaskDrawer } from './components/TaskDrawer'
import { useDialogFocus } from './components/useDialogFocus'
import { resolveDesktopRuntime } from './preview/browserPreviewApi'

type Screen = 'workspace' | 'focus'

type ComposerProjection =
  | { kind: 'single'; chartId: string }
  | { kind: 'multi' }

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

function composerProjectionFromPlan(plan: WorkflowPlanView | undefined): ComposerProjection | undefined {
  if (!plan || ['rejected', 'cancelled', 'failed', 'unsupported'].includes(plan.state)) return undefined
  const profileIds = [...new Set(plan.steps.map((step) => step.profileId))]
    .filter((profileId) => chartCatalog.some((chart) => chart.id === profileId))
  if (profileIds.length === 1) return { kind: 'single', chartId: profileIds[0] }
  if (profileIds.length > 1) return { kind: 'multi' }
  return undefined
}

interface ProviderConfigurationView {
  readonly baseUrl: string
  readonly modelId: string
}

function readProviderConfiguration(value: JsonValue): ProviderConfigurationView | undefined {
  if (!isJsonRecord(value)) return undefined
  if (typeof value.endpoint_origin === 'string' && typeof value.model_id === 'string') {
    return { baseUrl: value.endpoint_origin, modelId: value.model_id }
  }
  for (const item of Object.values(value)) {
    const nested = readProviderConfiguration(item)
    if (nested) return nested
  }
  return undefined
}

function readExportRecord(
  value: JsonValue,
  format: 'png' | 'svg' | 'opju',
  target: { kind: 'plot'; id: string; version: number },
): ExportRecordView | undefined {
  if (!isJsonRecord(value) || typeof value.export_id !== 'string') return undefined
  const artifact = isJsonRecord(value.artifact) ? value.artifact : undefined
  const resource = artifact && isJsonRecord(artifact.resource) ? artifact.resource : undefined
  if (
    resource === undefined
    || typeof resource.resourceId !== 'string'
    || typeof resource.fileName !== 'string'
  ) return undefined
  if (
    value.plot_id !== target.id
    || value.plot_version !== target.version
  ) {
    throw new Error('导出返回的图形版本与当前版本不一致，未报告成功。请刷新图形后重试。')
  }
  return {
    exportId: value.export_id,
    resourceId: resource.resourceId,
    fileName: resource.fileName,
    format,
    targetKind: 'plot',
    targetId: target.id,
    plotVersion: target.version,
    ...(artifact && typeof artifact.content_hash === 'string' ? { artifactHash: artifact.content_hash } : {}),
    ...(artifact && typeof artifact.size === 'number' ? { artifactSize: artifact.size } : {}),
  }
}

interface ProviderSettingsProps {
  busy: boolean
  configured?: ProviderConfigurationView
  notice?: ProductNotice
  motionState?: MotionPhase
  onClose: () => void
  onConfigure: (input: CustomProviderConfigureInput) => void
}

function ProviderSettings({ busy, configured, notice, motionState = 'entered', onClose, onConfigure }: ProviderSettingsProps): React.JSX.Element {
  const initialProvider = matchProviderPreset(configured?.baseUrl)
  const initialPreset = providerPreset(initialProvider)
  const configuredPresetModel = initialPreset?.models.find((model) => model.id === configured?.modelId)
  const [providerId, setProviderId] = useState<ProviderPresetId>(initialProvider)
  const [baseUrl, setBaseUrl] = useState(initialProvider === 'custom' ? configured?.baseUrl ?? '' : initialPreset?.baseUrl ?? '')
  const [modelId, setModelId] = useState(
    initialProvider === 'custom'
      ? configured?.modelId ?? ''
      : configuredPresetModel?.id ?? initialPreset?.models[0]?.id ?? '',
  )
  const [apiKey, setApiKey] = useState('')
  const [acknowledged, setAcknowledged] = useState(false)
  const dialogRef = useDialogFocus<HTMLElement>(motionState === 'entered')
  const preset = providerPreset(providerId)
  const effectiveBaseUrl = preset?.baseUrl ?? baseUrl
  const keyRequired = configured?.baseUrl.replace(/\/$/, '') !== effectiveBaseUrl.replace(/\/$/, '')

  const chooseProvider = (nextId: ProviderPresetId): void => {
    setProviderId(nextId)
    const nextPreset = providerPreset(nextId)
    if (nextPreset) {
      setBaseUrl(nextPreset.baseUrl)
      setModelId(nextPreset.models[0]?.id ?? '')
    } else {
      setBaseUrl(initialProvider === 'custom' ? configured?.baseUrl ?? '' : '')
      setModelId(initialProvider === 'custom' ? configured?.modelId ?? '' : '')
    }
  }

  return (
    <div className="provider-settings-layer" data-motion-state={motionState} aria-hidden={motionState === 'exiting' ? true : undefined} inert={motionState === 'exiting' ? true : undefined} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section ref={dialogRef} className="provider-settings" role={motionState === 'entered' ? 'dialog' : undefined} aria-modal={motionState === 'entered' ? true : undefined} aria-labelledby="provider-settings-title" tabIndex={-1}>
        <header><div><h2 id="provider-settings-title">模型服务</h2></div><button className="icon-button" type="button" onClick={onClose} aria-label="关闭模型服务设置"><X size={18} /></button></header>
        <form onSubmit={(event) => {
          event.preventDefault()
          onConfigure({ baseUrl: effectiveBaseUrl, modelId, ...(apiKey ? { apiKey } : {}), retentionAcknowledged: true })
          setApiKey('')
        }}>
          <label>模型厂商<select data-autofocus aria-label="模型厂商" value={providerId} onChange={(event) => chooseProvider(event.target.value as ProviderPresetId)}>{providerPresets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}<option value="custom">自定义兼容服务</option></select></label>
          {preset ? <>
            <label>模型<select aria-label="模型" required value={modelId} onChange={(event) => setModelId(event.target.value)}>{preset.models.map((model) => <option key={model.id} value={model.id}>{model.name} · {model.availability}</option>)}</select></label>
            <p className="provider-preset-note">{preset.description} 连接地址已由 PlotAgent 配置。</p>
          </> : <>
            <label>Base URL<input type="url" required placeholder="https://provider.example/v1 或 http://127.0.0.1:8000/v1" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} /></label>
            <label>Model ID<input type="text" required placeholder="model-id" value={modelId} onChange={(event) => setModelId(event.target.value)} /></label>
          </>}
          <label>API Key{keyRequired ? '' : '（留空沿用已保存密钥）'}<input type="password" required={keyRequired} autoComplete="off" value={apiKey} onChange={(event) => setApiKey(event.target.value)} /></label>
          <label className="provider-retention"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} /><span>我已了解：Agent 会向所选模型服务发送指令、字段元数据和受控样本，保留政策由该服务决定。</span></label>
          {notice && <div className={`provider-inline-status provider-inline-status--${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}><strong>{notice.title}</strong><span>{notice.message}</span></div>}
          <footer><button type="button" onClick={onClose}>稍后配置</button><button className="primary-button" type="submit" disabled={!acknowledged || !effectiveBaseUrl || !modelId || (keyRequired && !apiKey) || busy}>{busy && <LoaderCircle className="spin" size={15} />}保存模型服务</button></footer>
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
  const [projectPlots, setProjectPlots] = useState<ProductPlot[]>([])
  const [previousPlot, setPreviousPlot] = useState<ProductPlot>()
  const [exportRecord, setExportRecord] = useState<ExportRecordView>()
  const [notice, setNotice] = useState<ProductNotice>()
  const [importNotice, setImportNotice] = useState<ProductNotice>()
  const [workflowOutcome, setWorkflowOutcome] = useState<WorkflowOutcome>()
  const [workflowPlan, setWorkflowPlan] = useState<WorkflowPlanView>()
  const [composerProjection, setComposerProjection] = useState<ComposerProjection>()
  const [workflowPlans, setWorkflowPlans] = useState<WorkflowPlanView[]>([])
  const [durableTasks, setDurableTasks] = useState<DurableTaskView[]>([])
  const [agentConfigured, setAgentConfigured] = useState(false)
  const [providerConfiguration, setProviderConfiguration] = useState<ProviderConfigurationView>()
  const [undoStack, setUndoStack] = useState<PlotHistoryEntry[]>([])
  const [redoStack, setRedoStack] = useState<PlotHistoryEntry[]>([])
  const [providerOpen, setProviderOpen] = useState(false)
  const [providerNotice, setProviderNotice] = useState<ProductNotice>()
  const [focusParameterTabs, setFocusParameterTabs] = useState<Record<string, ParameterTab>>({})

  const [libraryOpen, setLibraryOpen] = useState(false)
  const [tasksOpen, setTasksOpen] = useState(false)
  const [busyAction, setBusyAction] = useState<string>()
  const [taskEvents, setTaskEvents] = useState<Record<string, TaskEvent>>({})
  const [agentRuntimeEvent, setAgentRuntimeEvent] = useState<WorkflowRuntimeEvent>()
  const pendingAgentRequest = useRef<{
    instruction: string
    selectedPlots: WorkflowPlotSelection[]
  } | undefined>(
    undefined,
  )
  const [originStatus, setOriginStatus] = useState<'unknown' | 'checking' | 'available' | 'unavailable' | 'exporting'>('unknown')
  const [originDiagnostic, setOriginDiagnostic] = useState('Origin 环境未通过检测。请重新检测后再导出。')
  const importInFlight = useRef(false)
  const agentRequestGeneration = useRef(0)
  const workflowHistorySources = useRef(new Map<string, ProductPlot>())
  const corePhaseRef = useRef<CoreStatus['phase']>(initialCore.phase)

  useEffect(() => {
    if (notice?.kind !== 'success') return
    const timer = window.setTimeout(() => setNotice(undefined), 8_000)
    return () => window.clearTimeout(timer)
  }, [notice])

  const activeDataset = datasets.find((dataset) => dataset.datasetId === activeDatasetId) ?? datasets[0]
  const projectedChart = composerProjection?.kind === 'single'
    ? chartCatalog.find((chart) => chart.id === composerProjection.chartId)
    : undefined
  const composerChart = composerProjection?.kind === 'multi'
    ? undefined
    : projectedChart ?? selectedChart
  const composerIsMultiChart = composerProjection?.kind === 'multi'
  const durableTaskIds = new Set(durableTasks.map((task) => task.taskId))
  const agentRuntimeTaskCount = agentRuntimeEvent
    && agentRuntimeEvent.projectId === project?.projectId
    && agentRuntimeEvent.taskId !== undefined
    && !['completed', 'cancelled', 'failed'].includes(agentRuntimeEvent.stage)
    && !durableTaskIds.has(agentRuntimeEvent.taskId)
    && taskEvents[agentRuntimeEvent.taskId] === undefined ? 1 : 0
  const taskCount = durableTasks.filter((task) => !['completed_verified', 'cancelled', 'rejected', 'failed', 'unsupported'].includes(task.state)).length
    + Object.values(taskEvents).filter((event) => !durableTaskIds.has(event.taskId) && !['succeeded', 'failed', 'cancelled', 'partially_succeeded', 'interrupted'].includes(event.state)).length
    + agentRuntimeTaskCount
  const activeProjectId = project?.projectId

  const mergeDurableResult = useCallback((value: JsonValue): void => {
    const nextTasks = readDurableTasks(value)
    if (nextTasks.length > 0) {
      setDurableTasks((current) => {
        const byId = new Map(current.map((task) => [task.taskId, task]))
        for (const task of nextTasks) byId.set(task.taskId, task)
        return [...byId.values()]
      })
    }
    const nextPlan = readWorkflowPlan(value)
    if (nextPlan) {
      setWorkflowPlans((current) => {
        const byId = new Map(current.map((plan) => [plan.planId, plan]))
        byId.set(nextPlan.planId, nextPlan)
        return [...byId.values()]
      })
    }
  }, [])

  const mergeProjectPlot = useCallback((nextPlot: ProductPlot): void => {
    setProjectPlots((current) => {
      const existingIndex = current.findIndex((item) => item.plotId === nextPlot.plotId)
      if (existingIndex < 0) return [...current, nextPlot]
      const updated = [...current]
      updated[existingIndex] = nextPlot.plotVersion >= updated[existingIndex].plotVersion
        ? nextPlot
        : updated[existingIndex]
      return updated
    })
  }, [])

  const projectWorkflowPlan = useCallback((nextPlan: WorkflowPlanView | undefined): void => {
    setWorkflowPlan(nextPlan)
    setComposerProjection(composerProjectionFromPlan(nextPlan))
  }, [])

  useEffect(() => {
    if (!api || !project) return
    const requiredDatasetIds = new Set([
      ...(activeDataset === undefined ? [] : [activeDataset.datasetId]),
      ...(workflowPlan?.steps.flatMap((step) => step.sourceDatasetIds) ?? []),
    ])
    const pending = datasets.filter((dataset) => (
      requiredDatasetIds.has(dataset.datasetId)
      && dataset.sampleRows === undefined
      && !dataset.samplePreviewUnavailable
    ))
    if (pending.length === 0) return
    let active = true
    const markUnavailable = (datasetId: string, sourceVersion: number): void => {
      if (!active) return
      setDatasets((current) => current.map((dataset) => (
        dataset.datasetId === datasetId && dataset.sourceVersion === sourceVersion
          ? { ...dataset, samplePreviewUnavailable: true }
          : dataset
      )))
    }
    void Promise.all(pending.map(async (candidate) => {
      try {
        const result = await api.describeDataset({
          projectId: project.projectId,
          datasetId: candidate.datasetId,
          sourceVersion: candidate.sourceVersion,
        })
        if (!active) return
        if (!result.ok) {
          markUnavailable(candidate.datasetId, candidate.sourceVersion)
          return
        }
        const described = readDatasets(result.value).find((dataset) => (
          dataset.datasetId === candidate.datasetId
          && dataset.sourceVersion === candidate.sourceVersion
        ))
        if (!described || described.sampleRows === undefined) {
          markUnavailable(candidate.datasetId, candidate.sourceVersion)
          return
        }
        setDatasets((current) => current.map((dataset) => (
          dataset.datasetId === described.datasetId
          && dataset.sourceVersion === described.sourceVersion
            ? { ...dataset, ...described }
            : dataset
        )))
      } catch {
        markUnavailable(candidate.datasetId, candidate.sourceVersion)
      }
    }))
    return () => { active = false }
  }, [activeDataset, api, datasets, project, workflowPlan])

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
      workflowSourceIds: selection.workflowSourceIds ?? workflowSourceIds,
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
    plots: ProductPlot[]
    notice?: ProductNotice
  }> => {
    if (!api) return { plots: [] }
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
      if (!latest) return { plots, notice: removedNotice }
      const stored = valueOrThrow(await api.getPlot({
        projectId,
        plotId: latest.plotId,
        plotVersion: latest.plotVersion,
      }))
      const recovered = readPlot(stored) ?? latest
      return {
        plot: recovered,
        plots: plots.map((item) => item.plotId === recovered.plotId ? recovered : item),
        notice: removedNotice,
      }
    } catch (error) {
      return {
        plots: [],
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
      const tasks = readDurableTasks(result.value)
      const latest = plans.at(-1)
      setWorkflowPlans(plans)
      setDurableTasks(tasks)
      projectWorkflowPlan(latest)
      const restoredOutcome = readWorkflowOutcome(result.value)
      if (restoredOutcome.kind === 'needs_input') setWorkflowOutcome(restoredOutcome)
    })
    return () => { active = false }
  }, [api, activeProjectId, projectWorkflowPlan])

  useEffect(() => {
    if (!api || !activeProjectId || !agentRuntimeEvent) return
    if (!['completed', 'cancelled', 'failed'].includes(agentRuntimeEvent.stage)) return
    let active = true
    void api.listTaskPlans({ projectId: activeProjectId }).then((result) => {
      if (!active || !result.ok) return
      setWorkflowPlans(readWorkflowPlans(result.value))
      setDurableTasks(readDurableTasks(result.value))
    })
    return () => { active = false }
  }, [api, activeProjectId, agentRuntimeEvent])

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
      if (active && result.ok) {
        setAgentConfigured(readProviderConfigured(result.value))
        setProviderConfiguration(readProviderConfiguration(result.value))
      }
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
      setWorkflowSourceIds(nextDatasets.slice(1, MAX_WORKFLOW_SOURCES).map((dataset) => dataset.datasetId))
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
    setProjectPlots([])
    setPreviousPlot(undefined)
    setExportRecord(undefined)
    setImportNotice(undefined)
    setWorkflowOutcome(undefined)
    setWorkflowPlan(undefined)
    setComposerProjection(undefined)
    setWorkflowPlans([])
    setDurableTasks([])
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

  const restoreProjectAfterCoreRestart = useEffectEvent(async (): Promise<void> => {
    if (!api || !project) return
    const projectId = project.projectId
    setBusyAction('core-recovery')
    setNotice({ kind: 'warning', title: '正在恢复项目', message: '本地 Core 已重启，正在重新打开当前项目。' })
    try {
      const opened = valueOrThrow(await api.activateProject({ projectId }))
      const nextProject = projectWithVersion(project, projectVersionFrom(opened, project.projectVersion))
      setProject(nextProject)
      mergeProjects([nextProject])

      const listed = valueOrThrow(await api.listDatasets({ projectId }))
      const restoredDatasets = disambiguateDatasetDisplayNames(readDatasets(listed))
      const availableIds = new Set(restoredDatasets.map((dataset) => dataset.datasetId))
      setDatasets(restoredDatasets)
      setActiveDatasetId((current) => (
        current !== undefined && availableIds.has(current)
          ? current
          : restoredDatasets[0]?.datasetId
      ))
      setWorkflowSourceIds((current) => current.filter((id) => availableIds.has(id)))

      const recovery = await recoverLatestPlot(projectId)
      setPlot(recovery.plot)
      setProjectPlots(recovery.plots)
      setPreviousPlot(undefined)
      setSelectedChart(recovery.plot
        ? chartCatalog.find((chart) => chart.id === recovery.plot?.chartId)
        : selectedChart)
      setNotice(recovery.notice ?? {
        kind: 'success',
        title: '项目已恢复',
        message: '本地 Core 已重新连接，当前项目和图形版本已恢复。',
      })
    } catch (error) {
      setNotice({
        kind: 'error',
        title: '项目恢复未完成',
        message: `${errorNotice(error).message} 请从左侧重新打开项目。`,
      })
    } finally {
      setBusyAction((current) => current === 'core-recovery' ? undefined : current)
    }
  })

  const projectCoreStatus = useEffectEvent((status: CoreStatus): void => {
    const previous = corePhaseRef.current
    corePhaseRef.current = status.phase
    setCore(status)
    if (status.phase === 'ready' && previous !== 'ready' && project !== undefined) {
      void restoreProjectAfterCoreRestart()
    }
  })

  useEffect(() => {
    if (!api) return
    let active = true
    void api.getBootstrap().then((bootstrap) => {
      if (!active) return
      projectCoreStatus(bootstrap.core)
    }).catch((error: unknown) => { if (active) setNotice(errorNotice(error)) })
    const unsubCore = api.onCoreStatus(projectCoreStatus)
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
        setProjectPlots(recovery.plots)
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
      setWorkflowSourceIds(imported.slice(1, MAX_WORKFLOW_SOURCES).map((dataset) => dataset.datasetId))
    } else if (imported.length > 0) {
      setWorkflowSourceIds((current) => [...new Set([
        ...current,
        ...imported.map((dataset) => dataset.datasetId),
      ])].filter((datasetId) => datasetId !== activeDatasetId).slice(0, MAX_WORKFLOW_SOURCES - 1))
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
    const nextImportNotice: ProductNotice | undefined = partial ? {
      kind: 'warning',
      title: '部分文件未导入',
      message: outcomeLines.join('\n'),
      actionLabel: summary.attentionCount > 0 ? '继续处理' : '重新选择文件',
      onAction: () => { retryImportIntoProject(targetProject) },
    } : undefined
    setImportNotice(nextImportNotice)
    setNotice(partial ? undefined : {
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
    setImportNotice(undefined)
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
    setBusyAction('sample'); setNotice(undefined); setImportNotice(undefined)
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
    setBusyAction('import'); setNotice(undefined); setImportNotice(undefined)
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
    setBusyAction('open-project'); setNotice(undefined); setImportNotice(undefined)
    try {
      const value = valueOrThrow(await api.openProject())
      const nextProject = hydrateProject(value)
      let recoveryNotice: ProductNotice | undefined
      if (nextProject) {
        const listed = valueOrThrow(await api.listDatasets({ projectId: nextProject.projectId }))
        hydrateProject(listed, nextProject.name, nextProject)
        const recovery = await recoverLatestPlot(nextProject.projectId)
        setPlot(recovery.plot)
        setProjectPlots(recovery.plots)
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
    setBusyAction('activate-project'); setNotice(undefined); setImportNotice(undefined)
    try {
      const known = projects.find((item) => item.projectId === projectId)
      const opened = valueOrThrow(await api.activateProject({ projectId }))
      const next = { ...(known ?? { projectId, name: '本机项目', projectVersion: 0, isOpen: true }), projectVersion: projectVersionFrom(opened, 0), isOpen: true }
      setProject(next); mergeProjects([next])
      setDatasets([]); setActiveDatasetId(undefined); setWorkflowSourceIds([])
      setPlot(undefined); setProjectPlots([]); setPreviousPlot(undefined); setSelectedChart(undefined); setConfirmedMapping(undefined)
      setWorkflowPlan(undefined); setWorkflowOutcome(undefined); setComposerProjection(undefined); setExportRecord(undefined)

      let datasetNotice: ProductNotice | undefined
      try {
        const listed = valueOrThrow(await api.listDatasets({ projectId }))
        const nextDatasets = readDatasets(listed)
      const persisted = readWorkspaceSelection(window.localStorage, projectId)
      const nextDataset = nextDatasets.find((item) => item.datasetId === persisted?.datasetId) ?? nextDatasets[0]
      const availableDatasetIds = new Set(nextDatasets.map((item) => item.datasetId))
      const nextWorkflowSourceIds = (
        persisted?.workflowSourceIds
        ?? nextDatasets.map((dataset) => dataset.datasetId)
      )
        .filter((datasetId) => availableDatasetIds.has(datasetId) && datasetId !== nextDataset?.datasetId)
        .slice(0, MAX_WORKFLOW_SOURCES - 1)
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
      setProjectPlots(recovery.plots)
      if (recovery.plot) {
        setPlot(recovery.plot)
        setSelectedChart(chartCatalog.find((chart) => chart.id === recovery.plot?.chartId))
      }
      if (recovery.notice) setNotice(recovery.notice)
      else if (datasetNotice) setNotice(datasetNotice)
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const confirmMapping = async (mapping: FieldMappingInput): Promise<void> => {
    if (!api || !project || !activeDataset || !composerChart) return
    setConfirmedMapping(mapping)
    rememberWorkspace({
      datasetId: activeDataset.datasetId,
      chartId: composerChart.id,
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
          profile_id: composerChart.id,
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
      mergeProjectPlot(nextPlot)
      setPreviousPlot(undefined)
      setUndoStack([])
      setRedoStack([])
      setProject(projectWithVersion(project, projectVersionFrom(created, project.projectVersion + 1)))
      setNotice({
        kind: 'success',
        title: '绘图完成',
        message: previewMode
          ? `${composerChart.name} ${composerChart.id} 已按确认映射生成界面预览。`
          : `${composerChart.name} ${composerChart.id} 已按确认映射创建，预览来自本地 Core。`,
      })
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const confirmMultiSourceMapping = async (mapping: FieldMappingInput): Promise<void> => {
    if (!api || !project || !activeDataset || !composerChart) return
    const selectedIds = [activeDataset.datasetId, ...workflowSourceIds.filter((id) => id !== activeDataset.datasetId)].slice(0, MAX_WORKFLOW_SOURCES)
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
        selectedProfileIds: [composerChart.id],
        expectedProjectVersion: project.projectVersion,
        instruction: `将这些数据表合并绘制在同一张 ${composerChart.id} ${composerChart.name} 中；字段角色为 ${roleDescription.join('、')}；保留数据来源分组。`,
      }))
      mergeDurableResult(created)
      setConfirmedMapping(mapping)
      const outcome = readWorkflowOutcome(created)
      projectWorkflowPlan(outcome.plan)
      setWorkflowOutcome(outcome)
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const runAgent = async (
    instruction: string,
    selectedPlots: WorkflowPlotSelection[],
  ): Promise<void> => {
    if (!project) return
    if (!activeDataset && selectedPlots.length === 0) {
      pendingAgentRequest.current = { instruction, selectedPlots }
      setWorkflowOutcome({ kind: 'needs_input', title: '请先上传数据', message: '收到你的要求了。上传数据后，我会继续声明字段绑定。' })
      return
    }
    const continuationPlan = workflowOutcome?.kind === 'task_plan'
      ? workflowOutcome.plan ?? workflowPlan
      : workflowPlan
    const continuationWorkflowRunId = workflowOutcome?.kind === 'needs_input'
      ? workflowOutcome.workflowRunId
      : continuationPlan?.taskId !== undefined
        && ['awaiting_confirmation', 'awaiting_reconfirmation', 'partially_succeeded']
          .includes(continuationPlan.state)
        ? continuationPlan.taskId
        : undefined
    if (!api) return
    pendingAgentRequest.current = undefined
    const selectedHistorySource = selectedPlots.length === 1
      ? [plot, ...projectPlots].find((candidate) => (
          candidate?.plotId === selectedPlots[0].plotId
          && candidate.plotVersion === selectedPlots[0].plotVersion
        ))
      : selectedPlots.length === 0 ? plot : undefined
    const requestGeneration = agentRequestGeneration.current + 1
    agentRequestGeneration.current = requestGeneration
    setBusyAction('agent'); setWorkflowOutcome(undefined); setWorkflowPlan(undefined); setNotice(undefined)
    try {
      const selectedIds = activeDataset === undefined ? [] : [
        activeDataset.datasetId,
        ...workflowSourceIds.filter((id) => id !== activeDataset.datasetId),
      ].slice(0, MAX_WORKFLOW_SOURCES)
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
        ...(composerChart === undefined || selectedPlots.length > 0 || (
          continuationWorkflowRunId !== undefined && workflowOutcome?.kind !== 'needs_input'
        )
          ? {}
          : { selectedProfileIds: [composerChart.id] }),
        ...(selectedPlots.length === 0 ? {} : { selectedPlots }),
        ...(continuationWorkflowRunId === undefined ? {} : { continuationWorkflowRunId }),
        instruction,
      }))
      if (agentRequestGeneration.current !== requestGeneration) return
      mergeDurableResult(value)
      const outcome = readWorkflowOutcome(value)
      if (outcome.plan && selectedHistorySource) {
        workflowHistorySources.current.set(outcome.plan.planId, selectedHistorySource)
      }
      projectWorkflowPlan(outcome.plan)
      setWorkflowOutcome(outcome)
    } catch (error) {
      if (agentRequestGeneration.current === requestGeneration) {
        setWorkflowOutcome({ kind: 'rejected', title: '指令未执行', message: errorNotice(error).message })
        const listed = await api.listTaskPlans({ projectId: project.projectId })
        if (listed.ok) {
          setWorkflowPlans(readWorkflowPlans(listed.value))
          setDurableTasks(readDurableTasks(listed.value))
        }
      }
    } finally {
      if (agentRequestGeneration.current === requestGeneration) setBusyAction(undefined)
    }
  }
  const resumePendingAgent = useEffectEvent(
    (pending: { instruction: string; selectedPlots: WorkflowPlotSelection[] }) => {
      void runAgent(pending.instruction, pending.selectedPlots)
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
    mergeProjectPlot(nextPlot)
    setPreviousPlot(plot)
    setProject(projectWithVersion(project, Math.max(project.projectVersion, nextPlot.projectVersion)))
    return nextPlot
  }

  const executeWorkflowPlan = async (
    planId: string,
    resume = false,
    historySourceOverride?: ProductPlot,
  ): Promise<void> => {
    if (!api || !project || busyAction !== undefined) return
    const historySourcePlot = historySourceOverride ?? plot
    setBusyAction('agent-plan')
    setNotice(undefined)
    setWorkflowPlan((current) => current?.planId === planId ? { ...current, state: 'running' } : current)
    try {
      const value = valueOrThrow(resume
        ? await api.resumeTaskPlan({ projectId: project.projectId, planId })
        : await api.runTaskPlan({ projectId: project.projectId, planId }))
      mergeDurableResult(value)
      const outcome = readWorkflowOutcome(value)
      if (outcome.kind === 'needs_input') {
        const stored = await api.getTaskPlan({ projectId: project.projectId, planId })
        const pendingPlan = stored.ok ? readWorkflowPlan(stored.value) : undefined
        if (pendingPlan) {
          projectWorkflowPlan(pendingPlan)
          await syncPlanOutput(pendingPlan)
        }
        setWorkflowOutcome(outcome)
        return
      }
      const plan = readWorkflowPlan(value)
      if (!plan) throw new Error('Core 未返回任务计划状态。')
      projectWorkflowPlan(plan)
      const nextPlot = await syncPlanOutput(plan)
      const historyActions = historySourcePlot && nextPlot?.plotId === historySourcePlot.plotId
        ? [
            ...(plan.steps.some((step) => (
              step.taskKind === 'update_data'
              && step.outputPlot?.plotId === historySourcePlot.plotId
            )) ? [{
                operation: 'bind_fields',
                target: historySourcePlot.plotId,
                data: nextPlot.engineData,
                bindings: nextPlot.engineBindings,
              } satisfies JsonValue] : []),
            ...plan.boundActions,
          ]
        : []
      const historyEntry = historySourcePlot
        && nextPlot
        ? plotHistoryEntry(historySourcePlot, nextPlot, historyActions)
        : undefined
      if ((plan.state === 'succeeded' || plan.state === 'completed_with_skips') && historyEntry) {
        setUndoStack((current) => [...current, historyEntry].slice(-50))
        setRedoStack([])
      }
      if (plan.state === 'succeeded' || plan.state === 'completed_with_skips' || plan.state === 'failed') {
        workflowHistorySources.current.delete(planId)
      }
      setWorkflowOutcome({
        kind: 'task_plan',
        title: plan.state === 'succeeded'
          ? '任务已完成'
          : plan.state === 'completed_with_skips'
            ? '任务已完成（含跳过项）'
            : plan.state === 'partially_succeeded'
              ? '任务等待处理'
              : plan.state === 'failed' ? '任务失败' : '任务未完成',
        message: plan.state === 'succeeded'
          ? '更改已保存为可追溯版本。'
          : plan.state === 'completed_with_skips'
            ? '成功项已保留，未执行或失败项已按你的选择跳过。'
            : plan.state === 'failed'
              ? '任务已停止。请查看失败项诊断，修改要求后创建新任务。'
              : '已保留完成项，可继续处理未完成步骤。',
        plan,
      })
      if (plan.state === 'succeeded' || plan.state === 'completed_with_skips') setNotice(undefined)
    } catch (error) {
      const stored = await api.getTaskPlan({ projectId: project.projectId, planId })
      if (stored.ok) projectWorkflowPlan(readWorkflowPlan(stored.value))
      setWorkflowOutcome({ kind: 'rejected', title: '计划未执行', message: errorNotice(error).message })
    } finally {
      setBusyAction(undefined)
    }
  }

  const cancelTask = async (taskId: string): Promise<void> => {
    if (!api || !project) return
    const result = await api.cancelTask(taskId)
    if (!result.ok) {
      setNotice(failureNotice(result.error))
      return
    }
    const listed = await api.listTaskPlans({ projectId: project.projectId })
    const refreshedDurable = listed.ok ? readDurableTasks(listed.value) : durableTasks
    if (listed.ok) {
      setWorkflowPlans(readWorkflowPlans(listed.value))
      setDurableTasks(refreshedDurable)
    }
    if (agentRuntimeEvent?.taskId === taskId) {
      invalidateAgentRequest()
      const retainedCount = refreshedDurable
        .find((task) => task.taskId === taskId)
        ?.items.filter((item) => item.state === 'succeeded').length ?? 0
      if (retainedCount === 0) setComposerProjection(undefined)
      setWorkflowOutcome({
        kind: 'no_change',
        title: '任务已取消',
        message: retainedCount > 0
          ? `任务已停止，已保留 ${retainedCount} 项成功结果。`
          : '任务已停止，项目未发生更改。',
      })
    }
  }

  const acceptPartialTask = async (taskId: string): Promise<void> => {
    if (!api || !project || busyAction !== undefined) return
    setBusyAction('agent-plan')
    try {
      const result = await api.acceptPartialTask(taskId)
      if (!result.ok) {
        setNotice(failureNotice(result.error))
        return
      }
      const listed = await api.listTaskPlans({ projectId: project.projectId })
      if (!listed.ok) {
        setNotice(failureNotice(listed.error))
        return
      }
      const plans = readWorkflowPlans(listed.value)
      const durable = readDurableTasks(listed.value)
      setWorkflowPlans(plans)
      setDurableTasks(durable)
      const completed = plans.find((plan) => plan.taskId === taskId)
      if (completed) {
        projectWorkflowPlan(completed)
        setWorkflowOutcome({
          kind: 'task_plan',
          title: '任务已完成（含跳过项）',
          message: '成功项已保留，未完成项已按你的选择跳过。',
          plan: completed,
        })
      }
      setNotice(undefined)
    } finally {
      setBusyAction(undefined)
    }
  }

  const resumeAgentTask = async (taskId: string): Promise<void> => {
    if (!api || !project) return
    setBusyAction('agent'); setNotice(undefined)
    try {
      const value = valueOrThrow(await api.resumeAgentTask(taskId))
      mergeDurableResult(value)
      const outcome = readWorkflowOutcome(value)
      projectWorkflowPlan(outcome.plan)
      setWorkflowOutcome(outcome)
      const listed = await api.listTaskPlans({ projectId: project.projectId })
      if (listed.ok) {
        setWorkflowPlans(readWorkflowPlans(listed.value))
        setDurableTasks(readDurableTasks(listed.value))
      }
    } catch (error) {
      setNotice(errorNotice(error))
    } finally {
      setBusyAction(undefined)
    }
  }

  const confirmWorkflowPlan = async (planId: string): Promise<void> => {
    if (!api || !project || busyAction !== undefined) return
    // React state projection of the confirmed plan is asynchronous. Preserve the
    // exact pre-execution plot here instead of trying to recover it from the next
    // render, otherwise Agent edits never enter the shared undo history.
    const historySourcePlot = workflowHistorySources.current.get(planId) ?? plot
    setBusyAction('agent-plan')
    let confirmedPlan: WorkflowPlanView | undefined
    try {
      const confirmed = valueOrThrow(await api.confirmTaskPlan({ projectId: project.projectId, planId, accept: true }))
      mergeDurableResult(confirmed)
      confirmedPlan = readWorkflowPlan(confirmed)
      if (confirmedPlan) projectWorkflowPlan(confirmedPlan)
      if (confirmedPlan?.state === 'succeeded') {
        setWorkflowOutcome(readWorkflowOutcome(confirmed))
      }
    } catch (error) {
      setWorkflowOutcome({ kind: 'rejected', title: '计划未确认', message: errorNotice(error).message })
      setBusyAction(undefined)
      return
    }
    setBusyAction(undefined)
    if (confirmedPlan?.state === 'succeeded') return
    await executeWorkflowPlan(planId, false, historySourcePlot)
  }

  const rejectWorkflowPlan = async (planId: string): Promise<void> => {
    if (!api || !project || busyAction !== undefined) return
    setBusyAction('agent-plan')
    try {
      const value = valueOrThrow(await api.confirmTaskPlan({ projectId: project.projectId, planId, accept: false }))
      mergeDurableResult(value)
      const rejectedPlan = readWorkflowPlan(value)
      if ((rejectedPlan?.state ?? (isJsonRecord(value) ? value.state : undefined)) !== 'rejected') {
        throw new Error('Core did not confirm plan cancellation.')
      }
      if (rejectedPlan) setWorkflowPlan(rejectedPlan)
      else setWorkflowPlan(undefined)
      workflowHistorySources.current.delete(planId)
      setComposerProjection(undefined)
      const retainedCount = rejectedPlan?.completedCount ?? 0
      setWorkflowOutcome({
        kind: 'no_change',
        title: '计划已拒绝',
        message: retainedCount > 0
          ? `未执行修订计划；已保留此前完成的 ${retainedCount} 项结果。`
          : '未执行计划，项目未发生更改。',
      })
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
      mergeProjectPlot(nextPlot)
      setPreviousPlot(plot)
      setProject(projectWithVersion(project, projectVersionFrom(value, project.projectVersion + 1)))
      const historyEntry = plotHistoryEntry(plot, nextPlot, [patch])
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
    try {
      const value = valueOrThrow(await api.restorePlotVersion({
        projectId: project.projectId,
        expectedProjectVersion: project.projectVersion,
        plotId: plot.plotId,
        expectedPlotVersion: plot.plotVersion,
        sourcePlotVersion: direction === 'undo'
          ? entry.undoPlotVersion
          : entry.redoPlotVersion,
        actionId: `action:ui.${direction}.${crypto.randomUUID()}`,
      }))
      const nextPlot = readPlot(value)
      if (!nextPlot) throw new Error('Core 未返回恢复后的 PlotDocument。')
      const nextProjectVersion = projectVersionFrom(value, project.projectVersion + 1)
      setPlot(nextPlot)
      mergeProjectPlot(nextPlot)
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
  }, [api, busyAction, mergeProjectPlot, plot, project])

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
    let exportPlot = plot
    if (format === 'opju' && originStatus === 'unavailable') {
      setNotice({ kind: 'error', title: 'Origin 不可用', message: originDiagnostic })
      return
    }
    if (format === 'opju' && originStatus !== 'available' && !await refreshOriginStatus(true)) return
    setBusyAction(`export-${format}`); setNotice(undefined); setExportRecord(undefined)
    if (format === 'opju') setOriginStatus('exporting')
    try {
      const listedValue = valueOrThrow(await api.listPlots({ projectId: project.projectId }))
      const durable = readPlots(listedValue).find((candidate) => candidate.plotId === plot.plotId)
      if (!durable) {
        const stored = valueOrThrow(await api.getPlot({
          projectId: project.projectId,
          plotId: plot.plotId,
          plotVersion: plot.plotVersion,
        }))
        const exact = readPlot(stored)
        if (!exact || exact.plotId !== plot.plotId || exact.plotVersion !== plot.plotVersion) {
          throw new Error('Core 中找不到当前界面显示的图形版本，已停止导出。')
        }
        exportPlot = exact
      }
      if (durable && durable.plotVersion < plot.plotVersion) {
        throw new Error('Core 中的图形版本落后于当前界面，已停止导出以避免写出错误版本。')
      }
      if (durable && durable.plotVersion > plot.plotVersion) {
        const stored = valueOrThrow(await api.getPlot({
          projectId: project.projectId,
          plotId: durable.plotId,
          plotVersion: durable.plotVersion,
        }))
        const synchronized = readPlot(stored)
        if (!synchronized || synchronized.plotId !== durable.plotId || synchronized.plotVersion !== durable.plotVersion) {
          throw new Error('无法核对当前图形的最新耐久版本，已停止导出。')
        }
        exportPlot = synchronized
        setPreviousPlot(plot)
        setPlot(synchronized)
        mergeProjectPlot(synchronized)
        setProject(projectWithVersion(project, projectVersionFrom(listedValue, project.projectVersion)))
      }
      const target = { kind: 'plot' as const, id: exportPlot.plotId, version: exportPlot.plotVersion }
      const result = format === 'opju'
        ? await api.exportOrigin({ projectId: project.projectId, target })
        : await api.exportPngSvg({ projectId: project.projectId, target, format })
      const exported = valueOrThrow(result)
      const completedExport = readExportRecord(exported, format, target)
      if (completedExport === undefined || completedExport.artifactHash === undefined || completedExport.artifactSize === undefined) {
        throw new Error('导出结果缺少可验证的文件记录，未报告成功。请重试导出。')
      }
      setExportRecord(completedExport)
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
    if (!api || !project || !composerChart || datasets.length === 0 || !activeDataset) return
    const selectedIds = [
      activeDataset.datasetId,
      ...workflowSourceIds.filter((id) => id !== activeDataset.datasetId),
    ].slice(0, MAX_WORKFLOW_SOURCES)
    const selectedBatchDatasets = selectedIds.flatMap((datasetId) => {
      const dataset = datasets.find((candidate) => candidate.datasetId === datasetId)
      return dataset === undefined ? [] : [dataset]
    })
    setBusyAction('batch'); setNotice(undefined)
    try {
      const created = valueOrThrow(await api.runWorkflow({
        projectId: project.projectId,
        selectedSources: selectedBatchDatasets.map((dataset) => ({
          datasetId: dataset.datasetId,
          sourceVersion: dataset.sourceVersion,
        })),
        selectedProfileIds: [composerChart.id],
        expectedProjectVersion: project.projectVersion,
        instruction: `分别为每个数据表创建 ${composerChart.id} ${composerChart.name}，保持原始数据不变。`,
      }))
      mergeDurableResult(created)
      const outcome = readWorkflowOutcome(created)
      projectWorkflowPlan(outcome.plan)
      setWorkflowOutcome(outcome)
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const openExportResource = async (resourceId: string, reveal = false): Promise<void> => {
    if (!api) return
    const result = reveal
      ? await api.revealExportResource({ resourceId })
      : await api.openExportResource({ resourceId })
    if (!result.ok) setNotice(failureNotice(result.error))
  }

  const configureProvider = async (input: CustomProviderConfigureInput): Promise<void> => {
    if (!api) return
    setBusyAction('provider'); setProviderNotice(undefined)
    try {
      const value = valueOrThrow(await api.configureCustomProvider(input))
      setAgentConfigured(readProviderConfigured(value))
      setProviderConfiguration({ baseUrl: input.baseUrl, modelId: input.modelId })
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
    const nextWorkflowSourceIds = [...new Set([
      ...(activeDataset && activeDataset.datasetId !== datasetId ? [activeDataset.datasetId] : []),
      ...workflowSourceIds,
    ])].filter((id) => id !== datasetId).slice(0, MAX_WORKFLOW_SOURCES - 1)
    setWorkflowSourceIds(nextWorkflowSourceIds)
    setConfirmedMapping(undefined)
    setPlot(undefined)
    setPreviousPlot(undefined)
    setWorkflowPlan(undefined)
    setComposerProjection(undefined)
    setUndoStack([])
    setRedoStack([])
    rememberWorkspace({ datasetId, workflowSourceIds: nextWorkflowSourceIds, mapping: null })
  }
  const toggleWorkflowSource = (datasetId: string): void => {
    if (datasetId === activeDataset?.datasetId) return
    const next = workflowSourceIds.includes(datasetId)
      ? workflowSourceIds.filter((id) => id !== datasetId)
      : [...workflowSourceIds, datasetId].slice(0, MAX_WORKFLOW_SOURCES - 1)
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
          <ConversationWorkspace key={project?.projectId ?? 'no-project'} core={core} project={project} datasets={datasets} activeDataset={activeDataset} selectedWorkflowSourceIds={activeDataset === undefined ? [] : [activeDataset.datasetId, ...workflowSourceIds.filter((id) => id !== activeDataset.datasetId)].slice(0, MAX_WORKFLOW_SOURCES)} selectedChart={composerChart} multiChartTask={composerIsMultiChart} plot={plot} projectPlots={projectPlots} exportRecord={exportRecord} notice={notice} importNotice={importNotice} busyAction={busyAction} agentRuntimeLabel={agentRuntimeEvent?.projectId === project?.projectId ? agentRuntimeEvent?.label : undefined} agentRuntimeTaskId={agentRuntimeEvent?.projectId === project?.projectId ? agentRuntimeEvent?.taskId : undefined} agentRuntimeStartedAt={agentRuntimeEvent?.projectId === project?.projectId ? agentRuntimeEvent?.startedAt : undefined} workflowOutcome={workflowOutcome} workflowPlan={workflowPlan} agentConfigured={agentConfigured} taskEvents={Object.values(taskEvents)} previewMode={previewMode} canUndo={canUndo} canRedo={canRedo} onUndo={() => void undoPlotChange()} onRedo={() => void redoPlotChange()} onOpenSample={() => void openSample()} onImportData={() => void importData()} onOpenProject={() => void openProject()} onOpenLibrary={() => setLibraryOpen(true)} onSelectDataset={selectDataset} onToggleWorkflowSource={toggleWorkflowSource} onConfirmMapping={(mapping) => void confirmMapping(mapping)} onConfirmMultiSourceMapping={(mapping) => void confirmMultiSourceMapping(mapping)} onAgentInstruction={(instruction, selectedPlots) => void runAgent(instruction, selectedPlots)} onConfirmWorkflowPlan={(planId) => void confirmWorkflowPlan(planId)} onRejectWorkflowPlan={(planId) => void rejectWorkflowPlan(planId)} onRunWorkflowPlan={(planId) => void executeWorkflowPlan(planId)} onResumeWorkflowPlan={(planId) => void executeWorkflowPlan(planId, true)} onConfigureAgent={() => setProviderOpen(true)} onExport={(format) => void exportArtifact(format)} onOpenExport={(resourceId) => void openExportResource(resourceId)} onRevealExport={(resourceId) => void openExportResource(resourceId, true)} onCreateBatch={() => void createBatch()} onOpenFocus={() => void openFocusEditor()} onOpenTasks={() => setTasksOpen(true)} onCancelTask={(taskId) => { void cancelTask(taskId) }} onAcceptPartialTask={(taskId) => { void acceptPartialTask(taskId) }} />
        </>}
        {screen === 'focus' && plot && <FocusEditor key={`${plot.plotId}:${plot.plotVersion}`} initialIndex={0} plot={{ ...plot, title: chartCatalog.find((chart) => chart.id === plot.chartId)?.name ?? plot.chartId }} previousPlot={previousPlot} onPatch={applyPlotPatch} canUndo={canUndo} canRedo={canRedo} onUndo={() => void undoPlotChange()} onRedo={() => void redoPlotChange()} onExport={(format) => void exportArtifact(format)} initialPanelOpen simplePanel initialParameterTab={focusParameterTabs[plot.plotId]} onParameterTabChange={(tab) => setFocusParameterTabs((current) => ({ ...current, [plot.plotId]: tab }))} onClose={() => setScreen('workspace')} />}
      </div>
      {libraryOpen && <ChartLibrary currentChartId={composerChart?.id} datasetCompatibility={chartCompatibility} onClose={() => setLibraryOpen(false)} onSelect={(chart) => {
        setLibraryOpen(false)
        invalidateAgentRequest()
        const answersPendingQuestion = workflowOutcome?.kind === 'needs_input'
        setSelectedChart(chart); setComposerProjection(undefined); setConfirmedMapping(undefined); setPlot(undefined); setPreviousPlot(undefined)
        if (!answersPendingQuestion) setWorkflowOutcome(undefined)
        rememberWorkspace({ chartId: chart.id, mapping: null })
        setUndoStack([]); setRedoStack([])
        setNotice(activeDataset ? undefined : { kind: 'info', title: `已选择 ${chart.name} ${chart.id}`, message: '可以继续上传数据。' })
      }} />}
      <MotionPresence present={tasksOpen} exitMs={160}>
        {(motionState) => <TaskDrawer motionState={motionState} tasks={Object.values(taskEvents)} durableTasks={durableTasks} plans={workflowPlans} runtimeEvent={agentRuntimeEvent?.projectId === project?.projectId ? agentRuntimeEvent : undefined} onCancel={(taskId) => { void cancelTask(taskId) }} onAcceptPartial={(taskId) => { void acceptPartialTask(taskId) }} onResumeTask={(taskId) => { void resumeAgentTask(taskId) }} onRetryPlan={(planId) => { void executeWorkflowPlan(planId, true) }} onClose={() => setTasksOpen(false)} />}
      </MotionPresence>
      <MotionPresence present={providerOpen} exitMs={140}>
        {(motionState) => <ProviderSettings motionState={motionState} busy={busyAction === 'provider'} configured={providerConfiguration} notice={providerNotice} onClose={() => setProviderOpen(false)} onConfigure={(input) => void configureProvider(input)} />}
      </MotionPresence>
    </div>
  )
}
