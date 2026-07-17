'use client'

import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Switch } from '@/components/ui/switch'
import { PromptToneSection } from '@/app/components/features/call-prompt-tone/prompt-tone-section'
import {
  useSystemSettings,
  useUpdateCallTranscription,
} from '@/service/use-system-settings'
import {
  useCallPromptTones,
  useUpdateCallPromptTones,
} from '@/service/use-call-prompt-tones'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { CallPromptTone } from '@/models/call-prompt-tone'

export default function CallCenterSettingsPage() {
  const { locale } = useLocaleStore()
  const { data: settings, isLoading: settingsLoading } = useSystemSettings()
  const { data: tonesData, isLoading: tonesLoading } = useCallPromptTones()
  const updateTranscription = useUpdateCallTranscription()
  const updateTones = useUpdateCallPromptTones()

  const [enabled, setEnabled] = useState(false)
  const [scenes, setScenes] = useState<CallPromptTone[]>([])

  useEffect(() => {
    if (settings) setEnabled(settings.bridge_asr_enabled)
  }, [settings])

  useEffect(() => {
    if (tonesData) setScenes(tonesData.scenes)
  }, [tonesData])

  const isLoading = settingsLoading || tonesLoading
  const isSaving = updateTranscription.isPending || updateTones.isPending

  const transcriptionDirty = settings ? enabled !== settings.bridge_asr_enabled : false
  const tonesDirty = useMemo(() => {
    if (!tonesData) return false
    return JSON.stringify(scenes) !== JSON.stringify(tonesData.scenes)
  }, [scenes, tonesData])
  const hasChanges = transcriptionDirty || tonesDirty

  // Client-side guard mirroring the backend save validation: block saving while
  // an enabled scene has empty TTS text or a missing audio asset.
  const hasInvalidScene = useMemo(
    () =>
      scenes.some((s) => {
        if (!s.enabled) return false
        if (s.prompt_type === 'tts') return (s.tts_text ?? '').trim().length === 0
        return !s.audio_asset_id
      }),
    [scenes],
  )

  // Warn on browser navigation with unsaved changes.
  useEffect(() => {
    if (!hasChanges) return
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [hasChanges])

  const handleSave = async () => {
    try {
      if (transcriptionDirty) {
        await updateTranscription.mutateAsync({ enabled })
      }
      if (tonesDirty) {
        await updateTones.mutateAsync({
          scenes: scenes.map((s) => ({
            scene: s.scene,
            enabled: s.enabled,
            prompt_type: s.prompt_type,
            tts_text: s.tts_text,
            audio_asset_id: s.audio_asset_id,
          })),
        })
      }
      toast.success(t('cpt.saveSuccess', locale))
    } catch {
      toast.error(t('cs.saveFailed', locale))
    }
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <div className="h-6 w-40 animate-pulse rounded bg-muted" />
        <div className="h-24 w-full max-w-[640px] animate-pulse rounded-lg bg-muted" />
        <div className="h-40 w-full max-w-[640px] animate-pulse rounded-lg bg-muted" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-8 pb-8">
      <h1 className="text-xl font-semibold text-foreground">{t('cs.title', locale)}</h1>

      {/* Call transcription (existing block) */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-4 max-w-[640px]">
          <h2 className="text-sm font-medium text-foreground">{t('cs.transcription', locale)}</h2>
          <Switch checked={enabled} onCheckedChange={setEnabled} disabled={isSaving} />
        </div>
        <p className="max-w-[640px] text-sm leading-relaxed text-muted-foreground">
          {t('cs.transcription.desc', locale)}
        </p>
      </div>

      {/* Call prompt tones */}
      <PromptToneSection
        locale={locale}
        scenes={scenes}
        onChange={setScenes}
        disabled={isSaving}
      />

      {/* Footer actions */}
      <div>
        <button
          type="button"
          onClick={handleSave}
          disabled={isSaving || !hasChanges || hasInvalidScene}
          className="flex h-10 items-center justify-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-60"
        >
          {isSaving ? t('cs.saving', locale) : t('cs.save', locale)}
        </button>
      </div>
    </div>
  )
}
