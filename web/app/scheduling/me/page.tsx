'use client'

import { Suspense } from 'react'
import { MyScheduleView } from '@/app/components/features/scheduling/my-schedule-view'

export default function MySchedulePage() {
  return (
    <Suspense fallback={null}>
      <MyScheduleView />
    </Suspense>
  )
}
