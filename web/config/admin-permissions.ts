export type AdminNavIconKey =
  | 'employees'
  | 'employeeGroups'
  | 'roles'
  | 'queueSettings'
  | 'flowStudio'
  | 'phoneNumbers'
  | 'callSummary'
  | 'conversationSettings'
  | 'channels'
  | 'sessionRouting'
  | 'sessionSummary'
  | 'userFields'
  | 'organizationFields'
  | 'userViews'
  | 'organizationViews'
  | 'organizationSettings'
  | 'formLayouts'
  | 'sharedFields'
  | 'ticketViews'
  | 'ticketWorkflows'
  | 'systemSettings'
  | 'serviceHours'
  | 'openAgent'

export type AdminNavItem = {
  labelKey: string
  href: string
  iconKey: AdminNavIconKey
  permission: string
}

export type AdminNavGroup = {
  labelKey: string
  items: AdminNavItem[]
}

export type AdminRouteRule = {
  prefix: string
  permissions: string[]
}

export const ADMIN_NAV_GROUPS: AdminNavGroup[] = [
  {
    labelKey: 'nav.group.organization',
    items: [
      { labelKey: 'nav.employees', href: '/employees', iconKey: 'employees', permission: 'org.employee.view' },
      { labelKey: 'nav.employeeGroups', href: '/employee-groups', iconKey: 'employeeGroups', permission: 'org.group.manage' },
      { labelKey: 'nav.roles', href: '/roles', iconKey: 'roles', permission: 'org.role.manage' },
      { labelKey: 'nav.queueSettings', href: '/queue-settings', iconKey: 'queueSettings', permission: 'org.queue.manage' },
    ],
  },
  {
    labelKey: 'nav.group.callCenter',
    items: [
      { labelKey: 'nav.flowStudio', href: '/flow-studio', iconKey: 'flowStudio', permission: 'call.admin.flow.manage' },
      { labelKey: 'nav.phoneNumbers', href: '/call-center/phone-numbers', iconKey: 'phoneNumbers', permission: 'call.admin.number.manage' },
      { labelKey: 'nav.callSummary', href: '/call-summary', iconKey: 'callSummary', permission: 'call.admin.summary_config.manage' },
    ],
  },
  {
    labelKey: 'nav.group.onlineService',
    items: [
      { labelKey: 'nav.conversationSettings', href: '/online-service/conversation-settings', iconKey: 'conversationSettings', permission: 'chat.admin.settings.manage' },
      { labelKey: 'nav.channels', href: '/channels', iconKey: 'channels', permission: 'chat.admin.channel.manage' },
      { labelKey: 'nav.sessionRouting', href: '/session-routing', iconKey: 'sessionRouting', permission: 'chat.admin.routing.manage' },
      { labelKey: 'nav.sessionSummary', href: '/session-summary', iconKey: 'sessionSummary', permission: 'chat.admin.summary_config.manage' },
    ],
  },
  {
    labelKey: 'nav.group.userOrganization',
    items: [
      { labelKey: 'nav.userFields', href: '/user-fields', iconKey: 'userFields', permission: 'crm.admin.user_field.manage' },
      { labelKey: 'nav.organizationFields', href: '/organization-fields', iconKey: 'organizationFields', permission: 'crm.admin.org_field.manage' },
      { labelKey: 'nav.userViews', href: '/user-views', iconKey: 'userViews', permission: 'crm.admin.user_view.manage' },
      { labelKey: 'nav.organizationViews', href: '/organization-views', iconKey: 'organizationViews', permission: 'crm.admin.org_view.manage' },
      { labelKey: 'nav.organizationSettings', href: '/organization-settings', iconKey: 'organizationSettings', permission: 'crm.admin.org_settings.manage' },
    ],
  },
  {
    labelKey: 'nav.group.ticket',
    items: [
      { labelKey: 'nav.formLayouts', href: '/form-layouts', iconKey: 'formLayouts', permission: 'ticket.admin.layout.manage' },
      { labelKey: 'nav.sharedFields', href: '/shared-fields', iconKey: 'sharedFields', permission: 'ticket.admin.shared_field.manage' },
      { labelKey: 'nav.ticketViews', href: '/ticket-views', iconKey: 'ticketViews', permission: 'ticket.admin.view.manage' },
      { labelKey: 'nav.ticketWorkflows', href: '/ticket-workflows', iconKey: 'ticketWorkflows', permission: 'ticket.admin.workflow.manage' },
    ],
  },
  {
    labelKey: 'nav.group.globalSettings',
    items: [
      { labelKey: 'nav.systemSettings', href: '/system-settings', iconKey: 'systemSettings', permission: 'settings.system.manage' },
      { labelKey: 'nav.serviceHours', href: '/service-hours', iconKey: 'serviceHours', permission: 'settings.service_hours.manage' },
      { labelKey: 'nav.openAgent', href: '/open-agent-settings', iconKey: 'openAgent', permission: 'settings.open_agent.manage' },
    ],
  },
]

export const ADMIN_ROUTE_RULES: AdminRouteRule[] = [
  { prefix: '/employees/new', permissions: ['org.employee.create'] },
  { prefix: '/employees', permissions: ['org.employee.view'] },
  { prefix: '/employee-groups', permissions: ['org.group.manage'] },
  { prefix: '/roles', permissions: ['org.role.manage'] },
  { prefix: '/queue-settings', permissions: ['org.queue.manage'] },
  { prefix: '/flow-studio', permissions: ['call.admin.flow.manage'] },
  { prefix: '/call-center/phone-numbers', permissions: ['call.admin.number.manage'] },
  { prefix: '/call-summary', permissions: ['call.admin.summary_config.manage'] },
  { prefix: '/online-service/conversation-settings', permissions: ['chat.admin.settings.manage'] },
  { prefix: '/channels', permissions: ['chat.admin.channel.manage'] },
  { prefix: '/session-routing', permissions: ['chat.admin.routing.manage'] },
  { prefix: '/session-summary', permissions: ['chat.admin.summary_config.manage'] },
  { prefix: '/user-fields', permissions: ['crm.admin.user_field.manage'] },
  { prefix: '/organization-fields', permissions: ['crm.admin.org_field.manage'] },
  { prefix: '/user-views', permissions: ['crm.admin.user_view.manage'] },
  { prefix: '/organization-views', permissions: ['crm.admin.org_view.manage'] },
  { prefix: '/organization-settings', permissions: ['crm.admin.org_settings.manage'] },
  { prefix: '/form-layouts', permissions: ['ticket.admin.layout.manage'] },
  { prefix: '/shared-fields', permissions: ['ticket.admin.shared_field.manage'] },
  { prefix: '/ticket-views', permissions: ['ticket.admin.view.manage'] },
  { prefix: '/ticket-workflows', permissions: ['ticket.admin.workflow.manage'] },
  { prefix: '/system-settings', permissions: ['settings.system.manage'] },
  { prefix: '/service-hours', permissions: ['settings.service_hours.manage'] },
  { prefix: '/open-agent-settings', permissions: ['settings.open_agent.manage'] },
].sort((a, b) => b.prefix.length - a.prefix.length)

export function isAdminPathMatch(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`)
}

export function getAdminRouteRule(pathname: string): AdminRouteRule | null {
  return ADMIN_ROUTE_RULES.find((rule) => isAdminPathMatch(pathname, rule.prefix)) ?? null
}
