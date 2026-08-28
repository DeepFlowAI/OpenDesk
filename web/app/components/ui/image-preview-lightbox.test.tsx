import { act, createElement, type HTMLAttributes } from 'react'
import { createRoot } from 'react-dom/client'
import { describe, expect, it, vi } from 'vitest'

import { ImagePreviewLightbox } from '@/app/components/ui/image-preview-lightbox'

vi.mock('yet-another-react-lightbox', async () => {
  const { createElement: createReactElement } = await import('react')
  const { createPortal } = await import('react-dom')

  type MockLightboxProps = {
    open?: boolean
    portal?: { container?: HTMLAttributes<HTMLDivElement> }
    slides?: readonly { src: string; alt?: string }[]
  }

  return {
    default: ({ open, portal, slides = [] }: MockLightboxProps) => {
      if (!open) return null
      const slide = slides[0]
      return createPortal(
        createReactElement(
          'div',
          { ...portal?.container, 'data-testid': 'lightbox-portal' },
          slide ? createReactElement('img', { src: slide.src, alt: slide.alt ?? '' }) : null,
        ),
        document.body,
      )
    },
    isImageSlide: (slide: unknown) => Boolean(slide && typeof slide === 'object' && 'src' in slide),
    useLightboxState: () => ({ currentIndex: 0, slides: [] }),
  }
})

vi.mock('yet-another-react-lightbox/plugins/zoom', () => ({ default: () => undefined }))
vi.mock('yet-another-react-lightbox/plugins/thumbnails', () => ({ default: () => undefined }))

describe('ImagePreviewLightbox context menu', () => {
  it('keeps the native image menu without bubbling into the parent message menu', async () => {
    const parentContextMenu = vi.fn()
    const lightboxContextMenu = vi.fn()
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    await act(async () => {
      root.render(createElement(
        'div',
        {
          onContextMenu: (event) => {
            parentContextMenu()
            event.preventDefault()
          },
        },
        createElement(ImagePreviewLightbox, {
          open: true,
          close: vi.fn(),
          slides: [{ src: 'https://example.com/image.png', alt: 'preview' }],
          portal: { container: { onContextMenu: lightboxContextMenu } },
        }),
      ))
    })

    const image = document.querySelector<HTMLImageElement>('[data-testid="lightbox-portal"] img')
    expect(image).not.toBeNull()

    const event = new MouseEvent('contextmenu', { bubbles: true, cancelable: true })
    await act(async () => {
      image?.dispatchEvent(event)
    })

    expect(lightboxContextMenu).toHaveBeenCalledOnce()
    expect(parentContextMenu).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)

    await act(async () => root.unmount())
    container.remove()
  })
})
