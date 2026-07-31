'use client'
/**
 * Shared TTS / audio-asset prompt input used by play / collect / hangup panels.
 */
import { useEffect, useRef, useState } from 'react'
import { HTTPError } from 'ky'
import type { Prompt } from '@/models/voice-flow-graph'
import { useAudioAsset, useUploadAudioAsset } from '@/service/use-audio-assets'

async function readUploadErrorMessage(error: unknown): Promise<string> {
  if (error instanceof HTTPError) {
    try {
      const body = (await error.response.json()) as { message?: string }
      if (body.message?.trim()) return body.message.trim()
    } catch {
      // fall through
    }
    return '上传失败，请检查文件格式后重试'
  }
  if (error instanceof Error && error.message.trim()) return error.message.trim()
  return '上传失败'
}

export function PromptInput({
  value,
  onChange,
  label = '播报内容',
  disabled = false,
}: {
  value: Prompt
  onChange: (v: Prompt) => void
  label?: string
  disabled?: boolean
}) {
  const upload = useUploadAudioAsset()
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  // Keep the other kind's draft so switching TTS <-> audio does not wipe content.
  const cachedTtsRef = useRef('')
  const cachedAudioIdRef = useRef(0)
  const [localFileName, setLocalFileName] = useState<string | null>(null)

  const assetId = value.kind === 'audio' && value.asset_id > 0 ? value.asset_id : null
  const assetQuery = useAudioAsset(assetId)
  const displayName =
    localFileName ||
    assetQuery.data?.name ||
    (assetId != null ? `音频资源 #${assetId}` : null)

  useEffect(() => {
    if (value.kind === 'tts') cachedTtsRef.current = value.text
    if (value.kind === 'audio' && value.asset_id > 0) cachedAudioIdRef.current = value.asset_id
  }, [value])

  useEffect(() => {
    // Clear local filename once the server-side name is available.
    if (assetQuery.data?.name) setLocalFileName(null)
  }, [assetQuery.data?.name])

  const uploadFile = async (file: File) => {
    setError(null)
    setLocalFileName(file.name)
    try {
      const asset = await upload.mutateAsync(file)
      cachedAudioIdRef.current = asset.id
      onChange({ kind: 'audio', asset_id: asset.id })
    } catch (err: unknown) {
      setLocalFileName(null)
      setError(await readUploadErrorMessage(err))
    }
  }

  const switchKind = (kind: 'tts' | 'audio') => {
    if (kind === 'tts') {
      onChange({ kind: 'tts', text: cachedTtsRef.current })
      return
    }
    onChange({
      kind: 'audio',
      asset_id: cachedAudioIdRef.current > 0 ? cachedAudioIdRef.current : 0,
    })
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="mb-1 block text-xs font-medium text-foreground/80">{label}类型</label>
        <select
          value={value.kind}
          disabled={disabled}
          onChange={(e) => switchKind(e.target.value as 'tts' | 'audio')}
          className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm disabled:opacity-50"
        >
          <option value="tts">TTS 文案</option>
          <option value="audio">音频文件</option>
        </select>
      </div>

      {value.kind === 'tts' ? (
        <div>
          <label className="mb-1 block text-xs font-medium text-foreground/80">TTS 文案</label>
          <textarea
            value={value.text}
            disabled={disabled}
            onChange={(e) => onChange({ kind: 'tts', text: e.target.value })}
            rows={4}
            maxLength={2000}
            className="max-h-40 w-full resize-y rounded-md border border-border bg-white px-2 py-1.5 text-sm disabled:opacity-50"
            placeholder="请输入要播报的内容"
          />
        </div>
      ) : (
        <div>
          <label className="mb-1 block text-xs font-medium text-foreground/80">音频文件</label>
          <input
            ref={fileInputRef}
            type="file"
            accept="audio/mpeg,audio/wav,audio/x-wav"
            disabled={disabled || upload.isPending}
            className="sr-only"
            onChange={async (e) => {
              const file = e.target.files?.[0]
              e.target.value = ''
              if (!file) return
              await uploadFile(file)
            }}
          />
          {value.asset_id > 0 ? (
            <div className="rounded-md border border-border bg-muted/40 px-2 py-1.5 text-sm">
              <span className="break-all">{displayName}</span>
              <button
                type="button"
                disabled={disabled || upload.isPending}
                className="ml-2 text-xs text-foreground/60 underline disabled:opacity-50"
                onClick={() => fileInputRef.current?.click()}
              >
                {upload.isPending ? '上传中…' : '重新上传'}
              </button>
            </div>
          ) : (
            <button
              type="button"
              disabled={disabled || upload.isPending}
              onClick={() => fileInputRef.current?.click()}
              className="h-9 rounded-md border border-border bg-white px-3 text-sm text-foreground/80 hover:bg-muted disabled:opacity-50"
            >
              {upload.isPending ? '上传中…' : '选择文件'}
            </button>
          )}
          {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
        </div>
      )}
    </div>
  )
}
