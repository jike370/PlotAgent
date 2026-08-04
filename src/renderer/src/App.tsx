import { FlaskConical } from 'lucide-react'

export function App(): React.JSX.Element {
  return (
    <main className="scaffold">
      <div className="scaffold__mark" aria-hidden="true">
        <FlaskConical size={22} strokeWidth={1.8} />
      </div>
      <p>PlotAgent 桌面端骨架已就绪</p>
    </main>
  )
}
