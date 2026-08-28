import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ConversationTranslationSettings } from '@/models/lingomaster'

const state = vi.hoisted(() => ({
  settings: {
    global_enabled: false,
    visitor_language: 'zh',
    visitor_language_source: 'detected' as const,
    visitor_language_locked: false,
    visitor_translation_enabled: false,
    agent_translation_enabled: false,
    visitor_translation_preference: true,
    agent_translation_preference: true,
    visitor_target_mode: 'agent' as const,
    visitor_target_language: null,
    resolved_visitor_target_language: 'zh',
    agent_language: 'zh',
    updated_by: null,
    updated_at: null,
  } satisfies ConversationTranslationSettings,
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ setQueryData: vi.fn() }),
}))

vi.mock('@/context/locale-store', () => ({
  useLocaleStore: () => ({ locale: 'zh' }),
}))

vi.mock('@/service/use-lingomaster', () => ({
  lingomasterKeys: { conversation: (conversationId: number) => ['lingomaster', 'conversation', conversationId] },
  useConversationTranslationSettings: () => ({ data: state.settings, isError: false, isLoading: false }),
  useUpdateConversationTranslationSettings: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/utils/i18n', () => ({
  t: (key: string) => ({
    'ws.chat.translation.source.detected': '自动识别',
  })[key] ?? key,
}))

import { ConversationTranslationControl } from './conversation-translation-control'

describe('ConversationTranslationControl', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true
    state.settings.global_enabled = false
    state.settings.agent_translation_enabled = false
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(async () => {
    await act(async () => root.unmount())
    container.remove()
  })

  it('does not render the workspace control when LingoMaster is globally disabled', async () => {
    await act(async () => {
      root.render(
        <ConversationTranslationControl conversationId={1} canManage socket={null} />,
      )
    })

    expect(container.innerHTML).toBe('')
  })

  it('shows only the visitor language in the workspace entry', async () => {
    state.settings.global_enabled = true
    state.settings.agent_translation_enabled = true

    await act(async () => {
      root.render(
        <ConversationTranslationControl conversationId={1} canManage socket={null} />,
      )
    })

    expect(container.querySelector('button')?.textContent).toBe('中文')
  })
})
