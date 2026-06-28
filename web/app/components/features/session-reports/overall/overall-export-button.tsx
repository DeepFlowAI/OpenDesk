'use client'

import { IconDownload } from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { useSystemInfo } from '@/service/use-system'
import { useOverallExport } from '@/service/use-session-reports-overall'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'
import type { OverallExportParams } from '@/models/session-report-overall'

type ToastState = { type: 'success' | 'error'; text: string }

type Props = {
  params: OverallExportParams
  disabled?: boolean
}

/** Export button for the grouped overall report (hits /overall/export). */
export function OverallExportButton({ params, disabled }: Props) {
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const { data: systemInfo } = useSystemInfo()
  const exportMutation = useOverallExport()
  const [toast, setToast] = useState<ToastState | null>(null)

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 2200)
    return () => window.clearTimeout(timer)
  }, [toast])

  const reportsEnabled = systemInfo?.reports_enabled ?? true
  const canExport = hasPermission(user, 'chat.session_report.export')
  if (!reportsEnabled || !canExport) return null

  const exporting = exportMutation.isPending

  const handleExport = async () => {
    try {
      const { blob, filename } = await exportMutation.mutateAsync(params)
      triggerDownload(blob, filename)
      setToast({ type: 'success', text: t('ws.records.sessionReports.export.success', locale) })
    } catch {
      setToast({ type: 'error', text: t('ws.records.sessionReports.export.failed', locale) })
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
          disabled || exporting ? 'cursor-not-allowed opacity-50' : 'hover:bg-muted/50'
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
