'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { IconLoader2 } from '@tabler/icons-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  AgentTargetPicker,
  type AgentTargetPickerItem,
  type AgentTargetStatus,
} from '@/app/components/features/chat/agent-target-picker'
import {
  useTransferTargets,
  useTransferConversation,
} from '@/service/use-transfer'
import type { Conversation } from '@/models/conversation'
import type { TransferTarget } from '@/models/transfer'

type Props = {
  conversation: Conversation
  open: boolean
  onClose: () => void
  onTransferred: (toName: string) => void
}

function statusLabel(status: AgentTargetStatus, locale: Locale): string {
  switch (status) {
    case 'online':
      return t('ws.chat.transferStatusOnline', locale)
    case 'busy':
      return t('ws.chat.transferStatusBusy', locale)
    case 'offline':
      return t('ws.chat.transferStatusOffline', locale)
  }
}

function pickDisplayName(target: TransferTarget): string {
  return target.display_name || target.name || `#${target.id}`
}

function toPickerItem(target: TransferTarget, locale: Locale): AgentTargetPickerItem {
  const isOnline = target.online_status === 'online'
  return {
    id: target.id,
    displayName: pickDisplayName(target),
    avatar: target.avatar,
    jobNumber: target.job_number,
    onlineStatus: target.online_status,
    currentCount: target.current_count,
    maxConcurrent: target.max_concurrent,
    available: isOnline,
    disabledText: isOnline ? null : t('ws.chat.transferUnavailable', locale),
  }
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

  const items = useMemo(
    () => (data?.items ?? []).map((item) => toPickerItem(item, locale)),
    [data?.items, locale],
  )
  const selectedTarget = useMemo(
    () => (data?.items ?? []).find((item) => item.id === selectedId) ?? null,
    [data?.items, selectedId],
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

        <AgentTargetPicker
          keyword={keyword}
          onKeywordChange={setKeyword}
          searchPlaceholder={t('ws.chat.transferSearchPlaceholder', locale)}
          isLoading={isLoading}
          isFetching={isFetching}
          items={items}
          selectedId={selectedId}
          onSelect={(item) => {
            setSelectedId(item.id)
            setErrorMessage(null)
          }}
          emptyText={emptyText}
          statusLabel={(status) => statusLabel(status, locale)}
          listMinHeightClassName="min-h-[200px]"
          feedback={
            errorMessage ? (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {errorMessage}
              </div>
            ) : null
          }
        />

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
