'use client'

import { useParams } from 'next/navigation'
import { DashboardEditor } from '@/app/components/features/custom-dashboard/dashboard-editor'

export default function EditCustomDashboardPage() {
  const params = useParams<{ dashboardId: string }>()
  const id = Number.parseInt(params.dashboardId, 10)
  if (Number.isNaN(id)) return <div className="p-6 text-sm text-destructive">Invalid dashboard ID</div>
  return <DashboardEditor id={id} />
}
