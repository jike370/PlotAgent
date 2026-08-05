import {
  parseCoreProtocolMessage,
  type CoreProtocolMessage,
} from '../../shared/desktop-contract.js'

export type FrameErrorCode =
  | 'CORE_PROTOCOL_INVALID_FRAME'
  | 'CORE_PROTOCOL_INVALID_MESSAGE'
  | 'CORE_PROTOCOL_TRUNCATED_FRAME'
  | 'CORE_PROTOCOL_FRAME_TOO_LARGE'

export type DecodedFrame =
  | { readonly kind: 'message'; readonly message: CoreProtocolMessage }
  | { readonly kind: 'error'; readonly code: FrameErrorCode }

const NEWLINE = 0x0a
const CARRIAGE_RETURN = 0x0d

export class JsonLineDecoder {
  private buffer = Buffer.alloc(0)
  private discardingOversizedFrame = false

  constructor(private readonly maximumFrameBytes = 1024 * 1024) {
    if (!Number.isSafeInteger(maximumFrameBytes) || maximumFrameBytes < 128) {
      throw new Error('maximumFrameBytes must be an integer of at least 128')
    }
  }

  push(chunk: Uint8Array | string): DecodedFrame[] {
    const frames: DecodedFrame[] = []
    let incoming = typeof chunk === 'string' ? Buffer.from(chunk, 'utf8') : Buffer.from(chunk)

    if (this.discardingOversizedFrame) {
      const newlineIndex = incoming.indexOf(NEWLINE)
      if (newlineIndex === -1) return frames
      incoming = incoming.subarray(newlineIndex + 1)
      this.discardingOversizedFrame = false
    }

    this.buffer = Buffer.concat([this.buffer, incoming])

    let newlineIndex = this.buffer.indexOf(NEWLINE)
    while (newlineIndex !== -1) {
      let line = this.buffer.subarray(0, newlineIndex)
      this.buffer = this.buffer.subarray(newlineIndex + 1)
      if (line.at(-1) === CARRIAGE_RETURN) line = line.subarray(0, -1)
      frames.push(this.decodeLine(line))
      newlineIndex = this.buffer.indexOf(NEWLINE)
    }

    if (this.buffer.length > this.maximumFrameBytes) {
      this.buffer = Buffer.alloc(0)
      this.discardingOversizedFrame = true
      frames.push({ kind: 'error', code: 'CORE_PROTOCOL_FRAME_TOO_LARGE' })
    }

    return frames
  }

  end(): DecodedFrame[] {
    const frames: DecodedFrame[] = []
    if (this.discardingOversizedFrame) {
      this.discardingOversizedFrame = false
    } else if (this.buffer.length > 0) {
      frames.push({ kind: 'error', code: 'CORE_PROTOCOL_TRUNCATED_FRAME' })
    }
    this.buffer = Buffer.alloc(0)
    return frames
  }

  private decodeLine(line: Buffer): DecodedFrame {
    if (line.length === 0 || line.length > this.maximumFrameBytes) {
      return {
        kind: 'error',
        code: line.length > this.maximumFrameBytes
          ? 'CORE_PROTOCOL_FRAME_TOO_LARGE'
          : 'CORE_PROTOCOL_INVALID_FRAME',
      }
    }

    let text: string
    try {
      text = new TextDecoder('utf-8', { fatal: true }).decode(line)
    } catch {
      return { kind: 'error', code: 'CORE_PROTOCOL_INVALID_FRAME' }
    }

    let value: unknown
    try {
      value = JSON.parse(text) as unknown
    } catch {
      return { kind: 'error', code: 'CORE_PROTOCOL_INVALID_FRAME' }
    }

    const message = parseCoreProtocolMessage(value)
    return message === null
      ? { kind: 'error', code: 'CORE_PROTOCOL_INVALID_MESSAGE' }
      : { kind: 'message', message }
  }
}

export function encodeJsonLine(message: CoreProtocolMessage): Buffer {
  const parsed = parseCoreProtocolMessage(message)
  if (parsed === null) throw new Error('Cannot encode an invalid Core protocol message')
  return Buffer.from(`${JSON.stringify(parsed)}\n`, 'utf8')
}
