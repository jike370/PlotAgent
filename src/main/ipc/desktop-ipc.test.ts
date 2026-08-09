import { describe, expect, it, vi } from 'vitest'

import { InMemoryResourceRegistry } from '../single-instance-routing.js'
import type { PythonCoreSupervisor } from '../core/python-supervisor.js'
import {
  AGENT_DECIDE_REQUEST_TIMEOUT_MS,
  requestAgentDecision,
  sanitizeCoreResult,
  withImportSourceIdentity,
} from './desktop-ipc.js'

describe('desktop product IPC boundary', () => {
  it('replaces Core artifact paths with random registered resources', () => {
    const registry = new InMemoryResourceRegistry()
    const result = sanitizeCoreResult({
      plot_id: 'plot:one',
      artifact: {
        resource_id: 'resource:core-preview',
        path: 'C:\\private\\project\\preview.png',
        content_hash: 'abc',
        size: 123,
      },
    }, registry)
    const serialized = JSON.stringify(result)

    expect(serialized).not.toContain('C:\\\\private')
    expect(serialized).not.toContain('"path"')
    expect(serialized).toContain('plotagent-resource://local/')
    expect(serialized).toContain('"kind":"preview"')
  })

  it('drops secret-shaped fields and rejects an unregistered absolute path value', () => {
    const registry = new InMemoryResourceRegistry()
    expect(sanitizeCoreResult({ status: 'ok', api_token: 'do-not-expose' }, registry))
      .toEqual({ status: 'ok' })
    expect(() => sanitizeCoreResult({ detail: 'C:\\private\\raw.csv' }, registry))
      .toThrow('Unregistered path')
  })

  it('adds a safe source file identity and preserves an available worksheet name', () => {
    expect(withImportSourceIdentity({
      kind: 'committed',
      datasets: [
        { source_dataset_id: 'source:one', source_version: 1, sheet_name: '动力学' },
        { source_dataset_id: 'source:two', source_version: 1 },
      ],
    }, '仪器记录.xlsx')).toEqual({
      kind: 'committed',
      source_file_name: '仪器记录.xlsx',
      datasets: [
        {
          source_dataset_id: 'source:one',
          source_version: 1,
          sheet_name: '动力学',
          source_file_name: '仪器记录.xlsx',
          source_table_index: 1,
          source_sheet_name: '动力学',
        },
        {
          source_dataset_id: 'source:two',
          source_version: 1,
          source_file_name: '仪器记录.xlsx',
          source_table_index: 2,
        },
      ],
    })
  })

  it('gives only the model decision request a budget beyond the Core model timeout', async () => {
    const request = vi.fn(async () => ({ accepted: true }))
    const supervisor = {
      request,
      toPublicResult: vi.fn(),
    } as unknown as PythonCoreSupervisor

    await expect(requestAgentDecision(
      supervisor,
      new InMemoryResourceRegistry(),
      { project_id: 'project:one', user_instruction: '统一颜色' },
    )).resolves.toEqual({ ok: true, value: { accepted: true } })
    expect(request).toHaveBeenCalledWith(
      'agent.decide',
      { project_id: 'project:one', user_instruction: '统一颜色' },
      AGENT_DECIDE_REQUEST_TIMEOUT_MS,
    )
    expect(AGENT_DECIDE_REQUEST_TIMEOUT_MS).toBe(35_000)
  })
})
