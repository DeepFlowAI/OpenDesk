import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getBlob } = vi.hoisted(() => ({ getBlob: vi.fn() }))
vi.mock('@/service/base', () => ({ getBlob }))

import {
  downloadCallReportExport,
  filenameFromContentDisposition,
} from '@/service/use-call-report-export'

describe('call report export service', () => {
  beforeEach(() => {
    getBlob.mockReset()
    getBlob.mockResolvedValue({
      blob: new Blob(['xlsx']),
      headers: new Headers({
        'content-disposition': "attachment; filename*=UTF-8''%E9%80%9A%E8%AF%9D%E6%8A%A5%E8%A1%A8.xlsx",
      }),
    })
  })

  it('exports every matching queue without pagination parameters', async () => {
    const result = await downloadCallReportExport({
      kind: 'queue-list',
      start: '2026-09-01',
      end: '2026-09-02',
      q: '售后',
      queue_type: 'employee_group',
      sort: 'queue_entry_count',
      order: 'desc',
    })

    expect(getBlob).toHaveBeenCalledWith('v1/reports/calls/queues/export', {
      searchParams: {
        start: '2026-09-01',
        end: '2026-09-02',
        q: '售后',
        queue_type: 'employee_group',
        sort: 'queue_entry_count',
        order: 'desc',
      },
    })
    expect(result.filename).toBe('通话报表.xlsx')
  })

  it('builds the employee detail endpoint with its trend', async () => {
    await downloadCallReportExport({
      kind: 'employee-detail',
      start: '2026-09-01',
      end: '2026-09-01',
      employee_id: 17,
      trend: 'hour',
    })

    expect(getBlob).toHaveBeenCalledWith('v1/reports/calls/employees/17/export', {
      searchParams: { start: '2026-09-01', end: '2026-09-01', trend: 'hour' },
    })
  })

  it('falls back when the response has no filename', () => {
    expect(filenameFromContentDisposition(null)).toBe('call-report.xlsx')
  })
})
