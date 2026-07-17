'use client'

import { useEffect, useMemo, useState } from 'react'
import { HTTPError } from 'ky'
import { IconBook2, IconRefresh } from '@tabler/icons-react'
import { toast } from 'sonner'

import { Switch } from '@/components/ui/switch'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import type { RobotQaKnowledgeBase } from '@/models/robot-qa'
import {
  useRobotQaKnowledgeBases,
  useRobotQaSetting,
  useSaveRobotQaSetting,
} from '@/service/use-robot-qa'
import { t } from '@/utils/i18n'


export function filterRobotQaKnowledgeBases(
  items: RobotQaKnowledgeBase[],
  search: string,
): RobotQaKnowledgeBase[] {
  const keyword = search.trim().toLocaleLowerCase()
  if (!keyword) return items
  return items.filter((item) =>
    `${item.name} ${item.description ?? ''}`.toLocaleLowerCase().includes(keyword),
  )
}

export function isRobotQaTargetInvalid(
  knowledgeBaseId: number | null,
  items: RobotQaKnowledgeBase[],
): boolean {
  return knowledgeBaseId != null && !items.some((item) => item.id === knowledgeBaseId)
}

async function candidateErrorText(error: unknown, locale: Locale): Promise<string> {
  if (error instanceof HTTPError) {
    try {
      const body = await error.response.clone().json() as { code?: string }
      if (body.code === 'ROBOT_QA_OPEN_AGENT_NOT_CONFIGURED') {
        return t('robotQa.settings.notConfigured', locale)
      }
      if (body.code === 'ROBOT_QA_OPEN_AGENT_SCOPE_ERROR') {
        return t('robotQa.settings.scopeError', locale)
      }
    } catch {
      // Use the generic localized fallback.
    }
  }
  return t('robotQa.settings.loadFailed', locale)
}

export function RobotQaSettingSection() {
  const { locale } = useLocaleStore()
  const settingQuery = useRobotQaSetting()
  const candidatesQuery = useRobotQaKnowledgeBases()
  const saveSetting = useSaveRobotQaSetting()
  const [enabled, setEnabled] = useState(false)
  const [knowledgeBaseId, setKnowledgeBaseId] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [fieldError, setFieldError] = useState('')
  const [candidateError, setCandidateError] = useState('')

  useEffect(() => {
    if (!settingQuery.data) return
    setEnabled(settingQuery.data.enabled)
    setKnowledgeBaseId(settingQuery.data.knowledge_base_id)
    setFieldError('')
  }, [settingQuery.data])

  useEffect(() => {
    if (!candidatesQuery.error) {
      setCandidateError('')
      return
    }
    let active = true
    void candidateErrorText(candidatesQuery.error, locale).then((message) => {
      if (active) setCandidateError(message)
    })
    return () => {
      active = false
    }
  }, [candidatesQuery.error, locale])

  const candidates = candidatesQuery.data?.items ?? []
  const filteredCandidates = useMemo(
    () => filterRobotQaKnowledgeBases(candidates, search),
    [candidates, search],
  )
  const targetInvalid = !candidatesQuery.isPending
    && !candidatesQuery.isError
    && isRobotQaTargetInvalid(knowledgeBaseId, candidates)
  const dirty = Boolean(
    settingQuery.data
    && (
      enabled !== settingQuery.data.enabled
      || knowledgeBaseId !== settingQuery.data.knowledge_base_id
    ),
  )
  const unavailableForEnable = enabled && (
    candidatesQuery.isPending
    || candidatesQuery.isError
    || candidates.length === 0
    || targetInvalid
  )

  const handleSave = async () => {
    if (enabled && knowledgeBaseId == null) {
      setFieldError(t('robotQa.settings.knowledgeBaseRequired', locale))
      return
    }
    if (unavailableForEnable) return
    try {
      await saveSetting.mutateAsync({ enabled, knowledge_base_id: knowledgeBaseId })
      toast.success(t('robotQa.settings.saveSuccess', locale))
    } catch {
      toast.error(t('robotQa.settings.saveFailed', locale))
    }
  }

  return (
    <section className="flex flex-col gap-4 border-t border-border pt-6">
      <div>
        <h2 className="text-lg font-semibold text-foreground">{t('robotQa.settings.title', locale)}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('robotQa.settings.description', locale)}</p>
      </div>

      {settingQuery.isPending ? (
        <div className="h-52 animate-pulse rounded-md border border-border bg-muted/50" />
      ) : settingQuery.isError ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border py-12">
          <p className="text-sm text-muted-foreground">{t('robotQa.settings.settingLoadFailed', locale)}</p>
          <button
            type="button"
            onClick={() => void settingQuery.refetch()}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-4 text-sm font-medium text-foreground hover:bg-accent"
          >
            <IconRefresh size={16} />
            {t('vc.retry', locale)}
          </button>
        </div>
      ) : settingQuery.data ? (
        <div className="overflow-hidden rounded-md border border-border bg-background">
          <div className="flex min-w-0 items-start justify-between gap-4 border-b border-border p-5">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <IconBook2 size={17} className="text-muted-foreground" />
                <h3 className="text-sm font-semibold text-foreground">{t('robotQa.settings.enableLabel', locale)}</h3>
                <span className="rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                  {enabled ? t('robotQa.settings.enabled', locale) : t('robotQa.settings.disabled', locale)}
                </span>
              </div>
              <p className="mt-2 text-sm leading-5 text-muted-foreground">{t('robotQa.settings.enableHint', locale)}</p>
            </div>
            <Switch
              checked={enabled}
              disabled={saveSetting.isPending}
              aria-label={t('robotQa.settings.enableLabel', locale)}
              onCheckedChange={(checked) => {
                setEnabled(checked)
                setFieldError('')
              }}
            />
          </div>

          <div className="grid gap-4 p-5 md:grid-cols-[180px_1fr]">
            <label htmlFor="robot-qa-knowledge-base" className="pt-2 text-sm font-medium text-foreground">
              {t('robotQa.settings.knowledgeBase', locale)}
            </label>
            <div className="max-w-xl space-y-2">
              {candidatesQuery.isPending ? (
                <div className="h-20 animate-pulse rounded-md bg-muted/50" />
              ) : candidatesQuery.isError ? (
                <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3">
                  <p className="text-sm text-destructive">{candidateError || t('robotQa.settings.loadFailed', locale)}</p>
                  <button
                    type="button"
                    onClick={() => void candidatesQuery.refetch()}
                    className="mt-2 inline-flex h-8 items-center gap-2 rounded-md border border-border px-3 text-xs font-medium text-foreground hover:bg-accent"
                  >
                    <IconRefresh size={14} />
                    {t('vc.retry', locale)}
                  </button>
                </div>
              ) : candidates.length === 0 ? (
                <p className="rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-foreground">
                  {t('robotQa.settings.empty', locale)}
                </p>
              ) : (
                <>
                  <input
                    type="search"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder={t('robotQa.settings.searchPlaceholder', locale)}
                    className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                  />
                  <select
                    id="robot-qa-knowledge-base"
                    value={knowledgeBaseId ?? ''}
                    disabled={saveSetting.isPending}
                    onChange={(event) => {
                      setKnowledgeBaseId(event.target.value ? Number(event.target.value) : null)
                      setFieldError('')
                    }}
                    className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
                  >
                    <option value="">{t('robotQa.settings.knowledgeBasePlaceholder', locale)}</option>
                    {targetInvalid && knowledgeBaseId != null && (
                      <option value={knowledgeBaseId}>
                        {settingQuery.data.knowledge_base_name || `#${knowledgeBaseId}`} ({t('robotQa.settings.invalidShort', locale)})
                      </option>
                    )}
                    {filteredCandidates.map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </>
              )}
              {targetInvalid && (
                <p className="rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-foreground">
                  {t('robotQa.settings.invalid', locale)}
                </p>
              )}
              {fieldError && <p className="text-xs text-destructive">{fieldError}</p>}
            </div>
          </div>

          <div className="flex justify-end border-t border-border p-5">
            <button
              type="button"
              disabled={!dirty || saveSetting.isPending || unavailableForEnable}
              onClick={() => void handleSave()}
              className="inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/80 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saveSetting.isPending ? t('robotQa.settings.saving', locale) : t('robotQa.settings.save', locale)}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  )
}
