import { cn } from '@/lib/utils'
import { avatarBackgroundForName, singleAvatarLetter } from '@/lib/avatar-fallback'

const SIZE_CLASS: Record<'xs' | 'sm' | 'md', string> = {
  xs: 'h-4 w-4 text-[8px] leading-none',
  sm: 'h-5 w-5 text-[9px] leading-none',
  md: 'h-6 w-6 text-[10px] leading-none',
}

/**
 * Circular avatar for ticket activity rows — real photo when `src` is set,
 * otherwise a single letter on a stable hue from `name`.
 */
export function ActivityActorAvatar({
  name,
  src,
  className,
  size = 'xs',
}: {
  name: string
  src?: string | null
  className?: string
  size?: 'xs' | 'sm' | 'md'
}) {
  const s = SIZE_CLASS[size]
  const label = singleAvatarLetter(name)
  if (src) {
    return (
      <span
        className={cn(
          'inline-flex shrink-0 overflow-hidden rounded-full bg-muted',
          s,
          className,
        )}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt="" className="h-full w-full object-cover" />
      </span>
    )
  }
  const bg = avatarBackgroundForName(name)
  return (
    <span
      className={cn(
        'inline-flex shrink-0 select-none items-center justify-center rounded-full font-semibold text-white',
        s,
        className,
      )}
      style={{ backgroundColor: bg }}
      aria-hidden
    >
      {label}
    </span>
  )
}
