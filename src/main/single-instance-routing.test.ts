import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { extractOpenFileArguments } from './single-instance-routing.js'

describe('single-instance file routing', () => {
  it('extracts only supported project packages and resolves relative paths', () => {
    const cwd = resolve('C:\\workspace')
    const paths = extractOpenFileArguments([
      'PlotAgent.exe',
      '--inspect=9229',
      'project.plotproj',
      'notes.csv',
      'https://example.com/remote.plotproj',
    ], cwd)

    expect(paths).toEqual([resolve(cwd, 'project.plotproj')])
  })

  it('deduplicates case-insensitively on Windows', () => {
    const cwd = resolve('C:\\workspace')
    const paths = extractOpenFileArguments(
      ['Result.PLOTPROJ', 'result.plotproj'],
      cwd,
    )

    expect(paths).toHaveLength(1)
  })

  it('rejects switches, NULs, and unsupported extensions', () => {
    expect(extractOpenFileArguments(
      ['--open=bad.plotproj', 'bad\0.plotproj', 'data.xlsx'],
      resolve('C:\\workspace'),
    )).toEqual([])
  })
})
