import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/i18n', () => ({
  t: (key: string) => ({
    'ws.chat.translation.original': '原文',
    'ws.chat.translation.translated': '译文',
    'ws.chat.translation.translating': '正在翻译…',
  })[key] ?? key,
}))

import { TranslatedMessageContent } from './translated-message-content'

describe('TranslatedMessageContent', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(async () => {
    await act(async () => root.unmount())
    container.remove()
  })

  it('shows the translation label without an extra translation badge', async () => {
    await act(async () => {
      root.render(
        <TranslatedMessageContent
          content="what's wrong"
          isRichText={false}
          translation={{
            status: 'translated',
            source_language: 'en',
            target_language: 'zh',
            translated_text: '怎么了？',
          }}
          locale="zh"
        />,
      )
    })

    expect(container.textContent).toBe("原文what's wrong译文怎么了？")
  })

  it('shows an inline progress state while translating', async () => {
    await act(async () => {
      root.render(
        <TranslatedMessageContent
          content="can you help me please"
          isRichText={false}
          translation={{
            status: 'pending',
            source_language: 'en',
            target_language: 'zh',
            direction: 'visitor_to_agent',
          }}
          locale="zh"
        />,
      )
    })

    expect(container.textContent).toBe('can you help me please正在翻译…')
    expect(container.querySelector('[role="status"]')).not.toBeNull()
  })
})
