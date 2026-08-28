'use client'
/**
 * Universal call bar shell.
 *
 * A reusable container for in-call control surfaces. It is deliberately
 * variant-agnostic: the agent workspace composes it with agent operations
 * (mute/hold/transfer/consult/conference), and the supervisor monitor composes
 * it with monitor operations (listen/whisper/barge/takeover/force-hangup).
 * Only the presentation shell is shared; the two variants never share the
 * business action set.
 *
 * Layout contract (acceptance-critical): the extension region is an INLINE
 * downward extension of the bar itself. When expanded, the bar grows taller and
 * the surrounding page content is pushed down — it is NOT a popover, dropdown,
 * dialog, or overlay, and it never uses a scrim.
 */
import type { ReactNode } from 'react'
import { IconChevronDown, IconChevronUp } from '@tabler/icons-react'

import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'

export type UniversalCallBarTone = 'active' | 'warning' | 'neutral' | 'destructive'

const TONE_CLASS: Record<UniversalCallBarTone, string> = {
  // Semantic tones only — no hard-coded hex values.
  active: 'border-success/30 bg-success/10',
  warning: 'border-warning/30 bg-warning/10',
  neutral: 'border-border bg-muted/40',
  destructive: 'border-destructive/30 bg-destructive/10',
}

export type UniversalCallBarProps = {
  /** Status/number/duration cluster shown at the start of the main row. */
  status: ReactNode
  /** High-frequency actions shown at the end of the main row. */
  mainActions: ReactNode
  /** Inline extension content revealed below the main row when expanded. */
  extension?: ReactNode
  tone?: UniversalCallBarTone
  expanded: boolean
  onToggleExpand: () => void
  /** When true the collapse control is hidden and the bar stays expanded. */
  expandLocked?: boolean
  /**
   * Toggle button chrome: 'label' renders text + chevron (default, used by the
   * supervisor monitor bar); 'icon' renders a 32×32 chevron-only button.
   */
  expandToggleVariant?: 'label' | 'icon'
  /** Optional trailing slot in the main row (e.g. "back to workspace" link). */
  trailing?: ReactNode
  className?: string
}

export function UniversalCallBar({
  status,
  mainActions,
  extension,
  tone = 'active',
  expanded,
  onToggleExpand,
  expandLocked = false,
  expandToggleVariant = 'label',
  trailing,
  className,
}: UniversalCallBarProps) {
  const { locale } = useLocaleStore()
  const showExtension = expanded && !!extension

  return (
    <div className={cn('rounded-lg border', TONE_CLASS[tone], className)}>
      {/* Persistent main row */}
      <div className="flex min-h-11 flex-wrap items-center gap-3 px-3 py-2">
        <div className="flex min-w-0 flex-1 items-center gap-3">{status}</div>
        <div className="flex shrink-0 items-center gap-2">{mainActions}</div>
        {extension && expandToggleVariant === 'icon' ? (
          <button
            type="button"
            onClick={onToggleExpand}
            disabled={expandLocked && expanded}
            aria-expanded={expanded}
            title={expanded ? t('ws.callbar.collapse', locale) : t('ws.callbar.expand', locale)}
            aria-label={expanded ? t('ws.callbar.collapse', locale) : t('ws.callbar.expand', locale)}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-md border border-border/60 bg-background/60 text-foreground/80 transition-colors hover:bg-background disabled:cursor-not-allowed disabled:opacity-60"
          >
            {expanded ? <IconChevronUp size={16} /> : <IconChevronDown size={16} />}
          </button>
        ) : extension ? (
          <button
            type="button"
            onClick={onToggleExpand}
            disabled={expandLocked && expanded}
            aria-expanded={expanded}
            aria-label={expanded ? t('ws.callbar.collapse', locale) : t('ws.callbar.expand', locale)}
            className={cn(
              'flex h-8 shrink-0 items-center gap-1 rounded-md border border-border/60 bg-background/60 px-2 text-xs font-medium text-foreground/80 transition-colors hover:bg-background disabled:cursor-not-allowed disabled:opacity-60',
            )}
          >
            <span>{expanded ? t('ws.callbar.collapse', locale) : t('ws.callbar.expand', locale)}</span>
            {expanded ? <IconChevronUp size={14} /> : <IconChevronDown size={14} />}
          </button>
        ) : null}
        {trailing && <div className="flex shrink-0 items-center">{trailing}</div>}
      </div>

      {/* Inline downward extension — grows the bar, pushes page content down. */}
      {showExtension && (
        <div className="border-t border-border/50 px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">{extension}</div>
        </div>
      )}
    </div>
  )
}
