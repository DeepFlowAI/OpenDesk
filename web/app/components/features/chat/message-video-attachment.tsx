'use client'

import { useEffect, useState } from 'react'
import { IconDownload, IconLoader2 } from '@tabler/icons-react'
import { cn } from '@/lib/utils'

const H264_MP4_CONTENT_TYPE = 'video/mp4; codecs="avc1.42E01E"'
const GENERIC_FILE_MIME_TYPES = new Set([
  '',
  'application/octet-stream',
  'binary/octet-stream',
  'unknown',
])

type Mp4Candidate = {
  name?: string | null
  mime_type?: string | null
}

type MessageVideoAttachmentProps = {
  url: string
  fileName: string
  sizeLabel: string
  onDownload: () => Promise<void> | void
  onPlaybackError: () => void
  className?: string
}

export function isMp4VideoCandidate(file: Mp4Candidate | null | undefined): boolean {
  if (!file) return false
  const mimeType = (file.mime_type ?? '').split(';', 1)[0].trim().toLowerCase()
  if (mimeType === 'video/mp4') return true
  return GENERIC_FILE_MIME_TYPES.has(mimeType) && Boolean(file.name?.toLowerCase().endsWith('.mp4'))
}

export function canPlayH264Mp4(video: Pick<HTMLVideoElement, 'canPlayType'>): boolean {
  return video.canPlayType(H264_MP4_CONTENT_TYPE) !== ''
}

export function MessageVideoAttachment({
  url,
  fileName,
  sizeLabel,
  onDownload,
  onPlaybackError,
  className,
}: MessageVideoAttachmentProps) {
  const [ready, setReady] = useState(false)

  useEffect(() => {
    setReady(false)
  }, [url])

  return (
    <div
      className={cn(
        'w-[420px] max-w-full overflow-hidden rounded-[18px] border border-border bg-background text-foreground',
        className,
      )}
    >
      <div className="relative aspect-video w-full overflow-hidden bg-black">
        <video
          data-testid="inline-message-video"
          src={url}
          controls
          playsInline
          preload="metadata"
          aria-label={fileName}
          className={cn('h-full w-full object-contain', !ready && 'opacity-0')}
          onCanPlay={() => setReady(true)}
          onLoadedData={() => setReady(true)}
          onError={onPlaybackError}
        />
        {!ready && (
          <div
            role="status"
            aria-label="Loading video"
            className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black"
          >
            <IconLoader2 size={20} className="animate-spin text-white/70" />
          </div>
        )}
      </div>
      <div className="flex items-center gap-3 border-t border-border px-3 py-2.5">
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium" title={fileName}>{fileName}</div>
          <div className="mt-0.5 text-xs text-muted-foreground">{sizeLabel}</div>
        </div>
        <button
          type="button"
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border text-xs transition-colors hover:bg-muted"
          aria-label="Download video"
          title="下载"
          onClick={(event) => {
            event.stopPropagation()
            void onDownload()
          }}
        >
          <IconDownload size={14} />
        </button>
      </div>
    </div>
  )
}
