'use client'

import { useEffect, useState } from 'react'
import { IconX, IconLoader2 } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useSessionRecordDetail } from '@/service/use-session-records'
import { MessageList } from './message-list'
import { SessionInfoPanel } from './session-info-panel'

type Props = {
  recordId: number
  onClose: () => void
}

export function SessionDetailDrawer({ recordId, onClose }: Props) {
  const { locale } = useLocaleStore()
  const { data: record, isLoading } = useSessionRecordDetail(recordId)
  const [summaryDirty, setSummaryDirty] = useState(false)

  const requestClose = () => {
    if (summaryDirty) {
      const confirmed = window.confirm(t('ws.summary.unsavedConfirm', locale))
      if (!confirmed) return
    }
    onClose()
  }

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') requestClose()
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [requestClose])

  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [])

  return (
    <div className="fixed inset-0 z-50">
      <div
        role="presentation"
        className="absolute inset-0 cursor-default bg-black/40 animate-opendesk-session-drawer-backdrop"
        onClick={requestClose}
      />
      {/* Full-width row so child w-[80%] resolves against the viewport, not a shrink-to-fit abspos width */}
      <div className="pointer-events-none absolute inset-0 flex justify-end">
        <div className="pointer-events-auto flex h-full min-w-0 w-[80%] max-w-[1200px] animate-opendesk-session-drawer-panel flex-col bg-background shadow-2xl">
        {/* Header */}
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
          <h2 className="text-base font-semibold text-foreground">
            {t('ws.records.sessions.detail.title', locale)}
          </h2>
          <button
            onClick={requestClose}
            className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <IconX size={18} />
          </button>
        </div>

        {/* Body */}
        {isLoading || !record ? (
          <div className="flex flex-1 items-center justify-center">
            <IconLoader2 size={28} className="animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="flex flex-1 overflow-hidden">
            {/* Left: Chat messages (read-only) */}
            <div className="flex min-w-0 flex-1 flex-col border-r border-border">
              <MessageList recordId={recordId} />
            </div>

            {/* Right: session info (~40% per spec). Avoid w-[min(...,...)] — Tailwind splits on comma and breaks width. */}
            <div className="flex w-[40%] min-w-[260px] max-w-sm shrink-0 flex-col overflow-x-hidden">
              <SessionInfoPanel record={record} onSummaryDirtyChange={setSummaryDirty} />
            </div>
          </div>
        )}
        </div>
      </div>
    </div>
  )
}
