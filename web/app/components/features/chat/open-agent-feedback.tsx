'use client'

import { useMemo, useState } from 'react'
import { IconLoader2, IconThumbDown, IconThumbUp, IconX } from '@tabler/icons-react'
import { cn } from '@/lib/utils'

export type OpenAgentFeedbackRating = 'like' | 'dislike'

export type OpenAgentFeedbackSubmitInput = {
  messageId: number
  stepId: number
  rating: OpenAgentFeedbackRating
  comment?: string | null
}

type OpenAgentFeedbackValue = {
  stepId: number | null
  rating: OpenAgentFeedbackRating | null
  comment: string | null
  updatedAt: string | null
}

type OpenAgentFeedbackProps = {
  messageId: number
  senderType: string
  metadata?: Record<string, unknown>
  locale: string
  enabled?: boolean
  readonly?: boolean
  align?: 'start' | 'end'
  onSubmit?: (input: OpenAgentFeedbackSubmitInput) => Promise<void>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function positiveInt(value: unknown): number | null {
  if (typeof value === 'number' && Number.isInteger(value) && value > 0) return value
  if (typeof value === 'string' && /^\d+$/.test(value.trim())) {
    const parsed = Number(value.trim())
    return parsed > 0 ? parsed : null
  }
  return null
}

function ratingValue(value: unknown): OpenAgentFeedbackRating | null {
  return value === 'like' || value === 'dislike' ? value : null
}

function textValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

export function resolveOpenAgentFeedback(metadata?: Record<string, unknown>): OpenAgentFeedbackValue {
  const feedback = isRecord(metadata?.open_agent_feedback) ? metadata.open_agent_feedback : {}
  return {
    stepId: positiveInt(feedback.step_id) ?? positiveInt(metadata?.open_agent_feedback_step_id),
    rating: ratingValue(feedback.rating),
    comment: textValue(feedback.comment),
    updatedAt: textValue(feedback.updated_at),
  }
}

function feedbackText(rating: OpenAgentFeedbackRating | null, locale: string): string {
  if (rating === 'like') return locale === 'zh' ? '已点赞' : 'Liked'
  if (rating === 'dislike') return locale === 'zh' ? '已点踩' : 'Disliked'
  return locale === 'zh' ? '反馈' : 'Feedback'
}

function formatFeedbackTime(value: string | null, locale: string): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

export function OpenAgentFeedback({
  messageId,
  senderType,
  metadata,
  locale,
  enabled = false,
  readonly = false,
  align = 'start',
  onSubmit,
}: OpenAgentFeedbackProps) {
  const feedback = useMemo(() => resolveOpenAgentFeedback(metadata), [metadata])
  const [commentOpen, setCommentOpen] = useState(false)
  const [comment, setComment] = useState(feedback.comment ?? '')
  const [pendingRating, setPendingRating] = useState<OpenAgentFeedbackRating | null>(null)
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const isBot = senderType === 'bot'
  const isStreaming = metadata?.streaming === true
  const canSubmit = isBot && !readonly && enabled && !isStreaming && feedback.stepId !== null && Boolean(onSubmit)
  const canRead = isBot && readonly && feedback.rating !== null
  const alignment = align === 'end' ? 'items-end text-right' : 'items-start text-left'
  const rowAlignment = align === 'end' ? 'justify-end' : 'justify-start'
  const timeText = formatFeedbackTime(feedback.updatedAt, locale)

  if (!canSubmit && !canRead) return null

  const submit = async (rating: OpenAgentFeedbackRating, nextComment?: string | null) => {
    if (!feedback.stepId || !onSubmit) return
    setPendingRating(rating)
    setError('')
    try {
      await onSubmit({
        messageId,
        stepId: feedback.stepId,
        rating,
        comment: rating === 'dislike' ? nextComment ?? null : null,
      })
      setCommentOpen(false)
      setSubmitted(true)
      window.setTimeout(() => setSubmitted(false), 1600)
    } catch {
      setError(locale === 'zh' ? '提交失败，请重试' : 'Failed to submit')
    } finally {
      setPendingRating(null)
    }
  }

  if (readonly) {
    return (
      <div className={cn('mt-1 flex max-w-full flex-col gap-1 text-[11px] text-[#71717A]', alignment)}>
        <div className={cn('flex flex-wrap items-center gap-1.5', rowAlignment)}>
          {feedback.rating === 'like' ? <IconThumbUp size={13} aria-hidden /> : <IconThumbDown size={13} aria-hidden />}
          <span>{feedbackText(feedback.rating, locale)}</span>
          {timeText && <span className="text-[#A1A1AA]">{timeText}</span>}
        </div>
        {feedback.rating === 'dislike' && feedback.comment && (
          <div className="max-w-full rounded-md bg-[#F4F4F5] px-2 py-1 text-[#52525B]">
            {feedback.comment}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className={cn('mt-1 flex flex-col gap-1 text-[11px] text-muted-foreground', alignment)}>
      <div className={cn('flex items-center gap-1', rowAlignment)}>
        <button
          type="button"
          className={cn(
            'inline-flex h-6 w-6 items-center justify-center rounded-md transition-colors hover:bg-black/5 disabled:pointer-events-none disabled:opacity-60',
            feedback.rating === 'like' && 'bg-[#EAF7EE] text-[#16803C]',
          )}
          onClick={() => void submit('like')}
          disabled={pendingRating !== null}
          title={locale === 'zh' ? '点赞' : 'Like'}
          aria-label={locale === 'zh' ? '点赞' : 'Like'}
          aria-pressed={feedback.rating === 'like'}
        >
          {pendingRating === 'like' ? <IconLoader2 size={14} className="animate-spin" /> : <IconThumbUp size={14} />}
        </button>
        <button
          type="button"
          className={cn(
            'inline-flex h-6 w-6 items-center justify-center rounded-md transition-colors hover:bg-black/5 disabled:pointer-events-none disabled:opacity-60',
            feedback.rating === 'dislike' && 'bg-[#FFF1F2] text-[#C2410C]',
          )}
          onClick={() => {
            setComment(feedback.comment ?? '')
            setCommentOpen(true)
            setError('')
          }}
          disabled={pendingRating !== null}
          title={locale === 'zh' ? '点踩' : 'Dislike'}
          aria-label={locale === 'zh' ? '点踩' : 'Dislike'}
          aria-pressed={feedback.rating === 'dislike'}
        >
          {pendingRating === 'dislike' ? <IconLoader2 size={14} className="animate-spin" /> : <IconThumbDown size={14} />}
        </button>
        {submitted && (
          <span className="text-[#16803C]">{locale === 'zh' ? '已提交' : 'Submitted'}</span>
        )}
      </div>
      {error && <span className="text-destructive">{error}</span>}
      {commentOpen && (
        <div className="fixed inset-0 z-[2147483647] flex items-end justify-center bg-black/30 p-3 sm:items-center">
          <div className="w-full max-w-sm rounded-lg bg-white p-4 shadow-xl">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-sm font-medium text-[#18181B]">
                {locale === 'zh' ? '点踩原因' : 'Dislike reason'}
              </div>
              <button
                type="button"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-[#71717A] hover:bg-[#F4F4F5]"
                onClick={() => setCommentOpen(false)}
                aria-label={locale === 'zh' ? '关闭' : 'Close'}
              >
                <IconX size={16} />
              </button>
            </div>
            <textarea
              value={comment}
              maxLength={500}
              onChange={(event) => setComment(event.target.value)}
              className="min-h-24 w-full resize-none rounded-md border border-[#E4E4E7] px-3 py-2 text-sm text-[#18181B] outline-none focus:border-[#4A8C5C]"
              placeholder={locale === 'zh' ? '可选，告诉我们哪里没有解决问题' : 'Optional, tell us what was not helpful'}
            />
            <div className="mt-2 flex items-center justify-between gap-3 text-xs text-[#A1A1AA]">
              <span>{comment.length}/500</span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="rounded-md px-3 py-1.5 text-[#71717A] hover:bg-[#F4F4F5]"
                  onClick={() => setCommentOpen(false)}
                >
                  {locale === 'zh' ? '取消' : 'Cancel'}
                </button>
                <button
                  type="button"
                  className="rounded-md bg-[#4A8C5C] px-3 py-1.5 text-white hover:bg-[#3D754C] disabled:opacity-60"
                  disabled={pendingRating !== null}
                  onClick={() => void submit('dislike', comment.trim() || null)}
                >
                  {pendingRating === 'dislike'
                    ? (locale === 'zh' ? '提交中' : 'Submitting')
                    : (locale === 'zh' ? '提交' : 'Submit')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export function OpenAgentFeedbackStatus(
  props: Omit<OpenAgentFeedbackProps, 'readonly' | 'enabled' | 'onSubmit'>,
) {
  return <OpenAgentFeedback {...props} readonly />
}
