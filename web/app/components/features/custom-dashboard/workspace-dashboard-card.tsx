'use client'

import { IconRefresh } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { DashboardResult } from './dashboard-result'
import type { ComponentPreview, WorkspaceDashboardComponent } from '@/models/custom-dashboard'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

export function WorkspaceDashboardCard({
  component,
  preview,
  onRetry,
  onDrilldown,
}: {
  component: WorkspaceDashboardComponent
  preview: ComponentPreview | undefined
  onRetry: () => void
  onDrilldown: (output: Record<string, unknown>) => void
}) {
  const { locale } = useLocaleStore()
  const response = preview?.response
  const output = response?.status === 'success' ? response.result : null
  const drillable = Boolean(output?.drilldown)
  return (
    <article className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-sm" style={{ gridColumn: `${component.x + 1} / span ${component.w}`, gridRow: `${component.y + 1} / span ${component.h}` }}>
      <header className="flex h-11 shrink-0 items-center justify-between border-b border-border px-4"><h2 className="truncate text-sm font-medium text-foreground">{component.title}</h2>{response?.cached && <span className="text-xs text-muted-foreground">{t('ws.cd.cached', locale)}</span>}</header>
      <div className="min-h-0 flex-1">
        {!preview || preview.status === 'idle' ? <StatusPanel text={t('ws.cd.waiting', locale)} />
          : preview.status === 'running' ? <div className="flex h-full flex-col items-center justify-center gap-3"><div className="h-3 w-32 animate-pulse rounded bg-muted" /><p className="text-sm text-muted-foreground">{t('ws.cd.running', locale)}</p></div>
            : output ? (drillable ? <button type="button" className="h-full w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring" onClick={() => onDrilldown(output)} aria-label={t('ws.cd.drilldown', locale)}><DashboardResult output={output} /></button> : <DashboardResult output={output} />)
              : <div className="flex h-full flex-col items-center justify-center gap-3 p-5 text-center"><p className="text-sm text-destructive">{response?.message || t('ws.cd.runFailed', locale)}</p>{preview.status !== 'cooldown' && <Button variant="outline" size="sm" onClick={onRetry}><IconRefresh />{t('ws.cd.retry', locale)}</Button>}</div>}
      </div>
      {response?.completed_at && <footer className="border-t border-border px-4 py-2 text-xs text-muted-foreground">{t('ws.cd.completedAt', locale, { time: new Date(response.completed_at).toLocaleTimeString(locale) })}</footer>}
    </article>
  )
}

function StatusPanel({ text }: { text: string }) {
  return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">{text}</div>
}
