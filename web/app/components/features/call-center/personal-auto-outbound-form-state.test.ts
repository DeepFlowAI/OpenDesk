import { describe, expect, it } from 'vitest'

import type {
  PersonalAutoOutboundConfig,
  PersonalAutoOutboundSession,
} from '@/models/personal-auto-outbound'

import { resolvePersonalAutoOutboundFormState } from './personal-auto-outbound-form-state'

const config: PersonalAutoOutboundConfig = {
  tasks: [
    { id: 11, name: '列表第一项', callable_count: 1 },
    { id: 22, name: '当前会话任务', callable_count: 1 },
  ],
  phone_numbers: [
    { id: 'first-phone', phone_number: '075589418464' },
    { id: 'session-phone', phone_number: '20260526' },
  ],
  fallback_groups: [
    { id: 31, name: '列表第一组', ready_agent_count: 1 },
    { id: 32, name: '当前会话组', ready_agent_count: 1 },
  ],
  recordings: {},
  has_enabled_prescreen_intents: true,
}

const session: PersonalAutoOutboundSession = {
  id: 41,
  task_id: 22,
  outbound_phone_number_id: 'session-phone',
  fallback_group_id: 32,
  opening_audio_asset_id: 51,
  closing_audio_asset_id: 52,
  configured_concurrency: 6,
  effective_concurrency: 6,
  status: 'running',
  pause_reason: null,
  started_at: '2026-08-15T13:30:00Z',
  paused_at: null,
  stopping_at: null,
  stopped_at: null,
  created_at: '2026-08-15T13:30:00Z',
  updated_at: '2026-08-15T13:30:00Z',
}

describe('resolvePersonalAutoOutboundFormState', () => {
  it('restores every locked field from the active session instead of config defaults', () => {
    expect(resolvePersonalAutoOutboundFormState(config, session, 11)).toEqual({
      taskId: '22',
      phoneId: 'session-phone',
      fallbackGroupId: '32',
      concurrency: 6,
      initialTaskMissing: false,
    })
  })

  it('uses the requested task and first phone only when there is no active session', () => {
    expect(resolvePersonalAutoOutboundFormState(config, null, 22)).toEqual({
      taskId: '22',
      phoneId: 'first-phone',
      fallbackGroupId: '',
      concurrency: 4,
      initialTaskMissing: false,
    })
  })

  it('reports a missing requested task while falling back to the first task', () => {
    expect(resolvePersonalAutoOutboundFormState(config, null, 999)).toEqual({
      taskId: '11',
      phoneId: 'first-phone',
      fallbackGroupId: '',
      concurrency: 4,
      initialTaskMissing: true,
    })
  })
})
