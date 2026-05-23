'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconGripVertical, IconHistory, IconPencil, IconPlus, IconSettings, IconTrash } from '@tabler/icons-react'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { Switch } from '@/components/ui/switch'
import { useChannels } from '@/service/use-channels'
import {
  useDeleteWelcomeMessageRule,
  usePatchWelcomeMessageRuleEnabled,
  useReorderWelcomeMessageRules,
  useWelcomeMessageRules,
} from '@/service/use-welcome-message-rules'
import {
  usePatchSatisfactionSurveyEnabled,
  useSatisfactionSurveyConfig,
} from '@/service/use-satisfaction-survey'
import type { Channel } from '@/models/channel'
import type { SatisfactionSurveyConfig, SatisfactionSurveyType } from '@/models/satisfaction-survey'
import { getActiveTriggerModes } from '@/models/satisfaction-survey'
import type {
  WelcomeMessageCondition,
  WelcomeMessageRuleListItem,
} from '@/models/welcome-message-rule'

function formatDate(iso: string | null, locale: Locale): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (value: number) => String(value).padStart(2, '0')
  if (locale === 'zh') {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
  }
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function opLabel(operator: string, locale: Locale): string {
  if (operator === 'eq') return t('wm.cond.op.eq', locale)
  if (operator === 'ne') return t('wm.cond.op.ne', locale)
  if (operator === 'any_eq') return t('wm.cond.op.anyEq', locale)
  if (operator === 'any_ne') return t('wm.cond.op.anyNe', locale)
  return operator
}

function conditionSummary(
  conditions: WelcomeMessageCondition[],
  channelById: Record<string, Channel>,
  locale: Locale,
): string {
  if (!conditions || conditions.length === 0) return t('wm.cond.allWebSdk', locale)
  return conditions
    .map((condition) => {
      if (condition.condition_type === 'channel') {
        return `${t('wm.cond.type.channel', locale)} ${opLabel(condition.operator, locale)} ${t('wm.cond.value.channel.webSdk', locale)}`
      }
      const values = Array.isArray(condition.value) ? condition.value : [condition.value]
      const names = values
        .map((value) => channelById[String(value)]?.name || t('wm.cond.value.sdk.missing.short', locale, { id: String(value) }))
        .join(', ')
      return `${t('wm.cond.type.webSdk', locale)} ${opLabel(condition.operator, locale)} ${names}`
    })
    .join(' · ')
}

function satText(locale: Locale, key: string) {
  return t(`sat.${key}`, locale)
}

function satisfactionTypeLabel(type: SatisfactionSurveyType, locale: Locale): string {
  return type === 'service' ? satText(locale, 'service') : satText(locale, 'product')
}

function satisfactionSummary(config: SatisfactionSurveyConfig, locale: Locale) {
  const types: SatisfactionSurveyType[] = []
  if (config.service.enabled) types.push('service')
  if (config.product.enabled) types.push('product')

  const ratingModes = types.map((type) => {
    const settings = type === 'service' ? config.service : config.product
    return `${satisfactionTypeLabel(type, locale)}: ${satText(locale, `ratingMode.${settings.rating_mode}`)}`
  })

  const triggers = getActiveTriggerModes(config.triggers).map((mode) =>
    satText(locale, `trigger.mode.${mode}`),
  )

  return { types, ratingModes, triggers }
}

function DeleteModal({
  item,
  onCancel,
  onConfirm,
  loading,
}: {
  item: WelcomeMessageRuleListItem
  onCancel: () => void
  onConfirm: () => void
  loading: boolean
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[420px] rounded-xl bg-white p-6">
        <h2 className="text-lg font-semibold text-foreground">{t('wm.delete.title', locale)}</h2>
        <p className="mt-3 text-sm text-muted-foreground">
          {t('wm.delete.confirm', locale, { name: item.name })}
        </p>
        <div className="mt-3 rounded-lg border border-border p-3">
          <p className="text-sm font-medium text-foreground">{item.name}</p>
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
          >
            {t('wm.delete.cancel', locale)}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="h-9 rounded-lg bg-destructive px-4 text-sm font-medium text-white hover:bg-destructive/80 disabled:opacity-50"
          >
            {loading ? '...' : t('wm.delete.ok', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ConversationSettingsPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const perPage = 100
  const { data, isLoading, refetch } = useWelcomeMessageRules({ page: 1, per_page: perPage })
  const {
    data: satisfaction,
    isPending: satisfactionPending,
    isError: satisfactionError,
    refetch: refetchSatisfaction,
  } = useSatisfactionSurveyConfig()
  const { data: channelsData } = useChannels()
  const deleteMut = useDeleteWelcomeMessageRule()
  const reorderMut = useReorderWelcomeMessageRules()
  const patchEnabledMut = usePatchWelcomeMessageRuleEnabled()
  const patchSatisfactionMut = usePatchSatisfactionSurveyEnabled()

  const items = useMemo(() => data?.items ?? [], [data?.items])
  const channels = (channelsData ?? []) as Channel[]
  const channelById = useMemo(
    () => Object.fromEntries(channels.map((channel) => [String(channel.id), channel])),
    [channels],
  )

  const [orderedIds, setOrderedIds] = useState<number[]>([])
  const [deleteTarget, setDeleteTarget] = useState<WelcomeMessageRuleListItem | null>(null)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    setOrderedIds(items.map((item) => item.id))
  }, [items])

  const byId = useMemo(() => Object.fromEntries(items.map((item) => [item.id, item])), [items])
  const displayRows = orderedIds.map((id) => byId[id]).filter(Boolean) as WelcomeMessageRuleListItem[]

  const showToast = (type: 'success' | 'error', text: string) => {
    setToast({ type, text })
    setTimeout(() => setToast(null), 3000)
  }

  const handleDrop = async (toIndex: number) => {
    if (dragIndex == null || dragIndex === toIndex) {
      setDragIndex(null)
      return
    }
    const next = [...orderedIds]
    const [removed] = next.splice(dragIndex, 1)
    next.splice(toIndex, 0, removed)
    setOrderedIds(next)
    setDragIndex(null)
    try {
      await reorderMut.mutateAsync(next)
      showToast('success', t('wm.reorderSuccess', locale))
    } catch {
      showToast('error', t('wm.reorderFailed', locale))
      refetch()
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMut.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
      showToast('success', t('wm.deleteSuccess', locale))
    } catch {
      showToast('error', t('wm.deleteFailed', locale))
    }
  }

  const handleToggleEnabled = async (item: WelcomeMessageRuleListItem) => {
    try {
      await patchEnabledMut.mutateAsync({ id: item.id, enabled: !item.enabled })
      showToast('success', t('wm.toggleSuccess', locale))
    } catch {
      showToast('error', t('wm.toggleFailed', locale))
      refetch()
    }
  }

  const handleToggleSatisfaction = async () => {
    if (!satisfaction?.configured) return
    try {
      await patchSatisfactionMut.mutateAsync(!satisfaction.enabled)
      showToast('success', t('wm.toggleSuccess', locale))
    } catch {
      showToast('error', t('wm.toggleFailed', locale))
      refetchSatisfaction()
    }
  }

  const satisfactionMeta = satisfaction?.configured ? satisfactionSummary(satisfaction, locale) : null

  return (
    <div className="flex flex-col gap-6">
      {toast && (
        <div
          className={`rounded-lg px-4 py-3 text-sm ${
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          }`}
        >
          {toast.text}
        </div>
      )}

      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-foreground">{t('wm.page.title', locale)}</h1>
      </div>

      <section className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">{t('wm.section.welcome', locale)}</h2>
          <button
            type="button"
            onClick={() => router.push('/online-service/conversation-settings/welcome/new')}
            className="flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
          >
            <IconPlus size={18} />
            {t('wm.new', locale)}
          </button>
        </div>

        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t('wm.loading', locale)}</p>
        ) : displayRows.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-4 py-20">
            <p className="text-sm text-muted-foreground">{t('wm.empty', locale)}</p>
            <button
              type="button"
              onClick={() => router.push('/online-service/conversation-settings/welcome/new')}
              className="flex h-10 items-center gap-2 rounded-lg bg-primary px-5 text-sm font-medium text-white"
            >
              <IconPlus size={18} />
              {t('wm.new', locale)}
            </button>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border">
            <div className="flex h-12 items-center gap-6 rounded-t-lg border-b border-border bg-muted px-6 text-sm font-semibold text-foreground/80">
              <div className="w-8 shrink-0" />
              <div className="w-[72px] shrink-0">{t('wm.col.priority', locale)}</div>
              <div className="min-w-0 flex-1">{t('wm.col.name', locale)}</div>
              <div className="w-[280px] shrink-0">{t('wm.col.conditions', locale)}</div>
              <div className="w-[100px] shrink-0">{t('wm.col.enabled', locale)}</div>
              <div className="w-[160px] shrink-0">{t('wm.col.updatedAt', locale)}</div>
              <div className="w-[80px] shrink-0 text-center">{t('wm.col.actions', locale)}</div>
            </div>
            {displayRows.map((row, index) => (
              <div
                key={row.id}
                className="flex h-14 items-center gap-6 border-b border-border px-6 last:border-b-0"
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => handleDrop(index)}
              >
                <div
                  className="flex w-8 shrink-0 cursor-grab items-center justify-center text-muted-foreground active:cursor-grabbing"
                  draggable
                  onDragStart={() => setDragIndex(index)}
                  onDragEnd={() => setDragIndex(null)}
                >
                  <IconGripVertical size={16} />
                </div>
                <div className="w-[72px] shrink-0 text-sm text-foreground">{index + 1}</div>
                <div className="min-w-0 flex-1 truncate text-sm text-foreground">{row.name}</div>
                <div className="w-[280px] shrink-0 truncate text-sm text-muted-foreground">
                  {conditionSummary(row.conditions, channelById, locale)}
                </div>
                <div className="w-[100px] shrink-0">
                  <Switch checked={row.enabled} onCheckedChange={() => handleToggleEnabled(row)} />
                </div>
                <div className="w-[160px] shrink-0 text-sm text-muted-foreground">
                  {formatDate(row.updated_at, locale)}
                </div>
                <div className="flex w-[80px] shrink-0 items-center justify-center gap-3">
                  <button
                    type="button"
                    onClick={() => router.push(`/online-service/conversation-settings/welcome/${row.id}`)}
                    className="text-foreground/80 transition-colors hover:text-foreground"
                    aria-label={t('wm.action.edit', locale)}
                  >
                    <IconPencil size={18} />
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(row)}
                    className="text-foreground/80 transition-colors hover:text-destructive"
                    aria-label={t('wm.action.delete', locale)}
                  >
                    <IconTrash size={18} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-4 border-t border-border pt-6">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-lg font-semibold text-foreground">{satText(locale, 'summary.title')}</h2>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => router.push('/online-service/conversation-settings/satisfaction/versions')}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm font-medium text-foreground hover:bg-accent"
            >
              <IconHistory size={17} />
              {satText(locale, 'summary.versions')}
            </button>
            <button
              type="button"
              onClick={() => router.push('/online-service/conversation-settings/satisfaction')}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/80"
            >
              <IconSettings size={17} />
              {satisfaction?.configured ? satText(locale, 'summary.edit') : satText(locale, 'summary.configure')}
            </button>
          </div>
        </div>

        {satisfactionPending ? (
          <div className="rounded-md border border-border p-5">
            <div className="grid animate-pulse gap-4 md:grid-cols-[140px_1fr_160px]">
              <div className="h-10 rounded-md bg-muted" />
              <div className="grid gap-4 md:grid-cols-2">
                <div className="h-10 rounded-md bg-muted" />
                <div className="h-10 rounded-md bg-muted" />
                <div className="h-10 rounded-md bg-muted" />
                <div className="h-10 rounded-md bg-muted" />
              </div>
              <div className="h-10 rounded-md bg-muted" />
            </div>
          </div>
        ) : satisfactionError ? (
          <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border py-16">
            <p className="text-sm text-muted-foreground">{satText(locale, 'summary.loadFailed')}</p>
            <button
              type="button"
              onClick={() => refetchSatisfaction()}
              className="inline-flex h-9 items-center rounded-md border border-border px-4 text-sm font-medium text-foreground hover:bg-accent"
            >
              {t('vc.retry', locale)}
            </button>
          </div>
        ) : !satisfaction?.configured ? (
          <div className="flex flex-col items-center justify-center gap-4 rounded-md border border-dashed border-border py-16">
            <p className="text-sm text-muted-foreground">{satText(locale, 'summary.empty')}</p>
            <button
              type="button"
              onClick={() => router.push('/online-service/conversation-settings/satisfaction')}
              className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground"
            >
              <IconSettings size={17} />
              {satText(locale, 'summary.configure')}
            </button>
          </div>
        ) : (
          <div className="rounded-md border border-border">
            <div className="grid gap-4 p-5 md:grid-cols-[140px_1fr_160px]">
              <div className="flex flex-col gap-2">
                <span className="text-xs font-medium text-muted-foreground">{satText(locale, 'summary.status')}</span>
                <div className="flex items-center gap-3">
                  <Switch
                    checked={satisfaction.enabled}
                    disabled={patchSatisfactionMut.isPending}
                    onCheckedChange={handleToggleSatisfaction}
                  />
                  <span className="text-sm font-medium text-foreground">
                    {satisfaction.enabled ? satText(locale, 'enabled.on') : satText(locale, 'enabled.off')}
                  </span>
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <span className="text-xs font-medium text-muted-foreground">{satText(locale, 'summary.types')}</span>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {satisfactionMeta?.types.map((type) => (
                      <span key={type} className="rounded-md bg-muted px-2.5 py-1 text-xs font-medium text-foreground">
                        {satisfactionTypeLabel(type, locale)}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <span className="text-xs font-medium text-muted-foreground">{satText(locale, 'summary.modes')}</span>
                  <p className="mt-2 text-sm text-foreground">{satisfactionMeta?.ratingModes.join(' / ') || '—'}</p>
                </div>
                <div>
                  <span className="text-xs font-medium text-muted-foreground">{satText(locale, 'summary.triggers')}</span>
                  <p className="mt-2 text-sm text-foreground">{satisfactionMeta?.triggers.join(' + ') || '—'}</p>
                </div>
                <div>
                  <span className="text-xs font-medium text-muted-foreground">{satText(locale, 'summary.updatedAt')}</span>
                  <p className="mt-2 text-sm text-foreground">{formatDate(satisfaction.updated_at, locale)}</p>
                </div>
              </div>
              <div className="flex flex-col gap-2 md:items-end">
                <span className="text-xs font-medium text-muted-foreground">{satText(locale, 'summary.version')}</span>
                <span className="text-sm font-semibold text-foreground">
                  {satisfaction.current_version ? `v${satisfaction.current_version}` : '—'}
                </span>
              </div>
            </div>
          </div>
        )}
      </section>

      {deleteTarget && (
        <DeleteModal
          item={deleteTarget}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
          loading={deleteMut.isPending}
        />
      )}
    </div>
  )
}
