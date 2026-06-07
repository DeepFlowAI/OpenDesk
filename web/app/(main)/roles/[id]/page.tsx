'use client'

import { useCallback, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'
import { useRole, useUpdateRole } from '@/service/use-roles'
import RoleForm from '@/app/(main)/roles/form'
import type { RolePayload } from '@/models/role'
import { cn } from '@/lib/utils'

export default function EditRolePage() {
  const router = useRouter()
  const params = useParams()
  const roleId = Number(params.id)
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const { data: role, isLoading } = useRole(roleId)
  const updateMutation = useUpdateRole()
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const canManage = hasPermission(user, 'org.role.manage')

  const handleSubmit = useCallback(async (data: RolePayload) => {
    if (!canManage) return
    try {
      await updateMutation.mutateAsync({ id: roleId, data })
      setToast({ type: 'success', text: t('role.saveSuccess', locale) })
      setTimeout(() => setToast(null), 3000)
    } catch {
      setToast({ type: 'error', text: t('role.saveFailed', locale) })
      setTimeout(() => setToast(null), 3000)
    }
  }, [canManage, locale, roleId, updateMutation])

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">{t('role.loading', locale)}</p>
      </div>
    )
  }

  if (!role) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">{t('role.notFound', locale)}</p>
      </div>
    )
  }

  return (
    <div className="-m-8 flex flex-col">
      <div className="sticky -top-8 z-20 flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <button
          type="button"
          onClick={() => router.push('/roles')}
          className="flex items-center gap-2 text-foreground transition-colors hover:text-foreground/80"
        >
          <IconArrowLeft size={20} className="text-muted-foreground" />
          <span className="text-base font-semibold">
            {t('role.edit.title', locale, { name: role.name })}
          </span>
        </button>
        {canManage && !role.is_system && (
          <button
            type="submit"
            form="role-form"
            disabled={updateMutation.isPending}
            className="flex h-9 items-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
          >
            {updateMutation.isPending ? t('role.saving', locale) : t('role.save', locale)}
          </button>
        )}
      </div>

      {toast && (
        <div
          className={cn(
            'mx-8 mt-4 rounded-lg px-4 py-3 text-sm',
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          )}
        >
          {toast.text}
        </div>
      )}

      <RoleForm initialData={role} readOnly={role.is_system} onSubmit={handleSubmit} />
    </div>
  )
}
