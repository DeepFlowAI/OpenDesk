'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'
import { useCreateEmployeeGroup } from '@/service/use-employee-groups'
import EmployeeGroupForm from '@/app/(main)/employee-groups/form'
import type { CreateEmployeeGroupPayload } from '@/models/employee-group'

export default function NewEmployeeGroupPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const createMutation = useCreateEmployeeGroup()
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const canManage = hasPermission(user, 'org.group.manage')

  const handleSave = async (payload: CreateEmployeeGroupPayload) => {
    if (!canManage) return
    try {
      const created = await createMutation.mutateAsync(payload)
      setToast({ type: 'success', text: t('eg.saveSuccess', locale) })
      setTimeout(() => {
        router.replace(`/employee-groups/${created.id}`)
      }, 800)
    } catch {
      setToast({ type: 'error', text: t('eg.saveFailed', locale) })
      setTimeout(() => setToast(null), 3000)
    }
  }

  return (
    <div className="-m-8 flex flex-col">
      {/* Sticky top bar — align with session-routing detail (cancel main p-8, stick under header) */}
      <div className="sticky -top-8 z-20 flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <button
          onClick={() => router.push('/employee-groups')}
          className="flex items-center gap-2 transition-colors hover:opacity-80"
        >
          <IconArrowLeft size={20} className="text-muted-foreground" />
          <span className="text-base font-semibold text-foreground">
            {t('eg.new', locale)}
          </span>
        </button>
        {canManage && (
          <button
            onClick={() => {
              const form = document.getElementById('eg-form') as HTMLFormElement | null
              form?.requestSubmit()
            }}
            disabled={createMutation.isPending}
            className="flex h-9 items-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
          >
            {createMutation.isPending ? t('eg.saving', locale) : t('eg.save', locale)}
          </button>
        )}
      </div>

      {toast && (
        <div
          className={`mx-8 mt-4 shrink-0 rounded-lg px-4 py-3 text-sm ${
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          }`}
        >
          {toast.text}
        </div>
      )}

      {/* Content */}
      <div className="p-8">
        <EmployeeGroupForm onSubmit={handleSave} saving={createMutation.isPending} />
      </div>
    </div>
  )
}
