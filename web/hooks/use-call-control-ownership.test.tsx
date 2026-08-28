import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { EmbeddedControlLease } from '@/models/embedded-call'

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
  return { updateEmbeddedControl: vi.fn() }
})

vi.mock('@/service/use-embedded-call', () => ({
  updateEmbeddedControl: mocks.updateEmbeddedControl,
}))

import { useCallControlOwnership } from './use-call-control-ownership'

function Probe() {
  const ownership = useCallControlOwnership(true)
  return (
    <div
      data-conflict={String(ownership.hasControlConflict)}
      data-owner={String(ownership.isOwner)}
    />
  )
}

function lease(overrides: Partial<EmbeddedControlLease>): EmbeddedControlLease {
  return {
    is_owner: false,
    owner_instance_id: 'embed_other',
    owner_surface: 'embedded_call',
    lease_token: null,
    expires_in: 15,
    ...overrides,
  }
}

describe('useCallControlOwnership', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true
    vi.useFakeTimers()
    sessionStorage.clear()
    localStorage.clear()
    mocks.updateEmbeddedControl.mockReset()
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(async () => {
    await act(async () => {
      try {
        root.unmount()
      } catch {
        // Test already unmounted the root to exercise cleanup.
      }
    })
    container.remove()
    localStorage.clear()
    vi.useRealTimers()
  })

  it('automatically acquires control after the previous window lease expires', async () => {
    let acquireCount = 0
    mocks.updateEmbeddedControl.mockImplementation((action: string) => {
      if (action === 'acquire') {
        acquireCount += 1
        return Promise.resolve(
          acquireCount === 1
            ? lease({})
            : lease({
                is_owner: true,
                owner_instance_id: 'workspace_current',
                owner_surface: 'opendesk_workspace',
                lease_token: 'lease_current',
              }),
        )
      }
      return Promise.resolve(lease({}))
    })

    await act(async () => root.render(<Probe />))
    await act(async () => Promise.resolve())

    expect(container.firstElementChild?.getAttribute('data-conflict')).toBe('true')
    expect(container.firstElementChild?.getAttribute('data-owner')).toBe('false')

    await act(async () => vi.advanceTimersByTimeAsync(5000))

    expect(acquireCount).toBe(2)
    expect(container.firstElementChild?.getAttribute('data-conflict')).toBe('false')
    expect(container.firstElementChild?.getAttribute('data-owner')).toBe('true')
  })

  it('does not report another window when a heartbeat fails transiently', async () => {
    let acquireCount = 0
    mocks.updateEmbeddedControl.mockImplementation((action: string) => {
      if (action === 'acquire') {
        acquireCount += 1
        return Promise.resolve(
          lease({
            is_owner: true,
            owner_instance_id: 'workspace_current',
            owner_surface: 'opendesk_workspace',
            lease_token: `lease_${acquireCount}`,
          }),
        )
      }
      if (action === 'heartbeat') return Promise.reject(new Error('network unavailable'))
      return Promise.resolve(lease({}))
    })

    await act(async () => root.render(<Probe />))
    await act(async () => Promise.resolve())
    expect(container.firstElementChild?.getAttribute('data-owner')).toBe('true')

    await act(async () => vi.advanceTimersByTimeAsync(5000))

    expect(container.firstElementChild?.getAttribute('data-conflict')).toBe('false')
    expect(container.firstElementChild?.getAttribute('data-owner')).toBe('true')

    await act(async () => vi.advanceTimersByTimeAsync(5000))

    expect(acquireCount).toBe(2)
    expect(container.firstElementChild?.getAttribute('data-owner')).toBe('true')
  })

  it('does not treat another workspace tab as a control conflict', async () => {
    mocks.updateEmbeddedControl.mockResolvedValue(
      lease({
        owner_instance_id: 'workspace_other',
        owner_surface: 'opendesk_workspace',
      }),
    )

    await act(async () => root.render(<Probe />))
    await act(async () => Promise.resolve())

    expect(container.firstElementChild?.getAttribute('data-conflict')).toBe('false')
    expect(container.firstElementChild?.getAttribute('data-owner')).toBe('true')
  })

  it('does not release control after the session is already gone', async () => {
    mocks.updateEmbeddedControl.mockResolvedValue(
      lease({
        is_owner: true,
        owner_instance_id: 'workspace_current',
        owner_surface: 'opendesk_workspace',
        lease_token: 'lease_current',
      }),
    )

    await act(async () => root.render(<Probe />))
    await act(async () => Promise.resolve())
    await act(async () => root.unmount())
    await act(async () => Promise.resolve())

    expect(mocks.updateEmbeddedControl).not.toHaveBeenCalledWith('release', expect.anything())
  })

  it('swallows release failures while the workspace is still signed in', async () => {
    localStorage.setItem('auth_token', 'still-valid')
    mocks.updateEmbeddedControl.mockImplementation((action: string) => {
      if (action === 'acquire') {
        return Promise.resolve(
          lease({
            is_owner: true,
            owner_instance_id: 'workspace_current',
            owner_surface: 'opendesk_workspace',
            lease_token: 'lease_current',
          }),
        )
      }
      if (action === 'release') return Promise.reject(new Error('401'))
      return Promise.resolve(lease({}))
    })

    await act(async () => root.render(<Probe />))
    await act(async () => Promise.resolve())
    await act(async () => root.unmount())
    await act(async () => Promise.resolve())

    expect(mocks.updateEmbeddedControl).toHaveBeenCalledWith(
      'release',
      expect.objectContaining({ leaseToken: 'lease_current' }),
    )
  })
})
