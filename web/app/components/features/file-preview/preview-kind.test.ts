import { describe, expect, it } from 'vitest'

import { attachmentPreviewKind, canPreviewAttachment } from './preview-kind'

describe('attachmentPreviewKind', () => {
  it('classifies office and text files as Jit documents', () => {
    expect(attachmentPreviewKind('application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'spec.docx')).toBe('document')
    expect(attachmentPreviewKind('text/plain', 'notes.txt')).toBe('document')
    expect(attachmentPreviewKind('application/pdf', 'manual.pdf')).toBe('pdf')
  })

  it('classifies iPhone camera videos as native video, not Jit documents', () => {
    expect(attachmentPreviewKind('video/quicktime', 'IMG_0001.MOV')).toBe('video')
    expect(attachmentPreviewKind('video/mp4', '80871305038__A36ACF83-BCAC-4193-A.mp4')).toBe('video')
  })

  it('does not preview zip, unknown, or extensionless binaries', () => {
    expect(attachmentPreviewKind('application/zip', 'bundle.zip')).toBeNull()
    expect(attachmentPreviewKind('application/octet-stream', '80871305038__A36ACF83-BCAC-4193-A')).toBeNull()
    expect(canPreviewAttachment('application/zip', 'bundle.zip')).toBe(false)
    expect(canPreviewAttachment('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'data.xlsx')).toBe(true)
  })
})
