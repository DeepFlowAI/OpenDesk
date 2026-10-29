import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  router: { push: vi.fn() }, toast: vi.fn(), claim: vi.fn(),
  refetch: vi.fn(), state: { token: 'token', user: { id: 7, tenant_id: 3 } },
}))
vi.mock('next/navigation', () => ({ useRouter: () => mocks.router }))
vi.mock('sonner', () => ({ toast: mocks.toast }))
vi.mock('@/context/locale-store', () => ({ useLocaleStore: () => ({ locale: 'zh' }) }))
vi.mock('@/context/auth-store', () => ({ useAuthStore: (selector: (state: typeof mocks.state) => unknown) => selector(mocks.state) }))
vi.mock('@/service/use-export-tasks', () => ({
  claimExportNotifications: mocks.claim,
  useExportStatus: () => ({ data: { visible: true, unread: 1 }, refetch: mocks.refetch }),
}))
import { ExportTaskEntry } from './export-task-entry'
let root: Root
let host: HTMLDivElement
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  vi.useFakeTimers()
  vi.clearAllMocks()
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  mocks.refetch.mockResolvedValue({ isSuccess: true, data: { server_time: '2026-09-13T00:00:00Z' } })
  mocks.claim.mockResolvedValue({ items: [], server_time: '2026-09-13T00:00:05Z' })
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.useRealTimers() })

it('shows persistent unread results without replaying offline notifications', async () => {
  await act(async () => root.render(<ExportTaskEntry />))
  expect(host.textContent).toContain('有未查看的导出结果')
  expect(mocks.claim).not.toHaveBeenCalled()
  expect(mocks.toast).not.toHaveBeenCalled()
  mocks.claim.mockResolvedValueOnce({ items: [{ id: 'new', status: 'completed', name: { zh: '导出' }, row_count: 2 }], server_time: '2026-09-13T00:00:05Z' })
  await act(async () => vi.advanceTimersByTimeAsync(5000))
  expect(mocks.toast).toHaveBeenCalledTimes(1)
  await act(async () => vi.advanceTimersByTimeAsync(5000))
  expect(mocks.toast).toHaveBeenCalledTimes(1)
})

it('pauses when hidden and establishes a fresh baseline on return', async () => {
  await act(async () => root.render(<ExportTaskEntry />))
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  await act(async () => vi.advanceTimersByTimeAsync(15000))
  expect(mocks.claim).not.toHaveBeenCalled()
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  expect(mocks.refetch).toHaveBeenCalledTimes(2)
  expect(mocks.claim).not.toHaveBeenCalled()
})

it('does not reuse a baseline request that finished after the tab became hidden', async () => {
  let resolveBaseline!: (value: unknown) => void
  mocks.refetch.mockReturnValueOnce(new Promise((resolve) => { resolveBaseline = resolve }))
  await act(async () => root.render(<ExportTaskEntry />))
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  await act(async () => resolveBaseline({ isSuccess: true, data: { server_time: '2026-09-13T00:00:00Z' } }))
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  expect(mocks.refetch).toHaveBeenCalledTimes(2)
  expect(mocks.claim).not.toHaveBeenCalled()
})
