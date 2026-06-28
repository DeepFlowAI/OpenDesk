'use client'

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
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useRespondCollaborationInvitation } from '@/service/use-conversation-collaboration'
import type { Conversation } from '@/models/conversation'
import type { CollaborationInvitation } from '@/models/conversation-collaboration'

type Props = {
  invitation: CollaborationInvitation | null
  onAccepted: (conversation: Conversation) => void
  onDeclined: () => void
}

function agentName(value: CollaborationInvitation['inviter']): string {
  return value?.display_name || value?.name || ''
}

export function CollaborationInvitationDialog({ invitation, onAccepted, onDeclined }: Props) {
  const { locale } = useLocaleStore()
  const respond = useRespondCollaborationInvitation()
  const inviterName = agentName(invitation?.inviter ?? null) || t('ws.chat.agentFallback', locale)
  const ownerName = agentName(invitation?.owner ?? null) || t('ws.chat.agentFallback', locale)

  const handleRespond = async (action: 'accept' | 'decline') => {
    if (!invitation || respond.isPending) return
    try {
      const result = await respond.mutateAsync({ invitationId: invitation.id, action })
      if (action === 'accept' && result.conversation) {
        onAccepted(result.conversation)
        return
      }
      onDeclined()
    } catch {
      window.alert(t('ws.chat.collabRespondFailed', locale))
    }
  }

  return (
    <Dialog open={Boolean(invitation)} onOpenChange={() => {}}>
      <DialogContent className="sm:max-w-[440px]" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t('ws.chat.collabInvitationTitle', locale, { name: inviterName })}</DialogTitle>
          <DialogDescription>
            {t('ws.chat.collabInvitationDesc', locale, { name: ownerName })}
          </DialogDescription>
        </DialogHeader>
        {invitation && (
          <div className="space-y-2 rounded-lg border border-border bg-muted/30 p-3 text-sm">
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">{t('ws.chat.collabVisitor', locale)}</span>
              <span className="truncate font-medium text-foreground">{invitation.visitor_name || `#${invitation.conversation_id}`}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-muted-foreground">{t('ws.chat.collabOwner', locale)}</span>
              <span className="truncate text-foreground">{ownerName}</span>
            </div>
            {invitation.channel_name && (
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">{t('ws.chat.collabChannel', locale)}</span>
                <span className="truncate text-foreground">{invitation.channel_name}</span>
              </div>
            )}
            {invitation.last_message_preview && (
              <p className="line-clamp-2 border-t border-border pt-2 text-xs text-muted-foreground">
                {invitation.last_message_preview}
              </p>
            )}
          </div>
        )}
        <DialogFooter className="pb-0">
          <Button variant="outline" disabled={respond.isPending} onClick={() => void handleRespond('decline')}>
            {t('ws.chat.collabDecline', locale)}
          </Button>
          <Button disabled={respond.isPending} onClick={() => void handleRespond('accept')}>
            {respond.isPending ? <IconLoader2 size={16} className="animate-spin" /> : <IconUserPlus size={16} />}
            {t('ws.chat.collabJoin', locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
