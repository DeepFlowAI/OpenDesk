import type { UserInfo } from '@/models/auth'
import { ADMIN_NAV_GROUPS } from '@/config/admin-permissions'

export type DataScopeResource =
  | 'ticket'
  | 'session_record'
  | 'call_record'
  | 'offline_message'
  | 'chat.conversation.peer.view'
  | 'chat.queue.view'
export type DataScopeValue = 'all' | 'group' | 'self'

type PermissionUser = Pick<UserInfo, 'is_super_admin' | 'permissions' | 'data_scopes'>

const DEFAULT_HOME_PRIORITY: Array<{ permissions: string[]; path: string }> = [
  { permissions: ['chat.workspace.use'], path: '/workspace/chat' },
  { permissions: ['call.workspace.use'], path: '/workspace/call' },
  { permissions: ['ticket.workspace.view', 'ticket.workspace.create'], path: '/workspace/tickets' },
  { permissions: ['knowledge.workspace.view'], path: '/workspace/knowledge' },
  { permissions: ['crm.workspace.user.view'], path: '/workspace/users' },
  { permissions: ['crm.workspace.org.view'], path: '/workspace/organizations' },
  { permissions: ['admin.access'], path: 'admin' },
]

export function hasPermission(user: PermissionUser | null | undefined, permission: string): boolean {
  if (!user) return false
  if (user.is_super_admin) return true
  return (user.permissions ?? []).includes(permission)
}

export function hasAnyPermission(user: PermissionUser | null | undefined, permissions: string[]): boolean {
  if (!user) return false
  if (user.is_super_admin) return true
  return permissions.some((permission) => (user.permissions ?? []).includes(permission))
}

export function hasAllPermissions(user: PermissionUser | null | undefined, permissions: string[]): boolean {
  if (!user) return false
  if (user.is_super_admin) return true
  return permissions.every((permission) => (user.permissions ?? []).includes(permission))
}

export function getDataScope(
  user: PermissionUser | null | undefined,
  resource: DataScopeResource,
): DataScopeValue | null {
  if (!user) return null
  if (user.is_super_admin) return 'all'
  return user.data_scopes?.[resource] ?? null
}

export function getDefaultAccessiblePath(user: PermissionUser | null | undefined): string {
  for (const item of DEFAULT_HOME_PRIORITY) {
    if (!hasAnyPermission(user, item.permissions)) continue
    if (item.path === 'admin') return getDefaultAdminPath(user)
    return item.path
  }
  return '/403'
}

export function getDefaultAdminPath(user: PermissionUser | null | undefined): string {
  if (!hasPermission(user, 'admin.access')) return '/403'
  for (const group of ADMIN_NAV_GROUPS) {
    const item = group.items.find((navItem) => (
      navItem.superAdminOnly ? Boolean(user?.is_super_admin) : hasPermission(user, navItem.permission)
    ))
    if (item) return item.href
  }
  return '/403'
}
