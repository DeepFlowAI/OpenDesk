'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import {
  IconArrowLeft,
  IconCheck,
  IconCircleCheck,
  IconCircleDot,
  IconClock,
  IconListCheck,
  IconToggleLeft,
  IconX,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type {
  AttemptDetailResponse,
  AttemptQuestion,
  AttemptQuestionOption,
  MyExamSummary,
  QuestionType,
} from '@/models/learning-exam'
import {
  useAbandonExamAttempt,
  useExamAttempt,
  useMyExamSummary,
  useSubmitExamAttempt,
} from '@/service/use-learning-exam'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { ExamStartConfirmDialog } from '@/app/components/features/learning/exam-start-confirm-dialog'
import {
  formatDurationSeconds,
  formatLearningDateTime,
} from '@/app/components/features/learning/learning-tags'
import { cn } from '@/lib/utils'

const TYPE_ICON: Record<QuestionType, typeof IconCircleDot> = {
  single: IconCircleDot,
  multiple: IconListCheck,
  judge: IconToggleLeft,
}

type Locale = Parameters<typeof t>[1]

function optionText(option: AttemptQuestionOption, locale: Locale): string {
  if (option.key === 'true' || option.key === 'false') {
    return t(`learning.exam.question.judge.${option.key}`, locale)
  }
  return `${option.key}. ${option.text ?? ''}`
}

// ---------------------------------------------------------------------------
// Taking view
// ---------------------------------------------------------------------------

function TakingQuestionBlock({
  question,
  index,
  selected,
  disabled,
  onToggle,
}: {
  question: AttemptQuestion
  index: number
  selected: string[]
  disabled: boolean
  onToggle: (key: string) => void
}) {
  const { locale } = useLocaleStore()
  const TypeIcon = TYPE_ICON[question.type]
  const multi = question.type === 'multiple'
  return (
    <div className="rounded-xl border border-border bg-white p-5">
      <div className="mb-3 flex items-start gap-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted text-xs font-semibold">
          {index + 1}
        </span>
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
              <TypeIcon size={12} />
              {t(`learning.exam.question.type.${question.type}`, locale)}
            </span>
            <span className="text-[11px] text-muted-foreground">
              {t('learning.exam.question.scoreText', locale, { score: String(question.score) })}
            </span>
          </div>
          <p className="text-sm font-medium leading-6">{question.stem}</p>
        </div>
      </div>
      <div className="ml-10 space-y-2">
        {question.options.map((option) => {
          const checked = selected.includes(option.key)
          return (
            <button
              key={option.key}
              type="button"
              disabled={disabled}
              onClick={() => onToggle(option.key)}
              className={cn(
                'flex w-full items-center gap-3 rounded-md border px-3 py-2.5 text-left text-sm',
                checked ? 'border-primary/40 bg-primary/5' : 'border-border bg-white',
                disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
              )}
            >
              <span
                className={cn(
                  'grid h-4 w-4 shrink-0 place-items-center border',
                  multi ? 'rounded' : 'rounded-full',
                  checked ? 'border-primary bg-primary text-white' : 'border-border',
                )}
              >
                {checked ? <IconCircleCheck size={11} stroke={3} /> : null}
              </span>
              <span>{optionText(option, locale)}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function TakingView({ attempt, examName }: { attempt: AttemptDetailResponse; examName: string }) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const [answers, setAnswers] = useState<Record<number, string[]>>({})
  const [submitOpen, setSubmitOpen] = useState(false)
  const [pendingNav, setPendingNav] = useState<string | null>(null)
  const submitMutation = useSubmitExamAttempt()
  const abandonMutation = useAbandonExamAttempt()
  const submittedRef = useRef(false)
  const answersRef = useRef(answers)
  answersRef.current = answers

  const questions = attempt.questions
  const answeredCount = questions.filter((q) => (answers[q.question_id]?.length ?? 0) > 0).length
  const unansweredCount = questions.length - answeredCount

  const deadlineMs =
    attempt.time_limit_minutes === null
      ? null
      : new Date(attempt.started_at).getTime() + attempt.time_limit_minutes * 60_000
  const [remainingSec, setRemainingSec] = useState<number | null>(() =>
    deadlineMs === null ? null : Math.max(0, Math.floor((deadlineMs - Date.now()) / 1000)),
  )

  const submit = useCallback(
    async (auto: boolean) => {
      if (submittedRef.current) return
      submittedRef.current = true
      const payload: Record<string, string[]> = {}
      for (const [id, keys] of Object.entries(answersRef.current)) {
        if (keys.length > 0) payload[id] = keys
      }
      try {
        await submitMutation.mutateAsync({ attemptId: attempt.attempt_id, answers: payload })
        toast.success(
          t(auto ? 'learning.myexam.toast.autoSubmitted' : 'learning.myexam.toast.submitted', locale),
        )
        router.replace(`/learning/exams/my/${attempt.exam_id}?attempt=${attempt.attempt_id}`)
      } catch {
        submittedRef.current = false
        toast.error(t('learning.common.loadFailed', locale))
      }
    },
    [attempt.attempt_id, attempt.exam_id, locale, router, submitMutation],
  )

  // Countdown: hitting zero auto-submits the current answers.
  useEffect(() => {
    if (deadlineMs === null) return
    const timer = setInterval(() => {
      const left = Math.max(0, Math.floor((deadlineMs - Date.now()) / 1000))
      setRemainingSec(left)
      if (left <= 0) {
        clearInterval(timer)
        void submit(true)
      }
    }, 1000)
    return () => clearInterval(timer)
  }, [deadlineMs, submit])

  // Leaving discards the attempt: warn on tab close and intercept in-app link clicks.
  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [])

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      const anchor = (event.target as HTMLElement | null)?.closest?.('a[href]')
      if (!anchor) return
      const href = anchor.getAttribute('href') ?? ''
      if (!href.startsWith('/')) return
      event.preventDefault()
      event.stopPropagation()
      setPendingNav(href)
    }
    document.addEventListener('click', onClick, true)
    return () => document.removeEventListener('click', onClick, true)
  }, [])

  const confirmLeave = async () => {
    const href = pendingNav
    if (!href) return
    // Best-effort: a stale in-progress attempt is also discarded when the next one starts.
    try {
      await abandonMutation.mutateAsync(attempt.attempt_id)
    } catch {
      // Navigation proceeds either way.
    }
    router.push(href)
  }

  const timerText = remainingSec === null ? null : (formatDurationSeconds(remainingSec) ?? '00:00')

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-border bg-white px-8 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => setPendingNav('/learning/exams/my')}
            className="flex shrink-0 items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <IconArrowLeft size={16} />
            <span>{t('learning.myexam.back', locale)}</span>
          </button>
          <span className="h-4 w-px shrink-0 bg-border" />
          <h1 className="truncate text-base font-semibold text-foreground">{examName}</h1>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-muted-foreground">
            {t('learning.myexam.taking.answered', locale, {
              answered: String(answeredCount),
              total: String(questions.length),
            })}
          </span>
          {timerText !== null ? (
            <span className="inline-flex items-center gap-1.5 rounded-md bg-amber-50 px-3 py-1.5 font-mono text-sm font-semibold text-amber-700">
              <IconClock size={16} />
              {timerText}
            </span>
          ) : null}
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
        <div className="mx-auto max-w-3xl space-y-4 pb-24">
          {questions.map((question, index) => (
            <TakingQuestionBlock
              key={question.question_id}
              question={question}
              index={index}
              selected={answers[question.question_id] ?? []}
              disabled={submitMutation.isPending}
              onToggle={(key) =>
                setAnswers((prev) => {
                  const current = prev[question.question_id] ?? []
                  if (question.type === 'multiple') {
                    return {
                      ...prev,
                      [question.question_id]: current.includes(key)
                        ? current.filter((item) => item !== key)
                        : [...current, key],
                    }
                  }
                  return { ...prev, [question.question_id]: [key] }
                })
              }
            />
          ))}
        </div>
      </main>

      <footer className="flex shrink-0 items-center justify-between border-t border-border bg-white px-8 py-3">
        <p className="text-xs text-muted-foreground">{t('learning.myexam.taking.submitHint', locale)}</p>
        <button
          type="button"
          disabled={submitMutation.isPending}
          onClick={() => setSubmitOpen(true)}
          className="h-10 rounded-md bg-primary px-6 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {t('learning.myexam.taking.submit', locale)}
        </button>
      </footer>

      <ConfirmDialog
        open={submitOpen}
        title={t('learning.myexam.submitConfirm.title', locale)}
        message={
          unansweredCount > 0
            ? t('learning.myexam.submitConfirm.unanswered', locale, { count: String(unansweredCount) })
            : t('learning.myexam.submitConfirm.allAnswered', locale)
        }
        confirmLabel={t('learning.myexam.submitConfirm.confirm', locale)}
        cancelLabel={t('learning.myexam.submitConfirm.cancel', locale)}
        loading={submitMutation.isPending}
        onCancel={() => setSubmitOpen(false)}
        onConfirm={async () => {
          setSubmitOpen(false)
          await submit(false)
        }}
      />
      <ConfirmDialog
        open={pendingNav !== null}
        title={t('learning.myexam.leave.title', locale)}
        message={t('learning.myexam.leave.message', locale)}
        confirmLabel={t('learning.myexam.leave.confirm', locale)}
        cancelLabel={t('learning.common.cancel', locale)}
        variant="destructive"
        loading={abandonMutation.isPending}
        onCancel={() => setPendingNav(null)}
        onConfirm={confirmLeave}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Result view
// ---------------------------------------------------------------------------

function ReviewBlock({ question, index }: { question: AttemptQuestion; index: number }) {
  const { locale } = useLocaleStore()
  const TypeIcon = TYPE_ICON[question.type]
  const gained = question.gained_score ?? 0
  const correct = Boolean(question.is_correct)
  const selectedKeys = question.selected_keys ?? []
  return (
    <div className="rounded-xl border border-border bg-white p-5">
      <div className="mb-3 flex items-start gap-3">
        <span
          className={cn(
            'flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-semibold',
            correct ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600',
          )}
        >
          {correct ? <IconCheck size={14} /> : <IconX size={14} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">
              {t('learning.myexam.result.questionIndex', locale, { index: String(index + 1) })}
            </span>
            <span className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
              <TypeIcon size={12} />
              {t(`learning.exam.question.type.${question.type}`, locale)}
            </span>
            <span className="text-[11px] text-muted-foreground">
              {t('learning.myexam.result.gainedScore', locale, {
                gained: String(gained),
                score: String(question.score),
              })}
            </span>
          </div>
          <p className="text-sm font-medium leading-6">{question.stem}</p>
        </div>
      </div>
      <div className="ml-10 space-y-2">
        {question.options.map((option) => {
          const selected = selectedKeys.includes(option.key)
          const isCorrect = Boolean(option.is_correct)
          return (
            <div
              key={option.key}
              className={cn(
                'flex items-center gap-3 rounded-md border px-3 py-2.5 text-sm',
                isCorrect
                  ? 'border-emerald-300 bg-emerald-50'
                  : selected
                    ? 'border-red-300 bg-red-50'
                    : 'border-border bg-white',
              )}
            >
              <span className="min-w-0 flex-1">{optionText(option, locale)}</span>
              {isCorrect ? (
                <span className="shrink-0 text-[11px] text-emerald-700">
                  {t('learning.myexam.result.correctAnswer', locale)}
                </span>
              ) : null}
              {selected ? (
                <span
                  className={cn(
                    'shrink-0 text-[11px]',
                    isCorrect ? 'text-emerald-700' : 'text-red-600',
                  )}
                >
                  {t('learning.myexam.result.yourAnswer', locale)}
                </span>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ResultView({ attempt, summary }: { attempt: AttemptDetailResponse; summary: MyExamSummary }) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const [retrying, setRetrying] = useState(false)

  const durationSec = attempt.submitted_at
    ? (new Date(attempt.submitted_at).getTime() - new Date(attempt.started_at).getTime()) / 1000
    : null
  const durationText = formatDurationSeconds(durationSec)

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-border bg-white px-8 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => router.push('/learning/exams/my')}
            className="flex shrink-0 items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <IconArrowLeft size={16} />
            <span>{t('learning.myexam.back', locale)}</span>
          </button>
          <span className="h-4 w-px shrink-0 bg-border" />
          <h1 className="truncate text-base font-semibold text-foreground">{summary.name}</h1>
        </div>
        {summary.remaining_attempts > 0 ? (
          <button
            type="button"
            onClick={() => setRetrying(true)}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
          >
            {t('learning.myexam.action.retry', locale)}
          </button>
        ) : null}
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
        <div className="mx-auto max-w-3xl space-y-5">
          <section className="rounded-xl border border-border bg-white p-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="text-sm text-muted-foreground">
                  {t('learning.myexam.result.scoreLabel', locale)}
                </div>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="font-display text-4xl font-bold tracking-tight">
                    {attempt.score ?? 0}
                  </span>
                  <span className="text-muted-foreground">/ {summary.total_score}</span>
                  <span
                    className={cn(
                      'rounded-md px-2 py-0.5 text-xs',
                      attempt.passed
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-amber-50 text-amber-700',
                    )}
                  >
                    {attempt.passed
                      ? t('learning.myexam.result.passed', locale)
                      : t('learning.myexam.result.failed', locale)}
                  </span>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {t('learning.myexam.result.passLine', locale, {
                    score: String(summary.pass_score),
                    percent: String(summary.pass_percent),
                  })}
                  {' · '}
                  {t('learning.myexam.result.attemptIndex', locale, {
                    index: String(attempt.attempt_index ?? 1),
                  })}
                  {durationText
                    ? ` · ${t('learning.myexam.result.duration', locale, { duration: durationText })}`
                    : ''}
                </p>
              </div>
              <div className="text-right text-xs text-muted-foreground">
                {t('learning.myexam.result.submittedAt', locale)}
                <div className="mt-1 text-sm text-foreground">
                  {formatLearningDateTime(attempt.submitted_at)}
                </div>
              </div>
            </div>
          </section>

          <section className="rounded-xl border border-border bg-white p-4">
            <div className="mb-3 text-sm font-medium">
              {t('learning.myexam.result.history', locale)}
            </div>
            {summary.attempts.length === 0 ? (
              <p className="py-2 text-sm text-muted-foreground">
                {t('learning.myexam.result.historyEmpty', locale)}
              </p>
            ) : (
              <div className="space-y-2">
                {summary.attempts.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() =>
                      router.replace(`/learning/exams/my/${summary.id}?attempt=${item.id}`)
                    }
                    className={cn(
                      'flex w-full items-center justify-between rounded-md border px-3 py-2.5 text-left text-sm',
                      item.id === attempt.attempt_id
                        ? 'border-border/50 bg-muted/30'
                        : 'border-border/40 hover:bg-muted/20',
                    )}
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-medium">
                        {t('learning.myexam.result.attemptIndex', locale, {
                          index: String(item.attempt_index),
                        })}
                      </span>
                      <span className="text-muted-foreground">
                        {formatLearningDateTime(item.submitted_at)}
                      </span>
                      <span
                        className={cn(
                          'rounded-md px-2 py-0.5 text-[11px]',
                          item.passed
                            ? 'bg-emerald-50 text-emerald-700'
                            : 'bg-amber-50 text-amber-700',
                        )}
                      >
                        {item.passed
                          ? t('learning.myexam.result.passed', locale)
                          : t('learning.myexam.result.failed', locale)}
                      </span>
                    </div>
                    <span className="font-medium">
                      {item.score}/{summary.total_score}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="space-y-3">
            <div className="text-sm font-medium">{t('learning.myexam.result.review', locale)}</div>
            {attempt.questions.map((question, index) => (
              <ReviewBlock key={question.question_id} question={question} index={index} />
            ))}
          </section>
        </div>
      </main>

      {retrying ? (
        <ExamStartConfirmDialog
          exam={{
            id: summary.id,
            name: summary.name,
            time_limit_minutes: summary.time_limit_minutes,
          }}
          onClose={() => setRetrying(false)}
        />
      ) : null}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page: same route hosts the taking view (in-progress attempt) and the result
// view (submitted attempt), switched by the attempt's status.
// ---------------------------------------------------------------------------

export default function MyExamDetailPage() {
  const router = useRouter()
  const params = useParams<{ examId: string }>()
  const searchParams = useSearchParams()
  const { locale } = useLocaleStore()

  const examId = Number(params.examId)
  const validExamId = Number.isFinite(examId) && examId > 0
  const attemptParam = searchParams.get('attempt')
  const attemptId = attemptParam === null ? null : Number(attemptParam)

  const summaryQuery = useMyExamSummary(validExamId ? examId : null)
  const attemptQuery = useExamAttempt(
    attemptId !== null && Number.isFinite(attemptId) && attemptId > 0 ? attemptId : null,
  )

  const summary = summaryQuery.data
  const attempt = attemptQuery.data

  // Without an attempt param, open the best attempt's result; with no result at
  // all there is nothing to show here, so go back to the list.
  useEffect(() => {
    if (!validExamId || attemptParam !== null || !summary) return
    if (summary.best_attempt_id !== null) {
      router.replace(`/learning/exams/my/${examId}?attempt=${summary.best_attempt_id}`)
    } else {
      router.replace('/learning/exams/my')
    }
  }, [validExamId, attemptParam, summary, examId, router])

  // Abandoned attempts have no viewable state; fall back to the exam entry.
  useEffect(() => {
    if (attempt?.status === 'abandoned') {
      router.replace(`/learning/exams/my/${examId}`)
    }
  }, [attempt, examId, router])

  if (!validExamId) return null

  const fullLoading = (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      {t('learning.common.loading', locale)}
    </div>
  )

  if (attemptParam === null) return fullLoading
  if (summaryQuery.isLoading || attemptQuery.isLoading) return fullLoading
  if (summaryQuery.isError || attemptQuery.isError || !summary || !attempt) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <p className="text-sm text-muted-foreground">{t('learning.common.loadFailed', locale)}</p>
        <button
          type="button"
          onClick={() => {
            void summaryQuery.refetch()
            void attemptQuery.refetch()
          }}
          className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
        >
          {t('learning.common.retry', locale)}
        </button>
      </div>
    )
  }
  if (attempt.status === 'abandoned') return fullLoading

  return attempt.status === 'in_progress' ? (
    <TakingView key={attempt.attempt_id} attempt={attempt} examName={summary.name} />
  ) : (
    <ResultView key={attempt.attempt_id} attempt={attempt} summary={summary} />
  )
}
