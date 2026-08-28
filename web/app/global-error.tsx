'use client'

import { useEffect } from 'react'
import { isChunkLoadError, reloadOnceOnChunkError } from '@/lib/chunk-load-error'
import { reportClientError } from '@/utils/report-client-error'

/**
 * Replaces the framework's built-in "Application error" screen when a render
 * throws with no boundary above it. It reports the error before showing the
 * fallback, and renders its own document because the root layout is gone.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    if (isChunkLoadError(error) && reloadOnceOnChunkError()) return
    void reportClientError('app_render_crashed', error, { digest: error.digest })
  }, [error])

  return (
    <html lang="zh-CN">
      <body
        style={{
          margin: 0,
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
          backgroundColor: '#fafafa',
          color: '#18181b',
          fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
        }}
      >
        <div style={{ maxWidth: '420px', textAlign: 'center' }}>
          <h1 style={{ margin: '0 0 8px', fontSize: '18px', fontWeight: 600 }}>页面出错了</h1>
          <p style={{ margin: '0 0 20px', fontSize: '14px', lineHeight: 1.6, color: '#71717a' }}>
            问题已自动上报，你可以重试或刷新页面。
          </p>
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
            <button
              type="button"
              onClick={reset}
              style={{
                padding: '8px 20px',
                fontSize: '14px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: '#18181b',
                color: '#ffffff',
                cursor: 'pointer',
              }}
            >
              重试
            </button>
            <button
              type="button"
              onClick={() => window.location.reload()}
              style={{
                padding: '8px 20px',
                fontSize: '14px',
                borderRadius: '6px',
                border: '1px solid #d4d4d8',
                backgroundColor: '#ffffff',
                color: '#18181b',
                cursor: 'pointer',
              }}
            >
              刷新页面
            </button>
          </div>
        </div>
      </body>
    </html>
  )
}
