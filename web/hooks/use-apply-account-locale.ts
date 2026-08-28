'use client'

import { useEffect } from 'react'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { isLocale, type Locale } from '@/lib/languages'
import { useSystemSettings } from '@/service/use-system-settings'

function toLocale(value: string | undefined): Locale | null {
  return isLocale(value) ? value : null
}

/**
 * Drive the UI locale from the account configuration once logged in:
 * explicit employee language wins; "system" resolves to the tenant default.
 * localStorage / browser locale only apply before login.
 */
export function useApplyAccountLocale() {
  const user = useAuthStore((state) => state.user)
  const setLocale = useLocaleStore((state) => state.setLocale)
  const followSystem = user?.default_language === 'system'
  const { data: systemSettings } = useSystemSettings(followSystem)

  useEffect(() => {
    if (!user) return
    const explicit = toLocale(user.default_language)
    if (explicit) {
      setLocale(explicit)
      return
    }
    if (followSystem) {
      const systemDefault = toLocale(systemSettings?.default_language)
      if (systemDefault) setLocale(systemDefault)
    }
  }, [user, followSystem, systemSettings, setLocale])
}
