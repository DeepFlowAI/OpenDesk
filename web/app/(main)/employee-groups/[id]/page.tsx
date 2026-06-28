'use client'

import { useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'
import { useEmployeeGroup, useUpdateEmployeeGroup } from '@/service/use-employee-groups'
import { useQueuePolicies, useUpsertQueuePolicy } from '@/service/use-queue-policies'
import EmployeeGroupForm from '@/app/(main)/employee-groups/form'
import type { UpdateEmployeeGroupPayload } from '@/models/employee-group'
import type { QueuePolicyUpsertPayload } from '@/models/queue-policy'

export default function EditEmployeeGroupPage() {
  const router = useRouter()
  const params = useParams()
  const id = Number(params.id)
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const { data, isLoading } = useEmployeeGroup(id)
  const canManage = hasPermission(user, 'org.group.manage')
  const canManageQueue = hasPermission(user, 'org.queue.manage')
  const { data: defaultQueuePolicies, isLoading: isDefaultQueuePoliciesLoading } = useQueuePolicies({
    scope_type: 'global',
  }, { enabled: canManageQueue })
  const { data: groupQueuePolicies, isLoading: isGroupQueuePoliciesLoading } = useQueuePolicies(
    { scope_type: 'employee_group', scope_id: id },
    { enabled: !!id && canManageQueue }
  )
  const updateMutation = useUpdateEmployeeGroup()
  const upsertQueuePolicyMutation = useUpsertQueuePolicy()
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const handleSave = async (
    payload: UpdateEmployeeGroupPayload,
    queuePolicyPayloads: QueuePolicyUpsertPayload[] = []
  ) => {
    if (!canManage) return
    try {
      await updateMutation.mutateAsync({ id, data: payload })
      if (canManageQueue && queuePolicyPayloads.length > 0) {
        await Promise.all(queuePolicyPayloads.map((queuePayload) => upsertQueuePolicyMutation.mutateAsync(queuePayload)))
      }
      setToast({ type: 'success', text: t('eg.saveSuccess', locale) })
      setTimeout(() => setToast(null), 3000)
    } catch {
      setToast({ type: 'error', text: t('eg.saveFailed', locale) })
      setTimeout(() => setToast(null), 3000)
    }
  }

  const saving = updateMutation.isPending || upsertQueuePolicyMutation.isPending

  if (isLoading || (canManageQueue && (isDefaultQueuePoliciesLoading || isGroupQueuePoliciesLoading))) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">{t('eg.loading', locale)}</p>
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
          onClick={() => router.push('/employee-groups')}
          className="flex items-center gap-2 transition-colors hover:opacity-80"
        >
          <IconArrowLeft size={20} className="text-muted-foreground" />
          <span className="text-base font-semibold text-foreground">
            {t('eg.edit', locale, { name: data.name })}
          </span>
        </button>
        {canManage && (
          <button
            onClick={() => {
              const form = document.getElementById('eg-form') as HTMLFormElement | null
              form?.requestSubmit()
            }}
            disabled={saving}
            className="flex h-9 items-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
          >
            {saving ? t('eg.saving', locale) : t('eg.save', locale)}
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
        <EmployeeGroupForm
          initialData={data}
          onSubmit={handleSave}
          saving={saving}
          queueSettings={canManageQueue
            ? {
                defaultPolicies: defaultQueuePolicies?.items ?? [],
                scopedPolicies: groupQueuePolicies?.items ?? [],
              }
            : undefined}
        />
      </div>
    </div>
  )
}
