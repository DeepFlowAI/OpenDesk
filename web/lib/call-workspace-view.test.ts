import { describe, expect, it } from 'vitest'

import {
  callWorkspaceHref,
  nextAnchorAfterDialNumberChange,
  nextAnchorAfterIdle,
  resolveCallWorkspaceRoute,
  taskDialBlockReason,
} from './call-workspace-view'

describe('resolveCallWorkspaceRoute', () => {
  it('keeps the outbound workbench when a task number is armed', () => {
    expect(
      resolveCallWorkspaceRoute({
        currentView: 'outbound-tasks',
        anchor: null,
        event: { type: 'task-call-armed', phone: '18601123206' },
      }),
    ).toEqual({
      view: 'outbound-tasks',
      anchor: { view: 'outbound-tasks', phone: '18601123206' },
    })
  })

  it('stays on the outbound workbench when that armed number is dialled', () => {
    expect(
      resolveCallWorkspaceRoute({
        currentView: 'outbound-tasks',
        anchor: { view: 'outbound-tasks', phone: '18601123206' },
        event: { type: 'dial-started', destination: '18601123206', callId: 'c1' },
      }),
    ).toEqual({
      view: 'outbound-tasks',
      anchor: { view: 'outbound-tasks', phone: '18601123206', callId: 'c1' },
    })
  })

  it('opens screen-pop for an ad-hoc dial from the workbench', () => {
    expect(
      resolveCallWorkspaceRoute({
        currentView: 'outbound-tasks',
        anchor: null,
        event: { type: 'dial-started', destination: '13800138000', callId: 'c2' },
      }),
    ).toEqual({ view: 'screen-pop', anchor: null })
  })

  it('opens screen-pop when a regular inbound arrives on personal auto-outbound', () => {
    expect(
      resolveCallWorkspaceRoute({
        currentView: 'personal-auto-outbound',
        anchor: { view: 'personal-auto-outbound', callId: 'p0' },
        event: { type: 'incoming', source: 'inbound', callId: 'in2' },
      }),
    ).toEqual({ view: 'screen-pop', anchor: null })
  })

  it('opens screen-pop when an inbound arrives on a workbench', () => {
    expect(
      resolveCallWorkspaceRoute({
        currentView: 'outbound-tasks',
        anchor: { view: 'outbound-tasks', phone: '18601123206' },
        event: { type: 'incoming', source: 'inbound', callId: 'in1' },
      }),
    ).toEqual({ view: 'screen-pop', anchor: null })
  })

  it('stays on personal auto-outbound for that source', () => {
    expect(
      resolveCallWorkspaceRoute({
        currentView: 'personal-auto-outbound',
        anchor: null,
        event: { type: 'incoming', source: 'personal_auto_outbound', callId: 'p1' },
      }),
    ).toEqual({
      view: 'personal-auto-outbound',
      anchor: { view: 'personal-auto-outbound', callId: 'p1' },
    })
  })

  it('keeps the current workspace when a personal auto-outbound call arrives', () => {
    expect(
      resolveCallWorkspaceRoute({
        currentView: 'outbound-tasks',
        anchor: null,
        event: { type: 'incoming', source: 'personal_auto_outbound', callId: 'p2' },
      }),
    ).toEqual({
      view: 'outbound-tasks',
      anchor: { view: 'personal-auto-outbound', callId: 'p2' },
    })
    expect(
      resolveCallWorkspaceRoute({
        currentView: 'screen-pop',
        anchor: null,
        event: { type: 'incoming', source: 'personal_auto_outbound', callId: 'p3' },
      }).view,
    ).toBe('screen-pop')
  })

  it('returns to the anchored workbench when the live recent-call row is clicked', () => {
    expect(
      resolveCallWorkspaceRoute({
        currentView: 'screen-pop',
        anchor: { view: 'outbound-tasks', phone: '18601123206', callId: 'c1' },
        event: { type: 'select-recent', isCurrentLive: true },
      }).view,
    ).toBe('outbound-tasks')
  })

  it('opens screen-pop for a historical recent-call row and keeps the live anchor', () => {
    const anchor = { view: 'outbound-tasks' as const, phone: '18601123206', callId: 'c1' }
    expect(
      resolveCallWorkspaceRoute({
        currentView: 'outbound-tasks',
        anchor,
        event: { type: 'select-recent', isCurrentLive: false },
      }),
    ).toEqual({ view: 'screen-pop', anchor })
  })
})

describe('call workspace anchor helpers', () => {
  it('clears a pending task lock when the dial number is edited', () => {
    expect(
      nextAnchorAfterDialNumberChange({ view: 'outbound-tasks', phone: '18601123206' }, '13800138000'),
    ).toBeNull()
  })

  it('keeps a pending fill through idle, but drops a bound live call', () => {
    expect(nextAnchorAfterIdle({ view: 'outbound-tasks', phone: '18601123206' })).toEqual({
      view: 'outbound-tasks',
      phone: '18601123206',
    })
    expect(
      nextAnchorAfterIdle({ view: 'outbound-tasks', phone: '18601123206', callId: 'c1' }),
    ).toBeNull()
  })

  it('blocks a one-click task dial when the workspace is not ready', () => {
    const ready = {
      phase: 'idle',
      canDialOutbound: true,
      hasUsableDevice: true,
      micChecking: false,
      outboundNumberId: 'pn-1',
    }
    expect(taskDialBlockReason(ready)).toBeNull()
    expect(taskDialBlockReason({ ...ready, outboundNumberId: '' })).toBe('请先选择外呼号码')
    expect(taskDialBlockReason({ ...ready, phase: 'on_call' })).toBe('当前无法发起外呼')
    expect(taskDialBlockReason({ ...ready, agentStatus: 'offline' })).toBe(
      '请先将客服状态切换为就绪',
    )
  })

  it('maps views to workspace hrefs', () => {
    expect(callWorkspaceHref('screen-pop')).toBe('/workspace/call')
    expect(callWorkspaceHref('outbound-tasks')).toBe('/workspace/call?view=outbound-tasks')
  })

  it('carries the task id into the outbound-tasks href', () => {
    expect(
      callWorkspaceHref('outbound-tasks', { view: 'outbound-tasks', phone: '18601123206', taskId: 5 }),
    ).toBe('/workspace/call?view=outbound-tasks&taskId=5')
    expect(callWorkspaceHref('outbound-tasks', { view: 'personal-auto-outbound', taskId: 5 })).toBe(
      '/workspace/call?view=outbound-tasks',
    )
  })

  it('keeps the task id on the anchor through arm and dial', () => {
    const armed = resolveCallWorkspaceRoute({
      currentView: 'outbound-tasks',
      anchor: null,
      event: { type: 'task-call-armed', phone: '18601123206', taskId: 5 },
    })
    expect(armed.anchor).toEqual({ view: 'outbound-tasks', phone: '18601123206', taskId: 5 })

    const dialled = resolveCallWorkspaceRoute({
      currentView: 'outbound-tasks',
      anchor: armed.anchor,
      event: { type: 'dial-started', destination: '18601123206', callId: 'c9' },
    })
    expect(dialled.anchor).toEqual({ view: 'outbound-tasks', phone: '18601123206', callId: 'c9', taskId: 5 })
  })
})
