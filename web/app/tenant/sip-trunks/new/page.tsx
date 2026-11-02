'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { readConsoleError } from '@/service/tenant-console-client'
import { useCreateSipTrunk } from '@/service/use-tenant-console'
import type { SipTrunkPayload } from '@/models/tenant-console'
import { DetailTopBar } from '@/app/tenant/_components/console-ui'
import { SIP_TRUNK_FORM_ID, SipTrunkForm } from '@/app/tenant/_components/sip-trunk-form'

export default function NewSipTrunkPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const createMutation = useCreateSipTrunk()
  const [dirty, setDirty] = useState(false)

  const goBack = () => {
    if (dirty && !window.confirm(t('tc.common.leaveConfirm', locale))) return
    router.push('/tenant/sip-trunks')
  }

  const handleSubmit = async (data: SipTrunkPayload) => {
    try {
      await createMutation.mutateAsync(data)
      toast.success(t('tc.common.saved', locale))
      router.push('/tenant/sip-trunks')
    } catch (err) {
      toast.error(await readConsoleError(err, t('tc.common.saveFailed', locale)))
    }
  }

  return (
    <div className="flex flex-col">
      <DetailTopBar
        title={t('tc.trunk.create', locale)}
        onBack={goBack}
        actions={
          <Button type="submit" form={SIP_TRUNK_FORM_ID} size="lg" disabled={createMutation.isPending}>
            {createMutation.isPending ? t('tc.common.saving', locale) : t('tc.common.save', locale)}
          </Button>
        }
      />
      <SipTrunkForm onSubmit={handleSubmit} onDirty={() => setDirty(true)} />
    </div>
  )
}
