'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { readConsoleError } from '@/service/tenant-console-client'
import { useCreatePhoneNumber } from '@/service/use-tenant-console'
import type { PhoneNumberCreatePayload } from '@/models/tenant-console'
import { DetailTopBar } from '@/app/tenant/_components/console-ui'
import { PHONE_NUMBER_FORM_ID, PhoneNumberForm } from '@/app/tenant/_components/phone-number-form'

export default function NewPhoneNumberPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const createMutation = useCreatePhoneNumber()
  const [dirty, setDirty] = useState(false)

  const goBack = () => {
    if (dirty && !window.confirm(t('tc.common.leaveConfirm', locale))) return
    router.push('/tenant/phone-numbers')
  }

  const handleSubmit = async (data: PhoneNumberCreatePayload) => {
    try {
      await createMutation.mutateAsync(data)
      toast.success(t('tc.common.saved', locale))
      router.push('/tenant/phone-numbers')
    } catch (err) {
      toast.error(await readConsoleError(err, t('tc.common.saveFailed', locale)))
    }
  }

  return (
    <div className="flex flex-col">
      <DetailTopBar
        title={t('tc.phone.create', locale)}
        onBack={goBack}
        actions={
          <Button type="submit" form={PHONE_NUMBER_FORM_ID} size="lg" disabled={createMutation.isPending}>
            {createMutation.isPending ? t('tc.common.saving', locale) : t('tc.common.save', locale)}
          </Button>
        }
      />
      <PhoneNumberForm onSubmit={handleSubmit} onDirty={() => setDirty(true)} />
    </div>
  )
}
