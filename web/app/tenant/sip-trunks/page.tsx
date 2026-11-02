'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { IconDownload, IconPencil, IconPlus, IconSearch, IconTrash } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { consoleDownload, readConsoleError } from '@/service/tenant-console-client'
import { compactParams, useDeleteSipTrunk, useSipTrunks } from '@/service/use-tenant-console'
import type { SipTrunk, TrunkStatus } from '@/models/tenant-console'
import {
  ConsolePagination,
  EmptyState,
  FIELD_CLASS,
  LoadingState,
  PageHeader,
  StatusPill,
  TABLE_CELL_CLASS,
  TABLE_HEAD_CLASS,
  formatDateTime,
} from '@/app/tenant/_components/console-ui'

export default function SipTrunkListPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const [keyword, setKeyword] = useState('')
  const [filters, setFilters] = useState<{ q: string; status: TrunkStatus | '' }>({ q: '', status: '' })
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const { data, isLoading } = useSipTrunks({ ...filters, page, per_page: perPage })
  const deleteMutation = useDeleteSipTrunk()
  const [deleteTarget, setDeleteTarget] = useState<SipTrunk | null>(null)
  const [exporting, setExporting] = useState(false)

  const applySearch = () => {
    setFilters((prev) => ({ ...prev, q: keyword.trim() }))
    setPage(1)
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const params = compactParams(filters) as Record<string, string>
      await consoleDownload('v1/sip-trunks/export', params, 'sip-trunks.csv')
    } catch (err) {
      toast.error(await readConsoleError(err, t('tc.common.exportFailed', locale)))
    } finally {
      setExporting(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      toast.success(t('tc.common.deleted', locale))
      setDeleteTarget(null)
    } catch (err) {
      toast.error(await readConsoleError(err, t('tc.common.deleteFailed', locale)))
    }
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title={t('tc.trunk.title', locale)}
        actions={
          <>
            <Button variant="outline" size="lg" disabled={exporting} onClick={handleExport}>
              <IconDownload size={16} />
              {t('tc.common.export', locale)}
            </Button>
            <Button size="lg" onClick={() => router.push('/tenant/sip-trunks/new')}>
              <IconPlus size={16} />
              {t('tc.trunk.create', locale)}
            </Button>
          </>
        }
      />
      <div className="flex items-center gap-3 px-8 pb-4">
        <div className="relative w-72">
          <IconSearch size={16} className="absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground" />
          <input
            value={keyword}
            placeholder={t('tc.trunk.searchPlaceholder', locale)}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && applySearch()}
            className={`${FIELD_CLASS} pl-9`}
          />
        </div>
        <select
          aria-label={t('tc.common.status', locale)}
          value={filters.status}
          onChange={(e) => {
            setFilters((prev) => ({ ...prev, status: e.target.value as TrunkStatus | '' }))
            setPage(1)
          }}
          className={`${FIELD_CLASS} w-36`}
        >
          <option value="">{t('tc.common.allStatus', locale)}</option>
          <option value="enabled">{t('tc.status.enabled', locale)}</option>
          <option value="disabled">{t('tc.status.disabled', locale)}</option>
        </select>
        <Button variant="outline" size="lg" onClick={applySearch}>
          {t('tc.common.search', locale)}
        </Button>
      </div>
      <div className="flex-1 overflow-auto px-8 pb-6">
        {isLoading ? (
          <LoadingState />
        ) : !data?.items.length ? (
          <EmptyState title={t('tc.trunk.empty', locale)} />
        ) : (
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full">
              <thead className="border-b border-border bg-muted/40">
                <tr>
                  <th className={TABLE_HEAD_CLASS}>{t('tc.trunk.col.supplier', locale)}</th>
                  <th className={TABLE_HEAD_CLASS}>{t('tc.trunk.col.name', locale)}</th>
                  <th className={TABLE_HEAD_CLASS}>{t('tc.trunk.col.types', locale)}</th>
                  <th className={TABLE_HEAD_CLASS}>{t('tc.trunk.col.endpoints', locale)}</th>
                  <th className={TABLE_HEAD_CLASS}>{t('tc.common.status', locale)}</th>
                  <th className={TABLE_HEAD_CLASS}>{t('tc.common.updatedAt', locale)}</th>
                  <th className={`${TABLE_HEAD_CLASS} w-24`}>{t('tc.common.actions', locale)}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((trunk) => (
                  <tr key={trunk.id} className="border-b border-border last:border-0 hover:bg-muted/30">
                    <td className={TABLE_CELL_CLASS}>{trunk.supplier_name}</td>
                    <td className={`${TABLE_CELL_CLASS} font-medium`}>{trunk.trunk_name}</td>
                    <td className={TABLE_CELL_CLASS}>
                      {trunk.trunk_types.map((type) => t(`tc.callType.${type}`, locale)).join(' / ')}
                    </td>
                    <td className={`${TABLE_CELL_CLASS} font-mono text-xs`}>
                      {trunk.peer_endpoints.map((ep) => `${ep.ip}:${ep.port}`).join(', ')}
                    </td>
                    <td className={TABLE_CELL_CLASS}>
                      <StatusPill tone={trunk.status === 'enabled' ? 'success' : 'muted'}>
                        {t(`tc.status.${trunk.status}`, locale)}
                      </StatusPill>
                    </td>
                    <td className={`${TABLE_CELL_CLASS} whitespace-nowrap text-muted-foreground`}>
                      {formatDateTime(trunk.updated_at)}
                    </td>
                    <td className={TABLE_CELL_CLASS}>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title={t('tc.common.edit', locale)}
                          aria-label={t('tc.common.edit', locale)}
                          onClick={() => router.push(`/tenant/sip-trunks/${encodeURIComponent(trunk.id)}`)}
                        >
                          <IconPencil size={16} />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title={t('tc.common.delete', locale)}
                          aria-label={t('tc.common.delete', locale)}
                          onClick={() => setDeleteTarget(trunk)}
                        >
                          <IconTrash size={16} />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {data && data.total > 0 && (
        <ConsolePagination
          page={data.page}
          pages={data.pages}
          total={data.total}
          perPage={perPage}
          onPageChange={setPage}
          onPerPageChange={(n) => {
            setPerPage(n)
            setPage(1)
          }}
        />
      )}
      <ConfirmDialog
        open={!!deleteTarget}
        title={t('tc.trunk.deleteTitle', locale)}
        message={t('tc.trunk.deleteMessage', locale)}
        itemName={deleteTarget?.trunk_name}
        itemDescription={deleteTarget?.supplier_name}
        confirmLabel={t('tc.common.delete', locale)}
        cancelLabel={t('tc.common.cancel', locale)}
        variant="destructive"
        loading={deleteMutation.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </div>
  )
}
