'use client'

import { cn } from '@/lib/utils'

type Props = {
  current: number
  max?: number | null
}

export function CurrentLoad({ current, max }: Props) {
  if (max == null || max <= 0) {
    return <span className="text-muted-foreground">{current} / —</span>
  }
  const isOver = current > max
  const isAtCap = !isOver && current >= max
  return (
    <span
      className={cn(
        'tabular-nums',
        isOver && 'font-semibold text-[#DC2626]',
        isAtCap && 'text-[#D97706]'
      )}
    >
      {current} / {max}
    </span>
  )
}
