'use client'

const DEFAULT_AGENT_AVATAR_SRC = '/default-avatar.jpg'

type TypingIndicatorProps = {
  agentBubbleBg?: string
  agentBubbleTextColor?: string
  agentBubbleRadius?: number[]
  agentBubbleBorder?: string
  showAvatar?: boolean
  agentAvatar?: string | null
  agentName?: string | null
  locale?: string
}

function toCssBorderRadius(radius: number[]): string {
  const [topLeft, topRight, bottomLeft, bottomRight] = radius
  return `${topLeft}px ${topRight}px ${bottomRight}px ${bottomLeft}px`
}

export function TypingIndicator({
  agentBubbleBg,
  agentBubbleTextColor,
  agentBubbleRadius,
  agentBubbleBorder,
  showAvatar = false,
  agentAvatar,
  agentName,
  locale = 'zh',
}: TypingIndicatorProps) {
  const radius = agentBubbleRadius || [10, 10, 0, 10]
  const label = locale === 'zh' ? '输入中...' : 'Typing...'
  const dotStyle = { backgroundColor: agentBubbleTextColor || 'var(--color-foreground)' }

  return (
    <div className="flex items-end gap-2 px-5 py-1">
      {showAvatar && (
        <img
          src={agentAvatar || DEFAULT_AGENT_AVATAR_SRC}
          alt={agentName || ''}
          className="h-9 w-9 shrink-0 rounded-full object-cover"
        />
      )}

      <div className="flex max-w-[75%] flex-col items-start gap-1">
        <div
          className="inline-flex items-center gap-1 px-4 py-3"
          style={{
            backgroundColor: agentBubbleBg || 'var(--color-secondary)',
            borderRadius: toCssBorderRadius(radius),
            border: agentBubbleBorder ? `1px solid ${agentBubbleBorder}` : undefined,
          }}
        >
          <span className="inline-block h-2 w-2 animate-bounce rounded-full [animation-delay:0ms]" style={dotStyle} />
          <span className="inline-block h-2 w-2 animate-bounce rounded-full [animation-delay:150ms]" style={dotStyle} />
          <span className="inline-block h-2 w-2 animate-bounce rounded-full [animation-delay:300ms]" style={dotStyle} />
        </div>
        <span className="text-[10px] text-muted-foreground">{label}</span>
      </div>
    </div>
  )
}
