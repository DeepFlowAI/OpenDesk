'use client'

import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { cn } from '@/lib/utils'
import type { EmbeddedPage, EmbeddedPageLocation } from '@/models/embedded-page'
import { useDeleteEmbeddedPage, useEmbeddedPages } from '@/service/use-embedded-pages'

type EmbeddedPagesSectionProps = {
  location: EmbeddedPageLocation
  basePath: string
}

function Tag({ children, tone }: { children: string; tone: 'blue' | 'violet' | 'green' | 'muted' }) {
  const styles = {
    blue: 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
    violet: 'bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300',
    green: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
    muted: 'bg-muted text-muted-foreground',
  }
  return (
    <span className={cn('inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium', styles[tone])}>
      {children}
    </span>
  )
}

export function EmbeddedPagesSection({ location, basePath }: EmbeddedPagesSectionProps) {
  const { locale } = useLocaleStore()
  const router = useRouter()
  const { data, isLoading, isError } = useEmbeddedPages(location)
  const deleteMutation = useDeleteEmbeddedPage()
  const [deleteTarget, setDeleteTarget] = useState<EmbeddedPage | null>(null)

  const text = useMemo(
    () =>
      location === 'call_screen_pop'
        ? {
            title: t('ep.call.title', locale),
            description: t('ep.call.description', locale),
            emptyHint: t('ep.call.emptyHint', locale),
            deleteMessage: t('ep.call.deleteMessage', locale),
          }
        : {
            title: t('ep.title', locale),
            description: t('ep.description', locale),
            emptyHint: t('ep.emptyHint', locale),
            deleteMessage: t('ep.delete.message', locale),
          },
    [location, locale],
  )

  const pages = useMemo(() => data?.items ?? [], [data])

  const formatTime = (iso: string | null) => {
    if (!iso) return '-'
    const date = new Date(iso)
    return new Intl.DateTimeFormat(locale, {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date)
  }

  const handleDelete = () => {
    if (!deleteTarget) return
    deleteMutation.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.success(t('ep.delete.success', locale))
        setDeleteTarget(null)
      },
      onError: () => toast.error(t('ep.delete.failed', locale)),
    })
  }

  return (
    <section className="flex flex-col gap-4 border-t border-border pt-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{text.title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{text.description}</p>
        </div>
        <Button onClick={() => router.push(`${basePath}/new`)}>
          <Plus className="h-4 w-4" />
          {t('ep.new', locale)}
        </Button>
      </div>

      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('ep.col.name', locale)}</TableHead>
              <TableHead className="w-[110px]">{t('ep.col.type', locale)}</TableHead>
              <TableHead className="w-[90px]">{t('ep.col.enabled', locale)}</TableHead>
              <TableHead className="w-[100px]">{t('ep.col.defaultFocus', locale)}</TableHead>
              <TableHead className="w-[80px]">{t('ep.col.sortOrder', locale)}</TableHead>
              <TableHead className="w-[140px]">{t('ep.col.updatedAt', locale)}</TableHead>
              <TableHead className="w-[110px] text-right">{t('ep.col.actions', locale)}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={7} className="py-12 text-center text-sm text-muted-foreground">
                  {t('ep.loading', locale)}
                </TableCell>
              </TableRow>
            ) : isError ? (
              <TableRow>
                <TableCell colSpan={7} className="py-12 text-center text-sm text-muted-foreground">
                  {t('ep.loadFailed', locale)}
                </TableCell>
              </TableRow>
            ) : pages.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-12 text-center">
                  <p className="text-sm font-medium">{t('ep.empty', locale)}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{text.emptyHint}</p>
                </TableCell>
              </TableRow>
            ) : (
              pages.map((page) => (
                <TableRow
                  key={page.id}
                  className="cursor-pointer"
                  onClick={() => router.push(`${basePath}/${page.id}`)}
                >
                  <TableCell className="font-medium">{page.name}</TableCell>
                  <TableCell>
                    {page.page_type === 'iframe' ? (
                      <Tag tone="blue">{t('ep.type.iframe', locale)}</Tag>
                    ) : (
                      <Tag tone="violet">{t('ep.type.react_code', locale)}</Tag>
                    )}
                  </TableCell>
                  <TableCell>
                    {page.enabled ? (
                      <Tag tone="green">{t('ep.enabled.on', locale)}</Tag>
                    ) : (
                      <Tag tone="muted">{t('ep.enabled.off', locale)}</Tag>
                    )}
                  </TableCell>
                  <TableCell>
                    <Switch checked={page.default_focus} disabled aria-label={t('ep.col.defaultFocus', locale)} />
                  </TableCell>
                  <TableCell>{page.sort_order}</TableCell>
                  <TableCell className="text-muted-foreground">{formatTime(page.updated_at)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t('ep.edit', locale)}
                        onClick={(event) => {
                          event.stopPropagation()
                          router.push(`${basePath}/${page.id}`)
                        }}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t('ep.delete', locale)}
                        onClick={(event) => {
                          event.stopPropagation()
                          setDeleteTarget(page)
                        }}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title={t('ep.delete.title', locale)}
        message={text.deleteMessage}
        itemName={deleteTarget?.name}
        confirmLabel={t('ep.delete.confirm', locale)}
        cancelLabel={t('ep.delete.cancel', locale)}
        variant="destructive"
        loading={deleteMutation.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </section>
  )
}
