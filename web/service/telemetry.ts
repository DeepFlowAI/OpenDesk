'use client'

import type {
  TelemetryBatch,
  TelemetryBatchResponse,
  TelemetryCommon,
  TelemetryEvent,
} from '@/models/telemetry'

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')
const SDK_NAME = 'opendesk-web'
const SDK_VERSION = '0.1.0'
const FLUSH_BATCH_SIZE = 20
const FLUSH_IDLE_MS = 5_000
const MAX_PENDING_BATCHES_PER_CHANNEL = 5
const PENDING_KEY_PREFIX = 'opendesk:telemetry:pending:'
const APP_PENDING_KEY_PREFIX = 'opendesk:telemetry:app-pending:'
const DEVICE_ID_KEY = 'opendesk:telemetry:device_id'
const APP_QUEUE_KEY = '__app__'

type StableCommon = Pick<
  TelemetryCommon,
  | 'session_id'
  | 'device_id'
  | 'release'
  | 'user_agent'
  | 'sdk_name'
  | 'sdk_version'
  | 'ts_offset_ms'
>

type TrackInput = Omit<TelemetryEvent, 'name' | 'ts'> & {
  ts?: number
  channel_key?: string | null
}

type AppTrackInput = Omit<TrackInput, 'channel_key'>

export type StreamFinishMetrics = {
  total_duration_ms: number
  chunk_count: number
  avg_chunk_idle_ms: number
  p95_chunk_idle_ms: number
  lag_1s_count: number
}

export type StreamMetricsCollector = {
  recordChunk: () => void
  finish: () => StreamFinishMetrics
}

const isBrowser = () => typeof window !== 'undefined'

function safeUUID(): string {
  if (isBrowser()) {
    const c = window.crypto as Crypto | undefined
    if (c?.randomUUID) return c.randomUUID()
    if (c?.getRandomValues) {
      const bytes = new Uint8Array(16)
      c.getRandomValues(bytes)
      bytes[6] = (bytes[6] & 0x0f) | 0x40
      bytes[8] = (bytes[8] & 0x3f) | 0x80
      const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
    }
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function readPersistentDeviceId(): string {
  if (!isBrowser()) return safeUUID()
  try {
    const existing = window.localStorage.getItem(DEVICE_ID_KEY)
    if (existing) return existing
    const fresh = safeUUID()
    window.localStorage.setItem(DEVICE_ID_KEY, fresh)
    return fresh
  } catch {
    return safeUUID()
  }
}

function readNetworkType(): string | null {
  if (!isBrowser()) return null
  const conn = (navigator as Navigator & {
    connection?: { effectiveType?: string }
  }).connection
  return conn?.effectiveType ?? null
}

function buildStableCommon(): StableCommon {
  return {
    session_id: safeUUID(),
    device_id: readPersistentDeviceId(),
    release: process.env.NEXT_PUBLIC_APP_VERSION || SDK_VERSION,
    user_agent: isBrowser() ? navigator.userAgent : undefined,
    sdk_name: SDK_NAME,
    sdk_version: SDK_VERSION,
    ts_offset_ms: 0,
  }
}

export function createStreamMetrics(): StreamMetricsCollector {
  const startedAt = Date.now()
  let lastChunkAt = startedAt
  let chunkCount = 0
  const idleGapsMs: number[] = []

  return {
    recordChunk() {
      const now = Date.now()
      idleGapsMs.push(now - lastChunkAt)
      lastChunkAt = now
      chunkCount += 1
    },
    finish() {
      const sum = idleGapsMs.reduce((acc, value) => acc + value, 0)
      const sorted = [...idleGapsMs].sort((a, b) => a - b)
      const p95Index = sorted.length === 0
        ? 0
        : Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))
      return {
        total_duration_ms: Date.now() - startedAt,
        chunk_count: chunkCount,
        avg_chunk_idle_ms: idleGapsMs.length ? Math.round(sum / idleGapsMs.length) : 0,
        p95_chunk_idle_ms: sorted.length ? Math.round(sorted[p95Index]) : 0,
        lag_1s_count: idleGapsMs.filter((gap) => gap > 1000).length,
      }
    },
  }
}

class TelemetryClient {
  private readonly stableCommon = buildStableCommon()
  private readonly queues = new Map<string, TelemetryEvent[]>()
  private flushTimer: ReturnType<typeof setTimeout> | null = null
  private flushPromise: Promise<void> | null = null
  private enabled = true
  private initializedListeners = false

  constructor() {
    this.initListenersOnce()
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled
  }

  track(name: string, input: TrackInput = {}): void {
    if (!this.enabled || !isBrowser()) return
    const channelKey = input.channel_key ?? null
    if (!channelKey) return
    this.enqueue(channelKey, name, input)
  }

  trackApp(name: string, input: AppTrackInput = {}): void {
    if (!this.enabled || !isBrowser()) return
    this.enqueue(APP_QUEUE_KEY, name, input)
  }

  async flushApp(): Promise<void> {
    if (!isBrowser()) return
    if (this.flushPromise) return this.flushPromise
    const promise = this.doFlushApp()
    this.flushPromise = promise
    try {
      await promise
    } finally {
      this.flushPromise = null
    }
  }

  private enqueue(queueKey: string, name: string, input: TrackInput | AppTrackInput): void {
    try {
      const event: TelemetryEvent = {
        name,
        ts: input.ts ?? Date.now(),
        level: input.level ?? 'info',
        trace_id: input.trace_id ?? null,
        conversation_external_id: input.conversation_external_id ?? null,
        request_id: input.request_id ?? null,
        client_message_id: input.client_message_id ?? null,
        props: input.props ?? null,
        metrics: input.metrics ?? null,
      }
      const queue = this.queues.get(queueKey) ?? []
      queue.push(event)
      this.queues.set(queueKey, queue)
      if (this.totalQueued() >= FLUSH_BATCH_SIZE) {
        void this.flush()
      } else {
        this.scheduleIdleFlush()
      }
    } catch (error) {
      console.warn('[telemetry] track failed', error)
    }
  }

  async flush(): Promise<void> {
    if (!isBrowser()) return
    if (this.flushPromise) return this.flushPromise
    const promise = this.doFlush()
    this.flushPromise = promise
    try {
      await promise
    } finally {
      this.flushPromise = null
    }
  }

  private buildCommon(): TelemetryCommon {
    return {
      ...this.stableCommon,
      url: isBrowser() ? window.location.href : undefined,
      viewport: isBrowser() ? `${window.innerWidth}x${window.innerHeight}` : undefined,
      network_type: readNetworkType(),
    }
  }

  private async doFlush(): Promise<void> {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer)
      this.flushTimer = null
    }
    await this.replayPersistedBatches()
    await this.replayPersistedAppBatches()
    while (this.totalQueued() > 0) {
      const drained = this.drainQueues()
      const common = this.buildCommon()
      for (const [queueKey, events] of drained) {
        const batch = { common, events }
        if (queueKey === APP_QUEUE_KEY) {
          await this.sendApp(batch, false)
        } else {
          await this.send(queueKey, batch, false)
        }
      }
    }
  }

  private async doFlushApp(): Promise<void> {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer)
      this.flushTimer = null
    }
    await this.replayPersistedAppBatches()
    const queue = this.queues.get(APP_QUEUE_KEY)
    if (!queue?.length) return
    const events = queue.splice(0, queue.length)
    await this.sendApp({ common: this.buildCommon(), events }, false)
  }

  private totalQueued(): number {
    let total = 0
    for (const queue of this.queues.values()) total += queue.length
    return total
  }

  private drainQueues(): Array<[string, TelemetryEvent[]]> {
    const drained: Array<[string, TelemetryEvent[]]> = []
    for (const [channelKey, queue] of this.queues) {
      if (queue.length === 0) continue
      drained.push([channelKey, queue.splice(0, queue.length)])
    }
    return drained
  }

  private scheduleIdleFlush(): void {
    if (this.flushTimer) return
    this.flushTimer = setTimeout(() => {
      this.flushTimer = null
      void this.flush()
    }, FLUSH_IDLE_MS)
  }

  private initListenersOnce(): void {
    if (!isBrowser() || this.initializedListeners) return
    this.initializedListeners = true
    const finalFlush = () => this.flushOnUnload()
    window.addEventListener('pagehide', finalFlush)
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') finalFlush()
    })
  }

  private flushOnUnload(): void {
    if (this.totalQueued() === 0) return
    const common = this.buildCommon()
    for (const [queueKey, events] of this.drainQueues()) {
      const batch = { common, events }
      if (queueKey === APP_QUEUE_KEY) {
        void this.sendApp(batch, true)
      } else {
        void this.send(queueKey, batch, true)
      }
    }
  }

  private endpointFor(channelKey: string): string {
    return `${API_BASE}/v1/public/channels/${encodeURIComponent(channelKey)}/telemetry/events`
  }

  private appEndpoint(): string {
    return `${API_BASE}/v1/telemetry/events`
  }

  private authHeaders(): Record<string, string> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (!isBrowser()) return headers
    const token = window.localStorage.getItem('auth_token')
    if (token) headers.Authorization = `Bearer ${token}`
    return headers
  }

  private isStatusRetryable(status: number): boolean {
    return status === 408 || status === 429 || status >= 500
  }

  private async send(channelKey: string, batch: TelemetryBatch, useBeacon: boolean): Promise<void> {
    const url = this.endpointFor(channelKey)
    const body = JSON.stringify(batch)

    if (useBeacon && typeof navigator !== 'undefined' && navigator.sendBeacon) {
      try {
        const ok = navigator.sendBeacon(url, new Blob([body], { type: 'application/json' }))
        if (ok) return
      } catch {
        // Fall through to fetch.
      }
    }

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        keepalive: true,
      })
      if (!response.ok) {
        if (this.isStatusRetryable(response.status)) {
          this.stash(channelKey, batch)
        }
        return
      }
      try {
        const data = await response.json() as TelemetryBatchResponse
        if (data.dropped > 0) {
          console.warn('[telemetry] backend dropped %d events', data.dropped)
        }
      } catch {
        // Successful POST is enough.
      }
    } catch {
      this.stash(channelKey, batch)
    }
  }

  private async sendApp(batch: TelemetryBatch, _useBeacon: boolean): Promise<void> {
    const url = this.appEndpoint()
    const body = JSON.stringify(batch)

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: this.authHeaders(),
        body,
        keepalive: true,
      })
      if (!response.ok) {
        if (this.isStatusRetryable(response.status)) {
          this.stashApp(batch)
        }
        return
      }
      try {
        const data = await response.json() as TelemetryBatchResponse
        if (data.dropped > 0) {
          console.warn('[telemetry] backend dropped %d app events', data.dropped)
        }
      } catch {
        // Successful POST is enough.
      }
    } catch {
      this.stashApp(batch)
    }
  }

  private pendingKey(channelKey: string): string {
    const rand = Math.random().toString(36).slice(2, 6)
    return `${PENDING_KEY_PREFIX}${channelKey}:${Date.now()}-${rand}`
  }

  private parsePendingKey(key: string): { channelKey: string } | null {
    if (!key.startsWith(PENDING_KEY_PREFIX)) return null
    const rest = key.slice(PENDING_KEY_PREFIX.length)
    const separator = rest.indexOf(':')
    if (separator <= 0) return null
    return { channelKey: rest.slice(0, separator) }
  }

  private stash(channelKey: string, batch: TelemetryBatch): void {
    try {
      window.localStorage.setItem(this.pendingKey(channelKey), JSON.stringify(batch))
      this.trimPending(channelKey)
    } catch {
      // Best effort only.
    }
  }

  private stashApp(batch: TelemetryBatch): void {
    try {
      const key = `${APP_PENDING_KEY_PREFIX}${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
      window.localStorage.setItem(key, JSON.stringify(batch))
      this.trimAppPending()
    } catch {
      // Best effort only.
    }
  }

  private trimPending(channelKey: string): void {
    const keys = this.pendingKeys()
      .filter((key) => this.parsePendingKey(key)?.channelKey === channelKey)
      .sort()
    while (keys.length > MAX_PENDING_BATCHES_PER_CHANNEL) {
      const key = keys.shift()
      if (key) window.localStorage.removeItem(key)
    }
  }

  private trimAppPending(): void {
    const keys = this.appPendingKeys().sort()
    while (keys.length > MAX_PENDING_BATCHES_PER_CHANNEL) {
      const key = keys.shift()
      if (key) window.localStorage.removeItem(key)
    }
  }

  private pendingKeys(): string[] {
    const keys: string[] = []
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const key = window.localStorage.key(i)
      if (key?.startsWith(PENDING_KEY_PREFIX)) keys.push(key)
    }
    return keys
  }

  private appPendingKeys(): string[] {
    const keys: string[] = []
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const key = window.localStorage.key(i)
      if (key?.startsWith(APP_PENDING_KEY_PREFIX)) keys.push(key)
    }
    return keys
  }

  private async replayPersistedBatches(): Promise<void> {
    for (const key of this.pendingKeys().sort()) {
      const parsed = this.parsePendingKey(key)
      if (!parsed) continue
      try {
        const raw = window.localStorage.getItem(key)
        if (!raw) continue
        const batch = JSON.parse(raw) as TelemetryBatch
        window.localStorage.removeItem(key)
        await this.send(parsed.channelKey, batch, false)
      } catch {
        window.localStorage.removeItem(key)
      }
    }
  }

  private async replayPersistedAppBatches(): Promise<void> {
    for (const key of this.appPendingKeys().sort()) {
      try {
        const raw = window.localStorage.getItem(key)
        if (!raw) continue
        const batch = JSON.parse(raw) as TelemetryBatch
        window.localStorage.removeItem(key)
        await this.sendApp(batch, false)
      } catch {
        window.localStorage.removeItem(key)
      }
    }
  }
}

export const telemetry = new TelemetryClient()
