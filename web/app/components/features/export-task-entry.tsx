'use client'

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { IconDownload } from '@tabler/icons-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/tiptap-ui-primitive/tooltip'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { claimExportNotifications, useExportStatus } from '@/service/use-export-tasks'
import { t } from '@/utils/i18n'

export function ExportTaskEntry() {
  const status = useExportStatus()
  const { locale } = useLocaleStore()
  const router = useRouter()
  const token = useAuthStore((state) => state.token)
  const employeeId = useAuthStore((state) => state.user?.id)
  const tenantId = useAuthStore((state) => state.user?.tenant_id)
  const authenticated = Boolean(token)
  const { refetch } = status
  const localeRef = useRef(locale)
  localeRef.current = locale

  useEffect(() => {
    if (!authenticated || !employeeId || !tenantId) return
    let cursor: string | null = null
    let busy = false
    let controller: AbortController | null = null
    let stopped = false
    let generation = 0
    const poll = async () => {
      if (document.visibilityState !== 'visible' || busy || stopped) return
      busy = true
      const pollGeneration = generation
      controller = new AbortController()
      try {
        // Mount/reconnect establishes a server-time baseline without claiming old results.
        if (!cursor) {
          const result = await refetch()
          if (result.isSuccess && !stopped && pollGeneration === generation) cursor = result.data.server_time
          return
        }
        const result = await claimExportNotifications(cursor, controller.signal)
        if (stopped || pollGeneration !== generation || document.visibilityState !== 'visible') return
        cursor = result.server_time
        const language = localeRef.current
        for (const task of result.items) {
          const name = task.name[language] ?? task.name.zh ?? task.name.en
          toast(task.status === 'completed'
            ? t('exports.completedNotice', language, { name, count: task.row_count ?? 0 })
            : t('exports.failedNotice', language, { name }), {
            id: `export-result-${task.id}`,
            action: { label: t('exports.viewTasks', language), onClick: () => router.push('/workspace/exports') },
          })
        }
      } catch {
        cursor = null
      } finally {
        busy = false
      }
    }
    const onVisibility = () => {
      generation += 1
      cursor = null
      controller?.abort()
      if (document.visibilityState === 'visible') void poll()
    }
    void poll()
    const timer = window.setInterval(() => void poll(), 5000)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      stopped = true
      controller?.abort()
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  // refetch is stable; account changes reset the notification baseline.
  }, [authenticated, employeeId, tenantId, router, refetch])

  if (!token || !status.data?.visible) return null
  const label = t('exports.title', locale)
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={label}
          onClick={() => router.push('/workspace/exports')}>
          <IconDownload size={20} />
          {status.data.unread > 0 && <>
            <span aria-hidden="true" className="absolute right-1 top-1 size-1.5 rounded-full bg-destructive" />
            <span className="sr-only">{t('exports.unread', locale)}</span>
          </>}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}
