'use client'

import { useParams } from 'next/navigation'
import { ConversationAnnouncementForm } from '@/app/components/features/conversation-announcement-form'

export default function EditConversationAnnouncementPage() {
  const params = useParams()
  const id = Number.parseInt(params.id as string, 10)
  if (Number.isNaN(id)) {
    return <p className="text-sm text-destructive">Invalid id</p>
  }
  return <ConversationAnnouncementForm ruleId={id} />
}
