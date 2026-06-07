'use client'

import { useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'
import { useCreateEmployee } from '@/service/use-employees'
import EmployeeForm from '@/app/(main)/employees/form'
import type { CreateEmployeePayload } from '@/models/employee'

export default function NewEmployeePage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const createMutation = useCreateEmployee()
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const canCreate = hasPermission(user, 'org.employee.create')

  const handleSubmit = useCallback(
    async (data: CreateEmployeePayload) => {
      if (!canCreate) return
      try {
        const created = await createMutation.mutateAsync(data as CreateEmployeePayload)
        setToast({ type: 'success', text: t('emp.saveSuccess', locale) })
        setTimeout(() => {
          router.push(`/employees/${created.id}`)
        }, 800)
      } catch {
        setToast({ type: 'error', text: t('emp.saveFailed', locale) })
        setTimeout(() => setToast(null), 3000)
      }
    },
    [canCreate, createMutation, locale, router]
  )

  return (
    <div className="-m-8 flex flex-col">
      {/* Sticky top bar — align with session-routing detail (cancel main p-8, stick under header) */}
      <div className="sticky -top-8 z-20 flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <button
          type="button"
          onClick={() => router.push('/employees')}
          className="flex items-center gap-2 text-foreground transition-colors hover:text-foreground/80"
        >
          <IconArrowLeft size={20} className="text-muted-foreground" />
          <span className="text-base font-semibold">{t('emp.new.title', locale)}</span>
        </button>
        {canCreate && (
          <button
            type="submit"
            form="employee-form"
            disabled={createMutation.isPending}
            className="flex h-9 items-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
          >
            {createMutation.isPending ? t('emp.saving', locale) : t('emp.save', locale)}
          </button>
        )}
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
        <EmployeeForm onSubmit={(data) => handleSubmit(data as CreateEmployeePayload)} />
      </div>
    </div>
  )
}
