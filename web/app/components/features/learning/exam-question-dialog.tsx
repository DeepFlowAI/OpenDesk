'use client'

import { useEffect, useState } from 'react'
import { IconCheck, IconPlus, IconTrash, IconX } from '@tabler/icons-react'
import { toast } from 'sonner'
import type {
  ExamQuestionOption,
  ExamQuestionPayload,
  LearningExamQuestion,
  QuestionType,
} from '@/models/learning-exam'
import { useCreateQuestion, useUpdateQuestion } from '@/service/use-learning-exam'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

const MAX_OPTIONS = 6
const MIN_OPTIONS = 2

function optionKey(index: number): string {
  return String.fromCharCode(65 + index)
}

interface ExamQuestionDialogProps {
  open: boolean
  examId: number
  /** Set in edit mode; the question type is immutable once created. */
  question?: LearningExamQuestion
  /** Type chosen from the add-question dropdown in create mode. */
  presetType: QuestionType
  onClose: () => void
}

export function ExamQuestionDialog({ open, examId, question, presetType, onClose }: ExamQuestionDialogProps) {
  const { locale } = useLocaleStore()
  const createMutation = useCreateQuestion(examId)
  const updateMutation = useUpdateQuestion(examId)
  const saving = createMutation.isPending || updateMutation.isPending

  const questionType = question?.type ?? presetType
  const isJudge = questionType === 'judge'
  const isMultiple = questionType === 'multiple'

  const [stem, setStem] = useState('')
  const [score, setScore] = useState('5')
  const [options, setOptions] = useState<ExamQuestionOption[]>([])
  const [error, setError] = useState<string | null>(null)

  // Reset the form whenever the dialog opens for another question.
  useEffect(() => {
    if (!open) return
    setError(null)
    if (question) {
      setStem(question.stem)
      setScore(String(question.score))
      setOptions(question.options.map((o) => ({ key: o.key, text: o.text, is_correct: o.is_correct })))
      return
    }
    setStem('')
    setScore('5')
    if (presetType === 'judge') {
      setOptions([
        { key: 'true', text: null, is_correct: true },
        { key: 'false', text: null, is_correct: false },
      ])
    } else {
      setOptions([
        { key: 'A', text: '', is_correct: true },
        { key: 'B', text: '', is_correct: false },
      ])
    }
  }, [open, question, presetType])

  const markCorrect = (index: number) => {
    if (isMultiple) {
      setOptions(options.map((o, i) => (i === index ? { ...o, is_correct: !o.is_correct } : o)))
    } else {
      setOptions(options.map((o, i) => ({ ...o, is_correct: i === index })))
    }
  }

  const addOption = () => {
    if (options.length >= MAX_OPTIONS) return
    setOptions([...options, { key: optionKey(options.length), text: '', is_correct: false }])
  }

  const removeOption = (index: number) => {
    if (options.length <= MIN_OPTIONS) return
    // Re-letter the remaining options so keys stay contiguous (A, B, C...).
    setOptions(
      options
        .filter((_, i) => i !== index)
        .map((o, i) => ({ ...o, key: optionKey(i) })),
    )
  }

  const validate = (): string | null => {
    if (!stem.trim()) return t('learning.exam.question.error.stemRequired', locale)
    const scoreValue = Number(score)
    if (!Number.isInteger(scoreValue) || scoreValue < 1 || scoreValue > 100) {
      return t('learning.exam.question.error.scoreRequired', locale)
    }
    if (!isJudge && options.some((o) => !(o.text ?? '').trim())) {
      return t('learning.exam.question.error.optionRequired', locale)
    }
    const correctCount = options.filter((o) => o.is_correct).length
    if (isMultiple) {
      if (correctCount < 2) return t('learning.exam.question.error.multiCorrect', locale)
    } else if (correctCount !== 1) {
      return t('learning.exam.question.error.singleCorrect', locale)
    }
    return null
  }

  const handleSave = async () => {
    const message = validate()
    if (message) {
      setError(message)
      return
    }
    const payload: ExamQuestionPayload = {
      type: questionType,
      stem: stem.trim(),
      score: Number(score),
      options: isJudge
        ? options.map((o) => ({ key: o.key, text: null, is_correct: o.is_correct }))
        : options.map((o) => ({ key: o.key, text: (o.text ?? '').trim(), is_correct: o.is_correct })),
    }
    try {
      if (question) {
        await updateMutation.mutateAsync({ questionId: question.id, payload })
        toast.success(t('learning.exam.toast.questionUpdated', locale))
      } else {
        await createMutation.mutateAsync(payload)
        toast.success(t('learning.exam.toast.questionAdded', locale))
      }
      onClose()
    } catch {
      toast.error(t('learning.common.loadFailed', locale))
    }
  }

  if (!open) return null

  const typeLabel = t(`learning.exam.question.type.${questionType}`, locale)
  const optionsHint = isMultiple
    ? t('learning.exam.question.multiHint', locale)
    : isJudge
      ? t('learning.exam.question.judgeHint', locale)
      : t('learning.exam.question.singleHint', locale)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative flex max-h-[860px] w-[560px] flex-col rounded-xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-base font-semibold">
            {question
              ? t('learning.exam.question.editTitle', locale, { type: typeLabel })
              : t('learning.exam.question.addTitle', locale, { type: typeLabel })}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-accent"
            aria-label={t('learning.common.cancel', locale)}
          >
            <IconX size={18} />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-5">
          <div>
            <div className="mb-1.5 text-sm font-medium">
              {t('learning.exam.question.stemLabel', locale)}
              <span className="ml-0.5 text-red-500">*</span>
            </div>
            <textarea
              value={stem}
              onChange={(event) => setStem(event.target.value)}
              rows={3}
              maxLength={500}
              placeholder={t('learning.exam.question.stemPlaceholder', locale)}
              className="min-h-20 w-full rounded-md border border-border px-3 py-2 text-sm outline-none focus:border-primary"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              {t('learning.exam.question.stemHint', locale)}
            </p>
          </div>

          <div>
            <div className="mb-1.5 text-sm font-medium">
              {t('learning.exam.question.scoreLabel', locale)}
              <span className="ml-0.5 text-red-500">*</span>
            </div>
            <input
              type="number"
              min={1}
              max={100}
              value={score}
              onChange={(event) => setScore(event.target.value)}
              className="flex h-10 w-28 items-center rounded-md border border-border px-3 text-sm outline-none focus:border-primary"
            />
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-medium">
                {t('learning.exam.question.optionsLabel', locale)}
                <span className="ml-0.5 text-red-500">*</span>
              </span>
              <span className="text-xs text-muted-foreground">{optionsHint}</span>
            </div>
            <div className="space-y-2">
              {options.map((option, index) => (
                <div key={option.key} className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => markCorrect(index)}
                    className={`grid h-4 w-4 shrink-0 place-items-center border ${
                      isMultiple ? 'rounded' : 'rounded-full'
                    } ${
                      option.is_correct
                        ? 'border-primary bg-primary text-white'
                        : 'border-border hover:border-primary/60'
                    }`}
                    title={t('learning.exam.question.markCorrect', locale)}
                  >
                    {option.is_correct ? <IconCheck size={10} /> : null}
                  </button>
                  {isJudge ? (
                    <span className="text-sm">
                      {t(`learning.exam.question.judge.${option.key}`, locale)}
                    </span>
                  ) : (
                    <>
                      <span className="w-5 shrink-0 text-xs text-muted-foreground">{option.key}</span>
                      <input
                        value={option.text ?? ''}
                        onChange={(event) =>
                          setOptions(
                            options.map((o, i) => (i === index ? { ...o, text: event.target.value } : o)),
                          )
                        }
                        maxLength={200}
                        placeholder={t('learning.exam.question.optionPlaceholder', locale, {
                          letter: option.key,
                        })}
                        className="flex h-9 min-w-0 flex-1 items-center rounded-md border border-border px-3 text-sm outline-none focus:border-primary"
                      />
                      <button
                        type="button"
                        disabled={options.length <= MIN_OPTIONS}
                        onClick={() => removeOption(index)}
                        className="rounded p-1 text-muted-foreground/50 hover:bg-accent disabled:opacity-40"
                        aria-label={t('learning.exam.question.removeOption', locale)}
                      >
                        <IconTrash size={14} />
                      </button>
                    </>
                  )}
                </div>
              ))}
            </div>
            {!isJudge && options.length < MAX_OPTIONS ? (
              <button
                type="button"
                onClick={addOption}
                className="mt-3 flex h-8 items-center gap-1 text-xs font-medium text-primary"
              >
                <IconPlus size={14} />
                {t('learning.exam.question.addOption', locale)}
              </button>
            ) : null}
          </div>

          {error ? <p className="text-xs text-red-500">{error}</p> : null}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="h-9 rounded-md border border-border px-4 text-sm hover:bg-accent"
          >
            {t('learning.common.cancel', locale)}
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={handleSave}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            {saving ? t('learning.common.loading', locale) : t('learning.exam.question.save', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}
