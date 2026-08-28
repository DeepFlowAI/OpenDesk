export type AttachmentPreviewKind = 'image' | 'pdf' | 'document' | 'video'

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'avif'])
const DOCUMENT_EXTENSIONS = new Set([
  'doc',
  'docx',
  'xls',
  'xlsx',
  'ppt',
  'pptx',
  'txt',
  'csv',
  'md',
  'json',
  'xml',
  'html',
  'htm',
])
const VIDEO_EXTENSIONS = new Set(['mp4', 'mov', 'm4v'])
const VIDEO_MIME_TYPES = new Set([
  'video/mp4',
  'video/quicktime',
  'video/x-m4v',
])

export function fileExtension(filename: string | null | undefined): string {
  const cleanName = (filename ?? '').split('?')[0]?.split('#')[0] ?? ''
  const dot = cleanName.lastIndexOf('.')
  if (dot < 0 || dot === cleanName.length - 1) return ''
  return cleanName.slice(dot + 1).toLowerCase()
}

function normalizedMimeType(mimeType: string | null | undefined): string {
  return (mimeType ?? '').split(';', 1)[0].trim().toLowerCase()
}

export function attachmentPreviewKind(
  mimeType: string | null | undefined,
  filename: string | null | undefined,
): AttachmentPreviewKind | null {
  const mime = normalizedMimeType(mimeType)
  const ext = fileExtension(filename)

  if (mime.startsWith('image/') || IMAGE_EXTENSIONS.has(ext)) return 'image'
  if (mime === 'application/pdf' || ext === 'pdf') return 'pdf'
  if (VIDEO_MIME_TYPES.has(mime) || VIDEO_EXTENSIONS.has(ext)) return 'video'
  if (
    mime.includes('word')
    || mime.includes('excel')
    || mime.includes('spreadsheet')
    || mime.includes('powerpoint')
    || mime.includes('presentation')
    || DOCUMENT_EXTENSIONS.has(ext)
  ) {
    return 'document'
  }

  return null
}

export function canPreviewAttachment(
  mimeType: string | null | undefined,
  filename: string | null | undefined,
): boolean {
  const kind = attachmentPreviewKind(mimeType, filename)
  return kind === 'pdf' || kind === 'document' || kind === 'video'
}
