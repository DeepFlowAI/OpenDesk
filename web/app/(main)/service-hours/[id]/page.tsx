'use client'

import { useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useServiceHoursDetail, useUpdateServiceHours } from '@/service/use-service-hours'
import ServiceHoursForm from '@/app/(main)/service-hours/form'
import type { UpdateServiceHoursPayload } from '@/models/service-hours'

export default function EditServiceHoursPage() {
  const router = useRouter()
  const params = useParams()
  const id = Number(params.id)
  const { locale } = useLocaleStore()
  const { data, isLoading } = useServiceHoursDetail(id)
  const updateMutation = useUpdateServiceHours()
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const handleSave = async (payload: UpdateServiceHoursPayload) => {
    try {
      await updateMutation.mutateAsync({ id, data: payload })
      setToast({ type: 'success', text: t('sh.saveSuccess', locale) })
      setTimeout(() => setToast(null), 3000)
    } catch {
      setToast({ type: 'error', text: t('sh.saveFailed', locale) })
      setTimeout(() => setToast(null), 3000)
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">{t('sh.loading', locale)}</p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">Not found</p>
      </div>
    )
  }

  return (
    <div className="-m-8 flex flex-col">
      {/* Sticky top bar — align with session-routing detail (cancel main p-8, stick under header) */}
      <div className="sticky -top-8 z-20 flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <button
          onClick={() => router.push('/service-hours')}
          className="flex items-center gap-2 transition-colors hover:opacity-80"
        >
          <IconArrowLeft size={20} className="text-muted-foreground" />
          <span className="text-base font-semibold text-foreground">
            {t('sh.edit', locale, { name: data.name })}
          </span>
        </button>
        <button
          onClick={() => {
            const form = document.getElementById('sh-form') as HTMLFormElement | null
            form?.requestSubmit()
          }}
          disabled={updateMutation.isPending}
          className="flex h-9 items-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
        >
          {updateMutation.isPending ? t('sh.saving', locale) : t('sh.save', locale)}
        </button>
      </div>

      {toast && (
        <div
          className={`mx-8 mt-4 shrink-0 rounded-lg px-4 py-3 text-sm ${
            toast.type === 'success'
              ? 'bg-green-50 text-green-700'
              : 'bg-red-50 text-red-700'
          }`}
        >
          {toast.text}
        </div>
      )}

      {/* Content */}
      <div className="p-8">
        <ServiceHoursForm initialData={data} onSubmit={handleSave} />
      </div>
    </div>
  )
}
