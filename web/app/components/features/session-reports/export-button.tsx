'use client'

import { IconDownload } from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { useSystemInfo } from '@/service/use-system'
import { useSessionQueueReportExport, useSessionReportExport } from '@/service/use-session-reports'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'
import type { QueueReportExportParams, SessionReportExportParams } from '@/models/session-report'

type ToastState = {
  type: 'success' | 'error'
  text: string
}

type Props = {
  params: SessionReportExportParams | QueueReportExportParams
  disabled?: boolean
  variant?: 'session' | 'queue'
}

export function SessionReportExportButton({ params, disabled, variant = 'session' }: Props) {
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const { data: systemInfo } = useSystemInfo()
  const sessionExportMutation = useSessionReportExport()
  const queueExportMutation = useSessionQueueReportExport()
  const [toast, setToast] = useState<ToastState | null>(null)

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 2200)
    return () => window.clearTimeout(timer)
  }, [toast])

  const reportsEnabled = systemInfo?.reports_enabled ?? true
  const canExport = hasPermission(user, 'chat.session_report.export')

  if (!reportsEnabled || !canExport) return null

  const exporting = variant === 'queue'
    ? queueExportMutation.isPending
    : sessionExportMutation.isPending

  const handleExport = async () => {
    try {
      const { blob, filename } = variant === 'queue'
        ? await queueExportMutation.mutateAsync(params as QueueReportExportParams)
        : await sessionExportMutation.mutateAsync(params as SessionReportExportParams)
      triggerDownload(blob, filename)
      setToast({
        type: 'success',
        text: t('ws.records.sessionReports.export.success', locale),
      })
    } catch {
      setToast({
        type: 'error',
        text: t('ws.records.sessionReports.export.failed', locale),
      })
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={handleExport}
        disabled={disabled || exporting}
        className={cn(
          'flex h-9 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-[13px] text-foreground transition-colors',
          disabled || exporting
            ? 'cursor-not-allowed opacity-50'
            : 'hover:bg-muted/50'
        )}
      >
        <IconDownload size={16} className={exporting ? 'animate-pulse' : ''} />
        {exporting
          ? t('ws.records.sessionReports.export.exporting', locale)
          : t('ws.records.sessionReports.export.button', locale)}
      </button>
      {toast && (
        <div
          className={cn(
            'fixed right-6 top-6 z-50 rounded-lg border px-4 py-2 text-sm shadow-lg',
            toast.type === 'success'
              ? 'border-success/30 bg-success/10 text-success'
              : 'border-destructive/30 bg-destructive/10 text-destructive'
          )}
        >
          {toast.text}
        </div>
      )}
    </>
  )
}

function triggerDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename || 'session-report.xlsx'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.URL.revokeObjectURL(url)
}
