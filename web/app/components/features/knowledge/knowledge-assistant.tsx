'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  IconArrowLeft,
  IconBook2,
  IconChevronLeft,
  IconChevronRight,
  IconCopy,
  IconLoader2,
  IconSearch,
  IconSend,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { SafeHtml } from '@/components/safe-html'
import { useLocaleStore } from '@/context/locale-store'
import type { KnowledgeDocument } from '@/models/knowledge'
import { useKnowledgeDirectories, useKnowledgeDocument, useKnowledgeDocuments } from '@/service/use-knowledge'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import {
  flattenKnowledgeDirectories,
  knowledgeDirectoryPath,
  knowledgeHasUnsupportedSendContent,
  knowledgeHtmlToMessageText,
} from './knowledge-utils'

const PER_PAGE = 20
const SEND_MAX_LENGTH = 4000

export type KnowledgeAssistantActionContext = {
  document: KnowledgeDocument
  messageText: string
}

type KnowledgeAssistantProps = {
  className?: string
  mode?: 'chat' | 'drawer'
  canUse?: boolean
  useDisabledReason?: string
  canSend?: boolean
  sendDisabledReason?: string
  showCopy?: boolean
  onUse?: (context: KnowledgeAssistantActionContext) => void | Promise<void>
  onSend?: (context: KnowledgeAssistantActionContext) => void | Promise<void>
}

function useDebouncedValue(value: string): string {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [value])

  return debounced
}

function messageTextFor(document: KnowledgeDocument): string {
  return knowledgeHtmlToMessageText(document.content_html)
}

function actionBlockReason(document: KnowledgeDocument, action: 'use' | 'send'): string | null {
  const messageText = messageTextFor(document)
  if (!messageText) return 'empty'
  if (action === 'send' && messageText.length > SEND_MAX_LENGTH) return 'too-long'
  if (action === 'send' && knowledgeHasUnsupportedSendContent(document.content_html)) return 'unsupported'
  return null
}

export function KnowledgeAssistant({
  className,
  mode = 'chat',
  canUse = false,
  useDisabledReason,
  canSend = false,
  sendDisabledReason,
  showCopy = false,
  onUse,
  onSend,
}: KnowledgeAssistantProps) {
  const { locale } = useLocaleStore()
  const [search, setSearch] = useState('')
  const [directoryId, setDirectoryId] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [confirmDoc, setConfirmDoc] = useState<KnowledgeDocument | null>(null)
  const [sending, setSending] = useState(false)
  const query = useDebouncedValue(search)

  const directoriesQuery = useKnowledgeDirectories()
  const directories = directoriesQuery.data?.items ?? []
  const flatDirectories = useMemo(
    () => flattenKnowledgeDirectories(directories).filter((item) => item.depth <= 3),
    [directories],
  )

  const documentsQuery = useKnowledgeDocuments({
    directory: directoryId,
    q: query,
    display_status: 'published',
    page,
    per_page: PER_PAGE,
  })
  const selectedQuery = useKnowledgeDocument(selectedId)
  const documents = documentsQuery.data?.items ?? []
  const selectedDocument = selectedQuery.data ?? documents.find((item) => item.id === selectedId) ?? null

  useEffect(() => {
    setPage(1)
  }, [directoryId, query])

  const reasonText = (reason: string | null | undefined): string => {
    if (!reason) return ''
    if (reason === 'empty') return t('ws.knowledge.emptyContent', locale)
    if (reason === 'too-long') return t('ws.knowledge.contentTooLong', locale)
    if (reason === 'unsupported') return t('ws.knowledge.unsupportedContent', locale)
    return reason
  }

  const handleCopy = async (document: KnowledgeDocument) => {
    const messageText = messageTextFor(document)
    if (!messageText) {
      toast.error(t('ws.knowledge.emptyContent', locale))
      return
    }
    await navigator.clipboard.writeText(messageText)
    toast.success(t('ws.knowledge.copied', locale))
  }

  const handleUse = async (document: KnowledgeDocument) => {
    const block = actionBlockReason(document, 'use')
    if (block || !canUse || !onUse) {
      toast.error(reasonText(block) || useDisabledReason || t('ws.knowledge.selectConversation', locale))
      return
    }
    await onUse({ document, messageText: messageTextFor(document) })
  }

  const handleConfirmSend = async () => {
    if (!confirmDoc || !onSend) return
    const block = actionBlockReason(confirmDoc, 'send')
    if (block || !canSend) {
      toast.error(reasonText(block) || sendDisabledReason || t('ws.knowledge.selectConversation', locale))
      return
    }
    setSending(true)
    try {
      await onSend({ document: confirmDoc, messageText: messageTextFor(confirmDoc) })
      toast.success(t('ws.knowledge.sent', locale))
      setConfirmDoc(null)
    } catch {
      toast.error(t('ws.knowledge.sendFailed', locale))
    } finally {
      setSending(false)
    }
  }

  const renderActions = (document: KnowledgeDocument, compact = false) => {
    const useReason = reasonText(actionBlockReason(document, 'use')) || (!canUse ? useDisabledReason : '')
    const sendReason = reasonText(actionBlockReason(document, 'send')) || (!canSend ? sendDisabledReason : '')
    const buttonSize = compact ? 'xs' : 'sm'

    return (
      <div className="flex items-center justify-end gap-1.5">
        {showCopy && (
          <Button type="button" variant="outline" size={buttonSize} onClick={() => void handleCopy(document)}>
            <IconCopy size={14} />
            {t('ws.knowledge.copy', locale)}
          </Button>
        )}
        {onUse && (
          <Button
            type="button"
            variant="outline"
            size={buttonSize}
            disabled={Boolean(useReason)}
            title={useReason}
            onClick={() => void handleUse(document)}
          >
            {t('ws.knowledge.use', locale)}
          </Button>
        )}
        {onSend && (
          <Button
            type="button"
            size={buttonSize}
            disabled={Boolean(sendReason)}
            title={sendReason}
            onClick={() => setConfirmDoc(document)}
          >
            <IconSend size={14} />
            {t('ws.knowledge.send', locale)}
          </Button>
        )}
      </div>
    )
  }

  const renderList = () => {
    if (documentsQuery.isLoading || directoriesQuery.isLoading) {
      return (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-28 animate-pulse rounded-lg border border-border bg-muted" />
          ))}
        </div>
      )
    }

    if (documentsQuery.isError || directoriesQuery.isError) {
      return (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 py-12 text-center">
          <IconBook2 size={28} className="text-muted-foreground" />
          <p className="text-sm text-muted-foreground">{t('ws.knowledge.loadFailed', locale)}</p>
          <Button type="button" variant="outline" size="sm" onClick={() => void documentsQuery.refetch()}>
            {t('ws.knowledge.retry', locale)}
          </Button>
        </div>
      )
    }

    if (documents.length === 0) {
      return (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 py-12 text-center">
          <IconBook2 size={28} className="text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {query ? t('ws.knowledge.noResults', locale) : t('ws.knowledge.empty', locale)}
          </p>
        </div>
      )
    }

    return (
      <div className="flex flex-col gap-2">
        {documents.map((document) => (
          <article key={document.id} className="rounded-lg border border-border bg-background p-3">
            <button
              type="button"
              onClick={() => setSelectedId(document.id)}
              className="block w-full text-left"
            >
              <h3 className="line-clamp-2 text-sm font-semibold text-foreground">{document.title}</h3>
              <p className="mt-1 truncate text-xs text-muted-foreground">{knowledgeDirectoryPath(document) || '-'}</p>
              <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">{messageTextFor(document)}</p>
            </button>
            <div className="mt-3">{renderActions(document, true)}</div>
          </article>
        ))}
      </div>
    )
  }

  const confirmText = confirmDoc ? messageTextFor(confirmDoc) : ''
  const confirmBlock = confirmDoc ? actionBlockReason(confirmDoc, 'send') : null
  const confirmDisabledReason = reasonText(confirmBlock) || (!canSend ? sendDisabledReason : '')

  return (
    <section className={cn('flex min-h-0 flex-1 flex-col bg-background', className)}>
      {!selectedDocument ? (
        <>
          <div className={cn('shrink-0 border-b border-border p-3', mode === 'drawer' && 'p-4')}>
            <div className="relative">
              <IconSearch size={16} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t('ws.knowledge.search', locale)}
                className="h-9 pl-8"
              />
            </div>
            <select
              value={directoryId ?? ''}
              onChange={(event) => setDirectoryId(event.target.value ? Number(event.target.value) : null)}
              className="mt-2 h-9 w-full rounded-lg border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <option value="">{t('ws.knowledge.allArticles', locale)}</option>
              {flatDirectories.map(({ node, depth, path }) => (
                <option key={node.id} value={node.id}>
                  {`${'  '.repeat(Math.max(0, depth - 1))}${path}`}
                </option>
              ))}
            </select>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-3">{renderList()}</div>

          {documentsQuery.data && documentsQuery.data.total > 0 && (
            <div className="flex shrink-0 items-center justify-between border-t border-border px-3 py-2 text-xs text-muted-foreground">
              <span>{t('ws.knowledge.total', locale, { total: documentsQuery.data.total })}</span>
              {documentsQuery.data.pages > 1 && (
                <div className="flex items-center gap-2">
                  <span>{documentsQuery.data.page} / {documentsQuery.data.pages}</span>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon-xs"
                    disabled={documentsQuery.data.page <= 1}
                    onClick={() => setPage((value) => Math.max(1, value - 1))}
                    title="Previous"
                  >
                    <IconChevronLeft size={14} />
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon-xs"
                    disabled={documentsQuery.data.page >= documentsQuery.data.pages}
                    onClick={() => setPage((value) => value + 1)}
                    title="Next"
                  >
                    <IconChevronRight size={14} />
                  </Button>
                </div>
              )}
            </div>
          )}
        </>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="shrink-0 border-b border-border p-3">
            <button
              type="button"
              className="mb-3 flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
              onClick={() => setSelectedId(null)}
            >
              <IconArrowLeft size={14} />
              {t('ws.knowledge.back', locale)}
            </button>
            <h3 className="text-base font-semibold text-foreground">{selectedDocument.title}</h3>
            <p className="mt-1 text-xs text-muted-foreground">{knowledgeDirectoryPath(selectedDocument) || '-'}</p>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {selectedQuery.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <IconLoader2 size={16} className="animate-spin" />
                {t('ws.knowledge.loading', locale)}
              </div>
            ) : (
              <>
                {knowledgeHasUnsupportedSendContent(selectedDocument.content_html) && (
                  <div className="mb-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-foreground">
                    {t('ws.knowledge.unsupportedContent', locale)}
                  </div>
                )}
                <SafeHtml
                  html={selectedDocument.content_html}
                  className="text-sm leading-6 text-foreground [&_a]:text-primary [&_blockquote]:border-l [&_blockquote]:border-border [&_blockquote]:pl-3 [&_li]:ml-5 [&_ol]:list-decimal [&_p]:mb-3 [&_ul]:list-disc"
                />
              </>
            )}
          </div>
          <div className="shrink-0 border-t border-border bg-background p-3">{renderActions(selectedDocument)}</div>
        </div>
      )}

      <Dialog open={confirmDoc != null} onOpenChange={(open) => !open && setConfirmDoc(null)}>
        <DialogContent
          className="w-[500px] max-w-[calc(100vw-2rem)] gap-0 overflow-hidden rounded-2xl border border-[#E5E5E5] bg-white p-0 shadow-lg ring-0"
          showCloseButton={!sending}
        >
          {confirmDoc && (
            <>
              <DialogHeader className="px-5 pt-5">
                <DialogTitle>{t('ws.knowledge.confirmTitle', locale)}</DialogTitle>
              </DialogHeader>
              <div className="px-5 pb-2">
                <pre className="max-h-56 whitespace-pre-wrap rounded-lg border border-border bg-background p-3 text-xs leading-5 text-foreground">
                  {confirmText}
                </pre>
                {confirmDisabledReason && (
                  <p className="mt-2 text-xs text-destructive">{confirmDisabledReason}</p>
                )}
              </div>
              <DialogFooter className="rounded-b-2xl border-t border-[#E5E5E5] px-5">
                <Button type="button" variant="outline" onClick={() => setConfirmDoc(null)} disabled={sending}>
                  {t('ws.common.cancel', locale)}
                </Button>
                <Button
                  type="button"
                  onClick={() => void handleConfirmSend()}
                  disabled={sending || Boolean(confirmDisabledReason)}
                >
                  {sending && <IconLoader2 size={14} className="animate-spin" />}
                  {t('ws.knowledge.confirmSend', locale)}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </section>
  )
}
