'use client'

import { useCallback, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'
import { useCreateRole, useRole } from '@/service/use-roles'
import RoleForm from '@/app/(main)/roles/form'
import type { RolePayload } from '@/models/role'
import { cn } from '@/lib/utils'

export default function NewRolePage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const copyFrom = Number(searchParams.get('copyFrom') ?? 0)
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const { data: sourceRole, isLoading: isSourceLoading } = useRole(copyFrom, copyFrom > 0)
  const createMutation = useCreateRole()
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const canManage = hasPermission(user, 'org.role.manage')

  const initialData = useMemo(() => {
    if (!sourceRole) return undefined
    return {
      ...sourceRole,
      id: undefined,
      key: null,
      name: t('role.copy.name', locale, { name: sourceRole.name }),
      is_system: false,
    }
  }, [locale, sourceRole])

  const handleSubmit = useCallback(async (data: RolePayload) => {
    if (!canManage) return
    try {
      const created = await createMutation.mutateAsync(data)
      setToast({ type: 'success', text: t('role.saveSuccess', locale) })
      setTimeout(() => router.push(`/roles/${created.id}`), 800)
    } catch {
      setToast({ type: 'error', text: t('role.saveFailed', locale) })
      setTimeout(() => setToast(null), 3000)
    }
  }, [canManage, createMutation, locale, router])

  if (copyFrom > 0 && isSourceLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">{t('role.loading', locale)}</p>
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
          <span className="text-base font-semibold">{t('role.new.title', locale)}</span>
        </button>
        {canManage && (
          <button
            type="submit"
            form="role-form"
            disabled={createMutation.isPending}
            className="flex h-9 items-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
          >
            {createMutation.isPending ? t('role.saving', locale) : t('role.save', locale)}
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

      <RoleForm initialData={initialData} onSubmit={handleSubmit} />
    </div>
  )
}
