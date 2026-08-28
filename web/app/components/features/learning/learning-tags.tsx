'use client'

import type { CourseStatus, LearnStatus } from '@/models/learning'
import type { ExamResultStatus, ExamStatus } from '@/models/learning-exam'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

export function CourseStatusTag({ status }: { status: CourseStatus }) {
  const { locale } = useLocaleStore()
  const tone =
    status === 'published'
      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
      : status === 'unpublished'
        ? 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300'
        : 'bg-muted text-muted-foreground'
  return (
    <span className={`rounded-md px-2 py-1 text-[11px] ${tone}`}>
      {t(`learning.course.status.${status}`, locale)}
    </span>
  )
}

export function LearnStatusTag({ status }: { status: LearnStatus }) {
  const { locale } = useLocaleStore()
  const tone =
    status === 'completed'
      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
      : status === 'in_progress'
        ? 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300'
        : 'bg-muted text-muted-foreground'
  return (
    <span className={`rounded-md px-2 py-1 text-[11px] ${tone}`}>
      {t(`learning.learnStatus.${status}`, locale)}
    </span>
  )
}

export function ExamStatusTag({ status }: { status: ExamStatus }) {
  const { locale } = useLocaleStore()
  const tone =
    status === 'published'
      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
      : status === 'unpublished'
        ? 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300'
        : 'bg-muted text-muted-foreground'
  return (
    <span className={`rounded-md px-2 py-1 text-[11px] ${tone}`}>
      {t(`learning.exam.status.${status}`, locale)}
    </span>
  )
}

export function ExamResultStatusTag({ status }: { status: ExamResultStatus }) {
  const { locale } = useLocaleStore()
  const tone =
    status === 'passed'
      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
      : status === 'failed'
        ? 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300'
        : 'bg-muted text-muted-foreground'
  return (
    <span className={`rounded-md px-2 py-1 text-[11px] ${tone}`}>
      {t(`learning.exam.resultStatus.${status}`, locale)}
    </span>
  )
}

export function formatLearningDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDurationSeconds(value: number | null | undefined): string | null {
  if (value == null || value <= 0) return null
  const minutes = Math.floor(value / 60)
  const seconds = Math.floor(value % 60)
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export function PaginationBar({
  total,
  page,
  pages,
  onPageChange,
}: {
  total: number
  page: number
  pages: number
  onPageChange: (page: number) => void
}) {
  const { locale } = useLocaleStore()
  if (total <= 0) return null
  return (
    <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
      <span>{t('learning.common.total', locale, { count: String(total) })}</span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="h-8 rounded-lg border border-border px-3 disabled:opacity-50"
        >
          {t('learning.common.prevPage', locale)}
        </button>
        <span>
          {t('learning.common.pageInfo', locale, {
            page: String(page),
            pages: String(Math.max(pages, 1)),
          })}
        </span>
        <button
          type="button"
          disabled={pages === 0 || page >= pages}
          onClick={() => onPageChange(page + 1)}
          className="h-8 rounded-lg border border-border px-3 disabled:opacity-50"
        >
          {t('learning.common.nextPage', locale)}
        </button>
      </div>
    </div>
  )
}
