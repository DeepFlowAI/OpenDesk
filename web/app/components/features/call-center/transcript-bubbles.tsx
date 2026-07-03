'use client'

import { useEffect, useRef } from 'react'

import { cn } from '@/lib/utils'

/**
 * Presentational chat-bubble list for a call transcript. Shared by the live
 * (socket-driven) panel and the persisted history view. `final === false`
 * renders a streaming style (dimmed + caret on the last item).
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
}: {
  items: TranscriptBubble[]
  autoScroll?: boolean
}) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (autoScroll) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [items, autoScroll])

  return (
    <div
      ref={scrollRef}
      className="flex max-h-72 min-h-[120px] flex-col gap-2 overflow-y-auto"
    >
      {items.map((c, i) => {
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
              {c.final === false && i === items.length - 1 && (
                <span className="ml-0.5 animate-pulse">▍</span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
