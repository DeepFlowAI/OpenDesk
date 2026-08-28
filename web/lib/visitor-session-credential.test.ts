import { describe, expect, it } from 'vitest'

import {
  getVisitorPayloadKey,
  mergeEmbedInitPayload,
  resolveVisitorIdentitySource,
  selectStoredVisitorCredential,
  shouldAutoStartConversation,
  type VisitorCredential,
  type VisitorIdentityPayload,
} from './visitor-session-credential'

const loggedInCredential: VisitorCredential = {
  visitorExternalId: '678796100886475112',
  visitorSecret: 'vs_test_secret',
  visitorPayloadKey: getVisitorPayloadKey({ contextToken: 'odctx_user_a' }),
}

const anonymousCredential: VisitorCredential = {
  visitorExternalId: 'v_dvtsoKzEuYW5PN04Ng4uFsRN8lzKwqvZ',
  visitorSecret: 'vs_anon_secret',
  visitorPayloadKey: getVisitorPayloadKey({}),
}

describe('selectStoredVisitorCredential', () => {
  it('reuses credentials when the payload key still matches', () => {
    expect(
      selectStoredVisitorCredential(loggedInCredential, { contextToken: 'odctx_user_a' }),
    ).toEqual(loggedInCredential)
  })

  it('preserves the last identity when contextToken is absent after refresh', () => {
    expect(selectStoredVisitorCredential(loggedInCredential, {})).toEqual(loggedInCredential)
    expect(
      selectStoredVisitorCredential(loggedInCredential, { contextToken: undefined }),
    ).toEqual(loggedInCredential)
  })

  it('does not reuse credentials on explicit logout (contextToken null)', () => {
    expect(
      selectStoredVisitorCredential(loggedInCredential, { contextToken: null }),
    ).toBeNull()
  })

  it('does not reuse credentials when a different contextToken arrives', () => {
    expect(
      selectStoredVisitorCredential(loggedInCredential, { contextToken: 'odctx_user_b' }),
    ).toBeNull()
  })

  it('upgrades an anonymous credential when a contextToken arrives', () => {
    expect(
      selectStoredVisitorCredential(anonymousCredential, { contextToken: 'odctx_user_a' }),
    ).toBeNull()
  })

  it('returns null when storage is incomplete', () => {
    expect(selectStoredVisitorCredential(null, {})).toBeNull()
    expect(
      selectStoredVisitorCredential(
        { visitorExternalId: 'x', visitorSecret: '' },
        {},
      ),
    ).toBeNull()
  })
})

describe('mergeEmbedInitPayload', () => {
  it('keeps the first identity-bearing init', () => {
    const current: VisitorIdentityPayload = {
      contextToken: 'odctx_a',
      visitor: null,
      initSource: 'sdk',
    }
    const incoming: VisitorIdentityPayload = {
      contextToken: 'odctx_b',
      visitor: { name: 'Ada' },
      initSource: 'sdk',
    }
    expect(mergeEmbedInitPayload(current, incoming)).toBe(current)
  })

  it('allows a later SDK init to replace an empty timeout fallback', () => {
    const current: VisitorIdentityPayload = { initSource: 'timeout' }
    const incoming: VisitorIdentityPayload = {
      contextToken: 'odctx_a',
      visitor: { name: 'Ada' },
      initSource: 'sdk',
    }
    expect(mergeEmbedInitPayload(current, incoming)).toBe(incoming)
  })

  it('uses the incoming payload when nothing is initialized yet', () => {
    const incoming: VisitorIdentityPayload = { contextToken: 'odctx_a', initSource: 'sdk' }
    expect(mergeEmbedInitPayload(null, incoming)).toBe(incoming)
  })

  it('keeps the same object when a later open adds nothing', () => {
    const current: VisitorIdentityPayload = { initSource: 'sdk' }
    expect(mergeEmbedInitPayload(current, { initSource: 'sdk' })).toBe(current)
  })

  it('lets an anonymous sdk init release the timeout fallback', () => {
    const current: VisitorIdentityPayload = { initSource: 'timeout' }
    const incoming: VisitorIdentityPayload = { initSource: 'sdk' }
    expect(mergeEmbedInitPayload(current, incoming)).toBe(incoming)
  })
})

describe('shouldAutoStartConversation', () => {
  it('holds off on the timeout fallback until the grace period elapses', () => {
    expect(shouldAutoStartConversation({ initSource: 'timeout' }, false)).toBe(false)
    expect(shouldAutoStartConversation({ initSource: 'timeout' }, true)).toBe(true)
  })

  it('allows auto-start for sdk/standalone payloads', () => {
    expect(shouldAutoStartConversation({ initSource: 'sdk' }, false)).toBe(true)
    expect(shouldAutoStartConversation({ initSource: 'standalone' }, false)).toBe(true)
    expect(shouldAutoStartConversation({}, false)).toBe(true)
  })
})

describe('resolveVisitorIdentitySource', () => {
  it('labels reused and context-minted sessions', () => {
    expect(
      resolveVisitorIdentitySource({
        reused: true,
        hadStoredCredential: true,
        hasContextToken: false,
      }),
    ).toBe('stored')
    expect(
      resolveVisitorIdentitySource({
        reused: false,
        hadStoredCredential: false,
        hasContextToken: true,
      }),
    ).toBe('context')
    expect(
      resolveVisitorIdentitySource({
        reused: false,
        hadStoredCredential: false,
        hasContextToken: false,
      }),
    ).toBe('fresh')
  })
})
