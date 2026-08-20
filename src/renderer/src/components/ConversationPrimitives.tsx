import type { ReactNode } from 'react'

interface AgentMessageProps {
  children: ReactNode
  className?: string
  live?: boolean
}

export function AgentMessage({ children, className, live = false }: AgentMessageProps): React.JSX.Element {
  return (
    <div
      className={`message message--agent${className ? ` ${className}` : ''}`}
      role={live ? 'status' : undefined}
      aria-live={live ? 'polite' : undefined}
    >
      <div className="agent-avatar" aria-label={live ? undefined : 'PlotAgent'} aria-hidden={live ? true : undefined}>
        <span>PA</span>
      </div>
      <div className="agent-response">{children}</div>
    </div>
  )
}
