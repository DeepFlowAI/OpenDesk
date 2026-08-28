'use client'

import { useEffect, useRef, useState } from 'react'
import { IconFile } from '@tabler/icons-react'

type JitDocumentViewerProps = {
  url: string
  filename: string
}

/** Office / text document preview via the same jit-viewer used in chat. */
export function JitDocumentViewer({ url, filename }: JitDocumentViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const viewerRef = useRef<{ destroy: () => void } | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function mountViewer() {
      if (!containerRef.current) return

      try {
        setError(false)
        const { createViewer } = await import('jit-viewer')
        if (cancelled || !containerRef.current) return

        const viewer = createViewer({
          target: containerRef.current,
          file: url,
          filename,
          toolbar: true,
          width: '100%',
          height: '100%',
          locale: 'zh-CN',
          theme: 'light',
          onError: () => setError(true),
        })

        viewerRef.current = viewer
        await viewer.mount()
      } catch {
        if (!cancelled) setError(true)
      }
    }

    void mountViewer()

    return () => {
      cancelled = true
      viewerRef.current?.destroy()
      viewerRef.current = null
    }
  }, [url, filename])

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <IconFile size={36} className="text-muted-foreground" />
        <div className="text-sm font-medium">该文件暂时无法在线预览</div>
        <div className="max-w-md text-xs text-muted-foreground">请下载文件后查看。</div>
      </div>
    )
  }

  return <div ref={containerRef} className="h-full w-full" />
}
