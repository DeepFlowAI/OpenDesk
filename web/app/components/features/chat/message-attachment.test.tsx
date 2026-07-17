import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { createPendingAttachmentContent } from '@/lib/pending-attachment'
import { MessageAttachment, resolvePdfiumWasmUrl } from './message-attachment'
import { canPlayH264Mp4, isMp4VideoCandidate } from './message-video-attachment'

describe('MessageAttachment pending upload', () => {
  it('renders the retained file name and size before an upload succeeds', () => {
    const file = new File(['hello'], 'report.txt', { type: 'text/plain' })

    const html = renderToStaticMarkup(
      <MessageAttachment
        contentType="file"
        content={createPendingAttachmentContent(file, 'blob:https://example.test/local-file')}
      />,
    )

    expect(html).toContain('report.txt')
    expect(html).toContain('5 B')
  })

  it('renders a local image preview before an upload succeeds', () => {
    const file = new File(['image'], 'photo.png', { type: 'image/png' })

    const html = renderToStaticMarkup(
      <MessageAttachment
        contentType="image"
        content={createPendingAttachmentContent(file, 'blob:https://example.test/local-image')}
      />,
    )

    expect(html).toContain('alt="photo.png"')
    expect(html).toContain('src="blob:https://example.test/local-image"')
  })
})

describe('MessageAttachment PDF preview', () => {
  it('uses an absolute URL for the PDFium worker asset', () => {
    expect(resolvePdfiumWasmUrl('https://opendesk-test.example.com')).toBe(
      'https://opendesk-test.example.com/vendor/embedpdf/pdfium.wasm',
    )
  })
})

describe('MessageAttachment inline MP4 video', () => {
  it('only treats MP4 video MIME or generic MP4 files as candidates', () => {
    expect(isMp4VideoCandidate({ name: 'clip.bin', mime_type: 'video/mp4' })).toBe(true)
    expect(isMp4VideoCandidate({ name: 'clip.MP4', mime_type: 'application/octet-stream' })).toBe(true)
    expect(isMp4VideoCandidate({ name: 'clip.mp4', mime_type: 'application/pdf' })).toBe(false)
    expect(isMp4VideoCandidate({ name: 'clip.mov', mime_type: 'video/quicktime' })).toBe(false)
  })

  it('uses the browser H.264 capability result', () => {
    const supported = { canPlayType: vi.fn(() => 'probably' as CanPlayTypeResult) }
    const unsupported = { canPlayType: vi.fn(() => '' as CanPlayTypeResult) }

    expect(canPlayH264Mp4(supported)).toBe(true)
    expect(canPlayH264Mp4(unsupported)).toBe(false)
    expect(supported.canPlayType).toHaveBeenCalledWith('video/mp4; codecs="avc1.42E01E"')
  })

  it('falls back to the file card when the browser reports no H.264 support', async () => {
    const canPlayType = vi.spyOn(HTMLMediaElement.prototype, 'canPlayType').mockReturnValue('')
    const file = new File(['video'], 'clip.mp4', { type: 'video/mp4' })
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    await act(async () => {
      root.render(
        <MessageAttachment
          contentType="file"
          content={createPendingAttachmentContent(file, 'blob:https://example.test/local-video')}
          inlinePlayableVideo
        />,
      )
    })

    expect(container.querySelector('[data-testid="inline-message-video"]')).toBeNull()
    expect(container.textContent).toContain('clip.mp4')
    expect(container.querySelector('[aria-label="Preview file"]')).not.toBeNull()

    await act(async () => root.unmount())
    container.remove()
    canPlayType.mockRestore()
  })

  it('shows the player after canplay and falls back to the file card after a media error', async () => {
    const canPlayType = vi
      .spyOn(HTMLMediaElement.prototype, 'canPlayType')
      .mockReturnValue('probably')
    const file = new File(['video'], 'clip.mp4', { type: 'video/mp4' })
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    await act(async () => {
      root.render(
        <MessageAttachment
          contentType="file"
          content={createPendingAttachmentContent(file, 'blob:https://example.test/local-video')}
          inlinePlayableVideo
        />,
      )
    })

    const video = container.querySelector<HTMLVideoElement>('[data-testid="inline-message-video"]')
    expect(video).not.toBeNull()
    expect(container.querySelector('[role="status"]')).not.toBeNull()

    await act(async () => {
      video?.dispatchEvent(new Event('canplay', { bubbles: true }))
    })
    expect(container.querySelector('[role="status"]')).toBeNull()

    await act(async () => {
      video?.dispatchEvent(new Event('error', { bubbles: true }))
    })
    expect(container.querySelector('[data-testid="inline-message-video"]')).toBeNull()
    expect(container.textContent).toContain('clip.mp4')
    expect(container.querySelector('[aria-label="Preview file"]')).not.toBeNull()

    await act(async () => root.unmount())
    container.remove()
    canPlayType.mockRestore()
  })

  it('keeps MP4 files as file cards when inline playback is not enabled', () => {
    const file = new File(['video'], 'clip.mp4', { type: 'video/mp4' })
    const html = renderToStaticMarkup(
      <MessageAttachment
        contentType="file"
        content={createPendingAttachmentContent(file, 'blob:https://example.test/local-video')}
      />,
    )

    expect(html).toContain('clip.mp4')
    expect(html).not.toContain('<video')
  })
})
