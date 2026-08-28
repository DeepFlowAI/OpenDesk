'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconClipboardList, IconSearch } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useMyExams } from '@/service/use-learning-exam'
import type { MyExamItem } from '@/models/learning-exam'
import { ExamResultStatusTag, PaginationBar } from '@/app/components/features/learning/learning-tags'
import {
  ExamStartConfirmDialog,
  type StartExamTarget,
} from '@/app/components/features/learning/exam-start-confirm-dialog'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 12

function ExamCard({ exam, onStart }: { exam: MyExamItem; onStart: (exam: StartExamTarget) => void }) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const canStart = exam.remaining_attempts > 0
  const notStarted = exam.status === 'not_started'
  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-border bg-white dark:bg-card">
      <div className="flex h-28 items-center justify-center bg-muted text-muted-foreground/50">
        <IconClipboardList size={30} stroke={1.5} />
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="truncate text-sm font-semibold" title={exam.name}>
            {exam.name}
          </h3>
          <ExamResultStatusTag status={exam.status} />
        </div>
        <p className="line-clamp-2 min-h-10 text-xs leading-5 text-muted-foreground">
          {exam.intro ?? ''}
        </p>
        <div className="mt-auto space-y-1.5">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>
              {t('learning.myexam.bestScore', locale)}{' '}
              <span className="font-medium text-foreground">
                {exam.best_score === null ? '-' : exam.best_score}
              </span>
              /{exam.total_score}
            </span>
            <span>
              {canStart
                ? t('learning.myexam.remaining', locale, { count: String(exam.remaining_attempts) })
                : t('learning.myexam.noAttemptsLeft', locale)}
            </span>
          </div>
          <div className="text-[11px] text-muted-foreground">
            {exam.time_limit_minutes
              ? t('learning.myexam.timeLimited', locale, { minutes: String(exam.time_limit_minutes) })
              : t('learning.myexam.noTimeLimit', locale)}
          </div>
          <div className="flex gap-2 pt-1">
            {!notStarted || !canStart ? (
              <button
                type="button"
                onClick={() => router.push(`/learning/exams/my/${exam.id}`)}
                className="h-8 flex-1 rounded-md border border-border bg-white text-xs font-medium text-foreground dark:bg-card"
              >
                {t('learning.myexam.action.viewResult', locale)}
              </button>
            ) : null}
            {canStart ? (
              <button
                type="button"
                onClick={() =>
                  onStart({ id: exam.id, name: exam.name, time_limit_minutes: exam.time_limit_minutes })
                }
                className={cn(
                  'h-8 flex-1 rounded-md text-xs font-medium',
                  'bg-primary text-primary-foreground',
                )}
              >
                {notStarted
                  ? t('learning.myexam.action.start', locale)
                  : t('learning.myexam.action.retry', locale)}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function MyExamsPage() {
  const { locale } = useLocaleStore()
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [starting, setStarting] = useState<StartExamTarget | null>(null)
  const { data, isLoading, isError, refetch } = useMyExams({
    q: search || undefined,
    page,
    per_page: PAGE_SIZE,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between px-8 py-5">
        <h1 className="text-xl font-semibold">{t('learning.myexam.title', locale)}</h1>
        <div className="relative w-72">
          <IconSearch
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <input
            value={q}
            onChange={(event) => setQ(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                setSearch(q.trim())
                setPage(1)
              }
            }}
            placeholder={t('learning.myexam.searchPlaceholder', locale)}
            className="h-9 w-full rounded-md border border-border bg-white pl-9 pr-3 text-sm outline-none focus:border-primary dark:bg-card"
          />
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-y-auto px-8 pb-8">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t('learning.common.loading', locale)}</p>
        ) : isError ? (
          <div className="flex h-[420px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-white/60">
            <p className="text-sm text-muted-foreground">
              {t('learning.common.loadFailed', locale)}
            </p>
            <button
              type="button"
              onClick={() => refetch()}
              className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
            >
              {t('learning.common.retry', locale)}
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="flex h-[420px] flex-col items-center justify-center rounded-lg border border-dashed border-border bg-white/60">
            <p className="text-sm text-muted-foreground">{t('learning.myexam.empty', locale)}</p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-4">
              {items.map((exam) => (
                <ExamCard key={exam.id} exam={exam} onStart={setStarting} />
              ))}
            </div>
            <PaginationBar total={total} page={page} pages={pages} onPageChange={setPage} />
          </>
        )}
      </main>

      <ExamStartConfirmDialog exam={starting} onClose={() => setStarting(null)} />
    </div>
  )
}
