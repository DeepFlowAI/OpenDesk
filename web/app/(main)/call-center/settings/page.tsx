'use client'

import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Switch } from '@/components/ui/switch'
import { PromptToneSection } from '@/app/components/features/call-prompt-tone/prompt-tone-section'
import { EmbeddedPagesSection } from '@/app/components/features/conversation-settings/embedded-pages-section'
import {
  useSystemSettings,
  useUpdateCallShortAbandon,
  useUpdateCallTranscription,
  useUpdateCallWrapup,
} from '@/service/use-system-settings'
import {
  useCallPromptTones,
  useUpdateCallPromptTones,
} from '@/service/use-call-prompt-tones'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { CallPromptTone } from '@/models/call-prompt-tone'
import { OutboundPrescreenIntentEntry } from '@/app/components/features/call-center/outbound-prescreen-intent-entry'
import { WrapUpSection } from '@/app/components/features/call-center/wrap-up-section'
import { ShortAbandonSection } from '@/app/components/features/call-center/short-abandon-section'

export default function CallCenterSettingsPage() {
  const { locale } = useLocaleStore()
  const { data: settings, isLoading: settingsLoading } = useSystemSettings()
  const { data: tonesData, isLoading: tonesLoading } = useCallPromptTones()
  const updateTranscription = useUpdateCallTranscription()
  const updateTones = useUpdateCallPromptTones()
  const updateWrapup = useUpdateCallWrapup()
  const updateShortAbandon = useUpdateCallShortAbandon()

  const [enabled, setEnabled] = useState(false)
  const [scenes, setScenes] = useState<CallPromptTone[]>([])
  const [wrapupInput, setWrapupInput] = useState('30')
  const [shortAbandonInput, setShortAbandonInput] = useState('5')

  useEffect(() => {
    if (settings) setEnabled(settings.bridge_asr_enabled)
  }, [settings])

  useEffect(() => {
    if (settings) setWrapupInput(String(settings.call_wrapup_seconds))
  }, [settings])

  useEffect(() => {
    if (settings) {
      setShortAbandonInput(String(settings.call_short_abandon_threshold_seconds))
    }
  }, [settings])

  useEffect(() => {
    if (tonesData) setScenes(tonesData.scenes)
  }, [tonesData])

  const isSaving = updateTranscription.isPending || updateTones.isPending
  const wrapupSaving = updateWrapup.isPending
  const shortAbandonSaving = updateShortAbandon.isPending

  const transcriptionDirty = settings ? enabled !== settings.bridge_asr_enabled : false
  const tonesDirty = useMemo(() => {
    if (!tonesData) return false
    return JSON.stringify(scenes) !== JSON.stringify(tonesData.scenes)
  }, [scenes, tonesData])
  const wrapupParsed = /^\d+$/.test(wrapupInput.trim()) ? Number(wrapupInput.trim()) : NaN
  const wrapupValid = Number.isInteger(wrapupParsed) && wrapupParsed >= 0 && wrapupParsed <= 60
  const wrapupDirty = settings ? wrapupInput.trim() !== String(settings.call_wrapup_seconds) : false
  const shortAbandonParsed = /^\d+$/.test(shortAbandonInput.trim())
    ? Number(shortAbandonInput.trim())
    : NaN
  const shortAbandonValid =
    Number.isInteger(shortAbandonParsed) && shortAbandonParsed >= 1 && shortAbandonParsed <= 60
  const shortAbandonDirty = settings
    ? shortAbandonInput.trim() !== String(settings.call_short_abandon_threshold_seconds)
    : false
  // The footer save only covers transcription + prompt tones; the two numeric
  // settings save independently.
  const footerDirty = transcriptionDirty || tonesDirty
  const hasChanges = footerDirty || wrapupDirty || shortAbandonDirty

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

  const handleWrapupSave = async () => {
    if (!wrapupValid) return
    try {
      await updateWrapup.mutateAsync({ seconds: wrapupParsed })
      toast.success(t('cs.wrapup.saveSuccess', locale))
    } catch {
      toast.error(t('cs.saveFailed', locale))
    }
  }

  const handleShortAbandonSave = async () => {
    if (!shortAbandonValid) return
    try {
      await updateShortAbandon.mutateAsync({ seconds: shortAbandonParsed })
      toast.success(t('cs.shortAbandon.saveSuccess', locale))
    } catch {
      toast.error(t('cs.saveFailed', locale))
    }
  }

  return (
    <div className="flex flex-col gap-8 pb-8">
      <h1 className="text-xl font-semibold text-foreground">{t('cs.title', locale)}</h1>

      {settingsLoading ? (
        <div className="flex max-w-[640px] flex-col gap-4" aria-hidden="true">
          <div className="h-24 animate-pulse rounded-lg bg-muted" />
          <div className="h-40 animate-pulse rounded-lg bg-muted" />
          <div className="h-40 animate-pulse rounded-lg bg-muted" />
        </div>
      ) : (
        <>
          {/* Call transcription (existing block) */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-4 max-w-[640px]">
              <h2 className="text-sm font-medium text-foreground">
                {t('cs.transcription', locale)}
              </h2>
              <Switch checked={enabled} onCheckedChange={setEnabled} disabled={isSaving} />
            </div>
            <p className="max-w-[640px] text-sm leading-relaxed text-muted-foreground">
              {t('cs.transcription.desc', locale)}
            </p>
          </div>

          {/* After-call work duration (saves independently) */}
          <WrapUpSection
            locale={locale}
            value={wrapupInput}
            onChange={setWrapupInput}
            onSave={handleWrapupSave}
            saving={wrapupSaving}
            dirty={wrapupDirty}
            valid={wrapupValid}
            parsed={Number.isInteger(wrapupParsed) ? wrapupParsed : 0}
          />

          <ShortAbandonSection
            locale={locale}
            value={shortAbandonInput}
            onChange={setShortAbandonInput}
            onSave={handleShortAbandonSave}
            saving={shortAbandonSaving}
            dirty={shortAbandonDirty}
            valid={shortAbandonValid}
            parsed={Number.isInteger(shortAbandonParsed) ? shortAbandonParsed : 0}
          />
        </>
      )}

      {/* Call prompt tones */}
      {tonesLoading ? (
        <div
          className="h-40 w-full max-w-[640px] animate-pulse rounded-lg bg-muted"
          aria-hidden="true"
        />
      ) : (
        <PromptToneSection
          locale={locale}
          scenes={scenes}
          onChange={setScenes}
          disabled={isSaving}
        />
      )}

      {/* Screen-pop embedded pages */}
      <EmbeddedPagesSection
        location="call_screen_pop"
        basePath="/call-center/settings/embedded-pages"
      />

      {/* Footer actions */}
      <div>
        <button
          type="button"
          onClick={handleSave}
          disabled={settingsLoading || tonesLoading || isSaving || !footerDirty || hasInvalidScene}
          className="flex h-10 items-center justify-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-60"
        >
          {isSaving ? t('cs.saving', locale) : t('cs.save', locale)}
        </button>
      </div>

      <OutboundPrescreenIntentEntry />
    </div>
  )
}
