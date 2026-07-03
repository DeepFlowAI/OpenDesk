'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Switch } from '@/components/ui/switch'
import { useSystemSettings, useUpdateCallTranscription } from '@/service/use-system-settings'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

export default function CallCenterSettingsPage() {
  const { locale } = useLocaleStore()
  const { data, isLoading } = useSystemSettings()
  const updateMutation = useUpdateCallTranscription()

  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    if (data) {
      setEnabled(data.bridge_asr_enabled)
    }
  }, [data])

  const handleSave = async () => {
    try {
      await updateMutation.mutateAsync({ enabled })
      toast.success(t('cs.saveSuccess', locale))
    } catch {
      toast.error(t('cs.saveFailed', locale))
    }
  }

  if (isLoading) {
    return <div className="text-sm text-muted-foreground">{t('cs.loading', locale)}</div>
  }

  const hasChanges = data ? enabled !== data.bridge_asr_enabled : false

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">{t('cs.title', locale)}</h1>

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-4 max-w-[640px]">
          <h2 className="text-sm font-medium text-foreground">{t('cs.transcription', locale)}</h2>
          <Switch checked={enabled} onCheckedChange={setEnabled} />
        </div>
        <p className="max-w-[640px] text-sm leading-relaxed text-muted-foreground">
          {t('cs.transcription.desc', locale)}
        </p>
      </div>

      <div>
        <button
          type="button"
          onClick={handleSave}
          disabled={updateMutation.isPending || !hasChanges}
          className="flex h-10 items-center justify-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-60"
        >
          {updateMutation.isPending ? t('cs.saving', locale) : t('cs.save', locale)}
        </button>
      </div>
    </div>
  )
}
