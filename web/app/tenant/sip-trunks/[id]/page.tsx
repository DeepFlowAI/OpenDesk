'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { readConsoleError } from '@/service/tenant-console-client'
import { useSipTrunk, useUpdateSipTrunk } from '@/service/use-tenant-console'
import type { SipTrunkPayload } from '@/models/tenant-console'
import { DetailTopBar, EmptyState, LoadingState } from '@/app/tenant/_components/console-ui'
import { SIP_TRUNK_FORM_ID, SipTrunkForm } from '@/app/tenant/_components/sip-trunk-form'

export default function EditSipTrunkPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const trunkId = decodeURIComponent(params.id ?? '')
  const { locale } = useLocaleStore()
  const { data: trunk, isLoading } = useSipTrunk(trunkId)
  const updateMutation = useUpdateSipTrunk()
  const [dirty, setDirty] = useState(false)

  const goBack = () => {
    if (dirty && !window.confirm(t('tc.common.leaveConfirm', locale))) return
    router.push('/tenant/sip-trunks')
  }

  const handleSubmit = async (data: SipTrunkPayload) => {
    try {
      await updateMutation.mutateAsync({ id: trunkId, data })
      toast.success(t('tc.common.saved', locale))
      router.push('/tenant/sip-trunks')
    } catch (err) {
      toast.error(await readConsoleError(err, t('tc.common.saveFailed', locale)))
    }
  }

  if (isLoading) return <LoadingState />
  if (!trunk) {
    return (
      <div className="p-8">
        <EmptyState title={t('tc.common.notFound', locale)} />
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      <DetailTopBar
        title={t('tc.trunk.editTitle', locale, { name: trunk.trunk_name })}
        onBack={goBack}
        actions={
          <Button type="submit" form={SIP_TRUNK_FORM_ID} size="lg" disabled={!dirty || updateMutation.isPending}>
            {updateMutation.isPending ? t('tc.common.saving', locale) : t('tc.common.save', locale)}
          </Button>
        }
      />
      <SipTrunkForm key={trunk.id} trunk={trunk} onSubmit={handleSubmit} onDirty={() => setDirty(true)} />
    </div>
  )
}
