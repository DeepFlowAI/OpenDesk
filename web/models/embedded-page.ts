export type EmbeddedPageLocation = 'chat_auxiliary' | 'call_screen_pop'
export type EmbeddedPageType = 'iframe' | 'react_code'

export type EmbeddedPage = {
  id: number
  location: EmbeddedPageLocation
  name: string
  page_type: EmbeddedPageType
  url: string | null
  react_code: string | null
  config: Record<string, unknown>
  enabled: boolean
  default_focus: boolean
  sort_order: number
  created_at: string | null
  updated_at: string | null
  default_focus_overridden?: boolean
}

export type EmbeddedPageListResponse = {
  items: EmbeddedPage[]
  total: number
}

export type SaveEmbeddedPagePayload = {
  location: EmbeddedPageLocation
  name: string
  page_type: EmbeddedPageType
  url: string | null
  react_code: string | null
  config: Record<string, unknown>
  enabled: boolean
  default_focus: boolean
  sort_order: number
}

export type EmbeddedPageWorkspaceItem = {
  id: number
  name: string
  page_type: EmbeddedPageType
  url: string | null
  react_code: string | null
  config: Record<string, unknown>
  default_focus: boolean
  sort_order: number
}

export type EmbeddedPageAgentSummary = {
  id: number
  name: string
  email: string
}

export type EmbeddedPageWorkspaceResponse = {
  items: EmbeddedPageWorkspaceItem[]
  agent: EmbeddedPageAgentSummary
}

/** Runtime context injected into embedded pages (iframe postMessage payload / React props). */
export type EmbeddedPageContext = {
  location: EmbeddedPageLocation
  agent: { id: number; name: string; email: string } | null
  conversation: { id: number; channelType: string; status: string } | null
  visitor: { id: number; name: string; email: string | null; phone: string | null; userId: number } | null
  call: {
    recordId: number
    direction: 'inbound' | 'outbound'
    customerNumber: string
    queueId: number | null
    startedAt: string | null
  } | null
  user: { id: number; name: string; phone: string | null } | null
}
