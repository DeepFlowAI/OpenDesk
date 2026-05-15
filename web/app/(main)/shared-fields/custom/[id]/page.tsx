'use client'

import { useCallback, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  useFieldDefinition,
  useUpdateFieldDefinition,
} from '@/service/use-field-definitions'
import SharedFieldForm from '@/app/(main)/shared-fields/form'
import type { UpdateFdFieldDefinitionPayload } from '@/models/field-definition'

export default function EditSharedFieldPage() {
  const router = useRouter()
  const params = useParams()
  const id = Number(params.id)
  const { locale } = useLocaleStore()
  const { data, isLoading } = useFieldDefinition(id)
  const updateMutation = useUpdateFieldDefinition()
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const handleSubmit = useCallback(
    async (payload: unknown) => {
      try {
        await updateMutation.mutateAsync({ id, data: payload as UpdateFdFieldDefinitionPayload })
        setToast({ type: 'success', text: t('sf.saveSuccess', locale) })
        setTimeout(() => setToast(null), 3000)
      } catch {
        setToast({ type: 'error', text: t('sf.saveFailed', locale) })
        setTimeout(() => setToast(null), 3000)
      }
    },
    [id, updateMutation, locale],
  )

  const title = data ? t('sf.edit.title', locale, { name: data.name }) : ''

  return (
    <div className="-m-8 flex flex-col">
      {/* Sticky top bar — align with session-routing detail (cancel main p-8, stick under header) */}
      <div className="sticky -top-8 z-20 flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <button
          type="button"
          onClick={() => router.push('/shared-fields')}
          className="flex min-w-0 items-center gap-2 text-left transition-colors hover:opacity-80"
        >
          <IconArrowLeft size={20} className="shrink-0 text-muted-foreground" />
          <span className="truncate text-base font-semibold text-foreground">{title}</span>
        </button>
        <button
          type="submit"
          form="shared-field-form"
          disabled={updateMutation.isPending || isLoading}
          className="shrink-0 flex h-9 items-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
        >
          {updateMutation.isPending ? t('sf.saving', locale) : t('sf.save', locale)}
        </button>
      </div>

      {toast && (
        <div
          className={`mx-8 mt-4 rounded-lg px-4 py-3 text-sm ${
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          }`}
        >
          {toast.text}
        </div>
      )}

      <div className="p-8">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t('sf.loading', locale)}</p>
        ) : data ? (
          <SharedFieldForm initialData={data} isEdit onSubmit={handleSubmit} />
        ) : null}
      </div>
    </div>
  )
}
