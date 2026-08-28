import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { UserInfo } from '@/models/auth'

const mocks = vi.hoisted(() => {
  const values = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value)
      },
      removeItem: (key: string) => {
        values.delete(key)
      },
      clear: () => {
        values.clear()
      },
    },
  })
  return { mutate: vi.fn() }
})

vi.mock('@/service/use-auth', () => ({
  useUpdateCurrentUserPreferences: () => ({ mutate: mocks.mutate }),
}))

import { useAuthStore } from '@/context/auth-store'
import { useWorkspaceCallOutboundPreference } from './use-workspace-call-outbound-preference'

function user(partial: Partial<UserInfo> = {}): UserInfo {
  return {
    id: 42,
    username: 'agent',
    name: 'Agent',
    display_name: null,
    avatar: null,
    roles: [],
    tenant_id: 7,
    role_ids: [],
    permissions: [],
    data_scopes: {},
    is_super_admin: false,
    group_ids: [],
    preferences: {},
    default_language: 'system',
    ...partial,
  }
}

function Probe() {
  const { preferredId, savePreferredId } = useWorkspaceCallOutboundPreference()
  return createElement(
    'button',
    {
      type: 'button',
      'data-preferred': preferredId ?? '',
      onClick: () => savePreferredId('pn-2'),
    },
    'save',
  )
}

describe('useWorkspaceCallOutboundPreference', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true
    mocks.mutate.mockReset()
    localStorage.clear()
    useAuthStore.setState({ user: null, token: null })
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(async () => {
    await act(async () => root.unmount())
    container.remove()
  })

  it('reads the saved outbound number id from employee preferences', async () => {
    useAuthStore.setState({
      user: user({
        preferences: { workspace_call: { outbound_number_id: 'pn-2' } },
      }),
      token: 't',
    })

    await act(async () => {
      root.render(createElement(Probe))
    })

    expect(container.querySelector('button')?.getAttribute('data-preferred')).toBe('pn-2')
  })

  it('writes the selected number into preferences and keeps workspace_chat', async () => {
    useAuthStore.setState({
      user: user({
        preferences: {
          workspace_chat: { auxiliary_panel_width: 420 },
          workspace_call: { outbound_number_id: 'pn-1' },
        },
      }),
      token: 't',
    })

    await act(async () => {
      root.render(createElement(Probe))
    })
    await act(async () => {
      container.querySelector('button')?.click()
    })

    expect(useAuthStore.getState().user?.preferences).toEqual({
      workspace_chat: { auxiliary_panel_width: 420 },
      workspace_call: { outbound_number_id: 'pn-2' },
    })
    expect(mocks.mutate).toHaveBeenCalledWith(
      {
        workspace_chat: { auxiliary_panel_width: 420 },
        workspace_call: { outbound_number_id: 'pn-2' },
      },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    )
  })

  it('does not persist when the preferred number is unchanged', async () => {
    useAuthStore.setState({
      user: user({
        preferences: { workspace_call: { outbound_number_id: 'pn-2' } },
      }),
      token: 't',
    })

    await act(async () => {
      root.render(createElement(Probe))
    })
    await act(async () => {
      container.querySelector('button')?.click()
    })

    expect(mocks.mutate).not.toHaveBeenCalled()
  })
})
