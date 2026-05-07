'use client'

import { useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useCreateFieldDefinition } from '@/service/use-field-definitions'
import OrgFieldForm from '@/app/(main)/organization-fields/form'
import type { CreateFdFieldDefinitionPayload, UpdateFdFieldDefinitionPayload } from '@/models/field-definition'

export default function NewOrgFieldPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const createMutation = useCreateFieldDefinition()
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const handleSubmit = useCallback(
    async (data: CreateFdFieldDefinitionPayload | UpdateFdFieldDefinitionPayload) => {
      try {
        const created = await createMutation.mutateAsync(data as CreateFdFieldDefinitionPayload)
        setToast({ type: 'success', text: t('of.saveSuccess', locale) })
        setTimeout(() => {
          router.push(`/organization-fields/custom/${created.id}`)
        }, 800)
      } catch {
        setToast({ type: 'error', text: t('of.saveFailed', locale) })
        setTimeout(() => setToast(null), 3000)
      }
    },
    [createMutation, locale, router],
  )

  return (
    <div className="-m-8 flex flex-col">
      {/* Sticky top bar — align with session-routing detail (cancel main p-8, stick under header) */}
      <div className="sticky -top-8 z-20 flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <button
          type="button"
          onClick={() => router.push('/organization-fields')}
          className="flex items-center gap-2 text-left text-foreground transition-colors hover:opacity-80"
        >
          <IconArrowLeft size={20} className="text-muted-foreground" />
          <span className="text-base font-semibold">{t('of.new.title', locale)}</span>
        </button>
        <button
          type="submit"
          form="org-field-form"
          disabled={createMutation.isPending}
          className="flex h-9 items-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
        >
          {createMutation.isPending ? t('of.saving', locale) : t('of.save', locale)}
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
        <OrgFieldForm onSubmit={handleSubmit} />
      </div>
    </div>
  )
}
