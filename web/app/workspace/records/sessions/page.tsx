'use client'

import { useState } from 'react'
import { SessionTable } from '@/app/components/features/session-records/session-table'
import { SessionDetailDrawer } from '@/app/components/features/session-records/session-detail-drawer'
import type { SessionRecord } from '@/models/session-record'

export default function SessionRecordsPage() {
  const [selectedRecord, setSelectedRecord] = useState<SessionRecord | null>(null)

  return (
    <div className="flex h-full flex-col">
      <SessionTable onSelectRecord={setSelectedRecord} />

      {selectedRecord && (
        <SessionDetailDrawer
          recordId={selectedRecord.id}
          onClose={() => setSelectedRecord(null)}
        />
      )}
    </div>
  )
}
