import {
  Children,
  cloneElement,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from 'react'
import { cn } from '@/lib/utils'

export type ActivityTimelineRowProps = {
  children: ReactNode
  /** Injected by {@link ActivityTimeline} on the last row; hides rail below the last dot. */
  isLast?: boolean
  showRail?: boolean
  railTailClassName?: string
  railTailTopClassName?: string
  dotOffsetClassName?: string
}

/**
 * Wraps a vertical activity list with one continuous rail so the line is not
 * broken by row gaps.
 */
export function ActivityTimeline({
  children,
  showRail = true,
  railTailClassName = 'bg-[#f5f5f5]',
  railTopClassName = 'top-[22px]',
}: {
  children: ReactNode
  showRail?: boolean
  railTailClassName?: string
  railTopClassName?: string
}) {
  const items = Children.toArray(children) as ReactElement<ActivityTimelineRowProps>[]

  return (
    <div className="relative">
      {showRail ? (
        <div
          className={cn(
            'pointer-events-none absolute bottom-0 left-2 z-0 w-px -translate-x-1/2 bg-[#d4d4d4]',
            railTopClassName,
          )}
          aria-hidden
        />
      ) : null}
      <div className="relative z-[1] flex flex-col gap-5">
        {items.map((child, index) => {
          if (isValidElement<ActivityTimelineRowProps>(child)) {
            return cloneElement(child, {
              isLast: index === items.length - 1,
              showRail,
              railTailClassName,
            })
          }
          return child
        })}
      </div>
    </div>
  )
}

/**
 * One row in the right-rail activity feed: left dot + content card.
 * Rail line is drawn by {@link ActivityTimeline}. Pass as direct children of
 * ActivityTimeline so the parent can set {@link ActivityTimelineRowProps.isLast}.
 */
export function ActivityTimelineRow({
  children,
  isLast = false,
  showRail = true,
  railTailClassName = 'bg-[#f5f5f5]',
  railTailTopClassName = 'top-[26px]',
  dotOffsetClassName = 'pt-[18px]',
}: ActivityTimelineRowProps) {
  return (
    <div className="flex gap-2.5">
      <div
        className={cn(
          'relative flex w-4 shrink-0 flex-col items-center self-stretch',
          dotOffsetClassName,
        )}
        aria-hidden
      >
        <span className="z-[1] h-2 w-2 shrink-0 rounded-full bg-foreground" />
        {showRail && isLast ? (
          <div
            className={cn(
              'pointer-events-none absolute bottom-0 left-1/2 z-[2] w-3 -translate-x-1/2',
              railTailTopClassName,
              railTailClassName,
            )}
            aria-hidden
          />
        ) : null}
      </div>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}
