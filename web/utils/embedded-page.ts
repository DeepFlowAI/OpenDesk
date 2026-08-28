import type { EmbeddedPageContext, EmbeddedPageLocation } from '@/models/embedded-page'

export type EmbeddedPageUrlVariable = {
  key: string
  placeholder: string
}

const CHAT_AUXILIARY_URL_VARIABLES: EmbeddedPageUrlVariable[] = [
  { key: 'agent_id', placeholder: '{agent_id}' },
  { key: 'agent_name', placeholder: '{agent_name}' },
  { key: 'agent_email', placeholder: '{agent_email}' },
  { key: 'conversation_id', placeholder: '{conversation_id}' },
  { key: 'channel_type', placeholder: '{channel_type}' },
  { key: 'visitor_id', placeholder: '{visitor_id}' },
  { key: 'visitor_name', placeholder: '{visitor_name}' },
  { key: 'user_id', placeholder: '{user_id}' },
]

const CALL_SCREEN_POP_URL_VARIABLES: EmbeddedPageUrlVariable[] = [
  { key: 'agent_id', placeholder: '{agent_id}' },
  { key: 'agent_name', placeholder: '{agent_name}' },
  { key: 'agent_email', placeholder: '{agent_email}' },
  { key: 'call_record_id', placeholder: '{call_record_id}' },
  { key: 'direction', placeholder: '{direction}' },
  { key: 'customer_number', placeholder: '{customer_number}' },
  { key: 'queue_id', placeholder: '{queue_id}' },
  { key: 'user_id', placeholder: '{user_id}' },
]

/** URL variables available per embed location, shown as chips in the admin form. */
export const EMBEDDED_PAGE_URL_VARIABLES_BY_LOCATION: Record<
  EmbeddedPageLocation,
  EmbeddedPageUrlVariable[]
> = {
  chat_auxiliary: CHAT_AUXILIARY_URL_VARIABLES,
  call_screen_pop: CALL_SCREEN_POP_URL_VARIABLES,
}

const ALL_KNOWN_VARIABLE_KEYS = new Set(
  [...CHAT_AUXILIARY_URL_VARIABLES, ...CALL_SCREEN_POP_URL_VARIABLES].map((v) => v.key),
)

function resolveVariable(key: string, context: EmbeddedPageContext): string {
  switch (key) {
    case 'agent_id':
      return context.agent ? String(context.agent.id) : ''
    case 'agent_name':
      return context.agent?.name ?? ''
    case 'agent_email':
      return context.agent?.email ?? ''
    case 'conversation_id':
      return context.conversation ? String(context.conversation.id) : ''
    case 'channel_type':
      return context.conversation?.channelType ?? ''
    case 'visitor_id':
      return context.visitor ? String(context.visitor.id) : ''
    case 'visitor_name':
      return context.visitor?.name ?? ''
    case 'user_id':
      return context.user ? String(context.user.id) : ''
    case 'call_record_id':
      return context.call ? String(context.call.recordId) : ''
    case 'direction':
      return context.call?.direction ?? ''
    case 'customer_number':
      return context.call?.customerNumber ?? ''
    case 'queue_id':
      return context.call?.queueId != null ? String(context.call.queueId) : ''
    default:
      return ''
  }
}

/** Replace `{variable}` tokens in the configured URL. Missing values become empty strings. */
export function buildEmbeddedPageUrl(url: string, context: EmbeddedPageContext): string {
  return url.replace(/\{([a-z_]+)\}/g, (raw, key: string) => {
    return ALL_KNOWN_VARIABLE_KEYS.has(key) ? resolveVariable(key, context) : raw
  })
}
