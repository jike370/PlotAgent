import { delimiter, dirname, join } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  PACKAGED_CORE_RELATIVE_PATH,
  coreRequestFailure,
  resolveCoreLaunchSpec,
} from './python-supervisor.js'

describe('resolveCoreLaunchSpec', () => {
  it('keeps a bounded Core rejection reason for the user', () => {
    expect(coreRequestFailure({
      jsonrpc: '2.0',
      protocol_version: '1.0',
      id: 'req:one',
      error: { code: 'INVALID_PARAMS', message: '字段绑定不完整。' },
    })).toEqual({
      code: 'CORE_REQUEST_FAILED',
      message: '字段绑定不完整。',
      retryable: false,
    })
  })

  it('uses the bundled onedir sidecar in packaged builds', () => {
    const appPath = join('C:', 'Program Files', 'fig-agent', 'resources', 'app.asar')
    const resourcesPath = join('C:', 'Program Files', 'fig-agent', 'resources')
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
