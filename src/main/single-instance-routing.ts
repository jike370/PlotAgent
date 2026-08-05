import { randomUUID } from 'node:crypto'
import { basename, extname, isAbsolute, resolve } from 'node:path'

import type {
  DesktopResource,
  DesktopResourceKind,
  OpenResourceRequest,
} from '../shared/desktop-contract.js'
import { DESKTOP_API_VERSION } from '../shared/desktop-contract.js'

const MAXIMUM_ARGUMENT_LENGTH = 32_768
const SUPPORTED_EXTENSION = '.plotproj'

export function extractOpenFileArguments(
  commandLine: readonly string[],
  workingDirectory: string,
): string[] {
  const paths: string[] = []
  const seen = new Set<string>()

  for (const argument of commandLine) {
    if (
      argument.length === 0 ||
      argument.length > MAXIMUM_ARGUMENT_LENGTH ||
      argument.includes('\0') ||
      argument.startsWith('-') ||
      argument.includes('://') ||
      extname(argument).toLocaleLowerCase('en-US') !== SUPPORTED_EXTENSION
    ) continue

    const absolutePath = isAbsolute(argument) ? resolve(argument) : resolve(workingDirectory, argument)
    const normalizedKey = process.platform === 'win32'
      ? absolutePath.toLocaleLowerCase('en-US')
      : absolutePath
    if (seen.has(normalizedKey)) continue
    seen.add(normalizedKey)
    paths.push(absolutePath)
  }

  return paths
}

export interface ResourceRegistry {
  registerProjectPackage(path: string): OpenResourceRequest
  registerFile(path: string, kind: DesktopResourceKind): DesktopResource
  resolve(resourceId: string): string | undefined
  resolveEntry(resourceId: string): RegisteredResource | undefined
}

export interface RegisteredResource {
  readonly resourceId: string
  readonly path: string
  readonly kind: DesktopResourceKind
}

const MIME_BY_EXTENSION = new Map<string, DesktopResource['mimeType']>([
  ['.png', 'image/png'],
  ['.svg', 'image/svg+xml'],
])

export class InMemoryResourceRegistry implements ResourceRegistry {
  private readonly resources = new Map<string, RegisteredResource>()

  private register(path: string, kind: DesktopResourceKind): RegisteredResource {
    if (!isAbsolute(path) || path.includes('\0')) throw new Error('Resource path must be absolute')
    const resourceId = `resource:${randomUUID()}`
    const entry = { resourceId, path: resolve(path), kind }
    this.resources.set(resourceId, entry)
    return entry
  }

  registerProjectPackage(path: string): OpenResourceRequest {
    const { resourceId } = this.register(path, 'project-package')
    return {
      schemaVersion: DESKTOP_API_VERSION,
      requestId: `open:${randomUUID()}`,
      resourceId,
      kind: 'project-package',
    }
  }

  registerFile(path: string, kind: DesktopResourceKind): DesktopResource {
    const entry = this.register(path, kind)
    const extension = extname(entry.path).toLocaleLowerCase('en-US')
    const mimeType = MIME_BY_EXTENSION.get(extension)
    const isViewable = (kind === 'preview' || kind === 'export') && mimeType !== undefined
    return {
      resourceId: entry.resourceId,
      kind,
      ...(isViewable ? { url: `plotagent-resource://local/${entry.resourceId.slice('resource:'.length)}` } : {}),
      ...(mimeType === undefined ? {} : { mimeType }),
      fileName: basename(entry.path),
    }
  }

  resolve(resourceId: string): string | undefined {
    return this.resources.get(resourceId)?.path
  }

  resolveEntry(resourceId: string): RegisteredResource | undefined {
    return this.resources.get(resourceId)
  }
}

export class SingleInstanceOpenRouter {
  private readonly pending: OpenResourceRequest[] = []
  private listener?: (request: OpenResourceRequest) => void

  constructor(private readonly registry: ResourceRegistry) {}

  setListener(listener: (request: OpenResourceRequest) => void): void {
    this.listener = listener
    for (const request of this.pending.splice(0)) listener(request)
  }

  routeCommandLine(commandLine: readonly string[], workingDirectory: string): void {
    for (const path of extractOpenFileArguments(commandLine, workingDirectory)) {
      this.routePath(path)
    }
  }

  routePath(path: string): void {
    const [validatedPath] = extractOpenFileArguments([path], process.cwd())
    if (validatedPath === undefined) return
    const request = this.registry.registerProjectPackage(validatedPath)
    if (this.listener === undefined) this.pending.push(request)
    else this.listener(request)
  }
}
