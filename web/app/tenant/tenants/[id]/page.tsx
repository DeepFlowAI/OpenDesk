'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { readConsoleError } from '@/service/tenant-console-client'
import { useConsoleTenant, useUpdateConsoleTenant } from '@/service/use-tenant-console'
import type { ConsoleTenantUpdatePayload } from '@/models/tenant-console'
import { DetailTopBar, EmptyState, LoadingState } from '@/app/tenant/_components/console-ui'
import { TENANT_FORM_ID, TenantForm } from '@/app/tenant/_components/tenant-form'

export default function EditTenantPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const tenantId = decodeURIComponent(params.id ?? '')
  const { locale } = useLocaleStore()
  const { data: tenant, isLoading } = useConsoleTenant(tenantId)
  const updateMutation = useUpdateConsoleTenant()
  const [dirty, setDirty] = useState(false)

  const goBack = () => {
    if (dirty && !window.confirm(t('tc.common.leaveConfirm', locale))) return
    router.push('/tenant')
  }

  const handleSubmit = async (data: ConsoleTenantUpdatePayload) => {
    try {
      await updateMutation.mutateAsync({ id: tenantId, data })
      toast.success(t('tc.common.saved', locale))
      router.push('/tenant')
    } catch (err) {
      toast.error(await readConsoleError(err, t('tc.common.saveFailed', locale)))
    }
  }

  if (isLoading) return <LoadingState />
  if (!tenant) {
    return (
      <div className="p-8">
        <EmptyState title={t('tc.common.notFound', locale)} />
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      <DetailTopBar
        title={t('tc.tenant.editTitle', locale, { name: tenant.name })}
        onBack={goBack}
        actions={
          <Button
            type="submit"
            form={TENANT_FORM_ID}
            size="lg"
            disabled={!dirty || updateMutation.isPending}
          >
            {updateMutation.isPending ? t('tc.common.saving', locale) : t('tc.common.save', locale)}
          </Button>
        }
      />
      <TenantForm key={tenant.id} tenant={tenant} onSubmit={handleSubmit} onDirty={() => setDirty(true)} />
    </div>
  )
}
