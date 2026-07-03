'use client'
/**
 * Shared VoiceSpeed agent picker — searchable single-select with a refresh
 * button, used by both the routing-rule detail form and the voice-flow
 * VoiceSpeed node property panel. Owns the agent-list query and reports its
 * blocking state (not configured / load failed / selected-but-unavailable)
 * so the host form can disable Save accordingly.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import {
  IconAlertTriangle,
  IconCheck,
  IconChevronDown,
  IconRefresh,
  IconSearch,
} from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useVoiceSpeedAgents } from '@/service/use-open-agent-settings'

/** Overall state used by host forms to decide whether Save should be blocked. */
export type VoiceSpeedAgentSelectStatus =
  | 'loading'
  | 'not_configured'
  | 'forbidden'
  | 'error'
  | 'empty'
  | 'unavailable'
  | 'ok'

/** Whether the current state should prevent saving (regardless of required). */
export function isVoiceSpeedSelectBlocking(status: VoiceSpeedAgentSelectStatus): boolean {
  return (
    status === 'not_configured' ||
    status === 'forbidden' ||
    status === 'error' ||
    status === 'unavailable'
  )
}

export function VoiceSpeedAgentSelect({
  value,
  agentName,
  onChange,
  onStatusChange,
  enabled = true,
}: {
  value: string
  agentName?: string
  onChange: (agentId: string, agentName: string) => void
  onStatusChange?: (status: VoiceSpeedAgentSelectStatus) => void
  enabled?: boolean
}) {
  const { locale } = useLocaleStore()
  const { data, isLoading, isError, error, refetch, isRefetching } = useVoiceSpeedAgents(enabled)

  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const boxRef = useRef<HTMLDivElement>(null)

  const forbidden = isError && (error as { response?: Response })?.response?.status === 403
  const items = useMemo(() => data?.items ?? [], [data?.items])
  const selected = useMemo(() => items.find((a) => a.id === value), [items, value])
  // A value is set but no longer appears in the enabled list → unavailable.
  const unavailable = Boolean(value) && !isLoading && !isError && data?.configured === true && !selected

  const status: VoiceSpeedAgentSelectStatus = isLoading
    ? 'loading'
    : data?.configured === false
      ? 'not_configured'
      : forbidden
        ? 'forbidden'
        : isError
          ? 'error'
          : unavailable
            ? 'unavailable'
            : items.length === 0
              ? 'empty'
              : 'ok'

  useEffect(() => {
    onStatusChange?.(status)
  }, [status, onStatusChange])

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        (a.description ?? '').toLowerCase().includes(q),
    )
  }, [items, query])

  const disabled = isLoading || data?.configured === false || forbidden || isError

  const displayLabel = selected?.name || (value ? agentName || value : '')

  const handleRefresh = useCallback(() => {
    void refetch()
  }, [refetch])

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <div ref={boxRef} className="relative min-w-0 flex-1">
          <button
            type="button"
            disabled={disabled}
            onClick={() => setOpen((o) => !o)}
            className={cn(
              'flex h-10 w-full items-center justify-between gap-2 rounded-lg border bg-white px-3 text-left text-sm focus:outline-none focus:ring-1 focus:ring-ring',
              unavailable ? 'border-amber-400' : 'border-border',
              disabled && 'cursor-not-allowed opacity-60',
            )}
          >
            <span
              className={cn(
                'min-w-0 flex-1 truncate',
                displayLabel ? 'text-foreground' : 'text-muted-foreground',
              )}
            >
              {displayLabel || t('vs.agent.placeholder', locale)}
            </span>
            <IconChevronDown size={16} className="shrink-0 text-muted-foreground" />
          </button>

          {open && !disabled && (
            <div className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-lg border border-border bg-white shadow-md">
              <div className="flex items-center gap-2 border-b border-border px-2.5 py-2">
                <IconSearch size={14} className="shrink-0 text-muted-foreground" />
                <input
                  autoFocus
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={t('vs.agent.search.placeholder', locale)}
                  className="min-w-0 flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
                />
              </div>
              <ul className="max-h-60 overflow-auto py-1">
                {filtered.length === 0 ? (
                  <li className="px-3 py-3 text-center text-xs text-muted-foreground">
                    {items.length === 0
                      ? t('vs.agent.empty', locale)
                      : t('vs.agent.noMatch', locale)}
                  </li>
                ) : (
                  filtered.map((a) => (
                    <li key={a.id}>
                      <button
                        type="button"
                        onClick={() => {
                          onChange(a.id, a.name)
                          setOpen(false)
                          setQuery('')
                        }}
                        className={cn(
                          'flex w-full items-start gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-accent',
                          a.id === value && 'bg-accent',
                        )}
                      >
                        <span className="mt-0.5 w-4 shrink-0">
                          {a.id === value && <IconCheck size={14} className="text-primary" />}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-foreground">{a.name}</span>
                          {a.description && (
                            <span className="block truncate text-xs text-muted-foreground">
                              {a.description}
                            </span>
                          )}
                        </span>
                      </button>
                    </li>
                  ))
                )}
              </ul>
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={handleRefresh}
          disabled={data?.configured === false}
          title={t('vs.agent.refresh', locale)}
          aria-label={t('vs.agent.refresh', locale)}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:bg-accent disabled:opacity-40"
        >
          <IconRefresh size={16} className={cn(isRefetching && 'animate-spin')} />
        </button>
      </div>

      {status === 'loading' && (
        <p className="text-xs text-muted-foreground">{t('vs.agent.loading', locale)}</p>
      )}
      {status === 'not_configured' && (
        <p className="text-xs text-muted-foreground">
          {t('vs.agent.notConfigured', locale)}{' '}
          <Link href="/open-agent-settings" className="text-primary hover:underline">
            {t('vs.agent.notConfigured.link', locale)}
          </Link>
        </p>
      )}
      {status === 'forbidden' && (
        <p className="flex items-start gap-1 text-xs text-red-600">
          <IconAlertTriangle size={13} className="mt-0.5 shrink-0" />
          {t('vs.agent.forbidden', locale)}
        </p>
      )}
      {status === 'error' && (
        <p className="flex items-start gap-1 text-xs text-red-600">
          <IconAlertTriangle size={13} className="mt-0.5 shrink-0" />
          {t('vs.agent.loadFailed', locale)}
        </p>
      )}
      {status === 'empty' && (
        <p className="text-xs text-muted-foreground">{t('vs.agent.empty', locale)}</p>
      )}
      {status === 'unavailable' && (
        <p className="flex items-start gap-1 text-xs text-amber-600">
          <IconAlertTriangle size={13} className="mt-0.5 shrink-0" />
          {t('vs.agent.unavailable', locale)}
        </p>
      )}
    </div>
  )
}
