export type H5TicketListContext = {
  view?: string
  page?: number
  q?: string
  group?: string
}

const CONTEXT_KEYS = ['view', 'page', 'q', 'group'] as const

export function readH5TicketListContext(
  params: Pick<URLSearchParams, 'get'>,
): H5TicketListContext {
  const rawPage = Number(params.get('page'))
  return {
    view: clean(params.get('view')),
    page: Number.isInteger(rawPage) && rawPage > 1 ? rawPage : undefined,
    q: clean(params.get('q')),
    group: clean(params.get('group')),
  }
}

export function buildH5TicketListUrl(context: H5TicketListContext = {}): string {
  const params = contextSearchParams(context)
  const query = params.toString()
  return query ? `/h5/tickets?${query}` : '/h5/tickets'
}

export function buildH5TicketNewUrl(context: H5TicketListContext): string {
  return buildChildUrl('/h5/tickets/new', context)
}

export function buildH5TicketDetailUrl(
  ticketId: number,
  context: H5TicketListContext,
  fromList = true,
): string {
  const params = contextSearchParams(context)
  if (fromList) params.set('from', 'list')
  const query = params.toString()
  return `/h5/tickets/${ticketId}${query ? `?${query}` : ''}`
}

export function contextSearchParams(context: H5TicketListContext): URLSearchParams {
  const params = new URLSearchParams()
  if (context.view && context.view !== 'all') params.set('view', context.view)
  if (context.page && context.page > 1) params.set('page', String(context.page))
  if (context.q) params.set('q', context.q)
  if (context.group) params.set('group', context.group)
  return params
}

export function listContextFromChildParams(
  params: Pick<URLSearchParams, 'get'>,
): H5TicketListContext {
  const context = readH5TicketListContext(params)
  return Object.fromEntries(
    CONTEXT_KEYS
      .map((key) => [key, context[key]])
      .filter((entry) => entry[1] !== undefined),
  ) as H5TicketListContext
}

function buildChildUrl(path: string, context: H5TicketListContext): string {
  const query = contextSearchParams(context).toString()
  return query ? `${path}?${query}` : path
}

function clean(value: string | null): string | undefined {
  const normalized = value?.trim()
  return normalized ? normalized : undefined
}
