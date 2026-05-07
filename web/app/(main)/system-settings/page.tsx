'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { IconChevronDown, IconCheck, IconSearch } from '@tabler/icons-react'
import { useSystemSettings, useUpdateSystemSettings } from '@/service/use-system-settings'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

const LANGUAGE_OPTIONS = [
  { value: 'zh', label: 'zh 中文' },
  { value: 'en', label: 'en English' },
]

const TIMEZONE_OPTIONS = [
  { value: 'Asia/Shanghai', label: 'Asia/Shanghai (UTC+8)' },
  { value: 'Asia/Tokyo', label: 'Asia/Tokyo (UTC+9)' },
  { value: 'Asia/Singapore', label: 'Asia/Singapore (UTC+8)' },
  { value: 'Asia/Hong_Kong', label: 'Asia/Hong_Kong (UTC+8)' },
  { value: 'Asia/Kolkata', label: 'Asia/Kolkata (UTC+5:30)' },
  { value: 'Asia/Dubai', label: 'Asia/Dubai (UTC+4)' },
  { value: 'Europe/London', label: 'Europe/London (UTC+0)' },
  { value: 'Europe/Paris', label: 'Europe/Paris (UTC+1)' },
  { value: 'Europe/Berlin', label: 'Europe/Berlin (UTC+1)' },
  { value: 'Europe/Moscow', label: 'Europe/Moscow (UTC+3)' },
  { value: 'America/New_York', label: 'America/New_York (UTC-5)' },
  { value: 'America/Chicago', label: 'America/Chicago (UTC-6)' },
  { value: 'America/Denver', label: 'America/Denver (UTC-7)' },
  { value: 'America/Los_Angeles', label: 'America/Los_Angeles (UTC-8)' },
  { value: 'America/Sao_Paulo', label: 'America/Sao_Paulo (UTC-3)' },
  { value: 'Pacific/Auckland', label: 'Pacific/Auckland (UTC+12)' },
  { value: 'Australia/Sydney', label: 'Australia/Sydney (UTC+11)' },
  { value: 'UTC', label: 'UTC (UTC+0)' },
]

type SelectOption = { value: string; label: string }

function SimpleSelect({
  options,
  value,
  onChange,
  searchable = false,
  searchPlaceholder,
}: {
  options: SelectOption[]
  value: string
  onChange: (v: string) => void
  searchable?: boolean
  searchPlaceholder?: string
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const selected = options.find((o) => o.value === value)

  const filtered = searchable && search
    ? options.filter((o) => o.label.toLowerCase().includes(search.toLowerCase()))
    : options

  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (ref.current && !ref.current.contains(e.target as Node)) {
      setOpen(false)
      setSearch('')
    }
  }, [])

  useEffect(() => {
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [handleClickOutside])

  useEffect(() => {
    if (open && searchable && searchRef.current) {
      searchRef.current.focus()
    }
  }, [open, searchable])

  return (
    <div ref={ref} className="relative w-[400px]">
      <button
        type="button"
        onClick={() => { setOpen(!open); setSearch('') }}
        className="flex h-10 w-full items-center justify-between rounded-lg border border-border bg-white px-3 text-sm text-foreground/80 transition-colors hover:border-border"
      >
        <span>{selected?.label ?? ''}</span>
        <IconChevronDown size={18} className="text-muted-foreground" />
      </button>

      {open && (
        <div className="absolute top-[calc(100%+4px)] z-20 w-full rounded-lg border border-border bg-white py-1 shadow-lg">
          {searchable && (
            <div className="flex items-center gap-2 border-b border-border px-3 py-2">
              <IconSearch size={16} className="text-muted-foreground" />
              <input
                ref={searchRef}
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={searchPlaceholder}
                className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none"
              />
            </div>
          )}
          <div className="max-h-[240px] overflow-y-auto">
            {filtered.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => { onChange(opt.value); setOpen(false); setSearch('') }}
                className="flex w-full items-center justify-between px-3 py-2 text-sm text-foreground/80 transition-colors hover:bg-accent"
              >
                <span>{opt.label}</span>
                {opt.value === value && <IconCheck size={16} className="text-foreground" />}
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="px-3 py-4 text-center text-sm text-muted-foreground">
                No results
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function SystemSettingsPage() {
  const { locale } = useLocaleStore()
  const { data, isLoading } = useSystemSettings()
  const updateMutation = useUpdateSystemSettings()

  const [language, setLanguage] = useState('zh')
  const [timezone, setTimezone] = useState('Asia/Shanghai')
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    if (data) {
      setLanguage(data.default_language)
      setTimezone(data.default_timezone)
    }
  }, [data])

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000)
      return () => clearTimeout(timer)
    }
  }, [toast])

  const handleSave = async () => {
    try {
      await updateMutation.mutateAsync({
        default_language: language,
        default_timezone: timezone,
      })
      setToast({ type: 'success', text: t('settings.saveSuccess', locale) })
    } catch {
      setToast({ type: 'error', text: t('settings.saveFailed', locale) })
    }
  }

  if (isLoading) {
    return (
      <div className="text-sm text-muted-foreground">{t('settings.loading', locale)}</div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">
        {t('settings.title', locale)}
      </h1>

      {toast && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            toast.type === 'success'
              ? 'border-green-200 bg-green-50 text-green-700'
              : 'border-red-200 bg-red-50 text-red-700'
          }`}
        >
          {toast.text}
        </div>
      )}

      <div className="flex flex-col gap-4">
        {/* Language */}
        <div className="flex flex-col gap-2">
          <label className="text-sm font-medium text-foreground">
            {t('settings.language', locale)}
          </label>
          <SimpleSelect
            options={LANGUAGE_OPTIONS}
            value={language}
            onChange={setLanguage}
          />
        </div>

        {/* Timezone */}
        <div className="flex flex-col gap-2">
          <label className="text-sm font-medium text-foreground">
            {t('settings.timezone', locale)}
          </label>
          <SimpleSelect
            options={TIMEZONE_OPTIONS}
            value={timezone}
            onChange={setTimezone}
            searchable
            searchPlaceholder={t('settings.tz.search', locale)}
          />
        </div>
      </div>

      {/* Save button */}
      <div>
        <button
          type="button"
          onClick={handleSave}
          disabled={updateMutation.isPending}
          className="flex h-10 items-center justify-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-60"
        >
          {updateMutation.isPending
            ? t('settings.saving', locale)
            : t('settings.save', locale)}
        </button>
      </div>
    </div>
  )
}
