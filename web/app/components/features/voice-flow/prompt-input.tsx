'use client'
/**
 * Shared TTS / audio-asset prompt input used by play / collect / hangup panels.
 */
import { useState } from 'react'
import type { Prompt } from '@/models/voice-flow-graph'
import { useUploadAudioAsset } from '@/service/use-audio-assets'

export function PromptInput({
  value,
  onChange,
  label = '播报内容',
}: {
  value: Prompt
  onChange: (v: Prompt) => void
  label?: string
}) {
  const upload = useUploadAudioAsset()
  const [error, setError] = useState<string | null>(null)

  return (
    <div className="space-y-3">
      <div>
        <label className="mb-1 block text-xs font-medium text-foreground/80">{label}类型</label>
        <select
          value={value.kind}
          onChange={(e) => {
            const kind = e.target.value as 'tts' | 'audio'
            onChange(kind === 'tts' ? { kind: 'tts', text: '' } : { kind: 'audio', asset_id: 0 })
          }}
          className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm"
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
            onChange={(e) => onChange({ kind: 'tts', text: e.target.value })}
            rows={3}
            maxLength={2000}
            className="w-full rounded-md border border-border bg-white px-2 py-1.5 text-sm"
            placeholder="请输入要播报的内容"
          />
        </div>
      ) : (
        <div>
          <label className="mb-1 block text-xs font-medium text-foreground/80">音频文件</label>
          {value.asset_id > 0 ? (
            <div className="rounded-md border border-border bg-muted/40 px-2 py-1.5 text-sm">
              音频资源 #{value.asset_id}
              <button
                type="button"
                className="ml-2 text-xs text-foreground/60 underline"
                onClick={() => onChange({ kind: 'audio', asset_id: 0 })}
              >
                重新上传
              </button>
            </div>
          ) : (
            <input
              type="file"
              accept="audio/mpeg,audio/wav,audio/x-wav"
              disabled={upload.isPending}
              onChange={async (e) => {
                const file = e.target.files?.[0]
                if (!file) return
                setError(null)
                try {
                  const asset = await upload.mutateAsync(file)
                  onChange({ kind: 'audio', asset_id: asset.id })
                } catch (err: unknown) {
                  setError(err instanceof Error ? err.message : '上传失败')
                }
              }}
              className="block w-full text-sm"
            />
          )}
          {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
        </div>
      )}
    </div>
  )
}
