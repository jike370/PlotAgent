import { randomUUID } from 'node:crypto'
import { extname, isAbsolute, resolve } from 'node:path'

import type { OpenResourceRequest } from '../shared/desktop-contract.js'
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
  resolve(resourceId: string): string | undefined
}

export class InMemoryResourceRegistry implements ResourceRegistry {
  private readonly resources = new Map<string, string>()

  registerProjectPackage(path: string): OpenResourceRequest {
    const resourceId = `resource:${randomUUID()}`
    this.resources.set(resourceId, path)
    return {
      schemaVersion: DESKTOP_API_VERSION,
      requestId: `open:${randomUUID()}`,
      resourceId,
      kind: 'project-package',
    }
  }

  resolve(resourceId: string): string | undefined {
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
