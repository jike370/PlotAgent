import type { ReactNode } from 'react'

import { PUBLIC_AGENT_INITIALS, PUBLIC_PRODUCT_NAME } from '../../../shared/branding'

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
      <div className="agent-avatar" aria-label={live ? undefined : PUBLIC_PRODUCT_NAME} aria-hidden={live ? true : undefined}>
        <span>{PUBLIC_AGENT_INITIALS}</span>
      </div>
      <div className="agent-response">{children}</div>
    </div>
  )
}
