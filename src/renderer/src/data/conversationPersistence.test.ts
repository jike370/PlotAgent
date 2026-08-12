import { describe, expect, it } from 'vitest'

import { readConversationMessages, writeConversationMessages } from './conversationPersistence'

describe('conversation persistence', () => {
  it('round-trips bounded user instructions without accepting malformed records', () => {
    let stored: string | null = null
    const storage = {
      getItem: () => stored,
      setItem: (_key: string, value: string) => { stored = value },
    }
    writeConversationMessages(storage, 'project:one', [{
      id: 'message:user:one',
      role: 'user',
      text: '把纵轴改为 log10',
      createdAt: '2026-08-13T00:00:00.000Z',
    }])
    expect(readConversationMessages(storage, 'project:one')).toEqual([{
      id: 'message:user:one',
      role: 'user',
      text: '把纵轴改为 log10',
      createdAt: '2026-08-13T00:00:00.000Z',
    }])

    stored = JSON.stringify([{ id: 'bad', role: 'system', text: 'unsafe', createdAt: '' }])
    expect(readConversationMessages(storage, 'project:one')).toEqual([])
  })
})
