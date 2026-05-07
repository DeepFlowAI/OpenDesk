'use client'

import { useState, useCallback } from 'react'
import { IconTrash, IconPlus } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useEmployeeSelect } from '@/service/use-employee-groups'
import type {
  EmployeeGroup,
  CreateEmployeeGroupPayload,
  EmployeeGroupMember,
  UserListItem,
} from '@/models/employee-group'

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'

type MemberEntry = {
  employee_id: number
  username: string
  display_name: string | null
}

function AddMemberModal({
  existingIds,
  onConfirm,
  onCancel,
}: {
  existingIds: Set<number>
  onConfirm: (users: MemberEntry[]) => void
  onCancel: () => void
}) {
  const { locale } = useLocaleStore()
  const [keyword, setKeyword] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const [selected, setSelected] = useState<Map<number, UserListItem>>(new Map())
  const { data, isLoading } = useEmployeeSelect({ per_page: 50, keyword: searchKeyword || undefined })

  const users = [...(data?.items ?? [])].sort((a, b) => {
    const aInGroup = existingIds.has(a.id)
    const bInGroup = existingIds.has(b.id)
    if (aInGroup !== bInGroup) return aInGroup ? 1 : -1
    return a.id - b.id
  })

  const toggleSelect = (user: UserListItem) => {
    if (existingIds.has(user.id)) return
    setSelected((prev) => {
      const next = new Map(prev)
      if (next.has(user.id)) {
        next.delete(user.id)
      } else {
        next.set(user.id, user)
      }
      return next
    })
  }

  const handleConfirm = () => {
    const members: MemberEntry[] = Array.from(selected.values()).map((u) => ({
      employee_id: u.id,
      username: u.username,
      display_name: u.display_name,
    }))
    onConfirm(members)
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onCancel() }}>
      <DialogContent className="sm:max-w-[520px] max-h-[80vh] flex flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="px-6 pt-6 pb-4">
          <DialogTitle>{t('eg.addMember.title', locale)}</DialogTitle>
        </DialogHeader>

        <div className="px-6">
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') setSearchKeyword(keyword)
            }}
            placeholder={t('eg.addMember.search', locale)}
          />
        </div>

        <div className="mx-6 mt-3 mb-4 flex-1 overflow-y-auto rounded-lg border">
          {isLoading ? (
            <div className="p-4 text-center text-sm text-muted-foreground">{t('eg.loading', locale)}</div>
          ) : users.length === 0 ? (
            <div className="p-4 text-center text-sm text-muted-foreground">—</div>
          ) : (
            <div className="flex flex-col">
              <div className="flex h-10 items-center gap-4 bg-muted px-4">
                <div className="w-8 shrink-0" />
                <div className="min-w-0 flex-1 text-xs font-semibold">
                  {t('eg.addMember.col.name', locale)}
                </div>
                <div className="w-[140px] shrink-0 text-xs font-semibold">
                  {t('eg.addMember.col.username', locale)}
                </div>
              </div>
              {users.map((user) => {
                const inGroup = existingIds.has(user.id)
                const isSelected = selected.has(user.id)
                return (
                  <div
                    key={user.id}
                    onClick={() => toggleSelect(user)}
                    className={`flex h-10 cursor-pointer items-center gap-4 border-t px-4 transition-colors ${
                      inGroup ? 'cursor-not-allowed opacity-50' : 'hover:bg-accent'
                    }`}
                  >
                    {/* Stop bubbling: Base UI Checkbox dispatches a synthetic input click that would reach the row and double-invoke toggleSelect. */}
                    <div
                      className="flex w-8 shrink-0 items-center justify-center"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Checkbox
                        checked={isSelected}
                        disabled={inGroup}
                        onCheckedChange={() => !inGroup && toggleSelect(user)}
                      />
                    </div>
                    <div className="min-w-0 flex-1 truncate text-sm">
                      {user.display_name || user.username}
                      {inGroup && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          ({t('eg.addMember.inGroup', locale)})
                        </span>
                      )}
                    </div>
                    <div className="w-[140px] shrink-0 truncate text-sm text-muted-foreground">{user.username}</div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <DialogFooter className="px-6 py-4">
          <span className="mr-auto text-sm text-muted-foreground">
            {t('eg.addMember.selected', locale, { count: String(selected.size) })}
          </span>
          <Button variant="outline" onClick={onCancel}>
            {t('eg.addMember.cancel', locale)}
          </Button>
          <Button onClick={handleConfirm} disabled={selected.size === 0}>
            {t('eg.addMember.confirm', locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

type Props = {
  initialData?: EmployeeGroup
  onSubmit: (data: CreateEmployeeGroupPayload) => void
  saving?: boolean
}

export default function EmployeeGroupForm({ initialData, onSubmit, saving }: Props) {
  const { locale } = useLocaleStore()

  const [name, setName] = useState(initialData?.name ?? '')
  const [description, setDescription] = useState(initialData?.description ?? '')
  const [members, setMembers] = useState<MemberEntry[]>(
    initialData?.members?.map((m: EmployeeGroupMember) => ({
      employee_id: m.employee_id,
      username: m.username,
      display_name: m.display_name,
    })) ?? []
  )
  const [nameError, setNameError] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)

  const existingMemberIds = new Set(members.map((m) => m.employee_id))

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      const trimmed = name.trim()
      if (!trimmed) {
        setNameError(t('eg.form.name.required', locale))
        return
      }
      setNameError('')
      onSubmit({
        name: trimmed,
        description: description || null,
        member_ids: members.map((m) => m.employee_id),
      })
    },
    [name, description, members, locale, onSubmit]
  )

  const handleAddMembers = (newMembers: MemberEntry[]) => {
    setMembers((prev) => [...prev, ...newMembers])
    setShowAddModal(false)
  }

  const handleRemoveMember = (userId: number) => {
    setMembers((prev) => prev.filter((m) => m.employee_id !== userId))
  }

  const hasChanges = (() => {
    if (!initialData) return name.trim() !== '' || description !== '' || members.length > 0
    const origIds = new Set(initialData.members?.map((m) => m.employee_id) ?? [])
    const currIds = new Set(members.map((m) => m.employee_id))
    const idsChanged = origIds.size !== currIds.size || [...origIds].some((id) => !currIds.has(id))
    return (
      name.trim() !== (initialData.name ?? '') ||
      (description || '') !== (initialData.description || '') ||
      idsChanged
    )
  })()

  return (
    <>
      <form id="eg-form" onSubmit={handleSubmit} className="flex max-w-2xl flex-col gap-6">
        {/* Name */}
        <div className="flex flex-col gap-2">
          <Label>
            {t('eg.form.name', locale)}
            <span className="text-destructive">*</span>
          </Label>
          <Input
            value={name}
            onChange={(e) => { setName(e.target.value); setNameError('') }}
            placeholder={t('eg.form.name.placeholder', locale)}
            maxLength={50}
            aria-invalid={!!nameError}
          />
          {nameError && <span className="text-xs text-destructive">{nameError}</span>}
        </div>

        {/* Description */}
        <div className="flex flex-col gap-2">
          <Label>{t('eg.form.desc', locale)}</Label>
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={t('eg.form.desc.placeholder', locale)}
            maxLength={256}
            rows={3}
          />
        </div>

        {/* Members */}
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <Label>{t('eg.members.title', locale)}</Label>
            <Button type="button" variant="outline" size="sm" onClick={() => setShowAddModal(true)}>
              <IconPlus size={16} />
              {t('eg.members.add', locale)}
            </Button>
          </div>

          {members.length === 0 ? (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed py-10">
              <p className="text-sm text-muted-foreground">{t('eg.members.empty', locale)}</p>
              <Button type="button" variant="outline" size="sm" onClick={() => setShowAddModal(true)}>
                <IconPlus size={16} />
                {t('eg.members.add', locale)}
              </Button>
            </div>
          ) : (
            <div className="overflow-hidden rounded-lg border">
              <div className="flex h-10 items-center gap-4 bg-muted px-4">
                <div className="min-w-0 flex-1 text-xs font-semibold">
                  {t('eg.members.col.name', locale)}
                </div>
                <div className="w-[160px] shrink-0 text-xs font-semibold">
                  {t('eg.members.col.username', locale)}
                </div>
                <div className="w-[60px] shrink-0 text-xs font-semibold">
                  {t('eg.members.col.actions', locale)}
                </div>
              </div>
              {members.map((m) => (
                <div
                  key={m.employee_id}
                  className="flex h-10 items-center gap-4 border-t px-4"
                >
                  <div className="min-w-0 flex-1 truncate text-sm">
                    {m.display_name || m.username}
                  </div>
                  <div className="w-[160px] shrink-0 truncate text-sm text-muted-foreground">{m.username}</div>
                  <div className="w-[60px] shrink-0">
                    <Button
                      type="button"
                      variant="link"
                      size="xs"
                      className="text-destructive hover:text-destructive/80 p-0"
                      onClick={() => handleRemoveMember(m.employee_id)}
                    >
                      {t('eg.members.remove', locale)}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Hidden submit trigger for sticky bar */}
        <button type="submit" className="hidden" />
      </form>

      {/* Save button disabled state - exposed via data attribute */}
      <input type="hidden" id="eg-has-changes" value={hasChanges ? '1' : '0'} />

      {showAddModal && (
        <AddMemberModal
          existingIds={existingMemberIds}
          onConfirm={handleAddMembers}
          onCancel={() => setShowAddModal(false)}
        />
      )}
    </>
  )
}
