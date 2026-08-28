'use client'

import { useRef, useState } from 'react'
import { IconMicrophone, IconTrash, IconUpload } from '@tabler/icons-react'
import { toast } from 'sonner'

import { PersonalOutboundRecorderDialog } from '@/app/components/features/call-center/personal-outbound-recorder-dialog'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import type { PersonalOutboundRecording } from '@/models/personal-auto-outbound'
import { convertAudioFileToWav } from '@/lib/audio-wav'
import { t } from '@/utils/i18n'

export function PersonalOutboundRecordingField({
  type,
  recording,
  disabled,
  pending,
  onUpload,
  onRemove,
  openingScript,
  onOpeningScriptChange,
  onOpeningScriptSave,
  openingScriptError,
}: {
  type: 'opening' | 'closing'
  recording?: PersonalOutboundRecording
  disabled: boolean
  pending: boolean
  onUpload: (file: File) => Promise<void>
  onRemove: () => Promise<void>
  openingScript?: string
  onOpeningScriptChange?: (value: string) => void
  onOpeningScriptSave?: () => void
  openingScriptError?: string | null
}) {
  const { locale } = useLocaleStore()
  const inputRef = useRef<HTMLInputElement>(null)
  const [recorderOpen, setRecorderOpen] = useState(false)
  const upload = async (file: File) => {
    if (file.size > 10 * 1024 * 1024) {
      toast.error(t('personalAuto.audioTooLarge', locale))
      return
    }
    const ext = file.name.toLowerCase().split('.').pop()
    if (ext !== 'mp3' && ext !== 'wav') {
      toast.error(t('personalAuto.audioFormat', locale))
      return
    }
    try {
      const playableFile = ext === 'mp3' ? await convertAudioFileToWav(file) : file
      if (playableFile.size > 10 * 1024 * 1024) {
        toast.error(t('personalAuto.audioTooLarge', locale))
        return
      }
      await onUpload(playableFile)
    } catch {
      // The parent already displays the request error and keeps the current recording.
    }
  }

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex items-start justify-between gap-3">
        <div><h3 className="text-sm font-semibold">{t(type === 'opening' ? 'personalAuto.opening' : 'personalAuto.closing', locale)}</h3><p className="mt-1 text-xs text-muted-foreground">{t(type === 'opening' ? 'personalAuto.openingHint' : 'personalAuto.closingHint', locale)}</p></div>
        <div className="flex gap-2">
          <input ref={inputRef} type="file" accept=".mp3,.wav,audio/mpeg,audio/wav" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); event.target.value = '' }} />
          <Button variant="outline" size="sm" disabled={disabled || pending} onClick={() => inputRef.current?.click()}><IconUpload size={15} />{t(recording ? 'personalAuto.replace' : 'personalAuto.upload', locale)}</Button>
          <Button variant="outline" size="sm" disabled={disabled || pending} onClick={() => setRecorderOpen(true)}><IconMicrophone size={15} />{t('personalAuto.record', locale)}</Button>
          {recording && <Button variant="ghost" size="icon" disabled={disabled || pending} aria-label={t('personalAuto.remove', locale)} onClick={() => void onRemove()}><IconTrash size={16} /></Button>}
        </div>
      </div>
      {recording?.audio.preview_url ? <audio className="mt-3 w-full" controls src={recording.audio.preview_url} /> : <p className="mt-3 rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground">{t('personalAuto.noRecording', locale)}</p>}
      {type === 'opening' && onOpeningScriptChange && (
        <label className="mt-4 block">
          <span className="text-xs font-medium">{t('personalAuto.openingScript', locale)}</span>
          <span className="ml-1.5 text-[11px] text-muted-foreground">{t('personalAuto.openingScriptHint', locale)}</span>
          <textarea
            className="mt-1.5 min-h-[72px] w-full rounded-md border border-border bg-background px-3 py-2 text-sm leading-6 outline-none focus-visible:border-ring disabled:cursor-not-allowed disabled:bg-muted/40"
            value={openingScript ?? ''}
            maxLength={200}
            disabled={disabled}
            aria-label={t('personalAuto.openingScript', locale)}
            onChange={(event) => onOpeningScriptChange(event.target.value)}
            onBlur={() => onOpeningScriptSave?.()}
          />
          {openingScriptError ? <p className="mt-1 text-[11px] text-destructive">{openingScriptError}</p> : null}
        </label>
      )}
      <PersonalOutboundRecorderDialog open={recorderOpen} type={type} onOpenChange={setRecorderOpen} onSave={onUpload} saving={pending} />
    </div>
  )
}
