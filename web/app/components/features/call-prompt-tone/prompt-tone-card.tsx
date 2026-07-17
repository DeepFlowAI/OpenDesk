'use client'
/**
 * Single call-prompt-tone scene card: enable switch, type toggle (TTS / audio),
 * TTS text, audio upload/preview, local preview, read-only play mode, reset.
 */
import { useState } from 'react'
import { IconRefresh, IconUpload } from '@tabler/icons-react'
import { Switch } from '@/components/ui/switch'
import { AudioPlayer } from '@/app/components/base/audio-player'
import { useUploadAudioAsset, useAudioAsset } from '@/service/use-audio-assets'
import { formatDuration } from '@/utils/format-duration'
import { t } from '@/utils/i18n'
import type { Locale } from '@/context/locale-store'
import type { CallPromptScene, CallPromptTone } from '@/models/call-prompt-tone'
import { DEFAULT_TTS_TEXT } from '@/models/call-prompt-tone'

const TTS_MAX = 300

type Props = {
  locale: Locale
  value: CallPromptTone
  onChange: (next: CallPromptTone) => void
  disabled?: boolean
  activeToken: string | null
  onActivate: (token: string) => void
  onDeactivate: () => void
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function PromptToneCard({
  locale,
  value,
  onChange,
  disabled,
  activeToken,
  onActivate,
  onDeactivate,
}: Props) {
  const upload = useUploadAudioAsset()
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)

  // Resolve the selected asset (name / size / duration / preview_url).
  const assetQuery = useAudioAsset(
    value.prompt_type === 'audio' ? value.audio_asset_id : null,
  )
  const asset = assetQuery.data
  const assetInvalid =
    value.prompt_type === 'audio' &&
    !!value.audio_asset_id &&
    assetQuery.isError

  const scene = value.scene as CallPromptScene
  const playMode = value.play_mode

  const handleReset = () => {
    onDeactivate()
    onChange({
      ...value,
      enabled: true,
      prompt_type: 'tts',
      tts_text: DEFAULT_TTS_TEXT[scene],
      audio_asset_id: null,
    })
  }

  const ttsLen = (value.tts_text ?? '').trim().length
  const ttsEmptyError = value.enabled && value.prompt_type === 'tts' && ttsLen === 0

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-foreground">
            {t(`cpt.scene.${scene}.name`, locale)}
          </h3>
          <p className="mt-1 max-w-[560px] text-xs leading-relaxed text-muted-foreground">
            {t(`cpt.scene.${scene}.desc`, locale)}
          </p>
        </div>
        <Switch
          checked={value.enabled}
          onCheckedChange={(checked) => onChange({ ...value, enabled: checked })}
          disabled={disabled}
        />
      </div>

      {value.enabled && (
        <>
          {/* Type toggle (segmented) */}
          <div className="inline-flex w-fit rounded-lg border border-border p-0.5">
            {(['tts', 'audio'] as const).map((type) => (
              <button
                key={type}
                type="button"
                disabled={disabled}
                onClick={() => {
                  onDeactivate()
                  onChange({ ...value, prompt_type: type })
                }}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                  value.prompt_type === type
                    ? 'bg-primary text-white'
                    : 'text-foreground/70 hover:bg-accent'
                }`}
              >
                {t(`cpt.type.${type}`, locale)}
              </button>
            ))}
          </div>

          {value.prompt_type === 'tts' ? (
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-foreground/80">
                {t('cpt.type.tts', locale)}
              </label>
              <textarea
                value={value.tts_text ?? ''}
                disabled={disabled}
                maxLength={TTS_MAX}
                rows={2}
                onChange={(e) => onChange({ ...value, tts_text: e.target.value })}
                className="w-full max-w-[560px] rounded-md border border-border bg-white px-2.5 py-2 text-sm disabled:opacity-50"
                placeholder={DEFAULT_TTS_TEXT[scene]}
              />
              <div className="flex items-center justify-between max-w-[560px]">
                {ttsEmptyError ? (
                  <span className="text-xs text-destructive">
                    {t('cpt.err.ttsRequired', locale)}
                  </span>
                ) : (
                  <span />
                )}
                <span className="text-xs text-muted-foreground">
                  {ttsLen}/{TTS_MAX}
                </span>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <label className="text-xs font-medium text-foreground/80">
                {t('cpt.type.audio', locale)}
              </label>
              {value.audio_asset_id ? (
                <div className="max-w-[560px] rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                  {assetInvalid ? (
                    <p className="text-xs text-destructive">
                      {t('cpt.err.assetInvalid', locale)}
                    </p>
                  ) : (
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-foreground/70">
                      <span className="font-medium text-foreground">
                        {asset?.name ?? `#${value.audio_asset_id}`}
                      </span>
                      {asset?.mime_type && <span>{asset.mime_type}</span>}
                      {asset?.size_bytes != null && (
                        <span>{formatBytes(asset.size_bytes)}</span>
                      )}
                      {asset?.duration_ms != null && (
                        <span>{formatDuration(asset.duration_ms / 1000)}</span>
                      )}
                    </div>
                  )}
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => {
                      onDeactivate()
                      onChange({ ...value, audio_asset_id: null })
                    }}
                    className="mt-2 text-xs text-primary underline disabled:opacity-50"
                  >
                    {t('cpt.audio.replace', locale)}
                  </button>
                </div>
              ) : (
                <label className="inline-flex w-fit cursor-pointer items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-foreground/80 hover:bg-accent">
                  <IconUpload className="size-4" />
                  {upload.isPending
                    ? t('cpt.audio.uploading', locale)
                    : t('cpt.audio.upload', locale)}
                  <input
                    type="file"
                    accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav"
                    disabled={disabled || upload.isPending}
                    className="hidden"
                    onChange={async (e) => {
                      const file = e.target.files?.[0]
                      if (!file) return
                      setUploadError(null)
                      try {
                        const created = await upload.mutateAsync(file)
                        onChange({ ...value, audio_asset_id: created.id })
                      } catch {
                        setUploadError(t('cpt.err.uploadFailed', locale))
                      }
                    }}
                  />
                </label>
              )}
              {uploadError && (
                <p className="text-xs text-destructive">{uploadError}</p>
              )}
            </div>
          )}

          {/* Preview + play mode + reset */}
          <div className="flex flex-wrap items-center gap-3">
            <AudioPlayer
              mode={value.prompt_type}
              text={value.tts_text}
              url={value.prompt_type === 'audio' ? asset?.preview_url : null}
              lang={locale}
              token={`prompt-tone-${scene}`}
              activeToken={activeToken}
              onActivate={onActivate}
              onDeactivate={onDeactivate}
              onError={() => setPreviewError(t('cpt.err.previewFailed', locale))}
              disabled={
                disabled ||
                (value.prompt_type === 'tts' && ttsLen === 0) ||
                (value.prompt_type === 'audio' &&
                  (!value.audio_asset_id || assetInvalid))
              }
              playLabel={t('cpt.preview.play', locale)}
              stopLabel={t('cpt.preview.stop', locale)}
            />
            <span className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
              {t(`cpt.playMode.${playMode}`, locale)}
            </span>
            <button
              type="button"
              disabled={disabled}
              onClick={handleReset}
              className="inline-flex items-center gap-1 text-xs text-foreground/60 hover:text-foreground disabled:opacity-50"
            >
              <IconRefresh className="size-3.5" />
              {t('cpt.reset', locale)}
            </button>
          </div>
          {previewError && (
            <p className="text-xs text-destructive">{previewError}</p>
          )}
        </>
      )}
    </div>
  )
}
