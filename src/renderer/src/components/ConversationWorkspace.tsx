import { useState } from 'react'
import {
  Activity,
  ArchiveRestore,
  ArrowRight,
  AtSign,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  Columns3,
  Download,
  FileChartColumn,
  FileOutput,
  FileSpreadsheet,
  FolderOpen,
  History,
  Images,
  Layers3,
  Library,
  LoaderCircle,
  MoreHorizontal,
  MousePointer2,
  Paperclip,
  Play,
  RotateCcw,
  SendHorizontal,
  Sparkles,
  TableProperties,
  TriangleAlert,
} from 'lucide-react'

import type { ConversationId } from './Sidebar'
import { BatchPlot } from './PlotVisuals'

export type ScopeMode = 'current' | 'selected' | 'batch'

interface ConversationWorkspaceProps {
  activeConversation: ConversationId
  selectedChartName: string
  onOpenLibrary: () => void
  onOpenFocus: (index: number) => void
  onOpenCompose: () => void
  onOpenTasks: () => void
  onOpenSample: () => void
  onOpenResources: () => void
}

const scopeLabels: Record<ScopeMode, string> = {
  current: '当前图',
  selected: '选中图',
  batch: '整个批次',
}

const batchItems = [
  { file: 'sample_A_25C.csv', title: 'Sample A · 25 °C', series: 'control' as const, status: 'success' as const },
  { file: 'sample_B_37C.csv', title: 'Sample B · 37 °C', series: 'treated' as const, status: 'success' as const },
  { file: 'sample_C_42C.csv', title: 'Sample C · 42 °C', series: 'recovery' as const, status: 'success' as const },
  { file: 'sample_D_50C.csv', title: 'Sample D · 50 °C', series: 'treated' as const, status: 'failed' as const },
]

function DatasetObject(): React.JSX.Element {
  return (
    <section className="object-block dataset-object" aria-labelledby="dataset-title">
      <header className="object-header">
        <span className="object-icon object-icon--data" aria-hidden="true"><FileSpreadsheet size={17} /></span>
        <div>
          <h3 id="dataset-title">temperature_series.zip</h3>
          <p>数据集 · 4 个 CSV · 结构一致</p>
        </div>
        <span className="status-label status-label--success"><Check size={13} />已解析</span>
        <button className="icon-button" type="button" aria-label="数据集更多操作"><MoreHorizontal size={17} /></button>
      </header>
      <div className="dataset-stats" aria-label="数据集摘要">
        <span><strong>4</strong> 文件</span>
        <span><strong>9,624</strong> 行</span>
        <span><strong>5</strong> 列</span>
        <span><strong>0.12%</strong> 缺失</span>
        <span><strong>2.1 MB</strong> 本地副本</span>
      </div>
      <div className="schema-strip" role="table" aria-label="字段与类型">
        <div role="row" className="schema-row schema-row--heading">
          <span role="columnheader">字段</span><span role="columnheader">类型</span><span role="columnheader">单位</span><span role="columnheader">预览</span>
        </div>
        {[
          ['time', '数值', 'min', '0, 5, 10 …'],
          ['fluorescence', '数值', 'a.u.', '0.142, 0.188 …'],
          ['condition', '分类', '—', 'Control, Treated'],
        ].map((row) => (
          <div role="row" className="schema-row" key={row[0]}>
            {row.map((cell) => <span role="cell" key={cell}>{cell}</span>)}
          </div>
        ))}
      </div>
      <footer className="object-footer">
        <span><ArchiveRestore size={14} />原始数据只读</span>
        <button type="button">查看 4 个文件 <ArrowRight size={14} /></button>
      </footer>
    </section>
  )
}

function MappingObject({ selectedChartName }: { selectedChartName: string }): React.JSX.Element {
  return (
    <section className="object-block mapping-object" aria-labelledby="mapping-title">
      <header className="object-header">
        <span className="object-icon object-icon--mapping" aria-hidden="true"><TableProperties size={17} /></span>
        <div>
          <h3 id="mapping-title">字段映射</h3>
          <p>{selectedChartName || '线点图'} · 应用于 4 个同构文件</p>
        </div>
        <span className="status-label status-label--neutral">一次确认</span>
      </header>
      <div className="mapping-grid">
        <div className="mapping-slot">
          <span className="mapping-role">X 轴</span>
          <strong>time</strong>
          <span>数值 · min</span>
          <CheckCircle2 size={15} aria-label="字段兼容" />
        </div>
        <div className="mapping-arrow" aria-hidden="true"><ArrowRight size={16} /></div>
        <div className="mapping-slot">
          <span className="mapping-role">Y 轴</span>
          <strong>fluorescence</strong>
          <span>数值 · a.u.</span>
          <CheckCircle2 size={15} aria-label="字段兼容" />
        </div>
        <div className="mapping-arrow" aria-hidden="true"><ArrowRight size={16} /></div>
        <div className="mapping-slot">
          <span className="mapping-role">系列</span>
          <strong>condition</strong>
          <span>分类 · 2 水平</span>
          <CheckCircle2 size={15} aria-label="字段兼容" />
        </div>
      </div>
      <div className="validation-row">
        <CircleCheck size={15} />单位兼容，所有文件字段结构一致
        <button type="button">调整映射</button>
      </div>
    </section>
  )
}

interface BatchObjectProps {
  onOpenFocus: (index: number) => void
  onOpenCompose: () => void
}

function BatchObject({ onOpenFocus, onOpenCompose }: BatchObjectProps): React.JSX.Element {
  const [selected, setSelected] = useState<number[]>([0])

  const toggleSelection = (index: number): void => {
    setSelected((current) => current.includes(index) ? current.filter((item) => item !== index) : [...current, index])
  }

  return (
    <section className="object-block batch-object" aria-labelledby="batch-title">
      <header className="object-header">
        <span className="object-icon object-icon--batch" aria-hidden="true"><Images size={17} /></span>
        <div>
          <h3 id="batch-title">温度响应 · 批次 B-024</h3>
          <p>线点图 · 统一样式 · 各图独立坐标范围</p>
        </div>
        <span className="status-label status-label--warning"><CircleAlert size={13} />部分完成</span>
        <button className="text-button" type="button" onClick={onOpenCompose}><Columns3 size={15} />创建组合图</button>
      </header>

      <div className="batch-summary">
        <div className="progress-track" aria-label="批次进度 75%"><span style={{ width: '75%' }} /></div>
        <span>3 张成功</span><span>1 张失败</span><span>用时 18.4 秒</span>
      </div>

      <div className="batch-gallery" aria-label="批量图集">
        {batchItems.map((item, index) => (
          <article className={`batch-tile${selected.includes(index) ? ' is-selected' : ''}${item.status === 'failed' ? ' is-failed' : ''}`} key={item.file}>
            {item.status === 'success' ? (
              <button className="plot-open" type="button" onClick={() => onOpenFocus(index)} aria-label={`聚焦编辑 ${item.title}`}>
                <BatchPlot title={item.title} series={item.series} />
              </button>
            ) : (
              <div className="failed-plot" role="status">
                <TriangleAlert size={23} />
                <strong>列类型校验失败</strong>
                <span>fluorescence 含 7 个文本值</span>
                <button type="button"><RotateCcw size={14} />修复后重试</button>
              </div>
            )}
            <footer>
              <label>
                <input
                  type="checkbox"
                  checked={selected.includes(index)}
                  onChange={() => toggleSelection(index)}
                  aria-label={`选择 ${item.file}`}
                />
                <span>{item.file}</span>
              </label>
              <span className={`mini-status mini-status--${item.status}`}>{item.status === 'success' ? 'v3' : '失败'}</span>
            </footer>
          </article>
        ))}
      </div>

      <footer className="object-footer batch-footer">
        <span><MousePointer2 size={14} />已选 {selected.length} 张</span>
        <button type="button" disabled={selected.length === 0}>修改选中图</button>
        <button type="button">比较版本</button>
        <button type="button"><Download size={14} />导出图集</button>
      </footer>
    </section>
  )
}

function VersionAndExport(): React.JSX.Element {
  return (
    <div className="result-ledger" aria-label="版本、发表规格与导出结果">
      <section>
        <div className="ledger-icon"><History size={16} /></div>
        <div>
          <strong>图表版本 v3</strong>
          <p>线宽 0.8 pt，图例移至右上，保留单图坐标覆盖</p>
        </div>
        <button type="button">撤销</button>
      </section>
      <section>
        <div className="ledger-icon"><FileChartColumn size={16} /></div>
        <div>
          <strong>Nature · 双栏规格</strong>
          <p>183 mm · 300 DPI · 规则版本 2026.07</p>
        </div>
        <span className="status-label status-label--success"><Check size={13} />通过</span>
      </section>
      <section>
        <div className="ledger-icon"><FileOutput size={16} /></div>
        <div>
          <strong>已导出 6 个文件</strong>
          <p>3 PNG + 3 SVG · D:\exports\temperature_series</p>
        </div>
        <button type="button">打开目录</button>
      </section>
      <section className="ledger-warning">
        <div className="ledger-icon"><TriangleAlert size={16} /></div>
        <div>
          <strong>.opju 未导出</strong>
          <p>未检测到可授权 Origin，其他格式不受影响</p>
        </div>
        <button type="button">检查环境</button>
      </section>
    </div>
  )
}

function EmptyConversation({ onOpenSample }: { onOpenSample: () => void }): React.JSX.Element {
  return (
    <div className="empty-conversation">
      <div className="empty-mark" aria-hidden="true"><Sparkles size={23} /></div>
      <h2>从一份真实数据开始</h2>
      <p>拖入 CSV、XLSX、文件夹或 ZIP。数据会复制到本机项目中，原始内容保持只读。</p>
      <button className="drop-target" type="button">
        <FolderOpen size={24} />
        <strong>拖入数据，或选择文件</strong>
        <span>支持 CSV、TSV、TXT、DAT 与 XLSX</span>
      </button>
      <div className="empty-actions">
        <button type="button" onClick={onOpenSample}><Play size={15} />打开温度响应示例</button>
        <button type="button"><Library size={15} />先浏览图形库</button>
      </div>
      <div className="environment-checks" aria-label="环境检查">
        <span><CircleCheck size={14} />本机存储可用</span>
        <span><CircleCheck size={14} />模型服务已连接</span>
        <span className="is-warning"><TriangleAlert size={14} />Origin 不可用</span>
      </div>
    </div>
  )
}

interface ComposerProps {
  selectedChartName: string
  onOpenLibrary: () => void
  onOpenResources: () => void
}

function Composer({ selectedChartName, onOpenLibrary, onOpenResources }: ComposerProps): React.JSX.Element {
  const [scope, setScope] = useState<ScopeMode>('batch')
  const [value, setValue] = useState('')
  const [referencesOpen, setReferencesOpen] = useState(false)
  const [activity, setActivity] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  const send = (): void => {
    const text = value.trim()
    if (!text) return
    setActivity((current) => [...current, text])
    setValue('')
    setBusy(true)
    window.setTimeout(() => setBusy(false), 850)
  }

  return (
    <div className="composer-wrap">
      {activity.length > 0 && (
        <div className="ephemeral-activity" aria-live="polite">
          <div className="user-command"><span>{activity.at(-1)}</span><small>作用于：{scopeLabels[scope]}</small></div>
          {busy ? (
            <div className="agent-pending"><LoaderCircle className="spin" size={16} />正在校验并应用可逆样式修改…</div>
          ) : (
            <div className="agent-complete"><CircleCheck size={16} />已创建版本 v4，3 张图的图例已统一移动到左上角。<button type="button">撤销</button></div>
          )}
        </div>
      )}
      <div className="composer" aria-label="绘图指令输入">
        <div className="composer-context">
          <span className="target-chip"><Layers3 size={14} />作用对象：绘图批次 B-024</span>
          <div className="scope-switch" aria-label="作用范围">
            {(Object.keys(scopeLabels) as ScopeMode[]).map((mode) => (
              <button className={scope === mode ? 'is-active' : ''} key={mode} type="button" onClick={() => setScope(mode)} aria-pressed={scope === mode}>{scopeLabels[mode]}</button>
            ))}
          </div>
        </div>
        <textarea
          value={value}
          onChange={(event) => {
            setValue(event.target.value)
            setReferencesOpen(event.target.value.endsWith('@'))
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              send()
            }
          }}
          placeholder="描述要修改的内容，例如：把选中图的图例移到左上角"
          aria-label="描述绘图或修改要求"
        />
        {referencesOpen && (
          <div className="reference-menu" role="listbox" aria-label="引用对象">
            <div>引用项目对象</div>
            <button className="reference-library-entry" type="button" role="option" aria-selected="false" onClick={() => { setReferencesOpen(false); onOpenResources() }}>
              <Library size={15} /><span><strong>浏览项目资源库</strong><small>搜索全部项目对象</small></span><ArrowRight size={14} />
            </button>
            {[
              ['temperature_series.zip', '数据集', FileSpreadsheet],
              ['温度响应 · B-024', '绘图批次', Images],
              ['Sample A · v3', '图表', FileChartColumn],
            ].map(([name, type, Icon]) => (
              <button key={String(name)} type="button" role="option" aria-selected="false" onClick={() => { setValue((current) => `${current}${String(name)} `); setReferencesOpen(false) }}>
                <Icon size={15} /><span><strong>{String(name)}</strong><small>{String(type)}</small></span>
              </button>
            ))}
          </div>
        )}
        <div className="composer-toolbar">
          <button type="button" aria-label="导入文件"><Paperclip size={17} /></button>
          <button type="button" onClick={onOpenLibrary}><Library size={17} /><span>图形库</span></button>
          <button type="button" onClick={() => setReferencesOpen((open) => !open)} aria-expanded={referencesOpen}><AtSign size={17} /><span>引用</span></button>
          <span className="chosen-chart">图形：{selectedChartName || '线点图 K02'}</span>
          <button className="send-button" type="button" onClick={send} disabled={!value.trim()} aria-label="发送绘图指令"><SendHorizontal size={17} /></button>
        </div>
      </div>
      <p className="composer-note">Agent 只执行明确指令；统计与拟合需由你指定。项目已自动保存到本机。</p>
    </div>
  )
}

export function ConversationWorkspace({
  activeConversation,
  selectedChartName,
  onOpenLibrary,
  onOpenFocus,
  onOpenCompose,
  onOpenTasks,
  onOpenSample,
  onOpenResources,
}: ConversationWorkspaceProps): React.JSX.Element {
  const isEmpty = activeConversation === 'empty'
  const title = activeConversation === 'dose' ? '剂量反应曲线' : activeConversation === 'empty' ? '新对话' : '温度响应批量绘图'

  return (
    <main className="workspace-main">
      <header className="workspace-header">
        <div className="workspace-heading">
          <button className="project-resource-trigger" type="button" onClick={onOpenResources} aria-label="打开项目资源库：温度响应实验">
            <span>温度响应实验</span><Library size={12} />
          </button>
          <h1>{title}</h1>
        </div>
        <div className="workspace-header__actions">
          <button type="button"><FileChartColumn size={15} />Nature · 双栏<ChevronDown size={14} /></button>
          <button type="button" onClick={onOpenTasks}><Activity size={15} /><span className="live-dot" />2 个后台任务</button>
          <span className="autosave-status"><CircleCheck size={14} />已自动保存</span>
          <button className="icon-button" type="button" aria-label="对话更多操作"><MoreHorizontal size={18} /></button>
        </div>
      </header>

      <div className={`conversation-scroll${isEmpty ? ' conversation-scroll--empty' : ''}`}>
        {isEmpty ? (
          <EmptyConversation onOpenSample={onOpenSample} />
        ) : (
          <div className="conversation-feed">
            <div className="conversation-date"><span>今天 14:32</span></div>
            <div className="message message--user">
              <div className="message-content">导入这 4 个温度条件文件。我要画线点图，X 用 time，Y 用 fluorescence，按 condition 分组。</div>
              <span className="message-time">14:32</span>
            </div>
            <div className="message message--agent">
              <div className="agent-avatar" aria-label="PlotAgent"><span>PA</span></div>
              <div className="agent-response">
                <p>已读取 4 个文件。它们的字段结构一致，可以作为一个批次处理。下面是本机解析结果。</p>
                <DatasetObject />
                <p>已按你的明确指令选择线点图，并预填一次映射。请确认后应用到整个批次。</p>
                <MappingObject selectedChartName={selectedChartName} />
                <div className="inline-confirmation"><CheckCircle2 size={15} /><span>你已确认映射</span><time>14:33</time></div>
                <BatchObject onOpenFocus={onOpenFocus} onOpenCompose={onOpenCompose} />
                <div className="agent-note agent-note--warning">
                  <TriangleAlert size={16} />
                  <div><strong>批次部分完成</strong><p>sample_D_50C.csv 的 fluorescence 列含 7 个文本值。成功结果已保留，你可以修复后单独重试失败项。</p></div>
                </div>
                <VersionAndExport />
              </div>
            </div>
          </div>
        )}
      </div>

      {!isEmpty && <Composer selectedChartName={selectedChartName} onOpenLibrary={onOpenLibrary} onOpenResources={onOpenResources} />}
      {isEmpty && (
        <div className="empty-composer">
          <button type="button"><Paperclip size={17} />导入数据</button>
          <button type="button" onClick={onOpenLibrary}><Library size={17} />浏览图形库</button>
          <span>导入数据后可在此输入绘图指令</span>
        </div>
      )}
    </main>
  )
}
