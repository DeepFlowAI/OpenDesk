import { HTTPError } from 'ky'

export type CallEventRuleError = {
  status: number | null
  detailCode: string | null
  ruleName: string | null
  traceId: string | null
}

export async function readCallEventRuleError(error: unknown): Promise<CallEventRuleError> {
  if (!(error instanceof HTTPError)) {
    return { status: null, detailCode: null, ruleName: null, traceId: null }
  }
  const traceId = error.response.headers.get('X-Trace-Id')
  try {
    const body = (await error.response.clone().json()) as {
      details?: { code?: string; rule_name?: string | null } | null
    }
    return {
      status: error.response.status,
      detailCode: body.details?.code ?? null,
      ruleName: body.details?.rule_name ?? null,
      traceId,
    }
  } catch {
    return { status: error.response.status, detailCode: null, ruleName: null, traceId }
  }
}

export function permissionDeniedText(isZh: boolean): string {
  return isZh
    ? '你没有管理通话事件订阅的权限'
    : 'You do not have permission to manage call event subscriptions'
}
