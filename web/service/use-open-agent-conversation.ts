import type { Message } from '@/models/conversation'

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

const ROUND_EVENT_ID_RE = /^r\d+-e\d+$/
const DEFAULT_FIRST_CHUNK_TIMEOUT_MS = 35_000
const DEFAULT_CHUNK_IDLE_TIMEOUT_MS = 15_000
const DEFAULT_OVERALL_TIMEOUT_MS = 240_000
const HARD_OVERALL_TIMEOUT_CAP_MS = 300_000
const DEFAULT_RETRY = { maxRetries: 2, baseDelayMs: 1000 }
const JITTER_RATIO = 0.2

export type HumanHandoffEventPayload = {
  event_kind: 'human_handoff'
  schema_version: 1
  handoff_source?: 'bot_tool' | 'bot_event' | 'visitor'
  tool_call_id?: string
  related_tool_call_step_id?: number
  conversation?: {
    id?: number
    external_id?: string | null
  }
  tenant_id?: string
  agent_id?: number
  requested_at?: string
  handoff: {
    brief?: string
    reason?: string
    agent_group_id?: string
    agent_id?: string
    business_type?: string
    urgency?: 'normal' | 'high'
    user_message?: string
  }
}

export type OpenAgentToolCallPayload = Record<string, unknown> & {
  step_id?: number
  tool_name?: string
  name?: string
  brief?: string
  tool_call_id?: string
  call_id?: string
  id?: string
  arguments?: unknown
  args?: unknown
}

export type OpenAgentToolResultPayload = Record<string, unknown> & {
  tool_call_id?: string
  call_id?: string
  id?: string
  result?: unknown
  tool_name?: string
}

export type OpenAgentThinkingDeltaPayload = Record<string, unknown> & {
  content?: string
  delta?: string
  text?: string
}

export type OpenAgentLlmStepPayload = Record<string, unknown> & {
  step_id?: number
}

type WatchdogConfig = {
  first_chunk_ms: number
  chunk_idle_ms: number
  overall_ms: number
}

type OpenAgentSseHandlers = {
  onConversationCreated?: (data: Record<string, unknown>) => void
  onRoundStart?: (data: Record<string, unknown>) => void
  onLlmStepCreated?: (data: OpenAgentLlmStepPayload) => void
  onThinkingDelta?: (data: OpenAgentThinkingDeltaPayload) => void
  onContentDelta?: (text: string, data: Record<string, unknown>) => void
  onToolCall?: (data: OpenAgentToolCallPayload) => void
  onToolResult?: (data: OpenAgentToolResultPayload) => void
  onHumanHandoff?: (data: HumanHandoffEventPayload) => void
  onMessageSaved?: (message: Message) => void
  onHandoffUpdated?: (data: Record<string, unknown>) => void
  onConversationStatus?: (data: Record<string, unknown>) => void
  onDone?: (data: Record<string, unknown>) => void
  onAssistantReset?: (data: Record<string, unknown>) => void
  onRetry?: (attempt: number, maxAttempts: number) => void
  onError?: (message: string) => void
}

type RetryOptions = {
  maxRetries?: number
  baseDelayMs?: number
}

type StreamOpenAgentConversationParams = {
  conversationPublicId: string
  visitorSessionToken: string
  message: string
  quotedMessageId?: number
  clientMessageId?: string
  requestId?: string
  lastEventId?: string | null
  resume?: boolean
  signal?: AbortSignal
  retry?: RetryOptions
  handlers?: OpenAgentSseHandlers
}

export type SubmitOpenAgentFeedbackParams = {
  conversationPublicId: string
  visitorSessionToken: string
  messageId: number
  stepId: number
  rating: 'like' | 'dislike'
  comment?: string | null
}

export type SubmitOpenAgentFeedbackResponse = {
  message: Message
  step_id: number
  rating: 'like' | 'dislike'
  comment?: string | null
  updated_at?: string | null
}

export type OpenAgentStreamSnapshot = {
  requestId: string
  clientMessageId: string
  lastEventId: string | null
}

export type OpenAgentStreamController = AbortController & {
  completion: Promise<void>
  requestId: string
  clientMessageId: string
  getSnapshot: () => OpenAgentStreamSnapshot
  detach: () => OpenAgentStreamSnapshot
}

export async function submitOpenAgentFeedback({
  conversationPublicId,
  visitorSessionToken,
  messageId,
  stepId,
  rating,
  comment,
}: SubmitOpenAgentFeedbackParams): Promise<SubmitOpenAgentFeedbackResponse> {
  const response = await fetch(
    `${API_BASE}/v1/public/conversations/${conversationPublicId}/open-agent/feedback`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${visitorSessionToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message_id: messageId,
        step_id: stepId,
        rating,
        comment: rating === 'dislike' ? comment ?? null : null,
      }),
    },
  )

  if (!response.ok) {
    let message = 'OpenAgent feedback failed'
    try {
      const payload = await response.json() as { detail?: unknown; message?: unknown }
      if (typeof payload.detail === 'string') message = payload.detail
      else if (typeof payload.message === 'string') message = payload.message
    } catch {
      // Keep the generic error when the server response is not JSON.
    }
    throw new Error(message)
  }

  return await response.json() as SubmitOpenAgentFeedbackResponse
}

type RetryState = {
  requestId: string
  clientMessageId: string
  lastEventId: string | null
  resume: boolean
  isRetry: boolean
}

type StreamState = {
  lastChunkAt: number
  firstChunkReceived: boolean
  watchdogAbort: (() => void) | null
  watchdog: WatchdogConfig
}

function generateRequestId(): string {
  return `req_${Math.random().toString(36).slice(2, 11)}`
}

function generateClientMessageId(): string {
  const c = (typeof crypto !== 'undefined' ? crypto : null) as Crypto | null
  if (c && typeof c.randomUUID === 'function') {
    return c.randomUUID()
  }
  const bytes = new Uint8Array(16)
  if (c && typeof c.getRandomValues === 'function') {
    c.getRandomValues(bytes)
  } else {
    for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256)
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

function attachControllerSnapshot(controller: OpenAgentStreamController, state: RetryState) {
  controller.getSnapshot = () => ({
    requestId: state.requestId,
    clientMessageId: state.clientMessageId,
    lastEventId: state.lastEventId,
  })
  controller.detach = () => {
    const snapshot = controller.getSnapshot()
    controller.abort()
    return snapshot
  }
}

function getString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isHumanHandoffPayload(
  data: Record<string, unknown> | null,
): data is Record<string, unknown> & HumanHandoffEventPayload {
  return Boolean(
    data
      && data.event_kind === 'human_handoff'
      && data.handoff
      && typeof data.handoff === 'object',
  )
}

export function isHumanHandoffEventPayload(value: unknown): value is HumanHandoffEventPayload {
  return isHumanHandoffPayload(isPlainRecord(value) ? value : null)
}

function dispatchSseEvent(
  event: string,
  data: Record<string, unknown> | null,
  handlers?: OpenAgentSseHandlers,
) {
  if (event === 'conversation_created' && data) {
    handlers?.onConversationCreated?.(data)
    return
  }
  if (event === 'round_start' && data) {
    handlers?.onRoundStart?.(data)
    return
  }
  if (event === 'llm_step_created' && data) {
    handlers?.onLlmStepCreated?.(data as OpenAgentLlmStepPayload)
    return
  }
  if ((event === 'thinking_delta' || event === 'thinking') && data) {
    handlers?.onThinkingDelta?.(data as OpenAgentThinkingDeltaPayload)
    return
  }
  if ((event === 'content_delta' || event === 'content') && data) {
    handlers?.onContentDelta?.(
      getString(data.content) || getString(data.delta) || getString(data.text),
      data,
    )
    return
  }
  if (event === 'tool_call' && data) {
    handlers?.onToolCall?.(data as OpenAgentToolCallPayload)
    return
  }
  if (event === 'tool_result' && data) {
    handlers?.onToolResult?.(data as OpenAgentToolResultPayload)
    return
  }
  if (event === 'human_handoff_event' && isHumanHandoffPayload(data)) {
    handlers?.onHumanHandoff?.(data)
    return
  }
  if (event === 'open_desk_message_saved' && data) {
    handlers?.onMessageSaved?.(data as Message)
    return
  }
  if (event === 'open_desk_handoff_updated' && data) {
    handlers?.onHandoffUpdated?.(data)
    return
  }
  if (event === 'open_desk_conversation_status' && data) {
    handlers?.onConversationStatus?.(data)
    return
  }
  if (event === 'assistant_reset' && data) {
    handlers?.onAssistantReset?.(data)
    return
  }
  if (event === 'done' && data) {
    handlers?.onDone?.(data)
    return
  }
  if (event === 'error') {
    handlers?.onError?.(getString(data?.message) || 'OpenAgent stream failed')
  }
}

function coerceWatchdog(data: Record<string, unknown> | null): WatchdogConfig | null {
  const raw = data?.watchdog
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const obj = raw as Record<string, unknown>
  const first = Number(obj.first_chunk_ms)
  const idle = Number(obj.chunk_idle_ms)
  const overall = Number(obj.overall_ms)
  if (!Number.isFinite(first) || !Number.isFinite(idle) || !Number.isFinite(overall)) return null
  return {
    first_chunk_ms: Math.max(1000, first),
    chunk_idle_ms: Math.max(1000, idle),
    overall_ms: Math.max(1000, overall),
  }
}

function parseRetryAfter(value: string | null): number | null {
  if (!value) return null
  const seconds = Number(value)
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000)
  const date = Date.parse(value)
  if (Number.isNaN(date)) return null
  return Math.max(0, date - Date.now())
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function waitForRetry(
  attempt: number,
  baseDelayMs: number,
  signal: AbortSignal,
  retryAfterMs?: number | null,
): Promise<void> {
  const exp = Math.min(baseDelayMs * Math.pow(2, attempt - 1), 10_000)
  const baseMs = retryAfterMs != null ? Math.max(exp, retryAfterMs) : exp
  const jittered = baseMs * (1 - JITTER_RATIO + Math.random() * JITTER_RATIO * 2)
  const delay = Math.round(jittered)

  return new Promise<void>((resolve) => {
    if (signal.aborted) {
      resolve()
      return
    }

    let timer: ReturnType<typeof setTimeout> | null = null
    let onlineHandler: (() => void) | null = null
    let abortHandler: (() => void) | null = null

    const cleanup = () => {
      if (timer) clearTimeout(timer)
      if (onlineHandler && typeof window !== 'undefined') window.removeEventListener('online', onlineHandler)
      if (abortHandler) signal.removeEventListener('abort', abortHandler)
    }

    abortHandler = () => {
      cleanup()
      resolve()
    }
    signal.addEventListener('abort', abortHandler, { once: true })

    if (typeof navigator !== 'undefined' && !navigator.onLine && typeof window !== 'undefined') {
      onlineHandler = () => {
        if (timer) clearTimeout(timer)
        timer = setTimeout(() => {
          cleanup()
          resolve()
        }, Math.min(baseDelayMs, 1000))
      }
      window.addEventListener('online', onlineHandler, { once: true })
      timer = setTimeout(() => {
        cleanup()
        resolve()
      }, 30_000)
      return
    }

    timer = setTimeout(() => {
      cleanup()
      resolve()
    }, delay)
  })
}

function readWithIdleTimeout(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  timeoutMs: number,
  onTimeout: () => void,
): Promise<ReadableStreamReadResult<Uint8Array>> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      onTimeout()
      reject(new DOMException('OpenAgent stream idle timeout', 'AbortError'))
    }, timeoutMs)

    reader.read().then(
      (result) => {
        clearTimeout(timer)
        resolve(result)
      },
      (error: unknown) => {
        clearTimeout(timer)
        reject(error)
      },
    )
  })
}

async function fetchSSEWithRetry(
  url: string,
  buildInit: () => RequestInit,
  handlers: OpenAgentSseHandlers | undefined,
  controller: AbortController,
  state: RetryState,
  retryOpts?: RetryOptions,
): Promise<void> {
  const maxRetries = retryOpts?.maxRetries ?? DEFAULT_RETRY.maxRetries
  const baseDelayMs = retryOpts?.baseDelayMs ?? DEFAULT_RETRY.baseDelayMs
  let attempt = 0
  let overallTimedOut = false
  let overallTimer: ReturnType<typeof setTimeout> | null = null

  const streamState: StreamState = {
    lastChunkAt: Date.now(),
    firstChunkReceived: false,
    watchdogAbort: null,
    watchdog: {
      first_chunk_ms: DEFAULT_FIRST_CHUNK_TIMEOUT_MS,
      chunk_idle_ms: DEFAULT_CHUNK_IDLE_TIMEOUT_MS,
      overall_ms: DEFAULT_OVERALL_TIMEOUT_MS,
    },
  }

  const startedAt = Date.now()
  const armOverallTimer = (budgetMs: number) => {
    if (overallTimer) clearTimeout(overallTimer)
    const capped = Math.min(budgetMs, HARD_OVERALL_TIMEOUT_CAP_MS)
    const remaining = capped - (Date.now() - startedAt)
    overallTimer = setTimeout(() => {
      overallTimedOut = true
      streamState.watchdogAbort?.()
      controller.abort()
    }, Math.max(0, remaining))
  }
  armOverallTimer(streamState.watchdog.overall_ms)

  const originalRoundStart = handlers?.onRoundStart
  const wrappedHandlers: OpenAgentSseHandlers | undefined = handlers
    ? {
      ...handlers,
      onRoundStart: (data) => {
        const watchdog = coerceWatchdog(data)
        if (watchdog) {
          streamState.watchdog = watchdog
          armOverallTimer(watchdog.overall_ms)
        }
        originalRoundStart?.(data)
      },
    }
    : undefined

  const onVisibilityChange = () => {
    if (typeof document === 'undefined') return
    if (document.visibilityState !== 'visible') return
    if (!streamState.firstChunkReceived) return
    if (Date.now() - streamState.lastChunkAt >= streamState.watchdog.chunk_idle_ms) {
      streamState.watchdogAbort?.()
    }
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibilityChange)
  }

  try {
    while (true) {
      if (controller.signal.aborted) {
        if (overallTimedOut) {
          handlers?.onError?.('OpenAgent stream timed out')
        }
        return
      }

      const result = await doFetchSSE(
        url,
        buildInit(),
        wrappedHandlers,
        controller,
        streamState,
        state,
      )

      if (result.abortedByUserSignal && overallTimedOut) {
        handlers?.onError?.('OpenAgent stream timed out')
        return
      }

      if (result.completed || result.nonRetryable) return
      if (controller.signal.aborted) return

      attempt += 1
      if (attempt > maxRetries) {
        handlers?.onError?.('OpenAgent stream failed after retries')
        return
      }

      state.resume = true
      state.isRetry = true
      handlers?.onRetry?.(attempt, maxRetries)
      await waitForRetry(attempt, baseDelayMs, controller.signal, result.retryAfterMs)
      if (controller.signal.aborted) return
    }
  } finally {
    if (overallTimer) clearTimeout(overallTimer)
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }
}

async function doFetchSSE(
  url: string,
  init: RequestInit,
  handlers: OpenAgentSseHandlers | undefined,
  userController: AbortController,
  streamState: StreamState,
  retryState: RetryState,
): Promise<{
  completed: boolean
  nonRetryable: boolean
  retryAfterMs?: number | null
  abortedByUserSignal?: boolean
}> {
  const watchdogController = new AbortController()
  const forwardAbort = () => watchdogController.abort()
  streamState.watchdogAbort = forwardAbort
  streamState.firstChunkReceived = false
  streamState.lastChunkAt = Date.now()

  if (userController.signal.aborted) {
    watchdogController.abort()
  } else {
    userController.signal.addEventListener('abort', forwardAbort, { once: true })
  }

  let receivedDoneOrError = false
  const mergedInit: RequestInit = { ...init, signal: watchdogController.signal }

  try {
    const response = await fetch(url, mergedInit)
    if (!response.ok) {
      const text = await response.text()
      const retryable = response.status >= 500 || response.status === 408 || response.status === 429
      if (!retryable) {
        handlers?.onError?.(text || `HTTP ${response.status}`)
      }
      return {
        completed: false,
        nonRetryable: !retryable,
        retryAfterMs: parseRetryAfter(response.headers.get('Retry-After')),
      }
    }

    const reader = response.body?.getReader()
    if (!reader) {
      handlers?.onError?.('OpenAgent stream has no response body')
      return { completed: false, nonRetryable: true }
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''
    let currentEventId: string | null = null
    let currentDataLines: string[] = []

    const dispatchBufferedEvent = () => {
      if (!currentEvent && currentDataLines.length === 0 && currentEventId === null) return

      const event = currentEvent
      const rawData = currentDataLines.join('\n')
      const eventId = currentEventId
      currentEvent = ''
      currentEventId = null
      currentDataLines = []

      if (!event) return

      let data: Record<string, unknown> | null = null
      if (rawData) {
        try {
          const parsed = JSON.parse(rawData) as unknown
          data = parsed && typeof parsed === 'object' && !Array.isArray(parsed)
            ? parsed as Record<string, unknown>
            : { value: parsed }
        } catch {
          data = { content: rawData }
        }
      }

      if (eventId && ROUND_EVENT_ID_RE.test(eventId)) {
        retryState.lastEventId = eventId
      }
      dispatchSseEvent(event, data, handlers)
      if (event === 'done' || event === 'error') {
        receivedDoneOrError = true
      }
    }

    while (true) {
      const idleMs = streamState.firstChunkReceived
        ? streamState.watchdog.chunk_idle_ms
        : streamState.watchdog.first_chunk_ms
      const { value, done } = await readWithIdleTimeout(
        reader,
        idleMs,
        () => watchdogController.abort(),
      )

      if (done) {
        buffer += decoder.decode()
        break
      }

      streamState.lastChunkAt = Date.now()
      if (!streamState.firstChunkReceived && value && value.byteLength > 0) {
        streamState.firstChunkReceived = true
      }

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const normalized = line.endsWith('\r') ? line.slice(0, -1) : line
        if (normalized === '') {
          dispatchBufferedEvent()
        } else if (normalized.startsWith('id:')) {
          currentEventId = normalized.slice(3).trimStart()
        } else if (normalized.startsWith('event:')) {
          currentEvent = normalized.slice(6).trimStart()
        } else if (normalized.startsWith('data:')) {
          currentDataLines.push(normalized.slice(5).trimStart())
        }
      }
    }

    if (buffer) {
      const normalized = buffer.endsWith('\r') ? buffer.slice(0, -1) : buffer
      if (normalized.startsWith('id:')) {
        currentEventId = normalized.slice(3).trimStart()
      } else if (normalized.startsWith('event:')) {
        currentEvent = normalized.slice(6).trimStart()
      } else if (normalized.startsWith('data:')) {
        currentDataLines.push(normalized.slice(5).trimStart())
      }
    }
    dispatchBufferedEvent()

    return receivedDoneOrError
      ? { completed: true, nonRetryable: false }
      : { completed: false, nonRetryable: false }
  } catch (error) {
    if (receivedDoneOrError) return { completed: true, nonRetryable: false }
    if (isAbortError(error) && userController.signal.aborted) {
      return { completed: true, nonRetryable: true, abortedByUserSignal: true }
    }
    return { completed: false, nonRetryable: false }
  } finally {
    userController.signal.removeEventListener('abort', forwardAbort)
    streamState.watchdogAbort = null
  }
}

export function streamOpenAgentConversation({
  conversationPublicId,
  visitorSessionToken,
  message,
  quotedMessageId,
  clientMessageId,
  requestId,
  lastEventId,
  resume = false,
  signal,
  retry,
  handlers,
}: StreamOpenAgentConversationParams): OpenAgentStreamController {
  const state: RetryState = {
    requestId: requestId || generateRequestId(),
    clientMessageId: clientMessageId || generateClientMessageId(),
    lastEventId: lastEventId && ROUND_EVENT_ID_RE.test(lastEventId) ? lastEventId : null,
    resume,
    isRetry: false,
  }

  const controller = new AbortController() as OpenAgentStreamController
  controller.requestId = state.requestId
  controller.clientMessageId = state.clientMessageId
  controller.completion = Promise.resolve()
  attachControllerSnapshot(controller, state)

  let forwardAbort: (() => void) | null = null
  if (signal) {
    forwardAbort = () => controller.abort()
    if (signal.aborted) {
      controller.abort()
    } else {
      signal.addEventListener('abort', forwardAbort, { once: true })
    }
  }

  const buildInit = (): RequestInit => {
    const body: Record<string, unknown> = {
      message,
      ...(quotedMessageId ? { quoted_message_id: quotedMessageId } : {}),
      request_id: state.requestId,
      client_message_id: state.clientMessageId,
      resume: state.resume || state.isRetry,
    }
    if (state.lastEventId) {
      body.last_event_id = state.lastEventId
    }

    return {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${visitorSessionToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    }
  }

  controller.completion = fetchSSEWithRetry(
    `${API_BASE}/v1/public/conversations/${conversationPublicId}/open-agent/chat`,
    buildInit,
    handlers,
    controller,
    state,
    retry,
  ).finally(() => {
    if (signal && forwardAbort) {
      signal.removeEventListener('abort', forwardAbort)
    }
  })

  return controller
}
