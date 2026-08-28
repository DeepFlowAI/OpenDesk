'use client'

import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useStartExamAttempt } from '@/service/use-learning-exam'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'

export interface StartExamTarget {
  id: number
  name: string
  time_limit_minutes: number | null
}

/**
 * Shared "start exam" confirm: starts an attempt and navigates straight into
 * the taking view of the exam detail page.
 */
export function ExamStartConfirmDialog({
  exam,
  onClose,
}: {
  exam: StartExamTarget | null
  onClose: () => void
}) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const startMutation = useStartExamAttempt()

  return (
    <ConfirmDialog
      open={exam !== null}
      title={t('learning.myexam.startConfirm.title', locale)}
      message={
        exam?.time_limit_minutes
          ? t('learning.myexam.startConfirm.messageLimited', locale, {
              minutes: String(exam.time_limit_minutes),
            })
          : t('learning.myexam.startConfirm.messageUnlimited', locale)
      }
      itemName={exam?.name}
      confirmLabel={t('learning.myexam.startConfirm.confirm', locale)}
      cancelLabel={t('learning.common.cancel', locale)}
      loading={startMutation.isPending}
      onCancel={onClose}
      onConfirm={async () => {
        if (!exam) return
        try {
          const attempt = await startMutation.mutateAsync(exam.id)
          onClose()
          router.push(`/learning/exams/my/${exam.id}?attempt=${attempt.attempt_id}`)
        } catch {
          toast.error(t('learning.common.loadFailed', locale))
          onClose()
        }
      }}
    />
  )
}
