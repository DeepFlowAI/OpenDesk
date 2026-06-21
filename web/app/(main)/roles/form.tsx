'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { DataScopeValue, PermissionNode, Role, RolePayload } from '@/models/role'
import { usePermissionTree } from '@/service/use-roles'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'

type FormErrors = Record<string, string>

type Props = {
  initialData?: Partial<Role>
  readOnly?: boolean
  onSubmit: (payload: RolePayload) => void
}

function permissionLabel(node: PermissionNode, locale: 'zh' | 'en') {
  return locale === 'zh' ? node.name : node.name_en
}

function scopeLabel(scope: DataScopeValue, locale: 'zh' | 'en') {
  if (locale === 'zh') {
    if (scope === 'all') return '全部'
    if (scope === 'group') return '所在组'
    return '仅自己'
  }
  if (scope === 'all') return 'All'
  if (scope === 'group') return 'Group'
  return 'Self'
}

const sessionRecordCompatScopeResources = new Set(['chat.conversation.peer.view', 'chat.queue.view'])

function scopeValue(dataScopes: Record<string, DataScopeValue>, resource: string): DataScopeValue {
  return dataScopes[resource] ?? (sessionRecordCompatScopeResources.has(resource) ? dataScopes.session_record : undefined) ?? 'self'
}

export default function RoleForm({ initialData, readOnly = false, onSubmit }: Props) {
  const { locale } = useLocaleStore()
  const { data: treeData, isLoading } = usePermissionTree()
  const [activeTab, setActiveTab] = useState('workspace')
  const [name, setName] = useState(initialData?.name ?? '')
  const [description, setDescription] = useState(initialData?.description ?? '')
  const [isActive, setIsActive] = useState(initialData?.is_active ?? true)
  const [permissions, setPermissions] = useState<string[]>(initialData?.permissions ?? [])
  const [dataScopes, setDataScopes] = useState<Record<string, DataScopeValue>>(initialData?.data_scopes ?? {})
  const [errors, setErrors] = useState<FormErrors>({})

  const initKey = `${initialData?.id ?? 'new'}:${initialData?.name ?? ''}:${initialData?.permissions?.join(',') ?? ''}`
  useEffect(() => {
    setName(initialData?.name ?? '')
    setDescription(initialData?.description ?? '')
    setIsActive(initialData?.is_active ?? true)
    setPermissions(initialData?.permissions ?? [])
    setDataScopes(initialData?.data_scopes ?? {})
    setErrors({})
  }, [initKey, initialData?.description, initialData?.is_active, initialData?.data_scopes])

  const nodes = useMemo(() => {
    const items: PermissionNode[] = []
    for (const tab of treeData?.tabs ?? []) {
      for (const module of tab.modules) {
        items.push(...module.permissions)
      }
    }
    return items
  }, [treeData])

  const nodeByKey = useMemo(() => {
    const map = new Map<string, PermissionNode>()
    for (const node of nodes) map.set(node.key, node)
    return map
  }, [nodes])

  const dependentsByRequirement = useMemo(() => {
    const map = new Map<string, string[]>()
    for (const node of nodes) {
      if (!node.requires) continue
      map.set(node.requires, [...(map.get(node.requires) ?? []), node.key])
    }
    return map
  }, [nodes])

  const collectDependents = useCallback((key: string): string[] => {
    const direct = dependentsByRequirement.get(key) ?? []
    return direct.flatMap((child) => [child, ...collectDependents(child)])
  }, [dependentsByRequirement])

  const addWithRequirements = useCallback((key: string, current: Set<string>) => {
    current.add(key)
    const node = nodeByKey.get(key)
    if (node?.requires) addWithRequirements(node.requires, current)
  }, [nodeByKey])

  const togglePermission = useCallback((key: string) => {
    if (readOnly) return
    setPermissions((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
        for (const child of collectDependents(key)) next.delete(child)
      } else {
        addWithRequirements(key, next)
      }
      return Array.from(next).sort()
    })
    setErrors((prev) => ({ ...prev, permissions: '' }))
  }, [addWithRequirements, collectDependents, readOnly])

  const validate = useCallback((): FormErrors => {
    const next: FormErrors = {}
    if (!name.trim()) next.name = t('role.validation.name.required', locale)
    if (permissions.length === 0) next.permissions = t('role.validation.permissions.required', locale)
    return next
  }, [locale, name, permissions.length])

  const handleSubmit = useCallback((event: React.FormEvent) => {
    event.preventDefault()
    if (readOnly) return
    const nextErrors = validate()
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) return
    onSubmit({
      name: name.trim(),
      description: description.trim() || null,
      is_active: isActive,
      permissions,
      data_scopes: dataScopes,
    })
  }, [dataScopes, description, isActive, name, onSubmit, permissions, readOnly, validate])

  if (isLoading) {
    return (
      <div className="p-8">
        <p className="text-sm text-muted-foreground">{t('role.loading', locale)}</p>
      </div>
    )
  }

  const tabs = treeData?.tabs ?? []
  const currentTab = tabs.find((tab) => tab.key === activeTab) ?? tabs[0]

  return (
    <form id="role-form" onSubmit={handleSubmit} className="flex flex-col gap-6 p-8">
      <section className="flex flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-1">
            <label className="text-sm font-medium text-foreground/80">{t('role.form.name', locale)}</label>
            <span className="text-sm text-destructive">*</span>
          </div>
          <input
            type="text"
            value={name}
            onChange={(event) => {
              setName(event.target.value)
              setErrors((prev) => ({ ...prev, name: '' }))
            }}
            disabled={readOnly}
            maxLength={64}
            className={cn(
              'h-10 w-[320px] rounded-lg border px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:bg-muted disabled:text-muted-foreground',
              errors.name ? 'border-destructive' : 'border-border'
            )}
            placeholder={t('role.form.name.placeholder', locale)}
          />
          {errors.name && <span className="text-xs text-destructive">{errors.name}</span>}
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-foreground/80">{t('role.form.description', locale)}</label>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            disabled={readOnly}
            maxLength={255}
            className="min-h-24 w-full max-w-[640px] rounded-lg border border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:bg-muted disabled:text-muted-foreground"
            placeholder={t('role.form.description.placeholder', locale)}
          />
        </div>

        <label className="flex w-fit items-center gap-2 text-sm text-foreground/80">
          <button
            type="button"
            disabled={readOnly || initialData?.is_system}
            onClick={() => setIsActive((prev) => !prev)}
            className={cn(
              'relative h-5 w-9 rounded-full transition-colors disabled:opacity-50',
              isActive ? 'bg-primary' : 'bg-border'
            )}
          >
            <span
              className={cn(
                'absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform',
                isActive ? 'left-4' : 'left-0.5'
              )}
            />
          </button>
          {t('role.form.active', locale)}
        </label>
      </section>

      <section className="flex flex-col gap-4">
        <div className="flex border-b border-border">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'h-10 px-4 text-sm font-medium transition-colors',
                (currentTab?.key ?? activeTab) === tab.key
                  ? 'border-b-2 border-primary text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {locale === 'zh' ? tab.name : tab.name_en}
            </button>
          ))}
        </div>

        {errors.permissions && <span className="text-xs text-destructive">{errors.permissions}</span>}

        <div className="grid gap-4 xl:grid-cols-2">
          {(currentTab?.modules ?? []).map((module) => (
            <div key={module.key} className="rounded-lg border border-border">
              <div className="border-b border-border bg-muted px-4 py-3">
                <h2 className="text-sm font-semibold text-foreground">
                  {locale === 'zh' ? module.name : module.name_en}
                </h2>
              </div>
              <div className="flex flex-col divide-y divide-border">
                {module.permissions.map((node) => {
                  const checked = permissions.includes(node.key)
                  const disabled = readOnly || Boolean(node.requires && !permissions.includes(node.requires))
                  const scopeResource = node.data_scope_resource
                  return (
                    <div key={node.key} className="flex flex-col gap-3 px-4 py-3">
                      <button
                        type="button"
                        disabled={disabled}
                        onClick={() => togglePermission(node.key)}
                        className="flex w-full items-center gap-3 text-left disabled:opacity-50"
                      >
                        <span
                          className={cn(
                            'flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[10px] transition-colors',
                            checked ? 'border-primary bg-primary text-primary-foreground' : 'border-border'
                          )}
                        >
                          {checked ? '✓' : ''}
                        </span>
                        <span className="flex-1 text-sm text-foreground/85">
                          {permissionLabel(node, locale)}
                        </span>
                        <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                          {node.type}
                        </span>
                      </button>

                      {checked && scopeResource && (
                        <div className="ml-7 flex flex-wrap items-center gap-2">
                          {(treeData?.data_scope_options ?? ['all', 'group', 'self']).map((scope) => (
                            <button
                              key={scope}
                              type="button"
                              disabled={readOnly}
                              onClick={() =>
                                setDataScopes((prev) => ({
                                  ...prev,
                                  [scopeResource]: scope,
                                }))
                              }
                              className={cn(
                                'h-8 rounded-lg border px-3 text-xs transition-colors disabled:opacity-50',
                                scopeValue(dataScopes, scopeResource) === scope
                                  ? 'border-primary bg-primary text-primary-foreground'
                                  : 'border-border text-foreground/80 hover:bg-accent'
                              )}
                            >
                              {scopeLabel(scope, locale)}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </section>
    </form>
  )
}
