import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getConversationFileUrl } from '@/service/use-conversation-files'
import { postForm } from '@/service/base'
import {
  buildKnowledgeImageHtml,
  KNOWLEDGE_GIF_IMAGE_PROCESS_PROFILES,
  KNOWLEDGE_STATIC_IMAGE_PROCESS_PROFILES,
  KnowledgeImageTransferError,
  MAX_KNOWLEDGE_IMAGE_BYTES,
  MAX_OSS_IMAGE_PROCESS_SOURCE_BYTES,
  persistKnowledgeImage,
} from './knowledge-message-image'

vi.mock('@/service/use-conversation-files', () => ({
  getConversationFileUrl: vi.fn(),
}))

vi.mock('@/service/base', () => ({
  postForm: vi.fn(),
}))

const mockedGetConversationFileUrl = vi.mocked(getConversationFileUrl)
const mockedPostForm = vi.mocked(postForm)

function sizedImageBlob(size: number, type: string): Blob {
  return { size, type } as Blob
}

function responseWith(blob: Blob): Pick<Response, 'ok' | 'blob'> {
  return { ok: true, blob: async () => blob }
}

describe('persistKnowledgeImage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mockedPostForm.mockResolvedValue({
      url: 'https://cdn.example.com/custom-field-files/persisted.png',
      name: 'persisted.png',
      size: 12,
      content_type: 'image/png',
    })
  })

  it('uploads an original image when its actual size is within 10MB', async () => {
    mockedGetConversationFileUrl.mockResolvedValue({
      url: 'https://signed.example.com/original.png',
      expires_seconds: 300,
    })
    vi.stubGlobal('fetch', vi.fn(async () => responseWith(
      new Blob(['small'], { type: 'image/png' }),
    )))

    await persistKnowledgeImage({
      conversationId: 20,
      fileId: 'file_123',
      name: 'source.png',
      mimeType: 'image/png',
    })

    expect(mockedGetConversationFileUrl).toHaveBeenCalledOnce()
    expect(mockedGetConversationFileUrl).toHaveBeenCalledWith({
      conversationId: 20,
      fileId: 'file_123',
      downloadName: 'source.png',
    })
    expect(mockedPostForm).toHaveBeenCalledOnce()
  })

  it('tries static WebP profiles until the actual result is within 10MB', async () => {
    mockedGetConversationFileUrl.mockImplementation(async ({ imageProcess }) => ({
      url: `https://signed.example.com/${imageProcess ?? 'original'}`,
      expires_seconds: 300,
    }))
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(responseWith(sizedImageBlob(MAX_KNOWLEDGE_IMAGE_BYTES + 1, 'image/png')))
      .mockResolvedValueOnce(responseWith(sizedImageBlob(MAX_KNOWLEDGE_IMAGE_BYTES + 1, 'image/webp')))
      .mockResolvedValueOnce(responseWith(new Blob(['compressed'], { type: 'image/webp' })))
    vi.stubGlobal('fetch', fetchMock)

    await persistKnowledgeImage({
      conversationId: 20,
      fileId: 'file_123',
      name: 'source.png',
      mimeType: 'image/png',
      size: MAX_KNOWLEDGE_IMAGE_BYTES + 1,
    })

    expect(mockedGetConversationFileUrl).toHaveBeenNthCalledWith(2, expect.objectContaining({
      imageProcess: KNOWLEDGE_STATIC_IMAGE_PROCESS_PROFILES[0],
    }))
    expect(mockedGetConversationFileUrl).toHaveBeenNthCalledWith(3, expect.objectContaining({
      imageProcess: KNOWLEDGE_STATIC_IMAGE_PROCESS_PROFILES[1],
    }))
    const formData = mockedPostForm.mock.calls[0]?.[1] as FormData
    const file = formData.get('file') as File
    expect(file.name).toBe('source.webp')
    expect(file.type).toBe('image/webp')
  })

  it('uses GIF output profiles to preserve animation', async () => {
    mockedGetConversationFileUrl.mockResolvedValue({
      url: 'https://signed.example.com/image.gif',
      expires_seconds: 300,
    })
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(responseWith(sizedImageBlob(MAX_KNOWLEDGE_IMAGE_BYTES + 1, 'image/gif')))
      .mockResolvedValueOnce(responseWith(new Blob(['compressed'], { type: 'image/gif' }))))

    await persistKnowledgeImage({
      conversationId: 20,
      fileId: 'gif_123',
      name: 'animated.gif',
      mimeType: 'image/gif',
    })

    expect(mockedGetConversationFileUrl).toHaveBeenNthCalledWith(2, expect.objectContaining({
      imageProcess: KNOWLEDGE_GIF_IMAGE_PROCESS_PROFILES[0],
    }))
    const formData = mockedPostForm.mock.calls[0]?.[1] as FormData
    const file = formData.get('file') as File
    expect(file.name).toBe('animated.gif')
    expect(file.type).toBe('image/gif')
  })

  it('rejects known sources above the OSS 20MB processing limit before fetching', async () => {
    await expect(persistKnowledgeImage({
      conversationId: 20,
      fileId: 'large_123',
      name: 'large.png',
      mimeType: 'image/png',
      size: MAX_OSS_IMAGE_PROCESS_SOURCE_BYTES + 1,
    })).rejects.toMatchObject<Partial<KnowledgeImageTransferError>>({
      code: 'source_too_large',
    })

    expect(mockedGetConversationFileUrl).not.toHaveBeenCalled()
    expect(mockedPostForm).not.toHaveBeenCalled()
  })

  it('rejects an image when every processed result still exceeds 10MB', async () => {
    mockedGetConversationFileUrl.mockResolvedValue({
      url: 'https://signed.example.com/large.png',
      expires_seconds: 300,
    })
    vi.stubGlobal('fetch', vi.fn(async () => responseWith(
      sizedImageBlob(MAX_KNOWLEDGE_IMAGE_BYTES + 1, 'image/webp'),
    )))

    await expect(persistKnowledgeImage({
      conversationId: 20,
      fileId: 'large_123',
      name: 'large.png',
      mimeType: 'image/png',
    })).rejects.toMatchObject<Partial<KnowledgeImageTransferError>>({
      code: 'output_too_large',
    })

    expect(mockedGetConversationFileUrl).toHaveBeenCalledTimes(4)
    expect(mockedPostForm).not.toHaveBeenCalled()
  })
})

describe('buildKnowledgeImageHtml', () => {
  it('uses only the persistent URL and escapes image attributes', () => {
    const html = buildKnowledgeImageHtml({
      url: 'https://cdn.example.com/image.png?a=1&b=2',
      name: 'a"b.png',
      size: 12,
      content_type: 'image/png',
    })

    expect(html).toContain('src="https://cdn.example.com/image.png?a=1&amp;b=2"')
    expect(html).toContain('alt="a&quot;b.png"')
    expect(html).not.toContain('file_id')
    expect(html).not.toContain('signed')
  })
})
