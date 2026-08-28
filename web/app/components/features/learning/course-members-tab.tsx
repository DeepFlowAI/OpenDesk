'use client'

import { useEffect, useState } from 'react'
import { IconPlus, IconSearch, IconUser, IconUsers, IconX } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { AssignmentItem, LearnerItem, LearningCourseDetail } from '@/models/learning'
import {
  useAssignments,
  useLearners,
  useRemoveAssignment,
  useUpdateVisibility,
} from '@/service/use-learning'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { AddLearnersDialog } from './add-learners-dialog'
import { LearnStatusTag, PaginationBar, formatLearningDateTime } from './learning-tags'

const PER_PAGE = 20

function VisibilityRadio({ course }: { course: LearningCourseDetail }) {
  const { locale } = useLocaleStore()
  const updateVisibility = useUpdateVisibility(course.id)
  const options = [
    { value: 'all', labelKey: 'learning.members.all' },
    { value: 'assigned', labelKey: 'learning.members.assigned' },
  ] as const
  return (
    <div className="flex items-center gap-6 rounded-lg border border-border bg-white px-4 py-3">
      <span className="text-sm font-medium text-foreground">
        {t('learning.members.visibility', locale)}
      </span>
      {options.map((option) => {
        const active = course.visibility === option.value
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

function sourceText(learner: LearnerItem, locale: Parameters<typeof t>[1]): string {
  const parts: string[] = []
  if (learner.assigned_group_names.length > 0) {
    parts.push(
      t('learning.members.source.group', locale, { name: learner.assigned_group_names.join('、') }),
    )
  }
  if (learner.direct_assigned) parts.push(t('learning.members.source.direct', locale))
  return parts.join(' + ') || '—'
}

export function CourseMembersTab({ course }: { course: LearningCourseDetail }) {
  const { locale } = useLocaleStore()
  const [pickerOpen, setPickerOpen] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [confirm, setConfirm] = useState<
    | { kind: 'group'; assignment: AssignmentItem }
    | { kind: 'learner'; learner: LearnerItem; assignmentId: number }
    | null
  >(null)

  const isAll = course.visibility === 'all'
  const assignmentsQuery = useAssignments(course.id)
  const learnersQuery = useLearners(course.id, { q: q || undefined, page, per_page: PER_PAGE })
  const removeAssignment = useRemoveAssignment(course.id)

  // Debounce the name search (assigned courses search the table; all courses too).
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
  const learners = learnersQuery.data?.items ?? []
  const total = learnersQuery.data?.total ?? 0
  const pages = learnersQuery.data?.pages ?? 0

  const findEmployeeAssignmentId = (employeeId: number): number | undefined =>
    assignments.find(
      (item) => item.target_type === 'employee' && item.target_id === employeeId,
    )?.id

  const confirmLoading = removeAssignment.isPending

  return (
    <div className="space-y-4">
      <VisibilityRadio course={course} />

      {isAll ? (
        <>
          <div className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300">
            {t('learning.members.allHint', locale)}
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {t('learning.members.allTableTitle', locale)}
            </span>
            <div className="flex h-9 w-56 items-center gap-2 rounded-md border border-border bg-white px-3">
              <IconSearch size={16} className="text-muted-foreground" />
              <input
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder={t('learning.members.searchName', locale)}
                className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              />
            </div>
          </div>
        </>
      ) : (
        <div className="rounded-lg border border-border bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-medium text-foreground">
              {t('learning.members.assignScope', locale)}
            </span>
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className="flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground"
            >
              <IconPlus size={14} />
              {t('learning.members.addLearners', locale)}
            </button>
          </div>
          {assignments.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t('learning.members.assignEmpty', locale)}
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
                          ? t('learning.picker.memberCount', locale, { count: String(target.detail) })
                          : target.detail}
                      </span>
                    ) : null}
                    <button
                      type="button"
                      aria-label={t('learning.members.remove', locale)}
                      onClick={() =>
                        isGroup
                          ? setConfirm({ kind: 'group', assignment: target })
                          : setConfirm({
                              kind: 'learner',
                              learner: {
                                employee_id: target.target_id,
                                name: target.name,
                                group_names: [],
                                direct_assigned: true,
                                assigned_group_names: [],
                                progress: 0,
                                status: 'not_started',
                                last_learn_at: null,
                              },
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
            {t('learning.members.groupDynamicHint', locale)}
          </p>
        </div>
      )}

      {/* Learner progress table */}
      <div className="overflow-hidden rounded-lg border border-border bg-white">
        <table className="w-full text-sm">
          <thead className="bg-muted/60 text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">{t('learning.members.col.name', locale)}</th>
              <th className="px-4 py-3 font-medium">{t('learning.members.col.groups', locale)}</th>
              {!isAll ? (
                <th className="px-4 py-3 font-medium">{t('learning.members.col.source', locale)}</th>
              ) : null}
              <th className="px-4 py-3 font-medium">{t('learning.members.col.progress', locale)}</th>
              <th className="px-4 py-3 font-medium">{t('learning.members.col.status', locale)}</th>
              <th className="px-4 py-3 font-medium">
                {t('learning.members.col.lastLearnAt', locale)}
              </th>
              {!isAll ? (
                <th className="px-4 py-3 font-medium">{t('learning.members.col.actions', locale)}</th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {learnersQuery.isLoading ? (
              <tr>
                <td className="px-4 py-8 text-center text-muted-foreground" colSpan={isAll ? 5 : 7}>
                  {t('learning.common.loading', locale)}
                </td>
              </tr>
            ) : learners.length === 0 ? (
              <tr>
                <td className="px-4 py-8 text-center text-muted-foreground" colSpan={isAll ? 5 : 7}>
                  —
                </td>
              </tr>
            ) : (
              learners.map((learner) => (
                <tr key={learner.employee_id} className="border-t border-border">
                  <td className="px-4 py-3 font-medium">{learner.name}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {learner.group_names.join('、') || '—'}
                  </td>
                  {!isAll ? (
                    <td className="px-4 py-3 text-muted-foreground">{sourceText(learner, locale)}</td>
                  ) : null}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                        <div
                          className={`h-full rounded-full ${
                            learner.progress === 100 ? 'bg-emerald-500' : 'bg-primary'
                          }`}
                          style={{ width: `${learner.progress}%` }}
                        />
                      </div>
                      <span className="text-xs text-muted-foreground">{learner.progress}%</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <LearnStatusTag status={learner.status} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {formatLearningDateTime(learner.last_learn_at)}
                  </td>
                  {!isAll ? (
                    <td className="px-4 py-3">
                      {learner.direct_assigned ? (
                        <button
                          type="button"
                          onClick={() => {
                            const assignmentId = findEmployeeAssignmentId(learner.employee_id)
                            if (assignmentId !== undefined) {
                              setConfirm({ kind: 'learner', learner, assignmentId })
                            }
                          }}
                          className="text-xs font-medium text-red-600"
                        >
                          {t('learning.members.remove', locale)}
                        </button>
                      ) : (
                        <span
                          className="text-xs text-muted-foreground/50"
                          title={t('learning.members.removeViaGroupHint', locale)}
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

      <AddLearnersDialog courseId={course.id} open={pickerOpen} onClose={() => setPickerOpen(false)} />

      <ConfirmDialog
        open={confirm?.kind === 'group'}
        title={t('learning.confirm.removeGroup.title', locale)}
        message={t('learning.confirm.removeGroup.message', locale)}
        itemName={
          confirm?.kind === 'group'
            ? `${confirm.assignment.name} · ${t('learning.picker.memberCount', locale, { count: String(confirm.assignment.detail ?? 0) })}`
            : undefined
        }
        confirmLabel={t('learning.confirm.remove.confirm', locale)}
        cancelLabel={t('learning.common.cancel', locale)}
        variant="destructive"
        loading={confirmLoading}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (confirm?.kind !== 'group') return
          try {
            await removeAssignment.mutateAsync(confirm.assignment.id)
            toast.success(t('learning.toast.removed', locale))
          } catch {
            toast.error(t('learning.common.loadFailed', locale))
          } finally {
            setConfirm(null)
          }
        }}
      />
      <ConfirmDialog
        open={confirm?.kind === 'learner'}
        title={t('learning.confirm.removeLearner.title', locale)}
        message={t('learning.confirm.removeLearner.message', locale)}
        itemName={confirm?.kind === 'learner' ? confirm.learner.name : undefined}
        confirmLabel={t('learning.confirm.remove.confirm', locale)}
        cancelLabel={t('learning.common.cancel', locale)}
        variant="destructive"
        loading={confirmLoading}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (confirm?.kind !== 'learner') return
          try {
            await removeAssignment.mutateAsync(confirm.assignmentId)
            toast.success(t('learning.toast.removed', locale))
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
