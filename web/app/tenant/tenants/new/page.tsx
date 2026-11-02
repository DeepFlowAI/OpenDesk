'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { readConsoleError } from '@/service/tenant-console-client'
import { useCreateConsoleTenant } from '@/service/use-tenant-console'
import type { ConsoleTenantCreatePayload } from '@/models/tenant-console'
import { DetailTopBar } from '@/app/tenant/_components/console-ui'
import { TENANT_FORM_ID, TenantForm } from '@/app/tenant/_components/tenant-form'

export default function NewTenantPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const createMutation = useCreateConsoleTenant()
  const [dirty, setDirty] = useState(false)

  const goBack = () => {
    if (dirty && !window.confirm(t('tc.common.leaveConfirm', locale))) return
    router.push('/tenant')
  }

  const handleSubmit = async (data: ConsoleTenantCreatePayload) => {
    try {
      await createMutation.mutateAsync(data)
      toast.success(t('tc.tenant.createdToast', locale))
      router.push('/tenant')
    } catch (err) {
      toast.error(await readConsoleError(err, t('tc.common.saveFailed', locale)))
    }
  }

  return (
    <div className="flex flex-col">
      <DetailTopBar
        title={t('tc.tenant.create', locale)}
        onBack={goBack}
        actions={
          <Button type="submit" form={TENANT_FORM_ID} size="lg" disabled={createMutation.isPending}>
            {createMutation.isPending ? t('tc.common.saving', locale) : t('tc.common.save', locale)}
          </Button>
        }
      />
      <TenantForm onSubmit={handleSubmit} onDirty={() => setDirty(true)} />
    </div>
  )
}
