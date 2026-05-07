'use client'

import { useCallback, useMemo, useState } from 'react'

import { cn } from '@/lib/utils'
import { FieldType } from '@/types/field-enums'
import { FieldValueDisplay } from '@/app/components/features/field-system/field-value-display'
import { RichTextFieldEditor } from '@/app/components/features/field-system/rich-text-field-editor'
import {
  useCreateTicketComment,
  useTicketComments,
} from '@/service/use-ticket-comments'
import type { TicketChange } from '@/models/ticket'
import type {
  TicketComment,
  TicketCommentAttachment,
} from '@/models/ticket-comment'
import type { UnifiedField } from '@/models/field-definition'

import { ActivityActorAvatar } from './activity-actor-avatar'
import { ActivityTimeline, ActivityTimelineRow } from './activity-timeline-row'
import { TicketCommentAttachmentPicker } from './ticket-comment-attachment-picker'

const COMMENT_MAX_LENGTH = 50000
const ATTACHMENT_MAX_COUNT = 10

type TimelineItem =
  | { kind: 'comment'; at: string; data: TicketComment }
  | { kind: 'change'; at: string; data: TicketChange }

type Props = {
  ticketId: number
  isZh: boolean
  /** Empty hint when both lists are empty in the current view. */
  emptyText: string
  /** When true, comments are interleaved with changes by `created_at desc`. */
  mergeWithChanges?: boolean
  changes?: TicketChange[]
  changesLoading?: boolean
  changesError?: boolean
  /** Field-def lookup so change rows can format select values. */
  resolveFieldDef?: (fieldKey: string) => UnifiedField | undefined
  /** Optional renderer for change rows so the page-level component owns formatting. */
  renderChange?: (change: TicketChange) => React.ReactNode
  /** Whether to show the comment composer below the timeline. */
  showComposer?: boolean
  className?: string
}

/**
 * Right-rail comment thread for the ticket detail page.
 *
 * Owns its own state for the composer (rich-text body + attachments). The
 * caller must pass `changes` only when `mergeWithChanges` is true — the
 * underlying "all" tab interleaves both timelines client-side.
 */
export function TicketCommentThread({
  ticketId,
  isZh,
  emptyText,
  mergeWithChanges = false,
  changes,
  changesLoading,
  changesError,
  renderChange,
  showComposer = true,
  className,
}: Props) {
  const [body, setBody] = useState<string>('')
  /** Bumps after successful send so the TipTap editor remounts when `body` was already "". */
  const [composerKey, setComposerKey] = useState(0)
  const [attachments, setAttachments] = useState<TicketCommentAttachment[]>([])
  const [submitToast, setSubmitToast] = useState<'success' | 'error' | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const listParams = useMemo(() => ({ page: 1, per_page: 50 }), [])
  const {
    data: commentsData,
    isLoading: commentsLoading,
    isError: commentsError,
  } = useTicketComments(ticketId, listParams)

  const createMutation = useCreateTicketComment(ticketId)

  const trimmedBody = body.trim()
  const hasBody = trimmedBody.length > 0
  const hasAttachments = attachments.length > 0
  const canSubmit =
    !createMutation.isPending && (hasBody || hasAttachments) &&
    trimmedBody.length <= COMMENT_MAX_LENGTH

  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return
    setSubmitError(null)
    if (trimmedBody.length > COMMENT_MAX_LENGTH) {
      setSubmitError(
        isZh
          ? `评论正文过长（最多 ${COMMENT_MAX_LENGTH} 字符）`
          : `Comment is too long (max ${COMMENT_MAX_LENGTH} chars)`,
      )
      return
    }
    if (attachments.length > ATTACHMENT_MAX_COUNT) {
      setSubmitError(
        isZh
          ? `最多只能上传 ${ATTACHMENT_MAX_COUNT} 个附件`
          : `Up to ${ATTACHMENT_MAX_COUNT} attachments allowed`,
      )
      return
    }
    try {
      await createMutation.mutateAsync({
        body: hasBody ? body : null,
        body_format: 'html',
        attachments: hasAttachments ? attachments : null,
      })
      setBody('')
      setAttachments([])
      setComposerKey((k) => k + 1)
      setSubmitToast('success')
      window.setTimeout(() => setSubmitToast(null), 2500)
    } catch {
      setSubmitToast('error')
      window.setTimeout(() => setSubmitToast(null), 2500)
    }
  }, [
    attachments,
    body,
    canSubmit,
    createMutation,
    hasAttachments,
    hasBody,
    isZh,
    trimmedBody,
  ])

  const comments = commentsData?.items ?? []

  const timeline: TimelineItem[] = useMemo(() => {
    const items: TimelineItem[] = comments.map((c) => ({
      kind: 'comment',
      at: c.created_at,
      data: c,
    }))
    if (mergeWithChanges && changes) {
      for (const ch of changes) {
        items.push({ kind: 'change', at: ch.created_at, data: ch })
      }
    }
    items.sort((a, b) => {
      if (a.at === b.at) {
        if (a.kind !== b.kind) return a.kind === 'comment' ? -1 : 1
        return b.data.id - a.data.id
      }
      return a.at < b.at ? 1 : -1
    })
    return items
  }, [comments, mergeWithChanges, changes])

  const showLoading =
    commentsLoading || (mergeWithChanges && changesLoading && timeline.length === 0)

  return (
    <div className={cn('flex h-full flex-col', className)}>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {showLoading ? (
          <CenteredHint
            text={isZh ? '加载评论中...' : 'Loading comments...'}
          />
        ) : commentsError ? (
          <CenteredHint
            tone="destructive"
            text={isZh ? '评论加载失败' : 'Failed to load comments'}
          />
        ) : mergeWithChanges && changesError && timeline.length === 0 ? (
          <CenteredHint
            tone="destructive"
            text={isZh ? '动态记录加载失败' : 'Failed to load activity'}
          />
        ) : timeline.length === 0 ? (
          <CenteredHint text={emptyText} />
        ) : (
          <ActivityTimeline>
            {timeline.map((item) =>
              item.kind === 'comment' ? (
                <ActivityTimelineRow key={`c-${item.data.id}`}>
                  <CommentCard
                    comment={item.data}
                    isZh={isZh}
                    showKindBadge={mergeWithChanges}
                  />
                </ActivityTimelineRow>
              ) : (
                <ActivityTimelineRow key={`ch-${item.data.id}`}>
                  {renderChange ? renderChange(item.data) : null}
                </ActivityTimelineRow>
              ),
            )}
          </ActivityTimeline>
        )}
      </div>

      {showComposer && (
        <div className="shrink-0 px-5 pb-4 pt-1.5">
          <div className="flex flex-col gap-2 overflow-hidden rounded-2xl border border-border bg-white p-2.5">
            <RichTextFieldEditor
              key={composerKey}
              value={body}
              onChange={(v) => setBody(v ?? '')}
              placeholder={isZh ? '输入评论…' : 'Write a comment…'}
              typeConfig={{ rich_format: 'html' }}
              disabled={createMutation.isPending}
              plainChrome
              className="bg-white shadow-none focus-within:ring-0 [&_.ProseMirror]:min-h-[72px] [&_.ProseMirror]:rounded-xl [&_.ProseMirror]:bg-white"
            />
            <div className="flex flex-wrap items-end justify-between gap-2">
              <TicketCommentAttachmentPicker
                value={attachments}
                onChange={setAttachments}
                disabled={createMutation.isPending}
                isZh={isZh}
                maxCount={ATTACHMENT_MAX_COUNT}
              />
              <div className="ml-auto flex items-center gap-2">
                {submitToast === 'success' && (
                  <span className="text-xs text-green-600">
                    {isZh ? '发送成功' : 'Comment sent'}
                  </span>
                )}
                {submitToast === 'error' && (
                  <span className="text-xs text-destructive">
                    {isZh ? '发送失败，请重试' : 'Failed to send. Please try again'}
                  </span>
                )}
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={!canSubmit}
                  className="flex h-8 shrink-0 items-center justify-center rounded-full bg-primary px-3 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
                >
                  {createMutation.isPending
                    ? (isZh ? '发送中...' : 'Sending...')
                    : (isZh ? '发送' : 'Send')}
                </button>
              </div>
            </div>
            {submitError && (
              <p className="text-[11px] text-destructive">{submitError}</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function CenteredHint({
  text,
  tone = 'muted',
}: {
  text: string
  tone?: 'muted' | 'destructive'
}) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center">
      <p
        className={cn(
          'text-xs',
          tone === 'destructive' ? 'text-destructive' : 'text-muted-foreground',
        )}
      >
        {text}
      </p>
    </div>
  )
}

function CommentCard({
  comment,
  isZh,
  showKindBadge = false,
}: {
  comment: TicketComment
  isZh: boolean
  /** When true (e.g. "All" activity tab), show a pill after the name. */
  showKindBadge?: boolean
}) {
  const author = comment.author_name ?? (isZh ? '系统' : 'System')
  const hasBody = !!comment.body && comment.body.trim() !== ''
  const attachments = comment.attachments ?? []

  return (
    <div className="rounded-lg bg-white px-4 py-3.5">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          <ActivityActorAvatar name={author} src={comment.author_avatar} />
          <span className="min-w-0 truncate text-[13px] text-foreground">
            {author}
          </span>
          {showKindBadge && (
            <span className="shrink-0 rounded-md border border-border bg-muted/50 px-1.5 py-px text-[10px] leading-tight text-muted-foreground">
              {isZh ? '评论' : 'Comment'}
            </span>
          )}
        </div>
        <time
          className="shrink-0 text-xs text-muted-foreground"
          dateTime={comment.created_at}
        >
          {formatCommentTime(comment.created_at, isZh)}
        </time>
      </div>
      {hasBody && (
        <FieldValueDisplay
          fieldType={FieldType.RICH_TEXT}
          value={comment.body}
          typeConfig={{ rich_format: comment.body_format }}
          className="text-sm text-foreground prose-p:my-2 prose-p:leading-relaxed"
        />
      )}
      {attachments.length > 0 && (
        <ul className={cn('flex flex-col gap-2', hasBody && 'mt-3')}>
          {attachments.map((file, i) => (
            <li
              key={`${file.url}-${i}`}
              className="flex items-center rounded-md border border-border bg-muted/30 px-2.5 py-1.5 text-xs"
            >
              <a
                href={file.url}
                target="_blank"
                rel="noopener noreferrer"
                className="min-w-0 flex-1 truncate text-primary underline-offset-2 hover:underline"
                title={file.name}
              >
                {file.name || (isZh ? `文件 ${i + 1}` : `File ${i + 1}`)}
              </a>
              {typeof file.size === 'number' && file.size > 0 && (
                <span className="ml-2 shrink-0 text-[11px] text-muted-foreground">
                  {formatBytes(file.size)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function formatCommentTime(value: string, isZh: boolean): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(isZh ? 'zh-CN' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}
