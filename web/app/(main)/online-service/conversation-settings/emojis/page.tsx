'use client'

import { useCallback, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft } from 'lucide-react'
import { IconGripVertical, IconRefresh, IconSearch, IconTrash } from '@tabler/icons-react'
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import {
  ALL_EMOJI_ITEMS,
  DEFAULT_EMOJI_ITEMS,
  getEmojiAlias,
  getEmojiName,
  getEmojiSearchText,
} from '@/lib/emoji-catalog'
import type {
  EmojiItem,
  EmojiTarget,
  EmojiTargetPayload,
  SaveEmojiSettingsPayload,
} from '@/models/emoji-setting'
import { useEmojiSettings, useSaveEmojiSettings } from '@/service/use-emoji-settings'
import { t } from '@/utils/i18n'

const MAX_EMOJI_COUNT = 48
const TARGETS: EmojiTarget[] = ['user', 'agent']

function cloneItem(item: EmojiItem): EmojiItem {
  return {
    emoji: item.emoji,
    name: item.name,
    name_en: item.name_en ?? null,
    alias: item.alias ?? null,
    alias_en: item.alias_en ?? null,
    keywords: [...item.keywords],
  }
}

function cloneTarget(target: EmojiTargetPayload): EmojiTargetPayload {
  return {
    enabled: target.enabled,
    emojis: target.emojis.map(cloneItem),
  }
}

function clonePayload(payload: SaveEmojiSettingsPayload): SaveEmojiSettingsPayload {
  return {
    user: cloneTarget(payload.user),
    agent: cloneTarget(payload.agent),
  }
}

function payloadKey(payload: SaveEmojiSettingsPayload | null): string {
  return payload ? JSON.stringify(payload) : ''
}

function targetLabel(target: EmojiTarget, locale: Locale): string {
  return t(`emoji.target.${target}`, locale)
}

function validateTarget(target: EmojiTargetPayload, locale: Locale): string | null {
  if (target.enabled && target.emojis.length === 0) return t('emoji.validation.empty', locale)
  if (target.emojis.length > MAX_EMOJI_COUNT) return t('emoji.validation.max', locale)
  const values = target.emojis.map((item) => item.emoji)
  if (values.length !== new Set(values).size) return t('emoji.validation.duplicate', locale)
  return null
}

function mergeItem(candidate: EmojiItem): EmojiItem {
  return cloneItem(candidate)
}

function matchesSearch(item: EmojiItem, query: string): boolean {
  if (!query) return true
  return getEmojiSearchText(item).includes(query.toLowerCase())
}

export default function EmojiSettingsPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const { data, isLoading, isError, refetch } = useEmojiSettings()
  const saveMut = useSaveEmojiSettings()
  const [form, setForm] = useState<SaveEmojiSettingsPayload | null>(null)
  const [baseline, setBaseline] = useState<SaveEmojiSettingsPayload | null>(null)
  const [activeTarget, setActiveTarget] = useState<EmojiTarget>('user')
  const [search, setSearch] = useState('')
  const [activeDragId, setActiveDragId] = useState<string | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    if (!data || form) return
    const next = clonePayload({ user: data.user, agent: data.agent })
    setForm(next)
    setBaseline(clonePayload(next))
  }, [data, form])

  useEffect(() => {
    setActiveDragId(null)
  }, [activeTarget])

  const activeConfig = form?.[activeTarget] ?? null
  const selectedSet = useMemo(
    () => new Set(activeConfig?.emojis.map((item) => item.emoji) ?? []),
    [activeConfig?.emojis],
  )
  const validationErrors = useMemo(
    () => ({
      user: form ? validateTarget(form.user, locale) : null,
      agent: form ? validateTarget(form.agent, locale) : null,
    }),
    [form, locale],
  )
  const dirty = payloadKey(form) !== payloadKey(baseline)
  const hasErrors = Boolean(validationErrors.user || validationErrors.agent)

  const candidateItems = useMemo(
    () => ALL_EMOJI_ITEMS.filter((item) => matchesSearch(item, search.trim())),
    [search],
  )

  const showToast = (type: 'success' | 'error', text: string) => {
    setToast({ type, text })
    window.setTimeout(() => setToast(null), 3000)
  }

  const updateTarget = (target: EmojiTarget, updater: (current: EmojiTargetPayload) => EmojiTargetPayload) => {
    setForm((current) => {
      if (!current) return current
      return {
        ...current,
        [target]: updater(cloneTarget(current[target])),
      }
    })
  }

  const handleBack = () => {
    if (dirty && !window.confirm(t('emoji.leaveConfirm', locale))) return
    router.push('/online-service/conversation-settings')
  }

  const handleToggle = (enabled: boolean) => {
    updateTarget(activeTarget, (current) => ({ ...current, enabled }))
  }

  const handleAdd = (item: EmojiItem) => {
    if (!activeConfig || selectedSet.has(item.emoji) || activeConfig.emojis.length >= MAX_EMOJI_COUNT) return
    updateTarget(activeTarget, (current) => ({
      ...current,
      emojis: [...current.emojis, mergeItem(item)],
    }))
  }

  const handleRemove = (emoji: string) => {
    updateTarget(activeTarget, (current) => ({
      ...current,
      emojis: current.emojis.filter((item) => item.emoji !== emoji),
    }))
  }

  const emojiIds = useMemo(() => activeConfig?.emojis.map((item) => item.emoji) ?? [], [activeConfig?.emojis])
  const activeDragItem = useMemo(
    () => activeConfig?.emojis.find((item) => item.emoji === activeDragId) ?? null,
    [activeConfig?.emojis, activeDragId],
  )

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveDragId(String(event.active.id))
  }, [])

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      setActiveDragId(null)
      const { active, over } = event
      if (!over || active.id === over.id) return
      const oldIndex = emojiIds.indexOf(String(active.id))
      const newIndex = emojiIds.indexOf(String(over.id))
      if (oldIndex < 0 || newIndex < 0) return
      updateTarget(activeTarget, (current) => ({
        ...current,
        emojis: arrayMove(current.emojis, oldIndex, newIndex),
      }))
    },
    [activeTarget, emojiIds],
  )

  const handleDragCancel = useCallback(() => {
    setActiveDragId(null)
  }, [])

  const handleRestoreDefault = () => {
    const label = targetLabel(activeTarget, locale)
    if (!window.confirm(t('emoji.restoreConfirm', locale, { target: label }))) return
    updateTarget(activeTarget, () => ({
      enabled: true,
      emojis: DEFAULT_EMOJI_ITEMS.map(cloneItem),
    }))
  }

  const handleSave = async () => {
    if (!form || hasErrors) return
    try {
      const saved = await saveMut.mutateAsync(form)
      const next = clonePayload({ user: saved.user, agent: saved.agent })
      setForm(next)
      setBaseline(clonePayload(next))
      showToast('success', t('emoji.saveSuccess', locale))
    } catch {
      showToast('error', t('emoji.saveFailed', locale))
    }
  }

  if (isLoading || !form || !activeConfig) {
    return (
      <div className="-m-8 flex flex-col">
        <div className="sticky -top-8 z-20 flex min-h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-white px-6 py-2">
          <button
            type="button"
            onClick={() => router.push('/online-service/conversation-settings')}
            className="flex min-w-0 items-center gap-2 text-left"
          >
            <ArrowLeft size={20} className="shrink-0 text-muted-foreground" />
            <span className="truncate text-base font-semibold text-foreground">{t('emoji.page.title', locale)}</span>
          </button>
        </div>
        <div className="flex flex-col gap-4 p-8">
          <div className="h-10 w-48 animate-pulse rounded-md bg-muted" />
          <div className="h-[420px] animate-pulse rounded-lg border border-border bg-muted/40" />
        </div>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="-m-8 flex flex-col">
        <div className="sticky -top-8 z-20 flex min-h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-white px-6 py-2">
          <button
            type="button"
            onClick={() => router.push('/online-service/conversation-settings')}
            className="flex min-w-0 items-center gap-2 text-left"
          >
            <ArrowLeft size={20} className="shrink-0 text-muted-foreground" />
            <span className="truncate text-base font-semibold text-foreground">{t('emoji.page.title', locale)}</span>
          </button>
        </div>
        <div className="flex flex-col gap-4 p-8">
          <p className="text-sm text-muted-foreground">{t('emoji.loadFailed', locale)}</p>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => refetch()}
              className="inline-flex h-9 items-center rounded-md border border-border px-4 text-sm font-medium text-foreground hover:bg-accent"
            >
              {t('vc.retry', locale)}
            </button>
            <button
              type="button"
              onClick={() => router.push('/online-service/conversation-settings')}
              className="inline-flex h-9 items-center rounded-md px-4 text-sm font-medium text-muted-foreground hover:bg-accent"
            >
              {t('emoji.back', locale)}
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="-m-8 flex flex-col">
      <div className="sticky -top-8 z-20 flex min-h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-white px-6 py-2">
        <button type="button" onClick={handleBack} className="flex min-w-0 items-center gap-2 text-left">
          <ArrowLeft size={20} className="shrink-0 text-muted-foreground" />
          <span className="truncate text-base font-semibold text-foreground">{t('emoji.page.title', locale)}</span>
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={!dirty || hasErrors || saveMut.isPending}
          className="inline-flex h-9 shrink-0 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/80 disabled:opacity-40"
        >
          {saveMut.isPending ? t('emoji.saving', locale) : t('emoji.save', locale)}
        </button>
      </div>

      {toast && (
        <div
          className={`mx-8 mt-4 rounded-md px-4 py-3 text-sm ${
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          }`}
        >
          {toast.text}
        </div>
      )}

      <div className="flex flex-col gap-6 p-8">
        <div className="flex w-fit rounded-lg border border-border p-1">
          {TARGETS.map((target) => (
            <button
              key={target}
              type="button"
              onClick={() => setActiveTarget(target)}
              className={`h-9 rounded-md px-4 text-sm font-medium transition-colors ${
                activeTarget === target
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-foreground'
              }`}
            >
              {targetLabel(target, locale)}
            </button>
          ))}
        </div>

        <section className="rounded-lg border border-border">
          <div className="flex flex-col gap-5 p-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">{targetLabel(activeTarget, locale)}</h2>
                <p className="mt-1 text-sm text-muted-foreground">{t('emoji.panel.description', locale)}</p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-foreground">{t('emoji.panel.enabled', locale)}</span>
                <Switch checked={activeConfig.enabled} onCheckedChange={handleToggle} />
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">{t('emoji.selected.title', locale)}</h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t('emoji.selected.count', locale, { count: activeConfig.emojis.length })}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleRestoreDefault}
                  className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm font-medium text-foreground hover:bg-accent"
                >
                  <IconRefresh size={16} />
                  {t('emoji.restoreDefault', locale)}
                </button>
              </div>

              {activeConfig.emojis.length === 0 ? (
                <div className="flex min-h-28 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
                  {t('emoji.selected.empty', locale)}
                </div>
              ) : (
                <DndContext
                  sensors={sensors}
                  collisionDetection={closestCenter}
                  onDragStart={handleDragStart}
                  onDragEnd={handleDragEnd}
                  onDragCancel={handleDragCancel}
                >
                  <SortableContext items={emojiIds} strategy={rectSortingStrategy}>
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                      {activeConfig.emojis.map((item) => (
                        <SortableSelectedEmojiItem
                          key={item.emoji}
                          item={item}
                          locale={locale}
                          onRemove={handleRemove}
                        />
                      ))}
                    </div>
                  </SortableContext>
                  <DragOverlay dropAnimation={null}>
                    {activeDragItem ? (
                      <SelectedEmojiCard
                        item={activeDragItem}
                        locale={locale}
                        overlay
                      />
                    ) : null}
                  </DragOverlay>
                </DndContext>
              )}

              {validationErrors[activeTarget] && (
                <p className="text-sm text-destructive">{validationErrors[activeTarget]}</p>
              )}
            </div>

            <div className="flex flex-col gap-4 border-t border-border pt-5">
              <div className="relative max-w-md">
                <IconSearch size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={t('emoji.search.placeholder', locale)}
                  className="h-10 w-full rounded-md border border-border bg-background pl-9 pr-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                />
              </div>

              {search.trim() ? (
                <EmojiCandidateGrid
                  title={t('emoji.search.results', locale)}
                  items={candidateItems}
                  selectedSet={selectedSet}
                  locale={locale}
                  onAdd={handleAdd}
                />
              ) : (
                <EmojiCandidateGrid
                  title={t('emoji.all.title', locale)}
                  items={candidateItems}
                  selectedSet={selectedSet}
                  locale={locale}
                  onAdd={handleAdd}
                />
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

function SelectedEmojiCard({
  item,
  locale,
  dragHandle,
  onRemove,
  overlay = false,
  placeholder = false,
}: {
  item: EmojiItem
  locale: Locale
  dragHandle?: ReactNode
  onRemove?: (emoji: string) => void
  overlay?: boolean
  placeholder?: boolean
}) {
  return (
    <div
      className={cn(
        'flex h-14 items-center gap-3 rounded-md border px-3',
        placeholder
          ? 'border-dashed border-primary/40 bg-primary/5'
          : 'border-border bg-background',
        overlay && 'shadow-lg ring-2 ring-primary/20',
      )}
    >
      {dragHandle ?? (
        <span className="flex h-8 w-8 shrink-0 items-center justify-center text-muted-foreground">
          <IconGripVertical size={16} />
        </span>
      )}
      <span className="shrink-0 text-2xl leading-none">{item.emoji}</span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-foreground">{getEmojiName(item, locale)}</div>
        <div className="truncate text-xs text-muted-foreground">{getEmojiAlias(item, locale)}</div>
      </div>
      {onRemove ? (
        <button
          type="button"
          onClick={() => onRemove(item.emoji)}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          aria-label={t('emoji.remove', locale)}
          title={t('emoji.remove', locale)}
        >
          <IconTrash size={16} />
        </button>
      ) : (
        <span className="h-8 w-8 shrink-0" />
      )}
    </div>
  )
}

function SortableSelectedEmojiItem({
  item,
  locale,
  onRemove,
}: {
  item: EmojiItem
  locale: Locale
  onRemove: (emoji: string) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.emoji,
  })
  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  const dragHandle = (
    <button
      type="button"
      className="flex h-8 w-8 shrink-0 cursor-grab touch-none select-none items-center justify-center rounded-md text-muted-foreground active:cursor-grabbing"
      {...attributes}
      {...listeners}
      aria-label={t('emoji.drag', locale)}
      title={t('emoji.drag', locale)}
    >
      <IconGripVertical size={16} />
    </button>
  )

  return (
    <div ref={setNodeRef} style={style} className={cn(isDragging && 'z-10')}>
      <SelectedEmojiCard
        item={item}
        locale={locale}
        dragHandle={dragHandle}
        onRemove={onRemove}
        placeholder={isDragging}
      />
    </div>
  )
}

function EmojiCandidateGrid({
  title,
  items,
  selectedSet,
  locale,
  onAdd,
}: {
  title: string
  items: EmojiItem[]
  selectedSet: Set<string>
  locale: Locale
  onAdd: (item: EmojiItem) => void
}) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      {items.length === 0 ? (
        <div className="flex h-16 items-center rounded-md border border-dashed border-border px-4 text-sm text-muted-foreground">
          {t('emoji.search.empty', locale)}
        </div>
      ) : (
        <div className="grid grid-cols-4 gap-2 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 xl:grid-cols-12">
          {items.map((item) => {
            const selected = selectedSet.has(item.emoji)
            return (
              <button
                key={item.emoji}
                type="button"
                onClick={() => onAdd(item)}
                disabled={selected}
                className="flex h-16 flex-col items-center justify-center gap-1 rounded-md border border-border bg-background text-center transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
                aria-label={`${t('emoji.add', locale)}: ${getEmojiName(item, locale)}`}
                title={getEmojiAlias(item, locale)}
              >
                <span className="text-2xl leading-none">{item.emoji}</span>
                <span className="max-w-full truncate px-1 text-[11px] text-muted-foreground">
                  {getEmojiName(item, locale)}
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
