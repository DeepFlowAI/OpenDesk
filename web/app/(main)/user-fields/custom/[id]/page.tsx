'use client'

import { useState, useCallback } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useFieldDefinition, useUpdateFieldDefinition } from '@/service/use-field-definitions'
import UserFieldForm from '@/app/(main)/user-fields/form'
import type { CreateFdFieldDefinitionPayload, UpdateFdFieldDefinitionPayload } from '@/models/field-definition'

export default function EditUserFieldPage() {
  const router = useRouter()
  const params = useParams()
  const fieldId = Number(params.id)
  const { locale } = useLocaleStore()
  const { data: fieldDef, isLoading } = useFieldDefinition(fieldId)
  const updateMutation = useUpdateFieldDefinition()
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const handleSubmit = useCallback(
    async (data: CreateFdFieldDefinitionPayload | UpdateFdFieldDefinitionPayload) => {
      try {
        await updateMutation.mutateAsync({ id: fieldId, data: data as UpdateFdFieldDefinitionPayload })
        setToast({ type: 'success', text: t('uf.saveSuccess', locale) })
        setTimeout(() => setToast(null), 3000)
      } catch {
        setToast({ type: 'error', text: t('uf.saveFailed', locale) })
        setTimeout(() => setToast(null), 3000)
      }
    },
    [updateMutation, fieldId, locale],
  )

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">{t('uf.loading', locale)}</p>
      </div>
    )
  }

  if (!fieldDef) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">Field not found</p>
      </div>
    )
  }

  const title = t('uf.edit.title', locale, { name: fieldDef.name })

  return (
    <div className="-m-8 flex flex-col">
      {/* Sticky top bar — align with session-routing detail (cancel main p-8, stick under header) */}
      <div className="sticky -top-8 z-20 flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <button
          type="button"
          onClick={() => router.push('/user-fields')}
          className="flex min-w-0 items-center gap-2 text-left text-foreground transition-colors hover:opacity-80"
        >
          <IconArrowLeft size={20} className="shrink-0 text-muted-foreground" />
          <span className="truncate text-base font-semibold">{title}</span>
        </button>
        <button
          type="submit"
          form="user-field-form"
          disabled={updateMutation.isPending}
          className="shrink-0 flex h-9 items-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
        >
          {updateMutation.isPending ? t('uf.saving', locale) : t('uf.save', locale)}
        </button>
      </div>

      {/* Toast */}
      {toast && (
        <div
          className={`mx-8 mt-4 rounded-lg px-4 py-3 text-sm ${
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          }`}
        >
          {toast.text}
        </div>
      )}

      {/* Form content */}
      <div className="p-8">
        <UserFieldForm
          initialData={fieldDef}
          isEdit
          onSubmit={handleSubmit}
        />
      </div>
    </div>
  )
}
