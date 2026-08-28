import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { RecordsPanel } from './auto-outbound-records-panel'
import type { AutoOutboundRecord } from '@/models/auto-outbound-task'

vi.mock('@/app/components/features/call-center/call-record-detail-drawer', () => ({
  CallRecordDetailDrawer: () => null,
}))

function makeRecord(overrides: Partial<AutoOutboundRecord> = {}): AutoOutboundRecord {
  return {
    id: 1,
    phone_number: '13800138000',
    target_id: 10,
    started_at: '2026-08-07T10:00:00+00:00',
    terminal_state: 'answered',
    reception_type: 'ivr',
    agent_name: null,
    duration_ms: 12_000,
    reception_result: null,
    call_record_id: null,
    call_record_public_id: null,
    ...overrides,
  }
}

describe('RecordsPanel', () => {
  it('renders a localized IVR summary instead of raw reception_result JSON', () => {
    const html = renderToStaticMarkup(
      createElement(RecordsPanel, {
        locale: 'zh',
        loading: false,
        canViewCallRecord: false,
        onOpenTarget: () => undefined,
        items: [
          makeRecord({
            reception_result: { exit: 'simulated', degraded: true, collected: {} },
          }),
        ],
      }),
    )

    expect(html).toContain('流程出口：simulated')
    expect(html).not.toContain('{"exit"')
    expect(html).not.toContain('"degraded":true')
  })

  it('renders an em dash when reception_result is null', () => {
    const html = renderToStaticMarkup(
      createElement(RecordsPanel, {
        locale: 'zh',
        loading: false,
        canViewCallRecord: false,
        onOpenTarget: () => undefined,
        items: [makeRecord({ reception_result: null })],
      }),
    )

    expect(html).toMatch(/data-testid="auto-outbound-record-result"[^>]*>—</)
  })

  it('renders call-detail action when the CDR public id is present', () => {
    const html = renderToStaticMarkup(
      createElement(RecordsPanel, {
        locale: 'zh',
        loading: false,
        canViewCallRecord: true,
        onOpenTarget: () => undefined,
        items: [
          makeRecord({
            call_record_id: 88,
            call_record_public_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
          }),
        ],
      }),
    )

    expect(html).toContain('data-testid="auto-outbound-record-call-detail"')
    expect(html).toContain('通话详情')
  })

  it('hides call-detail action when the CDR is not linked', () => {
    const html = renderToStaticMarkup(
      createElement(RecordsPanel, {
        locale: 'zh',
        loading: false,
        canViewCallRecord: true,
        onOpenTarget: () => undefined,
        items: [makeRecord({ call_record_id: null, call_record_public_id: null })],
      }),
    )

    expect(html).not.toContain('data-testid="auto-outbound-record-call-detail"')
  })
})
