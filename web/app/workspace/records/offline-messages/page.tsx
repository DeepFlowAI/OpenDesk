'use client'

import { OfflineMessagePanel } from '@/app/components/features/offline-messages/offline-message-panel'

export default function OfflineMessagesRecordPage() {
  return <OfflineMessagePanel status="all" readOnly />
}
