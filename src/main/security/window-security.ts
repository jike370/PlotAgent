import type { Session, WebContents, WebPreferences } from 'electron'

export const PRODUCTION_CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: plotagent-resource:",
  "font-src 'self'",
  "connect-src 'none'",
  "object-src 'none'",
  "base-uri 'none'",
  "frame-ancestors 'none'",
  "form-action 'none'",
].join('; ')

export function hardenSession(session: Session): void {
  session.setPermissionCheckHandler(() => false)
  session.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false))
  session.webRequest.onHeadersReceived((details, callback) => {
    if (!details.url.startsWith('file:')) {
      callback({})
      return
    }
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [PRODUCTION_CONTENT_SECURITY_POLICY],
      },
    })
  })
}

export function hardenWebContents(webContents: WebContents): void {
  webContents.on('will-attach-webview', (event) => event.preventDefault())
  webContents.on('will-navigate', (event, url) => {
    if (url !== webContents.getURL()) event.preventDefault()
  })
  webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
}

export function assertSecureWebPreferences(preferences: WebPreferences): void {
  if (
    preferences.contextIsolation !== true ||
    preferences.nodeIntegration !== false ||
    preferences.sandbox !== true ||
    preferences.webviewTag === true ||
    preferences.webSecurity === false
  ) {
    throw new Error('BrowserWindow security invariants are not satisfied')
  }
}
