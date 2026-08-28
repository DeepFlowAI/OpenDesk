import type {
  EmbedSession,
  EmbeddedControlLease,
  EmbeddedDialCommand,
  EmbeddedDialPayload,
} from '@/models/embedded-call'
import type { TenantPhoneNumberListResponse } from '@/models/tenant-phone-number'
import { useQuery } from '@tanstack/react-query'
import { get, post } from '@/service/base'
export const exchangeEmbedSession = (body: {
  embedSignature: string
  origin: string
  nonce: string
  instanceId: string
}) =>
  post<EmbedSession>('v1/public/call-center/embed-sessions', {
    json: {
      embed_signature: body.embedSignature,
      origin: body.origin,
      nonce: body.nonce,
      instance_id: body.instanceId,
    },
  })

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
) =>
  post<EmbeddedControlLease>(`v1/call-center/embed/control/${action}`, {
    json: {
      instance_id: body.instanceId,
      surface: body.surface ?? 'embedded_call',
      lease_token: body.leaseToken,
    },
  })
