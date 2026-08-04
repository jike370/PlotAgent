import { contextBridge } from 'electron'

const desktop = {
  platform: process.platform,
  versions: {
    chrome: process.versions.chrome,
    electron: process.versions.electron,
  },
} as const

contextBridge.exposeInMainWorld('plotAgentDesktop', desktop)
