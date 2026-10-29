import { describe, expect, it, vi } from 'vitest'

import {
  canAttemptSessionRecovery,
  canAttemptSessionRecoveryForToken,
  claimSessionRecoveryReconnect,
  CONVERSATION_SUBSCRIPTION_REPLACED_EVENT,
  decideJoinNotFoundReplace,
  emptySessionRecoveryBudget,
  followSessionRecoveryToken,
  isSessionRecoveryFlightCurrent,
  MAX_JOIN_NOT_FOUND_REPLACES_PER_CONNECTION,
  MAX_SESSION_RECOVERIES,
  recordSessionRecoveryAttempt,
  requestSessionRecoveryReconnect,
  resolveSessionRecoveryReconnectIntent,
  SESSION_RECOVERY_BUDGET_DECAY_MS,
  sessionRecoveryFailureTelemetryLevel,
  shouldForceSessionRecoveryReconnect,
  shouldReportSessionRecoveryExhausted,
  VISITOR_SESSION_RECOVERY_EXHAUSTED_EVENT,
  withVisitorSessionRecovery,
} from './visitor-session-recovery'

describe('visitor session recovery exhausted telemetry', () => {
  it('uses a stable error-level event name', () => {
    expect(VISITOR_SESSION_RECOVERY_EXHAUSTED_EVENT).toBe('visitor_session_recovery_exhausted')
  })
})

describe('canAttemptSessionRecovery', () => {
  it('caps remint attempts at MAX_SESSION_RECOVERIES', () => {
    expect(canAttemptSessionRecovery(0)).toBe(true)
    expect(canAttemptSessionRecovery(MAX_SESSION_RECOVERIES - 1)).toBe(true)
    expect(canAttemptSessionRecovery(MAX_SESSION_RECOVERIES)).toBe(false)
  })
})

describe('session recovery budget', () => {
  const t0 = 1_700_000_000_000

  it('does not reset the remint count on join/connect success after a remint chain', () => {
    let budget = emptySessionRecoveryBudget()

    budget = recordSessionRecoveryAttempt(budget, 'tok_a', t0)
    budget = followSessionRecoveryToken(budget, 'tok_b')
    expect(canAttemptSessionRecoveryForToken(budget, 'tok_b', t0)).toBe(true)

    budget = recordSessionRecoveryAttempt(budget, 'tok_b', t0 + 1)
    budget = followSessionRecoveryToken(budget, 'tok_c')
    budget = recordSessionRecoveryAttempt(budget, 'tok_c', t0 + 2)
    expect(budget.attempts).toBe(MAX_SESSION_RECOVERIES)
    expect(canAttemptSessionRecoveryForToken(budget, 'tok_c', t0 + 2)).toBe(false)

    // A later join/connect success must not clear the chain — following
    // the minted token keeps the count until the decay window elapses.
    expect(followSessionRecoveryToken(budget, 'tok_c').attempts).toBe(MAX_SESSION_RECOVERIES)
  })

  it('resets the remint count when the recorded token is stale', () => {
    let budget = recordSessionRecoveryAttempt(emptySessionRecoveryBudget(), 'tok_a', t0)
    budget = followSessionRecoveryToken(budget, 'tok_b')
    budget = recordSessionRecoveryAttempt(budget, 'tok_a', t0 + 1)
    expect(budget).toEqual({ token: 'tok_a', attempts: 1, lastAttemptAt: t0 + 1 })
  })

  it('keeps a failed mint charged against the failing token', () => {
    let budget = recordSessionRecoveryAttempt(emptySessionRecoveryBudget(), 'tok_a', t0)
    budget = recordSessionRecoveryAttempt(budget, 'tok_a', t0 + 1)
    expect(budget).toEqual({ token: 'tok_a', attempts: 2, lastAttemptAt: t0 + 1 })
    expect(canAttemptSessionRecoveryForToken(budget, 'tok_a', t0 + 1)).toBe(true)
  })

  it('resets the remint count after the decay window', () => {
    let budget = recordSessionRecoveryAttempt(emptySessionRecoveryBudget(), 'tok_a', t0)
    budget = followSessionRecoveryToken(budget, 'tok_b')
    budget = recordSessionRecoveryAttempt(budget, 'tok_b', t0 + 1)
    budget = followSessionRecoveryToken(budget, 'tok_c')
    budget = recordSessionRecoveryAttempt(budget, 'tok_c', t0 + 2)
    expect(canAttemptSessionRecoveryForToken(budget, 'tok_c', t0 + 2)).toBe(false)
    expect(followSessionRecoveryToken(budget, 'tok_c').lastAttemptAt).toBe(t0 + 2)

    const afterDecay = t0 + 2 + SESSION_RECOVERY_BUDGET_DECAY_MS
    expect(canAttemptSessionRecoveryForToken(budget, 'tok_c', afterDecay)).toBe(true)

    budget = recordSessionRecoveryAttempt(budget, 'tok_c', afterDecay)
    expect(budget).toEqual({ token: 'tok_c', attempts: 1, lastAttemptAt: afterDecay })
  })
})

describe('decideJoinNotFoundReplace', () => {
  it('discards a stale conversation once with warn telemetry and no error', () => {
    const first = decideJoinNotFoundReplace(null, 'conv_1')
    expect(first).toEqual({
      action: 'replace',
      discardedId: 'conv_1',
      replaceCount: 1,
      telemetry: {
        name: CONVERSATION_SUBSCRIPTION_REPLACED_EVENT,
        level: 'warn',
        conversation_external_id: 'conv_1',
        props: { error: 'NOT_FOUND', replaced: true },
      },
    })
    expect(first.action === 'replace' && first.telemetry.level).toBe('warn')
    expect(first.action === 'replace' && first.telemetry.level).not.toBe('error')
  })

  it('does not discard the same conversation id twice', () => {
    const first = decideJoinNotFoundReplace(null, 'conv_1')
    expect(decideJoinNotFoundReplace(first.discardedId, 'conv_1')).toEqual({
      action: 'fail',
      discardedId: 'conv_1',
      replaceAttempted: true,
    })
  })

  it('discards a different conversation id after a prior replace', () => {
    const first = decideJoinNotFoundReplace(null, 'conv_1')
    const second = decideJoinNotFoundReplace(first.discardedId, 'conv_2')
    expect(second.action).toBe('replace')
    expect(second.discardedId).toBe('conv_2')
  })

  it('does not self-heal a conversation that already ended', () => {
    expect(decideJoinNotFoundReplace(null, 'conv_1', { ended: true })).toEqual({
      action: 'fail',
      discardedId: 'conv_1',
      replaceAttempted: false,
    })
  })

  it('caps replace attempts per connection so cycling ids cannot loop', () => {
    const first = decideJoinNotFoundReplace(null, 'conv_x', { replaceCount: 0 })
    expect(first.action).toBe('replace')
    const second = decideJoinNotFoundReplace(
      first.action === 'replace' ? first.discardedId : null,
      'conv_y',
      { replaceCount: first.action === 'replace' ? first.replaceCount : 0 },
    )
    expect(second).toMatchObject({
      action: 'replace',
      discardedId: 'conv_y',
      replaceCount: MAX_JOIN_NOT_FOUND_REPLACES_PER_CONNECTION,
    })
    expect(decideJoinNotFoundReplace('conv_y', 'conv_x', {
      replaceCount: MAX_JOIN_NOT_FOUND_REPLACES_PER_CONNECTION,
    })).toEqual({
      action: 'fail',
      discardedId: 'conv_y',
      replaceAttempted: true,
    })
  })
})

describe('shouldReportSessionRecoveryExhausted', () => {
  it('emits once when the token is null because the sentinel is undefined', () => {
    expect(shouldReportSessionRecoveryExhausted(undefined, null)).toBe(true)
    expect(shouldReportSessionRecoveryExhausted(null, null)).toBe(false)
  })

  it('dedupes mint_failed / exhausted telemetry by token', () => {
    expect(shouldReportSessionRecoveryExhausted(undefined, 'tok_a')).toBe(true)
    expect(shouldReportSessionRecoveryExhausted('tok_a', 'tok_a')).toBe(false)
    expect(shouldReportSessionRecoveryExhausted('tok_a', 'tok_b')).toBe(true)
    expect(shouldReportSessionRecoveryExhausted('tok_a', null)).toBe(true)
  })
})

describe('session recovery reconnect intent', () => {
  it('upgrades an in-flight remint so a later reconnectSocket caller is not dropped', () => {
    const flight = {
      wantReconnect: false,
      didReconnect: false,
      visitorExternalId: 'vis_1',
      generation: 1,
    }
    requestSessionRecoveryReconnect(flight)
    expect(claimSessionRecoveryReconnect(flight)).toBe('vis_1')
    expect(flight.didReconnect).toBe(true)
  })

  it('lets only one waiter claim the reconnect', () => {
    const flight = {
      wantReconnect: true,
      didReconnect: false,
      visitorExternalId: 'vis_1',
      generation: 1,
    }
    expect(claimSessionRecoveryReconnect(flight)).toBe('vis_1')
    expect(claimSessionRecoveryReconnect(flight)).toBeNull()
  })

  it('does not reconnect when remint has no visitor id yet', () => {
    const flight = {
      wantReconnect: true,
      didReconnect: false,
      visitorExternalId: null,
      generation: 1,
    }
    expect(claimSessionRecoveryReconnect(flight)).toBeNull()
    expect(flight.didReconnect).toBe(false)
  })

  it('forces reconnect when remint changes visitor identity', () => {
    const flight = {
      wantReconnect: false,
      didReconnect: false,
      visitorExternalId: null,
      generation: 1,
    }
    expect(shouldForceSessionRecoveryReconnect('vis_a', 'vis_b')).toBe(true)
    expect(resolveSessionRecoveryReconnectIntent(flight, 'vis_a', 'vis_b')).toBe('vis_b')
    expect(flight.wantReconnect).toBe(true)
    expect(flight.didReconnect).toBe(true)
  })

  it('does not reconnect a healthy socket when identity is unchanged', () => {
    const flight = {
      wantReconnect: false,
      didReconnect: false,
      visitorExternalId: null,
      generation: 1,
    }
    expect(shouldForceSessionRecoveryReconnect('vis_a', 'vis_a')).toBe(false)
    expect(resolveSessionRecoveryReconnectIntent(flight, 'vis_a', 'vis_a')).toBeNull()
    expect(flight.didReconnect).toBe(false)
  })
})

describe('session recovery flight generation', () => {
  it('discards a remint that finished after a newer payload generation', () => {
    expect(isSessionRecoveryFlightCurrent(1, 1)).toBe(true)
    expect(isSessionRecoveryFlightCurrent(1, 2)).toBe(false)
  })
})

describe('session recovery failure telemetry level', () => {
  it('warns on the first mint_failed and errors once the budget is spent', () => {
    expect(sessionRecoveryFailureTelemetryLevel('mint_failed', 1)).toBe('warn')
    expect(sessionRecoveryFailureTelemetryLevel('mint_failed', MAX_SESSION_RECOVERIES)).toBe('error')
    expect(sessionRecoveryFailureTelemetryLevel('budget_exhausted', 1)).toBe('error')
  })
})

describe('withVisitorSessionRecovery', () => {
  it('retries the original call after a successful remint', async () => {
    const recoverVisitorSession = vi.fn().mockResolvedValue('tok_new')
    const run = vi.fn()
      .mockRejectedValueOnce({ response: { status: 401 }, message: 'Request failed with status code 401' })
      .mockResolvedValueOnce({ items: [] })

    await expect(withVisitorSessionRecovery(run, {
      visitorSessionToken: 'tok_old',
      recoverVisitorSession,
    })).resolves.toEqual({ items: [] })

    expect(recoverVisitorSession).toHaveBeenCalledOnce()
    expect(run).toHaveBeenNthCalledWith(1, 'tok_old')
    expect(run).toHaveBeenNthCalledWith(2, 'tok_new')
  })

  it('does not remint or retry a non-recoverable failure', async () => {
    const recoverVisitorSession = vi.fn()
    const error = { response: { status: 500 }, message: 'Request failed with status code 500' }
    const run = vi.fn().mockRejectedValue(error)

    await expect(withVisitorSessionRecovery(run, {
      visitorSessionToken: 'tok_old',
      recoverVisitorSession,
    })).rejects.toBe(error)

    expect(recoverVisitorSession).not.toHaveBeenCalled()
    expect(run).toHaveBeenCalledOnce()
  })

  it('rethrows the original error when remint is exhausted', async () => {
    const recoverVisitorSession = vi.fn().mockResolvedValue(null)
    const error = { response: { status: 401 }, message: 'Request failed with status code 401' }
    const run = vi.fn().mockRejectedValue(error)

    await expect(withVisitorSessionRecovery(run, {
      visitorSessionToken: 'tok_old',
      recoverVisitorSession,
    })).rejects.toBe(error)

    expect(run).toHaveBeenCalledOnce()
  })
})
