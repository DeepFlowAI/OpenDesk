'use client'

import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { DashboardForm, type DashboardFormValue } from '@/app/components/features/custom-dashboard/dashboard-form'
import { useCreateCustomDashboard } from '@/service/use-custom-dashboards'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

export default function NewCustomDashboardPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const createDashboard = useCreateCustomDashboard()

  async function create(value: DashboardFormValue) {
    try {
      const dashboard = await createDashboard.mutateAsync({
        ...value,
        description: value.description.trim() || null,
        filters: [],
        components: [],
      })
      router.push(`/custom-dashboards/${dashboard.id}`)
    } catch {
      toast.error(t('cd.actionFailed', locale))
    }
  }

  return (
    <DashboardForm
      title={t('cd.newTitle', locale)}
      submitting={createDashboard.isPending}
      onBack={() => router.push('/custom-dashboards')}
      onSubmit={create}
    />
  )
}
