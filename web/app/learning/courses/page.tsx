'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  IconBook2,
  IconCircleArrowDown,
  IconCircleArrowUp,
  IconPencil,
  IconPlus,
  IconSearch,
  IconTrash,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  useAdminCourses,
  useDeleteCourse,
  usePublishCourse,
  useUnpublishCourse,
} from '@/service/use-learning'
import type { AdminCourseListItem, CourseStatus } from '@/models/learning'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  CourseStatusTag,
  PaginationBar,
  formatLearningDateTime,
} from '@/app/components/features/learning/learning-tags'

const PER_PAGE = 20

export default function LearningCoursesPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { locale } = useLocaleStore()

  const q = searchParams.get('q') ?? ''
  const status = (searchParams.get('status') ?? '') as CourseStatus | ''
  const page = Number(searchParams.get('page') ?? '1') || 1

  const [searchInput, setSearchInput] = useState(q)
  const [confirm, setConfirm] = useState<
    | { kind: 'unpublish'; course: AdminCourseListItem }
    | { kind: 'delete'; course: AdminCourseListItem }
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
      router.replace(qs ? `/learning/courses?${qs}` : '/learning/courses')
    },
    [router, searchParams],
  )

  // Debounce the name search into the URL (§3.4).
  useEffect(() => {
    const keyword = searchInput.trim()
    if (keyword === q) return
    const timer = setTimeout(() => syncParams({ q: keyword, page: 1 }), 400)
    return () => clearTimeout(timer)
  }, [searchInput, q, syncParams])

  const { data, isLoading, isError, refetch } = useAdminCourses({
    page,
    per_page: PER_PAGE,
    q: q || undefined,
    status: status || undefined,
  })

  const publishMutation = usePublishCourse()
  const unpublishMutation = useUnpublishCourse()
  const deleteMutation = useDeleteCourse()

  const [pendingId, setPendingId] = useState<number | null>(null)

  const handlePublish = async (course: AdminCourseListItem) => {
    setPendingId(course.id)
    try {
      await publishMutation.mutateAsync(course.id)
      toast.success(t('learning.toast.published', locale))
    } catch {
      toast.error(t('learning.course.publishNotReady', locale))
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
          {t('learning.courses.title', locale)}
        </h1>
        <button
          type="button"
          onClick={() => router.push('/learning/courses/new')}
          className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          <IconPlus size={18} />
          {t('learning.courses.new', locale)}
        </button>
      </div>

      <div className="flex shrink-0 items-center gap-4">
        <div className="flex h-9 w-64 items-center gap-2 rounded-lg border border-border bg-white px-3">
          <IconSearch size={16} className="text-muted-foreground" />
          <input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder={t('learning.courses.searchPlaceholder', locale)}
            className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
        <select
          value={status}
          onChange={(event) => syncParams({ status: event.target.value, page: 1 })}
          className="h-9 w-36 rounded-lg border border-border bg-white px-3 text-sm outline-none"
        >
          <option value="">{t('learning.courses.statusAll', locale)}</option>
          <option value="draft">{t('learning.course.status.draft', locale)}</option>
          <option value="published">{t('learning.course.status.published', locale)}</option>
          <option value="unpublished">{t('learning.course.status.unpublished', locale)}</option>
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
            <p className="text-sm text-muted-foreground">{t('learning.courses.empty', locale)}</p>
            <button
              type="button"
              onClick={() => router.push('/learning/courses/new')}
              className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
            >
              <IconPlus size={18} />
              {t('learning.courses.new', locale)}
            </button>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border">
            <div className="overflow-x-auto">
              <div style={{ minWidth: 1100 }}>
                <div className="flex h-14 items-center gap-6 rounded-t-lg bg-muted px-6">
                  <div className="min-w-[220px] flex-1 text-sm font-semibold text-foreground/80">
                    {t('learning.courses.col.course', locale)}
                  </div>
                  <div className="w-[90px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.courses.col.status', locale)}
                  </div>
                  <div className="w-[100px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.courses.col.visibility', locale)}
                  </div>
                  <div className="w-[70px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.courses.col.sections', locale)}
                  </div>
                  <div className="w-[70px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.courses.col.materials', locale)}
                  </div>
                  <div className="w-[80px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.courses.col.learners', locale)}
                  </div>
                  <div className="w-[90px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.courses.col.completed', locale)}
                  </div>
                  <div className="w-[140px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.courses.col.updatedAt', locale)}
                  </div>
                  <div className="w-[96px] shrink-0 text-sm font-semibold text-foreground/80">
                    {t('learning.courses.col.actions', locale)}
                  </div>
                </div>

                {items.map((row) => (
                  <div
                    key={row.id}
                    className="flex h-14 items-center gap-6 border-t border-border px-6"
                  >
                    <div className="flex min-w-[220px] flex-1 items-center gap-3">
                      {row.cover_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={row.cover_url}
                          alt={row.name}
                          className="h-9 w-14 shrink-0 rounded-md object-cover"
                        />
                      ) : (
                        <span className="grid h-9 w-14 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground/50">
                          <IconBook2 size={16} />
                        </span>
                      )}
                      <span className="truncate text-sm font-medium text-foreground" title={row.name}>
                        {row.name}
                      </span>
                    </div>
                    <div className="flex w-[90px] shrink-0 items-center">
                      <CourseStatusTag status={row.status} />
                    </div>
                    <div className="w-[100px] shrink-0 truncate text-sm text-muted-foreground">
                      {t(`learning.course.visibility.${row.visibility}`, locale)}
                    </div>
                    <div className="w-[70px] shrink-0 text-sm text-muted-foreground">
                      {row.section_count}
                    </div>
                    <div className="w-[70px] shrink-0 text-sm text-muted-foreground">
                      {row.material_count}
                    </div>
                    <div className="w-[80px] shrink-0 text-sm text-muted-foreground">
                      {row.learner_count === null
                        ? t('learning.courses.allEmployees', locale)
                        : row.learner_count}
                    </div>
                    <div className="w-[90px] shrink-0 text-sm text-muted-foreground">
                      {row.completed_count}
                    </div>
                    <div className="w-[140px] shrink-0 truncate text-sm text-muted-foreground">
                      {formatLearningDateTime(row.updated_at)}
                    </div>
                    <div className="flex w-[96px] shrink-0 items-center gap-3">
                      <button
                        type="button"
                        onClick={() => router.push(`/learning/courses/${row.id}`)}
                        className="text-foreground/80 transition-colors hover:text-foreground"
                        aria-label={t('learning.courses.action.edit', locale)}
                        title={t('learning.courses.action.edit', locale)}
                      >
                        <IconPencil size={18} />
                      </button>
                      {row.status === 'published' ? (
                        <button
                          type="button"
                          onClick={() => setConfirm({ kind: 'unpublish', course: row })}
                          className="text-foreground/80 transition-colors hover:text-foreground"
                          aria-label={t('learning.courses.action.unpublish', locale)}
                          title={t('learning.courses.action.unpublish', locale)}
                        >
                          <IconCircleArrowDown size={18} />
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled={pendingId === row.id}
                          onClick={() => handlePublish(row)}
                          className="text-foreground/80 transition-colors hover:text-foreground disabled:opacity-40"
                          aria-label={t('learning.courses.action.publish', locale)}
                          title={t('learning.courses.action.publish', locale)}
                        >
                          <IconCircleArrowUp size={18} />
                        </button>
                      )}
                      {row.status === 'published' ? (
                        <button
                          type="button"
                          disabled
                          className="cursor-not-allowed text-foreground/80 opacity-40"
                          title={t('learning.courses.deleteDisabledHint', locale)}
                          aria-label={t('learning.courses.action.delete', locale)}
                        >
                          <IconTrash size={18} />
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setConfirm({ kind: 'delete', course: row })}
                          className="text-foreground/80 transition-colors hover:text-destructive"
                          aria-label={t('learning.courses.action.delete', locale)}
                          title={t('learning.courses.action.delete', locale)}
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
        title={t('learning.confirm.unpublish.title', locale)}
        message={t('learning.confirm.unpublish.message', locale)}
        itemName={confirm?.kind === 'unpublish' ? confirm.course.name : undefined}
        confirmLabel={t('learning.confirm.unpublish.confirm', locale)}
        cancelLabel={t('learning.common.cancel', locale)}
        loading={confirming}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (confirm?.kind !== 'unpublish') return
          try {
            await unpublishMutation.mutateAsync(confirm.course.id)
            toast.success(t('learning.toast.unpublished', locale))
          } catch {
            toast.error(t('learning.common.loadFailed', locale))
          } finally {
            setConfirm(null)
          }
        }}
      />
      <ConfirmDialog
        open={confirm?.kind === 'delete'}
        title={t('learning.confirm.deleteCourse.title', locale)}
        message={t('learning.confirm.deleteCourse.message', locale)}
        itemName={confirm?.kind === 'delete' ? confirm.course.name : undefined}
        confirmLabel={t('learning.confirm.deleteCourse.confirm', locale)}
        cancelLabel={t('learning.common.cancel', locale)}
        variant="destructive"
        loading={confirming}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (confirm?.kind !== 'delete') return
          try {
            await deleteMutation.mutateAsync(confirm.course.id)
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
