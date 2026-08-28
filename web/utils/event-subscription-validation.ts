import { z } from 'zod'

function isSafeHttpsShape(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password && !url.hash && Boolean(url.hostname)
  } catch {
    return false
  }
}

export const eventSubscriptionSchema = z.object({
  name: z.string().trim().min(2, 'name').max(80, 'name'),
  endpoint_url: z.string().trim().min(1, 'endpoint').max(2048, 'endpoint').refine(isSafeHttpsShape, 'endpoint'),
  description: z.string().trim().max(200, 'description'),
})

export type EventSubscriptionFormValue = z.infer<typeof eventSubscriptionSchema>

export function validateEventSubscriptionForm(value: EventSubscriptionFormValue) {
  const result = eventSubscriptionSchema.safeParse(value)
  const errors: Partial<Record<keyof EventSubscriptionFormValue, string>> = {}
  if (!result.success) {
    for (const issue of result.error.issues) {
      const field = issue.path[0] as keyof EventSubscriptionFormValue
      errors[field] ??= issue.message
    }
  }
  return { data: result.success ? result.data : null, errors }
}
