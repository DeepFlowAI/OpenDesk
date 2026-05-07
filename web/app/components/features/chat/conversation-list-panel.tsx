'use client'

import { useState, useRef, useEffect } from 'react'
import { IconChevronDown } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { useUpdateAgentStatus } from '@/service/use-conversations'
import { t } from '@/utils/i18n'
import type { Conversation, AgentStatus, AgentStats } from '@/models/conversation'

type Props = {
  conversations: Conversation[]
  selectedId: number | null
  onSelect: (id: number) => void
  agentStatus: AgentStatus | null
  agentStats: AgentStats | null
}

const STATUS_OPTIONS = [
  { value: 'online', colorClass: 'bg-success', labelKey: 'ws.status.online' },
  { value: 'busy', colorClass: 'bg-warning', labelKey: 'ws.status.busy' },
  { value: 'offline', colorClass: 'bg-muted-foreground', labelKey: 'ws.status.offline' },
] as const

function formatTime(dateStr: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  if (isToday) {
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
  }
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function ConversationListPanel({ conversations, selectedId, onSelect, agentStatus, agentStats }: Props) {
  const { locale } = useLocaleStore()
  const { user } = useAuthStore()
  const [statusDropdownOpen, setStatusDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const updateStatus = useUpdateAgentStatus()

  const currentStatus = agentStatus?.status || 'offline'
  const currentOption = STATUS_OPTIONS.find((o) => o.value === currentStatus) || STATUS_OPTIONS[2]

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setStatusDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  return (
    <div className="flex w-[280px] shrink-0 flex-col border-r border-[#E5E5E5] bg-[#F5F5F5]">
      {/* 客服状态区 — 2.1 pen: height 56, px 20 */}
      <div className="flex h-14 shrink-0 items-center justify-between px-5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="truncate text-sm font-semibold text-[#1a1a1a]">
            {user?.display_name || user?.username}
          </span>
          <div className="relative shrink-0" ref={dropdownRef}>
            <button
              onClick={() => setStatusDropdownOpen(!statusDropdownOpen)}
              className="flex items-center gap-1.5 rounded-md py-0.5 text-[12px] font-medium transition-colors hover:bg-black/[0.04]"
            >
              <span
                className={cn(
                  'h-2 w-2 rounded-full',
                  currentStatus === 'online' && 'bg-[#22C55E]',
                  currentStatus === 'busy' && 'bg-amber-500',
                  currentStatus === 'offline' && 'bg-neutral-400',
                )}
              />
              <span
                className={cn(
                  currentStatus === 'online' && 'text-[#22C55E]',
                  currentStatus !== 'online' && 'text-[#737373]',
                )}
              >
                {t(currentOption.labelKey, locale)}
              </span>
              <IconChevronDown size={14} className="text-[#999999]" />
            </button>
            {statusDropdownOpen && (
              <div className="absolute left-0 top-full z-50 mt-1 w-32 rounded-lg border border-[#E5E5E5] bg-white py-1 shadow-lg">
                {STATUS_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => {
                      updateStatus.mutate(opt.value)
                      setStatusDropdownOpen(false)
                    }}
                    className={cn(
                      'flex w-full items-center gap-2 px-3 py-2 text-xs transition-colors hover:bg-[#F5F5F5]',
                      currentStatus === opt.value && 'font-medium',
                    )}
                  >
                    <span className={cn('h-2 w-2 rounded-full', opt.colorClass)} />
                    {t(opt.labelKey, locale)}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        {agentStats && (
          <span className="inline-flex shrink-0 items-center gap-1.5 rounded-[14px] bg-[#EBEBEB] px-3 py-1 text-[12px]">
            <span className="font-medium text-[#737373]">{t('ws.chat.receptionLabel', locale)}</span>
            <span className="font-semibold text-[#1a1a1a]">
              {agentStats.current_count} / {agentStats.max_concurrent}
            </span>
          </span>
        )}
      </div>

      {/* 会话列表 — pen: gap 4, padding 4 8 */}
      <div className="flex-1 overflow-y-auto px-2 py-1">
        {conversations.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-[#737373]">{t('ws.chat.noConversations', locale)}</p>
          </div>
        ) : (
          conversations.map((conv) => {
            const selected = selectedId === conv.id
            return (
              <button
                key={conv.id}
                onClick={() => onSelect(conv.id)}
                className={cn(
                  'mb-1 flex min-h-[72px] w-full items-center gap-3 rounded-[20px] px-4 py-2 text-left transition-colors',
                  selected
                    ? 'border border-[#E0E0E0] bg-[#FAFAFA]'
                    : 'border border-transparent hover:bg-white/60',
                )}
              >
                <div
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-base font-medium text-white"
                  style={{ backgroundColor: conv.visitor?.avatar_color || '#4A8C5C' }}
                >
                  {(conv.visitor?.name || '访').charAt(0)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={cn(
                        'truncate text-sm text-[#1a1a1a]',
                        selected ? 'font-semibold' : 'font-medium',
                      )}
                    >
                      {conv.visitor?.name || `#${conv.id}`}
                    </span>
                    <span className="shrink-0 text-[12px] text-[#999999]">
                      {formatTime(conv.last_message_at)}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <span className="truncate text-[13px] text-[#737373]">
                      {conv.last_message_preview || ''}
                    </span>
                    {conv.unread_count > 0 && (
                      <span className="flex h-[18px] min-w-[18px] shrink-0 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium text-white">
                        {conv.unread_count > 99 ? '99+' : conv.unread_count}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}
