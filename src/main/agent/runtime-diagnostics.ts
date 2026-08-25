import { appendFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'

import type { PiRuntimeV2Diagnostic } from './pi-runtime-v2.js'

export class AgentRuntimeDiagnosticWriter {
  readonly filePath: string

  constructor(logDirectory: string) {
    this.filePath = join(logDirectory, 'agent-runtime-diagnostics.jsonl')
  }

  write(diagnostic: PiRuntimeV2Diagnostic): void {
    try {
      mkdirSync(dirname(this.filePath), { recursive: true })
      appendFileSync(this.filePath, `${JSON.stringify(diagnostic)}\n`, {
        encoding: 'utf8',
        mode: 0o600,
      })
    } catch {
      // Diagnostics must never change the outcome of the user's Agent task.
    }
  }
}
