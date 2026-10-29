export type WorkspaceNavIconKey =
  | 'tickets'
  | 'chat'
  | 'call'
  | 'engagement'
  | 'records'
  | 'learning'
  | 'scheduling'
  | 'contacts'
  | 'knowledge'

export type WorkspaceNavItem = {
  labelKey: string
  href: string
  iconKey: WorkspaceNavIconKey
  permissions: string[]
  permissionSets?: string[][]
  activePrefixes?: string[]
  /** Open in a new browser tab so the current workspace page stays intact. */
  openInNewTab?: boolean
}

export type WorkspaceRecordIconKey =
  | 'onlineMonitor'
  | 'sessions'
  | 'offlineMessages'
  | 'sessionReports'
  | 'callMonitor'
  | 'calls'
  | 'callReports'
  | 'smsRecords'
  | 'dashboards'
  | 'quality'

export type WorkspaceRecordChildNavItem = {
  labelKey: string
  href: string
  permission: string
}

export type WorkspaceRecordNavItem = {
  labelKey: string
  href: string
  iconKey: WorkspaceRecordIconKey
  permissions: string[]
  requireAll?: boolean
  requiresReports?: boolean
  children?: WorkspaceRecordChildNavItem[]
}

export type WorkspaceRecordNavGroup = {
  items: WorkspaceRecordNavItem[]
}

export type WorkspaceRouteRule = {
  prefix: string
  permissions: string[]
  requireAll?: boolean
  permissionSets?: string[][]
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
    labelKey: 'ws.nav.engagement',
    href: '/workspace/engagement/outbound-tasks',
    iconKey: 'engagement',
    permissions: [
      'engagement.outbound_task.manage',
      'engagement.outbound_task.create',
      'engagement.auto_outbound_task.manage',
      'engagement.auto_outbound_task.create',
    ],
  },
  {
    labelKey: 'ws.nav.records',
    href: '/workspace/records',
    iconKey: 'records',
    permissions: [
      'chat.session_record.view',
      'chat.offline_message.view',
      'chat.online_monitor.view',
      'chat.session_report.view',
      'call.monitor.view',
      'call.record.view',
      'call.report.view',
      'call.sms_record.view',
      'quality.online.access',
    ],
    permissionSets: [['report.dashboard.view', 'ticket.workspace.view']],
    activePrefixes: ['/workspace/quality'],
  },
  {
    labelKey: 'ws.nav.learning',
    href: '/learning',
    iconKey: 'learning',
    permissions: ['learning.center.use'],
    openInNewTab: true,
  },
  {
    labelKey: 'ws.nav.scheduling',
    href: '/scheduling',
    iconKey: 'scheduling',
    permissions: ['scheduling.my.view', 'scheduling.center.manage'],
    openInNewTab: true,
  },
  {
    labelKey: 'ws.nav.contacts',
    href: '/workspace/users',
    iconKey: 'contacts',
    permissions: ['crm.workspace.user.view', 'crm.workspace.org.view'],
  },
  {
    labelKey: 'ws.nav.knowledge',
    href: '/workspace/knowledge',
    iconKey: 'knowledge',
    permissions: ['knowledge.workspace.view'],
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
        labelKey: 'ws.records.nav.offlineMessages',
        href: '/workspace/records/offline-messages',
        iconKey: 'offlineMessages',
        permissions: ['chat.offline_message.view'],
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
      {
        labelKey: 'ws.records.nav.smsRecords',
        href: '/workspace/records/sms',
        iconKey: 'smsRecords',
        permissions: ['call.sms_record.view'],
      },
    ],
  },
  {
    items: [
      {
        labelKey: 'ws.records.nav.dashboards',
        href: '/workspace/records/dashboards',
        iconKey: 'dashboards',
        permissions: ['report.dashboard.view', 'ticket.workspace.view'],
        requireAll: true,
      },
      {
        labelKey: 'ws.nav.quality',
        href: '/workspace/quality',
        iconKey: 'quality',
        permissions: ['quality.online.access'],
        children: [
          {
            labelKey: 'ws.quality.nav.plans',
            href: '/workspace/quality/online/plans',
            permission: 'quality.online.plan.view',
          },
          {
            labelKey: 'ws.quality.nav.scorecards',
            href: '/workspace/quality/online/scorecards',
            permission: 'quality.online.scorecard.view',
          },
        ],
      },
    ],
  },
]

export const WORKSPACE_ROUTE_RULES: WorkspaceRouteRule[] = [
  { prefix: '/workspace/quality', permissions: ['quality.online.access'] },
  { prefix: '/workspace/records/dashboards', permissions: ['report.dashboard.view', 'ticket.workspace.view'], requireAll: true },
  { prefix: '/workspace/records/online-monitor', permissions: ['chat.online_monitor.view'] },
  { prefix: '/workspace/records/session-reports', permissions: ['chat.session_report.view'] },
  { prefix: '/workspace/records/offline-messages', permissions: ['chat.offline_message.view'] },
  { prefix: '/workspace/records/call-monitor', permissions: ['call.monitor.view'] },
  { prefix: '/workspace/records/call-reports', permissions: ['call.report.view'] },
  { prefix: '/workspace/records/sessions', permissions: ['chat.session_record.view'] },
  { prefix: '/workspace/records/calls', permissions: ['call.record.view'] },
  { prefix: '/workspace/records/sms', permissions: ['call.sms_record.view'] },
  {
    prefix: '/workspace/records',
    permissions: [
      'chat.session_record.view',
      'chat.offline_message.view',
      'chat.online_monitor.view',
      'chat.session_report.view',
      'call.monitor.view',
      'call.record.view',
      'call.report.view',
      'call.sms_record.view',
    ],
    permissionSets: [['report.dashboard.view', 'ticket.workspace.view']],
  },
  { prefix: '/workspace/chat', permissions: ['chat.workspace.use'] },
  { prefix: '/workspace/engagement/outbound-task-templates', permissions: ['engagement.outbound_task.template.manage'] },
  {
    prefix: '/workspace/engagement/auto-outbound-tasks',
    permissions: ['engagement.auto_outbound_task.manage', 'engagement.auto_outbound_task.create'],
  },
  {
    prefix: '/workspace/engagement',
    permissions: [
      'engagement.outbound_task.manage',
      'engagement.outbound_task.create',
      'engagement.auto_outbound_task.manage',
      'engagement.auto_outbound_task.create',
    ],
  },
  { prefix: '/workspace/call/outbound-tasks', permissions: ['engagement.outbound_task.execute'] },
  { prefix: '/workspace/call', permissions: ['call.workspace.use'] },
  { prefix: '/workspace/tickets', permissions: ['ticket.workspace.view'] },
  { prefix: '/workspace/knowledge', permissions: ['knowledge.workspace.view'] },
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
  canAccess: (permissions: string[], requireAll?: boolean) => boolean,
  reportsEnabled: boolean,
): string {
  for (const group of WORKSPACE_RECORD_NAV_GROUPS) {
    for (const item of group.items) {
      if (item.requiresReports && !reportsEnabled) continue
      if (canAccess(item.permissions, item.requireAll)) return item.href
    }
  }
  return '/403'
}
