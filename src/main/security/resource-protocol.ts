import { readFile, lstat } from 'node:fs/promises'
import { extname } from 'node:path'

import type { Session } from 'electron'

import type { ResourceRegistry } from '../single-instance-routing.js'

const MAX_VIEWABLE_RESOURCE_BYTES = 32 * 1024 * 1024
const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])

export interface ResourcePayload {
  readonly body: Uint8Array
  readonly mimeType: 'image/png' | 'image/svg+xml'
}

function resourceIdFromUrl(rawUrl: string): string | null {
  try {
    const url = new URL(rawUrl)
    if (url.protocol !== 'plotagent-resource:' || url.hostname !== 'local') return null
    const token = url.pathname.slice(1)
    return /^[0-9a-f-]{36}$/i.test(token) ? `resource:${token}` : null
  } catch {
    return null
  }
}

function isSafeSvg(body: Buffer): boolean {
  const text = body.toString('utf8')
  return /^\s*(?:<\?xml[^>]*>\s*)?<svg\b/i.test(text) &&
    !/<(?:script|foreignObject|iframe|object|embed)\b/i.test(text) &&
    !/<!ENTITY\b/i.test(text) &&
    !/(?:href|src)\s*=\s*["']\s*(?:https?:|file:|\\\\|[A-Za-z]:)/i.test(text)
}

export async function loadRegisteredResource(
  rawUrl: string,
  registry: ResourceRegistry,
): Promise<ResourcePayload | null> {
  const resourceId = resourceIdFromUrl(rawUrl)
  if (resourceId === null) return null
  const entry = registry.resolveEntry(resourceId)
  if (entry === undefined || (entry.kind !== 'preview' && entry.kind !== 'export')) return null

  const extension = extname(entry.path).toLocaleLowerCase('en-US')
  if (extension !== '.png' && extension !== '.svg') return null
  try {
    const info = await lstat(entry.path)
    if (!info.isFile() || info.isSymbolicLink() || info.size <= 0 || info.size > MAX_VIEWABLE_RESOURCE_BYTES) {
      return null
    }
    const body = await readFile(entry.path)
    if (extension === '.png') {
      return body.subarray(0, PNG_SIGNATURE.length).equals(PNG_SIGNATURE)
        ? { body, mimeType: 'image/png' }
        : null
    }
    return isSafeSvg(body) ? { body, mimeType: 'image/svg+xml' } : null
  } catch {
    return null
  }
}

export function registerResourceProtocol(session: Session, registry: ResourceRegistry): void {
  session.protocol.handle('plotagent-resource', async (request) => {
    const payload = await loadRegisteredResource(request.url, registry)
    if (payload === null) {
      return new Response('Resource unavailable', {
        status: 404,
        headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' },
      })
    }
    const body = payload.body.buffer.slice(
      payload.body.byteOffset,
      payload.body.byteOffset + payload.body.byteLength,
    ) as ArrayBuffer
    return new Response(body, {
      status: 200,
      headers: {
        'Content-Type': payload.mimeType,
        'Content-Length': String(payload.body.byteLength),
        'Cache-Control': 'no-store',
        'Content-Security-Policy': "default-src 'none'; sandbox",
        'X-Content-Type-Options': 'nosniff',
      },
    })
  })
}
