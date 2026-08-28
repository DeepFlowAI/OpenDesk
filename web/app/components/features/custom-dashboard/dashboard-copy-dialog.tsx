'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { DashboardListItem } from '@/models/custom-dashboard'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

export function DashboardCopyDialog({
  dashboard,
  loading,
  onClose,
  onCopy,
}: {
  dashboard: DashboardListItem | null
  loading: boolean
  onClose: () => void
  onCopy: (slug: string) => Promise<void>
}) {
  const { locale } = useLocaleStore()
  const [slug, setSlug] = useState('')
  const valid = /^[a-z][a-z0-9_]{1,63}$/.test(slug)

  useEffect(() => {
    setSlug(dashboard ? `${dashboard.slug}_copy`.slice(0, 64) : '')
  }, [dashboard])

  if (!dashboard) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/20" role="presentation" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-border bg-popover p-6 shadow-xl" role="dialog" aria-modal="true" aria-labelledby="copy-dashboard-title" onClick={(event) => event.stopPropagation()}>
        <h2 id="copy-dashboard-title" className="text-base font-semibold text-foreground">{t('cd.copyTitle', locale)}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{dashboard.name}</p>
        <div className="mt-5 grid gap-2">
          <Label htmlFor="copy-dashboard-slug">{t('cd.slug', locale)}</Label>
          <Input id="copy-dashboard-slug" value={slug} maxLength={64} onChange={(event) => setSlug(event.target.value.toLowerCase())} className="font-mono" aria-invalid={!valid} />
          {!valid && <p className="text-xs text-destructive">{t('cd.validation.slug', locale)}</p>}
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose} disabled={loading}>{t('cd.cancel', locale)}</Button>
          <Button type="button" onClick={() => void onCopy(slug)} disabled={!valid || loading}>{loading ? t('cd.copying', locale) : t('cd.copy', locale)}</Button>
        </div>
      </div>
    </div>
  )
}
