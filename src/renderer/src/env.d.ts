/// <reference types="vite/client" />

interface Window {
  plotAgentDesktop?: {
    readonly platform: string
    readonly versions: {
      readonly chrome: string
      readonly electron: string
    }
  }
}
