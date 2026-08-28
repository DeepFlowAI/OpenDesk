'use client'

import type { ReactElement } from 'react'
import { IconChevronDown, IconUsersGroup, IconX } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useEmployeeGroups } from '@/service/use-employee-groups'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export type PoolPickerProps = {
  groupIds: number[]
  onGroupIdsChange: (ids: number[]) => void
  /** Custom trigger rendered via Base UI `render` prop; defaults to the picker button. */
  trigger?: ReactElement
}

export function PoolPicker({ groupIds, onGroupIdsChange, trigger }: PoolPickerProps) {
  const { locale } = useLocaleStore()
  const { data: groupsData } = useEmployeeGroups({ per_page: 200 })
  const groups = groupsData?.items ?? []
  const selectedGroups = groups.filter((g) => groupIds.includes(g.id))

  const toggleGroup = (id: number, checked: boolean) => {
    if (checked) onGroupIdsChange([...groupIds, id])
    else onGroupIdsChange(groupIds.filter((x) => x !== id))
  }

  const defaultTrigger =
    groupIds.length === 0 ? (
      <button
        type="button"
        className="flex h-9 min-w-[180px] items-center justify-between rounded-md border border-dashed border-border bg-muted/20 px-3 text-sm text-muted-foreground"
      >
        <span>{t('scheduling.board.poolPlaceholder', locale)}</span>
        <IconChevronDown size={14} />
      </button>
    ) : (
      <button
        type="button"
        className="flex h-9 items-center gap-2 rounded-md border border-border bg-background px-2.5 text-sm"
      >
        <span className="flex max-w-[320px] items-center gap-1 overflow-hidden">
          {selectedGroups.map((g) => (
            <span
              key={g.id}
              className="inline-flex shrink-0 items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
            >
              <IconUsersGroup size={12} />
              <span className="max-w-[120px] truncate">{g.name}</span>
              <span
                role="button"
                tabIndex={-1}
                aria-label={`Remove ${g.name}`}
                className="opacity-60 hover:opacity-100"
                onClick={(e) => {
                  e.stopPropagation()
                  toggleGroup(g.id, false)
                }}
              >
                <IconX size={12} />
              </span>
            </span>
          ))}
        </span>
        <IconChevronDown size={14} className="text-muted-foreground" />
      </button>
    )

  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={trigger ?? defaultTrigger} />
      <DropdownMenuContent align="start" className="w-64">
        {groups.length === 0 ? (
          <div className="px-3 py-2 text-xs text-muted-foreground">
            {t('scheduling.board.groupEmpty', locale)}
          </div>
        ) : (
          groups.map((g) => (
            <DropdownMenuCheckboxItem
              key={g.id}
              checked={groupIds.includes(g.id)}
              onCheckedChange={(checked) => toggleGroup(g.id, checked)}
              closeOnClick={false}
            >
              {t('scheduling.board.groupOption', locale, {
                name: g.name,
                count: g.member_count,
              })}
            </DropdownMenuCheckboxItem>
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
