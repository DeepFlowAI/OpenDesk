'use client'

import { useParams } from 'next/navigation'
import { WorkspaceDashboardView } from '@/app/components/features/custom-dashboard/workspace-dashboard-view'

export default function WorkspaceDashboardPage() {
  const params = useParams<{ dashboardId: string }>()
  const id = Number.parseInt(params.dashboardId, 10)
  if (Number.isNaN(id)) return <div className="p-7 text-sm text-destructive">Invalid dashboard ID</div>
  return <WorkspaceDashboardView id={id} />
}
