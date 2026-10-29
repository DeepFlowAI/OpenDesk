import { describe, expect, it } from 'vitest'

import { describeScope } from '@/app/components/features/call-center/call-event-rule-catalog'
import { getAdminRouteRule } from '@/config/admin-permissions'
import { canAccessAdminRoute, getDefaultAdminPath } from '@/utils/permissions'

const EMBED = 'call.admin.embed.manage'
const EVENTS = 'call.admin.event_subscription.manage'

function user(permissions: string[]) {
  return { is_super_admin: false, permissions: ['admin.access', ...permissions], data_scopes: {} }
}

describe('call integration route rules', () => {
  it('allows the integrations root with either sub-feature permission', () => {
    const rule = getAdminRouteRule('/call-center/integrations')
    expect(rule?.forbidOnDeny).toBe(true)
    expect(canAccessAdminRoute(user([EMBED]), rule!)).toBe(true)
    expect(canAccessAdminRoute(user([EVENTS]), rule!)).toBe(true)
    expect(canAccessAdminRoute(user([]), rule!)).toBe(false)
  })

  it('guards each sub-feature with its own permission', () => {
    const embedRule = getAdminRouteRule('/call-center/integrations/embedded-call/new')
    const eventsRule = getAdminRouteRule('/call-center/integrations/event-subscriptions/abc')
    expect(canAccessAdminRoute(user([EVENTS]), embedRule!)).toBe(false)
    expect(canAccessAdminRoute(user([EVENTS]), eventsRule!)).toBe(true)
    expect(canAccessAdminRoute(user([EMBED]), eventsRule!)).toBe(false)
  })

  it('shows the integrations nav entry for event-subscription-only admins', () => {
    expect(getDefaultAdminPath(user([EVENTS]))).toBe('/call-center/integrations')
  })
})

describe('describeScope', () => {
  it('summarizes full and partial scopes', () => {
    expect(
      describeScope(
        ['inbound', 'outbound'],
        ['inbound', 'agent_dial', 'embedded_call', 'personal_auto_outbound', 'manual_outbound_task', 'auto_outbound'],
        true,
      ).summary,
    ).toBe('全部方向 · 全部来源')
    expect(describeScope(['inbound'], ['inbound', 'agent_dial', 'auto_outbound'], true).summary).toBe('呼入 · 3 个来源')
  })
})
