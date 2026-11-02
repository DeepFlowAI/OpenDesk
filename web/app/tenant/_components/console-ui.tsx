'use client'

import type { ReactNode } from 'react'
import { IconArrowLeft, IconChevronLeft, IconChevronRight } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'

export const FIELD_CLASS =
  'h-9 w-full rounded-lg border border-input bg-background px-3 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-60 aria-invalid:border-destructive'

export function PageHeader({ title, actions }: { title: string; actions?: ReactNode }) {
  return (
    <div className="flex items-center justify-between px-8 py-6">
      <h1 className="font-display text-xl font-bold text-foreground">{title}</h1>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

export function DetailTopBar({
  title,
  onBack,
  actions,
}: {
  title: string
  onBack: () => void
  actions?: ReactNode
}) {
  return (
    <div className="sticky top-0 z-20 flex h-14 shrink-0 items-center justify-between border-b border-border bg-background px-6">
      <button
        type="button"
        onClick={onBack}
        className="flex items-center gap-2 text-foreground transition-colors hover:text-foreground/80"
      >
        <IconArrowLeft size={20} className="text-muted-foreground" />
        <span className="text-base font-semibold">{title}</span>
      </button>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

export function FormSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-4">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      {children}
    </section>
  )
}

export function Field({
  label,
  htmlFor,
  required,
  hint,
  error,
  children,
}: {
  label?: string
  htmlFor?: string
  required?: boolean
  hint?: string
  error?: string
  children: ReactNode
}) {
  return (
    <div className="space-y-1.5">
      {label && (
        <label htmlFor={htmlFor} className="text-sm font-medium text-foreground">
          {label}
          {required && <span className="ml-0.5 text-destructive">*</span>}
        </label>
      )}
      {children}
      {error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : (
        hint && <p className="text-xs text-muted-foreground">{hint}</p>
      )}
    </div>
  )
}

type Tone = 'success' | 'muted' | 'info' | 'warning'

const TONE_CLASS: Record<Tone, string> = {
  success: 'bg-success/10 text-success',
  muted: 'bg-muted text-muted-foreground',
  info: 'bg-info/10 text-info',
  warning: 'bg-warning/10 text-warning',
}

export function StatusPill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        TONE_CLASS[tone],
      )}
    >
      {children}
    </span>
  )
}

export function LoadingState() {
  const { locale } = useLocaleStore()
  return (
    <div className="flex items-center justify-center py-20 text-sm text-muted-foreground">
      {t('tc.common.loading', locale)}
    </div>
  )
}

export function EmptyState({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-border py-16">
      <p className="text-sm text-muted-foreground">{title}</p>
      {action}
    </div>
  )
}

const PER_PAGE_OPTIONS = [10, 20, 50, 100]

export function ConsolePagination({
  page,
  pages,
  total,
  perPage,
  onPageChange,
  onPerPageChange,
}: {
  page: number
  pages: number
  total: number
  perPage: number
  onPageChange: (page: number) => void
  onPerPageChange: (perPage: number) => void
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="flex items-center justify-between border-t border-border px-8 py-3 text-sm text-muted-foreground">
      <span>{t('tc.common.total', locale, { total })}</span>
      <div className="flex items-center gap-3">
        <select
          aria-label={t('tc.common.perPage', locale)}
          value={perPage}
          onChange={(e) => onPerPageChange(Number(e.target.value))}
          className="h-8 rounded-lg border border-input bg-background px-2 text-sm text-foreground"
        >
          {PER_PAGE_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {t('tc.common.perPageOption', locale, { n })}
            </option>
          ))}
        </select>
        <button
          type="button"
          aria-label={t('tc.common.prevPage', locale)}
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="flex size-8 items-center justify-center rounded-lg border border-border transition-colors hover:bg-accent disabled:opacity-40"
        >
          <IconChevronLeft size={16} />
        </button>
        <span className="min-w-[56px] text-center text-foreground">
          {page} / {Math.max(pages, 1)}
        </span>
        <button
          type="button"
          aria-label={t('tc.common.nextPage', locale)}
          disabled={page >= pages}
          onClick={() => onPageChange(page + 1)}
          className="flex size-8 items-center justify-center rounded-lg border border-border transition-colors hover:bg-accent disabled:opacity-40"
        >
          <IconChevronRight size={16} />
        </button>
      </div>
    </div>
  )
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`
}

export const TABLE_HEAD_CLASS = 'h-11 px-4 text-left text-xs font-semibold text-muted-foreground whitespace-nowrap'
export const TABLE_CELL_CLASS = 'px-4 py-3 text-sm text-foreground'
