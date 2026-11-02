'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { readConsoleError } from '@/service/tenant-console-client'
import { usePhoneNumber, useUpdatePhoneNumber } from '@/service/use-tenant-console'
import type { PhoneNumberCreatePayload, PhoneNumberUpdatePayload } from '@/models/tenant-console'
import { DetailTopBar, EmptyState, LoadingState } from '@/app/tenant/_components/console-ui'
import { PHONE_NUMBER_FORM_ID, PhoneNumberForm } from '@/app/tenant/_components/phone-number-form'

export default function EditPhoneNumberPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const phoneId = decodeURIComponent(params.id ?? '')
  const { locale } = useLocaleStore()
  const { data: phone, isLoading } = usePhoneNumber(phoneId)
  const updateMutation = useUpdatePhoneNumber()
  const [dirty, setDirty] = useState(false)

  const goBack = () => {
    if (dirty && !window.confirm(t('tc.common.leaveConfirm', locale))) return
    router.push('/tenant/phone-numbers')
  }

  const handleSubmit = async (data: PhoneNumberCreatePayload) => {
    const update: PhoneNumberUpdatePayload = { ...data }
    delete (update as Partial<PhoneNumberCreatePayload>).phone_number
    try {
      await updateMutation.mutateAsync({ id: phoneId, data: update })
      toast.success(t('tc.common.saved', locale))
      router.push('/tenant/phone-numbers')
    } catch (err) {
      toast.error(await readConsoleError(err, t('tc.common.saveFailed', locale)))
    }
  }

  if (isLoading) return <LoadingState />
  if (!phone) {
    return (
      <div className="p-8">
        <EmptyState title={t('tc.common.notFound', locale)} />
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      <DetailTopBar
        title={t('tc.phone.editTitle', locale, { number: phone.phone_number })}
        onBack={goBack}
        actions={
          <Button type="submit" form={PHONE_NUMBER_FORM_ID} size="lg" disabled={!dirty || updateMutation.isPending}>
            {updateMutation.isPending ? t('tc.common.saving', locale) : t('tc.common.save', locale)}
          </Button>
        }
      />
      <PhoneNumberForm key={phone.id} phone={phone} onSubmit={handleSubmit} onDirty={() => setDirty(true)} />
    </div>
  )
}
