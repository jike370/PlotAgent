/// <reference types="vite/client" />

import type { PlotAgentDesktopApi } from '../../shared/desktop-contract'

declare global {
  interface Window {
    readonly plotAgentDesktop?: PlotAgentDesktopApi
  }
}

export {}
