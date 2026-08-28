'use client'

import { useEffect, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import type { LearningExamDetail } from '@/models/learning-exam'
import { useUpdateExam } from '@/service/use-learning-exam'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

function FormField({
  label,
  required,
  hint,
  children,
}: {
  label: string
  required?: boolean
  hint?: string
  children: ReactNode
}) {
  return (
    <div>
      <div className="mb-1.5 text-sm font-medium">
        {label}
        {required ? <span className="ml-0.5 text-red-500">*</span> : null}
      </div>
      {children}
      {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  )
}

export function ExamBasicTab({ exam }: { exam: LearningExamDetail }) {
  const { locale } = useLocaleStore()
  const editable = exam.status === 'draft'
  const updateMutation = useUpdateExam(exam.id)

  const [name, setName] = useState(exam.name)
  const [intro, setIntro] = useState(exam.intro ?? '')
  const [passPercent, setPassPercent] = useState(String(exam.pass_percent))
  const [timeLimit, setTimeLimit] = useState(
    exam.time_limit_minutes === null ? '' : String(exam.time_limit_minutes),
  )
  const [maxAttempts, setMaxAttempts] = useState(String(exam.max_attempts))
  const [shuffle, setShuffle] = useState(exam.shuffle_questions)
  const [error, setError] = useState<string | null>(null)

  // Reset the form when navigating between exams.
  useEffect(() => {
    setName(exam.name)
    setIntro(exam.intro ?? '')
    setPassPercent(String(exam.pass_percent))
    setTimeLimit(exam.time_limit_minutes === null ? '' : String(exam.time_limit_minutes))
    setMaxAttempts(String(exam.max_attempts))
    setShuffle(exam.shuffle_questions)
    setError(null)
  }, [exam])

  const totalScore = (exam.questions ?? []).reduce((sum, q) => sum + q.score, 0)
  const passScorePreview = Math.floor((totalScore * Number(passPercent || '0')) / 100)

  const handleSave = async () => {
    if (!name.trim()) {
      setError(t('learning.exam.basic.error.nameRequired', locale))
      return
    }
    const percent = Number(passPercent)
    if (!Number.isInteger(percent) || percent < 1 || percent > 100) {
      setError(t('learning.exam.basic.error.passPercentInvalid', locale))
      return
    }
    if (timeLimit !== '') {
      const minutes = Number(timeLimit)
      if (!Number.isInteger(minutes) || minutes < 1 || minutes > 180) {
        setError(t('learning.exam.basic.error.timeLimitInvalid', locale))
        return
      }
    }
    const attempts = Number(maxAttempts)
    if (!Number.isInteger(attempts) || attempts < 1 || attempts > 10) {
      setError(t('learning.exam.basic.error.maxAttemptsInvalid', locale))
      return
    }
    setError(null)
    try {
      await updateMutation.mutateAsync({
        name: name.trim(),
        intro: intro.trim(),
        pass_percent: percent,
        time_limit_minutes: timeLimit === '' ? null : Number(timeLimit),
        max_attempts: attempts,
        shuffle_questions: shuffle,
      })
      toast.success(t('learning.exam.toast.updated', locale))
    } catch {
      toast.error(t('learning.common.loadFailed', locale))
    }
  }

  const inputCls =
    'flex h-10 items-center rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-primary disabled:bg-muted/50'

  return (
    <div className="max-w-xl space-y-6 rounded-xl border border-border bg-white p-6">
      {!editable ? (
        <p className="text-xs text-muted-foreground">
          {t('learning.exam.basic.readonlyHint', locale)}
        </p>
      ) : null}

      <FormField
        label={t('learning.exam.basic.name', locale)}
        required
        hint={t('learning.exam.basic.nameHint', locale)}
      >
        <input
          value={name}
          disabled={!editable}
          onChange={(event) => setName(event.target.value)}
          maxLength={50}
          className={`${inputCls} w-full`}
        />
      </FormField>

      <FormField label={t('learning.exam.basic.intro', locale)} hint={t('learning.exam.basic.introHint', locale)}>
        <textarea
          value={intro}
          disabled={!editable}
          onChange={(event) => setIntro(event.target.value)}
          maxLength={200}
          className="h-24 w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus:border-primary disabled:bg-muted/50"
        />
      </FormField>

      <FormField
        label={t('learning.exam.basic.passPercent', locale)}
        required
        hint={t('learning.exam.basic.passPercentHint', locale)}
      >
        <div className={`${inputCls} w-40 gap-2`}>
          <input
            type="number"
            min={1}
            max={100}
            value={passPercent}
            disabled={!editable}
            onChange={(event) => setPassPercent(event.target.value)}
            className="min-w-0 flex-1 outline-none disabled:bg-transparent"
          />
          <span className="text-muted-foreground">%</span>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {t('learning.exam.basic.passScorePreview', locale, {
            total: String(totalScore),
            score: String(passScorePreview),
          })}
        </p>
      </FormField>

      <FormField label={t('learning.exam.basic.timeLimit', locale)}>
        <div className="flex items-center gap-4">
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="radio"
              name="exam-time-limit"
              checked={timeLimit === ''}
              disabled={!editable}
              onChange={() => setTimeLimit('')}
              className="h-4 w-4 accent-primary"
            />
            {t('learning.exam.basic.noLimit', locale)}
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="radio"
              name="exam-time-limit"
              checked={timeLimit !== ''}
              disabled={!editable}
              onChange={() => setTimeLimit((current) => current || '30')}
              className="h-4 w-4 accent-primary"
            />
            {t('learning.exam.basic.limited', locale)}
          </label>
          {timeLimit !== '' ? (
            <div className={`${inputCls} w-36 gap-2`}>
              <input
                type="number"
                min={1}
                max={180}
                value={timeLimit}
                disabled={!editable}
                onChange={(event) => setTimeLimit(event.target.value)}
                className="min-w-0 flex-1 outline-none disabled:bg-transparent"
              />
              <span className="text-muted-foreground">
                {t('learning.exam.basic.minuteUnit', locale)}
              </span>
            </div>
          ) : null}
        </div>
      </FormField>

      <FormField
        label={t('learning.exam.basic.maxAttempts', locale)}
        required
        hint={t('learning.exam.basic.maxAttemptsHint', locale)}
      >
        <input
          type="number"
          min={1}
          max={10}
          value={maxAttempts}
          disabled={!editable}
          onChange={(event) => setMaxAttempts(event.target.value)}
          className={`${inputCls} w-40`}
        />
      </FormField>

      <FormField label={t('learning.exam.basic.shuffle', locale)}>
        <label className="flex items-center gap-3 text-sm">
          <button
            type="button"
            role="switch"
            aria-checked={shuffle}
            disabled={!editable}
            onClick={() => setShuffle(!shuffle)}
            className={`relative h-5 w-9 rounded-full transition-colors disabled:opacity-60 ${
              shuffle ? 'bg-primary' : 'bg-muted'
            }`}
          >
            <span
              className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${
                shuffle ? 'left-[18px]' : 'left-0.5'
              }`}
            />
          </button>
          <span className="text-muted-foreground">
            {shuffle
              ? t('learning.exam.basic.shuffleOn', locale)
              : t('learning.exam.basic.shuffleOff', locale)}
          </span>
        </label>
      </FormField>

      {error ? <p className="text-xs text-red-500">{error}</p> : null}

      {editable ? (
        <div className="flex justify-end border-t border-border pt-4">
          <button
            type="button"
            disabled={updateMutation.isPending}
            onClick={handleSave}
            className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            {updateMutation.isPending ? t('learning.common.loading', locale) : t('learning.common.save', locale)}
          </button>
        </div>
      ) : null}
    </div>
  )
}
