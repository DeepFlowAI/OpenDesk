'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { IconAlertTriangle, IconLoader2 } from '@tabler/icons-react'

import { EmbeddedCallPanel } from '@/app/components/features/embedded-call/embedded-call-panel'
import { CallCenterProvider, useCallCenterRuntime } from '@/context/call-center-runtime'
import { useLocaleStore } from '@/context/locale-store'
import { useSocketStore } from '@/context/socket-store'
import type {
  EmbedSession,
  EmbeddedControlLease,
  EmbeddedDialPayload,
  EmbeddedExternalContext,
} from '@/models/embedded-call'
import { setRuntimeAccessToken } from '@/service/base'
import {
  dialFromEmbed,
  exchangeEmbedSession,
  updateEmbeddedControl,
  useEmbeddedOutboundNumbers,
} from '@/service/use-embedded-call'
import { useMyCurrentCallDevice } from '@/service/use-agent-devices'


const PROTOCOL_VERSION = '1.0'

type HostMessage = {
  source?: string
  protocolVersion?: string
  instanceId?: string
  type?: string
  requestId?: string | null
  payload?: Record<string, unknown>
}

type CommandExecutor = (name: string, payload: Record<string, unknown>) => Promise<unknown>

type EmbeddedCallClientProps = {
  integrationKey: string
  instanceId: string
  protocolVersion: string
  initialExpanded: boolean
  requestedLocale?: string
  requestedTheme?: string
}

function randomId(prefix: string): string {
  const bytes = new Uint8Array(12)
  crypto.getRandomValues(bytes)
  return `${prefix}${Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')}`
}

function parentOrigin(): string | null {
  if (!document.referrer) return null
  try {
    return new URL(document.referrer).origin
  } catch {
    return null
  }
}

async function apiError(error: unknown): Promise<{ code: string; message: string }> {
  const response = (error as { response?: Response })?.response
  if (response) {
    try {
      const body = await response.clone().json() as { code?: string; message?: string }
      return {
        code: body.code || 'EMBED_API_ERROR',
        message: body.message || 'Embedded call request failed',
      }
    } catch {
      return { code: 'EMBED_API_ERROR', message: `Request failed (${response.status})` }
    }
  }
  const clientError = error as { code?: unknown; message?: unknown }
  return {
    code: typeof clientError?.code === 'string' ? clientError.code : 'EMBED_NETWORK_ERROR',
    message: typeof clientError?.message === 'string'
      ? clientError.message
      : 'Embedded call request failed',
  }
}

function embeddedClientError(code: string, message: string): Error & { code: string } {
  return Object.assign(new Error(message), { code })
}

export function EmbeddedCallClient({
  integrationKey,
  instanceId,
  protocolVersion,
  initialExpanded,
  requestedLocale,
  requestedTheme,
}: EmbeddedCallClientProps) {
  const hostOrigin = parentOrigin()
  const [session, setSession] = useState<EmbedSession | null>(null)
  const [lease, setLease] = useState<EmbeddedControlLease | null>(null)
  const [expanded, setExpanded] = useState(initialExpanded)
  const [prefill, setPrefill] = useState<EmbeddedDialPayload | null>(null)
  const [hostContext, setHostContext] = useState<EmbeddedExternalContext | undefined>()
  const [fatalError, setFatalError] = useState<{ code: string; message: string } | null>(null)
  const nonceRef = useRef('')
  const commandExecutorRef = useRef<CommandExecutor | null>(null)
  const leaseRef = useRef<EmbeddedControlLease | null>(null)
  const sessionRef = useRef<EmbedSession | null>(null)
  const setLocale = useLocaleStore((state) => state.setLocale)
  const connectSocket = useSocketStore((state) => state.connect)
  const disconnectSocket = useSocketStore((state) => state.disconnect)
  const connected = useSocketStore((state) => state.connected)
  const authFailed = useSocketStore((state) => state.authFailed)

  sessionRef.current = session
  leaseRef.current = lease

  const postToHost = useCallback((type: string, payload: Record<string, unknown>, requestId?: string | null) => {
    if (!hostOrigin || window.parent === window) return
    window.parent.postMessage({
      source: 'opendesk-call-frame',
      protocolVersion: PROTOCOL_VERSION,
      instanceId,
      type,
      requestId: requestId || null,
      payload,
    }, hostOrigin)
  }, [hostOrigin, instanceId])

  const emitEvent = useCallback((name: string, payload: Record<string, unknown> = {}) => {
    postToHost('event', {
      name,
      payload: {
        protocolVersion: PROTOCOL_VERSION,
        eventId: randomId('ecevt_'),
        occurredAt: new Date().toISOString(),
        integrationKey,
        instanceId,
        name,
        ...payload,
      },
    })
  }, [integrationKey, instanceId, postToHost])

  const requestAuthentication = useCallback((type: 'handshake' | 'authRequested') => {
    const nonce = randomId('ecnonce_')
    nonceRef.current = nonce
    postToHost(type, { nonce, integrationKey })
  }, [integrationKey, postToHost])

  const releaseControl = useCallback(async () => {
    const current = leaseRef.current
    if (!current?.lease_token) return
    try {
      await updateEmbeddedControl('release', {
        instanceId,
        leaseToken: current.lease_token,
      })
    } catch {
      // The short lease expires automatically if the page is already unloading.
    }
  }, [instanceId])

  useEffect(() => {
    if (!hostOrigin || window.parent === window) {
      setFatalError({ code: 'EMBED_HOST_REQUIRED', message: 'This page must be opened by the OpenDesk Call SDK' })
      return
    }
    if (!integrationKey || !instanceId || protocolVersion !== PROTOCOL_VERSION) {
      setFatalError({ code: 'EMBED_PROTOCOL_INVALID', message: 'Embedded call URL is invalid or unsupported' })
      return
    }
    requestAuthentication('handshake')
  }, [hostOrigin, integrationKey, instanceId, protocolVersion, requestAuthentication])

  useEffect(() => {
    const handleMessage = (event: MessageEvent<HostMessage>) => {
      if (event.origin !== hostOrigin || event.source !== window.parent) return
      const message = event.data
      if (!message || message.source !== 'opendesk-call-host') return
      if (message.protocolVersion !== PROTOCOL_VERSION || message.instanceId !== instanceId) return

      if (message.type === 'authenticate') {
        const signature = message.payload?.embedSignature
        const origin = message.payload?.origin
        const nonce = message.payload?.nonce
        if (
          typeof signature !== 'string'
          || origin !== hostOrigin
          || nonce !== nonceRef.current
        ) {
          emitEvent('error', { code: 'EMBED_AUTH_MESSAGE_INVALID', message: 'Authentication message is invalid' })
          return
        }
        void exchangeEmbedSession({
          embedSignature: signature,
          origin,
          nonce,
          instanceId,
        }).then((nextSession) => {
          setRuntimeAccessToken(nextSession.access_token)
          setSession(nextSession)
          const locale = requestedLocale === 'zh' || requestedLocale === 'en'
            ? requestedLocale
            : nextSession.agent.default_language.startsWith('zh') ? 'zh' : 'en'
          setLocale(locale)
          emitEvent('authStateChanged', { state: 'authenticated' })
        }).catch(async (error) => {
          const detail = await apiError(error)
          emitEvent('error', detail)
          window.setTimeout(() => requestAuthentication('authRequested'), 1000)
        })
        return
      }

      if (message.type !== 'command' || !message.requestId) return
      const name = message.payload?.name
      const payload = message.payload?.payload
      if (typeof name !== 'string' || !payload || typeof payload !== 'object') return
      const respond = (ok: boolean, result?: unknown, error?: { code: string; message: string }) => {
        postToHost('response', { ok, result: result ?? null, error: error ?? null }, message.requestId)
      }
      if (name === 'open' || name === 'close') {
        const next = name === 'open'
        setExpanded(next)
        emitEvent('resizeRequested', { expanded: next, height: next ? 620 : 56 })
        respond(true, { expanded: next })
        return
      }
      if (name === 'destroy') {
        void releaseControl()
        respond(true, { released: true })
        return
      }
      if (name === 'setContext') {
        setHostContext(payload as EmbeddedExternalContext)
        respond(true, { updated: true })
        return
      }
      const executor = commandExecutorRef.current
      if (!executor) {
        respond(false, undefined, { code: 'EMBED_NOT_READY', message: 'Embedded call is not ready' })
        return
      }
      void executor(name, payload as Record<string, unknown>)
        .then((result) => respond(true, result))
        .catch(async (error) => respond(false, undefined, await apiError(error)))
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [emitEvent, hostOrigin, instanceId, postToHost, releaseControl, requestedLocale, requestAuthentication, setLocale])

  useEffect(() => {
    if (!session) return
    setRuntimeAccessToken(session.access_token)
    let cancelled = false
    void updateEmbeddedControl('acquire', { instanceId }).then((result) => {
      if (!cancelled) setLease(result)
    }).catch(async (error) => {
      if (!cancelled) setFatalError(await apiError(error))
    })
    const renewAt = Math.max(30, session.expires_in - 45) * 1000
    const authTimer = window.setTimeout(
      () => requestAuthentication('authRequested'),
      renewAt,
    )
    return () => {
      cancelled = true
      window.clearTimeout(authTimer)
    }
  }, [instanceId, requestAuthentication, session])

  useEffect(() => {
    if (!session || !lease) return
    if (lease.is_owner) connectSocket(session.access_token)
    else disconnectSocket()
  }, [connectSocket, disconnectSocket, lease, session])

  useEffect(() => {
    if (!lease?.lease_token) return
    const timer = window.setInterval(() => {
      const token = leaseRef.current?.lease_token
      if (!token) return
      void updateEmbeddedControl('heartbeat', {
        instanceId,
        leaseToken: token,
      }).then(setLease).catch(() => setLease((current) => current ? { ...current, is_owner: false, lease_token: null } : current))
    }, 5000)
    return () => window.clearInterval(timer)
  }, [instanceId, lease?.lease_token])

  useEffect(() => {
    if (!authFailed || !session) return
    requestAuthentication('authRequested')
  }, [authFailed, requestAuthentication, session])

  useEffect(() => {
    if (!lease) return
    emitEvent('controlOwnershipChanged', {
      isOwner: lease.is_owner,
      ownerInstanceId: lease.owner_instance_id,
    })
  }, [emitEvent, lease])

  useEffect(() => {
    const dark = requestedTheme === 'dark'
      || requestedTheme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches
    document.documentElement.classList.toggle('dark', dark)
  }, [requestedTheme])

  useEffect(() => () => {
    void releaseControl()
    disconnectSocket()
    setRuntimeAccessToken(null)
  }, [disconnectSocket, releaseControl])

  const takeover = async () => {
    const result = await updateEmbeddedControl('takeover', { instanceId })
    setLease(result)
  }

  const updateExpanded = (next: boolean) => {
    setExpanded(next)
    emitEvent('resizeRequested', { expanded: next, height: next ? 620 : 56 })
  }

  if (fatalError) {
    return <EmbeddedError error={fatalError} />
  }
  if (!session || !lease) {
    return (
      <div className={`flex h-dvh min-w-[320px] items-center justify-center bg-background text-foreground ${expanded ? 'min-h-[420px]' : 'min-h-14'}`}>
        <div className="text-center">
          <IconLoader2 className="mx-auto animate-spin text-primary" size={expanded ? 28 : 18} />
          {expanded ? <p className="mt-3 text-sm">正在安全登录 / Secure sign-in</p> : null}
        </div>
      </div>
    )
  }

  const locale = requestedLocale === 'zh' || requestedLocale === 'en'
    ? requestedLocale
    : session.agent.default_language.startsWith('zh') ? 'zh' : 'en'

  return (
    <CallCenterProvider recordsEnabled={false} controlEnabled={lease.is_owner}>
      <EmbeddedRuntimeBridge
        session={session}
        locale={locale}
        connected={connected}
        lease={lease}
        expanded={expanded}
        prefill={prefill}
        hostContext={hostContext}
        commandExecutorRef={commandExecutorRef}
        emitEvent={emitEvent}
        setPrefill={setPrefill}
        setHostContext={setHostContext}
        onExpandedChange={updateExpanded}
        onTakeover={takeover}
      />
    </CallCenterProvider>
  )
}

type RuntimeBridgeProps = {
  session: EmbedSession
  locale: 'zh' | 'en'
  connected: boolean
  lease: EmbeddedControlLease
  expanded: boolean
  prefill: EmbeddedDialPayload | null
  hostContext?: EmbeddedExternalContext
  commandExecutorRef: React.MutableRefObject<CommandExecutor | null>
  emitEvent: (name: string, payload?: Record<string, unknown>) => void
  setPrefill: React.Dispatch<React.SetStateAction<EmbeddedDialPayload | null>>
  setHostContext: React.Dispatch<React.SetStateAction<EmbeddedExternalContext | undefined>>
  onExpandedChange: (expanded: boolean) => void
  onTakeover: () => Promise<void>
}

function EmbeddedRuntimeBridge({
  session,
  locale,
  connected,
  lease,
  expanded,
  prefill,
  hostContext,
  commandExecutorRef,
  emitEvent,
  setPrefill,
  setHostContext,
  onExpandedChange,
  onTakeover,
}: RuntimeBridgeProps) {
  const runtime = useCallCenterRuntime()
  const { data: currentDevice } = useMyCurrentCallDevice()
  const { data: phoneNumbers } = useEmbeddedOutboundNumbers()
  const [activated, setActivated] = useState(false)
  const contextRef = useRef(hostContext)
  const callContextRef = useRef<EmbeddedExternalContext | undefined>(undefined)
  const hasBusinessInfoRef = useRef(false)
  const previousPhaseRef = useRef<string | null>(null)
  const previousModeRef = useRef(runtime.callControl.mode)

  contextRef.current = hostContext

  useEffect(() => {
    if (currentDevice?.device_type === 'sip_phone') setActivated(true)
  }, [currentDevice?.device_type])

  const runDial = useCallback(async (payload: EmbeddedDialPayload & { outboundNumberId?: string }) => {
    if (!lease.is_owner) {
      throw embeddedClientError('EMBED_CONTROL_NOT_OWNER', 'This call is controlled in another window')
    }
    if (!activated) {
      throw embeddedClientError(
        'EMBED_ACTIVATION_REQUIRED',
        'Enable calling in the embedded panel before starting a call',
      )
    }
    const outboundId = payload.outboundNumberId
      || (phoneNumbers?.items ?? []).find((item) => item.call_types.includes('outbound'))?.id
    if (!outboundId) throw new Error('No outbound number is available')
    const externalContext = payload.externalContext || contextRef.current
    const command = await dialFromEmbed({
      ...payload,
      outboundNumberId: outboundId,
      externalContext,
    })
    const selected = phoneNumbers?.items.find((item) => item.id === outboundId)
    callContextRef.current = externalContext
    hasBusinessInfoRef.current = Boolean(payload.customBusinessInfo)
    if (command.call_id) {
      await runtime.handleDialStarted({
        callId: command.call_id,
        destination: payload.number,
        outboundNumber: selected?.phone_number || '',
      })
    }
    setPrefill(null)
    return {
      commandId: command.command_id,
      callId: command.call_id,
      status: command.status,
    }
  }, [activated, lease.is_owner, phoneNumbers?.items, runtime, setPrefill])

  useEffect(() => {
    commandExecutorRef.current = async (name, rawPayload) => {
      if (name === 'dial') return runDial(rawPayload as EmbeddedDialPayload)
      if (name === 'prefillDialer') {
        const payload = rawPayload as EmbeddedDialPayload
        setPrefill({ ...payload, externalContext: payload.externalContext || contextRef.current })
        onExpandedChange(true)
        return { prefilled: true }
      }
      if (name === 'setContext') {
        setHostContext(rawPayload as EmbeddedExternalContext)
        return { updated: true }
      }
      throw new Error(`Unsupported embedded call command: ${name}`)
    }
    return () => {
      commandExecutorRef.current = null
    }
  }, [commandExecutorRef, onExpandedChange, runDial, setHostContext, setPrefill])

  useEffect(() => {
    emitEvent('ready', {
      authState: 'authenticated',
      isOwner: lease.is_owner,
      permissions: session.agent.permissions,
    })
  }, [emitEvent, lease.is_owner, session.agent.permissions])

  useEffect(() => {
    emitEvent('stateChanged', {
      phase: runtime.phase,
      availability: runtime.status?.status,
      connected,
      isOwner: lease.is_owner,
      expanded,
      callId: runtime.incoming?.call_id,
    })
  }, [connected, emitEvent, expanded, lease.is_owner, runtime.incoming?.call_id, runtime.phase, runtime.status?.status])

  useEffect(() => {
    if (runtime.status?.status) {
      emitEvent('availabilityChanged', { availability: runtime.status.status })
    }
  }, [emitEvent, runtime.status?.status])

  useEffect(() => {
    emitEvent('deviceStateChanged', {
      deviceType: currentDevice?.device_type,
      available: currentDevice?.available,
      extensionNumber: currentDevice?.extension_number,
    })
  }, [currentDevice?.available, currentDevice?.device_type, currentDevice?.extension_number, emitEvent])

  useEffect(() => {
    const previous = previousPhaseRef.current
    const phase = runtime.phase
    const summary = {
      callId: runtime.incoming?.call_id,
      direction: runtime.incoming?.direction,
      customerNumber: runtime.incoming?.direction === 'outbound' ? runtime.incoming?.to : runtime.incoming?.from,
      serviceNumber: runtime.incoming?.direction === 'outbound' ? runtime.incoming?.from : runtime.incoming?.to,
      userPublicId: runtime.incoming?.user_public_id,
      externalContext: callContextRef.current,
      hasCustomBusinessInfo: hasBusinessInfoRef.current,
    }
    if (phase === 'incoming' && previous !== 'incoming') {
      emitEvent('callRinging', summary)
      emitEvent('screenPopRequested', summary)
      onExpandedChange(true)
    } else if (phase === 'outbound_ringing' && previous !== 'outbound_ringing') {
      emitEvent('callConnecting', summary)
    } else if (phase === 'on_call' && previous !== 'on_call') {
      emitEvent('callConnected', summary)
    } else if (phase === 'wrap_up' && previous !== 'wrap_up') {
      emitEvent('callEnded', { ...summary, endedAt: new Date().toISOString() })
      emitEvent('wrapUpStarted', summary)
    } else if (phase === 'idle' && previous === 'wrap_up') {
      emitEvent('wrapUpEnded', summary)
      callContextRef.current = undefined
      hasBusinessInfoRef.current = false
    }
    previousPhaseRef.current = phase
  }, [emitEvent, onExpandedChange, runtime.incoming, runtime.phase])

  useEffect(() => {
    const previous = previousModeRef.current
    const mode = runtime.callControl.mode
    if (mode === 'hold' && previous !== 'hold') emitEvent('callHeld', {})
    if (previous === 'hold' && mode === 'single') emitEvent('callResumed', {})
    if (mode !== previous && runtime.phase === 'on_call') {
      emitEvent('callUpdated', {
        callId: runtime.incoming?.call_id,
        mode,
      })
    }
    previousModeRef.current = mode
  }, [emitEvent, runtime.callControl.mode, runtime.incoming?.call_id, runtime.phase])

  return (
    <EmbeddedCallPanel
      session={session}
      locale={locale}
      connected={connected}
      isOwner={lease.is_owner}
      ownerInstanceId={lease.owner_instance_id}
      expanded={expanded}
      activated={activated}
      prefill={prefill}
      onExpandedChange={onExpandedChange}
      onActivatedChange={setActivated}
      onDial={runDial}
      onTakeover={onTakeover}
    />
  )
}

function EmbeddedError({ error }: { error: { code: string; message: string } }) {
  return (
    <div className="flex h-dvh min-h-[420px] min-w-[320px] items-center justify-center bg-background p-6 text-foreground">
      <div className="max-w-sm rounded-xl border border-destructive/30 bg-destructive/5 p-5 text-center" role="alert">
        <IconAlertTriangle className="mx-auto text-destructive" size={30} />
        <h1 className="mt-3 text-sm font-semibold">Embedded call unavailable</h1>
        <p className="mt-2 text-xs text-muted-foreground">{error.message}</p>
        <code className="mt-3 block text-[11px] text-destructive">{error.code}</code>
      </div>
    </div>
  )
}
