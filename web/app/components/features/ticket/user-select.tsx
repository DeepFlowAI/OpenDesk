'use client'

import { useEffect, useMemo, useState } from 'react'
import { IconChevronDown, IconX } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useQueryUsers, useUser } from '@/service/use-users'
import type { User } from '@/models/user'

type UserSelectProps = {
  value: number | number[] | null | undefined
  onChange: (value: number | number[] | null) => void
  multi?: boolean
  disabled?: boolean
  placeholder?: string
  className?: string
  dropdownPlacement?: 'top' | 'bottom'
}

function userDisplayName(user: User | undefined, fallbackId?: number): string {
  if (!user) return fallbackId ? `User #${fallbackId}` : ''
  const secondary = user.public_id || user.phone || user.email
  return secondary ? `${user.name} · ${secondary}` : user.name
}

export function UserSelect({
  value,
  onChange,
  multi = false,
  disabled = false,
  placeholder = 'Search users...',
  className,
  dropdownPlacement = 'bottom',
}: UserSelectProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 250)
    return () => window.clearTimeout(timer)
  }, [search])

  const selectedIds = useMemo(() => {
    if (multi) return Array.isArray(value) ? value : []
    return typeof value === 'number' ? [value] : []
  }, [multi, value])

  const { data: selectedUser } = useUser(!multi && selectedIds[0] ? selectedIds[0] : 0)
  const { data: usersData, isLoading } = useQueryUsers({
    search: debouncedSearch || null,
    page: 1,
    per_page: 20,
  })

  const users = usersData?.items ?? []
  const userMap = useMemo(() => {
    const map = new Map<number, User>()
    for (const user of users) map.set(user.id, user)
    if (selectedUser) map.set(selectedUser.id, selectedUser)
    return map
  }, [users, selectedUser])

  const selectedLabel = useMemo(() => {
    if (multi) {
      if (selectedIds.length === 0) return ''
      return selectedIds.map((id) => userDisplayName(userMap.get(id), id)).join(', ')
    }
    const id = selectedIds[0]
    return id ? userDisplayName(userMap.get(id), id) : ''
  }, [multi, selectedIds, userMap])

  const toggleSelection = (userId: number) => {
    if (multi) {
      const exists = selectedIds.includes(userId)
      const next = exists ? selectedIds.filter((id) => id !== userId) : [...selectedIds, userId]
      onChange(next)
      return
    }
    onChange(userId)
    setOpen(false)
    setSearch('')
  }

  const clearValue = () => {
    onChange(multi ? [] : null)
    setSearch('')
  }

  return (
    <div className={cn('relative', className)}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          'flex h-9 w-full items-center gap-2 rounded-md border border-input bg-transparent px-3 text-left text-sm text-foreground outline-none transition-colors',
          'focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50',
        )}
      >
        <span className={cn('min-w-0 flex-1 truncate', !selectedLabel && 'text-muted-foreground')}>
          {selectedLabel || placeholder}
        </span>
        {!disabled && selectedIds.length > 0 && (
          <span
            onClick={(event) => {
              event.stopPropagation()
              clearValue()
            }}
            className="rounded text-muted-foreground hover:text-foreground"
          >
            <IconX size={14} />
          </span>
        )}
        <IconChevronDown size={14} className="shrink-0 text-muted-foreground" />
      </button>

      {open && !disabled && (
        <div
          className={cn(
            'absolute z-50 w-full rounded-md border border-border bg-background p-2 shadow-lg',
            dropdownPlacement === 'top' ? 'bottom-full mb-1' : 'mt-1',
          )}
        >
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={placeholder}
            className="mb-2 h-8 w-full rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring"
            autoFocus
          />
          <div className="max-h-56 overflow-y-auto">
            {isLoading ? (
              <div className="px-2 py-2 text-sm text-muted-foreground">Loading...</div>
            ) : users.length === 0 ? (
              <div className="px-2 py-2 text-sm text-muted-foreground">No users</div>
            ) : (
              users.map((user) => {
                const selected = selectedIds.includes(user.id)
                return (
                  <button
                    type="button"
                    key={user.id}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => toggleSelection(user.id)}
                    className={cn(
                      'flex w-full flex-col rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-accent',
                      selected && 'bg-accent',
                    )}
                  >
                    <span className="font-medium text-foreground">{user.name}</span>
                    {(user.public_id || user.phone || user.email) && (
                      <span className="text-xs text-muted-foreground">
                        {user.public_id || user.phone || user.email}
                      </span>
                    )}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
