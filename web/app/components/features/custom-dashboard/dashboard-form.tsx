'use client'

import { useState } from 'react'
import { IconArrowLeft } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { DashboardIcon, DASHBOARD_ICON_OPTIONS } from './dashboard-icon'
import { validateDashboardForm } from '@/utils/custom-dashboard'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

export type DashboardFormValue = {
  name: string
  slug: string
  icon: string
  description: string
}

export function DashboardForm({
  title,
  initialValue,
  submitting,
  onBack,
  onSubmit,
}: {
  title: string
  initialValue?: Partial<DashboardFormValue>
  submitting: boolean
  onBack: () => void
  onSubmit: (value: DashboardFormValue) => Promise<void>
}) {
  const { locale } = useLocaleStore()
  const [value, setValue] = useState<DashboardFormValue>({
    name: initialValue?.name ?? '',
    slug: initialValue?.slug ?? '',
    icon: initialValue?.icon ?? 'chart-bar',
    description: initialValue?.description ?? '',
  })
  const [submitted, setSubmitted] = useState(false)
  const errors = validateDashboardForm({ ...value, components: [] }, true)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setSubmitted(true)
    if (Object.keys(errors).length > 0) return
    await onSubmit(value)
  }

  return (
    <form onSubmit={submit} className="flex min-h-full flex-col">
      <div className="sticky top-0 z-10 -mx-8 -mt-8 flex h-16 items-center justify-between border-b border-border bg-background px-8">
        <div className="flex items-center gap-3">
          <Button type="button" variant="ghost" size="icon" onClick={onBack} aria-label={t('cd.back', locale)}>
            <IconArrowLeft />
          </Button>
          <h1 className="text-xl font-semibold text-foreground">{title}</h1>
        </div>
        <Button type="submit" disabled={submitting}>
          {submitting ? t('cd.creating', locale) : t('cd.createAndEdit', locale)}
        </Button>
      </div>

      <div className="mx-auto mt-8 w-full max-w-2xl rounded-xl border border-border bg-card p-6">
        <div className="grid gap-5">
          <div className="grid gap-2">
            <Label htmlFor="dashboard-name">{t('cd.name', locale)}</Label>
            <Input id="dashboard-name" maxLength={80} value={value.name} onChange={(event) => setValue({ ...value, name: event.target.value })} aria-invalid={submitted && !!errors.name} />
            {submitted && errors.name && <p className="text-xs text-destructive">{t('cd.validation.name', locale)}</p>}
          </div>
          <div className="grid gap-2">
            <Label htmlFor="dashboard-slug">{t('cd.slug', locale)}</Label>
            <Input id="dashboard-slug" maxLength={64} value={value.slug} onChange={(event) => setValue({ ...value, slug: event.target.value.toLowerCase() })} className="font-mono" aria-invalid={submitted && !!errors.slug} />
            <p className="text-xs text-muted-foreground">{t('cd.slugHint', locale)}</p>
            {submitted && errors.slug && <p className="text-xs text-destructive">{t('cd.validation.slug', locale)}</p>}
          </div>
          <fieldset className="grid gap-2">
            <legend className="text-sm font-medium text-foreground">{t('cd.icon', locale)}</legend>
            <div className="flex gap-2">
              {DASHBOARD_ICON_OPTIONS.map((icon) => (
                <Button key={icon} type="button" variant={value.icon === icon ? 'secondary' : 'outline'} size="icon-lg" onClick={() => setValue({ ...value, icon })} aria-label={icon}>
                  <DashboardIcon name={icon} />
                </Button>
              ))}
            </div>
          </fieldset>
          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="dashboard-description">{t('cd.description', locale)}</Label>
              <span className="text-xs text-muted-foreground">{value.description.length}/300</span>
            </div>
            <Textarea id="dashboard-description" maxLength={300} rows={4} value={value.description} onChange={(event) => setValue({ ...value, description: event.target.value })} />
          </div>
        </div>
      </div>
    </form>
  )
}
