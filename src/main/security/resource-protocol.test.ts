import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

import { afterEach, describe, expect, it } from 'vitest'

import { InMemoryResourceRegistry } from '../single-instance-routing.js'
import { loadRegisteredResource } from './resource-protocol.js'

const temporaryDirectories: string[] = []

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((directory) => (
    rm(directory, { recursive: true, force: true })
  )))
})

async function temporaryFile(name: string, body: string | Uint8Array): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), 'plotagent-resource-test-'))
  temporaryDirectories.push(directory)
  const path = join(directory, name)
  await writeFile(path, body)
  return path
}

describe('plotagent resource protocol', () => {
  it('serves a registered safe preview without exposing its path in the URL', async () => {
    const path = await temporaryFile('preview.svg', '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>')
    const registry = new InMemoryResourceRegistry()
    const resource = registry.registerFile(path, 'preview')

    expect(resource.url).toMatch(/^plotagent-resource:\/\/local\/[0-9a-f-]{36}$/)
    expect(resource.url).not.toContain(path)
    await expect(loadRegisteredResource(resource.url!, registry)).resolves.toMatchObject({
      mimeType: 'image/svg+xml',
    })
  })

  it('rejects unregistered, project-package, active SVG, and unsupported resources', async () => {
    const activeSvg = await temporaryFile(
      'active.svg',
      '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
    )
    const registry = new InMemoryResourceRegistry()
    const preview = registry.registerFile(activeSvg, 'preview')
    const project = registry.registerProjectPackage(await temporaryFile('project.plotproj', 'x'))

    await expect(loadRegisteredResource(preview.url!, registry)).resolves.toBeNull()
    await expect(loadRegisteredResource(
      `plotagent-resource://local/${project.resourceId.slice('resource:'.length)}`,
      registry,
    )).resolves.toBeNull()
    await expect(loadRegisteredResource('plotagent-resource://local/00000000-0000-0000-0000-000000000000', registry))
      .resolves.toBeNull()
  })
})
