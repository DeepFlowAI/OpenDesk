'use client'

import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { IconChevronDown, IconPhotoPlus, IconLoader2, IconX } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useUploadAvatar } from '@/service/use-upload'
import { useEmployeeGroups } from '@/service/use-employee-groups'
import { useRoleOptions } from '@/service/use-roles'
import { ScopedQueueSettings } from '@/app/components/features/queue-settings/scoped-queue-settings'
import type { Employee, CreateEmployeePayload, UpdateEmployeePayload } from '@/models/employee'
import type { QueuePolicy, QueuePolicyUpsertPayload } from '@/models/queue-policy'
import type { RoleOption } from '@/models/role'

type FormErrors = Record<string, string>

type Props = {
  initialData?: Employee
  isEdit?: boolean
  onSubmit: (
    data: CreateEmployeePayload | UpdateEmployeePayload,
    queuePolicies?: QueuePolicyUpsertPayload[]
  ) => void
  queueSettings?: {
    defaultPolicies?: QueuePolicy[]
    scopedPolicies?: QueuePolicy[]
  }
}

function generateRandomPassword(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
  let password = ''
  for (let i = 0; i < 12; i++) {
    password += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  return password
}

function FormSelect({
  value,
  options,
  onChange,
  width = 120,
}: {
  value: string
  options: { value: string; label: string }[]
  onChange: (v: string) => void
  width?: number
}) {
  const [open, setOpen] = useState(false)
  const selected = options.find((o) => o.value === value)
  return (
    <div className="relative" style={{ width }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-10 w-full items-center justify-between rounded-lg border border-border px-3 text-sm text-foreground/80"
      >
        <span>{selected?.label ?? value}</span>
        <IconChevronDown size={16} className="text-muted-foreground" />
      </button>
      {open && (
        <div className="absolute top-11 left-0 z-20 w-full rounded-lg border border-border bg-white py-1 shadow-lg">
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => { onChange(opt.value); setOpen(false) }}
              className={`block w-full px-3 py-2 text-left text-sm transition-colors hover:bg-accent ${
                opt.value === value ? 'font-medium text-foreground' : 'text-foreground/80'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function EmployeeForm({ initialData, isEdit = false, onSubmit, queueSettings }: Props) {
  const { locale } = useLocaleStore()
  const uploadMutation = useUploadAvatar()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [name, setName] = useState(initialData?.name ?? '')
  const [avatar, setAvatar] = useState(initialData?.avatar ?? '')
  const [nickname, setNickname] = useState(initialData?.nickname ?? '')
  const [jobNumber, setJobNumber] = useState(initialData?.job_number ?? '')
  const [username, setUsername] = useState(initialData?.username ?? '')
  const [email, setEmail] = useState(initialData?.email ?? '')
  const [phone, setPhone] = useState(initialData?.phone ?? '')
  const [password, setPassword] = useState('')
  const [roleIds, setRoleIds] = useState<number[]>(initialData?.role_ids ?? [])
  const [groupIds, setGroupIds] = useState<number[]>(initialData?.group_ids ?? [])
  const [maxConcurrent, setMaxConcurrent] = useState(String(initialData?.max_concurrent ?? 10))
  const [defaultLanguage, setDefaultLanguage] = useState(initialData?.default_language ?? 'system')
  const [errors, setErrors] = useState<FormErrors>({})
  const [queuePolicyPayloads, setQueuePolicyPayloads] = useState<QueuePolicyUpsertPayload[]>([])
  const [queuePoliciesValid, setQueuePoliciesValid] = useState(true)
  const [groupDropdownOpen, setGroupDropdownOpen] = useState(false)
  const [roleDropdownOpen, setRoleDropdownOpen] = useState(false)

  const { data: groupsData } = useEmployeeGroups({ per_page: 100 })
  const { data: rolesData } = useRoleOptions()
  const allGroups = useMemo(() => groupsData?.items ?? [], [groupsData])
  const availableRoles = useMemo(() => rolesData?.items ?? [], [rolesData])
  const groupDropdownRef = useRef<HTMLDivElement>(null)
  const roleDropdownRef = useRef<HTMLDivElement>(null)
  const rolesInitializedRef = useRef(false)

  useEffect(() => {
    if (!groupDropdownOpen) return
    const handleClick = (e: MouseEvent) => {
      if (groupDropdownRef.current && !groupDropdownRef.current.contains(e.target as Node)) {
        setGroupDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [groupDropdownOpen])

  useEffect(() => {
    if (!roleDropdownOpen) return
    const handleClick = (e: MouseEvent) => {
      if (roleDropdownRef.current && !roleDropdownRef.current.contains(e.target as Node)) {
        setRoleDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [roleDropdownOpen])

  useEffect(() => {
    if (rolesInitializedRef.current || availableRoles.length === 0) return
    const existingIds = initialData?.role_ids ?? []
    if (existingIds.length > 0) {
      setRoleIds(existingIds)
      rolesInitializedRef.current = true
      return
    }

    const legacyRoles = initialData?.roles ?? ['agent']
    const mappedIds = availableRoles
      .filter((role) => role.key && legacyRoles.includes(role.key))
      .map((role) => role.id)
    setRoleIds(mappedIds.length > 0 ? mappedIds : [availableRoles[0].id])
    rolesInitializedRef.current = true
  }, [availableRoles, initialData?.role_ids, initialData?.roles])

  const selectedRoles = useMemo<RoleOption[]>(() => (
    roleIds
      .map((roleId) => availableRoles.find((role) => role.id === roleId))
      .filter((role): role is RoleOption => Boolean(role))
  ), [availableRoles, roleIds])

  const legacyRoles = useMemo(() => {
    const keys = selectedRoles
      .map((role) => role.key)
      .filter((key): key is string => key === 'admin' || key === 'agent')
    return keys.length > 0 ? Array.from(new Set(keys)).sort() : ['agent']
  }, [selectedRoles])

  const hasChannelEligibility = useMemo(() => {
    if (selectedRoles.some((role) => role.permissions.includes('chat.workspace.use') || role.permissions.includes('call.workspace.use'))) {
      return true
    }
    return legacyRoles.includes('agent')
  }, [legacyRoles, selectedRoles])

  const langOptions = useMemo(() => [
    { value: 'system', label: t('emp.form.lang.system', locale) },
    { value: 'zh', label: t('emp.form.lang.zh', locale) },
    { value: 'en', label: t('emp.form.lang.en', locale) },
  ], [locale])

  const validate = useCallback((): FormErrors => {
    const errs: FormErrors = {}
    if (!name.trim()) errs.name = t('emp.validation.name.required', locale)
    if (!username.trim()) errs.username = t('emp.validation.username.required', locale)
    if (!email.trim()) errs.email = t('emp.validation.email.required', locale)
    else if (!email.includes('@')) errs.email = t('emp.validation.email.invalid', locale)
    if (!isEdit && !password) errs.password = t('emp.validation.password.required', locale)
    if (password && (password.length < 8 || password.length > 32)) {
      errs.password = t('emp.validation.password.format', locale)
    }
    if (roleIds.length === 0) errs.roles = t('emp.validation.roles.required', locale)
    return errs
  }, [name, username, email, password, roleIds, isEdit, locale])

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      const errs = validate()
      if (!queuePoliciesValid) errs.queue_settings = t('queue.validation.fixErrors', locale)
      setErrors(errs)
      if (Object.keys(errs).length > 0) return

      const mc = parseInt(maxConcurrent, 10)
      if (isEdit) {
        const payload: UpdateEmployeePayload = {
          name: name.trim(),
          nickname: nickname.trim() || null,
          job_number: jobNumber.trim() || null,
          username: username.trim(),
          email: email.trim(),
          phone: phone.trim() || null,
          avatar: avatar || null,
          roles: legacyRoles,
          role_ids: roleIds,
          max_concurrent: isNaN(mc) ? 10 : mc,
          default_language: defaultLanguage,
          group_ids: groupIds,
        }
        if (password) payload.password = password
        onSubmit(payload, queuePolicyPayloads)
      } else {
        const payload: CreateEmployeePayload = {
          name: name.trim(),
          nickname: nickname.trim() || null,
          job_number: jobNumber.trim() || null,
          username: username.trim(),
          email: email.trim(),
          phone: phone.trim() || null,
          password,
          avatar: avatar || null,
          roles: legacyRoles,
          role_ids: roleIds,
          max_concurrent: isNaN(mc) ? 10 : mc,
          default_language: defaultLanguage,
          group_ids: groupIds,
        }
        onSubmit(payload, queuePolicyPayloads)
      }
    },
    [name, nickname, jobNumber, username, email, phone, password, legacyRoles, roleIds, groupIds, maxConcurrent, defaultLanguage, isEdit, validate, onSubmit, avatar, queuePoliciesValid, queuePolicyPayloads, locale]
  )

  const handleQueueSettingsChange = useCallback((payloads: QueuePolicyUpsertPayload[], valid: boolean) => {
    setQueuePolicyPayloads(payloads)
    setQueuePoliciesValid(valid)
    if (valid) setErrors((prev) => ({ ...prev, queue_settings: '' }))
  }, [])

  const handleGeneratePassword = () => {
    const pwd = generateRandomPassword()
    setPassword(pwd)
    setErrors((prev) => ({ ...prev, password: '' }))
  }

  const handleAvatarClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const url = await uploadMutation.mutateAsync(file)
      setAvatar(url)
    } catch {
      // upload failed silently
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <form id="employee-form" onSubmit={handleSubmit} className="flex flex-col gap-5 p-8">
      {/* Name */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-1">
          <label className="text-sm font-medium text-foreground/80">{t('emp.form.name', locale)}</label>
          <span className="text-sm text-destructive">*</span>
        </div>
        <input
          type="text"
          value={name}
          onChange={(e) => { setName(e.target.value); setErrors((p) => ({ ...p, name: '' })) }}
          placeholder={t('emp.form.name.placeholder', locale)}
          maxLength={64}
          className={`h-10 w-[280px] rounded-lg border px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring ${
            errors.name ? 'border-destructive' : 'border-border'
          }`}
        />
        {errors.name && <span className="text-xs text-destructive">{errors.name}</span>}
      </div>

      {/* Avatar */}
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground/80">{t('emp.form.avatar', locale)}</label>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/gif,image/webp"
          onChange={handleFileChange}
          className="hidden"
        />
        <button
          type="button"
          onClick={handleAvatarClick}
          disabled={uploadMutation.isPending}
          className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-lg border border-border bg-muted transition-colors hover:border-muted-foreground disabled:opacity-50"
        >
          {uploadMutation.isPending ? (
            <IconLoader2 size={24} className="animate-spin text-muted-foreground" />
          ) : avatar ? (
            <img src={avatar} alt="avatar" className="h-full w-full object-cover" />
          ) : (
            <IconPhotoPlus size={24} className="text-muted-foreground" />
          )}
        </button>
      </div>

      {/* Nickname */}
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground/80">{t('emp.form.nickname', locale)}</label>
        <input
          type="text"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          placeholder={t('emp.form.nickname.placeholder', locale)}
          maxLength={64}
          className="h-10 rounded-lg border border-border px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          style={{ width: 'min(100%, 480px)' }}
        />
      </div>

      {/* Job Number */}
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground/80">{t('emp.form.jobNumber', locale)}</label>
        <input
          type="text"
          value={jobNumber}
          onChange={(e) => setJobNumber(e.target.value)}
          placeholder={t('emp.form.jobNumber.placeholder', locale)}
          maxLength={32}
          className="h-10 w-[200px] rounded-lg border border-border px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>

      {/* Username */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-1">
          <label className="text-sm font-medium text-foreground/80">{t('emp.form.username', locale)}</label>
          <span className="text-sm text-destructive">*</span>
        </div>
        <input
          type="text"
          value={username}
          onChange={(e) => { setUsername(e.target.value); setErrors((p) => ({ ...p, username: '' })) }}
          placeholder={t('emp.form.username.placeholder', locale)}
          maxLength={32}
          className={`h-10 w-[280px] rounded-lg border px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring ${
            errors.username ? 'border-destructive' : 'border-border'
          }`}
        />
        {errors.username && <span className="text-xs text-destructive">{errors.username}</span>}
      </div>

      {/* Email */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-1">
          <label className="text-sm font-medium text-foreground/80">{t('emp.form.email', locale)}</label>
          <span className="text-sm text-destructive">*</span>
        </div>
        <input
          type="text"
          value={email}
          onChange={(e) => { setEmail(e.target.value); setErrors((p) => ({ ...p, email: '' })) }}
          placeholder={t('emp.form.email.placeholder', locale)}
          maxLength={128}
          className={`h-10 w-[280px] rounded-lg border px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring ${
            errors.email ? 'border-destructive' : 'border-border'
          }`}
        />
        {errors.email && <span className="text-xs text-destructive">{errors.email}</span>}
      </div>

      {/* Phone */}
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground/80">{t('emp.form.phone', locale)}</label>
        <input
          type="text"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder={t('emp.form.phone.placeholder', locale)}
          maxLength={32}
          className="h-10 w-[200px] rounded-lg border border-border px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>

      {/* Password */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-1">
          <label className="text-sm font-medium text-foreground/80">{t('emp.form.password', locale)}</label>
          {!isEdit && <span className="text-sm text-destructive">*</span>}
        </div>
        <div className="flex items-center gap-3">
          <input
            type="text"
            value={password}
            onChange={(e) => { setPassword(e.target.value); setErrors((p) => ({ ...p, password: '' })) }}
            placeholder={isEdit ? t('emp.form.password.editHint', locale) : t('emp.form.password.placeholder', locale)}
            maxLength={32}
            className={`h-10 w-[280px] rounded-lg border px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring ${
              errors.password ? 'border-destructive' : 'border-border'
            }`}
          />
          <button
            type="button"
            onClick={handleGeneratePassword}
            className="text-sm text-foreground transition-colors hover:text-foreground/80"
          >
            {t('emp.form.generatePassword', locale)}
          </button>
        </div>
        {errors.password && <span className="text-xs text-destructive">{errors.password}</span>}
      </div>

      {/* Role */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-1">
          <label className="text-sm font-medium text-foreground/80">{t('emp.form.role', locale)}</label>
          <span className="text-sm text-destructive">*</span>
        </div>
        <div className="relative w-[360px]" ref={roleDropdownRef}>
          <button
            type="button"
            onClick={() => setRoleDropdownOpen(!roleDropdownOpen)}
            className={`flex min-h-10 w-full items-center justify-between rounded-lg border px-3 py-1.5 text-sm ${
              errors.roles ? 'border-destructive' : 'border-border'
            }`}
          >
            {roleIds.length > 0 ? (
              <div className="flex flex-1 flex-wrap items-center gap-1 overflow-hidden">
                {roleIds.map((roleId) => {
                  const role = availableRoles.find((item) => item.id === roleId)
                  return (
                    <span
                      key={roleId}
                      className="inline-flex items-center gap-0.5 rounded bg-muted px-1.5 py-0.5 text-xs"
                    >
                      {role?.name ?? `#${roleId}`}
                      <IconX
                        size={12}
                        className="cursor-pointer text-muted-foreground hover:text-foreground"
                        onClick={(event) => {
                          event.stopPropagation()
                          setRoleIds((prev) => prev.filter((id) => id !== roleId))
                        }}
                      />
                    </span>
                  )
                })}
              </div>
            ) : (
              <span className="text-muted-foreground">{t('emp.form.role.placeholder', locale)}</span>
            )}
            <IconChevronDown size={16} className="shrink-0 text-muted-foreground" />
          </button>
          {roleDropdownOpen && (
            <div className="absolute left-0 top-11 z-20 max-h-[240px] w-full overflow-y-auto rounded-lg border border-border bg-white py-1 shadow-lg">
              {availableRoles.length === 0 ? (
                <div className="px-3 py-2 text-sm text-muted-foreground">
                  {t('role.empty', locale)}
                </div>
              ) : (
                availableRoles.map((role) => {
                  const selected = roleIds.includes(role.id)
                  return (
                    <button
                      key={role.id}
                      type="button"
                      onClick={() => {
                        setRoleIds((prev) =>
                          selected ? prev.filter((id) => id !== role.id) : [...prev, role.id]
                        )
                        setErrors((p) => ({ ...p, roles: '' }))
                      }}
                      className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-accent ${
                        selected ? 'font-medium text-foreground' : 'text-foreground/80'
                      }`}
                    >
                      <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                        selected ? 'border-primary bg-primary text-primary-foreground' : 'border-border'
                      }`}>
                        {selected && <span className="text-[10px]">✓</span>}
                      </span>
                      <span className="min-w-0 flex-1 truncate">{role.name}</span>
                      {role.is_system && (
                        <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                          {t('role.type.system', locale)}
                        </span>
                      )}
                    </button>
                  )
                })
              )}
            </div>
          )}
        </div>
        {errors.roles && <span className="text-xs text-destructive">{errors.roles}</span>}
      </div>

      {/* Employee Group */}
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground/80">{t('emp.form.group', locale)}</label>
        <div className="relative w-[300px]" ref={groupDropdownRef}>
          <button
            type="button"
            onClick={() => setGroupDropdownOpen(!groupDropdownOpen)}
            className="flex h-10 w-full items-center justify-between rounded-lg border border-border px-3 text-sm"
          >
            {groupIds.length > 0 ? (
              <div className="flex flex-1 flex-wrap items-center gap-1 overflow-hidden">
                {groupIds.map((gid) => {
                  const g = allGroups.find((x) => x.id === gid)
                  return (
                    <span
                      key={gid}
                      className="inline-flex items-center gap-0.5 rounded bg-muted px-1.5 py-0.5 text-xs"
                    >
                      {g?.name ?? `#${gid}`}
                      <IconX
                        size={12}
                        className="cursor-pointer text-muted-foreground hover:text-foreground"
                        onClick={(e) => {
                          e.stopPropagation()
                          setGroupIds((prev) => prev.filter((id) => id !== gid))
                        }}
                      />
                    </span>
                  )
                })}
              </div>
            ) : (
              <span className="text-muted-foreground">{t('emp.form.group.placeholder', locale)}</span>
            )}
            <IconChevronDown size={16} className="shrink-0 text-muted-foreground" />
          </button>
          {groupDropdownOpen && (
            <div className="absolute top-11 left-0 z-20 max-h-[200px] w-full overflow-y-auto rounded-lg border border-border bg-white py-1 shadow-lg">
              {allGroups.length === 0 ? (
                <div className="px-3 py-2 text-sm text-muted-foreground">
                  {locale === 'zh' ? '暂无员工组' : 'No groups'}
                </div>
              ) : (
                allGroups.map((g) => {
                  const selected = groupIds.includes(g.id)
                  return (
                    <button
                      key={g.id}
                      type="button"
                      onClick={() => {
                        setGroupIds((prev) =>
                          selected ? prev.filter((id) => id !== g.id) : [...prev, g.id]
                        )
                      }}
                      className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-accent ${
                        selected ? 'font-medium text-foreground' : 'text-foreground/80'
                      }`}
                    >
                      <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                        selected ? 'border-primary bg-primary text-primary-foreground' : 'border-border'
                      }`}>
                        {selected && <span className="text-[10px]">✓</span>}
                      </span>
                      {g.name}
                    </button>
                  )
                })
              )}
            </div>
          )}
        </div>
      </div>

      {/* Max Concurrent */}
      {hasChannelEligibility && (
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-foreground/80">{t('emp.form.maxConcurrent', locale)}</label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={maxConcurrent}
              onChange={(e) => setMaxConcurrent(e.target.value)}
              min={1}
              className="h-10 w-[120px] rounded-lg border border-border px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <span className="text-xs text-muted-foreground">{t('emp.form.maxConcurrent.hint', locale)}</span>
          </div>
        </div>
      )}

      {queueSettings && initialData && (
        <ScopedQueueSettings
          title={t('queue.employeeSection.title', locale)}
          scopeType="employee"
          scopeId={initialData.id}
          defaultPolicies={queueSettings.defaultPolicies}
          scopedPolicies={queueSettings.scopedPolicies}
          includeStrategy={false}
          disabled={!hasChannelEligibility}
          disabledHint={t('queue.employee.noChannelEligibility', locale)}
          onChange={handleQueueSettingsChange}
        />
      )}
      {errors.queue_settings && <span className="text-sm text-destructive">{errors.queue_settings}</span>}

      {/* Language */}
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground/80">{t('emp.form.language', locale)}</label>
        <FormSelect value={defaultLanguage} options={langOptions} onChange={setDefaultLanguage} width={140} />
      </div>
    </form>
  )
}
