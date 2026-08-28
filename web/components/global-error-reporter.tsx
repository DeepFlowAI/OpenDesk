'use client'

import { useEffect } from 'react'
import { reportClientError } from '@/utils/report-client-error'

/**
 * Reports uncaught errors and unhandled promise rejections so client-side
 * failures show up in server-side logs instead of only the user's console.
 * Mounted at the root so it covers every route. Renders nothing.
 */
export function GlobalErrorReporter() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      void reportClientError('app_unhandled_error', event.error ?? event.message, {
        source: event.filename || undefined,
        lineno: event.lineno || undefined,
        colno: event.colno || undefined,
      })
    }
    const onRejection = (event: PromiseRejectionEvent) => {
      void reportClientError('app_unhandled_rejection', event.reason)
    }

    window.addEventListener('error', onError)
    window.addEventListener('unhandledrejection', onRejection)
    return () => {
      window.removeEventListener('error', onError)
      window.removeEventListener('unhandledrejection', onRejection)
    }
  }, [])

  return null
}
