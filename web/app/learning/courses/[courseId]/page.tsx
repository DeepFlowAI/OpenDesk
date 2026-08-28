'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  useAdminCourse,
  useCreateCourse,
  usePublishCourse,
  useUnpublishCourse,
} from '@/service/use-learning'
import { CourseBasicTab } from '@/app/components/features/learning/course-basic-tab'
import { CourseContentTab } from '@/app/components/features/learning/course-content-tab'
import { CourseMembersTab } from '@/app/components/features/learning/course-members-tab'
import { CourseStatusTag } from '@/app/components/features/learning/learning-tags'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'

type EditTab = 'basic' | 'content' | 'members'

const TAB_KEYS: EditTab[] = ['basic', 'content', 'members']

export default function CourseEditPage() {
  const router = useRouter()
  const params = useParams<{ courseId: string }>()
  const searchParams = useSearchParams()
  const { locale } = useLocaleStore()

  const rawId = params.courseId
  const isNew = rawId === 'new'
  const courseId = isNew ? null : Number(rawId)
  const tabParam = searchParams.get('tab')
  const tab: EditTab = TAB_KEYS.includes(tabParam as EditTab) ? (tabParam as EditTab) : 'basic'

  const [creating, setCreating] = useState(false)
  const [confirmUnpublish, setConfirmUnpublish] = useState(false)

  const createCourse = useCreateCourse()
  const { data: course, isLoading, isError, refetch } = useAdminCourse(
    courseId !== null && Number.isFinite(courseId) ? courseId : null,
  )
  const publishMutation = usePublishCourse()
  const unpublishMutation = useUnpublishCourse()

  // /new creates a draft first so every tab operates on a real course entity.
  useEffect(() => {
    if (!isNew || creating) return
    setCreating(true)
    createCourse
      .mutateAsync({})
      .then((created) => {
        router.replace(`/learning/courses/${created.id}?tab=basic`)
      })
      .catch(() => {
        toast.error(t('learning.common.loadFailed', locale))
        router.replace('/learning/courses')
      })
  }, [isNew, creating, createCourse, router, locale])

  const switchTab = (next: EditTab) => {
    const paramsNext = new URLSearchParams(searchParams.toString())
    if (next === 'basic') paramsNext.delete('tab')
    else paramsNext.set('tab', next)
    const qs = paramsNext.toString()
    router.replace(qs ? `/learning/courses/${rawId}?${qs}` : `/learning/courses/${rawId}`)
  }

  const handlePublish = async () => {
    if (!course) return
    try {
      await publishMutation.mutateAsync(course.id)
      toast.success(t('learning.toast.published', locale))
    } catch {
      toast.error(t('learning.course.publishNotReady', locale))
    }
  }

  if (isNew) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        {t('learning.common.loading', locale)}
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between px-8 pt-5">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => router.push('/learning/courses')}
            className="flex shrink-0 items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <IconArrowLeft size={16} />
            <span>{t('learning.edit.back', locale)}</span>
          </button>
          <span className="h-4 w-px shrink-0 bg-border" />
          <h1 className="truncate text-base font-semibold text-foreground">
            {course
              ? t('learning.edit.titleEdit', locale, { name: course.name })
              : t('learning.common.loading', locale)}
          </h1>
          {course ? <CourseStatusTag status={course.status} /> : null}
        </div>
        {course ? (
          course.status === 'published' ? (
            <button
              type="button"
              onClick={() => setConfirmUnpublish(true)}
              className="h-9 shrink-0 rounded-md border border-amber-300 bg-white px-4 text-sm font-medium text-amber-700 hover:bg-amber-50"
            >
              {t('learning.courses.action.unpublish', locale)}
            </button>
          ) : (
            <button
              type="button"
              disabled={publishMutation.isPending}
              onClick={() => void handlePublish()}
              className="h-9 shrink-0 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {t('learning.courses.action.publish', locale)}
            </button>
          )
        ) : null}
      </header>

      <nav className="flex shrink-0 items-center gap-1 border-b border-border px-8 pt-4">
        {TAB_KEYS.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => switchTab(key)}
            className={`-mb-px flex h-11 items-center border-b-2 px-3 text-sm ${
              tab === key
                ? 'border-primary font-semibold text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {t(`learning.edit.tab.${key}`, locale)}
          </button>
        ))}
      </nav>

      <main className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t('learning.common.loading', locale)}</p>
        ) : isError || !course ? (
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
        ) : tab === 'basic' ? (
          <CourseBasicTab course={course} />
        ) : tab === 'content' ? (
          <CourseContentTab course={course} />
        ) : (
          <CourseMembersTab course={course} />
        )}
      </main>

      <ConfirmDialog
        open={confirmUnpublish}
        title={t('learning.confirm.unpublish.title', locale)}
        message={t('learning.confirm.unpublish.message', locale)}
        itemName={course?.name}
        confirmLabel={t('learning.confirm.unpublish.confirm', locale)}
        cancelLabel={t('learning.common.cancel', locale)}
        loading={unpublishMutation.isPending}
        onCancel={() => setConfirmUnpublish(false)}
        onConfirm={async () => {
          if (!course) return
          try {
            await unpublishMutation.mutateAsync(course.id)
            toast.success(t('learning.toast.unpublished', locale))
          } catch {
            toast.error(t('learning.common.loadFailed', locale))
          } finally {
            setConfirmUnpublish(false)
          }
        }}
      />
    </div>
  )
}
