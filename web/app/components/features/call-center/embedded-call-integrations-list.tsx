'use client'

import { useMemo, useState } from 'react'
import { IconCopy, IconPencil, IconPhoneCall, IconPlus, IconSearch, IconTrash } from '@tabler/icons-react'
import { HTTPError } from 'ky'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Switch } from '@/components/ui/switch'
import { useLocaleStore } from '@/context/locale-store'
import { copyPlainTextToClipboard } from '@/lib/clipboard'
import type { EmbeddedCallIntegration } from '@/models/embedded-call'
import {
  useDeleteEmbeddedCallIntegration,
  useEmbeddedCallIntegrations,
  useUpdateEmbeddedCallIntegration,
} from '@/service/use-embedded-call-integrations'


function formatDateTime(value: string | null, locale: string) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return value
  }
}

async function readErrorMessage(error: unknown, fallback: string) {
  if (error instanceof HTTPError) {
    try {
      const body = (await error.response.json()) as { message?: string }
      if (body.message?.trim()) return body.message.trim()
    } catch {
      return fallback
    }
  }
  return fallback
}

export function EmbeddedCallIntegrationsList() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const query = useEmbeddedCallIntegrations()
  const update = useUpdateEmbeddedCallIntegration()
  const remove = useDeleteEmbeddedCallIntegration()
  const [keyword, setKeyword] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<EmbeddedCallIntegration | null>(null)
  const newPath = '/call-center/integrations/embedded-call/new'

  const items = query.data?.items ?? []
  const filteredItems = useMemo(() => {
    const needle = searchKeyword.trim().toLowerCase()
    if (!needle) return items
    return items.filter((item) => {
      const haystack = [item.name, item.integration_key, ...item.allowed_origins]
        .join(' ')
        .toLowerCase()
      return haystack.includes(needle)
    })
  }, [items, searchKeyword])

  const handleSearch = () => {
    setSearchKeyword(keyword.trim())
  }

  const handleReset = () => {
    setKeyword('')
    setSearchKeyword('')
  }

  const toggle = async (item: EmbeddedCallIntegration, enabled: boolean) => {
    try {
      await update.mutateAsync({ id: item.public_id, data: { is_enabled: enabled } })
      toast.success(isZh ? '状态已更新' : 'Status updated')
    } catch (error) {
      toast.error(await readErrorMessage(error, isZh ? '状态更新失败' : 'Failed to update status'))
    }
  }

  const copyKey = async (value: string) => {
    const ok = await copyPlainTextToClipboard(value)
    if (ok) toast.success(isZh ? '已复制' : 'Copied')
    else toast.error(isZh ? '复制失败' : 'Failed to copy')
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await remove.mutateAsync(deleteTarget.public_id)
      setDeleteTarget(null)
      toast.success(isZh ? '集成已删除' : 'Integration deleted')
    } catch (error) {
      toast.error(await readErrorMessage(error, isZh ? '删除失败' : 'Failed to delete'))
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">
            {isZh ? '嵌入式通话' : 'Embedded calling'}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {isZh
              ? '把 OpenDesk 软电话安全嵌入第三方 Web 系统。'
              : 'Securely embed the OpenDesk softphone in third-party web apps.'}
          </p>
        </div>
        <button
          type="button"
          onClick={() => router.push(newPath)}
          className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          <IconPlus size={18} />
          {isZh ? '新建集成' : 'New integration'}
        </button>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex h-9 w-72 items-center gap-2 rounded-lg border border-border px-3">
          <IconSearch size={16} className="text-muted-foreground" />
          <input
            type="text"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') handleSearch()
            }}
            placeholder={isZh ? '搜索名称、Key 或来源' : 'Search name, key, or origin'}
            className="flex-1 border-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none"
          />
        </div>
        <button
          type="button"
          onClick={handleSearch}
          className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          {isZh ? '查询' : 'Search'}
        </button>
        <button
          type="button"
          onClick={handleReset}
          className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
        >
          {isZh ? '重置' : 'Reset'}
        </button>
      </div>

      {query.isLoading ? (
        <p className="text-sm text-muted-foreground">{isZh ? '加载中…' : 'Loading…'}</p>
      ) : query.isError ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16">
          <p className="text-sm text-muted-foreground">{isZh ? '加载失败，请重试' : 'Failed to load. Try again.'}</p>
          <button
            type="button"
            onClick={() => query.refetch()}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
          >
            {isZh ? '重试' : 'Retry'}
          </button>
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
            <IconPhoneCall size={22} className="text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground">
            {searchKeyword
              ? isZh
                ? '没有匹配的集成'
                : 'No matching integrations'
              : isZh
                ? '暂无嵌入式通话集成'
                : 'No embedded call integrations'}
          </p>
          {!searchKeyword && (
            <button
              type="button"
              onClick={() => router.push(newPath)}
              className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white"
            >
              <IconPlus size={18} />
              {isZh ? '新建集成' : 'New integration'}
            </button>
          )}
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-border">
            <div className="flex h-12 items-center gap-6 rounded-t-lg bg-muted px-6 text-sm font-semibold text-foreground/80">
              <div className="min-w-0 flex-1">{isZh ? '集成名称' : 'Name'}</div>
              <div className="min-w-0 flex-[1.4]">Integration key</div>
              <div className="w-[80px] shrink-0">{isZh ? '状态' : 'Status'}</div>
              <div className="w-[160px] shrink-0">{isZh ? '更新时间' : 'Updated'}</div>
              <div className="w-[80px] shrink-0">{isZh ? '操作' : 'Actions'}</div>
            </div>
            {filteredItems.map((item) => {
              const editPath = `/call-center/integrations/embedded-call/${item.public_id}`
              return (
                <div
                  key={item.public_id}
                  className="flex min-h-14 items-center gap-6 border-t border-border px-6 py-3"
                >
                  <div className="min-w-0 flex-1">
                    <button
                      type="button"
                      onClick={() => router.push(editPath)}
                      className="truncate text-left text-sm text-foreground hover:underline"
                      title={item.name}
                    >
                      {item.name}
                    </button>
                  </div>
                  <div className="flex min-w-0 flex-[1.4] items-center gap-2">
                    <span className="truncate font-mono text-xs text-muted-foreground" title={item.integration_key}>
                      {item.integration_key}
                    </span>
                    <button
                      type="button"
                      onClick={() => copyKey(item.integration_key)}
                      className="shrink-0 text-foreground/80 transition-colors hover:text-foreground"
                      aria-label={isZh ? '复制 Integration key' : 'Copy integration key'}
                    >
                      <IconCopy size={16} />
                    </button>
                  </div>
                  <div className="w-[80px] shrink-0">
                    <Switch
                      checked={item.is_enabled}
                      disabled={update.isPending}
                      aria-label={isZh ? '切换集成状态' : 'Toggle integration'}
                      onCheckedChange={(checked) => toggle(item, checked)}
                    />
                  </div>
                  <div className="w-[160px] shrink-0 text-sm text-muted-foreground">
                    {formatDateTime(item.updated_at, locale)}
                  </div>
                  <div className="flex w-[80px] shrink-0 items-center gap-3">
                    <button
                      type="button"
                      onClick={() => router.push(editPath)}
                      className="text-foreground/80 transition-colors hover:text-foreground"
                      aria-label={isZh ? '编辑' : 'Edit'}
                    >
                      <IconPencil size={18} />
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(item)}
                      className="text-foreground/80 transition-colors hover:text-destructive"
                      aria-label={isZh ? '删除' : 'Delete'}
                    >
                      <IconTrash size={18} />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
          <span className="text-sm text-muted-foreground">
            {isZh ? `共 ${filteredItems.length} 条` : `${filteredItems.length} total`}
          </span>
        </>
      )}
      <ConfirmDialog
        open={deleteTarget !== null}
        title={isZh ? '删除集成' : 'Delete integration'}
        message={isZh ? '删除后第三方将无法继续使用该集成，此操作不可恢复。' : 'The host will no longer be able to use this integration. This cannot be undone.'}
        itemName={deleteTarget?.name}
        confirmLabel={isZh ? '确定删除' : 'Delete'}
        cancelLabel={isZh ? '取消' : 'Cancel'}
        variant="destructive"
        loading={remove.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </div>
  )
}
