'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  IconCircleDot,
  IconGripVertical,
  IconListCheck,
  IconPencil,
  IconPlus,
  IconTrash,
  IconToggleLeft,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import type { LearningExamDetail, LearningExamQuestion, QuestionType } from '@/models/learning-exam'
import { useDeleteQuestion, useReorderQuestions } from '@/service/use-learning-exam'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { ExamQuestionDialog } from './exam-question-dialog'

const TYPE_ICON: Record<QuestionType, typeof IconCircleDot> = {
  single: IconCircleDot,
  multiple: IconListCheck,
  judge: IconToggleLeft,
}

const QUESTION_TYPES: QuestionType[] = ['single', 'multiple', 'judge']

export function ExamQuestionsTab({ exam }: { exam: LearningExamDetail }) {
  const { locale } = useLocaleStore()
  const editable = exam.status === 'draft'

  const serverQuestions = useMemo(
    () => [...(exam.questions ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [exam.questions],
  )
  const [ordered, setOrdered] = useState<LearningExamQuestion[]>(serverQuestions)
  const [dirty, setDirty] = useState(false)
  const [dragIndex, setDragIndex] = useState<number | null>(null)

  const [typeMenuOpen, setTypeMenuOpen] = useState(false)
  const typeMenuRef = useRef<HTMLDivElement | null>(null)
  const [dialog, setDialog] = useState<{ question?: LearningExamQuestion; presetType: QuestionType } | null>(null)
  const [deleting, setDeleting] = useState<LearningExamQuestion | null>(null)

  const reorderMutation = useReorderQuestions(exam.id)
  const deleteMutation = useDeleteQuestion(exam.id)

  // Resync local order from the server once no local drag is pending.
  useEffect(() => {
    if (!dirty) setOrdered(serverQuestions)
  }, [serverQuestions, dirty])

  // Close the type dropdown on outside click.
  useEffect(() => {
    if (!typeMenuOpen) return
    const onClick = (event: MouseEvent) => {
      if (typeMenuRef.current && !typeMenuRef.current.contains(event.target as Node)) {
        setTypeMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [typeMenuOpen])

  const totalScore = ordered.reduce((sum, q) => sum + q.score, 0)
  const publishReady = ordered.length >= 1 && totalScore > 0

  const handleDrop = (targetIndex: number) => {
    if (dragIndex === null || dragIndex === targetIndex) {
      setDragIndex(null)
      return
    }
    const next = [...ordered]
    const [moved] = next.splice(dragIndex, 1)
    next.splice(targetIndex, 0, moved)
    setOrdered(next)
    setDragIndex(null)
    setDirty(true)
  }

  const saveOrder = async () => {
    try {
      await reorderMutation.mutateAsync(ordered.map((q) => q.id))
      setDirty(false)
      toast.success(t('learning.exam.toast.questionsReordered', locale))
    } catch {
      toast.error(t('learning.common.loadFailed', locale))
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <span>
            {t('learning.exam.questions.stats', locale, {
              count: String(ordered.length),
              total: String(totalScore),
            })}
          </span>
          {editable && !publishReady ? (
            <span className="text-xs text-amber-600">
              {t('learning.exam.questions.publishHint', locale)}
            </span>
          ) : null}
          {!editable ? (
            <span className="text-xs">{t('learning.exam.questions.readonlyHint', locale)}</span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {dirty ? (
            <button
              type="button"
              disabled={reorderMutation.isPending}
              onClick={saveOrder}
              className="h-9 rounded-md border border-border bg-white px-4 text-sm font-medium hover:bg-accent disabled:opacity-50"
            >
              {t('learning.exam.questions.saveOrder', locale)}
            </button>
          ) : null}
          {editable ? (
            <div className="relative" ref={typeMenuRef}>
              <button
                type="button"
                onClick={() => setTypeMenuOpen((open) => !open)}
                className="flex h-9 items-center gap-1 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground"
              >
                <IconPlus size={14} />
                <span>{t('learning.exam.questions.add', locale)}</span>
                <span className="ml-1 text-[10px] opacity-70">▾</span>
              </button>
              {typeMenuOpen ? (
                <div className="absolute right-0 z-20 mt-1 w-32 overflow-hidden rounded-md border border-border bg-white py-1 shadow-lg">
                  {QUESTION_TYPES.map((type) => (
                    <button
                      key={type}
                      type="button"
                      onClick={() => {
                        setTypeMenuOpen(false)
                        setDialog({ presetType: type })
                      }}
                      className="flex w-full items-center px-3 py-2 text-left text-sm hover:bg-accent"
                    >
                      {t(`learning.exam.question.type.${type}`, locale)}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      {ordered.length === 0 ? (
        <div className="flex h-64 flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-white/60">
          <p className="text-sm text-muted-foreground">{t('learning.exam.questions.empty', locale)}</p>
          {editable ? (
            <button
              type="button"
              onClick={() => setDialog({ presetType: 'single' })}
              className="flex h-9 items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
            >
              <IconPlus size={16} />
              {t('learning.exam.questions.add', locale)}
            </button>
          ) : null}
        </div>
      ) : (
        <div className="space-y-2 pb-2">
          {ordered.map((question, index) => {
            const TypeIcon = TYPE_ICON[question.type]
            return (
              <div
                key={question.id}
                draggable={editable}
                onDragStart={() => setDragIndex(index)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => handleDrop(index)}
                onDragEnd={() => setDragIndex(null)}
                className={`flex items-center gap-2.5 rounded-md border border-border bg-white px-3 py-2.5 ${
                  dragIndex === index ? 'opacity-50' : ''
                }`}
              >
                {editable ? (
                  <IconGripVertical size={14} className="shrink-0 cursor-grab text-muted-foreground/50" />
                ) : null}
                <span className="w-6 shrink-0 text-center text-xs text-muted-foreground">{index + 1}</span>
                <TypeIcon size={15} className="shrink-0 text-muted-foreground" />
                <span className="shrink-0 rounded-md bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                  {t(`learning.exam.question.type.${question.type}`, locale)}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm" title={question.stem}>
                  {question.stem}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {t('learning.exam.question.scoreText', locale, { score: String(question.score) })}
                </span>
                {editable ? (
                  <div className="flex shrink-0 items-center gap-2 text-muted-foreground">
                    <button
                      type="button"
                      onClick={() => setDialog({ question, presetType: question.type })}
                      className="rounded p-1 hover:bg-accent"
                      aria-label={t('learning.exam.questions.edit', locale)}
                    >
                      <IconPencil size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleting(question)}
                      className="rounded p-1 hover:bg-accent"
                      aria-label={t('learning.exam.questions.delete', locale)}
                    >
                      <IconTrash size={14} className="text-red-500" />
                    </button>
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      )}

      {dialog ? (
        <ExamQuestionDialog
          open
          examId={exam.id}
          question={dialog.question}
          presetType={dialog.presetType}
          onClose={() => setDialog(null)}
        />
      ) : null}

      <ConfirmDialog
        open={deleting !== null}
        title={t('learning.exam.confirm.deleteQuestion.title', locale)}
        message={t('learning.exam.confirm.deleteQuestion.message', locale)}
        itemName={deleting?.stem}
        confirmLabel={t('learning.exam.confirm.deleteQuestion.confirm', locale)}
        cancelLabel={t('learning.common.cancel', locale)}
        variant="destructive"
        loading={deleteMutation.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={async () => {
          if (!deleting) return
          try {
            await deleteMutation.mutateAsync(deleting.id)
            toast.success(t('learning.exam.toast.questionDeleted', locale))
          } catch {
            toast.error(t('learning.common.loadFailed', locale))
          } finally {
            setDeleting(null)
          }
        }}
      />
    </div>
  )
}
