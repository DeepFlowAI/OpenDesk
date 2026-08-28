import { describe, expect, it } from 'vitest'

import type { CallRecordingItem } from '@/models/call-center'

import { selectDisplayRecording } from './call-record-utils'

function recording(overrides: Partial<CallRecordingItem> & Pick<CallRecordingItem, 'recording_id'>): CallRecordingItem {
  return {
    call_leg_id: null,
    phase: null,
    status: 'completed',
    started_at: null,
    ended_at: null,
    duration_ms: null,
    access_url: null,
    ...overrides,
  }
}

describe('selectDisplayRecording', () => {
  it('returns null when there are no artifacts', () => {
    expect(selectDisplayRecording([])).toBeNull()
    expect(selectDisplayRecording(undefined)).toBeNull()
  })

  it('keeps the full-span ai artifact instead of the bridged fallback', () => {
    const ai = recording({
      recording_id: 'ai',
      phase: 'ai',
      status: 'completed',
      duration_ms: 19184,
      access_url: 'https://example.com/ai.wav',
    })
    const bridged = recording({
      recording_id: 'bridged',
      phase: 'bridged',
      status: 'partial',
      duration_ms: 15000,
      access_url: 'https://example.com/bridged.wav',
    })

    expect(selectDisplayRecording([bridged, ai])?.recording_id).toBe('ai')
  })

  it('prefers a playable bridged artifact when the ai file has no URL', () => {
    const ai = recording({
      recording_id: 'ai',
      phase: 'ai',
      status: 'completed',
      duration_ms: 20000,
    })
    const bridged = recording({
      recording_id: 'bridged',
      phase: 'bridged',
      status: 'partial',
      duration_ms: 4000,
      access_url: 'https://example.com/bridged.wav',
    })

    expect(selectDisplayRecording([ai, bridged])?.recording_id).toBe('bridged')
  })

  it('prefers the longer completed file when both are playable', () => {
    const shortAi = recording({
      recording_id: 'short',
      phase: 'ai',
      status: 'completed',
      duration_ms: 4000,
      access_url: 'https://example.com/short.wav',
    })
    const longBridged = recording({
      recording_id: 'long',
      phase: 'bridged',
      status: 'completed',
      duration_ms: 20000,
      access_url: 'https://example.com/long.wav',
    })

    expect(selectDisplayRecording([shortAi, longBridged])?.recording_id).toBe('long')
  })

  it('falls back to the best non-playable status', () => {
    const failed = recording({ recording_id: 'failed', status: 'failed' })
    const inProgress = recording({ recording_id: 'recording', status: 'recording' })

    expect(selectDisplayRecording([failed, inProgress])?.recording_id).toBe('recording')
  })
})
