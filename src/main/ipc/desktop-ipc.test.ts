import { describe, expect, it, vi } from 'vitest'
import { createHash } from 'node:crypto'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { InMemoryResourceRegistry } from '../single-instance-routing.js'
import type { PythonCoreSupervisor } from '../core/python-supervisor.js'
import { IPC_CHANNELS, type DesktopDataResult } from '../../shared/desktop-contract.js'
import {
  importOptionLabel,
  importOptionPatch,
  normalizeOriginStatus,
  ORIGIN_EXPORT_REQUEST_TIMEOUT_MS,
  ORIGIN_STATUS_REQUEST_TIMEOUT_MS,
  preflightOriginExport,
  requestOriginExport,
  requestPlotList,
  readImportClarification,
  registerDesktopIpc,
  safeExportDefaultPath,
  sanitizeCoreResult,
  verifyExportArtifact,
  withImportSourceIdentity,
} from './desktop-ipc.js'

describe('desktop product IPC boundary', () => {
  it('keeps readable export names while removing Windows-invalid filename syntax', () => {
    expect(safeExportDefaultPath('图1-X38-Y偏移堆叠线图-v11.opju', 'opju'))
      .toBe('图1-X38-Y偏移堆叠线图-v11.opju')
    expect(safeExportDefaultPath('plot:workflow/one*?.opju', 'opju'))
      .toBe('plot-workflow-one.opju')
    expect(safeExportDefaultPath('CON.opju', 'opju')).toBe('fig-agent-export.opju')
    expect(safeExportDefaultPath('  ...  ', 'png')).toBe('fig-agent-export.png')
    expect(safeExportDefaultPath(`图1-${'长'.repeat(180)}.svg`, 'svg').length).toBeLessThanOrEqual(124)
  })

  it('turns supported import clarifications into safe retry options', () => {
    expect(readImportClarification({
      kind: 'clarification',
      code: 'IMPORT_DELIMITER_AMBIGUOUS',
      question: '请选择分隔符。',
      options: [
        { value: ',', label: ',' },
        { value: '\t', label: '\t' },
      ],
    })).toEqual({
      code: 'IMPORT_DELIMITER_AMBIGUOUS',
      question: '请选择分隔符。',
      options: [
        { value: ',', label: ',' },
        { value: '\t', label: '\t' },
      ],
    })
    expect(importOptionPatch('IMPORT_DELIMITER_AMBIGUOUS', '\t')).toEqual({ delimiter: '\t' })
    expect(importOptionLabel('IMPORT_DELIMITER_AMBIGUOUS', '\t', '\t')).toBe('制表符（Tab）')
    expect(importOptionPatch('IMPORT_HEADER_AMBIGUOUS', 'line:3')).toEqual({ header_row: 3 })
    expect(importOptionPatch('IMPORT_HEADER_AMBIGUOUS', 'none')).toEqual({ header_row: 0 })
    expect(importOptionPatch('IMPORT_REGION_AMBIGUOUS', 'A1:B3')).toBeUndefined()
  })

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

  it('exposes a path-free Origin status and blocks export before a save dialog when unavailable', async () => {
    expect(normalizeOriginStatus({
      status: 'ready',
      target_path: 'D:\\private\\probe.opju',
      environment: {
        display_name: 'OriginPro',
        display_version: '2025b',
        install_dir: 'D:\\origin',
        executable_path: 'D:\\origin\\Origin64.exe',
        discovery_source: 'portable',
      },
    })).toEqual({
      status: 'ready',
      display_name: 'OriginPro',
      display_version: '2025b',
      discovery_source: 'portable',
    })

    const supervisor = {
      request: vi.fn(async () => ({
        status: 'error',
        target_path: 'D:\\private\\probe.opju',
        error: { code: 'NOT_INSTALLED', message: 'not installed', retryable: false },
      })),
      toPublicResult: vi.fn(),
    } as unknown as PythonCoreSupervisor
    await expect(preflightOriginExport(supervisor)).resolves.toEqual({
      ok: false,
      error: {
        code: 'ORIGIN_UNAVAILABLE',
        message: '未找到受支持的 Origin。请安装 Origin，或将便携版放置于 D:\\origin 后重新检测。',
        retryable: false,
      },
    })
    expect(supervisor.request).toHaveBeenCalledWith(
      'origin.status',
      {},
      ORIGIN_STATUS_REQUEST_TIMEOUT_MS,
    )
  })

  it('routes persisted plot discovery through the project-scoped engine list method', async () => {
    const request = vi.fn(async () => ({
      project_id: 'project:recovered',
      project_version: 7,
      plots: [{ plot_id: 'plot:alpha', plot_version: 2 }],
    }))
    const supervisor = {
      request,
      toPublicResult: vi.fn(),
    } as unknown as PythonCoreSupervisor

    await expect(requestPlotList(
      supervisor,
      new InMemoryResourceRegistry(),
      'project:recovered',
    )).resolves.toMatchObject({ ok: true })
    expect(request).toHaveBeenCalledWith(
      'engine.plots.list',
      { project_id: 'project:recovered' },
      undefined,
    )
  })

  it('gives only the Origin export request enough time for probe, build, and reopen validation', async () => {
    const request = vi.fn(async () => ({ export_id: 'export:origin' }))
    const supervisor = {
      request,
      toPublicResult: vi.fn(),
    } as unknown as PythonCoreSupervisor

    await expect(requestOriginExport(
      supervisor,
      new InMemoryResourceRegistry(),
      { project_id: 'project:one', target_kind: 'plot' },
    )).resolves.toMatchObject({ ok: true })
      expect(request).toHaveBeenCalledWith(
        'engine.exports.execute',
        { project_id: 'project:one', target_kind: 'plot' },
        ORIGIN_EXPORT_REQUEST_TIMEOUT_MS,
      )
    expect(ORIGIN_EXPORT_REQUEST_TIMEOUT_MS).toBe(925_000)
  })

  it('surfaces a failed Origin outcome instead of reporting a successful export', async () => {
    const request = vi.fn(async () => ({
      task_id: 'task:origin-failed',
      export_id: null,
      result: {
        status: 'failed',
        error: {
          code: 'VALIDATION_FAILURE',
          message: 'Origin 项目重开校验未通过。',
          retryable: false,
        },
      },
    }))
    const supervisor = {
      request,
      toPublicResult: vi.fn(),
    } as unknown as PythonCoreSupervisor

    await expect(requestOriginExport(
      supervisor,
      new InMemoryResourceRegistry(),
      { project_id: 'project:one', target_kind: 'plot' },
    )).resolves.toEqual({
      ok: false,
      error: {
        code: 'CORE_REQUEST_FAILED',
        message: 'Origin 项目重开校验未通过。',
        retryable: false,
      },
    })
  })

  it('returns one named terminal outcome for every file in a mixed import selection', async () => {
    const handlers = new Map<string, (...args: unknown[]) => unknown>()
    const ipcMain = {
      handle: vi.fn((channel: string, handler: (...args: unknown[]) => unknown) => {
        handlers.set(channel, handler)
      }),
      removeHandler: vi.fn(),
    }
    const selectedPaths = [
      'D:\\inputs\\multi-block.txt',
      'D:\\inputs\\valid.csv',
      'D:\\inputs\\ragged.csv',
    ]
    const request = vi.fn(async (method: string, params?: Record<string, unknown>) => {
      if (method === 'datasets.list') return { project_version: 0, datasets: [] }
      if (method !== 'datasets.import') throw new Error(`unexpected method ${method}`)
      const sourcePath = String(params?.source_path)
      if (sourcePath.endsWith('multi-block.txt')) {
        return {
          kind: 'committed',
          project_version: 1,
          datasets: [
            { source_dataset_id: 'source:block-1', source_version: 1 },
            { source_dataset_id: 'source:block-2', source_version: 1 },
          ],
        }
      }
      if (sourcePath.endsWith('valid.csv')) {
        return {
          kind: 'committed',
          project_version: 2,
          datasets: [{ source_dataset_id: 'source:valid', source_version: 1 }],
        }
      }
      return {
        kind: 'rejection',
        code: 'IMPORT_RAGGED_ROWS',
        message: '数据块 1 的行宽不一致。',
      }
    })
    const supervisor = {
      request,
      toPublicResult: vi.fn(() => ({
        code: 'CORE_REQUEST_FAILED', message: 'unexpected', retryable: false,
      })),
      getStatus: vi.fn(() => ({ phase: 'ready', restartAttempt: 0 })),
      retry: vi.fn(() => false),
    } as unknown as PythonCoreSupervisor
    registerDesktopIpc({
      ipcMain: ipcMain as never,
      supervisor,
      tasks: { snapshot: vi.fn(() => ({ tasks: [], activeTaskCount: 0, hasCommittingTask: false })), get: vi.fn() } as never,
      closeController: { respond: vi.fn() } as never,
      dialog: {
        showOpenDialog: vi.fn(async () => ({ canceled: false, filePaths: selectedPaths })),
        showMessageBox: vi.fn(),
        showSaveDialog: vi.fn(),
      } as never,
      getWindow: () => ({}) as never,
      resources: new InMemoryResourceRegistry(),
      ensureSampleSource: vi.fn(),
      agentFoundationRuntime: { ownsTask: vi.fn(() => false) } as never,
      openPath: vi.fn(async () => ''),
      revealPath: vi.fn(),
    })
    const handler = handlers.get(IPC_CHANNELS.datasetImport)
    expect(handler).toBeDefined()

    const response = await handler?.({}, { projectId: 'project:mixed' }) as DesktopDataResult

    expect(response.ok).toBe(true)
    if (!response.ok) return
    expect(response.value).toMatchObject({
      selected_files: ['multi-block.txt', 'valid.csv', 'ragged.csv'],
      project_version: 2,
      imports: [
        { kind: 'committed', source_file_name: 'multi-block.txt' },
        { kind: 'committed', source_file_name: 'valid.csv' },
        {
          kind: 'rejection',
          source_file_name: 'ragged.csv',
          message: '数据块 1 的行宽不一致。',
        },
      ],
    })
    expect(request.mock.calls.filter(([method]) => method === 'datasets.import')).toHaveLength(3)
  })

  it('reports export success only after the authorized file matches Core metadata', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'plotagent-export-proof-'))
    try {
      const destination = join(directory, 'verified.opju')
      const payload = Buffer.from('native editable project')
      const contentHash = createHash('sha256').update(payload).digest('hex')
      const result = {
        ok: true as const,
        value: {
          export_id: 'export:verified',
          artifact: { size: payload.length, content_hash: contentHash },
        },
      }

      await expect(verifyExportArtifact(result, destination)).resolves.toMatchObject({
        ok: false,
        error: { code: 'RESOURCE_INVALID' },
      })
      await writeFile(destination, payload)
      await expect(verifyExportArtifact(result, destination)).resolves.toEqual(result)
      await writeFile(destination, Buffer.from('corrupted'))
      await expect(verifyExportArtifact(result, destination)).resolves.toMatchObject({
        ok: false,
        error: { code: 'RESOURCE_INVALID' },
      })
    } finally {
      await rm(directory, { recursive: true, force: true })
    }
  })
})
