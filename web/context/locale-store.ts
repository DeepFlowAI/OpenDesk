import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { DEFAULT_LOCALE, detectBrowserLocale, type Locale } from '@/lib/languages'

export type { Locale } from '@/lib/languages'

type LocaleState = {
  locale: Locale
  _hydrated: boolean
  setLocale: (locale: Locale) => void
}

export const useLocaleStore = create<LocaleState>()(
  persist(
    (set) => ({
      locale: DEFAULT_LOCALE,
      _hydrated: false,
      setLocale: (locale) => set({ locale }),
    }),
    {
      name: 'app-locale',
      onRehydrateStorage: () => (state) => {
        if (state) {
          if (!state._hydrated) {
            const stored = localStorage.getItem('app-locale')
            if (!stored || !JSON.parse(stored)?.state?.locale) {
              state.locale = detectBrowserLocale('en')
            }
          }
          state._hydrated = true
        }
      },
      partialize: (state) => ({ locale: state.locale } as unknown as LocaleState),
    }
  )
)
