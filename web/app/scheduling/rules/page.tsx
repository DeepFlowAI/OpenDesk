'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconCopy, IconPencil, IconPlus, IconStar, IconTrash } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { RuleSet } from '@/models/scheduling-rule'
import { useShifts } from '@/service/use-scheduling'
import { useEmployeeGroups } from '@/service/use-employee-groups'
import { useCopyRuleSet, useDeleteRuleSet, useRuleSets } from '@/service/use-scheduling-rules'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { constraintSummary, targetSummary } from '@/app/components/features/scheduling/rules/rule-summary'

export default function SchedulingRulesPage() {
  const { locale } = useLocaleStore()
  const router = useRouter()
  const { data, isLoading } = useRuleSets()
  const { data: shiftsData } = useShifts()
  const { data: groupsData } = useEmployeeGroups({ per_page: 200 })
  const copyMutation = useCopyRuleSet()
  const deleteMutation = useDeleteRuleSet()

  const [deleteTarget, setDeleteTarget] = useState<RuleSet | null>(null)
  const [deleting, setDeleting] = useState(false)

  const ruleSets = data?.items ?? []
  const shifts = shiftsData?.items ?? []
  const groups = groupsData?.items ?? []

  const groupNames = (ids: number[]) =>
    ids
      .map((id) => groups.find((g) => g.id === id)?.name)
      .filter(Boolean)
      .join('、')

  const handleCopy = async (ruleSet: RuleSet) => {
    try {
      await copyMutation.mutateAsync(ruleSet.id)
      toast.success(t('scheduling.rules.toast.copied', locale))
    } catch {
      toast.error(t('scheduling.rules.toast.opFailed', locale))
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      toast.success(t('scheduling.rules.toast.deleted', locale))
      setDeleteTarget(null)
    } catch {
      toast.error(t('scheduling.rules.toast.deleteFailed', locale))
    } finally {
      setDeleting(false)
    }
  }

  if (!isLoading && ruleSets.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-8">
        <div className="max-w-md text-center">
          <h2 className="text-lg font-semibold text-foreground">
            {t('scheduling.rules.empty.title', locale)}
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {t('scheduling.rules.empty.desc', locale)}
          </p>
          <button
            type="button"
            className="mt-6 inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
            onClick={() => router.push('/scheduling/rules/new')}
          >
            <IconPlus size={18} />
            {t('scheduling.rules.new', locale)}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">
          {t('scheduling.rules.title', locale)}
        </h1>
        <button
          type="button"
          onClick={() => router.push('/scheduling/rules/new')}
          className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          <IconPlus size={18} />
          {t('scheduling.rules.new', locale)}
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border border-border">
        <div className="overflow-x-auto">
          <div style={{ minWidth: 980 }}>
            <div className="flex h-14 items-center gap-6 rounded-t-lg bg-muted px-6">
              <div className="w-[160px] shrink-0 text-sm font-semibold text-foreground/80">
                {t('scheduling.rules.col.name', locale)}
              </div>
              <div className="w-[80px] shrink-0 text-sm font-semibold text-foreground/80">
                {t('scheduling.rules.col.default', locale)}
              </div>
              <div className="min-w-[120px] flex-1 text-sm font-semibold text-foreground/80">
                {t('scheduling.rules.col.groups', locale)}
              </div>
              <div className="min-w-[160px] flex-1 text-sm font-semibold text-foreground/80">
                {t('scheduling.rules.col.targets', locale)}
              </div>
              <div className="min-w-[160px] flex-1 text-sm font-semibold text-foreground/80">
                {t('scheduling.rules.col.constraints', locale)}
              </div>
              <div className="w-[140px] shrink-0 text-sm font-semibold text-foreground/80">
                {t('scheduling.rules.col.updatedAt', locale)}
              </div>
              <div className="w-[96px] shrink-0 text-sm font-semibold text-foreground/80">
                {t('scheduling.rules.col.actions', locale)}
              </div>
            </div>

            {isLoading ? (
              <div className="border-t border-border px-6 py-10 text-center text-sm text-muted-foreground">
                {t('scheduling.rules.loading', locale)}
              </div>
            ) : (
              ruleSets.map((rs) => (
                <div
                  key={rs.id}
                  className="flex h-14 items-center gap-6 border-t border-border px-6"
                >
                  <div className="w-[160px] shrink-0 truncate text-sm font-medium text-foreground" title={rs.name}>
                    {rs.name}
                  </div>
                  <div className="flex w-[80px] shrink-0 items-center">
                    {rs.is_default ? (
                      <span className="inline-flex items-center gap-0.5 rounded-md bg-primary/10 px-1.5 py-0.5 text-[11px] text-primary">
                        <IconStar size={12} />
                        {t('scheduling.rules.default', locale)}
                      </span>
                    ) : (
                      <span className="text-sm text-muted-foreground">—</span>
                    )}
                  </div>
                  <div
                    className="min-w-[120px] flex-1 truncate text-sm text-muted-foreground"
                    title={groupNames(rs.default_group_ids) || undefined}
                  >
                    {groupNames(rs.default_group_ids) || '—'}
                  </div>
                  <div
                    className="min-w-[160px] flex-1 truncate text-sm text-muted-foreground"
                    title={targetSummary(rs, shifts, locale) || undefined}
                  >
                    {targetSummary(rs, shifts, locale) || '—'}
                  </div>
                  <div
                    className="min-w-[160px] flex-1 truncate text-sm text-muted-foreground"
                    title={constraintSummary(rs.constraints, locale) || undefined}
                  >
                    {constraintSummary(rs.constraints, locale) || '—'}
                  </div>
                  <div className="w-[140px] shrink-0 truncate text-sm text-muted-foreground">
                    {rs.updated_at
                      ? new Date(rs.updated_at).toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US', {
                          month: '2-digit',
                          day: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit',
                        })
                      : '—'}
                  </div>
                  <div className="flex w-[96px] shrink-0 items-center gap-3">
                    <button
                      type="button"
                      onClick={() => router.push(`/scheduling/rules/${rs.id}`)}
                      className="text-foreground/80 transition-colors hover:text-foreground"
                      aria-label={t('scheduling.rules.edit', locale)}
                      title={t('scheduling.rules.edit', locale)}
                    >
                      <IconPencil size={18} />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleCopy(rs)}
                      disabled={copyMutation.isPending}
                      className="text-foreground/80 transition-colors hover:text-foreground disabled:opacity-40"
                      aria-label={t('scheduling.rules.copy', locale)}
                      title={t('scheduling.rules.copy', locale)}
                    >
                      <IconCopy size={18} />
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(rs)}
                      className="text-foreground/80 transition-colors hover:text-destructive"
                      aria-label={t('scheduling.rules.delete', locale)}
                      title={t('scheduling.rules.delete', locale)}
                    >
                      <IconTrash size={18} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title={t('scheduling.rules.confirmDelete.title', locale)}
        message={t('scheduling.rules.confirmDelete.message', locale)}
        itemName={deleteTarget?.name}
        confirmLabel={t('scheduling.rules.confirmDelete.confirm', locale)}
        cancelLabel={t('scheduling.form.cancel', locale)}
        variant="destructive"
        loading={deleting}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
      />
    </div>
  )
}
