'use client'

import {
  IconArrowsMaximize,
  IconCopy,
  IconGripVertical,
  IconMinus,
  IconPencil,
  IconPlus,
  IconTrash,
} from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { DashboardResult } from './dashboard-result'
import type { ComponentPreview, DashboardComponent } from '@/models/custom-dashboard'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

export function ComponentCard({
  component,
  preview,
  onEdit,
  onCopy,
  onDelete,
  onResize,
  onDragStart,
}: {
  component: DashboardComponent
  preview: ComponentPreview | undefined
  onEdit: () => void
  onCopy: () => void
  onDelete: () => void
  onResize: (widthDelta: number, heightDelta: number) => void
  onDragStart: (event: React.DragEvent) => void
}) {
  const { locale } = useLocaleStore()
  const response = preview?.response
  return (
    <article
      className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-sm"
      style={{ gridColumn: `${component.x + 1} / span ${component.w}`, gridRow: `${component.y + 1} / span ${component.h}` }}
    >
      <header className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-3">
        <button type="button" draggable onDragStart={onDragStart} className="cursor-grab text-muted-foreground active:cursor-grabbing" aria-label={t('cd.dragComponent', locale)}><IconGripVertical size={17} /></button>
        <h3 className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{component.title}</h3>
        <span className="text-xs text-muted-foreground">{preview?.status === 'success' ? t('cd.preview.success', locale) : preview?.status === 'failed' ? t('cd.preview.failed', locale) : preview?.status === 'running' ? t('cd.preview.running', locale) : t('cd.preview.waiting', locale)}</span>
        <Button variant="ghost" size="icon-xs" onClick={onEdit} aria-label={t('cd.editComponent', locale)}><IconPencil /></Button>
        <Button variant="ghost" size="icon-xs" onClick={onCopy} aria-label={t('cd.copyComponent', locale)}><IconCopy /></Button>
        <Button variant="ghost" size="icon-xs" onClick={onDelete} aria-label={t('cd.deleteComponent', locale)}><IconTrash /></Button>
      </header>
      <div className="min-h-0 flex-1">
        {preview?.status === 'running' ? <div className="flex h-full items-center justify-center text-sm text-muted-foreground">{t('cd.preview.running', locale)}</div> : response?.status === 'success' && response.result ? <DashboardResult output={response.result} /> : response?.message ? <div className="flex h-full flex-col items-center justify-center gap-2 p-5 text-center"><p className="text-sm text-destructive">{response.message}</p>{response.error_line && <p className="text-xs text-muted-foreground">{t('cd.errorLine', locale, { line: response.error_line })}</p>}</div> : <div className="flex h-full items-center justify-center text-sm text-muted-foreground">{t('cd.preview.empty', locale)}</div>}
      </div>
      <footer className="flex h-9 shrink-0 items-center justify-end gap-1 border-t border-border px-2">
        <IconArrowsMaximize size={14} className="mr-1 text-muted-foreground" />
        <Button variant="ghost" size="icon-xs" onClick={() => onResize(-1, 0)} disabled={component.w <= 3} aria-label={t('cd.widthDecrease', locale)}><IconMinus /></Button>
        <span className="w-8 text-center font-mono text-xs">{component.w}×{component.h}</span>
        <Button variant="ghost" size="icon-xs" onClick={() => onResize(1, 0)} disabled={component.w >= 12} aria-label={t('cd.widthIncrease', locale)}><IconPlus /></Button>
        <Button variant="ghost" size="icon-xs" onClick={() => onResize(0, -1)} disabled={component.h <= 4} aria-label={t('cd.heightDecrease', locale)}><IconMinus /></Button>
        <Button variant="ghost" size="icon-xs" onClick={() => onResize(0, 1)} disabled={component.h >= 24} aria-label={t('cd.heightIncrease', locale)}><IconPlus /></Button>
      </footer>
    </article>
  )
}
