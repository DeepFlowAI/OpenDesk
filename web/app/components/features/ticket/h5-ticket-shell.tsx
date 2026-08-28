'use client'

import { useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowLeft, IconChevronDown, IconLogout } from '@tabler/icons-react'

import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { avatarBackgroundForName, singleAvatarLetter } from '@/lib/avatar-fallback'
import { LANGUAGE_OPTIONS } from '@/lib/languages'
import { cn } from '@/lib/utils'

type Props = {
  title: string
  backLabel?: string
  onBack?: () => void
  action?: ReactNode
  children: ReactNode
  footer?: ReactNode
  contentClassName?: string
}

export function H5TicketShell({
  title,
  backLabel,
  onBack,
  action,
  children,
  footer,
  contentClassName,
}: Props) {
  return (
    <div className="flex h-full min-h-0 flex-col bg-background text-foreground">
      <header className="relative z-30 flex h-14 shrink-0 items-center justify-between border-b border-border bg-background px-4">
        <div className="flex w-24 items-center">
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              aria-label={backLabel ?? 'Back'}
              className="flex h-11 min-w-11 items-center justify-start rounded-md text-muted-foreground transition-colors active:opacity-60"
            >
              <IconArrowLeft size={20} />
            </button>
          )}
        </div>
        <h1 className="min-w-0 flex-1 truncate px-2 text-center font-display text-base font-semibold">
          {title}
        </h1>
        <div className="flex w-24 items-center justify-end gap-1">
          {action}
          <H5AccountMenu />
        </div>
      </header>

      <main className={cn('min-h-0 flex-1 overflow-y-auto overflow-x-hidden', contentClassName)}>
        {children}
      </main>
      {footer}
    </div>
  )
}

function H5AccountMenu() {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const { user, clearAuth } = useAuthStore()
  const { locale, setLocale } = useLocaleStore()
  const displayName = user?.name || user?.display_name || user?.username || 'U'
  const avatarUrl = user?.avatar

  const logout = () => {
    clearAuth()
    router.replace('/login')
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={locale === 'zh' ? '账号菜单' : 'Account menu'}
        className="flex h-11 min-w-11 items-center justify-end gap-1 active:opacity-60"
      >
        <span
          className="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full text-xs font-semibold text-white"
          style={!avatarUrl ? { backgroundColor: avatarBackgroundForName(displayName) } : undefined}
        >
          {avatarUrl ? <img src={avatarUrl} alt="" className="h-full w-full object-cover" /> : singleAvatarLetter(displayName)}
        </span>
        <IconChevronDown size={14} className="text-muted-foreground" />
      </button>

      {open && (
        <>
          <button
            type="button"
            aria-label={locale === 'zh' ? '关闭账号菜单' : 'Close account menu'}
            className="fixed inset-0 z-40 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 top-full z-50 mt-1 w-48 rounded-lg border border-border bg-popover p-1 shadow-lg">
            <p className="truncate border-b border-border px-3 py-2 text-sm font-medium">{displayName}</p>
            <div className="max-h-60 overflow-y-auto px-1 py-1">
              <div className="flex flex-col gap-0.5">
                {LANGUAGE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setLocale(opt.value)}
                    className={cn(
                      'flex h-9 w-full items-center rounded-md px-3 text-xs transition-colors',
                      locale === opt.value
                        ? 'bg-muted font-medium text-foreground'
                        : 'text-muted-foreground hover:bg-muted',
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
            <button
              type="button"
              onClick={logout}
              className="flex h-10 w-full items-center gap-2 rounded-md px-3 text-sm text-muted-foreground transition-colors hover:bg-muted"
            >
              <IconLogout size={16} />
              {locale === 'zh' ? '退出登录' : 'Sign out'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
