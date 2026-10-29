import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { ExportTask } from '@/models/export-task'

const mocks = vi.hoisted(() => ({
  viewed: vi.fn().mockResolvedValue(undefined), cancel: vi.fn().mockResolvedValue(undefined),
  download: vi.fn(), invalidate: vi.fn().mockResolvedValue(undefined),
  query: { data: undefined as unknown, dataUpdatedAt: 1, isPlaceholderData: false, isError: false,
    isFetching: false, error: null, refetch: vi.fn() },
}))
vi.mock('@/context/locale-store', () => ({ useLocaleStore: () => ({ locale: 'zh' }) }))
vi.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries: mocks.invalidate }) }))
vi.mock('@/service/use-export-tasks', () => ({
  useExportIdentity: () => '3:7', useExportForeground: () => true, useExportTasks: () => mocks.query,
  exportKeys: ['export-tasks'], markExportsViewed: mocks.viewed, cancelExportTask: mocks.cancel,
  downloadExportTask: mocks.download, exportErrorCode: async () => 'access_changed',
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
import ExportTasksPage from './page'

let root: Root
let host: HTMLDivElement
function item(id: string, status: ExportTask['status']): ExportTask {
  return { id, kind: 'sample', name: { zh: '测试导出' }, business_type: { zh: '测试' }, summary: { zh: '全部匹配项' },
    status, error_code: null, row_count: status === 'completed' ? 1 : null, file_name: 'test.csv', file_size: 5,
    created_at: '2026-09-13T00:00:00Z', expires_at: '2026-09-20T00:00:00Z',
    scope_reduced: false, can_download: status === 'completed', viewed: false }
}
const button = (text: string) => [...document.querySelectorAll('button')].find((node) => node.textContent === text)!

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  vi.clearAllMocks()
  mocks.query.data = { items: [item('done', 'completed'), item('queued', 'pending')], total: 22, page: 1, per_page: 20, pages: 2 }
  mocks.query.isError = false
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })

it('marks only displayed terminal results and keeps rows during refresh failures', async () => {
  await act(async () => root.render(<ExportTasksPage />))
  expect(mocks.viewed).toHaveBeenCalledWith(['done'])
  expect(host.textContent).toContain('已完成')
  mocks.query.isError = true
  await act(async () => root.render(<ExportTasksPage />))
  expect(host.textContent).toContain('更新失败')
  expect(host.textContent).toContain('已完成')
})

it('requires cancellation confirmation and preserves the dialog on polling', async () => {
  await act(async () => root.render(<ExportTasksPage />))
  await act(async () => button('取消').click())
  expect(mocks.cancel).not.toHaveBeenCalled()
  mocks.query.dataUpdatedAt += 1
  await act(async () => root.render(<ExportTasksPage />))
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('取消导出？')
  await act(async () => button('取消导出').click())
  expect(mocks.cancel).toHaveBeenCalledWith('queued')
})

it('removes download after a scope rejection while preserving task status', async () => {
  mocks.download.mockRejectedValue(new Error('denied'))
  await act(async () => root.render(<ExportTasksPage />))
  await act(async () => button('下载').click())
  expect(button('下载')).toBeUndefined()
  expect(host.textContent).toContain('权限或数据范围已变化')
  expect(host.textContent).toContain('已完成')
})

it('downloads directly from the signed storage URL', async () => {
  const url = 'https://storage.example/export?signature=test'
  mocks.download.mockResolvedValue({ url })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.href).toBe(url)
    expect(this.referrerPolicy).toBe('no-referrer')
  })
  try {
    await act(async () => root.render(<ExportTasksPage />))
    await act(async () => button('下载').click())
    expect(mocks.download).toHaveBeenCalledWith('done')
    expect(click).toHaveBeenCalledOnce()
    expect(document.querySelector(`a[href="${url}"]`)).toBeNull()
  } finally {
    click.mockRestore()
  }
})
