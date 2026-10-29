'use client'

import { IconDownload } from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import type { CallReportExportParams } from '@/models/call-report-export'
import { useCallReportExport } from '@/service/use-call-report-export'
import { useSystemInfo } from '@/service/use-system'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'

type ToastState = { type: 'success' | 'error'; text: string }

export function CallReportExportButton({ params, disabled }: {
  params: CallReportExportParams
  disabled?: boolean
}) {
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const { data: systemInfo } = useSystemInfo()
  const mutation = useCallReportExport()
  const [toast, setToast] = useState<ToastState | null>(null)

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 2200)
    return () => window.clearTimeout(timer)
  }, [toast])

  if (!(systemInfo?.reports_enabled ?? true) || !hasPermission(user, 'call.report.export')) return null

  const handleExport = async () => {
    try {
      const { blob, filename } = await mutation.mutateAsync(params)
      triggerDownload(blob, filename)
      setToast({ type: 'success', text: t('ws.records.callReports.export.success', locale) })
    } catch {
      setToast({ type: 'error', text: t('ws.records.callReports.export.failed', locale) })
    }
  }

  return <>
    <button type="button" onClick={handleExport} disabled={disabled || mutation.isPending}
      className={cn('flex h-9 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-[13px] text-foreground transition-colors',
        disabled || mutation.isPending ? 'cursor-not-allowed opacity-50' : 'hover:bg-muted/50')}>
      <IconDownload size={16} className={mutation.isPending ? 'animate-pulse' : ''} />
      {t(mutation.isPending ? 'ws.records.callReports.export.exporting' : 'ws.records.callReports.export.button', locale)}
    </button>
    {toast ? <div className={cn('fixed right-6 top-6 z-50 rounded-lg border px-4 py-2 text-sm shadow-lg',
      toast.type === 'success' ? 'border-success/30 bg-success/10 text-success' : 'border-destructive/30 bg-destructive/10 text-destructive')}>
      {toast.text}
    </div> : null}
  </>
}

function triggerDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename || 'call-report.xlsx'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.URL.revokeObjectURL(url)
}
