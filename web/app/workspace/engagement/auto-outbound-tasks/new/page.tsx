'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { toast } from 'sonner'
import { AutoOutboundTaskForm } from '@/app/components/features/engagement/auto-outbound-task-form'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { readAutoOutboundErrorMessage } from '@/lib/auto-outbound-api-error'
import type { CreateAutoOutboundTaskPayload } from '@/models/auto-outbound-task'
import { useCreateAutoOutboundTask } from '@/service/use-auto-outbound-tasks'
import { t } from '@/utils/i18n'

export default function NewAutoOutboundTaskPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const createTask = useCreateAutoOutboundTask()

  return (
    <div className="h-full overflow-hidden">
      <AutoOutboundTaskForm
        locale={locale}
        mode="create"
        header={(
          <div className="flex items-center gap-3 px-6 py-4">
            <Link href="/workspace/engagement/auto-outbound-tasks" className="rounded-md p-2 hover:bg-muted">
              <IconArrowLeft size={18} />
            </Link>
            <div>
              <h1 className="text-xl font-semibold text-foreground">{t('ws.autoOutbound.new.title', locale)}</h1>
            </div>
          </div>
        )}
        currentUserId={user?.id}
        submitting={createTask.isPending}
        onCancel={() => router.push('/workspace/engagement/auto-outbound-tasks')}
        onSaveDraft={async (values) => {
          try {
            const task = await createTask.mutateAsync(values as CreateAutoOutboundTaskPayload)
            toast.success(t('ws.autoOutbound.toast.draftSaved', locale))
            router.push(`/workspace/engagement/auto-outbound-tasks/${task.id}`)
          } catch (err) {
            toast.error(await readAutoOutboundErrorMessage(err, t('ws.autoOutbound.toast.saveFailed', locale)))
          }
        }}
        onStart={async (values) => {
          try {
            const task = await createTask.mutateAsync(values as CreateAutoOutboundTaskPayload)
            toast.success(t('ws.autoOutbound.toast.createdNeedTargets', locale))
            router.push(`/workspace/engagement/auto-outbound-tasks/${task.id}`)
          } catch (err) {
            toast.error(await readAutoOutboundErrorMessage(err, t('ws.autoOutbound.toast.saveFailed', locale)))
          }
        }}
      />
    </div>
  )
}
