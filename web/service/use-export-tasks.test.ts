import { expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('./base', () => ({ ...mocks, getBlob: vi.fn() }))
import { createExportTask } from './use-export-tasks'

it('reconciles an uncertain submission without creating another job', async () => {
  const body = { idempotency_key: 'fixed-key', kind: 'test', config: {}, language: 'zh' as const, timezone: 'UTC' }
  mocks.post.mockRejectedValueOnce(new Error('response lost'))
  mocks.get.mockResolvedValueOnce({ id: 'created' })
  expect(await createExportTask(body)).toEqual({ id: 'created' })
  expect(mocks.post).toHaveBeenCalledTimes(1)
  expect(mocks.get).toHaveBeenCalledWith('v1/exports/by-key/fixed-key', { retry: 0 })
})
