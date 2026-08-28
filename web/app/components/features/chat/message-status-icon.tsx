'use client'

import {
  FloatingPortal,
  autoUpdate,
  flip,
  offset,
  shift,
  useDismiss,
  useFloating,
  useFocus,
  useHover,
  useInteractions,
  useRole,
} from '@floating-ui/react'
import {
  IconCircle,
  IconCircleCheck,
  IconCloud,
  IconLoader2,
} from '@tabler/icons-react'
import { useState } from 'react'

import type { Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'

export type VisibleMessageStatus = 'sending' | 'offline' | 'unread' | 'read'

export function resolveVisibleMessageStatus(
  status: string | undefined,
  options: {
    enabled: boolean
    deliveredAsUnread?: boolean
    alwaysShowOffline?: boolean
  },
): VisibleMessageStatus | null {
  if (status === 'sending') return 'sending'
  if (status === 'offline') return options.enabled || options.alwaysShowOffline ? 'offline' : null
  if (!options.enabled) return null
  if (status === 'unread' || (options.deliveredAsUnread && status === 'delivered')) return 'unread'
  if (status === 'read') return 'read'
  return null
}

function statusLabel(status: VisibleMessageStatus, locale: Locale): string {
  return t(`chat.messageStatus.${status}`, locale)
}

export function MessageStatusIcon({
  status,
  locale,
  tone = 'blue',
}: {
  status: VisibleMessageStatus
  locale: Locale
  tone?: 'blue' | 'gray'
}) {
  const [open, setOpen] = useState(false)
  const { refs, floatingStyles, context } = useFloating({
    open,
    onOpenChange: setOpen,
    placement: 'top',
    whileElementsMounted: autoUpdate,
    middleware: [offset(6), flip({ padding: 4 }), shift({ padding: 4 })],
  })
  const hover = useHover(context, { mouseOnly: true, move: false, delay: { open: 0, close: 0 } })
  const focus = useFocus(context)
  const dismiss = useDismiss(context)
  const role = useRole(context, { role: 'tooltip' })
  const { getReferenceProps, getFloatingProps } = useInteractions([hover, focus, dismiss, role])
  const label = statusLabel(status, locale)
  const iconClassName = cn(
    'h-4 w-4',
    tone === 'gray' ? 'text-[#A3A3A3]' : 'text-[#93C5FD]',
    status === 'sending' && 'motion-safe:animate-spin motion-reduce:animate-none',
  )

  return (
    <>
      <span
        ref={refs.setReference}
        tabIndex={0}
        role="img"
        aria-label={label}
        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        {...getReferenceProps()}
      >
        {status === 'sending' && <IconLoader2 className={iconClassName} aria-hidden="true" />}
        {status === 'offline' && <IconCloud className={iconClassName} aria-hidden="true" />}
        {status === 'unread' && <IconCircle className={iconClassName} aria-hidden="true" />}
        {status === 'read' && <IconCircleCheck className={iconClassName} aria-hidden="true" />}
      </span>
      {open && (
        <FloatingPortal>
          <div
            ref={refs.setFloating}
            style={floatingStyles}
            className="z-[100] whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background shadow-md"
            {...getFloatingProps()}
          >
            {label}
          </div>
        </FloatingPortal>
      )}
    </>
  )
}
