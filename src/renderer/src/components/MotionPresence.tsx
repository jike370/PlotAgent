import { useEffect, useState, type ReactNode } from 'react'

export type MotionPhase = 'entered' | 'exiting'

interface MotionPresenceProps {
  present: boolean
  exitMs: number
  children: (phase: MotionPhase) => ReactNode
}

export function MotionPresence({ present, exitMs, children }: MotionPresenceProps): React.JSX.Element | null {
  const [mounted, setMounted] = useState(present)

  if (present && !mounted) setMounted(true)

  useEffect(() => {
    if (present || !mounted) return
    const unmountTimer = window.setTimeout(() => {
      setMounted(false)
    }, exitMs)
    return () => window.clearTimeout(unmountTimer)
  }, [exitMs, mounted, present])

  return mounted ? <>{children(present ? 'entered' : 'exiting')}</> : null
}
