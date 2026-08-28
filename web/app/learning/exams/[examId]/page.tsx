'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  useAdminExam,
  useCreateExam,
  usePublishExam,
  useUnpublishExam,
} from '@/service/use-learning-exam'
import { ExamBasicTab } from '@/app/components/features/learning/exam-basic-tab'
import { ExamQuestionsTab } from '@/app/components/features/learning/exam-questions-tab'
import { ExamMembersTab } from '@/app/components/features/learning/exam-members-tab'
import { ExamStatusTag } from '@/app/components/features/learning/learning-tags'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'

type EditTab = 'basic' | 'questions' | 'members'

const TAB_KEYS: EditTab[] = ['basic', 'questions', 'members']

export default function ExamEditPage() {
  const router = useRouter()
  const params = useParams<{ examId: string }>()
  const searchParams = useSearchParams()
  const { locale } = useLocaleStore()

  const rawId = params.examId
  const isNew = rawId === 'new'
  const examId = isNew ? null : Number(rawId)
  const tabParam = searchParams.get('tab')
  const tab: EditTab = TAB_KEYS.includes(tabParam as EditTab) ? (tabParam as EditTab) : 'basic'

  const [creating, setCreating] = useState(false)
  const [confirmUnpublish, setConfirmUnpublish] = useState(false)

  const createExam = useCreateExam()
  const { data: exam, isLoading, isError, refetch } = useAdminExam(
    examId !== null && Number.isFinite(examId) ? examId : null,
  )
  const publishMutation = usePublishExam()
  const unpublishMutation = useUnpublishExam()

  // /new creates a draft first so every tab operates on a real exam entity.
  useEffect(() => {
    if (!isNew || creating) return
    setCreating(true)
    createExam
      .mutateAsync({})
      .then((created) => {
        router.replace(`/learning/exams/${created.id}?tab=basic`)
      })
      .catch(() => {
        toast.error(t('learning.common.loadFailed', locale))
        router.replace('/learning/exams')
      })
  }, [isNew, creating, createExam, router, locale])

  const switchTab = (next: EditTab) => {
    const paramsNext = new URLSearchParams(searchParams.toString())
    if (next === 'basic') paramsNext.delete('tab')
    else paramsNext.set('tab', next)
    const qs = paramsNext.toString()
    router.replace(qs ? `/learning/exams/${rawId}?${qs}` : `/learning/exams/${rawId}`)
  }

  const handlePublish = async () => {
    if (!exam) return
    try {
      await publishMutation.mutateAsync(exam.id)
      toast.success(t('learning.exam.toast.published', locale))
    } catch {
      toast.error(t('learning.exam.publishNotReady', locale))
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
            onClick={() => router.push('/learning/exams')}
            className="flex shrink-0 items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <IconArrowLeft size={16} />
            <span>{t('learning.exam.edit.back', locale)}</span>
          </button>
          <span className="h-4 w-px shrink-0 bg-border" />
          <h1 className="truncate text-base font-semibold text-foreground">
            {exam
              ? t('learning.exam.edit.titleEdit', locale, { name: exam.name })
              : t('learning.common.loading', locale)}
          </h1>
          {exam ? <ExamStatusTag status={exam.status} /> : null}
        </div>
        {exam ? (
          exam.status === 'published' ? (
            <button
              type="button"
              onClick={() => setConfirmUnpublish(true)}
              className="h-9 shrink-0 rounded-md border border-amber-300 bg-white px-4 text-sm font-medium text-amber-700 hover:bg-amber-50"
            >
              {t('learning.exams.action.unpublish', locale)}
            </button>
          ) : (
            <button
              type="button"
              disabled={publishMutation.isPending}
              onClick={() => void handlePublish()}
              className="h-9 shrink-0 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {t('learning.exams.action.publish', locale)}
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
            {t(`learning.exam.edit.tab.${key}`, locale)}
          </button>
        ))}
      </nav>

      <main className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t('learning.common.loading', locale)}</p>
        ) : isError || !exam ? (
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
          <ExamBasicTab exam={exam} />
        ) : tab === 'questions' ? (
          <ExamQuestionsTab exam={exam} />
        ) : (
          <ExamMembersTab exam={exam} />
        )}
      </main>

      <ConfirmDialog
        open={confirmUnpublish}
        title={t('learning.exam.confirm.unpublish.title', locale)}
        message={t('learning.exam.confirm.unpublish.message', locale)}
        itemName={exam?.name}
        confirmLabel={t('learning.exam.confirm.unpublish.confirm', locale)}
        cancelLabel={t('learning.common.cancel', locale)}
        loading={unpublishMutation.isPending}
        onCancel={() => setConfirmUnpublish(false)}
        onConfirm={async () => {
          if (!exam) return
          try {
            await unpublishMutation.mutateAsync(exam.id)
            toast.success(t('learning.exam.toast.unpublished', locale))
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
