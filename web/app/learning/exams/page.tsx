'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  IconCircleArrowDown,
  IconCircleArrowUp,
  IconClipboardList,
  IconPencil,
  IconPlus,
  IconSearch,
  IconTrash,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  useAdminExams,
  useDeleteExam,
  usePublishExam,
  useUnpublishExam,
} from '@/service/use-learning-exam'
import type { AdminExamListItem, ExamStatus } from '@/models/learning-exam'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  ExamStatusTag,
  PaginationBar,
  formatLearningDateTime,
} from '@/app/components/features/learning/learning-tags'

const PER_PAGE = 20

export default function LearningExamsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { locale } = useLocaleStore()

  const q = searchParams.get('q') ?? ''
  const status = (searchParams.get('status') ?? '') as ExamStatus | ''
  const page = Number(searchParams.get('page') ?? '1') || 1

  const [searchInput, setSearchInput] = useState(q)
  const [confirm, setConfirm] = useState<
    | { kind: 'unpublish'; exam: AdminExamListItem }
    | { kind: 'delete'; exam: AdminExamListItem }
    | null
  >(null)

  const syncParams = useCallback(
    (next: { q?: string; status?: string; page?: number }) => {
      const params = new URLSearchParams(searchParams.toString())
      const apply = (key: string, value?: string | number) => {
        if (value === undefined || value === '' || value === null) params.delete(key)
        else params.set(key, String(value))
      }
      if ('q' in next) apply('q', next.q)
      if ('status' in next) apply('status', next.status)
      if ('page' in next) apply('page', next.page && next.page > 1 ? next.page : undefined)
      const qs = params.toString()
      router.replace(qs ? `/learning/exams?${qs}` : '/learning/exams')
    },
    [router, searchParams],
  )

  // Debounce the name search into the URL.
  useEffect(() => {
    const keyword = searchInput.trim()
    if (keyword === q) return
    const timer = setTimeout(() => syncParams({ q: keyword, page: 1 }), 400)
    return () => clearTimeout(timer)
  }, [searchInput, q, syncParams])

  const { data, isLoading, isError, refetch } = useAdminExams({
    page,
    per_page: PER_PAGE,
    q: q || undefined,
    status: status || undefined,
  })

  const publishMutation = usePublishExam()
  const unpublishMutation = useUnpublishExam()
  const deleteMutation = useDeleteExam()

  const [pendingId, setPendingId] = useState<number | null>(null)

  const handlePublish = async (exam: AdminExamListItem) => {
    setPendingId(exam.id)
    try {
      await publishMutation.mutateAsync(exam.id)
      toast.success(t('learning.exam.toast.published', locale))
    } catch {
      toast.error(t('learning.exam.publishNotReady', locale))
    } finally {
      setPendingId(null)
    }
  }

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0
  const confirming = unpublishMutation.isPending || deleteMutation.isPending

  return (
    <div className="flex h-full flex-col gap-6 overflow-hidden p-8">
      <div className="flex shrink-0 items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">
          {t('learning.exams.title', locale)}
        </h1>
        <button
          type="button"
          onClick={() => router.push('/learning/exams/new')}
          className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          <IconPlus size={18} />
          {t('learning.exams.new', locale)}
        </button>
      </div>

      <div className="flex shrink-0 items-center gap-4">
        <div className="flex h-9 w-64 items-center gap-2 rounded-lg border border-border bg-white px-3">
          <IconSearch size={16} className="text-muted-foreground" />
          <input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder={t('learning.exams.searchPlaceholder', locale)}
            className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
        <select
          value={status}
          onChange={(event) => syncParams({ status: event.target.value, page: 1 })}
          className="h-9 w-36 rounded-lg border border-border bg-white px-3 text-sm outline-none"
        >
          <option value="">{t('learning.exams.statusAll', locale)}</option>
          <option value="draft">{t('learning.exam.status.draft', locale)}</option>
          <option value="published">{t('learning.exam.status.published', locale)}</option>
          <option value="unpublished">{t('learning.exam.status.unpublished', locale)}</option>
        </select>
      </div>

      <main className="min-h-0 flex-1 overflow-y-auto">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t('learning.common.loading', locale)}</p>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16">
            <p className="text-sm text-muted-foreground">{t('learning.common.loadFailed', locale)}</p>
            <button
              type="button"
              onClick={() => refetch()}
              className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
            >
              {t('learning.common.retry', locale)}
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="flex h-[420px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-white/60">
            <p className="text-sm text-muted-foreground">{t('learning.exams.empty', locale)}</p>
            <button
              type="button"
              onClick={() => router.push('/learning/exams/new')}
              className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
            >
              <IconPlus size={18} />
              {t('learning.exams.new', locale)}
            </button>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border">
            <div className="overflow-x-auto">
              <div style={{ minWidth: 1100 }}>
                <div className="flex h-14 items-center gap-6 rounded-t-lg bg-muted px-6">
                  <div className="min-w-[220px] flex-1 text-sm font-semibold text-foreground/80">
                    {t('learning.exams.col.exam', locale)}
                  </div>
                  <div className="w-[90px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.exams.col.status', locale)}
                  </div>
                  <div className="w-[100px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.exams.col.visibility', locale)}
                  </div>
                  <div className="w-[70px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.exams.col.questions', locale)}
                  </div>
                  <div className="w-[70px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.exams.col.totalScore', locale)}
                  </div>
                  <div className="w-[140px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.exams.col.passScore', locale)}
                  </div>
                  <div className="w-[80px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.exams.col.learners', locale)}
                  </div>
                  <div className="w-[80px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.exams.col.passed', locale)}
                  </div>
                  <div className="w-[140px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.exams.col.updatedAt', locale)}
                  </div>
                  <div className="w-[96px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.exams.col.actions', locale)}
                  </div>
                </div>

                {items.map((row) => (
                  <div
                    key={row.id}
                    className="flex h-14 items-center gap-6 border-t border-border px-6"
                  >
                    <div className="flex min-w-[220px] flex-1 items-center gap-3">
                      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground/50">
                        <IconClipboardList size={16} />
                      </span>
                      <span className="truncate text-sm font-medium text-foreground" title={row.name}>
                        {row.name}
                      </span>
                    </div>
                    <div className="flex w-[90px] shrink-0 items-center">
                      <ExamStatusTag status={row.status} />
                    </div>
                    <div className="w-[100px] shrink-0 truncate text-sm text-muted-foreground">
                      {t(`learning.exam.visibility.${row.visibility}`, locale)}
                    </div>
                    <div className="w-[70px] shrink-0 text-sm text-muted-foreground">
                      {row.question_count}
                    </div>
                    <div className="w-[70px] shrink-0 text-sm text-muted-foreground">
                      {row.total_score}
                    </div>
                    <div className="w-[140px] shrink-0 truncate text-sm text-muted-foreground">
                      {t('learning.exams.passScoreText', locale, {
                        score: String(row.pass_score),
                        percent: String(
                          Math.round(
                            row.pass_score && row.total_score
                              ? (row.pass_score / row.total_score) * 100
                              : 0,
                          ),
                        ),
                      })}
                    </div>
                    <div className="w-[80px] shrink-0 text-sm text-muted-foreground">
                      {row.learner_count === null
                        ? t('learning.exams.allEmployees', locale)
                        : row.learner_count}
                    </div>
                    <div className="w-[80px] shrink-0 text-sm text-muted-foreground">
                      {row.passed_count}
                    </div>
                    <div className="w-[140px] shrink-0 truncate text-sm text-muted-foreground">
                      {formatLearningDateTime(row.updated_at)}
                    </div>
                    <div className="flex w-[96px] shrink-0 items-center gap-3">
                      <button
                        type="button"
                        onClick={() => router.push(`/learning/exams/${row.id}`)}
                        className="text-foreground/80 transition-colors hover:text-foreground"
                        aria-label={t('learning.exams.action.edit', locale)}
                        title={t('learning.exams.action.edit', locale)}
                      >
                        <IconPencil size={18} />
                      </button>
                      {row.status === 'published' ? (
                        <button
                          type="button"
                          onClick={() => setConfirm({ kind: 'unpublish', exam: row })}
                          className="text-foreground/80 transition-colors hover:text-foreground"
                          aria-label={t('learning.exams.action.unpublish', locale)}
                          title={t('learning.exams.action.unpublish', locale)}
                        >
                          <IconCircleArrowDown size={18} />
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled={pendingId === row.id}
                          onClick={() => handlePublish(row)}
                          className="text-foreground/80 transition-colors hover:text-foreground disabled:opacity-40"
                          aria-label={t('learning.exams.action.publish', locale)}
                          title={t('learning.exams.action.publish', locale)}
                        >
                          <IconCircleArrowUp size={18} />
                        </button>
                      )}
                      {row.status === 'published' ? (
                        <button
                          type="button"
                          disabled
                          className="cursor-not-allowed text-foreground/80 opacity-40"
                          title={t('learning.exams.deleteDisabledHint', locale)}
                          aria-label={t('learning.exams.action.delete', locale)}
                        >
                          <IconTrash size={18} />
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setConfirm({ kind: 'delete', exam: row })}
                          className="text-foreground/80 transition-colors hover:text-destructive"
                          aria-label={t('learning.exams.action.delete', locale)}
                          title={t('learning.exams.action.delete', locale)}
                        >
                          <IconTrash size={18} />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {!isLoading && !isError ? (
          <PaginationBar total={total} page={page} pages={pages} onPageChange={(p) => syncParams({ page: p })} />
        ) : null}
      </main>

      <ConfirmDialog
        open={confirm?.kind === 'unpublish'}
        title={t('learning.exam.confirm.unpublish.title', locale)}
        message={t('learning.exam.confirm.unpublish.message', locale)}
        itemName={confirm?.kind === 'unpublish' ? confirm.exam.name : undefined}
        confirmLabel={t('learning.exam.confirm.unpublish.confirm', locale)}
        cancelLabel={t('learning.common.cancel', locale)}
        loading={confirming}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (confirm?.kind !== 'unpublish') return
          try {
            await unpublishMutation.mutateAsync(confirm.exam.id)
            toast.success(t('learning.exam.toast.unpublished', locale))
          } catch {
            toast.error(t('learning.common.loadFailed', locale))
          } finally {
            setConfirm(null)
          }
        }}
      />
      <ConfirmDialog
        open={confirm?.kind === 'delete'}
        title={t('learning.exam.confirm.delete.title', locale)}
        message={t('learning.exam.confirm.delete.message', locale)}
        itemName={confirm?.kind === 'delete' ? confirm.exam.name : undefined}
        confirmLabel={t('learning.exam.confirm.delete.confirm', locale)}
        cancelLabel={t('learning.common.cancel', locale)}
        variant="destructive"
        loading={confirming}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (confirm?.kind !== 'delete') return
          try {
            await deleteMutation.mutateAsync(confirm.exam.id)
            toast.success(t('learning.toast.deleted', locale))
          } catch {
            toast.error(t('learning.common.loadFailed', locale))
          } finally {
            setConfirm(null)
          }
        }}
      />
    </div>
  )
}
