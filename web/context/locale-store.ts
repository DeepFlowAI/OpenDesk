import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Locale = 'zh' | 'en'

type LocaleState = {
  locale: Locale
  _hydrated: boolean
  setLocale: (locale: Locale) => void
}

const DEFAULT_LOCALE: Locale = 'zh'

function detectBrowserLocale(): Locale {
  if (typeof navigator === 'undefined') return DEFAULT_LOCALE
  const lang = navigator.language.toLowerCase()
  return lang.startsWith('zh') ? 'zh' : 'en'
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
              state.locale = detectBrowserLocale()
            }
          }
          state._hydrated = true
        }
      },
      partialize: (state) => ({ locale: state.locale } as unknown as LocaleState),
    }
  )
)
