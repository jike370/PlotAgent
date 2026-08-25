import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import type { PiRuntimeV2Diagnostic } from './pi-runtime-v2.js'
import { AgentRuntimeDiagnosticWriter } from './runtime-diagnostics.js'

const temporaryDirectories: string[] = []

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true })
  }
})

describe('AgentRuntimeDiagnosticWriter', () => {
  it('appends one JSON line for each rejected tool call', () => {
    const directory = mkdtempSync(join(tmpdir(), 'plotagent-diagnostics-'))
    temporaryDirectories.push(directory)
    const writer = new AgentRuntimeDiagnosticWriter(join(directory, 'nested', 'logs'))
    const diagnostic: PiRuntimeV2Diagnostic = {
      schemaVersion: '1.0',
      occurredAt: '2026-08-25T12:00:00.000Z',
      activationId: 'activation:test',
      taskId: 'task:test',
      taskVersion: 1,
      modelTurn: 3,
      kind: 'tool_call_rejected',
      toolName: 'submit_agent_yield',
      toolCallId: 'provider-tool-call-3',
      message: 'Agent yield failed validation: intent.items.0.actions.0: missing.',
    }

    writer.write(diagnostic)
    writer.write({ ...diagnostic, modelTurn: 4, toolCallId: 'provider-tool-call-4' })

    const lines = readFileSync(writer.filePath, 'utf8').trim().split('\n')
    expect(lines.map((line) => JSON.parse(line))).toEqual([
      diagnostic,
      { ...diagnostic, modelTurn: 4, toolCallId: 'provider-tool-call-4' },
    ])
  })
})
