'use client'

import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import Lightbox, {
  type LightboxExternalProps,
  type Plugin,
  type RenderSlideContainerProps,
  type Slide,
  isImageSlide,
  useLightboxState,
} from 'yet-another-react-lightbox'
import Zoom from 'yet-another-react-lightbox/plugins/zoom'
import Thumbnails from 'yet-another-react-lightbox/plugins/thumbnails'
import { IconRotate2, IconRotateClockwise2 } from '@tabler/icons-react'

// Larger default so vertical phone screenshots stay readable next to session notes.
const WINDOWED_PREVIEW_WIDTH = 840
const WINDOWED_PREVIEW_HEIGHT = 740
const WINDOWED_PREVIEW_MARGIN = 16

type ImagePreviewLightboxProps = LightboxExternalProps

type WindowedPreviewPosition = {
  x: number
  y: number
}

function getWindowedPreviewSize() {
  if (typeof window === 'undefined') {
    return {
      width: WINDOWED_PREVIEW_WIDTH,
      height: WINDOWED_PREVIEW_HEIGHT,
    }
  }

  return {
    width: Math.min(WINDOWED_PREVIEW_WIDTH, Math.max(320, window.innerWidth - WINDOWED_PREVIEW_MARGIN * 2)),
    height: Math.min(WINDOWED_PREVIEW_HEIGHT, Math.max(260, window.innerHeight - WINDOWED_PREVIEW_MARGIN * 2)),
  }
}

function clampWindowedPreviewPosition(position: WindowedPreviewPosition): WindowedPreviewPosition {
  if (typeof window === 'undefined') {
    return position
  }

  const { width, height } = getWindowedPreviewSize()
  const maxX = Math.max(WINDOWED_PREVIEW_MARGIN, window.innerWidth - width - WINDOWED_PREVIEW_MARGIN)
  const maxY = Math.max(WINDOWED_PREVIEW_MARGIN, window.innerHeight - height - WINDOWED_PREVIEW_MARGIN)

  return {
    x: Math.min(Math.max(WINDOWED_PREVIEW_MARGIN, position.x), maxX),
    y: Math.min(Math.max(WINDOWED_PREVIEW_MARGIN, position.y), maxY),
  }
}

function getCenteredWindowedPreviewPosition(): WindowedPreviewPosition {
  if (typeof window === 'undefined') {
    return { x: WINDOWED_PREVIEW_MARGIN, y: WINDOWED_PREVIEW_MARGIN }
  }

  const { width, height } = getWindowedPreviewSize()
  return clampWindowedPreviewPosition({
    x: (window.innerWidth - width) / 2,
    y: (window.innerHeight - height) / 2,
  })
}

function WindowModeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M5 5h14v14H5z" />
      <path d="M9 9h6v6H9z" />
    </svg>
  )
}

function RestoreWindowIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M8 4h12v12H8z" />
      <path d="M4 8v12h12" />
    </svg>
  )
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  )
}

function ChevronIcon({ className, direction }: { className?: string; direction: 'left' | 'right' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d={direction === 'left' ? 'm15 6-6 6 6 6' : 'm9 6 6 6-6 6'} />
    </svg>
  )
}

function WindowedPreviewToolbarButton({ onOpen }: { onOpen: (slideIndex: number) => void }) {
  const { currentIndex } = useLightboxState()

  return (
    <button
      type="button"
      className="yarl__button"
      title="窗口缩小"
      aria-label="窗口缩小"
      onClick={() => onOpen(currentIndex)}
    >
      <WindowModeIcon className="yarl__icon" />
    </button>
  )
}

function createWindowedPreviewPlugin(onOpen: (slideIndex: number) => void): Plugin {
  return ({ augment }) => {
    augment(({ toolbar, ...restProps }) => ({
      ...restProps,
      toolbar: {
        ...toolbar,
        buttons: [<WindowedPreviewToolbarButton key="windowed-preview" onOpen={onOpen} />, ...toolbar.buttons],
      },
    }))
  }
}

function RotateToolbarButton({
  delta,
  onRotate,
}: {
  delta: number
  onRotate: (slideIndex: number, delta: number) => void
}) {
  const { currentIndex } = useLightboxState()
  const label = delta < 0 ? '向左旋转' : '向右旋转'
  return (
    <button
      type="button"
      className="yarl__button"
      title={label}
      aria-label={label}
      onClick={() => onRotate(currentIndex, delta)}
    >
      {delta < 0 ? (
        <IconRotate2 className="yarl__icon" stroke={1.5} />
      ) : (
        <IconRotateClockwise2 className="yarl__icon" stroke={1.5} />
      )}
    </button>
  )
}

function RotatingSlideContainer({
  slide,
  children,
  rotations,
}: {
  slide: Slide
  children: React.ReactNode
  rotations: Record<number, number>
}) {
  const { slides } = useLightboxState()
  const idx = slides.indexOf(slide)
  const deg = idx >= 0 ? (rotations[idx] ?? 0) : 0
  if (deg === 0) {
    return children
  }
  return (
    <div
      className="yarl__flex_center yarl__fullsize"
      style={{ transform: `rotate(${deg}deg)`, transition: 'transform 0.2s ease' }}
    >
      {children}
    </div>
  )
}

function WindowedImagePreview({
  slides,
  index,
  onIndexChange,
  onRestore,
  onClose,
}: {
  slides: readonly Slide[]
  index: number
  onIndexChange: (index: number) => void
  onRestore: () => void
  onClose: () => void
}) {
  const [position, setPosition] = useState<WindowedPreviewPosition>(getCenteredWindowedPreviewPosition)
  const dragOffsetRef = useRef<WindowedPreviewPosition | null>(null)

  useEffect(() => {
    const handleResize = () => setPosition((prev) => clampWindowedPreviewPosition(prev))
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const currentSlide = slides[index]
  const currentImage = currentSlide && isImageSlide(currentSlide) ? currentSlide : null
  const canGoPrev = index > 0
  const canGoNext = index < slides.length - 1
  const previewSize = getWindowedPreviewSize()

  const handleDragStart = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    dragOffsetRef.current = {
      x: event.clientX - position.x,
      y: event.clientY - position.y,
    }
  }

  const handleDragMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragOffsetRef.current) {
      return
    }

    setPosition(
      clampWindowedPreviewPosition({
        x: event.clientX - dragOffsetRef.current.x,
        y: event.clientY - dragOffsetRef.current.y,
      }),
    )
  }

  const handleDragEnd = () => {
    dragOffsetRef.current = null
  }

  if (!currentImage) {
    return null
  }

  return (
    <div
      className="fixed z-[9999] overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-2xl"
      style={{
        left: position.x,
        top: position.y,
        width: previewSize.width,
        height: previewSize.height,
      }}
    >
      <div
        className="flex h-10 cursor-move items-center justify-between border-b border-zinc-200 bg-white px-3 text-xs text-zinc-700"
        onPointerDown={handleDragStart}
        onPointerMove={handleDragMove}
        onPointerUp={handleDragEnd}
        onPointerCancel={handleDragEnd}
      >
        <span className="select-none">图片小窗</span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="inline-flex h-7 w-7 items-center justify-center rounded text-zinc-600 hover:bg-zinc-100 hover:text-zinc-950"
            title="还原预览"
            aria-label="还原预览"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={onRestore}
          >
            <RestoreWindowIcon className="h-5 w-5" />
          </button>
          <button
            type="button"
            className="inline-flex h-7 w-7 items-center justify-center rounded text-zinc-600 hover:bg-zinc-100 hover:text-zinc-950"
            title="关闭预览"
            aria-label="关闭预览"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={onClose}
          >
            <CloseIcon className="h-5 w-5" />
          </button>
        </div>
      </div>

      <div className="relative flex h-[calc(100%-2.5rem)] items-center justify-center bg-white">
        {canGoPrev && (
          <button
            type="button"
            className="absolute left-2 top-1/2 z-10 inline-flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-zinc-200 bg-white/90 text-zinc-700 shadow-sm hover:bg-zinc-100 hover:text-zinc-950"
            aria-label="上一张"
            onClick={() => onIndexChange(index - 1)}
          >
            <ChevronIcon className="h-6 w-6" direction="left" />
          </button>
        )}
        <img src={currentImage.src} alt={currentImage.alt ?? 'preview'} className="max-h-full max-w-full object-contain" />
        {canGoNext && (
          <button
            type="button"
            className="absolute right-2 top-1/2 z-10 inline-flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-zinc-200 bg-white/90 text-zinc-700 shadow-sm hover:bg-zinc-100 hover:text-zinc-950"
            aria-label="下一张"
            onClick={() => onIndexChange(index + 1)}
          >
            <ChevronIcon className="h-6 w-6" direction="right" />
          </button>
        )}
      </div>
    </div>
  )
}

export function ImagePreviewLightbox(props: ImagePreviewLightboxProps) {
  const [rotations, setRotations] = useState<Record<number, number>>({})
  const [windowed, setWindowed] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(props.index ?? 0)

  const bumpRotation = useCallback((slideIndex: number, delta: number) => {
    setRotations((prev) => ({
      ...prev,
      [slideIndex]: ((prev[slideIndex] ?? 0) + delta + 360) % 360,
    }))
  }, [])

  const clearRotations = useCallback(() => setRotations({}), [])
  const openWindowedPreview = useCallback((slideIndex: number) => {
    setCurrentIndex(slideIndex)
    setWindowed(true)
  }, [])

  const {
    plugins: userPlugins,
    render: userRender,
    toolbar: userToolbar,
    zoom: userZoom,
    thumbnails: userThumbnails,
    styles: userStyles,
    on: userOn,
    open,
    close,
    slides = [],
    index,
    ...rest
  } = props

  useEffect(() => {
    setCurrentIndex(index ?? 0)
    if (!open) {
      setWindowed(false)
    }
  }, [index, open])

  const plugins = useMemo(
    () => [Zoom, createWindowedPreviewPlugin(openWindowedPreview), Thumbnails, ...(userPlugins ?? [])],
    [openWindowedPreview, userPlugins],
  )

  const render = useMemo(
    () => ({
      ...userRender,
      slideContainer: (props: RenderSlideContainerProps) => {
        const { slide, children } = props
        const inner = userRender?.slideContainer?.(props) ?? children
        return (
          <RotatingSlideContainer slide={slide} rotations={rotations}>
            {inner}
          </RotatingSlideContainer>
        )
      },
    }),
    [userRender, rotations],
  )

  const toolbar = useMemo(
    () => ({
      ...userToolbar,
      buttons: [
        <RotateToolbarButton key="preview-rot-ccw" delta={-90} onRotate={bumpRotation} />,
        <RotateToolbarButton key="preview-rot-cw" delta={90} onRotate={bumpRotation} />,
        ...(userToolbar?.buttons ?? ['close']),
      ],
    }),
    [bumpRotation, userToolbar],
  )

  const styles = useMemo(
    () => ({
      ...userStyles,
      root: {
        '--yarl__color_backdrop': '#ffffff',
        '--yarl__color_button': 'rgba(24, 24, 27, 0.72)',
        '--yarl__color_button_active': '#18181b',
        '--yarl__color_button_disabled': 'rgba(24, 24, 27, 0.28)',
        '--yarl__button_filter': 'none',
        '--yarl__container_background_color': '#ffffff',
        '--yarl__slide_icon_loading_color': 'rgba(24, 24, 27, 0.48)',
        '--yarl__thumbnails_container_background_color': '#ffffff',
        '--yarl__thumbnails_thumbnail_background': '#ffffff',
        '--yarl__thumbnails_thumbnail_border_color': '#d4d4d8',
        '--yarl__thumbnails_thumbnail_active_border_color': '#18181b',
        '--yarl__thumbnails_thumbnail_focus_box_shadow': '#ffffff 0 0 0 2px, #18181b 0 0 0 4px',
        ...userStyles?.root,
      },
      container: {
        backgroundColor: '#ffffff',
        ...userStyles?.container,
      },
      button: {
        filter: 'none',
        ...userStyles?.button,
      },
    }),
    [userStyles],
  )

  const on = useMemo(
    () => ({
      ...userOn,
      view: ({ index }: { index: number }) => {
        setCurrentIndex(index)
        userOn?.view?.({ index })
      },
      exited: () => {
        setWindowed(false)
        clearRotations()
        userOn?.exited?.()
      },
    }),
    [clearRotations, userOn],
  )

  if (open && windowed) {
    return (
      <WindowedImagePreview
        slides={slides}
        index={currentIndex}
        onIndexChange={setCurrentIndex}
        onRestore={() => setWindowed(false)}
        onClose={() => close?.()}
      />
    )
  }

  return (
    <Lightbox
      {...rest}
      open={open}
      close={close}
      slides={slides}
      index={currentIndex}
      plugins={plugins}
      zoom={{
        scrollToZoom: true,
        // Default maxZoomPixelRatio is 1: when the image fits the viewport at native resolution,
        // computed maxZoom stays 1 so toolbar zoom (+/−) does nothing. Allow modest digital zoom.
        maxZoomPixelRatio: 3,
        ...userZoom,
      }}
      thumbnails={{ showToggle: true, ...userThumbnails }}
      render={render}
      toolbar={toolbar}
      styles={styles}
      on={on}
    />
  )
}
