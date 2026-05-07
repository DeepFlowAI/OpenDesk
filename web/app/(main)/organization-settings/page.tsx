'use client'

import { useState, useEffect } from 'react'
import { useSystemSettings, useUpdateOrganizationSettings } from '@/service/use-system-settings'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

export default function OrganizationSettingsPage() {
  const { locale } = useLocaleStore()
  const { data, isLoading } = useSystemSettings()
  const updateMutation = useUpdateOrganizationSettings()

  const [enabled, setEnabled] = useState(false)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    if (data) {
      setEnabled(data.organization_enabled)
    }
  }, [data])

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000)
      return () => clearTimeout(timer)
    }
  }, [toast])

  const handleSave = async () => {
    try {
      await updateMutation.mutateAsync({ organization_enabled: enabled })
      setToast({ type: 'success', text: t('os.saveSuccess', locale) })
    } catch {
      setToast({ type: 'error', text: t('os.saveFailed', locale) })
    }
  }

  if (isLoading) {
    return (
      <div className="text-sm text-muted-foreground">{t('os.loading', locale)}</div>
    )
  }

  const hasChanges = data ? enabled !== data.organization_enabled : false

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">
        {t('os.title', locale)}
      </h1>

      {toast && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            toast.type === 'success'
              ? 'border-green-200 bg-green-50 text-green-700'
              : 'border-red-200 bg-red-50 text-red-700'
          }`}
        >
          {toast.text}
        </div>
      )}

      <div className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-foreground">
          {t('os.enableOrg', locale)}
        </h2>
        <p className="max-w-[600px] text-sm leading-relaxed text-muted-foreground">
          {t('os.enableOrg.desc', locale)}
        </p>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={() => setEnabled(!enabled)}
          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors ${
            enabled ? 'bg-primary' : 'bg-input'
          }`}
        >
          <span
            className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
              enabled ? 'translate-x-[18px]' : 'translate-x-[3px]'
            }`}
          />
        </button>
      </div>

      <div>
        <button
          type="button"
          onClick={handleSave}
          disabled={updateMutation.isPending || !hasChanges}
          className="flex h-10 items-center justify-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-60"
        >
          {updateMutation.isPending
            ? t('os.saving', locale)
            : t('os.save', locale)}
        </button>
      </div>
    </div>
  )
}
