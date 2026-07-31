'use client'

import { useEffect, useRef } from 'react'

import { cn } from '@/lib/utils'

/**
 * Presentational chat-bubble list for a call transcript. Shared by the live
 * (socket-driven) panel and the persisted history view. `final === false`
 * renders a streaming style (dimmed + caret).
 */
export type TranscriptBubble = {
  id: number
  role: 'user' | 'agent'
  text: string
  final?: boolean
}

const ROLE_LABEL: Record<'user' | 'agent', string> = {
  user: '用户',
  agent: '坐席',
}

export function TranscriptBubbles({
  items,
  autoScroll = false,
  fill = false,
}: {
  items: TranscriptBubble[]
  autoScroll?: boolean
  /** Fill parent height (call workspace) instead of a fixed max-height box. */
  fill?: boolean
}) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (autoScroll) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [items, autoScroll])

  return (
    <div
      ref={scrollRef}
      className={cn(
        'overflow-y-auto',
        fill ? 'flex min-h-0 flex-1 flex-col' : 'max-h-72 min-h-[120px]',
      )}
    >
      {/* mt-auto pins short transcripts to the bottom (same as live). */}
      <div className={cn('flex flex-col gap-2', fill && 'mt-auto')}>
        {items.map((c) => {
          const isAgent = c.role === 'agent'
          return (
            <div
              key={c.id}
              className={cn('flex flex-col', isAgent ? 'items-end' : 'items-start')}
            >
              <span className="mb-0.5 px-1 text-[10px] text-muted-foreground">
                {ROLE_LABEL[c.role]}
              </span>
              <div
                className={cn(
                  'max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-3 py-2 text-sm',
                  isAgent
                    ? 'rounded-br-sm bg-primary text-primary-foreground'
                    : 'rounded-bl-sm bg-muted text-foreground',
                  c.final === false && 'opacity-70',
                )}
              >
                {c.text}
                {c.final === false && (
                  <span className="ml-0.5 animate-pulse">▍</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
