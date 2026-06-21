'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  IconAntennaBars1,
  IconAntennaBars3,
  IconAntennaBars5,
  IconAntennaBarsOff,
} from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'

type NetworkStatus = 'checking' | 'good' | 'slow' | 'bad'

const PING_INTERVAL_MS = 30_000
const PING_TIMEOUT_MS = 6_000
const SLOW_THRESHOLD_MS = 800
const BAD_THRESHOLD_MS = 1_800

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ''

function healthUrl(): string {
  const base = API_BASE.trim().replace(/\/+$/, '')
  return base ? `${base}/v1/health` : '/api/v1/health'
}

function statusForLatency(latencyMs: number): NetworkStatus {
  if (latencyMs <= SLOW_THRESHOLD_MS) return 'good'
  if (latencyMs <= BAD_THRESHOLD_MS) return 'slow'
  return 'bad'
}

export function NetworkMonitor() {
  const { locale } = useLocaleStore()
  const [status, setStatus] = useState<NetworkStatus>('checking')
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [checking, setChecking] = useState(false)
  const requestRef = useRef<AbortController | null>(null)

  const checkNetwork = useCallback(async () => {
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller
    const timeoutId = window.setTimeout(() => controller.abort(), PING_TIMEOUT_MS)
    const startedAt = performance.now()

    setChecking(true)

    try {
      const response = await fetch(healthUrl(), {
        cache: 'no-store',
        signal: controller.signal,
      })
      const elapsed = Math.round(performance.now() - startedAt)

      if (!response.ok) {
        if (requestRef.current === controller) {
          setStatus('bad')
          setLatencyMs(null)
        }
        return
      }

      if (requestRef.current === controller) {
        setStatus(statusForLatency(elapsed))
        setLatencyMs(elapsed)
      }
    } catch {
      if (requestRef.current === controller) {
        setStatus('bad')
        setLatencyMs(null)
      }
    } finally {
      window.clearTimeout(timeoutId)
      if (requestRef.current === controller) {
        requestRef.current = null
        setChecking(false)
      }
    }
  }, [])

  useEffect(() => {
    void checkNetwork()
    const intervalId = window.setInterval(() => {
      void checkNetwork()
    }, PING_INTERVAL_MS)

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void checkNetwork()
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      window.clearInterval(intervalId)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      requestRef.current?.abort()
      requestRef.current = null
    }
  }, [checkNetwork])

  const display = useMemo(() => {
    if (status === 'good') {
      return {
        Icon: IconAntennaBars5,
        className: 'text-[#16A34A]',
        label: t('ws.network.good', locale, { latency: latencyMs ?? '-' }),
      }
    }
    if (status === 'slow') {
      return {
        Icon: IconAntennaBars3,
        className: 'text-[#D97706]',
        label: t('ws.network.slow', locale, { latency: latencyMs ?? '-' }),
      }
    }
    if (status === 'bad') {
      return {
        Icon: IconAntennaBarsOff,
        className: 'text-[#DC2626]',
        label: t('ws.network.bad', locale),
      }
    }
    return {
      Icon: IconAntennaBars1,
      className: 'text-[#999999]',
      label: t('ws.network.checking', locale),
    }
  }, [latencyMs, locale, status])

  const title =
    latencyMs == null ? display.label : t('ws.network.response', locale, { latency: latencyMs })
  const Icon = display.Icon

  return (
    <button
      type="button"
      onClick={() => void checkNetwork()}
      className={cn(
        'group relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors hover:bg-[#F5F5F5]',
        display.className,
        checking && 'animate-pulse',
      )}
      aria-label={title}
    >
      <Icon size={22} stroke={2.4} />
      <span className="sr-only">{display.label}</span>
      <span className="pointer-events-none absolute left-1/2 top-full z-50 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md bg-foreground px-2.5 py-1.5 text-xs text-background opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
        {title}
      </span>
    </button>
  )
}
