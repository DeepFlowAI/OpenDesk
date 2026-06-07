export type WorkspaceNavIconKey =
  | 'tickets'
  | 'chat'
  | 'call'
  | 'records'
  | 'contacts'

export type WorkspaceNavItem = {
  labelKey: string
  href: string
  iconKey: WorkspaceNavIconKey
  permissions: string[]
}

export type WorkspaceRecordIconKey =
  | 'onlineMonitor'
  | 'sessions'
  | 'sessionReports'
  | 'callMonitor'
  | 'calls'
  | 'callReports'

export type WorkspaceRecordNavItem = {
  labelKey: string
  href: string
  iconKey: WorkspaceRecordIconKey
  permissions: string[]
  requiresReports?: boolean
}

export type WorkspaceRecordNavGroup = {
  items: WorkspaceRecordNavItem[]
}

export type WorkspaceRouteRule = {
  prefix: string
  permissions: string[]
}

export const WORKSPACE_NAV_ITEMS: WorkspaceNavItem[] = [
  {
    labelKey: 'ws.nav.tickets',
    href: '/workspace/tickets',
    iconKey: 'tickets',
    permissions: ['ticket.workspace.view', 'ticket.workspace.create'],
  },
  {
    labelKey: 'ws.nav.chat',
    href: '/workspace/chat',
    iconKey: 'chat',
    permissions: ['chat.workspace.use'],
  },
  {
    labelKey: 'ws.nav.call',
    href: '/workspace/call',
    iconKey: 'call',
    permissions: ['call.workspace.use'],
  },
  {
    labelKey: 'ws.nav.records',
    href: '/workspace/records',
    iconKey: 'records',
    permissions: [
      'chat.session_record.view',
      'chat.online_monitor.view',
      'chat.session_report.view',
      'call.monitor.view',
      'call.record.view',
      'call.report.view',
    ],
  },
  {
    labelKey: 'ws.nav.contacts',
    href: '/workspace/users',
    iconKey: 'contacts',
    permissions: ['crm.workspace.user.view', 'crm.workspace.org.view'],
  },
]

export const WORKSPACE_RECORD_NAV_GROUPS: WorkspaceRecordNavGroup[] = [
  {
    items: [
      {
        labelKey: 'ws.records.nav.onlineMonitor',
        href: '/workspace/records/online-monitor',
        iconKey: 'onlineMonitor',
        permissions: ['chat.online_monitor.view'],
        requiresReports: true,
      },
      {
        labelKey: 'ws.records.nav.sessions',
        href: '/workspace/records/sessions',
        iconKey: 'sessions',
        permissions: ['chat.session_record.view'],
      },
      {
        labelKey: 'ws.records.nav.sessionReports',
        href: '/workspace/records/session-reports',
        iconKey: 'sessionReports',
        permissions: ['chat.session_report.view'],
        requiresReports: true,
      },
    ],
  },
  {
    items: [
      {
        labelKey: 'ws.records.nav.callMonitor',
        href: '/workspace/records/call-monitor',
        iconKey: 'callMonitor',
        permissions: ['call.monitor.view'],
        requiresReports: true,
      },
      {
        labelKey: 'ws.records.nav.calls',
        href: '/workspace/records/calls',
        iconKey: 'calls',
        permissions: ['call.record.view'],
      },
      {
        labelKey: 'ws.records.nav.callReports',
        href: '/workspace/records/call-reports',
        iconKey: 'callReports',
        permissions: ['call.report.view'],
        requiresReports: true,
      },
    ],
  },
]

export const WORKSPACE_ROUTE_RULES: WorkspaceRouteRule[] = [
  { prefix: '/workspace/records/online-monitor', permissions: ['chat.online_monitor.view'] },
  { prefix: '/workspace/records/session-reports', permissions: ['chat.session_report.view'] },
  { prefix: '/workspace/records/call-monitor', permissions: ['call.monitor.view'] },
  { prefix: '/workspace/records/call-reports', permissions: ['call.report.view'] },
  { prefix: '/workspace/records/sessions', permissions: ['chat.session_record.view'] },
  { prefix: '/workspace/records/calls', permissions: ['call.record.view'] },
  {
    prefix: '/workspace/records',
    permissions: [
      'chat.session_record.view',
      'chat.online_monitor.view',
      'chat.session_report.view',
      'call.monitor.view',
      'call.record.view',
      'call.report.view',
    ],
  },
  { prefix: '/workspace/chat', permissions: ['chat.workspace.use'] },
  { prefix: '/workspace/call', permissions: ['call.workspace.use'] },
  { prefix: '/workspace/tickets', permissions: ['ticket.workspace.view'] },
  { prefix: '/workspace/organizations', permissions: ['crm.workspace.org.view'] },
  { prefix: '/workspace/users', permissions: ['crm.workspace.user.view'] },
].sort((a, b) => b.prefix.length - a.prefix.length)

export function isWorkspacePathMatch(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`)
}

export function getWorkspaceRouteRule(pathname: string): WorkspaceRouteRule | null {
  return WORKSPACE_ROUTE_RULES.find((rule) => isWorkspacePathMatch(pathname, rule.prefix)) ?? null
}

export function getDefaultWorkspaceRecordPath(
  canAccess: (permissions: string[]) => boolean,
  reportsEnabled: boolean,
): string {
  for (const group of WORKSPACE_RECORD_NAV_GROUPS) {
    for (const item of group.items) {
      if (item.requiresReports && !reportsEnabled) continue
      if (canAccess(item.permissions)) return item.href
    }
  }
  return '/403'
}
