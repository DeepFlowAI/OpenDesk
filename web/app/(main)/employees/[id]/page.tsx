'use client'

import { useState, useCallback } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'
import { useEmployee, useUpdateEmployee } from '@/service/use-employees'
import { useQueuePolicies, useUpsertQueuePolicy } from '@/service/use-queue-policies'
import EmployeeForm from '@/app/(main)/employees/form'
import type { UpdateEmployeePayload } from '@/models/employee'
import type { QueuePolicyUpsertPayload } from '@/models/queue-policy'

export default function EditEmployeePage() {
  const router = useRouter()
  const params = useParams()
  const employeeId = Number(params.id)
  const { locale } = useLocaleStore()
  const user = useAuthStore((s) => s.user)
  const updateUser = useAuthStore((s) => s.updateUser)
  const canEdit = hasPermission(user, 'org.employee.edit')
  const { data: employee, isLoading } = useEmployee(employeeId)
  const { data: defaultQueuePolicies, isLoading: isDefaultQueuePoliciesLoading } = useQueuePolicies({
    scope_type: 'global',
  })
  const { data: employeeQueuePolicies, isLoading: isEmployeeQueuePoliciesLoading } = useQueuePolicies(
    { scope_type: 'employee', scope_id: employeeId },
    { enabled: !!employeeId }
  )
  const updateMutation = useUpdateEmployee()
  const upsertQueuePolicyMutation = useUpsertQueuePolicy()
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const handleSubmit = useCallback(
    async (data: UpdateEmployeePayload, queuePolicyPayloads: QueuePolicyUpsertPayload[] = []) => {
      if (!canEdit) return
      try {
        const updated = await updateMutation.mutateAsync({
          id: employeeId,
          data: data as UpdateEmployeePayload,
        })
        if (queuePolicyPayloads.length > 0) {
          await Promise.all(queuePolicyPayloads.map((queuePayload) => upsertQueuePolicyMutation.mutateAsync(queuePayload)))
        }
        if (user?.id === employeeId) {
          updateUser({ name: updated.name, avatar: updated.avatar ?? null })
        }
        setToast({ type: 'success', text: t('emp.saveSuccess', locale) })
        setTimeout(() => setToast(null), 3000)
      } catch {
        setToast({ type: 'error', text: t('emp.saveFailed', locale) })
        setTimeout(() => setToast(null), 3000)
      }
    },
    [canEdit, updateMutation, employeeId, locale, user?.id, updateUser, upsertQueuePolicyMutation]
  )

  const saving = updateMutation.isPending || upsertQueuePolicyMutation.isPending

  if (isLoading || isDefaultQueuePoliciesLoading || isEmployeeQueuePoliciesLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">{t('emp.loading', locale)}</p>
      </div>
    )
  }

  if (!employee) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">Employee not found</p>
      </div>
    )
  }

  const title = t('emp.edit.title', locale, { name: employee.name || employee.username })

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
          <span className="text-base font-semibold">{title}</span>
        </button>
        {canEdit && (
          <button
            type="submit"
            form="employee-form"
            disabled={saving}
            className="flex h-9 items-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
          >
            {saving ? t('emp.saving', locale) : t('emp.save', locale)}
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
        <EmployeeForm
          initialData={employee}
          isEdit
          onSubmit={handleSubmit as (data: UpdateEmployeePayload) => void}
          queueSettings={{
            defaultPolicies: defaultQueuePolicies?.items ?? [],
            scopedPolicies: employeeQueuePolicies?.items ?? [],
          }}
        />
      </div>
    </div>
  )
}
