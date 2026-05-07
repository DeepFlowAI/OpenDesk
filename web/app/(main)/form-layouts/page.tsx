'use client'

import { useRouter } from 'next/navigation'
import { IconArrowRight } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useFormLayouts } from '@/service/use-form-layouts'

function SceneBadge({ scene, locale }: { scene: string; locale: 'zh' | 'en' }) {
  const key = scene === 'new_ticket' ? 'fl.scene.new_ticket' : 'fl.scene.ticket_detail'
  const bg =
    scene === 'new_ticket'
      ? 'bg-info/10 text-info'
      : 'bg-purple-50 text-purple-700'
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${bg}`}>
      {t(key, locale)}
    </span>
  )
}

function formatDate(iso: string, locale: 'zh' | 'en') {
  const d = new Date(iso)
  if (locale === 'zh') {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }
  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function FormLayoutsListPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const { data, isLoading } = useFormLayouts({ page: 1, per_page: 50 })

  const items = data?.items ?? []

  return (
    <div className="flex w-full flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">{t('fl.title', locale)}</h1>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('fl.loading', locale)}</p>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <p className="text-sm text-muted-foreground">{t('fl.empty', locale)}</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <div style={{ minWidth: 700 }}>
            {/* Table header */}
            <div className="flex h-14 items-center gap-6 rounded-t-lg bg-muted px-6">
              <div className="w-[60px] shrink-0">
                <span className="text-sm font-semibold text-foreground/80">{t('fl.col.index', locale)}</span>
              </div>
              <div className="min-w-[200px] flex-1">
                <span className="text-sm font-semibold text-foreground/80">{t('fl.col.name', locale)}</span>
              </div>
              <div className="w-[140px] shrink-0">
                <span className="text-sm font-semibold text-foreground/80">{t('fl.col.scene', locale)}</span>
              </div>
              <div className="w-[180px] shrink-0">
                <span className="text-sm font-semibold text-foreground/80">{t('fl.col.updatedAt', locale)}</span>
              </div>
              <div className="w-[120px] shrink-0 text-right">
                <span className="text-sm font-semibold text-foreground/80">{t('fl.col.actions', locale)}</span>
              </div>
            </div>

            {/* Table rows */}
            {items.map((layout, idx) => (
              <div
                key={layout.id}
                className="flex h-14 items-center gap-6 border-t border-border px-6"
              >
                <div className="w-[60px] shrink-0 text-sm text-muted-foreground">{idx + 1}</div>
                <div className="min-w-[200px] flex-1 truncate text-sm font-medium text-foreground">
                  {layout.name}
                </div>
                <div className="w-[140px] shrink-0">
                  <SceneBadge scene={layout.scene} locale={locale} />
                </div>
                <div className="w-[180px] shrink-0 text-sm text-muted-foreground">
                  {formatDate(layout.updated_at, locale)}
                </div>
                <div className="flex w-[120px] shrink-0 items-center justify-end">
                  <button
                    onClick={() => router.push(`/form-layouts/${layout.id}`)}
                    className="flex items-center gap-1 text-sm font-medium text-info transition-colors hover:text-info/80"
                  >
                    {t('fl.action.enter', locale)}
                    <IconArrowRight size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
