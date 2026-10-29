import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ky from 'ky'
import { del, get, normalizeApiBase, post, put } from '@/service/base'
import type {
  CallEventTesterEvent,
  CallEventTesterEventList,
  CallEventTesterReceiver,
} from '@/models/call-event-tester'

const BASE = 'v1/call-center/event-tester/receiver'
const RECEIVER_KEY = ['call-event-tester', 'receiver'] as const
const POLL_MS = 2000
const MAX_ITEMS = 500

const API_BASE = normalizeApiBase(process.env.NEXT_PUBLIC_API_URL)

// Requests authenticated by the tester's own credentials (integration secret,
// open API key) must not carry the signed-in admin session.
const publicClient = ky.create({ prefixUrl: API_BASE, timeout: 30000 })

/** Absolute webhook URL for a receiver path, resolved against the API origin. */
export function resolveWebhookUrl(path: string): string {
  return new URL(path, new URL(API_BASE || '/', window.location.origin)).toString()
}

export function useCallEventTesterReceiver() {
  return useQuery({
    queryKey: RECEIVER_KEY,
    queryFn: () => get<CallEventTesterReceiver>(BASE),
    staleTime: Infinity,
  })
}

export function useSetCallEventTesterSecret() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (secret: string | null) =>
      put<CallEventTesterReceiver>(`${BASE}/secret`, { json: { secret } }),
    onSuccess: (data) => queryClient.setQueryData(RECEIVER_KEY, data),
  })
}

export function useRotateCallEventTesterReceiver() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => post<CallEventTesterReceiver>(`${BASE}/rotate`),
    onSuccess: (data) => queryClient.setQueryData(RECEIVER_KEY, data),
  })
}

/** Incrementally polls the caller's receiver; resets when the token changes. */
export function useCallEventTesterEvents(token: string | undefined) {
  const [items, setItems] = useState<CallEventTesterEvent[]>([])
  const [error, setError] = useState<unknown>(null)
  const lastSeq = useRef(0)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    lastSeq.current = 0
    setItems([])

    const poll = async () => {
      try {
        const data = await get<CallEventTesterEventList>(`${BASE}/events`, {
          searchParams: { after: lastSeq.current },
        })
        if (cancelled) return
        setError(null)
        if (data.items.length) {
          lastSeq.current = data.items[data.items.length - 1].seq
          setItems((prev) => [...prev, ...data.items].slice(-MAX_ITEMS))
        } else if (data.last_seq < lastSeq.current) {
          lastSeq.current = data.last_seq
        }
      } catch (err) {
        if (!cancelled) setError(err)
      }
      if (!cancelled) timer = setTimeout(poll, POLL_MS)
    }
    void poll()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [token])

  const clear = async () => {
    await del(`${BASE}/events`)
    setItems([])
  }

  return { items, error, clear }
}

export interface EmbedSignatureResult {
  embed_signature: string
  expires_in?: number
}

export const requestEmbedSignature = (body: {
  integrationKey: string
  integrationSecret: string
  employeeIdentifier: string
  origin: string
  nonce: string
}) =>
  publicClient
    .post('v1/public/call-center/embed-signatures', {
      headers: { 'X-OpenDesk-Integration-Secret': body.integrationSecret },
      json: {
        integration_key: body.integrationKey,
        employee_identifier: body.employeeIdentifier,
        origin: body.origin,
        nonce: body.nonce,
      },
    })
    .json<EmbedSignatureResult>()

export const fetchOpenApi = (apiKey: string, path: string) =>
  publicClient
    .get(path, { headers: { Authorization: `Bearer ${apiKey}` }, throwHttpErrors: false })
    .then(async (res) => ({ status: res.status, body: await res.json().catch(() => null) }))
