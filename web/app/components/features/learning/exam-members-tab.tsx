'use client'

import { useEffect, useState } from 'react'
import { IconPlus, IconSearch, IconUser, IconUsers, IconX } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { AssignmentItem } from '@/models/learning'
import type { ExamResultItem, LearningExamDetail } from '@/models/learning-exam'
import {
  useExamAssignments,
  useExamResults,
  useRemoveExamAssignment,
  useUpdateExamVisibility,
} from '@/service/use-learning-exam'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { AddExamineesDialog } from './add-examinees-dialog'
import { ExamResultStatusTag, PaginationBar, formatLearningDateTime } from './learning-tags'

const PER_PAGE = 20

function VisibilityRadio({ exam }: { exam: LearningExamDetail }) {
  const { locale } = useLocaleStore()
  const updateVisibility = useUpdateExamVisibility(exam.id)
  const options = [
    { value: 'all', labelKey: 'learning.exam.members.all' },
    { value: 'assigned', labelKey: 'learning.exam.members.assigned' },
  ] as const
  return (
    <div className="flex items-center gap-6 rounded-lg border border-border bg-white px-4 py-3">
      <span className="text-sm font-medium text-foreground">
        {t('learning.exam.members.visibility', locale)}
      </span>
      {options.map((option) => {
        const active = exam.visibility === option.value
        return (
          <button
            key={option.value}
            type="button"
            disabled={updateVisibility.isPending || active}
            onClick={() =>
              updateVisibility.mutate(option.value, {
                onError: () => toast.error(t('learning.common.loadFailed', locale)),
              })
            }
            className="flex items-center gap-2 text-sm disabled:cursor-default"
          >
            <span
              className={`grid h-4 w-4 place-items-center rounded-full border ${
                active ? 'border-primary' : 'border-border'
              }`}
            >
              {active ? <span className="h-2 w-2 rounded-full bg-primary" /> : null}
            </span>
            {t(option.labelKey, locale)}
          </button>
        )
      })}
    </div>
  )
}

function sourceText(result: ExamResultItem, locale: Parameters<typeof t>[1]): string {
  const parts: string[] = []
  if (result.assigned_group_names.length > 0) {
    parts.push(
      t('learning.exam.members.source.group', locale, { name: result.assigned_group_names.join('、') }),
    )
  }
  if (result.direct_assigned) parts.push(t('learning.exam.members.source.direct', locale))
  return parts.join(' + ') || '—'
}

export function ExamMembersTab({ exam }: { exam: LearningExamDetail }) {
  const { locale } = useLocaleStore()
  const [pickerOpen, setPickerOpen] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [confirm, setConfirm] = useState<
    | { kind: 'group'; assignment: AssignmentItem }
    | { kind: 'learner'; name: string; assignmentId: number }
    | null
  >(null)

  const isAll = exam.visibility === 'all'
  const assignmentsQuery = useExamAssignments(exam.id)
  const resultsQuery = useExamResults(exam.id, { q: q || undefined, page, per_page: PER_PAGE })
  const removeAssignment = useRemoveExamAssignment(exam.id)

  // Debounce the name search.
  useEffect(() => {
    const keyword = searchInput.trim()
    if (keyword === q) return
    const timer = setTimeout(() => {
      setQ(keyword)
      setPage(1)
    }, 400)
    return () => clearTimeout(timer)
  }, [searchInput, q])

  const assignments = assignmentsQuery.data?.items ?? []
  const results = resultsQuery.data?.items ?? []
  const total = resultsQuery.data?.total ?? 0
  const pages = resultsQuery.data?.pages ?? 0

  const findEmployeeAssignmentId = (employeeId: number): number | undefined =>
    assignments.find(
      (item) => item.target_type === 'employee' && item.target_id === employeeId,
    )?.id

  const confirmLoading = removeAssignment.isPending

  return (
    <div className="space-y-4">
      <VisibilityRadio exam={exam} />

      {isAll ? (
        <>
          <div className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300">
            {t('learning.exam.members.allHint', locale)}
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {t('learning.exam.members.allTableTitle', locale)}
            </span>
            <div className="flex h-9 w-56 items-center gap-2 rounded-md border border-border bg-white px-3">
              <IconSearch size={16} className="text-muted-foreground" />
              <input
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder={t('learning.exam.members.searchName', locale)}
                className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              />
            </div>
          </div>
        </>
      ) : (
        <div className="rounded-lg border border-border bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-medium text-foreground">
              {t('learning.exam.members.assignScope', locale)}
            </span>
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className="flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground"
            >
              <IconPlus size={14} />
              {t('learning.exam.members.addExaminees', locale)}
            </button>
          </div>
          {assignments.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t('learning.exam.members.assignEmpty', locale)}
            </p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              {assignments.map((target) => {
                const isGroup = target.target_type === 'group'
                return (
                  <span
                    key={target.id}
                    className="flex items-center gap-1.5 rounded-md border border-border bg-white px-2.5 py-1.5 text-xs"
                  >
                    {isGroup ? (
                      <IconUsers size={13} className="text-sky-600" />
                    ) : (
                      <IconUser size={13} className="text-muted-foreground" />
                    )}
                    <span className="font-medium">{target.name}</span>
                    {target.detail !== null && target.detail !== '' ? (
                      <span className="text-muted-foreground">
                        {isGroup
                          ? t('learning.exam.picker.memberCount', locale, { count: String(target.detail) })
                          : target.detail}
                      </span>
                    ) : null}
                    <button
                      type="button"
                      aria-label={t('learning.exam.members.remove', locale)}
                      onClick={() =>
                        isGroup
                          ? setConfirm({ kind: 'group', assignment: target })
                          : setConfirm({
                              kind: 'learner',
                              name: target.name,
                              assignmentId: target.id,
                            })
                      }
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <IconX size={12} />
                    </button>
                  </span>
                )
              })}
            </div>
          )}
          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            {t('learning.exam.members.groupDynamicHint', locale)}
          </p>
        </div>
      )}

      {/* Results table */}
      <div className="overflow-hidden rounded-lg border border-border bg-white">
        <table className="w-full text-sm">
          <thead className="bg-muted/60 text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">{t('learning.exam.members.col.name', locale)}</th>
              <th className="px-4 py-3 font-medium">{t('learning.exam.members.col.groups', locale)}</th>
              {!isAll ? (
                <th className="px-4 py-3 font-medium">{t('learning.exam.members.col.source', locale)}</th>
              ) : null}
              <th className="px-4 py-3 font-medium">{t('learning.exam.members.col.bestScore', locale)}</th>
              <th className="px-4 py-3 font-medium">{t('learning.exam.members.col.status', locale)}</th>
              <th className="px-4 py-3 font-medium">{t('learning.exam.members.col.attempts', locale)}</th>
              <th className="px-4 py-3 font-medium">
                {t('learning.exam.members.col.lastSubmitAt', locale)}
              </th>
              {!isAll ? (
                <th className="px-4 py-3 font-medium">{t('learning.exam.members.col.actions', locale)}</th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {resultsQuery.isLoading ? (
              <tr>
                <td className="px-4 py-8 text-center text-muted-foreground" colSpan={isAll ? 6 : 8}>
                  {t('learning.common.loading', locale)}
                </td>
              </tr>
            ) : results.length === 0 ? (
              <tr>
                <td className="px-4 py-8 text-center text-muted-foreground" colSpan={isAll ? 6 : 8}>
                  —
                </td>
              </tr>
            ) : (
              results.map((result) => (
                <tr key={result.employee_id} className="border-t border-border">
                  <td className="px-4 py-3 font-medium">{result.name}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {result.group_names.join('、') || '—'}
                  </td>
                  {!isAll ? (
                    <td className="px-4 py-3 text-muted-foreground">{sourceText(result, locale)}</td>
                  ) : null}
                  <td className="px-4 py-3">{result.best_score === null ? '—' : result.best_score}</td>
                  <td className="px-4 py-3">
                    <ExamResultStatusTag status={result.status} />
                  </td>
                  <td className="px-4 py-3">{result.submitted_count}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {formatLearningDateTime(result.last_submitted_at)}
                  </td>
                  {!isAll ? (
                    <td className="px-4 py-3">
                      {result.direct_assigned ? (
                        <button
                          type="button"
                          onClick={() => {
                            const assignmentId = findEmployeeAssignmentId(result.employee_id)
                            if (assignmentId !== undefined) {
                              setConfirm({ kind: 'learner', name: result.name, assignmentId })
                            }
                          }}
                          className="text-xs font-medium text-red-600"
                        >
                          {t('learning.exam.members.remove', locale)}
                        </button>
                      ) : (
                        <span
                          className="text-xs text-muted-foreground/50"
                          title={t('learning.exam.members.removeViaGroupHint', locale)}
                        >
                          —
                        </span>
                      )}
                    </td>
                  ) : null}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <PaginationBar total={total} page={page} pages={pages} onPageChange={setPage} />

      <AddExamineesDialog examId={exam.id} open={pickerOpen} onClose={() => setPickerOpen(false)} />

      <ConfirmDialog
        open={confirm?.kind === 'group'}
        title={t('learning.exam.confirm.removeGroup.title', locale)}
        message={t('learning.exam.confirm.removeGroup.message', locale)}
        itemName={
          confirm?.kind === 'group'
            ? `${confirm.assignment.name} · ${t('learning.exam.picker.memberCount', locale, { count: String(confirm.assignment.detail ?? 0) })}`
            : undefined
        }
        confirmLabel={t('learning.exam.confirm.remove.confirm', locale)}
        cancelLabel={t('learning.common.cancel', locale)}
        variant="destructive"
        loading={confirmLoading}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (confirm?.kind !== 'group') return
          try {
            await removeAssignment.mutateAsync(confirm.assignment.id)
            toast.success(t('learning.exam.toast.removed', locale))
          } catch {
            toast.error(t('learning.common.loadFailed', locale))
          } finally {
            setConfirm(null)
          }
        }}
      />
      <ConfirmDialog
        open={confirm?.kind === 'learner'}
        title={t('learning.exam.confirm.removeLearner.title', locale)}
        message={t('learning.exam.confirm.removeLearner.message', locale)}
        itemName={confirm?.kind === 'learner' ? confirm.name : undefined}
        confirmLabel={t('learning.exam.confirm.remove.confirm', locale)}
        cancelLabel={t('learning.common.cancel', locale)}
        variant="destructive"
        loading={confirmLoading}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (confirm?.kind !== 'learner') return
          try {
            await removeAssignment.mutateAsync(confirm.assignmentId)
            toast.success(t('learning.exam.toast.removed', locale))
          } catch {
            toast.error(t('learning.common.loadFailed', locale))
          } finally {
            setConfirm(null)
          }
        }}
      />
    </div>
  )
}
