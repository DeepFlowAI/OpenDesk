import type {
  EmbedSession,
  EmbeddedControlLease,
  EmbeddedDialCommand,
  EmbeddedDialPayload,
} from '@/models/embedded-call'
import type { TenantPhoneNumberListResponse } from '@/models/tenant-phone-number'
import { useQuery } from '@tanstack/react-query'
import ky from 'ky'
import { get, normalizeApiBase, post } from '@/service/base'

// The frame may share an origin (and stored admin login) with the host page, so the
// unauthenticated exchange must not attach that login or trigger its 401 handling.
const publicClient = ky.create({
  prefixUrl: normalizeApiBase(process.env.NEXT_PUBLIC_API_URL),
  timeout: 30000,
})

export const exchangeEmbedSession = (body: {
  embedSignature: string
  origin: string
  nonce: string
  instanceId: string
}) =>
  publicClient
    .post('v1/public/call-center/embed-sessions', {
      json: {
        embed_signature: body.embedSignature,
        origin: body.origin,
        nonce: body.nonce,
        instance_id: body.instanceId,
      },
    })
    .json<EmbedSession>()

export const dialFromEmbed = (body: EmbeddedDialPayload & { outboundNumberId: string }) =>
  post<EmbeddedDialCommand>('v1/call-center/embed/commands/dial', {
    json: {
      number: body.number,
      outbound_number_id: body.outboundNumberId,
      external_context: body.externalContext,
      custom_business_info: body.customBusinessInfo,
      idempotency_key: body.idempotencyKey,
    },
  })

export const getEmbeddedDialCommand = (commandId: string) =>
  get<EmbeddedDialCommand>(`v1/call-center/embed/commands/${commandId}`)

export const useEmbeddedOutboundNumbers = () =>
  useQuery({
    queryKey: ['embedded-call', 'outbound-numbers'],
    queryFn: () =>
      get<TenantPhoneNumberListResponse>('v1/call-center/agents/me/outbound-numbers'),
  })

type ControlAction = 'acquire' | 'heartbeat' | 'takeover' | 'release'

export const updateEmbeddedControl = (
  action: ControlAction,
  body: { instanceId: string; surface?: string; leaseToken?: string | null },
  options?: { keepalive?: boolean },
) =>
  post<EmbeddedControlLease>(`v1/call-center/embed/control/${action}`, {
    json: {
      instance_id: body.instanceId,
      surface: body.surface ?? 'embedded_call',
      lease_token: body.leaseToken,
    },
    keepalive: options?.keepalive,
  })
