import { useCallback, useEffect, useMemo, useState } from 'react'
import { Check, FlaskConical, LoaderCircle, X } from 'lucide-react'

import type {
  CoreStatus,
  CustomProviderConfigureInput,
  DesktopDataResult,
  FieldMappingInput,
  JsonValue,
  TaskEvent,
} from '../../shared/desktop-contract'
import type { ChartType } from './data/chartCatalog'
import {
  isJsonRecord,
  projectVersionFrom,
  readAgentOutcome,
  readDatasets,
  readPlot,
  readProject,
  readProjects,
  resultKind,
  resultMessage,
  withPreview,
  type AgentOutcome,
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
  type FigureView,
  type ProductNotice,
  type ScopeMode,
} from './components/ConversationWorkspace'
import { FocusEditor } from './components/FocusEditor'
import { Sidebar } from './components/Sidebar'
import { TaskDrawer } from './components/TaskDrawer'
import { useDialogFocus } from './components/useDialogFocus'

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
  const taskId = typeof value.task_id === 'string' ? value.task_id : undefined
  if (!batchId || !taskId) return undefined
  const rawItems = Array.isArray(value.items) ? value.items : []
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
        <header><div><h2 id="provider-settings-title">模型服务</h2><p>只在首次使用 Agent 时配置，不影响本地绘图与导出。</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="关闭模型服务设置"><X size={18} /></button></header>
        <div className="provider-build-note"><strong>内置服务</strong><span>当前构建未配置可用端点，可使用 OpenAI-compatible 自定义服务。</span></div>
        <form onSubmit={(event) => {
          event.preventDefault()
          onConfigure({ baseUrl, modelId, ...(apiKey ? { apiKey } : {}), retentionAcknowledged: true })
          setApiKey('')
        }}>
          <label>Base URL<input data-autofocus type="url" required placeholder="https://provider.example/v1 或 http://127.0.0.1:8000/v1" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} /></label>
          <label>Model ID<input required placeholder="model-id" value={modelId} onChange={(event) => setModelId(event.target.value)} /></label>
          <label>API key（可选）<input type="password" autoComplete="off" value={apiKey} onChange={(event) => setApiKey(event.target.value)} /><small>提交后只写入系统凭据库，不回显到界面或项目。</small></label>
          <label className="provider-retention"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} /><span>我已了解：Agent 会向所选模型服务发送指令、字段元数据和受控样本，保留政策由该服务决定。</span></label>
          {notice && <div className={`provider-inline-status provider-inline-status--${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}><strong>{notice.title}</strong><span>{notice.message}</span></div>}
          <footer><button type="button" onClick={onClose}>稍后配置</button><button className="primary-button" type="submit" disabled={!acknowledged || !baseUrl || !modelId || busy}>{busy && <LoaderCircle className="spin" size={15} />}保存模型服务</button></footer>
        </form>
      </section>
    </div>
  )
}

export function App(): React.JSX.Element {
  const api = window.plotAgentDesktop
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
  const [plotHistory, setPlotHistory] = useState<ProductPlot[]>([])
  const [batch, setBatch] = useState<BatchView>()
  const [figure, setFigure] = useState<FigureView>()
  const [notice, setNotice] = useState<ProductNotice>()
  const [agentOutcome, setAgentOutcome] = useState<AgentOutcome>()
  const [agentConfigured, setAgentConfigured] = useState(false)
  const [providerOpen, setProviderOpen] = useState(false)
  const [providerNotice, setProviderNotice] = useState<ProductNotice>()
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [tasksOpen, setTasksOpen] = useState(false)
  const [busyAction, setBusyAction] = useState<string>()
  const [taskEvents, setTaskEvents] = useState<Record<string, TaskEvent>>({})
  const [originStatus, setOriginStatus] = useState<'unknown' | 'available' | 'unavailable' | 'exporting'>('unknown')

  const activeDataset = datasets.find((dataset) => dataset.datasetId === activeDatasetId) ?? datasets[0]
  const taskCount = Object.values(taskEvents).filter((event) => !['succeeded', 'failed', 'cancelled', 'partially_succeeded', 'interrupted'].includes(event.state)).length

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

  useEffect(() => {
    if (!api) return
    let active = true
    void Promise.all([api.getBootstrap(), api.listProjects(), api.getProviderStatus()]).then(([bootstrap, projectResult, providerResult]) => {
      if (!active) return
      setCore(bootstrap.core)
      if (projectResult.ok) setProjects(readProjects(projectResult.value))
      if (providerResult.ok) setAgentConfigured(readProviderConfigured(providerResult.value))
    }).catch((error: unknown) => { if (active) setNotice(errorNotice(error)) })
    const unsubCore = api.onCoreStatus((status) => setCore(status))
    const unsubTasks = api.onTaskEvent((event) => setTaskEvents((current) => ({ ...current, [event.taskId]: event })))
    const unsubOpen = api.onOpenResourceRequested((request) => {
      setBusyAction('open-project')
      void api.openProjectResource({ resourceId: request.resourceId }).then((result) => {
        const value = valueOrThrow(result)
        hydrateProject(value)
        setNotice({ kind: 'success', title: '项目已打开', message: '已从受控项目资源恢复本地会话。' })
      }).catch((error: unknown) => setNotice(errorNotice(error))).finally(() => setBusyAction(undefined))
    })
    return () => { active = false; unsubCore(); unsubTasks(); unsubOpen() }
  }, [api, hydrateProject])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.ctrlKey && event.key.toLocaleLowerCase('en-US') === 'n') {
        event.preventDefault(); setProject(undefined); setDatasets([]); setPlot(undefined); setSelectedChart(undefined); setConfirmedMapping(undefined); setScreen('workspace')
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
  }, [libraryOpen, providerOpen, screen, tasksOpen])

  const importIntoProject = async (targetProject: ProductProject): Promise<void> => {
    if (!api) return
    const value = valueOrThrow(await api.importDatasets({ projectId: targetProject.projectId }))
    const importKind = resultKind(value)
    if (importKind === 'clarification' || importKind === 'needs_input') {
      setNotice({ kind: 'warning', title: '导入需要确认', message: resultMessage(value) ?? 'Core 无法唯一确定表头、分隔符或小数格式，请按提示重新导入。' })
      return
    }
    if (importKind === 'rejection' || importKind === 'rejected') {
      setNotice({ kind: 'error', title: '数据未导入', message: resultMessage(value) ?? 'Core 判定该文件不属于支持的数值数据格式。' })
      return
    }
    const imported = readDatasets(value)
    setDatasets((current) => [...new Map([...current, ...imported].map((item) => [`${item.datasetId}:${item.sourceVersion}`, item])).values()])
    if (imported[0]) setActiveDatasetId(imported[0].datasetId)
    const version = projectVersionFrom(value, targetProject.projectVersion)
    const nextProject = projectWithVersion(targetProject, version)
    setProject(nextProject); mergeProjects([nextProject])
    setSelectedChart(undefined); setConfirmedMapping(undefined); setPlot(undefined)
    setNotice({ kind: 'success', title: '数据已导入', message: `本地 Core 返回 ${imported.length} 个工作表或数据块，请检查字段与质量摘要。` })
  }

  const openSample = async (): Promise<void> => {
    if (!api) return
    setBusyAction('sample'); setNotice(undefined)
    try {
      const value = valueOrThrow(await api.openSampleProject())
      hydrateProject(value, '温度响应示例')
      setNotice({ kind: 'success', title: '示例项目已创建', message: '内置 CSV 已通过真实导入路径复制到新的本地项目。' })
      await refreshProjects()
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const importData = async (): Promise<void> => {
    if (!api) return
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
    } finally { setBusyAction(undefined) }
  }

  const openProject = async (): Promise<void> => {
    if (!api) return
    setBusyAction('open-project'); setNotice(undefined)
    try {
      const value = valueOrThrow(await api.openProject())
      const nextProject = hydrateProject(value)
      if (nextProject) {
        const listed = valueOrThrow(await api.listDatasets({ projectId: nextProject.projectId }))
        hydrateProject(listed, nextProject.name, nextProject)
      }
      setNotice({ kind: 'success', title: '项目已打开', message: '.plotproj 已由 Main 授权并交给本地 Core 校验。' })
      await refreshProjects()
    } catch (error) {
      if (typeof error === 'object' && error !== null && 'code' in error && error.code === 'DIALOG_CANCELLED') setNotice(undefined)
      else setNotice(errorNotice(error))
    } finally { setBusyAction(undefined) }
  }

  const activateProject = async (projectId: string): Promise<void> => {
    if (!api || project?.projectId === projectId) return
    setBusyAction('activate-project'); setNotice(undefined)
    try {
      const known = projects.find((item) => item.projectId === projectId)
      const opened = valueOrThrow(await api.activateProject({ projectId }))
      const listed = valueOrThrow(await api.listDatasets({ projectId }))
      const next = { ...(known ?? { projectId, name: '本机项目', projectVersion: 0, isOpen: true }), projectVersion: projectVersionFrom(opened, 0), isOpen: true }
      setProject(next); setDatasets(readDatasets(listed)); setActiveDatasetId(readDatasets(listed)[0]?.datasetId)
      setPlot(undefined); setSelectedChart(undefined); setConfirmedMapping(undefined); setBatch(undefined); setFigure(undefined)
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
      setPlot(nextPlot); setPlotHistory((current) => [...current.filter((item) => item.plotId !== nextPlot!.plotId), nextPlot!])
      setProject(projectWithVersion(project, projectVersionFrom(created, project.projectVersion + 1)))
      setNotice({ kind: 'success', title: '绘图完成', message: `${selectedChart.name} ${selectedChart.id} 已按确认映射创建，预览来自本地 Core。` })
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const runAgent = async (instruction: string, scope: ScopeMode): Promise<void> => {
    if (!api || !project || !activeDataset || !plot) return
    setBusyAction('agent'); setAgentOutcome(undefined)
    try {
      const target = scope === 'batch'
        ? batch ? { kind: 'batch' as const, id: batch.batchId } : undefined
        : scope === 'figure'
          ? figure ? { kind: 'figure' as const, id: figure.figureId } : undefined
          : { kind: 'plot' as const, id: plot.plotId }
      if (!target) {
        setAgentOutcome({ kind: 'rejected', title: '作用对象不可用', message: scope === 'batch' ? '请先创建并运行一个批次。' : '请先创建组合图。' })
        return
      }
      const value = valueOrThrow(await api.decideAgent({
        projectId: project.projectId,
        sourceDatasetId: activeDataset.datasetId,
        sourceVersion: activeDataset.sourceVersion,
        expectedVersion: project.projectVersion,
        target,
        scope,
        utterance: instruction,
      }))
      const outcome = readAgentOutcome(value)
      if (outcome.execution) {
        const rendered = valueOrThrow(await api.renderPlot({ projectId: project.projectId, plotId: outcome.execution.plotId, plotVersion: outcome.execution.plotVersion, mode: 'preview' }))
        const executed = withPreview(outcome.execution, rendered)
        outcome.execution = executed
        setPlot(executed); setPlotHistory((current) => [...current, executed])
      } else if (outcome.scopeExecution?.kind === 'batch' && batch?.batchId === outcome.scopeExecution.id) {
        setBatch({
          ...batch,
          version: outcome.scopeExecution.version,
          items: outcome.scopeExecution.batchItems.length > 0 ? outcome.scopeExecution.batchItems : batch.items,
        })
      } else if (outcome.scopeExecution?.kind === 'figure' && figure?.figureId === outcome.scopeExecution.id) {
        let updatedFigure: FigureView = { ...figure, version: outcome.scopeExecution.version }
        try {
          const rendered = valueOrThrow(await api.renderFigure({ projectId: project.projectId, figureId: figure.figureId }))
          updatedFigure = { ...updatedFigure, ...readFigure(rendered), version: outcome.scopeExecution.version }
        } catch {
          updatedFigure = { figureId: figure.figureId, version: outcome.scopeExecution.version }
          outcome.message += ' 组合图版本已更新，但新预览暂不可用。'
        }
        setFigure(updatedFigure)
      }
      setProject(projectWithVersion(project, projectVersionFrom(value, project.projectVersion + 1)))
      setAgentOutcome(outcome)
    } catch (error) { setAgentOutcome({ kind: 'rejected', title: '指令未执行', message: errorNotice(error).message }) } finally { setBusyAction(undefined) }
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
      setPlotHistory((current) => [...current, nextPlot!])
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
    const target = explicitTarget ?? { kind: 'plot' as const, id: plot!.plotId, version: plot!.plotVersion }
    setBusyAction(`export-${format}`); setNotice(undefined)
    if (format === 'opju') setOriginStatus('exporting')
    try {
      const result = format === 'opju'
        ? await api.exportOrigin({ projectId: project.projectId, target })
        : await api.exportPngSvg({ projectId: project.projectId, target, format })
      valueOrThrow(result)
      if (format === 'opju') setOriginStatus('available')
      setNotice({ kind: 'success', title: `已导出 ${format.toLocaleUpperCase('en-US')}`, message: '文件已写入你在系统对话框中授权的位置。' })
    } catch (error) {
      if (format === 'opju') setOriginStatus('unavailable')
      if (!(typeof error === 'object' && error !== null && 'code' in error && error.code === 'DIALOG_CANCELLED')) setNotice(errorNotice(error))
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
      const createdBatch = readBatch(created)
      if (!createdBatch) throw new Error('Core 未返回批次任务。')
      const completed = valueOrThrow(await api.runBatch({ projectId: project.projectId, taskId: createdBatch.taskId, expectedVersion: projectVersionFrom(created, project.projectVersion) }))
      setBatch(readBatch(completed) ?? createdBatch)
      setProject(projectWithVersion(project, projectVersionFrom(completed, project.projectVersion)))
      setNotice({ kind: 'success', title: '批次已执行', message: '每个同构数据集使用同一字段映射，成功与失败项由 Core 分别返回。' })
    } catch (error) { setNotice(errorNotice(error)) } finally { setBusyAction(undefined) }
  }

  const createFigure = async (): Promise<void> => {
    if (!api || !project) return
    const uniquePlots = [...new Map(plotHistory.map((item) => [`${item.plotId}:${item.plotVersion}`, item])).values()]
    if (uniquePlots.length < 2) {
      setNotice({ kind: 'info', title: '还需要一张图', message: '组合图固定引用 2 至 4 个真实 PlotSpec 版本，请先再创建一张图。' })
      return
    }
    setBusyAction('figure'); setNotice(undefined)
    try {
      const created = valueOrThrow(await api.createFigure({ projectId: project.projectId, plotRefs: uniquePlots.slice(-2).map((item) => ({ plotId: item.plotId, plotVersion: item.plotVersion })), layout: '1x2', expectedVersion: project.projectVersion }))
      let nextFigure = readFigure(created)
      if (!nextFigure) throw new Error('Core 未返回 FigureSpec。')
      const rendered = valueOrThrow(await api.renderFigure({ projectId: project.projectId, figureId: nextFigure.figureId }))
      nextFigure = { ...nextFigure, ...readFigure(rendered) }
      setFigure(nextFigure); setProject(projectWithVersion(project, projectVersionFrom(created, project.projectVersion + 1)))
      setNotice({ kind: 'success', title: '组合图已创建', message: '面板固定引用源图版本，预览来自本地 Core。' })
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
  const availablePlotCount = useMemo(() => new Set(plotHistory.map((item) => `${item.plotId}:${item.plotVersion}`)).size, [plotHistory])
  const modalOpen = libraryOpen || tasksOpen || providerOpen

  return (
    <div className="app-shell">
      <a className="skip-link" href="#conversation-main">跳到绘图对话</a>
      <div className="app-titlebar" aria-hidden="true"><FlaskConical size={13} /><span>PlotAgent</span><span className="titlebar-context">本地科研绘图工作台</span></div>
      <div className="app-surface" inert={modalOpen ? true : undefined}>
        {screen === 'workspace' && <>
          <Sidebar projects={projects} activeProjectId={project?.projectId} core={core} taskCount={taskCount} originStatus={originStatus} onProjectChange={(id) => void activateProject(id)} onNewProject={() => { setProject(undefined); setDatasets([]); setPlot(undefined); setSelectedChart(undefined); setConfirmedMapping(undefined) }} onTaskCenter={() => setTasksOpen(true)} onConfigureAgent={() => setProviderOpen(true)} />
          <ConversationWorkspace core={core} project={project} datasets={datasets} activeDataset={activeDataset} selectedChart={selectedChart} plot={plot} batch={batch} figure={figure} notice={notice} busyAction={busyAction} agentOutcome={agentOutcome} agentConfigured={agentConfigured} onOpenSample={() => void openSample()} onImportData={() => void importData()} onOpenProject={() => void openProject()} onOpenLibrary={() => setLibraryOpen(true)} onSelectDataset={(id) => { setActiveDatasetId(id); setSelectedChart(undefined); setConfirmedMapping(undefined); setPlot(undefined) }} onConfirmMapping={(mapping) => void confirmMapping(mapping)} onAgentInstruction={(instruction, scope) => void runAgent(instruction, scope)} onConfigureAgent={() => setProviderOpen(true)} onExport={(format, target) => void exportArtifact(format, target)} onCreateBatch={() => void createBatch()} onCreateFigure={() => void createFigure()} onOpenFocus={() => setScreen('focus')} onOpenBatchInspect={() => setScreen('batch-inspector')} onOpenCompose={() => setScreen('composition')} onOpenTasks={() => setTasksOpen(true)} />
        </>}
        {screen === 'focus' && plot && <FocusEditor key={`${plot.plotId}:${plot.plotVersion}`} initialIndex={0} plot={{ ...plot, title: selectedChart?.name ?? plot.chartId }} onPatch={applyPlotPatch} onClose={() => setScreen('workspace')} />}
        {screen === 'composition' && figure && <CompositionEditor figure={figure} onClose={() => setScreen('workspace')} />}
        {screen === 'batch-inspector' && batch && <BatchInspector batch={batch} onClose={() => setScreen('workspace')} />}
      </div>
      {libraryOpen && <ChartLibrary currentChartId={selectedChart?.id} availablePlotCount={availablePlotCount} datasetCompatibility={chartCompatibility} onClose={() => setLibraryOpen(false)} onSelect={(chart) => {
        setLibraryOpen(false)
        if (chart.id === 'K25') { void createFigure(); return }
        setSelectedChart(chart); setConfirmedMapping(undefined); setPlot(undefined); setAgentOutcome(undefined)
        setNotice({ kind: 'info', title: `已选择 ${chart.name} ${chart.id}`, message: '下一步请确认一次字段映射。' })
      }} />}
      {tasksOpen && <TaskDrawer tasks={Object.values(taskEvents)} onCancel={(taskId) => { if (api) void api.cancelTask(taskId) }} onClose={() => setTasksOpen(false)} />}
      {providerOpen && <ProviderSettings busy={busyAction === 'provider'} notice={providerNotice} onClose={() => setProviderOpen(false)} onConfigure={(input) => void configureProvider(input)} />}
      {notice?.kind === 'success' && <div className="toast" role="status"><Check size={15} />{notice.title}</div>}
    </div>
  )
}
