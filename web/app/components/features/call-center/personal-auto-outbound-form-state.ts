import type {
  PersonalAutoOutboundConfig,
  PersonalAutoOutboundSession,
} from '@/models/personal-auto-outbound'

export type PersonalAutoOutboundFormState = {
  taskId: string
  phoneId: string
  fallbackGroupId: string
  concurrency: number
  initialTaskMissing: boolean
}

export function resolvePersonalAutoOutboundFormState(
  config: PersonalAutoOutboundConfig,
  session: PersonalAutoOutboundSession | null,
  initialTaskId: number | null,
): PersonalAutoOutboundFormState {
  if (session) {
    return {
      taskId: String(session.task_id),
      phoneId: session.outbound_phone_number_id,
      fallbackGroupId: session.fallback_group_id === null ? '' : String(session.fallback_group_id),
      concurrency: session.configured_concurrency,
      initialTaskMissing: false,
    }
  }

  const preferredTask = config.tasks.find((item) => item.id === initialTaskId)
  return {
    taskId: String(preferredTask?.id ?? config.tasks[0]?.id ?? ''),
    phoneId: config.phone_numbers[0]?.id ?? '',
    fallbackGroupId: '',
    concurrency: 4,
    initialTaskMissing: Boolean(initialTaskId && !preferredTask),
  }
}
