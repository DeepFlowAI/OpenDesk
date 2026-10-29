import { HTTPError } from 'ky'
import type { Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'

const API_MESSAGE_I18N: Array<{ match: string; key: string }> = [
  // Order matters: the first substring hit wins.
  {
    match: 'target has entered the calling process',
    key: 'ws.autoOutbound.deleteTarget.error.enteredCalling',
  },
  {
    match: 'task has ended. Outbound targets cannot be deleted',
    key: 'ws.autoOutbound.deleteTarget.error.taskEnded',
  },
  {
    match: 'Permission denied to delete auto outbound target',
    key: 'ws.autoOutbound.deleteTarget.error.forbidden',
  },
  {
    match: 'Auto outbound target not found',
    key: 'ws.autoOutbound.deleteTarget.error.notFound',
  },
  { match: 'Archived tasks cannot', key: 'ws.autoOutbound.validation.taskArchived' },
  { match: 'Completed tasks cannot accept', key: 'ws.autoOutbound.validation.taskCompleted' },
  { match: 'Add pending numbers before resuming', key: 'ws.autoOutbound.validation.resumeNoPending' },
  { match: 'has ended and cannot be resumed', key: 'ws.autoOutbound.validation.taskEnded' },
  { match: 'Targets can only be added', key: 'ws.autoOutbound.validation.taskNotMutable' },
  { match: 'import outbound targets before starting', key: 'ws.autoOutbound.validation.emptyTargets' },
]

export function localizeAutoOutboundApiMessage(message: string, locale: Locale): string {
  const text = message.trim()
  if (!text) return text
  const hit = API_MESSAGE_I18N.find((item) => text.includes(item.match))
  return hit ? t(hit.key, locale) : text
}

/** Prefer backend message / detail from a ky HTTPError; else fallback. */
export async function readAutoOutboundErrorMessage(
  error: unknown,
  fallback: string,
): Promise<string> {
  if (!(error instanceof HTTPError)) {
    if (error instanceof Error && error.message.trim()) return error.message.trim()
    return fallback
  }
  try {
    const body = (await error.response.clone().json()) as {
      message?: string
      detail?: string | Array<{ msg?: string }>
      error?: { message?: string } | string
    }
    if (typeof body.message === 'string' && body.message.trim()) {
      return body.message.trim()
    }
    if (typeof body.error === 'string' && body.error.trim()) {
      return body.error.trim()
    }
    if (
      body.error
      && typeof body.error === 'object'
      && typeof body.error.message === 'string'
      && body.error.message.trim()
    ) {
      return body.error.message.trim()
    }
    if (typeof body.detail === 'string' && body.detail.trim()) {
      return body.detail.trim()
    }
    if (Array.isArray(body.detail)) {
      const first = body.detail.find((item) => typeof item?.msg === 'string' && item.msg.trim())
      if (first?.msg) return first.msg.trim()
    }
  } catch {
    // ignore JSON parse errors
  }
  return fallback
}

export async function readLocalizedAutoOutboundError(
  error: unknown,
  locale: Locale,
  fallback: string,
): Promise<string> {
  const raw = await readAutoOutboundErrorMessage(error, fallback)
  return localizeAutoOutboundApiMessage(raw, locale)
}
