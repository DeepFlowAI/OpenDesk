'use client'

import { useEffect, useRef } from 'react'

import { cn } from '@/lib/utils'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

/**
 * Presentational chat-bubble list for a call transcript. Shared by the live
 * (socket-driven) panel and the persisted history view. `final === false`
 * renders a streaming style (dimmed + caret).
 */
export type TranscriptBubble = {
  id: number
  role: 'user' | 'agent' | 'bot'
  text: string
  final?: boolean
  interrupted?: boolean
}

const ROLE_KEY: Record<TranscriptBubble['role'], string> = {
  user: 'ws.call.roleUser',
  agent: 'ws.call.roleAgent',
  bot: 'ws.call.roleBot',
}

export function TranscriptBubbles({
  items,
  autoScroll = false,
  fill = false,
  embedded = false,
}: {
  items: TranscriptBubble[]
  autoScroll?: boolean
  /** Fill parent height (call workspace) instead of a fixed max-height box. */
  fill?: boolean
  /** Render bubbles only; parent owns scrolling. */
  embedded?: boolean
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const { locale } = useLocaleStore()

  useEffect(() => {
    if (embedded || !autoScroll) return
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [items, autoScroll, embedded])

  const list = (
    <div className={cn('flex flex-col gap-2', fill && !embedded && 'mt-auto')}>
      {items.map((c) => {
        const alignedEnd = c.role !== 'user'
        return (
          <div
            key={c.id}
            className={cn('flex flex-col', alignedEnd ? 'items-end' : 'items-start')}
          >
            <span className="mb-0.5 px-1 text-[10px] text-muted-foreground">
              {t(ROLE_KEY[c.role], locale)}
            </span>
            <div
              className={cn(
                'max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-3 py-2 text-sm',
                bubbleClass(c.role),
                c.final === false && 'opacity-70',
              )}
            >
              {c.text}
              {c.final === false && (
                <span className="ml-0.5 animate-pulse">▍</span>
              )}
            </div>
            {c.interrupted && (
              <span className="mt-0.5 px-1 text-[10px] text-muted-foreground">
                {t('ws.call.interrupted', locale)}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )

  if (embedded) return list

  return (
    <div
      ref={scrollRef}
      className={cn(
        'overflow-y-auto',
        fill ? 'flex min-h-0 flex-1 flex-col' : 'max-h-72 min-h-[120px]',
      )}
    >
      {list}
    </div>
  )
}

function bubbleClass(role: TranscriptBubble['role']) {
  if (role === 'agent') return 'rounded-br-sm bg-primary text-primary-foreground'
  if (role === 'bot') return 'rounded-br-sm border border-border bg-secondary text-foreground'
  return 'rounded-bl-sm bg-muted text-foreground'
}
