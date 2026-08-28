import { describe, expect, it } from 'vitest'

import {
  applyTranscriptEvent,
  transcriptCallIdMatches,
} from './call-transcript-panel'
import type { TranscriptBubble } from './transcript-bubbles'

function bubble(
  partial: Pick<TranscriptBubble, 'id' | 'role' | 'text'> & { final?: boolean },
): TranscriptBubble {
  return { final: false, ...partial }
}

describe('applyTranscriptEvent', () => {
  it('updates the same open bubble when a longer partial arrives', () => {
    const prev = [bubble({ id: 1, role: 'agent', text: '你好' })]
    const next = applyTranscriptEvent(prev, {
      role: 'agent',
      text: '你好世界',
      final: false,
    })
    expect(next).toHaveLength(1)
    expect(next[0]).toMatchObject({
      id: 1,
      role: 'agent',
      text: '你好世界',
      final: false,
    })
  })

  it('keeps the longer text when a shorter partial arrives', () => {
    const prev = [bubble({ id: 1, role: 'agent', text: '你好世界' })]
    const next = applyTranscriptEvent(prev, {
      role: 'agent',
      text: '你',
      final: false,
    })
    expect(next).toHaveLength(1)
    expect(next[0]).toMatchObject({
      id: 1,
      text: '你好世界',
      final: false,
    })
  })

  it('finalizes the same open bubble when a final arrives', () => {
    const prev = [bubble({ id: 1, role: 'agent', text: '你好' })]
    const next = applyTranscriptEvent(prev, {
      role: 'agent',
      text: '你好，请问有什么可以帮您',
      final: true,
    })
    expect(next).toHaveLength(1)
    expect(next[0]).toMatchObject({
      id: 1,
      text: '你好，请问有什么可以帮您',
      final: true,
    })
  })

  it('updates the open agent bubble across alternating speech without orphans', () => {
    let state: TranscriptBubble[] = []
    state = applyTranscriptEvent(state, {
      role: 'agent',
      text: '您好',
      final: false,
    })
    state = applyTranscriptEvent(state, {
      role: 'user',
      text: '我想',
      final: false,
    })
    state = applyTranscriptEvent(state, {
      role: 'agent',
      text: '您好，请说',
      final: false,
    })
    expect(state).toHaveLength(2)
    expect(state[0]).toMatchObject({
      role: 'agent',
      text: '您好，请说',
      final: false,
    })
    expect(state[1]).toMatchObject({
      role: 'user',
      text: '我想',
      final: false,
    })
  })

  it('finalizes the earlier agent bubble after a user barge-in', () => {
    let state: TranscriptBubble[] = []
    state = applyTranscriptEvent(state, {
      role: 'agent',
      text: '您好',
      final: false,
    })
    state = applyTranscriptEvent(state, {
      role: 'user',
      text: '等等',
      final: false,
    })
    state = applyTranscriptEvent(state, {
      role: 'agent',
      text: '您好，请问有什么可以帮您',
      final: true,
    })
    expect(state).toHaveLength(2)
    expect(state[0]).toMatchObject({
      role: 'agent',
      text: '您好，请问有什么可以帮您',
      final: true,
    })
    expect(state[1]).toMatchObject({
      role: 'user',
      text: '等等',
      final: false,
    })
  })

  it('appends a new bubble when a non-prefix shorter partial starts a new utterance', () => {
    // Previous utterance never got its final; the next sentence must not
    // replace its text — the transcript only grows.
    const prev = [bubble({ id: 1, role: 'agent', text: '您好，请问有什么可以帮您' })]
    const next = applyTranscriptEvent(prev, {
      role: 'agent',
      text: '我这边看',
      final: false,
    })
    expect(next).toHaveLength(2)
    expect(next[0]).toMatchObject({
      id: 1,
      text: '您好，请问有什么可以帮您',
      final: true,
    })
    expect(next[1]).toMatchObject({
      role: 'agent',
      text: '我这边看',
      final: false,
    })
  })

  it('creates a finalized bubble when that role has no open bubble', () => {
    const prev = [bubble({ id: 1, role: 'user', text: '你好', final: true })]
    const next = applyTranscriptEvent(prev, {
      role: 'agent',
      text: '您好',
      final: true,
    })
    expect(next).toHaveLength(2)
    expect(next[1]).toMatchObject({
      role: 'agent',
      text: '您好',
      final: true,
    })
  })

  it('assigns unique ids within the list for new bubbles', () => {
    const prev = [
      bubble({ id: 3, role: 'user', text: 'a', final: true }),
      bubble({ id: 7, role: 'agent', text: 'b', final: true }),
    ]
    const next = applyTranscriptEvent(prev, {
      role: 'user',
      text: 'c',
      final: false,
    })
    const ids = next.map((b) => b.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(next[2].id).toBe(8)
  })
})

describe('transcriptCallIdMatches', () => {
  it('matches when the event call id equals callId', () => {
    expect(
      transcriptCallIdMatches({
        eventCallId: 'sip-customer',
        callId: 'sip-customer',
        sourceCallId: undefined,
      }),
    ).toBe(true)
  })

  it('matches when the event call id equals sourceCallId', () => {
    expect(
      transcriptCallIdMatches({
        eventCallId: 'sip-customer',
        callId: 'internal:offer-1',
        sourceCallId: 'sip-customer',
      }),
    ).toBe(true)
  })

  it('does not match when neither callId nor sourceCallId equals the event', () => {
    expect(
      transcriptCallIdMatches({
        eventCallId: 'other-leg',
        callId: 'internal:offer-1',
        sourceCallId: 'sip-customer',
      }),
    ).toBe(false)
  })

  it('does not match sourceCallId when it is empty', () => {
    expect(
      transcriptCallIdMatches({
        eventCallId: 'sip-customer',
        callId: 'internal:offer-1',
        sourceCallId: null,
      }),
    ).toBe(false)
    expect(
      transcriptCallIdMatches({
        eventCallId: 'sip-customer',
        callId: 'internal:offer-1',
        sourceCallId: '',
      }),
    ).toBe(false)
  })
})
