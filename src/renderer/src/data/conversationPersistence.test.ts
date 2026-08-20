import { describe, expect, it } from 'vitest'

import { readConversationTimeline, writeConversationTimeline } from './conversationPersistence'

describe('conversation timeline persistence', () => {
  it('round-trips ordered timeline items and rejects malformed records', () => {
    let stored: string | null = null
    const storage = {
      getItem: () => stored,
      setItem: (_key: string, value: string) => { stored = value },
    }
    writeConversationTimeline(storage, 'project:one', [{
      type: 'text', id: 'message:user:one', turnId: 'turn:one', role: 'user',
      text: '把纵轴改为 log10', createdAt: '2026-08-13T00:00:00.000Z',
    }, {
      type: 'plan', id: 'plan:one', turnId: 'turn:one', createdAt: '2026-08-13T00:00:01.000Z',
      plan: {
        planId: 'plan:one', state: 'running', confirmationState: 'confirmed', warnings: [],
        steps: [], completedCount: 0, resumable: false, bindings: [], boundActions: [],
      },
    }])
    expect(readConversationTimeline(storage, 'project:one').map((item) => item.type)).toEqual(['text', 'plan'])

    stored = JSON.stringify([{ type: 'plot', id: 'bad', createdAt: '', plotNumber: 0, plot: {} }])
    expect(readConversationTimeline(storage, 'project:one')).toEqual([])
  })

  it('migrates valid v1 messages when no v2 timeline exists', () => {
    const legacy = JSON.stringify([{
      id: 'message:legacy', role: 'agent', title: '需要补充信息', text: '请选择图形。',
      createdAt: '2026-08-13T00:00:00.000Z', kind: 'warning',
    }])
    const storage = { getItem: (key: string) => key.includes('conversation.v1:') ? legacy : null }
    expect(readConversationTimeline(storage, 'project:one')).toEqual([{
      type: 'text', id: 'message:legacy', role: 'agent', title: '需要补充信息', text: '请选择图形。',
      createdAt: '2026-08-13T00:00:00.000Z', kind: 'warning',
    }])
  })
})
