'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconBook2, IconSearch } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useMyCourses } from '@/service/use-learning'
import type { MyCourseListItem } from '@/models/learning'
import { LearnStatusTag, PaginationBar } from '@/app/components/features/learning/learning-tags'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 12

function actionKey(status: MyCourseListItem['status']) {
  if (status === 'completed') return 'learning.my.action.relearn'
  if (status === 'in_progress') return 'learning.my.action.continue'
  return 'learning.my.action.start'
}

function CourseCard({ course }: { course: MyCourseListItem }) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-border bg-white dark:bg-card">
      {course.cover_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={course.cover_url} alt={course.name} className="h-28 w-full object-cover" />
      ) : (
        <div className="flex h-28 items-center justify-center bg-muted text-muted-foreground/50">
          <IconBook2 size={30} stroke={1.5} />
        </div>
      )}
      <div className="flex min-h-0 flex-1 flex-col gap-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="truncate text-sm font-semibold" title={course.name}>
            {course.name}
          </h3>
          <LearnStatusTag status={course.status} />
        </div>
        <p className="line-clamp-2 min-h-10 text-xs leading-5 text-muted-foreground">
          {course.intro ?? ''}
        </p>
        <div className="mt-auto space-y-1.5">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>
              {t('learning.my.materialCount', locale, { count: String(course.material_count) })}
            </span>
            <span>{course.progress}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className={cn(
                'h-full rounded-full',
                course.progress === 100 ? 'bg-emerald-500' : 'bg-primary',
              )}
              style={{ width: `${course.progress}%` }}
            />
          </div>
          <button
            type="button"
            onClick={() => router.push(`/learning/my/${course.id}`)}
            className={cn(
              'mt-2 h-8 w-full rounded-md text-xs font-medium',
              course.status === 'not_started'
                ? 'bg-primary text-primary-foreground'
                : 'border border-border bg-white text-foreground dark:bg-card',
            )}
          >
            {t(actionKey(course.status), locale)}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function MyLearningPage() {
  const { locale } = useLocaleStore()
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const { data, isLoading, isError, refetch } = useMyCourses({
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
        <h1 className="text-xl font-semibold">{t('learning.my.title', locale)}</h1>
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
            placeholder={t('learning.my.searchPlaceholder', locale)}
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
            <p className="text-sm text-muted-foreground">{t('learning.my.empty', locale)}</p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-4">
              {items.map((course) => (
                <CourseCard key={course.id} course={course} />
              ))}
            </div>
            <PaginationBar total={total} page={page} pages={pages} onPageChange={setPage} />
          </>
        )}
      </main>
    </div>
  )
}
