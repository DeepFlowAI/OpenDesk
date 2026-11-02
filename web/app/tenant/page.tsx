'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { IconPencil, IconPlayerPause, IconPlayerPlay, IconPlus } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { readConsoleError } from '@/service/tenant-console-client'
import { useConsoleTenants, useUpdateConsoleTenantStatus } from '@/service/use-tenant-console'
import type { ConsoleTenant } from '@/models/tenant-console'
import {
  ConsolePagination,
  EmptyState,
  LoadingState,
  PageHeader,
  StatusPill,
  TABLE_CELL_CLASS,
  TABLE_HEAD_CLASS,
  formatDateTime,
} from '@/app/tenant/_components/console-ui'

export default function TenantListPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const { data, isLoading } = useConsoleTenants({ page, per_page: perPage })
  const statusMutation = useUpdateConsoleTenantStatus()
  const [target, setTarget] = useState<ConsoleTenant | null>(null)

  const nextStatus = target?.status === 'enabled' ? 'disabled' : 'enabled'

  const handleToggle = async () => {
    if (!target) return
    try {
      await statusMutation.mutateAsync({ id: target.id, status: nextStatus })
      toast.success(
        t(nextStatus === 'enabled' ? 'tc.tenant.enabledToast' : 'tc.tenant.disabledToast', locale, {
          name: target.name,
        }),
      )
      setTarget(null)
    } catch (err) {
      toast.error(await readConsoleError(err, t('tc.common.actionFailed', locale)))
    }
  }

  const createButton = (
    <Button size="lg" onClick={() => router.push('/tenant/tenants/new')}>
      <IconPlus size={16} />
      {t('tc.tenant.create', locale)}
    </Button>
  )

  return (
    <div className="flex h-full flex-col">
      <PageHeader title={t('tc.tenant.title', locale)} actions={createButton} />
      <div className="flex-1 overflow-auto px-8 pb-6">
        {isLoading ? (
          <LoadingState />
        ) : !data?.items.length ? (
          <EmptyState title={t('tc.tenant.empty', locale)} action={createButton} />
        ) : (
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full">
              <thead className="border-b border-border bg-muted/40">
                <tr>
                  <th className={TABLE_HEAD_CLASS}>{t('tc.tenant.col.id', locale)}</th>
                  <th className={TABLE_HEAD_CLASS}>{t('tc.tenant.col.name', locale)}</th>
                  <th className={TABLE_HEAD_CLASS}>{t('tc.tenant.col.slug', locale)}</th>
                  <th className={TABLE_HEAD_CLASS}>{t('tc.tenant.col.admin', locale)}</th>
                  <th className={TABLE_HEAD_CLASS}>{t('tc.tenant.col.remark', locale)}</th>
                  <th className={TABLE_HEAD_CLASS}>{t('tc.common.status', locale)}</th>
                  <th className={TABLE_HEAD_CLASS}>{t('tc.common.createdAt', locale)}</th>
                  <th className={`${TABLE_HEAD_CLASS} w-24`}>{t('tc.common.actions', locale)}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((tenant) => (
                  <tr key={tenant.id} className="border-b border-border last:border-0 hover:bg-muted/30">
                    <td className={`${TABLE_CELL_CLASS} font-mono text-xs`}>{tenant.id}</td>
                    <td className={`${TABLE_CELL_CLASS} font-medium`}>{tenant.name}</td>
                    <td className={TABLE_CELL_CLASS}>{tenant.slug || '—'}</td>
                    <td className={TABLE_CELL_CLASS}>{tenant.admin_username || '—'}</td>
                    <td className={`${TABLE_CELL_CLASS} max-w-[240px] truncate text-muted-foreground`}>
                      {tenant.remark || '—'}
                    </td>
                    <td className={TABLE_CELL_CLASS}>
                      <StatusPill tone={tenant.status === 'enabled' ? 'success' : 'muted'}>
                        {t(tenant.status === 'enabled' ? 'tc.status.enabled' : 'tc.status.disabled', locale)}
                      </StatusPill>
                    </td>
                    <td className={`${TABLE_CELL_CLASS} whitespace-nowrap text-muted-foreground`}>
                      {formatDateTime(tenant.created_at)}
                    </td>
                    <td className={TABLE_CELL_CLASS}>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title={t('tc.common.edit', locale)}
                          aria-label={t('tc.common.edit', locale)}
                          onClick={() => router.push(`/tenant/tenants/${encodeURIComponent(tenant.id)}`)}
                        >
                          <IconPencil size={16} />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          title={t(tenant.status === 'enabled' ? 'tc.tenant.disable' : 'tc.tenant.enable', locale)}
                          aria-label={t(tenant.status === 'enabled' ? 'tc.tenant.disable' : 'tc.tenant.enable', locale)}
                          onClick={() => setTarget(tenant)}
                        >
                          {tenant.status === 'enabled' ? <IconPlayerPause size={16} /> : <IconPlayerPlay size={16} />}
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
        open={!!target}
        title={t(nextStatus === 'enabled' ? 'tc.tenant.enableTitle' : 'tc.tenant.disableTitle', locale)}
        message={t(nextStatus === 'enabled' ? 'tc.tenant.enableMessage' : 'tc.tenant.disableMessage', locale)}
        itemName={target?.name}
        itemDescription={target?.id}
        confirmLabel={t(nextStatus === 'enabled' ? 'tc.tenant.enable' : 'tc.tenant.disable', locale)}
        cancelLabel={t('tc.common.cancel', locale)}
        variant={nextStatus === 'disabled' ? 'destructive' : 'default'}
        loading={statusMutation.isPending}
        onCancel={() => setTarget(null)}
        onConfirm={handleToggle}
      />
    </div>
  )
}
