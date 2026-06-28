'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { IconLoader2, IconUserPlus } from '@tabler/icons-react'
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
  useCollaborationTargets,
  useCreateCollaborationInvitation,
} from '@/service/use-conversation-collaboration'
import type { Conversation } from '@/models/conversation'
import type { CollaborationTarget } from '@/models/conversation-collaboration'

type Props = {
  conversation: Conversation
  open: boolean
  onClose: () => void
  onInvited: (name: string) => void
}

function statusLabel(status: AgentTargetStatus, locale: Locale): string {
  if (status === 'online') return t('ws.chat.transferStatusOnline', locale)
  if (status === 'busy') return t('ws.chat.transferStatusBusy', locale)
  return t('ws.chat.transferStatusOffline', locale)
}

function displayName(target: CollaborationTarget): string {
  return target.display_name || target.name || `#${target.id}`
}

function disabledLabel(reason: CollaborationTarget['disabled_reason'], locale: Locale): string | null {
  if (reason === 'already_joined') return t('ws.chat.collabAlreadyJoined', locale)
  if (reason === 'pending') return t('ws.chat.collabPending', locale)
  if (reason === 'offline') return t('ws.chat.collabOffline', locale)
  return null
}

function toPickerItem(target: CollaborationTarget, locale: Locale): AgentTargetPickerItem {
  return {
    id: target.id,
    displayName: displayName(target),
    avatar: target.avatar,
    jobNumber: target.job_number,
    onlineStatus: target.online_status,
    currentCount: target.current_count,
    maxConcurrent: target.max_concurrent,
    available: target.available,
    disabledText: disabledLabel(target.disabled_reason, locale),
  }
}

export function InviteCollaboratorModal({ conversation, open, onClose, onInvited }: Props) {
  const { locale } = useLocaleStore()
  const [keyword, setKeyword] = useState('')
  const [debouncedKeyword, setDebouncedKeyword] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => setDebouncedKeyword(keyword), 300)
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
    }
  }, [keyword])

  useEffect(() => {
    if (!open) return
    setKeyword('')
    setDebouncedKeyword('')
    setSelectedId(null)
    setErrorMessage(null)
  }, [open])

  const targetsQuery = useCollaborationTargets(conversation.id, debouncedKeyword, open)
  const createInvitation = useCreateCollaborationInvitation(conversation.id)
  const items = useMemo(
    () => (targetsQuery.data?.items ?? []).map((item) => toPickerItem(item, locale)),
    [targetsQuery.data?.items, locale],
  )
  const selectedTarget = useMemo(
    () => (targetsQuery.data?.items ?? []).find((item) => item.id === selectedId) ?? null,
    [targetsQuery.data?.items, selectedId],
  )

  const handleSubmit = async () => {
    if (!selectedTarget || !selectedTarget.available) return
    setErrorMessage(null)
    try {
      await createInvitation.mutateAsync(selectedTarget.id)
      onInvited(displayName(selectedTarget))
      setSelectedId(null)
      void targetsQuery.refetch()
    } catch (err: unknown) {
      let msg = t('ws.chat.collabInviteFailed', locale)
      if (err && typeof err === 'object' && 'response' in err) {
        try {
          const body = await (err as { response: Response }).response.clone().json()
          if (body?.message) msg = body.message
        } catch {
          // ignore parse error
        }
      }
      setErrorMessage(msg)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && !createInvitation.isPending && onClose()}>
      <DialogContent className="gap-3 pb-3 sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>{t('ws.chat.collabInviteTitle', locale)}</DialogTitle>
          <DialogDescription>{t('ws.chat.collabInviteDesc', locale)}</DialogDescription>
        </DialogHeader>
        <AgentTargetPicker
          keyword={keyword}
          onKeywordChange={setKeyword}
          searchPlaceholder={t('ws.chat.collabSearchPlaceholder', locale)}
          isLoading={targetsQuery.isLoading}
          isFetching={targetsQuery.isFetching}
          items={items}
          selectedId={selectedId}
          onSelect={(item) => {
            setSelectedId(item.id)
            setErrorMessage(null)
          }}
          emptyText={debouncedKeyword ? t('ws.chat.collabNoMatch', locale) : t('ws.chat.collabNoTargets', locale)}
          statusLabel={(status) => statusLabel(status, locale)}
          feedback={
            errorMessage ? (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {errorMessage}
              </div>
            ) : null
          }
        />
        <DialogFooter className="pb-0">
          <Button variant="outline" onClick={onClose} disabled={createInvitation.isPending}>{t('ws.common.cancel', locale)}</Button>
          <Button onClick={handleSubmit} disabled={!selectedTarget?.available || createInvitation.isPending}>
            {createInvitation.isPending ? <IconLoader2 size={16} className="animate-spin" /> : <IconUserPlus size={16} />}
            {t('ws.chat.collabSendInvite', locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
