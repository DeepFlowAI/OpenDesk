import { act } from 'react'
import { HTTPError } from 'ky'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { TicketExportSource } from '@/models/ticket-export'

const mocks = vi.hoisted(() => ({
  create: vi.fn(), invalidate: vi.fn(), permitted: true, code: 'download_failed', inactive: false,
  fields: [{ id: null, key: 'ticket_number', name: '编号', source: 'system', status: 'active', field_type: 'single_line_text', slot_column: null, options: [] },
    { id: 7, key: 'custom_key', name: '分类', source: 'custom', status: 'active', field_type: 'single_line_text', slot_column: 'str_1', options: [] }],
}))
vi.mock('@/service/use-ticket-export', () => ({ useTicketExportConfig: () => ({ data: { prepared: { fields: mocks.fields, summary: { zh: '全部工单' }, query: {}, language: 'zh' }, token: '{}', signature: 'signed', count: 0 } }) }))
vi.mock('@/service/use-field-definitions', () => ({ useUnifiedFields: () => ({ data: { items: mocks.fields.map((field) => mocks.inactive && field.id === 7 ? { ...field, status: 'inactive' } : field) }, refetch: vi.fn() }) }))
vi.mock('@/context/auth-store', () => ({ useAuthStore: () => ({ id: 1 }) }))
vi.mock('@/utils/permissions', () => ({ hasAllPermissions: () => mocks.permitted }))
vi.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries: mocks.invalidate }) }))
vi.mock('@/service/use-export-tasks', () => ({ createExportTask: mocks.create, exportKeys: ['export-tasks'], exportErrorCode: async () => mocks.code }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('sonner', () => ({ toast: { success: vi.fn() } }))
import { TicketExportDialog } from '@/app/workspace/tickets/ticket-export-dialog'

let host: HTMLDivElement
let root: Root
const source: TicketExportSource = { query: { page: 3, per_page: 20, search: 'applied' }, columns: [{ field_id: 7, field_key: 'custom_key' }], language: 'zh', timezone: 'UTC' }
const button = (name: string) => [...document.querySelectorAll('button')].find((node) => node.textContent === name)!
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  vi.clearAllMocks()
  mocks.permitted = true
  mocks.code = 'download_failed'
  mocks.inactive = false
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })
it('allows header-only results and submits numbered columns through the common task service', async () => {
  const close = vi.fn()
  mocks.create.mockResolvedValueOnce({ id: 'task' })
  await act(async () => root.render(<TicketExportDialog source={source} onClose={close} />))
  expect(document.body.textContent).toContain('仅含表头')
  await act(async () => button('创建导出任务').click())
  expect(mocks.create.mock.calls[0][0]).toMatchObject({ kind: 'ticket', config: { fields: ['key:ticket_number', 'id:7'] } })
  expect(close).toHaveBeenCalledOnce()
})
it('keeps the same submission key and payload when creation is uncertain', async () => {
  mocks.create.mockRejectedValueOnce(new Error('lost')).mockResolvedValueOnce({ id: 'task' })
  await act(async () => root.render(<TicketExportDialog source={source} onClose={vi.fn()} />))
  await act(async () => button('创建导出任务').click())
  expect(button('选择全部').disabled).toBe(true)
  await act(async () => button('确认本次提交').click())
  expect(mocks.create.mock.calls[0][0]).toEqual(mocks.create.mock.calls[1][0])
})
it('blocks submission after permission loss', async () => {
  mocks.permitted = false
  await act(async () => root.render(<TicketExportDialog source={source} onClose={vi.fn()} />))
  expect(button('创建导出任务').disabled).toBe(true)
  expect(mocks.create).not.toHaveBeenCalled()
})

it('clears optional fields while keeping the number first', async () => {
  mocks.create.mockResolvedValueOnce({ id: 'task' })
  await act(async () => root.render(<TicketExportDialog source={source} onClose={vi.fn()} />))
  await act(async () => button('清除可选字段').click())
  await act(async () => button('创建导出任务').click())
  expect(mocks.create.mock.calls[0][0].config.fields).toEqual(['key:ticket_number'])
  expect(mocks.create.mock.calls[0][0].config.prepared).toBe('{}')
})

it('retains unresolved submission state instead of discarding the key on cancel', async () => {
  mocks.create.mockRejectedValueOnce(new Error('lost'))
  const close = vi.fn()
  await act(async () => root.render(<TicketExportDialog source={source} onClose={close} />))
  await act(async () => button('创建导出任务').click())
  expect(button('取消').disabled).toBe(true)
  expect(close).not.toHaveBeenCalled()
})

it('refreshes permissions and disables submit when the server rejects export permission', async () => {
  mocks.code = 'permission_lost'
  mocks.create.mockRejectedValueOnce(new HTTPError(new Response('', { status: 403 }), new Request('https://example.org'), {} as never))
  await act(async () => root.render(<TicketExportDialog source={source} onClose={vi.fn()} />))
  await act(async () => button('创建导出任务').click())
  expect(button('创建导出任务').disabled).toBe(true)
  expect(mocks.invalidate).toHaveBeenCalledWith({ queryKey: ['auth', 'me'] })
})

it('keeps invalid selected fields visible until removed', async () => {
  mocks.inactive = true
  await act(async () => root.render(<TicketExportDialog source={source} onClose={vi.fn()} />))
  expect(document.body.textContent).toContain('部分已选字段不可用')
  expect(button('创建导出任务').disabled).toBe(true)
  await act(async () => button('移除').click())
  expect(button('创建导出任务').disabled).toBe(false)
})
