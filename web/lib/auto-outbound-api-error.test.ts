import { describe, expect, it } from 'vitest'

import { localizeAutoOutboundApiMessage } from '@/lib/auto-outbound-api-error'

describe('auto outbound target deletion errors', () => {
  it.each([
    [
      'Auto outbound target has entered the calling process and cannot be deleted',
      '该对象已进入呼叫流程，无法删除',
      'This target has entered the calling process and cannot be deleted',
    ],
    [
      'Auto outbound task has ended. Outbound targets cannot be deleted',
      '任务已结束，无法删除外呼对象',
      'The task has ended. Outbound targets cannot be deleted',
    ],
    [
      'Auto outbound target not found',
      '外呼对象不存在或已被删除',
      'The outbound target does not exist or has already been deleted',
    ],
    [
      'Permission denied to delete auto outbound target',
      '无权限删除该外呼对象',
      'You do not have permission to delete this outbound target',
    ],
  ])('localizes %s', (message, zh, en) => {
    expect(localizeAutoOutboundApiMessage(message, 'zh')).toBe(zh)
    expect(localizeAutoOutboundApiMessage(message, 'en')).toBe(en)
  })
})
