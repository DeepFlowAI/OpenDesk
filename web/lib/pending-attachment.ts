export type PendingAttachmentPayload = {
  schema_version: 1
  pending_attachment: true
  local_url: string
  name: string
  size: number
  mime_type: string
}

export function createPendingAttachmentContent(file: File, localUrl: string): string {
  return JSON.stringify({
    schema_version: 1,
    pending_attachment: true,
    local_url: localUrl,
    name: file.name || 'attachment',
    size: file.size,
    mime_type: file.type || 'application/octet-stream',
  } satisfies PendingAttachmentPayload)
}

export function parsePendingAttachmentContent(content: string): PendingAttachmentPayload | null {
  try {
    const payload = JSON.parse(content) as Partial<PendingAttachmentPayload>
    if (
      payload.schema_version !== 1
      || payload.pending_attachment !== true
      || typeof payload.local_url !== 'string'
      || !payload.local_url.startsWith('blob:')
      || typeof payload.name !== 'string'
      || typeof payload.size !== 'number'
      || typeof payload.mime_type !== 'string'
    ) {
      return null
    }
    return payload as PendingAttachmentPayload
  } catch {
    return null
  }
}
