import { delimiter, dirname, join } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  PACKAGED_CORE_RELATIVE_PATH,
  resolveCoreLaunchSpec,
} from './python-supervisor.js'

describe('resolveCoreLaunchSpec', () => {
  it('uses the bundled onedir sidecar in packaged builds', () => {
    const appPath = join('C:', 'Program Files', 'PlotAgent', 'resources', 'app.asar')
    const resourcesPath = join('C:', 'Program Files', 'PlotAgent', 'resources')
    const spec = resolveCoreLaunchSpec({
      appPath,
      resourcesPath,
      isPackaged: true,
      platform: 'win32',
      processEnv: {
        PLOTAGENT_CORE_EXECUTABLE: join('C:', 'untrusted', 'python.exe'),
        PATH: 'test-path',
      },
    })

    const expectedCommand = join(resourcesPath, ...PACKAGED_CORE_RELATIVE_PATH)
    expect(spec).toEqual({
      command: expectedCommand,
      args: [],
      cwd: dirname(expectedCommand),
      env: {
        PLOTAGENT_CORE_EXECUTABLE: join('C:', 'untrusted', 'python.exe'),
        PATH: 'test-path',
      },
    })
  })

  it('keeps the module entrypoint and source path in development', () => {
    const appPath = join('C:', 'src', 'plotagent')
    const existingPythonPath = join('C:', 'existing', 'python')
    const spec = resolveCoreLaunchSpec({
      appPath,
      isPackaged: false,
      platform: 'win32',
      processEnv: {
        PLOTAGENT_CORE_EXECUTABLE: existingPythonPath,
        PYTHONPATH: 'existing-path',
      },
    })

    expect(spec.command).toBe(existingPythonPath)
    expect(spec.args).toEqual(['-m', 'plotagent.desktop_core'])
    expect(spec.cwd).toBe(appPath)
    expect(spec.env.PYTHONPATH).toBe(`${join(appPath, 'src')}${delimiter}existing-path`)
  })
})
