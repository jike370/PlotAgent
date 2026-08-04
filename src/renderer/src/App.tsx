import { useEffect, useState } from 'react'
import { Check, FlaskConical } from 'lucide-react'

import { chartCatalog, type ChartType } from './data/chartCatalog'
import { ChartLibrary } from './components/ChartLibrary'
import { CompositionEditor } from './components/CompositionEditor'
import { ConversationWorkspace } from './components/ConversationWorkspace'
import { FocusEditor } from './components/FocusEditor'
import { ProjectResourceLibrary } from './components/ProjectResourceLibrary'
import { Sidebar, type ConversationId } from './components/Sidebar'
import { TaskDrawer } from './components/TaskDrawer'

type Screen = 'workspace' | 'focus' | 'composition'

export function App(): React.JSX.Element {
  const [screen, setScreen] = useState<Screen>('workspace')
  const [activeConversation, setActiveConversation] = useState<ConversationId>('batch')
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [resourcesOpen, setResourcesOpen] = useState(false)
  const [tasksOpen, setTasksOpen] = useState(false)
  const [focusIndex, setFocusIndex] = useState(0)
  const [selectedChart, setSelectedChart] = useState<ChartType>(() => chartCatalog.find((chart) => chart.id === 'K02')!)
  const [toast, setToast] = useState('')

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.ctrlKey && event.key.toLowerCase() === 'n') {
        event.preventDefault()
        setScreen('workspace')
        setActiveConversation('empty')
      }
      if (event.key === 'Escape') {
        if (resourcesOpen) setResourcesOpen(false)
        else if (libraryOpen) setLibraryOpen(false)
        else if (tasksOpen) setTasksOpen(false)
        else if (screen !== 'workspace') setScreen('workspace')
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [libraryOpen, resourcesOpen, screen, tasksOpen])

  const chooseChart = (chart: ChartType): void => {
    setSelectedChart(chart)
    setLibraryOpen(false)
    setToast(`已选择 ${chart.name}（${chart.id}），请确认字段映射`)
    window.setTimeout(() => setToast(''), 3200)
  }

  const openFocus = (index: number): void => {
    setFocusIndex(index)
    setScreen('focus')
  }

  return (
    <div className="app-shell">
      <div className="app-titlebar" aria-hidden="true">
        <FlaskConical size={13} />
        <span>PlotAgent</span>
        <span className="titlebar-context">本地科研绘图工作台</span>
      </div>

      <div className="app-surface">
        {screen === 'workspace' && (
          <>
            <Sidebar
              activeConversation={activeConversation}
              onConversationChange={(id) => {
                setActiveConversation(id)
                setScreen('workspace')
              }}
              onNewConversation={() => setActiveConversation('empty')}
              onTaskCenter={() => setTasksOpen(true)}
              onOpenResources={() => setResourcesOpen(true)}
            />
            <ConversationWorkspace
              activeConversation={activeConversation}
              selectedChartName={`${selectedChart.name} ${selectedChart.id}`}
              onOpenLibrary={() => setLibraryOpen(true)}
              onOpenFocus={openFocus}
              onOpenCompose={() => setScreen('composition')}
              onOpenTasks={() => setTasksOpen(true)}
              onOpenSample={() => setActiveConversation('batch')}
              onOpenResources={() => setResourcesOpen(true)}
            />
          </>
        )}
        {screen === 'focus' && <FocusEditor initialIndex={focusIndex} onClose={() => setScreen('workspace')} />}
        {screen === 'composition' && <CompositionEditor onClose={() => setScreen('workspace')} />}
      </div>

      {libraryOpen && <ChartLibrary currentChartId={selectedChart.id} onClose={() => setLibraryOpen(false)} onSelect={chooseChart} />}
      {resourcesOpen && <ProjectResourceLibrary onClose={() => setResourcesOpen(false)} />}
      {tasksOpen && <TaskDrawer onClose={() => setTasksOpen(false)} />}
      {toast && <div className="toast" role="status"><Check size={15} />{toast}</div>}
    </div>
  )
}
