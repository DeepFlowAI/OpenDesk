'use client'

import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Conversation } from '@/models/conversation'
import type { Socket } from 'socket.io-client'

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

type Props = {
  conversation: Conversation
  onClose: () => void
  socket: Socket | null
}

export function EndConversationModal({ conversation, onClose, socket }: Props) {
  const { locale } = useLocaleStore()
  const visitorName = conversation.visitor?.name || `#${conversation.id}`

  const handleEnd = () => {
    if (socket) {
      socket.emit('end_conversation', { conversation_id: conversation.id })
    }
    onClose()
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="gap-3 pb-3 sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>
            {t('ws.chat.endConfirmTitle', locale)}
          </DialogTitle>
          <DialogDescription>
            {t('ws.chat.endConfirmMsg', locale, { name: visitorName })}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="pt-3 pb-0">
          <Button variant="outline" onClick={onClose}>
            {t('ws.common.cancel', locale)}
          </Button>
          <Button variant="destructive" onClick={handleEnd}>
            {t('ws.chat.endConfirmBtn', locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
