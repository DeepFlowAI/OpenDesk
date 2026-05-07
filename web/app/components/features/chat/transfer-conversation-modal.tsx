'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { IconLoader2, IconSearch } from '@tabler/icons-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  useTransferTargets,
  useTransferConversation,
} from '@/service/use-transfer'
import type { Conversation } from '@/models/conversation'
import type { TransferOnlineStatus, TransferTarget } from '@/models/transfer'

type Props = {
  conversation: Conversation
  open: boolean
  onClose: () => void
  onTransferred: (toName: string) => void
}

const STATUS_DOT_COLOR: Record<TransferOnlineStatus, string> = {
  online: '#22C55E',
  busy: '#F59E0B',
  offline: '#9CA3AF',
}

function statusLabel(status: TransferOnlineStatus, locale: Locale): string {
  switch (status) {
    case 'online':
      return t('ws.chat.transferStatusOnline', locale)
    case 'busy':
      return t('ws.chat.transferStatusBusy', locale)
    case 'offline':
      return t('ws.chat.transferStatusOffline', locale)
  }
}

function pickInitial(target: TransferTarget): string {
  const text = target.display_name || target.name || ''
  return text.trim().charAt(0).toUpperCase() || '?'
}

function pickDisplayName(target: TransferTarget): string {
  return target.display_name || target.name || `#${target.id}`
}

export function TransferConversationModal({
  conversation,
  open,
  onClose,
  onTransferred,
}: Props) {
  const { locale } = useLocaleStore()
  const [keyword, setKeyword] = useState('')
  const [debouncedKeyword, setDebouncedKeyword] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  // Debounce keyword updates by 300ms to keep request volume low while typing.
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => setDebouncedKeyword(keyword), 300)
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
    }
  }, [keyword])

  // Reset state every time the modal is opened so previous selections don't leak.
  useEffect(() => {
    if (open) {
      setKeyword('')
      setDebouncedKeyword('')
      setSelectedId(null)
      setErrorMessage(null)
    }
  }, [open])

  const { data, isLoading, isFetching } = useTransferTargets(
    debouncedKeyword,
    open,
    conversation.id,
  )
  const transferMutation = useTransferConversation()

  const items = data?.items ?? []
  const selectedTarget = useMemo(
    () => items.find((item) => item.id === selectedId) ?? null,
    [items, selectedId],
  )
  const canSubmit =
    !!selectedTarget &&
    selectedTarget.online_status === 'online' &&
    !transferMutation.isPending

  const handleSubmit = async () => {
    if (!selectedTarget) return
    setErrorMessage(null)
    try {
      await transferMutation.mutateAsync({
        conversationId: conversation.id,
        targetAgentId: selectedTarget.id,
      })
      onTransferred(pickDisplayName(selectedTarget))
      onClose()
    } catch (err: unknown) {
      // ky throws HTTPError; backend body is { code, message, status }
      let msg = locale === 'zh' ? '转接失败，请重试' : 'Transfer failed, please retry'
      if (err && typeof err === 'object' && 'response' in err) {
        const resp = (err as { response: Response }).response
        try {
          const body = await resp.clone().json()
          if (body?.message) msg = body.message
        } catch {
          // ignore JSON parse error
        }
      }
      setErrorMessage(msg)
    }
  }

  const showEmpty = !isLoading && items.length === 0
  const emptyText = debouncedKeyword
    ? t('ws.chat.transferNoMatch', locale)
    : t('ws.chat.transferEmpty', locale)

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !transferMutation.isPending) onClose()
      }}
    >
      <DialogContent className="gap-3 pb-3 sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t('ws.chat.transferTitle', locale)}</DialogTitle>
          <DialogDescription>{t('ws.chat.transferDesc', locale)}</DialogDescription>
        </DialogHeader>

        <div className="relative">
          <IconSearch
            size={16}
            stroke={1.5}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder={t('ws.chat.transferSearchPlaceholder', locale)}
            className="pl-8 pr-8"
            autoFocus
          />
          {isFetching && (
            <IconLoader2
              size={16}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 animate-spin text-muted-foreground"
            />
          )}
        </div>

        {errorMessage && (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {errorMessage}
          </div>
        )}

        <div className="-mx-1 max-h-[360px] min-h-[200px] overflow-y-auto px-1">
          {isLoading ? (
            <div className="space-y-2 py-2">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="h-12 animate-pulse rounded-md bg-muted/60"
                />
              ))}
            </div>
          ) : showEmpty ? (
            <div className="flex h-full min-h-[200px] items-center justify-center text-sm text-muted-foreground">
              {emptyText}
            </div>
          ) : (
            <ul className="divide-y divide-border/60">
              {items.map((item) => {
                const isOnline = item.online_status === 'online'
                const isSelected = selectedId === item.id
                return (
                  <li
                    key={item.id}
                    className={cn(
                      'flex items-center gap-3 rounded-md px-2 py-2 transition-colors',
                      isOnline
                        ? 'cursor-pointer hover:bg-muted'
                        : 'cursor-not-allowed opacity-60',
                      isSelected && 'bg-primary/10 hover:bg-primary/10',
                    )}
                    aria-disabled={!isOnline}
                    onClick={() => {
                      if (!isOnline) return
                      setSelectedId(item.id)
                      setErrorMessage(null)
                    }}
                  >
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-medium text-foreground">
                      {item.avatar ? (
                        // Avatars come from a trusted internal upload, no external URL handling needed.
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={item.avatar}
                          alt={pickDisplayName(item)}
                          className="h-9 w-9 rounded-full object-cover"
                        />
                      ) : (
                        pickInitial(item)
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 truncate text-sm font-medium">
                        <span className="truncate">{pickDisplayName(item)}</span>
                        {item.job_number && (
                          <span className="shrink-0 text-xs text-muted-foreground">
                            #{item.job_number}
                          </span>
                        )}
                      </div>
                      {!isOnline && (
                        <div className="mt-0.5 text-xs text-muted-foreground">
                          {t('ws.chat.transferUnavailable', locale)}
                        </div>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
                      <span
                        className="inline-block h-2 w-2 rounded-full"
                        style={{ backgroundColor: STATUS_DOT_COLOR[item.online_status] }}
                      />
                      <span>{statusLabel(item.online_status, locale)}</span>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <DialogFooter className="pt-3 pb-0">
          <Button
            variant="outline"
            onClick={onClose}
            disabled={transferMutation.isPending}
          >
            {t('ws.common.cancel', locale)}
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {transferMutation.isPending && (
              <IconLoader2 size={14} className="mr-1 animate-spin" />
            )}
            {t('ws.chat.transferSubmit', locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
