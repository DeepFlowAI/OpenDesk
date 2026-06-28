'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { IconLogout } from '@tabler/icons-react'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { avatarBackgroundForName, singleAvatarLetter } from '@/lib/avatar-fallback'
import { t } from '@/utils/i18n'

export function UserDropdown() {
  const router = useRouter()
  const { user, clearAuth } = useAuthStore()
  const { locale } = useLocaleStore()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleLogout = () => {
    clearAuth()
    router.replace('/login')
  }

  const displayName = user?.name || user?.display_name || user?.username || 'U'
  const accountName = user?.username || ''
  const showAccountName = Boolean(accountName && accountName !== displayName)
  const avatarLetter = singleAvatarLetter(displayName)
  const avatarUrl = user?.avatar
  const letterBg = avatarBackgroundForName(displayName)

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full text-sm font-semibold text-white transition-opacity hover:opacity-90"
        style={!avatarUrl ? { backgroundColor: letterBg } : undefined}
      >
        {avatarUrl ? (
          <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
        ) : (
          avatarLetter
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-56 rounded-lg border border-border bg-white py-1 shadow-lg">
          <div className="border-b border-border px-4 py-3">
            <p className="truncate text-sm font-medium text-foreground">{displayName}</p>
            {showAccountName && (
              <p className="mt-0.5 truncate text-xs text-muted-foreground">{accountName}</p>
            )}
          </div>
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <IconLogout size={16} />
            {t('ws.user.logout', locale)}
          </button>
        </div>
      )}
    </div>
  )
}
